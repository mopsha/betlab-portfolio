"""Soccer goals and both teams to score: FanDuel against Pinnacle's no-vig price (paper; market-only).

The bulk odds feed has only FanDuel's 3-way for soccer. From Oct 12 (Mike chose, ~700 credits a month) each
match's pre-game pull after lineups (pregame.py, the [15, 55] window) also takes the event endpoint's goals
ladder (`alternate_totals`) and both teams to score (`btts`), 2 credits a match. Pinnacle quotes both on every
match we pull, so:
- Goals: at each of FanDuel's numbers in POINTS, FanDuel's over and under against Pinnacle's no-vig chance at
  the same number (two-way, the picks' power method), else LowVig or BetOnline, else the median of two or
  more other books there. Quotes at other numbers are never translated: this is a price test.
- Both teams to score: FanDuel's Yes and No against Pinnacle's two-way no-vig, the same way.
Offers carry model weight 0, so picks come only from FanDuel lagging the sharp price, under the game-line
rules (picks.classify: 3% EV, prices within -250..+250). Graded from the final score
(fun_ledger._soccer_result: football-data, else ESPN), CLV against the last props pull before kickoff (`close`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import config
from betlab.books import name as _bk
from betlab import odds_math as om

MARKETS = ("alternate_totals", "btts")
POINTS = (1.5, 2.5, 3.5)
SHARP = ("pinnacle", "lowvig", "betonlineag")
SIDES = {"alternate_totals": ("Over", "Under"), "btts": ("Yes", "No")}


def _two_way(rows: pd.DataFrame, book: str, market: str, point) -> float | None:
    """A book's no-vig chance of the first side (Over / Yes), or None if it doesn't quote both."""
    a, b = SIDES[market]
    g = rows[(rows["bookmaker"] == book) & (rows["market"] == market)]
    if market == "alternate_totals":
        g = g[(g["point"].astype(float) - float(point)).abs() < 0.01]
    pa, pb = g[g["outcome"] == a]["price"], g[g["outcome"] == b]["price"]
    if pa.empty or pb.empty:
        return None
    method = config.settings()["picks"].get("devig_two_way", "power")
    return om.no_vig_two_way(float(pa.iloc[0]), float(pb.iloc[0]), method)[0]


def fair(rows: pd.DataFrame, market: str, point=None) -> tuple[float, str] | None:
    """(no-vig chance of Over / Yes, its source): the first sharp book quoting both sides, else the
    median of two or more other books (never FanDuel itself)."""
    for sharp in SHARP:
        p = _two_way(rows, sharp, market, point)
        if p is not None:
            return p, f"{sharp.capitalize() if sharp != 'betonlineag' else 'BetOnline'} no-vig"
    mine = set(config.settings()["odds_api"].get("target_books") or ["fanduel"])
    others = [p for b in rows["bookmaker"].unique() if b not in SHARP and b not in mine
              if (p := _two_way(rows, b, market, point)) is not None]
    if len(others) >= 2:
        return float(np.median(others)), f"consensus of {len(others)} books"
    return None


def _label(market: str, side: str, point) -> str:
    if market == "btts":
        return "Both teams to score" if side == "Yes" else "Both teams to score: No"
    return f"{side} {point:g} goals"


def evaluate(snap: pd.DataFrame, league: str, asof: pd.Timestamp, book: str = "fanduel") -> pd.DataFrame:
    """One offer row per FanDuel goals side (at POINTS) and BTTS side, for matches not yet started."""
    snap = snap[snap["market"].isin(MARKETS) & (pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof)]
    rows = []
    for eid, ev in snap.groupby("event_id"):
        home, away = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        fd = ev[ev["bookmaker"] == book]
        targets = [("btts", None)] + [("alternate_totals", p) for p in POINTS]
        for market, point in targets:
            f = fair(ev, market, point)
            if f is None:
                continue
            p_first, source = f
            for side, p in zip(SIDES[market], (p_first, 1 - p_first)):
                q = fd[(fd["market"] == market) & (fd["outcome"] == side)]
                if market == "alternate_totals":
                    q = q[(q["point"].astype(float) - float(point)).abs() < 0.01]
                if q.empty:
                    continue
                price = float(q["price"].iloc[0])
                if not -250 <= price <= 250:          # long prices carry FanDuel's heaviest margin
                    continue
                label = _label(market, side, point)
                rows.append({
                    "league": league, "event_id": str(eid), "game_ref": None, "commence_time": ev["commence_time"].iloc[0],
                    "matchup": f"{home} vs {away}", "market": "totals" if market == "alternate_totals" else "btts",
                    "side": side, "player": None, "label": label, "point": point, "price": price, "book": book,
                    "kind": "game_line", "w_model": 0.0, "p_model": float(p), "p_market": float(p), "p_final": float(p),
                    "p_push": 0.0, "ev": om.expected_value(float(p), price), "market_source": source,
                    "model_number": "market only (no model weight)",
                    "context": f"{label}: {_bk(book)} {price:+.0f} ({om.implied_prob(price):.1%} to break even) vs "
                               f"{source} {p:.1%}, from the pull after lineups."})
    return pd.DataFrame(rows)


def settle(market: str, side: str, point, hg: int, ag: int) -> str:
    if market == "btts":
        both = hg > 0 and ag > 0
        return "won" if both == (side == "Yes") else "lost"
    goals = hg + ag
    if goals == float(point):
        return "push"
    return "won" if (goals > float(point)) == (side == "Over") else "lost"


def close(league: str, event_id: str, market: str, side: str, point, kickoff, logged=None) -> float | None:
    """The sharp no-vig chance of the pick's side in the last props pull before kickoff and after the pick was
    logged (the CLV close); None when no pull followed it (Oct 13: pregame's closing look adds one)."""
    key = config.settings()["leagues"][league]["sport_key"]
    k = pd.Timestamp(kickoff)
    feed = "alternate_totals" if market == "totals" else market
    days = {f"{(k - pd.Timedelta(days=d)).tz_convert('America/New_York'):%Y-%m-%d}" for d in (0, 1)}
    files = sorted(f for d in days for f in (config.DATA_DIR / "odds" / key / d).glob("*_props.parquet"))
    for f in reversed(files):
        snap = pd.read_parquet(f)
        g = snap[(snap["event_id"].astype(str) == str(event_id)) & (snap["market"] == feed)]
        if g.empty or pd.to_datetime(g["snapshot_ts"], utc=True).max() > k:
            continue
        if logged is not None and pd.notna(logged) and pd.to_datetime(g["snapshot_ts"], utc=True).max() <= pd.Timestamp(logged):
            return None
        fr = fair(g, feed, point)
        if fr is not None:
            return fr[0] if side in ("Over", "Yes") else 1 - fr[0]
    return None
