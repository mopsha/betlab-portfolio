"""Time-weighted offense/defense ratings by ridge regression.

Each game contributes two rows, one per team's offense:

    value(team, game) = mu + home_edge * side + off[team] + def[opponent]

side is +0.5 for the home team, -0.5 for the away team, 0 on a neutral field,
so `home_edge` is the full home advantage in the margin. `def` is what a
defense *allows* (positive = bad defense). Recent games weigh more
(exponential decay), and the ridge penalty pulls teams with little data
toward league average. Works for any per-team value: points, EPA/play, etc.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Ratings:
    mu: float
    home_edge: float
    off: dict[str, float]
    dfn: dict[str, float]

    def expected(self, team: str, opponent: str, side: float) -> float:
        """Expected value for `team`'s offense. Unknown teams rate as average."""
        return self.mu + self.home_edge * side + self.off.get(team, 0.0) + self.dfn.get(opponent, 0.0)

    def predict(self, home: str, away: str, neutral: bool = False) -> tuple[float, float]:
        side = 0.0 if neutral else 0.5
        return self.expected(home, away, side), self.expected(away, home, -side)


def fit_ratings(
    games: pd.DataFrame,
    asof: pd.Timestamp,
    home_col: str,
    away_col: str,
    half_life_days: float = 200.0,
    ridge: float = 3.0,
    lookback_days: int = 800,
) -> Ratings:
    """Fit ratings from games played strictly before `asof`.

    `games` needs: date, home_team, away_team, neutral, plus the two value
    columns (the home offense's value and the away offense's value).
    """
    g = games[(games["date"] < asof) & (games["date"] >= asof - pd.Timedelta(days=lookback_days))]
    g = g.dropna(subset=[home_col, away_col])
    teams = sorted(set(g["home_team"]) | set(g["away_team"]))
    if not len(g):
        return Ratings(0.0, 0.0, {}, {})
    idx = {t: i for i, t in enumerate(teams)}
    n, m = len(teams), len(g)

    home_i = g["home_team"].map(idx).to_numpy()
    away_i = g["away_team"].map(idx).to_numpy()
    side = np.where(g["neutral"].to_numpy(), 0.0, 0.5)
    age = (asof - g["date"]).dt.days.to_numpy()
    weight = 0.5 ** (age / half_life_days)

    X = np.zeros((2 * m, 2 + 2 * n))
    rows = np.arange(m)
    # home offense vs away defense
    X[rows, 0] = 1
    X[rows, 1] = side
    X[rows, 2 + home_i] = 1
    X[rows, 2 + n + away_i] = 1
    # away offense vs home defense
    X[m + rows, 0] = 1
    X[m + rows, 1] = -side
    X[m + rows, 2 + away_i] = 1
    X[m + rows, 2 + n + home_i] = 1
    y = np.concatenate([g[home_col].to_numpy(float), g[away_col].to_numpy(float)])
    w = np.concatenate([weight, weight])

    penalty = np.diag([0.0, 0.0] + [ridge] * (2 * n))
    XtW = X.T * w
    beta = np.linalg.solve(XtW @ X + penalty, XtW @ y)
    return Ratings(
        mu=float(beta[0]),
        home_edge=float(beta[1]),
        off={t: float(beta[2 + i]) for t, i in idx.items()},
        dfn={t: float(beta[2 + n + i]) for t, i in idx.items()},
    )
