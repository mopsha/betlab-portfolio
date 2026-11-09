"""NHL props backtest: does the ML model beat simple baselines, and does our game analysis help?

Walk-forward by season: for each test season, the trees train on every earlier season
(2020 on, so the game model's projections exist) and predict the test season's games.
Scored on skaters with 5+ earlier games and 10+ minutes a night (who books post lines for):
- mean Poisson deviance of the predicted mean (lower is better);
- log loss of P(over) at the usual lines: shots 1.5 / 2.5 / 3.5, points / goals / assists 0.5.
Contenders:
- `recent`: the player's long-run rate times his recent ice time (what a box score says);
- `hand`: the same, scaled by tonight's projected team shots (or goals) against the league's;
- `ml_player`: the trees on the player features only;
- `ml`: the trees with our game analysis too (team and opponent projections, the opposing
  goalie, back-to-backs). `ml` beating `ml_player` is the evidence that the analysis helps.
`betlab backtest nhl-props` prints it and saves the final model (data/models/nhl_props.joblib).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import backtest_nhl as BG
from betlab.cards.preview_nhl import load_params
from betlab.models import props_nhl as P
from betlab.sources import nhl as src

SEASONS = range(2019, 2027)
TEST = (2025, 2026)
LINES = {"shots": (1.5, 2.5, 3.5), "points": (0.5,), "goals": (0.5,), "assists": (0.5,)}
MODEL_PATH = src.config.DATA_DIR / "models" / "nhl_props.joblib"


def prepare(seasons=SEASONS) -> pd.DataFrame:
    """Skater-game features with the game model's walk-forward projections attached."""
    tg, gg = BG.prepare(seasons)
    gm = BG.games(tg, gg)
    w = BG.walk(tg, gg, gm, load_params(), [s for s in seasons if s > min(seasons)])
    gf = P.game_features(w, tg)
    return P.features(src.load_skater_games(seasons), gf)


def _ll(p, y) -> float:
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _dev(mu, y) -> float:
    from sklearn.metrics import mean_poisson_deviance
    return float(mean_poisson_deviance(y, np.clip(mu, 1e-6, None)))


def baselines(df: pd.DataFrame, league: dict) -> dict[str, pd.DataFrame]:
    """The recent and hand-built means for every stat."""
    toi = df["toi_s"].fillna(df["toi_l"]) / 60
    rate = {"shots": df["shots60_l"], "points": df["points60_l"], "goals": df["goals60_l"], "assists": df["assists60_l"]}
    recent = pd.DataFrame({st: rate[st] * toi for st in P.STATS}, index=df.index)
    shot_k = (df["team_shots_proj"] / league["team_shots"]).fillna(1.0)
    goal_k = (df["team_xg"] / league["team_xg"]).fillna(1.0)
    present = (league["share_present"] / df["share_present"].clip(lower=0.5)).clip(0.8, 1.3).fillna(1.0)
    hand = pd.DataFrame({"shots": recent["shots"] * shot_k * present, "points": recent["points"] * goal_k,
                         "goals": recent["goals"] * goal_k, "assists": recent["assists"] * goal_k}, index=df.index)
    return {"recent": recent.fillna(0.01), "hand": hand.fillna(0.01)}


def evaluate(df: pd.DataFrame, test_seasons=TEST) -> pd.DataFrame:
    rows = []
    for season in test_seasons:
        train = df[(df["season"] < season) & (df["season"] >= 2020)]
        test = df[(df["season"] == season) & (df["games_prior"] >= 5) & (df["toi_l"] >= 10)]
        tr_ok = train[(train["games_prior"] >= 5) & (train["toi_l"] >= 10)]
        league = {"team_shots": float(train["team_shots_proj"].mean()), "team_xg": float(train["team_xg"].mean()),
                  "share_present": float(train["share_present"].median())}
        fits = {"ml": P.fit(train), "ml_player": P.fit(train, P.PLAYER_FEATURES)}
        means = {name: P.predict(f, test) for name, f in fits.items()}
        disp = {name: f.dispersion for name, f in fits.items()}
        base_tr, base_te = baselines(tr_ok, league), baselines(test, league)
        for name in ("recent", "hand"):
            means[name] = base_te[name]
            disp[name] = {st: P.nb_size(tr_ok[st].to_numpy(float), base_tr[name][st].to_numpy(float)) for st in P.STATS}
        for name, mu in means.items():
            for st in P.STATS:
                y = test[st].to_numpy(float)
                row = {"season": season, "model": name, "stat": st, "n": len(test), "deviance": _dev(mu[st], y)}
                for line in LINES[st]:
                    row[f"ll_{line}"] = _ll(P.p_over(mu[st], line, disp[name][st]), (y > line).astype(float))
                rows.append(row)
        print(f"season {season} done", flush=True)
    return pd.DataFrame(rows)


def train_final(df: pd.DataFrame, last_season: int) -> P.Fitted:
    """The live model: trained on every season through `last_season`, saved with joblib."""
    import joblib

    f = P.fit(df[(df["season"] >= 2020) & (df["season"] <= last_season)])
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(f, MODEL_PATH, compress=3)
    return f
