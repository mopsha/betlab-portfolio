"""NBA player model: minutes x per-minute rates x matchup, for points, rebounds, assists, threes.

Built for props (docs/NBA_PLAN.md). Every feature uses only games before the one being
predicted (walk-forward by construction: shifted rolling and exponentially weighted means).

1. **Minutes** (`fit` / `predict`): a regression on recent minutes (exponentially weighted,
   half-life 5 games), the last 10 games' average, how often he's started lately, the
   minutes of teammates ruled out for this game (injury, illness, rest or suspension on the
   box score's did-not-play reason, which the injury report gives before tip-off), a
   back-to-back, and home court. Fit on earlier seasons.
2. **Per-minute rates:** exponentially weighted (half-life 15 games) stat per minute, shrunk
   toward his position's league rate by 150 minutes.
3. **Matchup and pace:** the opponent's allowed points, rebounds, assists and threes per 100
   possessions against the league (shrunk), and the game's expected pace against his
   team's usual pace.
4. **Distribution:** negative binomial around the mean, dispersion fit per stat on earlier
   seasons (minutes uncertainty is inside it).
5. **Calibration settings per stat** (`params["tuning"]`, chosen on the training season by
   `backtest_nba.tune`): how much of the matchup and pace adjustments to use (exponents),
   how much to blend with his last-10 average, and a dispersion multiplier. v1 was
   overconfident at the extremes (its 77% points overs hit 66%).

v2 (2026-09-25) adds usage shifts when teammates sit (`usage_beta`: points +0.09, assists
+0.17 per unit of the team's usual production sitting), blowout minutes (starters about
-0.08 minutes per point of expected margin), combos (PRA, P+R, P+A, R+A), and an optional
starting-lineup feature: knowing tonight's starters cut minutes error 7% and was the
biggest single gain, so live props are priced after lineups (about 30 minutes before tip).

`backtest_nba.player_eval` scores every variant against a naive last-10-games average at a
typical prop line.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as st

STATS = {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes": "three_point_field_goals_made"}
OUT_REASONS_EXCLUDE = ("COACH'S DECISION",)  # a healthy scratch isn't news; everything else is
MIN_FEATURES = ["ewm_min", "avg10_min", "start_share", "missing_min", "b2b", "home"]  # v1
# v2 adds blowout minutes: starters sit in lopsided games, the bench plays more (expected
# margin from the team model in backtests; from the market spread live)
MIN_FEATURES_V2 = MIN_FEATURES + ["blowout_starter", "blowout_bench"]
LINEUP_FEATURE = "starter_now"  # tonight's starting lineup: known about 30 minutes before tip
# v3: players coming back from missed games play fewer minutes (about -1.2 per game missed,
# easing after long absences). Tested and dropped: position-specific defense (worse on every
# stat) and a short-memory "recent form" rate (tuning never used it). docs/NBA_PLAN.md.
RETURN_FEATURES = ["returning", "long_absence"]
MIN_FEATURES_V3 = MIN_FEATURES_V2 + RETURN_FEATURES
USAGE_SHARE = {"points": "missing_points_share", "rebounds": "missing_rebounds_share",
               "assists": "missing_assists_share", "threes": "missing_points_share"}
COMBOS = {"pra": ("points", "rebounds", "assists"), "pr": ("points", "rebounds"),
          "pa": ("points", "assists"), "ra": ("rebounds", "assists")}


def player_games(pb: pd.DataFrame, tg: pd.DataFrame, schedules: pd.DataFrame) -> pd.DataFrame:
    """Every player row with walk-forward features. Rows where he played carry targets."""
    p = pb.merge(schedules[["game_id", "tipoff"]], on="game_id", how="left").copy()
    p = p[p["season_type"].isin([2, 3, 5])]
    for k, col in STATS.items():
        p[k] = pd.to_numeric(p[col], errors="coerce")
    p["played"] = p["minutes"].fillna(0) > 0
    # "pending": tonight's players (live pricing, models/live_nba.py). They get features
    # from earlier games exactly like a played row, and no targets.
    p["pending"] = p["pending"].fillna(False).astype(bool) if "pending" in p else False
    p["pos"] = p["athlete_position_abbreviation"].fillna("F").str[0].map({"G": "G", "F": "F", "C": "C"}).fillna("F")
    p = p.sort_values(["athlete_id", "tipoff"]).reset_index(drop=True)

    # --- history over games he played (shifted: only earlier games)
    pl = p[p["played"] | p["pending"]].copy()
    g = pl.groupby("athlete_id")
    pl["ewm_min"] = g["minutes"].transform(lambda s: s.shift(1).ewm(halflife=5, min_periods=1).mean())
    pl["avg10_min"] = g["minutes"].transform(lambda s: s.shift(1).rolling(10, min_periods=1).mean())
    pl["start_share"] = g["starter"].transform(lambda s: s.astype(float).shift(1).ewm(halflife=5, min_periods=1).mean())
    pl["n_prior"] = g.cumcount()
    # games he missed right before tonight (DNP rows since his last game played), capped
    p["_gap"] = (~p["played"]).astype(int)
    p["_block"] = p.groupby("athlete_id")["played"].cumsum()
    missed = p.groupby(["athlete_id", "_block"])["_gap"].cumsum()
    p["missed_before"] = missed.groupby(p["athlete_id"]).shift(1).fillna(0)
    pl = pl.merge(p.loc[p["played"] | p["pending"], ["athlete_id", "game_id", "missed_before"]],
                  on=["athlete_id", "game_id"], how="left")
    pl["returning"] = pl["missed_before"].clip(upper=5).fillna(0)
    pl["long_absence"] = (pl["missed_before"] >= 5).astype(float)
    g = pl.groupby("athlete_id")
    for k in STATS:
        num = g[k].transform(lambda s: s.shift(1).ewm(halflife=15, min_periods=1).mean())
        den = g["minutes"].transform(lambda s: s.shift(1).ewm(halflife=15, min_periods=1).mean())
        pl[f"rate_{k}"] = num / den
        pl[f"avg10_{k}"] = g[k].transform(lambda s: s.shift(1).rolling(10, min_periods=1).mean())
        pl[f"med10_{k}"] = g[k].transform(lambda s: s.shift(1).rolling(10, min_periods=3).median())
    for c, parts in COMBOS.items():  # combos' own recent average and median (the naive baseline and a typical line)
        pl[c] = pl[list(parts)].sum(axis=1, min_count=len(parts))
        pl[f"med10_{c}"] = pl.groupby("athlete_id")[c].transform(lambda s: s.shift(1).rolling(10, min_periods=3).median())
        pl[f"avg10_{c}"] = pl.groupby("athlete_id")[c].transform(lambda s: s.shift(1).rolling(10, min_periods=1).mean())
    # minutes weight behind the rate (for shrinkage): weighted count of prior minutes
    pl["rate_minutes"] = g["minutes"].transform(lambda s: s.shift(1).rolling(20, min_periods=1).sum())

    # --- teammates ruled out: their latest weighted minutes (from games they played before)
    post = pl.loc[pl["played"], ["athlete_id", "tipoff"]].copy()
    played = pl[pl["played"]]
    post["ewm_after"] = played.groupby("athlete_id")["minutes"].transform(lambda s: s.ewm(halflife=5).mean())
    for k in ("points", "rebounds", "assists"):  # their usual production, for usage shifts
        post[f"{k}_after"] = played.groupby("athlete_id")[k].transform(lambda s: s.ewm(halflife=10).mean())
    out = p[~p["played"] & p["did_not_play"].fillna(False) & ~p["reason"].fillna("").isin(OUT_REASONS_EXCLUDE)]
    out = out[["game_id", "team_id", "athlete_id", "tipoff"]].sort_values("tipoff")
    post = post.sort_values("tipoff")
    out = pd.merge_asof(out, post, on="tipoff", by="athlete_id", direction="backward", allow_exact_matches=False)
    missing = (out.groupby(["game_id", "team_id"])[["ewm_after", "points_after", "rebounds_after", "assists_after"]]
               .sum().rename(columns={"ewm_after": "missing_min", "points_after": "missing_points",
                                      "rebounds_after": "missing_rebounds", "assists_after": "missing_assists"}))
    pl = pl.merge(missing, on=["game_id", "team_id"], how="left")
    for c in ("missing_min", "missing_points", "missing_rebounds", "missing_assists"):
        pl[c] = pl[c].fillna(0.0)
    pl[LINEUP_FEATURE] = pd.to_numeric(pl["starter"], errors="coerce").astype(float)

    # --- team context: rest, pace, opponent allowances (from team-games, shifted)
    t = tg[["game_id", "team", "opp", "home", "b2b", "pace", "poss"]].copy()
    abbr = pb[["team_id", "team_abbreviation"]].drop_duplicates("team_id").set_index("team_id")["team_abbreviation"]
    pl["team"] = pl["team_id"].map(abbr)
    pl = pl.merge(t, on=["game_id", "team"], how="left")
    pl = pl.merge(_team_context(pb, tg), on=["game_id", "team", "opp"], how="left")
    for k in ("points", "rebounds", "assists"):  # share of the team's usual production that sits tonight
        pl[f"missing_{k}_share"] = (pl[f"missing_{k}"] / pl[f"team_{k}_avg"]).clip(0, 0.6).fillna(0.0)
    pl["abs_margin"] = np.nan  # filled by add_team_projections (or the market spread live)
    return pl.sort_values("tipoff").reset_index(drop=True)


def add_team_projections(pg: pd.DataFrame, tg: pd.DataFrame, tp=None) -> pd.DataFrame:
    """Expected margin from the team model, walk-forward by date, as blowout features."""
    from betlab.models import team_nba as T

    home = tg[tg["home"] >= 0][["game_id", "date", "team", "rest"]]
    away = tg[tg["home"] < 0][["game_id", "team", "rest"]].rename(columns={"team": "away", "rest": "rest_away"})
    games = home.merge(away, on="game_id")
    games = games[games["game_id"].isin(pg["game_id"])]
    rows = []
    for d, g in games.groupby("date"):
        r = T.fit_ratings(tg, d, tp)
        for x in g.itertuples():
            m = T.project(r, x.team, x.away, rest_home=x.rest, rest_away=x.rest_away)["margin"]
            rows += [(x.game_id, x.team, m), (x.game_id, x.away, -m)]
    proj = pd.DataFrame(rows, columns=["game_id", "team", "proj_margin"])
    out = pg.drop(columns=["abs_margin"], errors="ignore").merge(proj, on=["game_id", "team"], how="left")
    return with_blowout(out, out["proj_margin"].abs())


def with_blowout(df: pd.DataFrame, abs_margin) -> pd.DataFrame:
    """Blowout features from an expected margin (team model or market spread)."""
    df = df.copy()
    df["abs_margin"] = np.asarray(abs_margin, dtype=float)
    m = df["abs_margin"].fillna(df["abs_margin"].median() if df["abs_margin"].notna().any() else 5.0)
    df["blowout_starter"] = m * df["start_share"]
    df["blowout_bench"] = m * (1 - df["start_share"])
    return df


def _team_context(pb: pd.DataFrame, tg: pd.DataFrame) -> pd.DataFrame:
    """Per (game, team, opp): the team's usual pace and the game's expected pace, and the
    opponent's allowed points/rebounds/assists/threes per 100 possessions vs the league,
    all from earlier games (half-life 20 games)."""
    box = pb.copy()
    for k, col in STATS.items():
        box[k] = pd.to_numeric(box[col], errors="coerce")
    abbr = pb[["team_id", "team_abbreviation"]].drop_duplicates("team_id").set_index("team_id")["team_abbreviation"]
    tot = box.groupby(["game_id", "team_id"])[list(STATS)].sum().reset_index()
    tot["team"] = tot["team_id"].map(abbr)
    t = tg[["game_id", "team", "opp", "tipoff", "pace", "poss"]].merge(tot.drop(columns="team_id"), on=["game_id", "team"])
    for k in STATS:
        t[f"{k}_p100"] = 100 * t[k] / t["poss"]
    t = t.sort_values("tipoff")
    by_team = t.groupby("team")
    t["team_pace"] = by_team["pace"].transform(lambda s: s.shift(1).ewm(halflife=20, min_periods=1).mean())
    for k in ("points", "rebounds", "assists"):
        t[f"team_{k}_avg"] = by_team[k].transform(lambda s: s.shift(1).ewm(halflife=20, min_periods=1).mean())
    # what each defense allowed: the opponent rows' production, keyed by the defense
    allowed = t[["game_id", "opp", "tipoff"] + [f"{k}_p100" for k in STATS]].rename(columns={"opp": "defense"})
    allowed = allowed.sort_values("tipoff")
    by_def = allowed.groupby("defense")
    for k in STATS:
        # the league average so far (earlier games only: no peeking at the rest of the season)
        lg = allowed[f"{k}_p100"].expanding().mean().shift(1).bfill()
        ew = by_def[f"{k}_p100"].transform(lambda s: s.shift(1).ewm(halflife=20, min_periods=1).mean())
        n = by_def.cumcount()
        allowed[f"opp_{k}"] = ((ew.fillna(lg) * n + lg * 10) / (n + 10)) / lg
    ctx = t[["game_id", "team", "opp", "team_pace", "team_points_avg", "team_rebounds_avg", "team_assists_avg"]].merge(
        allowed[["game_id", "defense"] + [f"opp_{k}" for k in STATS]], left_on=["game_id", "opp"],
        right_on=["game_id", "defense"], how="left").drop(columns="defense")
    opp_pace = t[["game_id", "team", "team_pace"]].rename(columns={"team": "opp", "team_pace": "opp_pace"})
    ctx = ctx.merge(opp_pace, on=["game_id", "opp"], how="left")
    ctx["pace_factor"] = ((ctx["team_pace"] + ctx["opp_pace"]) / 2) / ctx["team_pace"]
    return ctx.drop(columns=["opp_pace"])


def fit(train: pd.DataFrame, min_features=None, usage: bool = False) -> dict:
    """Minutes regression, position rate priors, usage shifts (v2) and negative-binomial
    dispersions (stats and combos) from training rows (players who played, 3+ prior games)."""
    feats = list(min_features or MIN_FEATURES)
    d = train[train["n_prior"] >= 3].dropna(subset=feats + ["minutes"])
    X = np.column_stack([np.ones(len(d))] + [d[c].to_numpy(float) for c in feats])
    coef = np.linalg.lstsq(X, d["minutes"].to_numpy(float), rcond=None)[0]
    params = {"min_features": feats, "min_coef": [float(c) for c in coef], "min_sd": float((d["minutes"] - X @ coef).std())}
    params["pos_rate"] = {k: (d.groupby("pos")[k].sum() / d.groupby("pos")["minutes"].sum()).to_dict() for k in STATS}
    if usage:  # y ~ mu * (1 + beta * share of the team's production sitting tonight), least squares
        base = predict(d, params)
        params["usage_beta"] = {}
        for k in STATS:
            y, m, s = d[k].to_numpy(float), base[k], d[USAGE_SHARE[k]].to_numpy(float)
            ok = np.isfinite(y) & np.isfinite(m)
            ms = m[ok] * s[ok]
            params["usage_beta"][k] = float((ms * (y[ok] - m[ok])).sum() / (ms ** 2).sum()) if (ms ** 2).sum() else 0.0
    mu = predict(d, params)
    params["dispersion"] = {}
    for k in list(STATS) + list(COMBOS):
        y = (d[list(COMBOS[k])].sum(axis=1, min_count=len(COMBOS[k])) if k in COMBOS else d[k]).to_numpy(float)
        m = mu[k]
        ok = np.isfinite(y) & np.isfinite(m) & (m > 0)
        excess = ((y[ok] - m[ok]) ** 2 - m[ok]).sum()
        params["dispersion"][k] = float((m[ok] ** 2).sum() / excess) if excess > 0 else 1e3
    return params


def predict(df: pd.DataFrame, params: dict) -> dict[str, np.ndarray]:
    """Expected minutes and expected stats per row."""
    feats = params.get("min_features", MIN_FEATURES)
    X = np.column_stack([np.ones(len(df))] + [df[c].to_numpy(float) for c in feats])
    minutes = np.clip(X @ np.array(params["min_coef"]), 0, 48)
    out = {"minutes": minutes}
    tuning = params.get("tuning", {})
    for k in STATS:
        tu = tuning.get(k, {})
        prior = df["pos"].map(params["pos_rate"][k]).to_numpy(float)
        raw = df[f"rate_{k}"].to_numpy(float)
        w = df["rate_minutes"].fillna(0).to_numpy(float)
        rate = (np.nan_to_num(raw) * w + prior * 150) / (w + 150)
        opp = df[f"opp_{k}"].fillna(1.0).to_numpy(float) ** tu.get("opp_exp", 1.0) if f"opp_{k}" in df else 1.0
        pace = df["pace_factor"].fillna(1.0).to_numpy(float) ** tu.get("pace_exp", 1.0) if "pace_factor" in df else 1.0
        mean = minutes * rate * opp * pace
        beta = params.get("usage_beta", {}).get(k, 0.0)
        if beta and USAGE_SHARE[k] in df:
            mean = mean * (1 + beta * df[USAGE_SHARE[k]].fillna(0.0).to_numpy(float))
        blend = tu.get("blend", 1.0)
        if blend < 1.0 and f"avg10_{k}" in df:
            recent = df[f"avg10_{k}"].to_numpy(float)
            mean = np.where(np.isfinite(recent), blend * mean + (1 - blend) * recent, mean)
        out[k] = mean
    for c, parts in COMBOS.items():
        out[c] = sum(out[k] for k in parts)
    return out


def p_over(mu: np.ndarray, line: np.ndarray, r: float) -> np.ndarray:
    """P(stat > line) under a negative binomial with mean mu and dispersion r."""
    mu = np.maximum(mu, 1e-6)
    p = r / (r + mu)
    return st.nbinom.sf(np.floor(line), r, p)


def crps(mu: np.ndarray, y: np.ndarray, r: float, kmax: int = 90) -> np.ndarray:
    """CRPS of the negative binomial predictive distribution at each observation (in stat units)."""
    mu = np.maximum(mu, 1e-6)
    k = np.arange(kmax + 1)
    cdf = st.nbinom.cdf(k[None, :], r, (r / (r + mu))[:, None])
    step = (k[None, :] >= y[:, None]).astype(float)
    return ((cdf - step) ** 2).sum(axis=1)
