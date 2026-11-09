"""NBA same-game simulator: every priced player and the game lines, drawn together.

Each player's lines come from the market (a negative binomial per stat, its mean set so the
market's no-vig price at the quoted line is reproduced; props_nba.mu_for_quote). How they
move together is a Gaussian copula whose correlations are measured from real games by role,
on within-player ranks (so a star's usual 30 and a bench player's 8 compare fairly):

- the same player's points, rebounds, assists and threes (points with threes 0.60)
- a player's stats with the game total and with his team's margin
- teammates (points with a teammate's assists +0.07; teammates' points about 0: sharing
  pace and competing for shots cancel out) and opponents (about 0)

Fit on 2024-25 regular-season games (players with 30+ games at 20+ minutes); 2025-26 agreed
on every entry within about 0.02 (docs/MODELS.md). The game's total and home margin are
normal around the market's (SD 18.4 and 13.9 against 2025-26 closing lines, uncorrelated).

Checked on 2025-26: for two 70% legs the copula's joint hit rate matches real games within
about 0.01 of lift on every pair. For two 25% legs it overstates a player's points with his
rebounds (1.46 vs 1.36) and with his team winning big (1.18 vs 1.07: stars sit in
blowouts), so tickets keep to likely legs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats as st

BASE = ("points", "rebounds", "assists", "threes")
COMBOS = {"pra": ("points", "rebounds", "assists"), "pr": ("points", "rebounds"),
          "pa": ("points", "assists"), "ra": ("rebounds", "assists")}
TOTAL_SD, MARGIN_SD = 18.4, 13.9

# Correlations of within-player normal scores, 2024-25 (2025-26 in docs/MODELS.md).
SAME = {("points", "rebounds"): 0.267, ("points", "assists"): 0.172, ("points", "threes"): 0.603,
        ("rebounds", "assists"): 0.192, ("rebounds", "threes"): 0.105, ("assists", "threes"): 0.097}
WITH_TOTAL = {"points": 0.153, "rebounds": -0.042, "assists": 0.110, "threes": 0.118}
WITH_MARGIN = {"points": 0.108, "rebounds": 0.076, "assists": 0.097, "threes": 0.097}  # his own team's margin
MATE = {("points", "points"): -0.012, ("points", "rebounds"): 0.015, ("points", "assists"): 0.068,
        ("points", "threes"): -0.008, ("rebounds", "rebounds"): 0.001, ("rebounds", "assists"): 0.004,
        ("rebounds", "threes"): 0.007, ("assists", "assists"): 0.006, ("assists", "threes"): 0.059,
        ("threes", "threes"): 0.004}
OPP = {("points", "points"): 0.022, ("points", "rebounds"): -0.009, ("points", "assists"): 0.014,
       ("points", "threes"): 0.009, ("rebounds", "rebounds"): 0.014, ("rebounds", "assists"): -0.012,
       ("rebounds", "threes"): -0.008, ("assists", "assists"): 0.004, ("assists", "threes"): 0.005,
       ("threes", "threes"): 0.002}


def _pair(table: dict, a: str, b: str) -> float:
    return table.get((a, b), table.get((b, a), 0.0))


@dataclass
class GameSim:
    """n joint draws of one game. draws[(player, stat)]: array of length n (combos included)."""

    n: int
    players: pd.DataFrame                         # player, team, stat, mu, r
    draws: dict = field(default_factory=dict)
    points: dict = field(default_factory=dict)    # team -> points per draw (for game-line legs)

    def get(self, player: str, stat: str) -> np.ndarray | None:
        return self.draws.get((player, stat))


def correlation(players: pd.DataFrame, home: str) -> np.ndarray:
    """The copula's correlation matrix for [total, home margin] + one entry per (player, stat)
    row of `players` (columns player, team, stat), made positive definite."""
    k = 2 + len(players)
    c = np.eye(k)
    rows = list(players[["player", "team", "stat"]].itertuples(index=False))
    for i, (p, t, s) in enumerate(rows):
        sign = 1.0 if t == home else -1.0
        c[0, 2 + i] = c[2 + i, 0] = WITH_TOTAL[s]
        c[1, 2 + i] = c[2 + i, 1] = sign * WITH_MARGIN[s]
        for j in range(i + 1, len(rows)):
            p2, t2, s2 = rows[j]
            if p2 == p:
                v = _pair(SAME, s, s2)
            elif t2 == t:
                v = _pair(MATE, s, s2)
            else:
                v = _pair(OPP, s, s2)
            c[2 + i, 2 + j] = c[2 + j, 2 + i] = v
    w, v = np.linalg.eigh(c)
    if w.min() < 1e-6:                         # nearest positive definite, unit diagonal kept
        c = v @ np.diag(np.maximum(w, 1e-6)) @ v.T
        d = np.sqrt(np.diag(c))
        c = c / np.outer(d, d)
    return c


def simulate(players: pd.DataFrame, home: str, away: str, spread_home: float, total: float,
             n: int = 20000, seed: int = 0) -> GameSim:
    """Draw one game n times. players: one row per (player, team, stat) for base stats, with
    the negative binomial's mean `mu` and dispersion `r`. spread_home: the home team's
    expected margin (+ = favored). Combos are the sums of their parts' draws."""
    players = players[players["stat"].isin(BASE)].reset_index(drop=True)
    c = correlation(players, home)
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, len(c))) @ np.linalg.cholesky(c).T
    u = st.norm.cdf(z)
    tot = total + TOTAL_SD * z[:, 0]
    mar = spread_home + MARGIN_SD * z[:, 1]
    sim = GameSim(n=n, players=players, points={home: (tot + mar) / 2, away: (tot - mar) / 2})
    for i, r in enumerate(players.itertuples()):
        mu, disp = max(float(r.mu), 1e-3), float(r.r)
        sim.draws[(r.player, r.stat)] = st.nbinom.ppf(np.clip(u[:, 2 + i], 1e-9, 1 - 1e-9), disp, disp / (disp + mu))
    for name in players["player"].unique():
        for combo, parts in COMBOS.items():
            got = [sim.draws.get((name, p)) for p in parts]
            if all(g is not None for g in got):
                sim.draws[(name, combo)] = np.sum(got, axis=0)
    return sim
