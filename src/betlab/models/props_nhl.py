"""NHL player props, machine-learning first (Mike, 2026-09-30: "the season just started, it's
the perfect time to start an ML model").

**Targets:** a skater's shots on goal, points, goals and assists in a game; a goalie's saves.

**Features** (`features`), all from games before this one:
- the player's role: recent ice time (all, even strength, power play, shorthanded; short
  and long averages), games played, forward or defense;
- the player's rates: shots, goals, assists and points per 60 minutes, and his share of
  his team's shots;
- tonight's lineup: how much of the team's usual shooting is in the lineup
  (`share_present`: when regulars are out, the others shoot more);
- **our game analysis** (models/nhl.py, refit weekly, walk-forward): the team's projected
  shots and goals, the opponent's projected shots, the opposing goalie's save %, home,
  back-to-back.

**Models** (`fit`): gradient-boosted trees with a Poisson loss (scikit-learn's
HistGradientBoostingRegressor), one per stat, predicting the mean; a negative binomial
around it (dispersion fit on the training seasons) gives P(over) at any line. Saves come
from the game model directly: the opponent's projected shots times the goalie's save %.

**Tests** (`backtest_props_nhl.py`): walk-forward by season against a recent-average
baseline, a hand-built model, and the same trees *without* the game-analysis features, so
it's measured whether the analysis helps props. No free historical prop lines exist, so
the market comparison comes from the lines logged from Oct 1 (tracking_nhl_props.py),
which are also the training set for the market layer (a market-offset model, the same
plan as the NFL's props ML).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

STATS = ("shots", "points", "goals", "assists")
SHORT, LONG = 6, 30                      # EWMA spans in games
GAME_FEATURES = ["team_shots_proj", "opp_shots_proj", "team_xg", "opp_goalie_sv", "home", "b2b"]
PLAYER_FEATURES = ["toi_s", "toi_l", "ev_toi_l", "pp_toi_s", "pp_toi_l", "sh_toi_l", "last_toi", "games_prior",
                   "is_d", "shots60_s", "shots60_l", "goals60_l", "assists60_l", "points60_l", "share_s", "share_l",
                   "share_present", "pp_share_l"]


def _ewm_prior(df: pd.DataFrame, cols: list[str], span: int) -> pd.DataFrame:
    """Each player's exponentially weighted mean over his earlier games (this game excluded)."""
    g = df.groupby("player_id", sort=False)[cols]
    return g.transform(lambda x: x.shift().ewm(span=span, min_periods=1).mean())


def features(sk: pd.DataFrame, team_feats: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per skater-game with the features above and the targets. sk: sources.nhl.
    load_skater_games (several seasons, sorted is not required). team_feats: one row per
    (game_id, team) with GAME_FEATURES (from `game_features`); missing ones stay NaN."""
    df = sk.sort_values(["player_id", "date", "game_id"]).reset_index(drop=True).copy()
    team_shots = df.groupby(["game_id", "team"])["shots"].transform("sum")
    team_pp = df.groupby(["game_id", "team"])["pp_toi"].transform("max").replace(0, np.nan)
    df["team_shots"] = team_shots
    df["pp_frac"] = (df["pp_toi"] / team_pp).fillna(0)
    m = lambda x: x / 60.0
    base = df.assign(toi_m=m(df["toi"]), ev_m=m(df["ev_toi"]), pp_m=m(df["pp_toi"]), sh_m=m(df["sh_toi"]))
    s = _ewm_prior(base, ["toi_m", "pp_m", "shots", "team_shots"], SHORT)
    l = _ewm_prior(base, ["toi_m", "ev_m", "pp_m", "sh_m", "shots", "goals", "assists", "points", "team_shots", "pp_frac"], LONG)
    out = df[["game_id", "season", "date", "player_id", "player", "pos", "team", "opp", "home"] + list(STATS)].copy()
    out["toi_s"], out["toi_l"] = s["toi_m"], l["toi_m"]
    out["ev_toi_l"], out["pp_toi_s"], out["pp_toi_l"], out["sh_toi_l"] = l["ev_m"], s["pp_m"], l["pp_m"], l["sh_m"]
    out["last_toi"] = df.groupby("player_id")["toi"].shift() / 60
    out["games_prior"] = df.groupby("player_id").cumcount()
    out["is_d"] = (df["pos"] == "D").astype(int)
    per60 = lambda num, toi: 60 * num / toi.clip(lower=1)
    out["shots60_s"], out["shots60_l"] = per60(s["shots"], s["toi_m"]), per60(l["shots"], l["toi_m"])
    out["goals60_l"], out["assists60_l"] = per60(l["goals"], l["toi_m"]), per60(l["assists"], l["toi_m"])
    out["points60_l"] = per60(l["points"], l["toi_m"])
    out["share_s"] = s["shots"] / s["team_shots"].clip(lower=1)
    out["share_l"] = l["shots"] / l["team_shots"].clip(lower=1)
    out["pp_share_l"] = l["pp_frac"]
    # How much of the team's usual shooting is in tonight's lineup (each player's prior share, summed).
    out["share_present"] = out.groupby(["game_id", "team"])["share_l"].transform("sum")
    if team_feats is not None and len(team_feats):
        out = out.merge(team_feats[["game_id", "team"] + GAME_FEATURES].drop(columns=["home"]),
                        on=["game_id", "team"], how="left")
    else:
        for c in GAME_FEATURES:
            if c != "home":
                out[c] = np.nan
    return out


def game_features(walk: pd.DataFrame, tg: pd.DataFrame) -> pd.DataFrame:
    """Per (game, team) from the game model's walk-forward projections (backtest_nhl.walk):
    the team's projected shots and goals, the opponent's projected shots, the opposing
    starter's save %, and back-to-backs (from team games)."""
    h = pd.DataFrame({"game_id": walk["game_id"], "team": walk["home"], "team_shots_proj": walk["home_shots"],
                      "opp_shots_proj": walk["away_shots"], "team_xg": walk["home_xg"], "opp_goalie_sv": walk["away_goalie_sv"]})
    a = pd.DataFrame({"game_id": walk["game_id"], "team": walk["away"], "team_shots_proj": walk["away_shots"],
                      "opp_shots_proj": walk["home_shots"], "team_xg": walk["away_xg"], "opp_goalie_sv": walk["home_goalie_sv"]})
    out = pd.concat([h, a], ignore_index=True)
    b2b = tg[["game_id", "team", "b2b"]]
    out = out.merge(b2b, on=["game_id", "team"], how="left")
    out["home"] = np.nan
    return out


@dataclass
class Fitted:
    models: dict = field(default_factory=dict)       # stat -> regressor
    dispersion: dict = field(default_factory=dict)   # stat -> negative binomial size (inf = Poisson)
    features: list = field(default_factory=list)


def _model():
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(loss="poisson", learning_rate=0.05, max_iter=300, max_leaf_nodes=31,
                                         min_samples_leaf=200, l2_regularization=1.0, random_state=0)


def fit(train: pd.DataFrame, feats: list[str] | None = None, stats=STATS) -> Fitted:
    """One Poisson-loss tree model per stat, and its dispersion from the training residuals."""
    feats = feats or PLAYER_FEATURES + GAME_FEATURES
    train = train[train["games_prior"] >= 1]
    f = Fitted(features=list(feats))
    for st in stats:
        mdl = _model().fit(train[feats], train[st])
        mu = mdl.predict(train[feats])
        f.models[st] = mdl
        f.dispersion[st] = nb_size(train[st].to_numpy(float), mu)
    return f


def predict(f: Fitted, df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({st: f.models[st].predict(df[f.features]) for st in f.models}, index=df.index)


def nb_size(y: np.ndarray, mu: np.ndarray) -> float:
    """Negative binomial size r (var = mu + mu^2 / r) by moments; inf when no extra spread."""
    excess = float(np.mean((y - mu) ** 2 - mu))
    m2 = float(np.mean(mu ** 2))
    return float(m2 / excess) if excess > 1e-9 else float("inf")


def p_over(mu, line: float, size: float) -> np.ndarray:
    """P(stat > line) for a mean (array) under the negative binomial (Poisson if size is inf)."""
    mu = np.clip(np.asarray(mu, float), 1e-6, None)
    k = np.floor(line)
    if not np.isfinite(size):
        return 1 - poisson.cdf(k, mu)
    p = size / (size + mu)
    return 1 - nbinom.cdf(k, size, p)


def saves_mean(opp_shots_proj: float, goalie_sv: float) -> float:
    """A goalie's expected saves: the shots he'll face times his save %."""
    return float(opp_shots_proj * goalie_sv)
