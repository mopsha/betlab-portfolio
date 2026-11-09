"""Integer outcome distributions with key numbers.

Football margins pile up on 3 and 7 (field goals and touchdowns), so a plain
normal curve misprices spreads like -2.5 vs -3.5. We start from a normal
around the predicted value and reweight each integer by how much more (or
less) often it happens historically than a smooth curve would suggest.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


class KeyNumberDist:
    """An integer outcome (margin or total) with key-number weights; see the module docstring."""

    def __init__(self, lo: int, hi: int, weights: np.ndarray, symmetric: bool):
        self.support = np.arange(lo, hi + 1)
        self.weights = weights
        self.symmetric = symmetric

    @classmethod
    def fit(cls, values, lo: int, hi: int, symmetric: bool, bandwidth: float = 2.0,
            clip: tuple[float, float] = (0.05, 4.0)) -> "KeyNumberDist":
        """Learn weights: each integer's empirical frequency / its kernel-smoothed frequency.

        symmetric=True pools margins by absolute value (3 and -3 share a weight).
        """
        values = np.asarray(values, dtype=int)
        if symmetric:
            values = np.abs(values)
            grid = np.arange(0, max(abs(lo), hi) + 1)
        else:
            grid = np.arange(lo, hi + 1)
        counts = np.array([(values == k).sum() for k in grid], dtype=float)
        emp = counts / counts.sum()
        # Gaussian kernel smoothing of the empirical frequencies.
        kernel = norm.pdf(grid[:, None], loc=grid[None, :], scale=bandwidth)
        if symmetric:  # reflect around 0 so the smooth curve isn't biased at the edge
            kernel = kernel + norm.pdf(grid[:, None], loc=-grid[None, :], scale=bandwidth)
            kernel[:, 0] /= 2
        smooth = kernel @ emp
        smooth /= smooth.sum()
        ratio = np.clip(np.divide(emp, smooth, out=np.ones_like(emp), where=smooth > 0), *clip)
        if symmetric:
            support = np.arange(lo, hi + 1)
            weights = ratio[np.minimum(np.abs(support), len(ratio) - 1)]
        else:
            weights = ratio
        return cls(lo, hi, weights, symmetric)

    def _raw_pmf(self, loc: float, sd: float) -> np.ndarray:
        """Reweighted normal around `loc` (not median-centered; see pmf)."""
        p = norm.pdf(self.support, loc=loc, scale=sd) * self.weights
        return p / p.sum()

    def pmf(self, center: float, sd: float) -> np.ndarray:
        """Distribution whose median sits at `center`.

        The key-number weights pull mass toward 3 and 7, which drags the
        midpoint of a plain reweighted normal. We shift the curve so its median
        lands on `center`: when our number equals the market's line, the model
        says 50/50 instead of favoring one side. Each integer's probability is
        treated as spread evenly over its unit interval, so the median (and
        every probability) moves smoothly as `center` moves.
        """
        return self._raw_pmf(self._location(round(float(center), 3), sd), sd)

    @lru_cache(maxsize=100_000)
    def _location(self, center: float, sd: float) -> float:
        k = math.floor(center + 0.5)          # the integer whose interval holds center
        frac = center + 0.5 - k               # how far into that interval
        below, at = self.support < k, self.support == k

        def cdf_gap(loc: float) -> float:
            p = self._raw_pmf(loc, sd)
            return p[below].sum() + frac * p[at].sum() - 0.5

        for width in (8, 20, 40):  # near the edge of the support the shift can be large
            if cdf_gap(center - width) * cdf_gap(center + width) < 0:
                return brentq(cdf_gap, center - width, center + width)
        return center

    def over_push_under(self, center: float, sd: float, line: float) -> tuple[float, float, float]:
        """P(outcome > line), P(outcome == line), P(outcome < line)."""
        p = self.pmf(center, sd)
        over = p[self.support > line].sum()
        push = p[self.support == line].sum() if float(line).is_integer() else 0.0
        return float(over), float(push), float(1 - over - push)

    def center_for(self, line: float, sd: float, p_over: float) -> float:
        """The center at which P(over `line` | no push) equals `p_over`.

        Used to read a market price as a full distribution: a sharp book's
        no-vig price at its line tells us where the market is centered, which
        then prices any other line (e.g. FanDuel's -3.5 vs the sharp -3).
        """
        def gap(center: float) -> float:
            over, push, under = self.over_push_under(center, sd, line)
            return over / (over + under) - p_over

        return brentq(gap, line - 25, line + 25)

    def log_likelihood(self, means, sds, actual) -> float:
        """Sum of log P(actual outcome) over games; used to choose the outcome SD."""
        total = 0.0
        for mean, sd, y in zip(means, sds, actual):
            p = self.pmf(mean, sd)
            i = int(y) - self.support[0]
            total += math.log(max(p[i], 1e-12)) if 0 <= i < len(p) else math.log(1e-12)
        return total
