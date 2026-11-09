"""The joint NHL game: score, team shots, every player's shots and the goalies' saves, together.

Built 2026-09-30 (Mike: "let's make the joint NHL model"), so props and game lines can share a
parlay with how they really move together. One simulated game is:
1. **The final score** drawn from the game grid (models/nhl.grid, fit to the market by the
   caller): ties, overtime and empty-net goals included.
2. **Team shots given the score:** log(shots / projected shots) = c + b_own x (own goals above
   expectation) + b_opp x (goals allowed above expectation) + b_win x (won) + noise, the two
   teams' noise correlated (`rho_teams`, negative: possession is shared). Fit on 2022-24 games:
   +2.3% shots per goal a team scores above expectation, -4.8% for the team that wins (leaders
   sit back: score effects), noise SD 0.20-0.21, correlation -0.14.
3. **Each player's shots given his team's:** beta-binomial on the team's shots with his share
   (his expected shots over the team's projected shots) and intra-class correlation `rho_player`
   (0.0032 on 2022-24: almost binomial, 9% extra spread at 30 shots).
4. **A goalie's saves** = the shots he faces minus the goals he allows (the final score's, so a
   goalie's big night and his team's win move together the way they do in a real game).
Tests (`backtest_joint_nhl.py`): joint hit rates of player-shots, saves, team-win and total
pairs on 2025-26 against what happened, next to the independent-legs product.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class JointParams:
    c: float = -0.006              # log-shots intercept (with the noise, keeps the mean at the projection)
    b_own: float = 0.0233          # log shots per own goal above expectation
    b_opp: float = 0.0017          # log shots per goal allowed above expectation
    b_win: float = -0.048          # log shots for the team that wins: leaders sit back (score effects)
    sd: float = 0.208              # noise SD of log team shots
    rho_teams: float = -0.144      # correlation of the two teams' noise
    rho_player: float = 0.0032     # beta-binomial intra-class correlation of a player's shots


def simulate(final: np.ndarray, shots_proj: tuple[float, float], goals_mean: tuple[float, float],
             players: list[dict], jp: JointParams | None = None, n: int = 3000, seed: int = 0) -> dict:
    """n simulated games. final: the final-score grid (home goals x away goals); shots_proj and
    goals_mean: (home, away) projected shots and expected final goals; players: [{"key", "side"
    ("home"/"away"), "mean" (expected shots)}]. Returns arrays: home_goals, away_goals,
    home_shots, away_shots, home_saves, away_saves, and per player key his shots."""
    jp = jp or JointParams()
    rng = np.random.default_rng(seed)
    flat = final.ravel() / final.sum()
    cell = rng.choice(flat.size, size=n, p=flat)
    gh, ga = np.unravel_index(cell, final.shape)
    gh, ga = gh.astype(float), ga.astype(float)
    cov = np.array([[1.0, jp.rho_teams], [jp.rho_teams, 1.0]]) * jp.sd ** 2
    eps = rng.multivariate_normal([0.0, 0.0], cov, size=n)
    dh, da = gh - goals_mean[0], ga - goals_mean[1]
    hw = (gh > ga).astype(float)
    sh = np.maximum(np.round(shots_proj[0] * np.exp(jp.c + jp.b_own * dh + jp.b_opp * da + jp.b_win * hw + eps[:, 0])), gh)
    sa = np.maximum(np.round(shots_proj[1] * np.exp(jp.c + jp.b_own * da + jp.b_opp * dh + jp.b_win * (1 - hw) + eps[:, 1])), ga)
    out = {"home_goals": gh, "away_goals": ga, "home_shots": sh, "away_shots": sa,
           "home_saves": np.maximum(sa - ga, 0), "away_saves": np.maximum(sh - gh, 0), "players": {}}
    for p in players:
        team_shots = sh if p["side"] == "home" else sa
        share = float(np.clip(p["mean"] / max(shots_proj[0 if p["side"] == "home" else 1], 1e-6), 1e-4, 0.6))
        out["players"][p["key"]] = beta_binomial(rng, team_shots.astype(int), share, jp.rho_player)
    return out


def beta_binomial(rng, trials: np.ndarray, p: float, rho: float) -> np.ndarray:
    """Beta-binomial draws with mean share p and intra-class correlation rho (0 = binomial)."""
    if rho <= 0:
        return rng.binomial(trials, p).astype(float)
    k = (1 - rho) / rho
    q = rng.beta(p * k, (1 - p) * k, size=len(trials))
    return rng.binomial(trials, q).astype(float)
