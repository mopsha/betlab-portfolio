"""College football moneyline dogs at 20-40%: data/ledger/cfb_dogs.csv. Tracked, never a pick.

On 2021-26 consensus closes (docs/MODELS.md, "Market leans in every sport", Oct 26), college moneyline dogs that the
power de-vig put at 20-40% won 33.0% against 29.8% priced, in all six seasons, but at +2.2% ROI with an SE of 3.1%.
This logs every such dog from the live pulls to see whether it holds against Pinnacle's own close (Mike, Oct 26).

One row per (game, dog): Pinnacle's no-vig chance (power; LowVig, then BetOnline, when Pinnacle has no price) and
FanDuel's, DraftKings' and Novig's prices when first seen at 20-40%, then the same at every later card run until
kickoff; the last look is the close. A close from the pull the dog was first seen in is no close (CLAUDE.md), so
`clv` stays empty then. Grading takes the score from CFBD's games.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab import config
from betlab import odds_math as om
from betlab.timefmt import utc_starts

PATH = config.DATA_DIR / "ledger" / "cfb_dogs.csv"
BAND = (0.20, 0.40)                                  # the dog's no-vig chance at first sight
SHARP = ("pinnacle", "lowvig", "betonlineag")         # the reference, in order
BOOKS = ("fanduel", "draftkings", "novig")
COLUMNS = (["line_id", "event_id", "kickoff", "home", "away", "dog", "side", "first_seen", "first_snap", "first_p",
            "first_source"] + [f"first_{b}" for b in BOOKS] + ["first_novig_limit", "updated_at", "last_snap", "last_p",
            "last_source"] + [f"last_{b}" for b in BOOKS] + ["game_id", "won", "clv", "status", "graded_at"])
TEXT = ["line_id", "event_id", "kickoff", "home", "away", "dog", "side", "first_seen", "first_snap", "first_source",
        "updated_at", "last_snap", "last_source", "game_id", "status", "graded_at"]


def line_id(event_id, dog) -> str:
    return hashlib.sha1(f"{event_id}|{dog}".encode()).hexdigest()[:12]


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT})


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def _prices(ev: pd.DataFrame, book: str, home: str, away: str) -> tuple[float, float] | None:
    h2h = ev[(ev["market"] == "h2h") & (ev["bookmaker"] == book)]
    ph, pa = h2h.loc[h2h["outcome"] == home, "price"], h2h.loc[h2h["outcome"] == away, "price"]
    if ph.empty or pa.empty:
        return None
    return float(ph.iloc[0]), float(pa.iloc[0])


def sides(snap: pd.DataFrame) -> list[dict]:
    """Both sides of every game in a snapshot with a sharp two-way moneyline: the side's power no-vig chance, its
    source, and FanDuel's, DraftKings' and Novig's prices (Novig's bet limit too)."""
    out = []
    for event_id, ev in snap.groupby("event_id"):
        home, away = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        ref = next(((b, tw) for b in SHARP if (tw := _prices(ev, b, home, away))), None)
        if ref is None:
            continue
        p_home = om.devig(list(ref[1]), "power")[0]
        books = {b: _prices(ev, b, home, away) for b in BOOKS}
        nv = ev[(ev["market"] == "h2h") & (ev["bookmaker"] == "novig")]
        for side, team, p, i in (("home", home, p_home, 0), ("away", away, 1 - p_home, 1)):
            lim = nv.loc[nv["outcome"] == team, "bet_limit"] if "bet_limit" in nv else pd.Series(dtype=float)
            out.append({"event_id": event_id, "kickoff": ev["commence_time"].iloc[0], "home": home, "away": away,
                        "dog": team, "side": side, "p": p, "source": ref[0],
                        **{b: (books[b][i] if books[b] else None) for b in BOOKS},
                        "novig_limit": float(lim.iloc[0]) if len(lim) and pd.notna(lim.iloc[0]) else None,
                        "snap": str(ev["snapshot_ts"].iloc[0])})
    return out


def record(snap: pd.DataFrame | None, asof: pd.Timestamp) -> int:
    """Log new 20-40% dogs from games not yet started and update the ones already logged; returns rows touched."""
    if snap is None or snap.empty:
        return 0
    now = asof.isoformat(timespec="seconds")
    df = load().set_index("line_id", drop=False)
    n = 0
    for s in sides(snap):
        if pd.Timestamp(s["kickoff"]) <= asof:
            continue
        lid = line_id(s["event_id"], s["dog"])
        last = {"updated_at": now, "last_snap": s["snap"], "last_p": round(s["p"], 4), "last_source": s["source"],
                **{f"last_{b}": s[b] for b in BOOKS}}
        if lid in df.index:
            if df.at[lid, "status"] == "open":
                for k, v in last.items():
                    df.at[lid, k] = v
                n += 1
            continue
        if not BAND[0] <= s["p"] < BAND[1]:
            continue
        new = {"line_id": lid, "event_id": s["event_id"], "kickoff": s["kickoff"], "home": s["home"], "away": s["away"],
               "dog": s["dog"], "side": s["side"], "first_seen": now, "first_snap": s["snap"],
               "first_p": round(s["p"], 4), "first_source": s["source"], **{f"first_{b}": s[b] for b in BOOKS},
               "first_novig_limit": s["novig_limit"], "status": "open", **last}
        df = pd.concat([df, pd.DataFrame([new]).set_index("line_id", drop=False)])
        n += 1
    for c in COLUMNS:
        if c not in df:
            df[c] = np.nan
    save(df.reset_index(drop=True).sort_values(["kickoff", "event_id", "dog"]))
    return n


def grade(games: pd.DataFrame | None = None, names: dict | None = None) -> int:
    """Settle dogs whose games are final in CFBD's games (matched by both schools and the kickoff's ET date, a day
    either way); clv = Pinnacle's closing chance minus the first, only when the close came from a later pull."""
    from betlab.sources import cfbd

    df = load()
    todo = df[df["status"] == "open"]
    if todo.empty:
        return 0
    games = cfbd.games() if games is None else games
    names = cfbd.team_names() if names is None else names
    done = games[games["home_pts"].notna() & games["away_pts"].notna()]
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for i, r in todo.iterrows():
        day = pd.Timestamp(r["kickoff"]).tz_convert("America/New_York").tz_localize(None).normalize()
        h, a = names.get(r["home"]), names.get(r["away"])
        g = done[(done["home_team"] == h) & (done["away_team"] == a) & ((done["date"] - day).abs() <= pd.Timedelta(days=1))]
        if g.empty:
            continue
        g = g.iloc[0]
        if g["home_pts"] == g["away_pts"]:
            continue
        home_won = g["home_pts"] > g["away_pts"]
        df.at[i, "game_id"] = str(g["game_id"])
        df.at[i, "won"] = float(home_won if r["side"] == "home" else not home_won)
        later = str(r["last_snap"]) > str(r["first_snap"])
        df.at[i, "clv"] = round(float(r["last_p"]) - float(r["first_p"]), 4) if later else np.nan
        df.at[i, "status"] = "graded"
        df.at[i, "graded_at"] = stamp
        n += 1
    if n:
        save(df)
    return n


def summary(df: pd.DataFrame | None = None) -> dict:
    """Graded dogs: won vs Pinnacle's first and closing chance, CLV (chance points), and units at each book's first
    price (a book without a price is left out of its own count)."""
    df = load() if df is None else df
    g = df[df["status"] == "graded"] if len(df) else df
    if g.empty:
        return {"n": 0}
    won = g["won"].astype(float)
    out = {"n": int(len(g)), "won": int(won.sum()), "expected_first": round(float(g["first_p"].astype(float).sum()), 1),
           "expected_close": round(float(g["last_p"].astype(float).sum()), 1),
           "clv_pts": round(100 * float(g["clv"].astype(float).mean()), 2) if g["clv"].notna().any() else None}
    for b in BOOKS:
        price = g[f"first_{b}"].astype(float)
        ok = price.notna()
        dec = price[ok].map(om.american_to_decimal)
        out[f"units_{b}"] = round(float(np.where(won[ok] == 1, dec - 1, -1.0).sum()), 2) if ok.any() else None
        out[f"n_{b}"] = int(ok.sum())
    return out
