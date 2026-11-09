"""Walk-forward checks of the game-flow engine's QB and weather terms (`betlab backtest game`).

- **QB ratings** (`qb_eval`): for every regular-season team-game, the team's pass EPA per
  dropback predicted from the ratings alone vs. with `qb_adjust` for the QB who started
  (the passer with the most dropbacks, known before kickoff in nearly every game).
  Scored by dropback-weighted squared error, overall and on games after a QB change.
  The settings were chosen on 2023-25; 2016-22 is the check they weren't tuned on.
- **Weather** (`weather_eval`): residuals of each team-game's stats from the
  walk-forward ratings, regressed on wind above 10 mph, rain or snow, and freezing
  cold, with game-bootstrap standard errors, plus the average residual by wind bucket.
  These fitted numbers are `game_nfl.WEATHER`.
- **Non-QB absences** (`injury_eval`): the same residuals (with the QB adjustment in the
  baseline) regressed on the counts of missing regulars from `injuries_nfl.absences`
  (offensive-line starters, the top target, the lead back, and the opponent's top pass
  rusher, front-seven and secondary starters), with game-bootstrap SEs and each half of
  the seasons. The ones that held are `injuries_nfl.EFFECTS`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab.models import game_nfl as GN
from betlab.sources import nflverse


def load(first_season: int, last_season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(team_games, qb_games) for the seasons, from nflverse play-by-play."""
    games = nflverse.load_games()
    parts_tg, parts_qg = [], []
    for lo in range(first_season, last_season + 1, 3):  # three seasons at a time keeps memory down
        pbp = nflverse.load_pbp(range(lo, min(lo + 3, last_season + 1)))
        parts_tg.append(GN.team_games(pbp, games))
        parts_qg.append(GN.qb_games(pbp, games))
    return (pd.concat(parts_tg).sort_values(["date", "game_id"]).reset_index(drop=True),
            pd.concat(parts_qg).sort_values(["date", "game_id"]).reset_index(drop=True))


def qb_eval(tg: pd.DataFrame, qg: pd.DataFrame, test_seasons, gp: GN.GameParams | None = None) -> pd.DataFrame:
    """One row per test team-game: actual pass EPA, dropbacks, the ratings-only
    prediction, the QB-adjusted one, and whether the starter changed from last game."""
    gp = gp or GN.GameParams()
    starters = qg[qg["starter"]][["game_id", "team", "passer_id"]].rename(columns={"passer_id": "starter"})
    t = tg.merge(starters, on=["game_id", "team"], how="left").sort_values(["date", "game_id"])
    t["qb_change"] = t["starter"].ne(t.groupby("team")["starter"].shift(1)) & t.groupby("team")["starter"].shift(1).notna()
    test = t[t["season"].isin(list(test_seasons)) & t["pass_epa"].notna() & (t["game_type"] == "REG")]
    rows = []
    for d, g in test.groupby("date"):
        r = GN.fit_ratings(tg, d, gp)
        qbr = GN.qb_ratings(qg, r, d, gp)
        for x in g.itertuples():
            base = GN._unit(r, "pass_epa", x.team, x.opp, x.home)
            adj = GN.qb_adjust(qg, qbr, x.team, x.starter if isinstance(x.starter, str) else None, d, gp)["adj"]
            rows.append({"game_id": x.game_id, "season": x.season, "team": x.team, "y": x.pass_epa,
                         "n": x.dropbacks, "base": base, "qb": base + adj, "qb_change": bool(x.qb_change)})
    return pd.DataFrame(rows)


def qb_report(res: pd.DataFrame) -> pd.DataFrame:
    """Dropback-weighted squared error of the pass EPA prediction, without and with the QB term."""
    out = []
    for name, m in (("all games", np.ones(len(res), bool)), ("after a QB change", res["qb_change"].to_numpy())):
        for seasons, s in res.groupby(res["season"].map(lambda y: "2016-22" if y <= 2022 else "2023-25")):
            k = m[res.index.get_indexer(s.index)]
            e = lambda col: float(np.average((s["y"][k] - s[col][k]) ** 2, weights=s["n"][k]))
            out.append({"games": name, "seasons": seasons, "n": int(k.sum()), "ratings only": e("base"),
                        "with QB": e("qb"), "change": e("qb") / e("base") - 1})
    return pd.DataFrame(out).round(4)


def weather_eval(tg: pd.DataFrame, wx: pd.DataFrame, test_seasons, boot: int = 200, seed: int = 0) -> dict:
    """Weather effects on team-game stats beyond the walk-forward ratings."""
    test = tg[tg["season"].isin(list(test_seasons))].merge(wx, on="game_id")
    stats = ("pass_epa", "rush_epa", "neutral_pass", "explosive", "plays")
    rows = []
    for d, g in test.groupby("date"):
        r = GN.fit_ratings(tg, d)
        for x in g.itertuples():
            rows.append({"game_id": x.game_id, "team": x.team,
                         **{f"p_{k}": GN._unit(r, k, x.team, x.opp, x.home) for k in stats}})
    res = test.merge(pd.DataFrame(rows), on=["game_id", "team"])
    res = res[res["wind"].notna()].reset_index(drop=True)
    X = np.column_stack([np.ones(len(res)), (res["wind"] - 10).clip(lower=0, upper=15) / 10,
                         res["precip"].astype(float), res["cold"].fillna(False).astype(float)])
    gids = res["game_id"].to_numpy()
    rows_of = pd.Series(np.arange(len(res))).groupby(gids).apply(np.array)
    rng = np.random.default_rng(seed)
    fits = []
    for stat, weight in (("pass_epa", "dropbacks"), ("rush_epa", "rushes"), ("neutral_pass", None),
                         ("explosive", "plays"), ("plays", None)):
        y = (res[stat] - res[f"p_{stat}"]).to_numpy()
        w = res[weight].to_numpy(dtype=float) if weight else np.ones(len(res))

        def fit(idx):
            idx = idx[np.isfinite(y[idx])]
            sw = np.sqrt(w[idx])[:, None]
            return np.linalg.lstsq(X[idx] * sw, y[idx] * sw[:, 0], rcond=None)[0]

        b = fit(np.arange(len(res)))
        bs = np.array([fit(np.concatenate(rows_of.loc[rng.choice(rows_of.index, len(rows_of))].to_list()))
                       for _ in range(boot)])
        fits.append({"stat": stat, "wind_per_10mph": b[1], "wind_se": bs[:, 1].std(), "precip": b[2],
                     "precip_se": bs[:, 2].std(), "cold": b[3], "cold_se": bs[:, 3].std()})
    outdoor = res[~res["indoor"]]
    bucket = pd.cut(outdoor["wind"], [-1, 9.99, 14.99, 19.99, 99], labels=["under 10", "10-14", "15-19", "20+"])
    by_wind = (outdoor["pass_epa"] - outdoor["p_pass_epa"]).groupby(bucket, observed=True).agg(["mean", "size"])
    return {"fits": pd.DataFrame(fits).round(4), "pass_epa_by_wind": by_wind.round(4), "n": len(res),
            "windy": int((outdoor["wind"] >= 15).sum()), "precip": int(res["precip"].sum()),
            "cold": int(res["cold"].fillna(False).sum())}


INJURY_FEATURES = {"own": ["ol_out", "top_target_out", "lead_back_out"], "opp": ["rusher_out", "front_out", "back_out"]}


def injury_eval(tg: pd.DataFrame, qg: pd.DataFrame, ab: pd.DataFrame, test_seasons, boot: int = 200,
                seed: int = 0, gp: GN.GameParams | None = None) -> dict:
    """Non-QB absences (injuries_nfl.absences) vs each offense's pass EPA, rush EPA and
    pressure rate, beyond the walk-forward ratings and the QB adjustment. Regressions with
    game-bootstrap standard errors, fit on all test seasons and on each half."""
    gp = gp or GN.GameParams()
    starters = qg[qg["starter"]][["game_id", "team", "passer_id"]].rename(columns={"passer_id": "starter"})
    t = tg.merge(starters, on=["game_id", "team"], how="left")
    test = t[t["season"].isin(list(test_seasons)) & t["pass_epa"].notna() & (t["game_type"] == "REG")]
    rows = []
    for d, g in test.groupby("date"):
        r = GN.fit_ratings(tg, d, gp)
        qbr = GN.qb_ratings(qg, r, d, gp)
        for x in g.itertuples():
            adj = GN.qb_adjust(qg, qbr, x.team, x.starter if isinstance(x.starter, str) else None, d, gp)["adj"]
            rows.append({"game_id": x.game_id, "team": x.team, "p_pass_epa": GN._unit(r, "pass_epa", x.team, x.opp, x.home) + adj,
                         "p_rush_epa": GN._unit(r, "rush_epa", x.team, x.opp, x.home),
                         "p_pressure": GN._unit(r, "pressure", x.team, x.opp, x.home)})
    res = test.merge(pd.DataFrame(rows), on=["game_id", "team"])
    own = ab.set_index(["game_id", "team"])[INJURY_FEATURES["own"]]
    opp = ab.rename(columns={"team": "opp"}).set_index(["game_id", "opp"])[INJURY_FEATURES["opp"]]
    res = res.join(own, on=["game_id", "team"]).join(opp, on=["game_id", "opp"])
    feats = INJURY_FEATURES["own"] + INJURY_FEATURES["opp"]
    res = res.dropna(subset=feats).reset_index(drop=True)
    X = np.column_stack([np.ones(len(res))] + [res[f].to_numpy(float) for f in feats])
    rng = np.random.default_rng(seed)
    out = []
    for stat, weight in (("pass_epa", "dropbacks"), ("rush_epa", "rushes"), ("pressure", "dropbacks")):
        y = (res[stat] - res[f"p_{stat}"]).to_numpy(float)
        w = res[weight].to_numpy(float)
        for label, mask in (("all", np.ones(len(res), bool)), ("first half", res["season"] <= np.median(list(test_seasons))),
                            ("second half", res["season"] > np.median(list(test_seasons)))):
            idx_all = np.where(np.asarray(mask) & np.isfinite(y))[0]
            gids = res["game_id"].to_numpy()[idx_all]
            groups = pd.Series(idx_all).groupby(gids).apply(np.array)

            def fit(idx):
                sw = np.sqrt(w[idx])[:, None]
                return np.linalg.lstsq(X[idx] * sw, y[idx] * sw[:, 0], rcond=None)[0]

            b = fit(idx_all)
            bs = np.array([fit(np.concatenate(groups.loc[rng.choice(groups.index, len(groups))].to_list()))
                           for _ in range(boot)]) if label == "all" else None
            row = {"stat": stat, "seasons": label, "n": len(idx_all)}
            for i, f in enumerate(feats, start=1):
                row[f] = round(float(b[i]), 4)
                if bs is not None:
                    row[f + "_se"] = round(float(bs[:, i].std()), 4)
            out.append(row)
    return {"fits": pd.DataFrame(out), "n": len(res), "rates": res[feats].mean().round(3).to_dict(), "data": res}
