"""Free game lines from ESPN's public scoreboard (DraftKings' numbers; no key, no credits).

ESPN shows one book per game, usually DraftKings: the moneyline, spread and total with
prices. `snapshot` returns them in the Odds API's flat format (`sources/odds_api.flatten`)
with bookmaker "draftkings", so a card can read them like any other snapshot. There's no
sharp book and no FanDuel in it, so nothing priced from it is a pick: it feeds reads
(our model against the posted line) and their tracking.

Used for college basketball until conference tournaments (Mike, 2026-09-30: he only bets
college basketball in March), to save odds credits.
"""

from __future__ import annotations

import pandas as pd
import requests

from betlab.sources.nhl import _am, _dig, _line

BASE = "https://site.api.espn.com/apis/site/v2/sports"
PATHS = {"basketball_ncaab": ("basketball/mens-college-basketball", {"groups": "50", "limit": "500"})}


def snapshot(sport_key: str, dates: list[str], ts: str) -> pd.DataFrame:
    """Every game on the given dates (YYYYMMDD) that hasn't started, as flat odds rows."""
    path, extra = PATHS[sport_key]
    rows = []
    for d in dates:
        r = requests.get(f"{BASE}/{path}/scoreboard", params={"dates": d, **extra}, timeout=60)
        r.raise_for_status()
        for e in r.json().get("events", []):
            if (e.get("status", {}).get("type", {}).get("state")) != "pre":
                continue
            c = e["competitions"][0]
            teams = {t["homeAway"]: t["team"]["displayName"] for t in c["competitors"]}
            odds = (c.get("odds") or [None])[0]
            if not odds:
                continue
            base = {"sport_key": sport_key, "event_id": f"espn-{e['id']}", "commence_time": e["date"],
                    "home_team": teams["home"], "away_team": teams["away"], "bookmaker": "draftkings",
                    "player": None, "snapshot_ts": ts}
            home_ml = _am(_dig(odds, "moneyline", "home", "close", "odds")) or _am(_dig(odds, "homeTeamOdds", "moneyLine"))
            away_ml = _am(_dig(odds, "moneyline", "away", "close", "odds")) or _am(_dig(odds, "awayTeamOdds", "moneyLine"))
            if home_ml and away_ml:
                rows += [base | {"market": "h2h", "outcome": teams["home"], "point": None, "price": home_ml},
                         base | {"market": "h2h", "outcome": teams["away"], "point": None, "price": away_ml}]
            h_pt = _line(_dig(odds, "pointSpread", "home", "close", "line"))
            h_pr = _am(_dig(odds, "pointSpread", "home", "close", "odds"))
            a_pr = _am(_dig(odds, "pointSpread", "away", "close", "odds"))
            if h_pt is None and odds.get("spread") is not None:
                # The flat spread is the home team's line; its prices are on the team blocks.
                h_pt = float(odds["spread"])
                h_pr = h_pr or _am(_dig(odds, "homeTeamOdds", "spreadOdds"))
                a_pr = a_pr or _am(_dig(odds, "awayTeamOdds", "spreadOdds"))
            if h_pt is not None and h_pr and a_pr:
                rows += [base | {"market": "spreads", "outcome": teams["home"], "point": h_pt, "price": h_pr},
                         base | {"market": "spreads", "outcome": teams["away"], "point": -h_pt, "price": a_pr}]
            tot = _line(_dig(odds, "total", "over", "close", "line"))
            o_pr, u_pr = _am(_dig(odds, "total", "over", "close", "odds")), _am(_dig(odds, "total", "under", "close", "odds"))
            if tot is None and odds.get("overUnder") is not None:
                tot, o_pr, u_pr = float(odds["overUnder"]), _am(odds.get("overOdds")), _am(odds.get("underOdds"))
            if tot is not None and o_pr and u_pr:
                rows += [base | {"market": "totals", "outcome": "Over", "point": tot, "price": o_pr},
                         base | {"market": "totals", "outcome": "Under", "point": tot, "price": u_pr}]
    return pd.DataFrame(rows)
