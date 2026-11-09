"""NBA game lines on the card (paper; market-only): FanDuel against the sharp market.

The market beat our NBA team model on 2025-26 closing lines (weight -0.13 +- 0.10,
docs/NBA_PLAN.md), so the model has no weight here. Picks come only from FanDuel lagging
the sharp book (Pinnacle, else LowVig or BetOnline):
- **Moneyline** (overtime counts): FanDuel's two prices against the sharp no-vig chance.
- **Spread and total:** at FanDuel's own number. When the sharp book hangs a number up to
  1.5 points away, its no-vig chance is moved to FanDuel's number along a normal curve
  (sd 13.9 points for the margin, 18.4 for the total) and the side is **a lean at most**
  (`lean_only`, enforced in picks.classify): on 2025-26 lines near tip the move didn't beat
  leaving Pinnacle's chance as it was (log loss 0.6948 vs 0.6912 on 335 spreads, 0.6926 vs
  0.6913 on 631 totals: within noise, but no evidence for it either; docs/DECISIONS.md,
  2026-10-04). The leans' CLV decides later. Further apart, the side is skipped. FanDuel
  and Pinnacle shared the number on 66% of spreads and 39% of totals near tip.
- **How often:** near tip in 2025-26, FanDuel's spreads and totals reached 3% EV against
  Pinnacle 3 times in 1,045 games. Expect leans, rarely picks; morning prices are untested.
- **Pushes** on whole-number lines: 2.8% for spreads, 1.6% for totals (2025-26, how often
  a game landed exactly on its whole-number closing line). The chances are conditional on
  no push, as on the football card.
Offer rows carry p_model = p_market and model weight 0; the normal game-line rules apply
(minimum EV, one pick per game side, moneylines within -250..+250, the 36-hour window).
Preseason games (before `leagues.nba.start`) are skipped.
Grading: `grading.grade_nba` (final scores from ESPN's schedule file; the close from our
last pull before tip, which the hourly NBA run takes 15-75 minutes before each game).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

from betlab import config
from betlab.books import name as _bk
from betlab import odds_math as om
from betlab.market import reference_books, two_way

SD = {"spreads": 13.9, "totals": 18.4}     # 2025-26: margin and total around the closing number
PUSH = {"spreads": 0.028, "totals": 0.016}  # 2025-26: games landing exactly on a whole-number line
MAX_SHIFT = 1.5                            # points between FanDuel's and the sharp number
MOVED = " ({}, moved to the book's number: a lean at most until that's tested)"
SAME = " at the same number"


def push_chance(market: str, point) -> float:
    return PUSH[market] if point is not None and float(point) % 1 == 0 else 0.0


def shift(market: str, p_a: float, sharp_point: float, point: float) -> float:
    """Side a's chance (home on spreads, Over on totals), conditional on no push, at `point`,
    given the sharp no-vig chance p_a at `sharp_point`. The game's center is the one that
    gives p_a at the sharp number (a half-point line has no push; a whole one splits it)."""
    sd = SD[market]
    # side a wins when X > c: X is the home margin (c = -spread) or the total (c = the line)
    c_sharp, c = (-sharp_point, -point) if market == "spreads" else (sharp_point, point)
    p_a = float(np.clip(p_a, 1e-4, 1 - 1e-4))
    mu = brentq(lambda m: _cover(m, c_sharp, sd) - p_a, c_sharp - 6 * sd, c_sharp + 6 * sd)
    return _cover(mu, c, sd)


def _cover(mu: float, c: float, sd: float) -> float:
    """P(X > c) for X ~ normal(mu, sd) on whole points, conditional on X != c."""
    if float(c) % 1 == 0:
        w, lose = norm.sf(c + 0.5, mu, sd), norm.cdf(c - 0.5, mu, sd)
        return float(w / (w + lose))
    return float(norm.sf(c, mu, sd))


def fair(ev: pd.DataFrame, market: str, a: str, b: str, point_a=None) -> tuple[float | None, str, str]:
    """(side a's no-vig chance at point_a, conditional on no push; the source; a note on the number)."""
    s = config.settings()
    books, source = reference_books(ev, market, s["odds_api"]["sharp_books"], "fanduel")
    fairs, notes = [], []
    for bk in books:
        tw = two_way(ev, market, bk, a, b)
        if not tw:
            continue
        (pt_a, pr_a), (_, pr_b) = tw
        p = om.no_vig_two_way(float(pr_a), float(pr_b))[0]
        if point_a is not None:
            if pd.isna(pt_a) or abs(float(pt_a) - float(point_a)) > MAX_SHIFT:
                continue
            if float(pt_a) != float(point_a):
                notes.append(f"{bk} hangs {float(pt_a):+g}" if market == "spreads" else f"{bk} hangs {float(pt_a):g}")
                p = shift(market, p, float(pt_a), float(point_a))
        fairs.append(p)
    if not fairs:
        return None, source, ""
    return float(np.median(fairs)), source, notes[0] if len(notes) == 1 and len(books) == 1 else ""


def _game_ids(asof: pd.Timestamp) -> dict:
    """{(home name, ET date): ESPN game id} from the season's schedule (free; empty if it can't load)."""
    try:
        from betlab.sources import nba
        sch = nba.load_schedules([nba.current_season(asof.tz_convert("America/New_York"))])
    except Exception:
        return {}
    day = sch["tipoff"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    return {(h, d): str(g) for h, d, g in zip(sch["home_display_name"], day, sch["game_id"])}


def evaluate(snap: pd.DataFrame, asof: pd.Timestamp, game_ids: dict | None = None, book: str = "fanduel") -> pd.DataFrame:
    """One offer row per FanDuel side (moneyline, spread, total) for regular-season games not yet started."""
    start_day = str(config.settings()["leagues"]["nba"]["start"])
    starts = pd.to_datetime(snap["commence_time"], utc=True, format="ISO8601")
    snap = snap[(starts > asof) & (starts.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d") >= start_day)]
    if snap.empty:
        return pd.DataFrame()
    game_ids = _game_ids(asof) if game_ids is None else game_ids
    rows = []
    for event_id, ev in snap.groupby("event_id"):
        home, away = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        start = ev["commence_time"].iloc[0]
        day = pd.Timestamp(start).tz_convert("America/New_York").strftime("%Y-%m-%d")
        base = {"league": "nba", "event_id": event_id, "game_ref": game_ids.get((home, day)),
                "commence_time": start, "matchup": f"{away} @ {home}", "player": None, "book": book,
                "kind": "game_line", "w_model": 0.0, "model_number": "market only (no model weight)"}
        # ---- moneyline
        fd = two_way(ev, "h2h", book, home, away)
        p_home, source, _ = fair(ev, "h2h", home, away)
        if fd and p_home is not None:
            (_, pr_h), (_, pr_a) = fd
            for side, pr, p in ((home, pr_h, p_home), (away, pr_a, 1 - p_home)):
                rows.append(base | {"market": "h2h", "side": side, "label": f"{side} ML", "point": None,
                                    "price": float(pr), "p_model": p, "p_market": p, "p_final": p, "p_push": 0.0,
                                    "ev": om.expected_value(p, float(pr)), "market_source": source,
                                    "context": f"Moneyline (overtime counts): {_bk(book)} {pr:+.0f} "
                                               f"({om.implied_prob(float(pr)):.1%} to break even) vs {source}'s "
                                               f"no-vig {p:.1%}. Our NBA model has no weight: the market beat it."})
        # ---- spread
        fd = two_way(ev, "spreads", book, home, away)
        if fd:
            (pt_h, pr_h), (pt_a, pr_a) = fd
            p_home, source, moved = fair(ev, "spreads", home, away, point_a=pt_h)
            if p_home is not None:
                push = push_chance("spreads", pt_h)
                for side, pt, pr, p in ((home, pt_h, pr_h, p_home), (away, pt_a, pr_a, 1 - p_home)):
                    rows.append(base | {"market": "spreads", "side": side, "label": f"{side} {float(pt):+g}",
                                        "point": float(pt), "price": float(pr), "p_model": p, "p_market": p,
                                        "p_final": p, "p_push": push, "lean_only": bool(moved),
                                        "ev": om.expected_value(p * (1 - push), float(pr), push), "market_source": source,
                                        "context": f"Spread {float(pt):+g}: {_bk(book)} {pr:+.0f} vs {source}'s no-vig "
                                                   f"{p:.1%}" + (MOVED.format(moved) if moved else SAME) + "."})
        # ---- total
        fd = two_way(ev, "totals", book, "Over", "Under")
        if fd:
            (line, pr_o), (_, pr_u) = fd
            p_over, source, moved = fair(ev, "totals", "Over", "Under", point_a=line)
            if p_over is not None:
                push = push_chance("totals", line)
                for side, pr, p in (("Over", pr_o, p_over), ("Under", pr_u, 1 - p_over)):
                    rows.append(base | {"market": "totals", "side": side, "label": f"{side} {float(line):g}",
                                        "point": float(line), "price": float(pr), "p_model": p, "p_market": p,
                                        "p_final": p, "p_push": push, "lean_only": bool(moved),
                                        "ev": om.expected_value(p * (1 - push), float(pr), push), "market_source": source,
                                        "context": f"Total {float(line):g} (overtime counts): {_bk(book)} {pr:+.0f} vs "
                                                   f"{source}'s no-vig {p:.1%}" + (MOVED.format(moved) if moved else SAME)
                                                   + "."})
    return pd.DataFrame(rows)
