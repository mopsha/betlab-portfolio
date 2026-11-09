"""Every FanDuel soccer line BetLab priced: data/ledger/soccer_lines.csv.

One row per (match, outcome): FanDuel's price and the sharp no-vig chance when first
seen and at the latest pricing before kickoff, then the result and the sharp closing
chance from football-data.co.uk (Pinnacle, Betfair Exchange or the books' average).
This is the soccer ML layer's training set and the test of whether FanDuel lags the
sharp market in soccer (CLV of every line, not just picks). Nothing here is a pick.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config

PATH = config.DATA_DIR / "ledger" / "soccer_lines.csv"
COLUMNS = ["line_id", "league", "event_id", "commence_time", "home", "away", "side",
           "first_seen", "first_price", "first_p_market", "updated_at", "fd_price", "p_market", "market_source",
           "hg", "ag", "won", "p_close", "close_source", "status", "graded_at"]
TEXT = ["line_id", "league", "event_id", "commence_time", "home", "away", "side", "first_seen", "updated_at",
        "market_source", "close_source", "status", "graded_at"]


def line_id(event_id, side) -> str:
    return hashlib.sha1(f"{event_id}|{side}".encode()).hexdigest()[:12]


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT})


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def record(offers: pd.DataFrame, asof: pd.Timestamp) -> int:
    """Upsert the soccer card's offer rows for matches not yet started; returns rows written.
    The first price and chance stay as first seen; the latest ones update until kickoff."""
    if offers is None or offers.empty:
        return 0
    o = offers[pd.to_datetime(offers["commence_time"], utc=True, format="ISO8601") > asof]
    # 3-way lines only (Oct 13: goals, BTTS and scorer rows from the same card reached here keyed only by side, e.g.
    # two "Yes" rows per match), at FanDuel's own price: books.select keeps the better book's row, so where
    # DraftKings won, FanDuel's price is the row's other_price (until Oct 13 its DraftKings price was logged as fd_price)
    if "market" in o:
        o = o[o["market"] == "h2h"]
    if "book" in o:
        book = o["book"].fillna("fanduel").astype(str).str.lower()
        other = o["other_book"].fillna("").astype(str).str.lower() if "other_book" in o else pd.Series("", index=o.index)
        fd = o["price"].where(book == "fanduel", o["other_price"] if "other_price" in o else np.nan)
        o = o.assign(price=fd)[(book == "fanduel") | (other == "fanduel")]
        o = o[o["price"].notna()]
    if o.empty:
        return 0
    now = asof.isoformat(timespec="seconds")
    home_away = o["matchup"].str.split(" vs ", n=1, expand=True)
    new = pd.DataFrame({"line_id": [line_id(e, s) for e, s in zip(o["event_id"], o["side"])],
                        "league": o["league"].to_numpy(), "event_id": o["event_id"].to_numpy(),
                        "commence_time": o["commence_time"].to_numpy(), "home": home_away[0].to_numpy(),
                        "away": home_away[1].to_numpy(), "side": o["side"].to_numpy(), "updated_at": now,
                        "fd_price": o["price"].to_numpy(), "p_market": o["p_market"].round(4).to_numpy(),
                        "market_source": o["market_source"].to_numpy(), "status": "open"})
    old = load()
    # one row per line for the lookups: Oct 13's goals/scorer rows left duplicate line ids (sides "Yes"), and a map
    # over a duplicated index stopped every card from 5:15 PM until fixed (they stay in the file as history)
    prev = (old.drop_duplicates("line_id", keep="last").set_index("line_id") if len(old)
            else pd.DataFrame(columns=COLUMNS).set_index("line_id"))
    new["first_seen"] = new["line_id"].map(prev["first_seen"]).fillna(now)
    new["first_price"] = new["line_id"].map(prev["first_price"]).fillna(new["fd_price"])
    new["first_p_market"] = new["line_id"].map(prev["first_p_market"]).fillna(new["p_market"])
    for c in COLUMNS:
        if c not in new:
            new[c] = np.nan
    keep = old[~old["line_id"].isin(new["line_id"])] if len(old) else old
    save(pd.concat([keep, new[COLUMNS]], ignore_index=True).sort_values(["commence_time", "event_id", "side"]))
    return len(new)


def grade(now: pd.Timestamp | None = None, lookup=None) -> int:
    """Fill the result and sharp close for lines whose match ended (3+ hours after kickoff)
    once football-data.co.uk has it (the European cups: ESPN's score and our own close). Returns lines graded."""
    from betlab.cards.soccer import CUPS, cup_result
    from betlab.sources import soccer

    default = lookup is None
    lookup = lookup or soccer.result
    df = load()
    if df.empty:
        return 0
    now = now or pd.Timestamp.now(tz="UTC")
    todo = df[(df["status"] == "open") & (pd.to_datetime(df["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=3))]
    stamp, n, cache = now.isoformat(timespec="seconds"), 0, {}
    for i, r in todo.iterrows():
        idx = {r["home"]: 0, "Draw": 1, r["away"]: 2}.get(r["side"])
        if idx is None:   # goals/BTTS/scorer rows that leaked in Oct 12-13 (fixed in cb566c0): closed, never graded
            df.loc[i, ["status", "graded_at"]] = ["excluded", stamp]
            n += 1
            continue
        k = (r["league"], r["event_id"])
        kickoff = pd.Timestamp(r["commence_time"])
        if k not in cache:
            cache[k] = (cup_result(r["league"], r["home"], r["away"], kickoff, r["event_id"])
                        if default and r["league"] in CUPS
                        else lookup(r["league"], r["home"], r["away"], kickoff))
        res = cache[k]
        if res is None:
            if (default and r["league"] not in CUPS and kickoff < now - pd.Timedelta(days=3)
                    and soccer.postponed(r["league"], r["home"], r["away"], kickoff) is not None):
                df.loc[i, ["status", "graded_at"]] = ["void", stamp]   # moved 2+ days: the books void it
                n += 1
            continue
        outcome = 0 if res["hg"] > res["ag"] else 1 if res["hg"] == res["ag"] else 2
        df.loc[i, ["hg", "ag", "won"]] = [res["hg"], res["ag"], float(outcome == idx)]
        if res["close"] is not None:
            df.loc[i, "p_close"] = round(res["close"][idx], 4)
            df.loc[i, "close_source"] = res["close_source"]
        df.loc[i, ["status", "graded_at"]] = ["graded", stamp]
        n += 1
    save(df)
    return n


from betlab.cards.soccer import NAMES as COMPETITIONS   # the leagues and the European cups


def _dk_prices(leagues: set[str]) -> dict[tuple[str, str], float]:
    """{(event id, side): DraftKings' 3-way price} from each league's latest game-line pull, for the game page's
    price table beside FanDuel (Oct 13). Empty where DraftKings isn't in the pull."""
    from betlab import pregame

    out = {}
    for lg in leagues:
        key = (config.settings()["leagues"].get(lg) or {}).get("sport_key")
        snap = pregame.latest(key, "pick") if key else None
        if snap is None or snap.empty:
            continue
        dk = snap[(snap["bookmaker"] == "draftkings") & (snap["market"] == "h2h")]
        for eid, side, price in zip(dk["event_id"].astype(str), dk["outcome"], dk["price"]):
            out[(eid, side)] = float(price)
    return out


def view(df: pd.DataFrame | None = None, now: pd.Timestamp | None = None, days: int = 8) -> dict:
    """Every tracked match from 3 hours ago to `days` ahead, with its 3-way lines (FanDuel's
    price, the sharp no-vig chance, EV and the move since first seen): the app's soccer games.
    Without it a match only reached the app when it made a pick, lean or ticket."""
    from betlab import odds_math as om

    df = load() if df is None else df
    now = now or pd.Timestamp.now(tz="UTC")
    if df.empty:
        return {"games": []}
    t = pd.to_datetime(df["commence_time"], utc=True, format="ISO8601")
    df = df[(t > now - pd.Timedelta(hours=3)) & (t < now + pd.Timedelta(days=days))]
    dk = _dk_prices(set(df["league"]))
    games = []
    for (league, event_id), g in df.groupby(["league", "event_id"], sort=False):
        first = g.iloc[0]
        order = {first["home"]: 0, "Draw": 1, first["away"]: 2}
        g = g[g["side"].isin(order)]                         # the 3-way sides (older rows held goals/scorer bets)
        lines = []
        for _, r in sorted(g.iterrows(), key=lambda x: order.get(x[1]["side"], 3)):
            price, p = float(r["fd_price"]), float(r["p_market"])
            d = dk.get((str(event_id), r["side"]))
            lines.append({"side": r["side"], "price": price, "p_market": p,
                          "ev": round(om.expected_value(p, price), 4),
                          "dk_price": d, "dk_ev": round(om.expected_value(p, d), 4) if d is not None else None,
                          "first_price": float(r["first_price"]), "first_p_market": float(r["first_p_market"]),
                          "source": r["market_source"]})
        games.append({"event_id": event_id, "league": league, "competition": COMPETITIONS.get(league, league),
                      "commence_time": first["commence_time"], "home": first["home"], "away": first["away"],
                      "matchup": f"{first['home']} vs {first['away']}", "updated_at": g["updated_at"].max(),
                      "first_seen": g["first_seen"].min(),
                      "lines": lines})
    games.sort(key=lambda x: x["commence_time"])
    return {"games": games}


def summary(df: pd.DataFrame | None = None) -> dict:
    """Does FanDuel lag the sharp market in soccer? Average CLV of taking every FanDuel
    line at its first price, and of the lines the card would have picked (EV 3%+)."""
    from betlab import odds_math as om

    df = load() if df is None else df
    g = df[(df["status"] == "graded") & df["p_close"].notna()] if len(df) else df
    if g.empty:
        return {"lines": int(len(df)), "graded": 0}
    clv = np.array([om.clv(float(p), float(c)) for p, c in zip(g["first_price"], g["p_close"])])
    ev = np.array([om.expected_value(float(q), float(p)) for q, p in zip(g["first_p_market"], g["first_price"])])
    return {"lines": int(len(df)), "graded": int(len(g)), "avg_clv_all": round(float(clv.mean()), 4),
            "avg_clv_ev3": round(float(clv[ev >= 0.03].mean()), 4) if (ev >= 0.03).any() else None,
            "n_ev3": int((ev >= 0.03).sum()),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
