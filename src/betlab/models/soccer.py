"""Soccer team ratings and match probabilities (the base the ML layer builds on).

A time-weighted Poisson model of goals, the standard starting point (Dixon and Coles 1997):

- Each team has an attack and a defense rating. Expected goals:
  home = exp(mu + home_adv + attack[home] - defense[away]);
  away = exp(mu + attack[away] - defense[home]).
- Fit by weighted Poisson likelihood on the league's earlier matches. Weights halve every
  `half_life_days`, and ridge pulls each rating toward its prior.
- **Promoted teams** (not in the league last season) start from a below-average prior:
  they're usually the weakest sides.
- **Shots on target** can stand in for part of the goals (`sot_weight`): shots on target
  times the league's goals per shot on target is a crude expected-goals number, steadier
  than goals over a few games. The big five record it; MLS doesn't.
- Probabilities come from the two Poisson scores with Dixon and Coles's low-score
  correction (`rho`): home/draw/away, over/under 2.5, and the goal-difference distribution
  for Asian handicaps.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import optimize
from scipy.stats import poisson


@dataclass
class Params:
    half_life_days: float = 240.0
    ridge: float = 6.0            # penalty per rating (in matches of evidence, roughly)
    promoted_prior: float = 0.2   # promoted teams start this much weaker in attack and in defense
    sot_weight: float = 0.0       # share of the goals target replaced by shots on target x conversion
    rho: float = -0.05            # Dixon-Coles low-score correction
    history_days: int = 800       # matches older than this are ignored (speed)
    max_goals: int = 10


@dataclass
class Ratings:
    teams: list
    attack: dict
    defense: dict
    mu: float
    home: float
    params: Params

    def expected(self, home: str, away: str) -> tuple[float, float]:
        a, d = self.attack, self.defense
        lh = np.exp(self.mu + self.home + a.get(home, -self.params.promoted_prior) - d.get(away, -self.params.promoted_prior))
        la = np.exp(self.mu + a.get(away, -self.params.promoted_prior) - d.get(home, -self.params.promoted_prior))
        return float(lh), float(la)


def fit(matches: pd.DataFrame, date, p: Params | None = None) -> Ratings:
    """Ratings from one league's matches before `date` (columns: date, season, home, away,
    hg, ag, and hst/ast if sot_weight > 0)."""
    p = p or Params()
    date = pd.Timestamp(date)
    m = matches[(matches["date"] < date) & (matches["date"] >= date - pd.Timedelta(days=p.history_days))]
    teams = sorted(set(m["home"]) | set(m["away"]))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    # Prior: teams that weren't in the league in the latest season before `date` count as promoted.
    last_season = m["season"].max() if len(m) else None
    this_season = matches.loc[matches["date"] >= date, "season"].min() if (matches["date"] >= date).any() else last_season
    in_last = set(m.loc[m["season"] == (this_season - 1 if this_season is not None else last_season), "home"])
    prior = np.array([0.0 if (t in in_last or not in_last) else -p.promoted_prior for t in teams])
    w = 0.5 ** ((date - m["date"]).dt.days.to_numpy() / p.half_life_days)
    hg, ag = m["hg"].to_numpy(float), m["ag"].to_numpy(float)
    if p.sot_weight > 0 and m["hst"].notna().all():
        conv = (hg.sum() + ag.sum()) / max(m["hst"].sum() + m["ast"].sum(), 1.0)
        hg = (1 - p.sot_weight) * hg + p.sot_weight * conv * m["hst"].to_numpy(float)
        ag = (1 - p.sot_weight) * ag + p.sot_weight * conv * m["ast"].to_numpy(float)
    hi, ai = m["home"].map(idx).to_numpy(), m["away"].map(idx).to_numpy()

    def nll(theta):
        mu, h = theta[0], theta[1]
        att, dfn = theta[2:2 + n], theta[2 + n:]
        lh = mu + h + att[hi] - dfn[ai]
        la = mu + att[ai] - dfn[hi]
        eh, ea = np.exp(lh), np.exp(la)
        ll = w * (hg * lh - eh) + w * (ag * la - ea)
        pen = p.ridge * (((att - prior) ** 2).sum() + ((dfn - prior) ** 2).sum()) / 2
        g_lh, g_la = w * (hg - eh), w * (ag - ea)
        grad = np.zeros_like(theta)
        grad[0] = -(g_lh.sum() + g_la.sum())
        grad[1] = -g_lh.sum()
        ga = np.bincount(hi, g_lh, n) + np.bincount(ai, g_la, n)
        gd = -np.bincount(ai, g_lh, n) - np.bincount(hi, g_la, n)
        grad[2:2 + n] = -ga + p.ridge * (att - prior)
        grad[2 + n:] = -gd + p.ridge * (dfn - prior)
        return -ll.sum() + pen, grad

    theta0 = np.concatenate([[np.log(max((hg.mean() + ag.mean()) / 2, 0.1)), 0.2], prior, prior])
    res = optimize.minimize(nll, theta0, jac=True, method="L-BFGS-B") if n else None
    th = res.x if res is not None else theta0
    return Ratings(teams=teams, attack=dict(zip(teams, th[2:2 + n])), defense=dict(zip(teams, th[2 + n:])),
                   mu=float(th[0]), home=float(th[1]), params=p)


def score_matrix(lh: float, la: float, rho: float = -0.05, max_goals: int = 10) -> np.ndarray:
    """P(home goals = i, away goals = j), with Dixon-Coles's low-score correction."""
    g = np.arange(max_goals + 1)
    m = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
    m[0, 0] *= 1 - lh * la * rho
    m[0, 1] *= 1 + lh * rho
    m[1, 0] *= 1 + la * rho
    m[1, 1] *= 1 - rho
    return m / m.sum()


def probs(r: Ratings, home: str, away: str) -> dict:
    """Home/draw/away, over 2.5, expected goals, and the goal-difference distribution."""
    lh, la = r.expected(home, away)
    sm = score_matrix(lh, la, r.params.rho, r.params.max_goals)
    i, j = np.indices(sm.shape)
    diff = i - j
    return {"h": float(sm[diff > 0].sum()), "d": float(sm[diff == 0].sum()), "a": float(sm[diff < 0].sum()),
            "o25": float(sm[i + j > 2.5].sum()), "xg_h": lh, "xg_a": la,
            "diff": {int(k): float(sm[diff == k].sum()) for k in range(-r.params.max_goals, r.params.max_goals + 1)}}
