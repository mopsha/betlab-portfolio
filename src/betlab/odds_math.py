"""Odds math: conversions, vig removal, expected value, staking and CLV.

Conventions used everywhere in BetLab:
- American odds are numbers like -110 or +150 (never between -100 and +100).
- Decimal odds include the returned stake: +150 -> 2.50, -110 -> 1.909.
- Probabilities are fractions in (0, 1). EV and CLV are per 1 unit staked.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from scipy.optimize import brentq


# ---------------------------------------------------------------- conversions

def american_to_decimal(american: float) -> float:
    """-110 -> 1.909, +150 -> 2.50 (decimal odds include the returned stake)."""
    if -100 < american < 100:
        raise ValueError(f"invalid American odds: {american}")
    if american > 0:
        return 1 + american / 100
    return 1 + 100 / -american


def decimal_to_american(decimal: float) -> float:
    """2.50 -> +150, 1.909 -> -110."""
    if decimal <= 1:
        raise ValueError(f"invalid decimal odds: {decimal}")
    if decimal >= 2:
        return (decimal - 1) * 100
    return -100 / (decimal - 1)


def implied_prob(american: float) -> float:
    """Break-even win probability of a price, vig included."""
    return 1 / american_to_decimal(american)


def prob_to_american(p: float) -> float:
    """Fair American odds for a win probability (no vig)."""
    if not 0 < p < 1:
        raise ValueError(f"probability must be in (0, 1): {p}")
    return decimal_to_american(1 / p)


# ---------------------------------------------------------------- the vig

def overround(americans: Sequence[float]) -> float:
    """How far the implied probabilities of a market add up past 100%."""
    return sum(implied_prob(a) for a in americans) - 1


def hold(americans: Sequence[float]) -> float:
    """The book's theoretical margin if action is balanced to the fair odds.

    -110/-110 -> 4.55%: of every $100 wagered, the book expects to keep $4.55.
    """
    return 1 - 1 / sum(implied_prob(a) for a in americans)


def devig(americans: Sequence[float], method: str = "power") -> list[float]:
    """Remove the vig from a complete market (all outcomes) -> fair probabilities.

    - multiplicative: scale every implied probability down by the same factor.
    - power: raise each to a power k so they sum to 1. Takes more vig off
      longshots, which matches how books actually shade prices.
    - shin: models the vig as protection against insiders; also leans the
      vig toward longshots. Preferred for 3-way soccer markets.
    """
    implied = [implied_prob(a) for a in americans]
    total = sum(implied)
    if method == "multiplicative":
        return [p / total for p in implied]
    if method == "power":
        if abs(total - 1) < 1e-12:
            return implied
        k = brentq(lambda k: sum(p**k for p in implied) - 1, 1e-6, 50)
        return [p**k for p in implied]
    if method == "shin":
        return _shin(implied)
    raise ValueError(f"unknown devig method: {method}")


def _shin(implied: list[float]) -> list[float]:
    """Shin's method: solve for the insider share z that makes fair probabilities sum to 1."""
    total = sum(implied)

    def fair(z: float) -> list[float]:
        return [
            (math.sqrt(z * z + 4 * (1 - z) * p * p / total) - z) / (2 * (1 - z))
            for p in implied
        ]

    if total <= 1:
        return [p / total for p in implied]
    z = brentq(lambda z: sum(fair(z)) - 1, 0.0, 0.5)
    return fair(z)


def no_vig_two_way(american_a: float, american_b: float, method: str = "power") -> tuple[float, float]:
    """Fair probabilities of the two sides of a two-way market."""
    fair_a, fair_b = devig([american_a, american_b], method)
    return fair_a, fair_b


# ---------------------------------------------------------------- value

def expected_value(p_win: float, american: float, p_push: float = 0.0) -> float:
    """Expected profit per 1 unit staked. A push returns the stake."""
    p_loss = 1 - p_win - p_push
    return p_win * (american_to_decimal(american) - 1) - p_loss


def kelly_fraction(p_win: float, american: float, p_push: float = 0.0) -> float:
    """Full-Kelly share of bankroll (0 when the bet has no edge)."""
    b = american_to_decimal(american) - 1
    p_loss = 1 - p_win - p_push
    return max(0.0, (b * p_win - p_loss) / b)


def bonus_bet_value(p_win: float, american: float) -> float:
    """Cash value of a $1 bonus bet: the stake is not returned, only profit."""
    return p_win * (american_to_decimal(american) - 1)


# ---------------------------------------------------------------- parlays

def parlay_decimal(americans: Sequence[float]) -> float:
    """Decimal odds of a parlay: the product of each leg's decimal odds."""
    return math.prod(american_to_decimal(a) for a in americans)


def parlay_ev(probs: Sequence[float], americans: Sequence[float]) -> float:
    """EV per unit of a parlay whose legs are independent."""
    return math.prod(probs) * parlay_decimal(americans) - 1


# ---------------------------------------------------------------- CLV

def clv(american_bet: float, p_close_fair: float, p_close_push: float = 0.0) -> float:
    """Closing line value: the bet's EV if the no-vig closing price is the truth.

    Positive means you got a better price than the market settled on, which is
    the most reliable early sign of a real edge.
    """
    return expected_value(p_close_fair, american_bet, p_close_push)
