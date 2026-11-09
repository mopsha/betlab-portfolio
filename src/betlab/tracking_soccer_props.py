"""Every FanDuel soccer prop rung we see: data/ledger/soccer_prop_lines.csv (Mike, 2026-10-10).

One row per (match, player, stat, line): shots and shots on target ("2+ shots" is line 1.5),
anytime scorer (line 0.5 goals) and assists (0.5). FanDuel posts only overs, so each row is the
bet we could make. Next to FanDuel's price:

- **fd_mean / fd_margin:** FanDuel's own ladder read as a negative binomial plus a margin
  (models/props_soccer.ladder_fit), and **p_fd_fair**, its chance at this rung with the margin off.
- **mkt_mean / p_market:** the other books' view, the median of their ladder fits (BetRivers posts
  shots and shots on target; scorer prices come from many books, and Pinnacle's two-sided price
  is the sharp one when it posts). How many books: `books`.
- **starter / team:** from ESPN's announced lineup at the pull (about an hour before kickoff).
- **p_model / model_mean:** the ML model's chance once it exists (no weight until it beats the
  market on these rows).

The first look keeps its prices; later looks before kickoff update `last_fd_price`. After the
match the row is graded from ESPN's box score: the player's count (`actual`), minutes, and
won / lost, or void when he didn't play (FanDuel voids those). Nothing here is a pick.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config
from betlab import odds_math as om
from betlab.models import props_soccer as PS

PATH = config.DATA_DIR / "ledger" / "soccer_prop_lines.csv"
COLUMNS = ["line_id", "league", "event_id", "espn_id", "commence_time", "matchup", "player", "team", "starter",
           "stat", "line", "fd_price", "fd_mean", "fd_margin", "p_fd_fair", "br_price", "p_market", "mkt_mean", "books",
           "p_model", "model_mean", "first_seen", "updated_at", "last_fd_price", "actual", "minutes", "status",
           "graded_at", "fd_link"]
TEXT = ["line_id", "league", "event_id", "espn_id", "commence_time", "matchup", "player", "team", "stat",
        "first_seen", "updated_at", "status", "graded_at"]
ACTUAL = {"shots": "shots", "sot": "sot", "scorer": "goals", "assists": "assists", "ga": "ga"}
TARGET = {"scorer": "goals", "assists": "assists", "ga": "ga"}     # the model's target for a one-rung stat


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT}).reindex(columns=COLUMNS)


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df.reindex(columns=COLUMNS)).to_csv(PATH, index=False)


def _fits(g: pd.DataFrame, stat: str) -> dict[str, tuple[float, float]]:
    """Each book's ladder fit for one player and stat."""
    out = {}
    for book, b in g.groupby("bookmaker"):
        b = b[b["outcome"] == "Over"].drop_duplicates("point")
        f = PS.ladder_fit(b["point"], b["price"], PS.SIZE[stat]) if len(b) >= 2 else None
        if f:
            out[book] = f
    return out


def _scorer_market(g: pd.DataFrame) -> tuple[float | None, int]:
    """P(scores): Pinnacle's no-vig two-way when it posts, else none (the other books are one-sided
    with unknown margins; their prices stay in the snapshot)."""
    pin = g[g["bookmaker"] == "pinnacle"]
    y, n = pin[pin["outcome"] == "Yes"], pin[pin["outcome"] == "No"]
    if len(y) and len(n):
        return om.no_vig_two_way(float(y["price"].iloc[0]), float(n["price"].iloc[0]))[0], 1
    return None, 0


def rows(props: pd.DataFrame, league: str, info: dict, squad: pd.DataFrame | None = None,
         model: dict | None = None, dispersion: dict | None = None) -> list[dict]:
    """Tracker rows for one match's props pull. info: {event_id, commence_time, matchup, espn_id};
    model: {ESPN player id: {"shots": mean, "sot": mean}} (cards/props_soccer.means) with its
    negative binomial `dispersion` per stat."""
    from betlab.sources.espn_soccer import match_player

    out = []
    props = props[props["market"].isin(PS.STATS)]
    for (market, player), g in props.groupby(["market", "player"]):
        stat = PS.STATS[market]
        fd = g[(g["bookmaker"] == "fanduel") & g["outcome"].isin(["Over", "Yes"])]
        if fd.empty:
            continue
        sq = match_player(player, squad) if squad is not None else None
        base = {"league": league, "event_id": info["event_id"], "espn_id": info.get("espn_id"),
                "commence_time": info["commence_time"], "matchup": info["matchup"], "player": player,
                "team": None if sq is None else sq["team"], "starter": None if sq is None else bool(sq["starter"]),
                "stat": stat}
        if stat in PS.SIZE:
            fits = _fits(g, stat)
            fdf = fits.pop("fanduel", None)
            others = [m for m, _ in fits.values()]
            mkt_mean = float(np.median(others)) if others else None
            mm = (model or {}).get(str(sq["player_id"])) if sq is not None else None
            mean = mm.get(stat) if mm else None
            for r in fd.drop_duplicates("point").itertuples():
                line = float(r.point)
                br = g[(g["bookmaker"] == "betrivers") & (g["point"] == r.point) & (g["outcome"] == "Over")]
                out.append(base | {"line": line, "fd_price": float(r.price),
                                   "fd_mean": None if fdf is None else fdf[0], "fd_margin": None if fdf is None else fdf[1],
                                   "p_fd_fair": PS.p_line(None if fdf is None else fdf[0], line, PS.SIZE[stat]),
                                   "br_price": float(br["price"].iloc[0]) if len(br) else None,
                                   "mkt_mean": mkt_mean, "p_market": PS.p_line(mkt_mean, line, PS.SIZE[stat]),
                                   "books": len(others), "model_mean": mean,
                                   "p_model": None if mean is None else PS.p_line(mean, line, dispersion[stat])})
        else:                                  # scorer, assists, score or assist: one rung (0.5)
            p_mkt, n = _scorer_market(g) if stat == "scorer" else (None, 0)
            target = TARGET[stat]
            mm = (model or {}).get(str(sq["player_id"])) if sq is not None else None
            mean = mm.get(target) if mm else None
            size = (dispersion or {}).get(target, float("inf"))
            out.append(base | {"line": 0.5, "fd_price": float(fd["price"].iloc[0]), "p_market": p_mkt, "books": n,
                               "fd_link": fd["link"].iloc[0] if "link" in fd and pd.notna(fd["link"].iloc[0]) else None,
                               "model_mean": mean, "p_model": None if mean is None else PS.p_line(mean, 0.5, size)})
    return out


def record(new: list[dict], asof: pd.Timestamp) -> int:
    """Add the first look at each rung; a later look before kickoff updates its last price."""
    now = asof.isoformat(timespec="seconds")
    df = load().set_index("line_id", drop=False)
    add, n = [], 0
    for r in new:
        if pd.Timestamp(r["commence_time"]) <= asof:
            continue
        lid = f"{r['event_id']}|{r['player']}|{r['stat']}|{r['line']:g}"
        if lid in df.index:
            df.at[lid, "updated_at"], df.at[lid, "last_fd_price"] = now, r["fd_price"]
            for k in ("team", "starter", "espn_id", "model_mean", "p_model"):   # lineups can come out between looks
                if pd.isna(df.at[lid, k]) and r.get(k) is not None:
                    df.at[lid, k] = r[k]
        else:
            add.append({c: np.nan for c in COLUMNS} | {k: v for k, v in r.items() if k in COLUMNS}
                       | {"line_id": lid, "first_seen": now, "updated_at": now, "last_fd_price": r["fd_price"],
                          "status": "open"})
        n += 1
    if add:
        df = pd.concat([df, pd.DataFrame(add).set_index("line_id", drop=False)])
    save(df.reset_index(drop=True))
    return n


def grade(now: pd.Timestamp | None = None, box_for=None) -> int:
    """Fill finished matches from ESPN's box scores (3+ hours after kickoff). box_for(league,
    espn_id) -> the player box (tests pass a fake)."""
    from betlab.sources import espn_soccer as E

    now = now or pd.Timestamp.now(tz="UTC")
    df = load()
    todo = df[(df["status"] == "open")
              & (pd.to_datetime(df["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=3))]
    if todo.empty:
        return 0
    box_for = box_for or (lambda lg, eid: E.box(E.summary(E.SLUGS[lg], eid), lg))
    stamp, n = now.isoformat(timespec="seconds"), 0
    for (league, eid), g in todo.groupby(["league", "event_id"]):
        espn = g["espn_id"].dropna()
        espn_id = str(espn.iloc[0]) if len(espn) else None
        if espn_id is None:
            home, away = str(g["matchup"].iloc[0]).split(" @ ")[::-1] if " @ " in str(g["matchup"].iloc[0]) else (None, None)
            if home:
                try:
                    espn_id = E.find_event(league, home, away, g["commence_time"].iloc[0])
                except Exception:  # noqa: BLE001 - try again tomorrow
                    espn_id = None
        if espn_id is None:
            continue
        try:
            b = box_for(league, espn_id)
        except Exception:  # noqa: BLE001 - ESPN down: grade tomorrow
            continue
        if b is None or b.empty:
            continue
        for i, r in g.iterrows():
            p = E.match_player(r["player"], b)
            mins = 0 if p is None else int(p["minutes"] or 0)
            if p is None:
                val = None
            elif r["stat"] == "ga":
                val = (p["goals"] or 0) + (p["assists"] or 0)
            else:
                val = p[ACTUAL[r["stat"]]]
            if mins == 0 or val is None or pd.isna(val):
                status = "void"
            else:
                status = "won" if float(val) > float(r["line"]) else "lost"
            df.loc[i, ["espn_id", "actual", "minutes", "status", "graded_at"]] = [espn_id, val, mins, status, stamp]
            n += 1
    save(df)
    return n


# p_market is the other books' chance (BetRivers on shots and on target; scorer: several books, Pinnacle's when posted)
SOURCES = {"p_model": "model", "p_fd_fair": "fanduel", "p_market": "other_books"}


def summary(df: pd.DataFrame | None = None) -> dict:
    """Log loss on graded rungs, by stat, always on the same rungs for the sources compared (Oct 20: each source was
    scored on its own rungs, so the model's 0.427 on shots sat beside FanDuel's 0.470 on a different 7,726). `same`:
    the rungs every source prices; `model_vs_<book>`: the model and one book on the rungs both price (BetRivers
    prices about half); a stat with one source (assists: the model only) gets just that source's log loss. Lower is
    better."""
    df = load() if df is None else df
    g = df[df["status"].isin(["won", "lost"])]
    out = {"lines": int(len(df)), "graded": int(len(g))}

    def ll(p, y):
        p = np.clip(p.astype(float).to_numpy(), 1e-4, 1 - 1e-4)
        return round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 4)

    for stat, s in g.groupby("stat"):
        y = (s["status"] == "won").astype(float)
        entry = {"n": int(len(s)), "hit_rate": round(float(y.mean()), 3)}
        cols = [c for c in SOURCES if c in s and s[c].notna().any()]
        if len(cols) == 1:
            m = s[cols[0]].notna()
            entry[SOURCES[cols[0]]] = {"n": int(m.sum()), "log_loss": ll(s.loc[m, cols[0]], y[m].to_numpy())}
        if len(cols) > 1:
            m = s[cols].notna().all(axis=1)
            if m.any():
                entry["same"] = {"n": int(m.sum()), **{SOURCES[c]: ll(s.loc[m, c], y[m].to_numpy()) for c in cols}}
        for c in cols:
            if c == "p_model" or "p_model" not in cols:
                continue
            m = s["p_model"].notna() & s[c].notna()
            if m.any():
                entry[f"model_vs_{SOURCES[c]}"] = {"n": int(m.sum()), "model": ll(s.loc[m, "p_model"], y[m].to_numpy()),
                                                   SOURCES[c]: ll(s.loc[m, c], y[m].to_numpy())}
        out[stat] = entry
    return out
