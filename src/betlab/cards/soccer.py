"""Soccer: FanDuel's 3-way match result against the sharp market (paper; market-only).

Our soccer ratings lost to the market in every league and didn't predict line moves
(`betlab backtest soccer`, docs/MODELS.md), so nothing here comes from a model:
- For every match in a snapshot, FanDuel's home / draw / away prices are compared with
  the sharp book's (Pinnacle, else LowVig or BetOnline, else the other books') no-vig
  3-way chances (Shin's method, settings picks.devig_three_way).
- Offer rows carry p_model = p_market and model weight 0, so picks come only from
  FanDuel lagging the sharp price, under the normal game-line rules (min EV, one pick
  per match, prices within -250..+250).
- FanDuel only posts the 3-way result for these leagues in the odds feed, so that's the
  one market (settings leagues.<league>.markets).
Every line also goes to the soccer tracker (tracking_soccer.py), graded against
football-data.co.uk's results and closing odds (the cups: ESPN's score and our last pull's close, `close_3way`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import config
from betlab.books import name as _bk
from betlab import odds_math as om
from betlab.market import reference_books

DOMESTIC = ("epl", "la_liga", "serie_a", "bundesliga", "ligue_1", "mls")
# The European cups (Mike, Oct 12: live from Oct 13): Champions League, Europa League, Conference League. Priced
# like the leagues (market-only, both books), graded from ESPN's score and our own last pull before kickoff
# (football-data.co.uk has no cup files); their players' model reads come from each player's domestic history.
CUPS = ("ucl", "uel", "uecl")
LEAGUES = DOMESTIC + CUPS
NAMES = {"epl": "Premier League", "la_liga": "La Liga", "serie_a": "Serie A", "bundesliga": "Bundesliga",
         "ligue_1": "Ligue 1", "mls": "MLS", "ucl": "Champions League", "uel": "Europa League",
         "uecl": "Conference League"}


def league_of(sport_key: str) -> str | None:
    for key, cfg in config.settings()["leagues"].items():
        if cfg["sport_key"] == sport_key and key in LEAGUES:
            return key
    return None


def three_way(h2h: pd.DataFrame, book: str, home: str, away: str) -> list[float] | None:
    """[home, draw, away] American prices for one book, or None if any is missing."""
    rows = h2h[h2h["bookmaker"] == book]
    out = []
    for outcome in (home, "Draw", away):
        r = rows[rows["outcome"] == outcome]
        if r.empty:
            return None
        out.append(float(r["price"].iloc[0]))
    return out


def evaluate(snap: pd.DataFrame, asof: pd.Timestamp, book: str = "fanduel") -> pd.DataFrame:
    """One offer row per FanDuel 3-way outcome, for matches not yet started."""
    s = config.settings()
    method = s["picks"].get("devig_three_way", "shin")
    snap = snap[pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof]
    rows = []
    for event_id, ev in snap.groupby("event_id"):
        league = league_of(ev["sport_key"].iloc[0])
        home, away = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        h2h = ev[ev["market"] == "h2h"]
        fd = three_way(h2h, book, home, away)
        if league is None or fd is None:
            continue
        books, source = reference_books(h2h, "h2h", s["odds_api"]["sharp_books"], "fanduel")
        fairs = [om.devig(tw, method) for b in books if (tw := three_way(h2h, b, home, away))]
        if not fairs:
            continue
        p_mkt = np.median(np.array(fairs), axis=0)
        for side, label, price, p in zip((home, "Draw", away), (f"{home} to win", "Draw", f"{away} to win"), fd, p_mkt):
            rows.append({
                "league": league, "event_id": event_id, "game_ref": None,
                "commence_time": ev["commence_time"].iloc[0], "matchup": f"{home} vs {away}",
                "market": "h2h", "side": side, "player": None, "label": label, "point": None,
                "price": price, "book": book, "model_number": "market only (no model weight)",
                "kind": "game_line", "p_model": float(p), "p_market": float(p), "p_final": float(p),
                "p_push": 0.0, "ev": om.expected_value(float(p), price), "market_source": source, "w_model": 0.0,
                "context": (f"3-way result: {_bk(book)} {price:+.0f} ({om.implied_prob(price):.1%} to break even) vs "
                            f"{source}'s no-vig {p:.1%}. Our soccer ratings have no weight: they lost to the "
                            f"market in every league tested."),
            })
    return pd.DataFrame(rows)


def close_3way(league: str, event_id: str, kickoff, after=None) -> tuple[float, float, float] | None:
    """The sharp no-vig (home, draw, away) chances in our last game-line pull before kickoff: the close for the
    cups, which football-data.co.uk doesn't carry. Each match's pre-game pull (pregame.py, 15-55 minutes out)
    lands in a *_pick snapshot, so this is a close within the hour. With `after` (a bet's created_at), only a pull
    taken after it counts: the pull a bet came from only repeats its EV (Oct 15: the Viking-Bayern draw's "close")."""
    s = config.settings()
    key = s["leagues"][league]["sport_key"]
    k = pd.Timestamp(kickoff)
    days = {f"{(k - pd.Timedelta(days=d)).tz_convert('America/New_York'):%Y-%m-%d}" for d in (0, 1)}
    files = sorted(f for d in days for f in (config.DATA_DIR / "odds" / key / d).glob("*_pick.parquet"))
    method = s["picks"].get("devig_three_way", "shin")
    for f in reversed(files):
        snap = pd.read_parquet(f)
        ev = snap[(snap["event_id"].astype(str) == str(event_id)) & (snap["market"] == "h2h")]
        if ev.empty or pd.to_datetime(ev["snapshot_ts"], utc=True).max() > k:
            continue
        if after is not None and pd.notna(after) and pd.to_datetime(ev["snapshot_ts"], utc=True).max() <= pd.Timestamp(after):
            return None                                     # every earlier pull is older still
        home, away = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        books, _ = reference_books(ev, "h2h", s["odds_api"]["sharp_books"], "fanduel")
        fairs = [om.devig(tw, method) for b in books if (tw := three_way(ev, b, home, away))]
        if fairs:
            return tuple(float(x) for x in np.median(np.array(fairs), axis=0))
    return None


def cup_result(league: str, home: str, away: str, kickoff, event_id: str, after=None) -> dict | None:
    """A European cup match's result in the shape of sources/soccer.result: ESPN's final score and our own
    close (close_3way), or None until ESPN has the match finished. ESPN's score is 90 minutes in the league
    phase; knockout ties can go to extra time, which the books don't settle on (check before February). `after`: a
    bet's created_at (see close_3way)."""
    from betlab.fun_ledger import _soccer_result

    res = _soccer_result(league, home, away, kickoff)
    if res is None:
        return None
    close = close_3way(league, event_id, kickoff, after)
    return {"hg": res["hg"], "ag": res["ag"], "close": close,
            "close_source": "our last pull before kickoff (sharp no-vig)" if close else None}
