"""The anytime TD read's backtest and fit (`betlab backtest td`): models/td_nfl.py.

Train on 2023-24, test on 2025 (log loss against usage + team points alone, game
bootstrap, calibration by eighths), then refit on 2023-25 and save the coefficients to
data/models/td_params.json for the live read.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.models import td_nfl as T
from betlab.sources import nflverse

BASE = ["is_RB", "is_WR", "is_TE", "lpts", "lopp"]


def training(seasons=(2022, 2023, 2024, 2025)) -> pd.DataFrame:
    """Player-games with rolling features from earlier games and the team's expected points."""
    pbp = nflverse.load_pbp(list(seasons), columns=["game_id", "season", "week", "posteam", "yardline_100",
                                                   "play_type", "rusher_player_id", "receiver_player_id"])
    d = T.rolling(T.player_games(pbp, nflverse.load_player_stats(list(seasons))), shift=1)
    g = nflverse.load_games()[["game_id", "home_team", "spread_line", "total_line"]]
    d = d.merge(g, on="game_id", how="left")
    home = d["posteam"] == d["home_team"]
    d["team_pts"] = np.where(home, (d["total_line"] + d["spread_line"]) / 2, (d["total_line"] - d["spread_line"]) / 2)
    d = d.dropna(subset=["opp_share", "team_pts"])
    return d[d["position"].isin(["RB", "WR", "TE", "QB"])].reset_index(drop=True)


def _ll(p, y):
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def run(d: pd.DataFrame | None = None, test_season: int = 2025, boot: int = 300, save: bool = True) -> dict:
    d = training() if d is None else d
    prior = d.groupby("position")["td"].mean().to_dict()
    X = pd.DataFrame(T.design(d, d["team_pts"], prior), columns=T.FEATURES)
    y = d["td"].to_numpy(float)
    tr, te = (d["season"] < test_season).to_numpy() & (d["season"] >= test_season - 2).to_numpy(), (d["season"] == test_season).to_numpy()
    games = d.loc[te, "game_id"].to_numpy()
    rows, ref = [], None
    for name, cols in (("usage + team points", BASE), ("+ red zone", BASE + ["rz20_share", "rz10_share"]),
                       ("+ recent TD rate", BASE + ["td_rate"]), ("+ both (the read)", T.FEATURES)):
        b = T.fit(X.loc[tr, cols].to_numpy(), y[tr])
        p = T.predict(b, X.loc[te, cols].to_numpy())
        loss = _ll(p, y[te])
        ref = loss if ref is None else ref
        by = pd.Series(ref - loss).groupby(games).sum()
        rng = np.random.default_rng(0)
        bs = [by.iloc[rng.integers(0, len(by), len(by))].sum() / len(loss) for _ in range(boot)]
        rows.append({"model": name, "test_log_loss": round(float(loss.mean()), 4),
                     "gain": round(float((ref - loss).mean()), 4), "se": round(float(np.std(bs)), 4)})
    calib = pd.DataFrame({"p": p, "td": y[te]})
    calib = calib.groupby(pd.qcut(calib["p"], 8), observed=True).agg(n=("td", "size"), predicted=("p", "mean"),
                                                                      scored=("td", "mean")).round(3)
    final = T.fit(X.loc[d["season"] >= test_season - 2, T.FEATURES].to_numpy(), y[(d["season"] >= test_season - 2).to_numpy()])
    params = {"coef": [round(float(v), 5) for v in final], "features": ["intercept"] + T.FEATURES,
              "prior_td": {k: round(float(v), 4) for k, v in prior.items()},
              "trained": f"{test_season - 2}-{test_season}", "n": int((d["season"] >= test_season - 2).sum()),
              "validation": rows, "fitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if save:
        T.PARAMS.parent.mkdir(parents=True, exist_ok=True)
        T.PARAMS.write_text(json.dumps(params, indent=2))
    return {"table": pd.DataFrame(rows), "calibration": calib, "params": params}
