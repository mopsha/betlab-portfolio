"""NHL on the card (paper; market-only): FanDuel against the sharp market.

Our NHL model tied DraftKings' opener and lost slightly to its close (docs/MODELS.md,
"NHL"), so it has no weight here. Picks come only from FanDuel lagging the sharp book:
- **Moneyline** (overtime and shootout included, as books settle it): FanDuel's two prices
  against the sharp book's no-vig chance (Pinnacle, else LowVig or BetOnline).
- **Puck line and total:** only where the sharp book hangs the same number as FanDuel
  (hockey lines are nearly always ±1.5 and 5.5 / 6.5, so this loses little). A different
  number is skipped rather than guessed.
Offer rows carry p_model = p_market and model weight 0; the normal game-line rules apply
(minimum EV, one pick per game side, prices within -250..+250, the 36-hour window).
Grading: `grading.grade_nhl` (results from the NHL's API, the close from our last pull
before the start).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import config
from betlab.books import name as _bk
from betlab import odds_math as om
from betlab.market import reference_books, two_way
from betlab.sources import nhl as src

ET = "America/New_York"


def _game_ids(asof: pd.Timestamp) -> pd.DataFrame:
    """The NHL's game ids for this week and next (free), to link picks to results."""
    local = asof.tz_convert(ET)
    frames = []
    for d in (0, 7):
        try:
            frames.append(src.schedule((local + pd.Timedelta(days=d)).strftime("%Y-%m-%d")))
        except Exception:
            pass
    return pd.concat(frames, ignore_index=True).drop_duplicates("game_id") if frames else pd.DataFrame(
        columns=["game_id", "start", "home", "away"])


def _game_ref(sched: pd.DataFrame, home: str, away: str, start) -> str | None:
    if sched.empty or home is None or away is None:
        return None
    t = pd.Timestamp(start)
    near = sched[(sched["home"] == home) & (sched["away"] == away)
                 & ((pd.to_datetime(sched["start"], utc=True, format="ISO8601") - t).abs() <= pd.Timedelta(hours=12))]
    return str(near["game_id"].iloc[0]) if len(near) else None


def _fair(ev: pd.DataFrame, market: str, a: str, b: str, point_a=None) -> tuple[float | None, str]:
    """The sharp books' no-vig chance of outcome a (at point_a for spreads and totals)."""
    s = config.settings()
    books, source = reference_books(ev, market, s["odds_api"]["sharp_books"], "fanduel")
    fairs = []
    for bk in books:
        tw = two_way(ev, market, bk, a, b)
        if not tw:
            continue
        (pt_a, pr_a), (_, pr_b) = tw
        if point_a is not None and (pd.isna(pt_a) or float(pt_a) != float(point_a)):
            continue
        fairs.append(om.no_vig_two_way(float(pr_a), float(pr_b))[0])
    return (float(np.median(fairs)), source) if fairs else (None, source)


def evaluate(snap: pd.DataFrame, asof: pd.Timestamp, sched: pd.DataFrame | None = None,
             codes: dict | None = None, book: str = "fanduel") -> pd.DataFrame:
    """One offer row per FanDuel side (moneyline, puck line, total) for games not yet started."""
    snap = snap[pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601") > asof]
    if snap.empty:
        return pd.DataFrame()
    sched = _game_ids(asof) if sched is None else sched
    codes = src.team_codes() if codes is None else codes
    rows = []
    for event_id, ev in snap.groupby("event_id"):
        home_name, away_name = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        home, away = src.code_for(home_name, codes), src.code_for(away_name, codes)
        start = ev["commence_time"].iloc[0]
        base = {"league": "nhl", "event_id": event_id, "game_ref": _game_ref(sched, home, away, start),
                "commence_time": start, "matchup": f"{away or away_name} @ {home or home_name}", "player": None,
                "book": book, "kind": "game_line", "w_model": 0.0, "p_push": 0.0,
                "model_number": "market only (no model weight)"}
        # ---- moneyline
        fd = two_way(ev, "h2h", book, home_name, away_name)
        p_home, source = _fair(ev, "h2h", home_name, away_name)
        if fd and p_home is not None:
            (_, pr_h), (_, pr_a) = fd
            for side, code, pr, p in ((home_name, home, pr_h, p_home), (away_name, away, pr_a, 1 - p_home)):
                rows.append(base | {"market": "h2h", "side": code or side, "label": f"{code or side} ML", "point": None,
                                    "price": float(pr), "p_model": p, "p_market": p, "p_final": p,
                                    "ev": om.expected_value(p, float(pr)), "market_source": source,
                                    "context": f"Moneyline (overtime and shootout count): {_bk(book)} {pr:+.0f} "
                                               f"({om.implied_prob(float(pr)):.1%} to break even) vs {source}'s "
                                               f"no-vig {p:.1%}. Our NHL model has no weight: it didn't beat the close."})
        # ---- puck line
        fd = two_way(ev, "spreads", book, home_name, away_name)
        if fd:
            (pt_h, pr_h), (pt_a, pr_a) = fd
            p_home, source = _fair(ev, "spreads", home_name, away_name, point_a=pt_h)
            if p_home is not None:
                for side, code, pt, pr, p in ((home_name, home, pt_h, pr_h, p_home),
                                              (away_name, away, pt_a, pr_a, 1 - p_home)):
                    rows.append(base | {"market": "spreads", "side": code or side, "label": f"{code or side} {float(pt):+g}",
                                        "point": float(pt), "price": float(pr), "p_model": p, "p_market": p, "p_final": p,
                                        "ev": om.expected_value(p, float(pr)), "market_source": source,
                                        "context": f"Puck line {float(pt):+g}: {_bk(book)} {pr:+.0f} vs {source}'s no-vig {p:.1%} "
                                                   f"at the same number."})
        # ---- total
        fd = two_way(ev, "totals", book, "Over", "Under")
        if fd:
            (line, pr_o), (_, pr_u) = fd
            p_over, source = _fair(ev, "totals", "Over", "Under", point_a=line)
            if p_over is not None:
                for side, pr, p in (("Over", pr_o, p_over), ("Under", pr_u, 1 - p_over)):
                    rows.append(base | {"market": "totals", "side": side, "label": f"{side} {float(line):g}",
                                        "point": float(line), "price": float(pr), "p_model": p, "p_market": p, "p_final": p,
                                        "ev": om.expected_value(p, float(pr)), "market_source": source,
                                        "context": f"Total {float(line):g} (the shootout winner counts as a goal): {_bk(book)} "
                                                   f"{pr:+.0f} vs {source}'s no-vig {p:.1%}."})
    return pd.DataFrame(rows)
