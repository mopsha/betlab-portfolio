"""Turning model and market probabilities into a final probability and an edge.

The market (sharp books with the vig removed) already knows about injuries,
weather and news we don't model. So our final probability is a blend, done in
log-odds space, with the weight on our model fit from history:

    logit(p_final) = w * logit(p_model) + (1 - w) * logit(p_market)

w = 0 means "trust the market", w = 1 means "trust our model". Backtests
decide w per market type; a model that adds nothing earns w near 0.
"""

from __future__ import annotations

import numpy as np
from scipy.special import expit, logit


def blend_prob(p_model, p_market, w: float):
    """Blend in log-odds space; w is the weight on our model (0 = market only). Scalars or arrays."""
    p_model = np.clip(p_model, 1e-4, 1 - 1e-4)
    p_market = np.clip(p_market, 1e-4, 1 - 1e-4)
    return expit(w * logit(p_model) + (1 - w) * logit(p_market))


def log_loss(p, y) -> float:
    """Average negative log-likelihood of outcomes y (1/0) under probabilities p; lower is better."""
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit_blend_weight(p_model, p_market, y) -> float:
    """Weight on our model that minimizes log loss of outcomes y (1/0)."""
    grid = np.linspace(0, 1, 101)
    losses = [log_loss(blend_prob(p_model, p_market, w), y) for w in grid]
    return float(grid[int(np.argmin(losses))])
