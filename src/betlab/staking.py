"""Stake sizing.

A unit is a fixed slice of the bankroll (1% by default). Paper picks are all
logged at a flat 1 unit, and we also record what two other staking plans
would have bet, so the weekly review can show how staking changes results:
- tiers: more units for bigger edges (1 / 1.5 / 2u)
- quarter-Kelly: bet a quarter of the Kelly-optimal fraction, capped at 2u.
  Full Kelly assumes our probabilities are exact; they aren't, so we shrink it.
"""

from __future__ import annotations

import pandas as pd

from betlab import odds_math as om


def tier_units(ev: float, tiers: list[dict]) -> float:
    """Units for the highest tier whose min_ev this EV reaches (0 below the first tier)."""
    units = 0.0
    for tier in sorted(tiers, key=lambda t: t["min_ev"]):
        if ev >= tier["min_ev"]:
            units = tier["units"]
    return units


def kelly_units(p_win: float, price: float, p_push: float, unit_pct: float,
                fraction: float, cap_units: float) -> float:
    """Fractional-Kelly stake in units (1 unit = unit_pct of the bankroll), capped at cap_units."""
    share = om.kelly_fraction(p_win, price, p_push) * fraction  # share of bankroll
    return round(min(cap_units, share / unit_pct), 2)


def apply_exposure_caps(picks: pd.DataFrame, units_col: str, max_per_game: float,
                        max_per_day: float) -> pd.DataFrame:
    """Trim stakes, best EV first, so no game or day exceeds its cap."""
    out = picks.sort_values("ev", ascending=False).copy()
    game_used: dict[str, float] = {}
    day_used = 0.0
    capped = []
    for event_id, units in zip(out["event_id"], out[units_col]):
        room = min(max_per_game - game_used.get(event_id, 0.0), max_per_day - day_used)
        u = max(0.0, min(units, room))
        game_used[event_id] = game_used.get(event_id, 0.0) + u
        day_used += u
        capped.append(u)
    out[units_col] = capped
    return out
