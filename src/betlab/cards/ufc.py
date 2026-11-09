"""UFC on the card (market-only, from UFC 333 on Oct 24; Mike, Oct 23): Mike's books against the sharp market.

We have no fight model, so it gets no weight (CLAUDE.md, hard rule 3): offers come only from a book's price
lagging the sharp books' no-vig chance (Pinnacle, else LowVig or BetOnline), as the NHL's do.
- **Moneyline** (a draw or a no contest voids it, as the books settle a two-way fight line).
- **Total rounds:** only where the sharp book hangs the same number (FanDuel has none in the feed; DraftKings and
  Novig do). Over 2.5 needs the fight to pass 2:30 of round 3; a decision goes the full distance.
The Odds API's MMA feed mixes promotions, and gives most fights the card's first start. Each fight is matched to
ESPN's UFC card by the fighters' last names (`espn_ufc.same_fight`); fights not on a UFC card are skipped, and each
keeps ESPN's start of its card segment (early prelims, prelims, main card), which pregame.py also pulls and closes by.
Grading: `grading.grade_ufc` (ESPN's result; the close from a pull after the bet, before its segment starts).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import config
from betlab import odds_math as om
from betlab.books import name as _bk
from betlab.market import reference_books, two_way
from betlab.sources import espn_ufc as src

ET = "America/New_York"


def card_fights(asof: pd.Timestamp, days: int = 3) -> pd.DataFrame:
    """ESPN's UFC fights of today and the next days (Eastern), with their segment starts (free)."""
    local = asof.tz_convert(ET)
    frames = []
    for d in range(days):
        try:
            frames.append(src.scheduled((local + pd.Timedelta(days=d)).strftime("%Y%m%d")))
        except Exception:      # ESPN down: no UFC card this run
            pass
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True).drop_duplicates("fight_id") if frames else pd.DataFrame()


def align(events: list[dict], fights: pd.DataFrame) -> list[dict]:
    """The Odds API's events that are UFC fights, each at its ESPN segment start (pregame.py)."""
    out = []
    for e in events:
        f = src.find(fights, e["home_team"], e["away_team"])
        if f is not None and f["start"]:
            out.append(e | {"commence_time": pd.Timestamp(f["start"]).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return out


def _fair(ev: pd.DataFrame, market: str, a: str, b: str, book: str, point_a=None) -> tuple[float | None, str]:
    books, source = reference_books(ev, market, config.settings()["odds_api"]["sharp_books"], book)
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


def evaluate(snap: pd.DataFrame, asof: pd.Timestamp, fights: pd.DataFrame | None = None,
             book: str = "fanduel") -> pd.DataFrame:
    """One offer row per side (moneyline, total rounds) at `book`, for UFC fights whose segment hasn't started."""
    if snap is None or snap.empty:
        return pd.DataFrame()
    fights = card_fights(asof) if fights is None else fights
    rows = []
    for event_id, ev in snap.groupby("event_id"):
        x, y = ev["home_team"].iloc[0], ev["away_team"].iloc[0]
        f = src.find(fights, x, y)
        if f is None or pd.Timestamp(f["start"]) <= asof:
            continue
        a, b = (x, y) if src.same_fight(f["a_name"], f["b_name"], x, y) and src._last(f["a_name"]) == src._last(x) else (y, x)
        start = pd.Timestamp(f["start"]).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = {"league": "ufc", "event_id": event_id, "game_ref": f"ufc:{f.get('espn_event')}:{f['fight_id']}", "commence_time": start,
                "matchup": f"{a} vs {b}", "player": None, "book": book, "kind": "game_line", "w_model": 0.0,
                "p_push": 0.0, "model_number": "market only (no model weight)"}
        rounds = int(f["rounds"])
        # ---- moneyline
        tw = two_way(ev, "h2h", book, a, b)
        p_a, source = _fair(ev, "h2h", a, b, book)
        if tw and p_a is not None:
            (_, pr_a), (_, pr_b) = tw
            for side, pr, p in ((a, pr_a, p_a), (b, pr_b, 1 - p_a)):
                rows.append(base | {"market": "h2h", "side": side, "label": f"{side} ML", "point": None,
                                    "price": float(pr), "p_model": p, "p_market": p, "p_final": p,
                                    "ev": om.expected_value(p, float(pr)), "market_source": source,
                                    "context": f"Moneyline ({rounds} rounds; a draw or no contest voids it): {_bk(book)} "
                                               f"{pr:+.0f} ({om.implied_prob(float(pr)):.1%} to break even) vs {source}'s "
                                               f"no-vig {p:.1%}. No fight model: market only."})
        # ---- total rounds
        tw = two_way(ev, "totals", book, "Over", "Under")
        if tw:
            (line, pr_o), (_, pr_u) = tw
            p_over, source = _fair(ev, "totals", "Over", "Under", book, point_a=line)
            if p_over is not None:
                mins = f"{int(line)}:{'30' if float(line) % 1 else '00'}"
                for side, pr, p in (("Over", pr_o, p_over), ("Under", pr_u, 1 - p_over)):
                    rows.append(base | {"market": "totals", "side": side, "label": f"{side} {float(line):g} rounds",
                                        "point": float(line), "price": float(pr), "p_model": p, "p_market": p,
                                        "p_final": p, "ev": om.expected_value(p, float(pr)), "market_source": source,
                                        "context": f"Total rounds {float(line):g} of {rounds}: the over needs the fight to "
                                                   f"go past {mins} into round {int(line) + 1} (a decision goes the "
                                                   f"distance). {_bk(book)} {pr:+.0f} vs {source}'s no-vig {p:.1%}."})
    return pd.DataFrame(rows)
