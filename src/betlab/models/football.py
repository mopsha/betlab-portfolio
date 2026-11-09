"""Football game model, shared by the NFL and college football.

1. Offense/defense ratings, refit before every week using only earlier games,
   on points scored and on EPA per play. The two are 95% correlated and EPA
   adds no predictive value in a backtest, so only the points ratings feed the
   prediction; EPA ratings are kept for the why-notes.
2. A linear combiner turns ratings (plus rest) into a predicted margin/total.
3. Key-number distributions turn those into probabilities for any line.
4. Our probability is blended with the market's no-vig probability (see
   betlab.edge); the blend weights are fit on history.

Every coefficient is fit on a training block of seasons and evaluated on
later seasons the fit never saw.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from betlab import odds_math as om
from betlab.edge import fit_blend_weight
from betlab.models.margins import KeyNumberDist
from betlab.models.ratings import fit_ratings


@dataclass
class GameParams:
    """Every setting of the football model; saved as data/models/<league>_params.json."""

    half_life_days: float = 150.0   # NFL: tuned on 2009-2018
    ridge_pts: float = 3.0
    ridge_epa: float = 3.0
    margin_coef: list[float] = field(default_factory=lambda: [0.0, 1.0, 0.0])  # c0, pts_margin, rest_diff
    total_coef: list[float] = field(default_factory=lambda: [0.0, 1.0])       # d0, pts_total
    margin_sd: float = 13.5          # spread of outcomes around OUR prediction
    total_sd: float = 13.5
    market_margin_sd: float = 13.0   # spread of outcomes around the MARKET's line
    market_total_sd: float = 13.0
    w_spread: float = 0.0            # weight on our model vs the no-vig market
    w_total: float = 0.0
    w_ml: float = 0.0
    early_weeks: int = 2             # through this week the ratings lack current-season data:
                                     # the model gets no weight, and blend weights ignore these weeks

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "GameParams":
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def rating_features(games: pd.DataFrame, target: pd.DataFrame, asof: pd.Timestamp, p: GameParams) -> pd.DataFrame:
    """Rating-based features for `target` games, using only games before `asof`."""
    pts = fit_ratings(games, asof, "home_pts", "away_pts", p.half_life_days, p.ridge_pts)
    epa = fit_ratings(games, asof, "home_epa", "away_epa", p.half_life_days, p.ridge_epa)
    out = target.copy()
    rows = [pts.predict(h, a, n) + epa.predict(h, a, n)
            for h, a, n in zip(target["home_team"], target["away_team"], target["neutral"])]
    arr = np.array(rows) if rows else np.empty((0, 4))
    out["pts_home"], out["pts_away"] = arr[:, 0], arr[:, 1]
    out["pts_margin"] = out["pts_home"] - out["pts_away"]
    out["pts_total"] = out["pts_home"] + out["pts_away"]
    out["epa_margin"] = arr[:, 2] - arr[:, 3]
    out["rest_diff"] = (target["home_rest"] - target["away_rest"]).clip(-7, 7).fillna(0)
    return out


def walk_forward(games: pd.DataFrame, seasons, p: GameParams) -> pd.DataFrame:
    """Predict every game of `seasons` week by week, never peeking ahead."""
    parts = []
    for _, wk in games[games["season"].isin(seasons)].groupby(["season", "week"]):
        parts.append(rating_features(games, wk, wk["date"].min(), p))
    return pd.concat(parts, ignore_index=True)


def apply(df: pd.DataFrame, p: GameParams) -> pd.DataFrame:
    """Add model_margin and model_total from the rating features via the combiner."""
    out = df.copy()
    out["model_margin"] = np.column_stack(
        [np.ones(len(out)), out["pts_margin"], out["rest_diff"]]) @ np.array(p.margin_coef)
    out["model_total"] = np.column_stack([np.ones(len(out)), out["pts_total"]]) @ np.array(p.total_coef)
    return out


def fit_distributions(games: pd.DataFrame) -> tuple[KeyNumberDist, KeyNumberDist]:
    """Key-number distributions for margins (symmetric) and totals, from completed games."""
    done = games.dropna(subset=["margin", "total"])
    margin = KeyNumberDist.fit(done["margin"], -70, 70, symmetric=True)
    total = KeyNumberDist.fit(done["total"], 0, 120, symmetric=False)
    return margin, total


# ------------------------------------------------------------ probabilities

def spread_probs(model_margin: float, spread_line: float, p: GameParams, dist: KeyNumberDist):
    """(P home covers, P push) for the home side at -spread_line."""
    cover, push, _ = dist.over_push_under(model_margin, p.margin_sd, spread_line)
    return cover, push


def total_probs(model_total: float, line: float, p: GameParams, dist: KeyNumberDist):
    over, push, _ = dist.over_push_under(model_total, p.total_sd, line)
    return over, push


def ml_prob(model_margin: float, p: GameParams, dist: KeyNumberDist) -> float:
    """P(home wins | no tie). NFL moneylines refund on a tie."""
    win, tie, _ = dist.over_push_under(model_margin, p.margin_sd, 0)
    return win / (1 - tie)


def market_rows(df: pd.DataFrame, p: GameParams, md: KeyNumberDist, td: KeyNumberDist) -> pd.DataFrame:
    """Model vs no-vig market probabilities (conditional on no push) for each game's closing lines."""
    rows = []
    for r in df.itertuples():
        row = {"game_id": r.game_id, "season": r.season}
        if r.week <= p.early_weeks:  # the market alone prices early-season games
            rows.append(row)
            continue
        if pd.notna(r.spread_line) and pd.notna(r.home_spread_odds) and pd.notna(r.away_spread_odds):
            cover, push = spread_probs(r.model_margin, r.spread_line, p, md)
            row |= {"sp_model": cover / (1 - push), "sp_push": push,
                    "sp_market": om.devig([r.home_spread_odds, r.away_spread_odds])[0],
                    "sp_y": np.nan if r.margin == r.spread_line else float(r.margin > r.spread_line)}
        if pd.notna(r.total_line) and pd.notna(r.over_odds) and pd.notna(r.under_odds):
            over, push = total_probs(r.model_total, r.total_line, p, td)
            row |= {"to_model": over / (1 - push), "to_push": push,
                    "to_market": om.devig([r.over_odds, r.under_odds])[0],
                    "to_y": np.nan if r.total == r.total_line else float(r.total > r.total_line)}
        if pd.notna(r.home_moneyline) and pd.notna(r.away_moneyline):
            row |= {"ml_model": ml_prob(r.model_margin, p, md),
                    "ml_market": om.devig([r.home_moneyline, r.away_moneyline])[0],
                    "ml_y": np.nan if r.margin == 0 else float(r.margin > 0)}
        rows.append(row)
    return pd.DataFrame(rows)


def fit_params(train: pd.DataFrame, p: GameParams, md: KeyNumberDist, td: KeyNumberDist) -> GameParams:
    """Fit the combiner, outcome spreads and market-blend weights on training predictions."""
    t = train.dropna(subset=["margin", "total"])
    X = np.column_stack([np.ones(len(t)), t["pts_margin"], t["rest_diff"]])
    p.margin_coef = np.linalg.lstsq(X, t["margin"], rcond=None)[0].tolist()
    Xt = np.column_stack([np.ones(len(t)), t["pts_total"]])
    p.total_coef = np.linalg.lstsq(Xt, t["total"], rcond=None)[0].tolist()
    t = apply(t, p)

    def best_sd(dist, centers, actual, grid):
        return float(max(grid, key=lambda sd: dist.log_likelihood(centers, [sd] * len(centers), actual)))

    p.margin_sd = best_sd(md, t["model_margin"].round(1), t["margin"], np.arange(12.0, 21.01, 0.5))
    p.total_sd = best_sd(td, t["model_total"].round(1), t["total"], np.arange(11.0, 21.01, 0.5))
    lines = t.dropna(subset=["spread_line", "total_line"])
    p.market_margin_sd = best_sd(md, lines["spread_line"], lines["margin"], np.arange(11.0, 20.01, 0.5))
    p.market_total_sd = best_sd(td, lines["total_line"], lines["total"], np.arange(11.0, 20.01, 0.5))

    m = market_rows(t, p, md, td)
    for key, attr in (("sp", "w_spread"), ("to", "w_total"), ("ml", "w_ml")):
        sub = m.dropna(subset=[f"{key}_model", f"{key}_market", f"{key}_y"])
        setattr(p, attr, fit_blend_weight(sub[f"{key}_model"], sub[f"{key}_market"], sub[f"{key}_y"]))
    return p


def production_params(games: pd.DataFrame, first_season: int = 2009,
                      base: GameParams | None = None) -> tuple[GameParams, KeyNumberDist, KeyNumberDist]:
    """Fit on every completed game, for live predictions. `base` sets the rating memory/shrinkage."""
    base = base or GameParams()
    done = games.dropna(subset=["margin"])
    seasons = range(first_season, int(done["season"].max()) + 1)
    wf = walk_forward(done, seasons, base)
    md, td = fit_distributions(done)
    return fit_params(wf, base, md, td), md, td
