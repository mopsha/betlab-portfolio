"""NBA backtests (`betlab backtest nba`): the team model and the player model, walk-forward.

There are no historical NBA betting lines (docs/NBA_PLAN.md), so both are scored against
naive baselines; the market test comes from lines logged from opening night.

- **Team** (`team_eval`): each regular-season game of the test seasons predicted from
  ratings fit on earlier games; margin and total mean absolute error vs home court alone
  and the league-average total. The back-to-back effect is fit on the season before.
- **Player** (`player_eval`): regulars (15+ minutes over their last 10, 5+ prior games) in
  the test season; minutes error, CRPS of each stat's distribution, and log loss at a
  typical prop line (his last-10 median + 0.5) for each stat and combo, vs his last-10
  average. Variants: v1; v2 (usage when teammates sit, blowout minutes); v3 (plus players
  returning from missed games); v3 with tonight's starting lineup (known about 30 minutes
  before tip). Each is fit and calibrated on the training season only. Both v3 settings
  are saved: `pre_lineup` and `lineup`.
"""

from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

from betlab import config
from betlab import odds_math as om
from betlab.models import player_nba as P
from betlab.models import team_nba as T
from betlab.sources import nba

PARAMS_PATH = config.DATA_DIR / "models" / "nba_player.json"
TEAM_PATH = config.DATA_DIR / "models" / "nba_team.json"


def load(seasons) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sch, tb, pb = nba.load_schedules(seasons), nba.load_team_box(seasons), nba.load_player_box(seasons)
    tg = T.team_games(tb, sch)
    return tg[tg["pace"].between(70, 130)], P.player_games(pb, tg, sch), sch


def _team_preds(tg: pd.DataFrame, seasons, p: T.Params) -> pd.DataFrame:
    games = tg[(tg["home"] == 1) & (tg["season_type"] == 2) & tg["season"].isin(list(seasons))]
    away = tg[tg["home"] == -1][["game_id", "team", "rest", "points"]].rename(
        columns={"team": "away", "rest": "rest_away", "points": "away_pts"})
    games = games.merge(away, on="game_id")
    out = []
    for d, g in games.groupby("date"):
        r = T.fit_ratings(tg, d, p)
        for x in g.itertuples():
            pr = T.project(r, x.team, x.away, rest_home=x.rest, rest_away=x.rest_away)
            out.append({"season": x.season, "game_id": x.game_id, "date": d, "home": x.team, "away": x.away,
                        "margin": x.points - x.away_pts, "total": x.points + x.away_pts,
                        "p_margin": pr["margin"], "p_total": pr["total"], "rest": x.rest, "rest_away": x.rest_away})
    return pd.DataFrame(out)


def team_eval(tg: pd.DataFrame, train_season: int, test_seasons) -> dict:
    """Fit the back-to-back effect on the training season's residuals, then score the test seasons."""
    base = _team_preds(tg, [train_season], T.Params())
    resid = base["margin"] - base["p_margin"]
    b2b = float((-resid[base["rest"] == 1].mean() + resid[base["rest_away"] == 1].mean()) / 2)
    p = T.Params(b2b_ortg=-b2b)
    res = _team_preds(tg, test_seasons, p)
    TEAM_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEAM_PATH.write_text(json.dumps({"half_life_days": p.half_life_days, "ridge": p.ridge, "b2b_ortg": p.b2b_ortg,
                                     "fit_on": train_season}, indent=2), encoding="utf-8")
    home = res["margin"].mean()
    return {"games": len(res), "b2b_ortg": round(p.b2b_ortg, 2),
            "margin_mae": round(float((res["margin"] - res["p_margin"]).abs().mean()), 2),
            "margin_mae_home_only": round(float((res["margin"] - home).abs().mean()), 2),
            "total_mae": round(float((res["total"] - res["p_total"]).abs().mean()), 2),
            "total_mae_league_avg": round(float((res["total"] - res["total"].mean()).abs().mean()), 2)}


SHARP = ("pinnacle", "lowvig", "betonlineag")


def market_lines(lines: pd.DataFrame, sch: pd.DataFrame) -> pd.DataFrame:
    """One row per game from backfill_nba_lines.closing_lines: the sharp consensus home spread
    and total (Pinnacle, LowVig, BetOnline median; else every book), FanDuel's spread and total
    with prices, and the ESPN game_id. Games are matched on home team and tip time (±1 hour)."""
    rows = []
    for eid, ev in lines.groupby("event_id"):
        home = ev["home_team"].iloc[0]
        sharp = ev[ev["bookmaker"].isin(SHARP)]
        ref = sharp if len(sharp) else ev
        sp = ref[(ref["market"] == "spreads") & (ref["outcome"] == ev["home_team"].iloc[0])]["point"]
        tot = ref[(ref["market"] == "totals") & (ref["outcome"] == "Over")]["point"]
        if sp.empty or tot.empty:
            continue
        fd = ev[ev["bookmaker"] == "fanduel"]
        fds = fd[(fd["market"] == "spreads")]
        fdt = fd[(fd["market"] == "totals")]
        row = {"event_id": eid, "home_name": home, "tip": ev["commence_time"].iloc[0],
               "hours_before": float(ev["hours_before"].iloc[0]),
               "mkt_margin": -float(sp.median()), "mkt_total": float(tot.median())}
        h, a = fds[fds["outcome"] == ev["home_team"].iloc[0]], fds[fds["outcome"] != ev["home_team"].iloc[0]]
        if len(h) and len(a):
            row.update(fd_spread=float(h["point"].iloc[0]), fd_home_price=float(h["price"].iloc[0]),
                       fd_away_price=float(a["price"].iloc[0]))
        o, u = fdt[fdt["outcome"] == "Over"], fdt[fdt["outcome"] == "Under"]
        if len(o) and len(u):
            row.update(fd_total=float(o["point"].iloc[0]), fd_over_price=float(o["price"].iloc[0]),
                       fd_under_price=float(u["price"].iloc[0]))
        rows.append(row)
    m = pd.DataFrame(rows)
    s = sch[["game_id", "home_display_name", "start_date"]].copy()
    s["home_display_name"] = s["home_display_name"].replace(nba.ESPN_NAMES)     # "LA Clippers" -> ours
    s["tip_s"] = pd.to_datetime(s["start_date"], utc=True, format="ISO8601")
    m = m.merge(s, left_on="home_name", right_on="home_display_name")
    m = m[(m["tip"] - m["tip_s"]).abs() <= pd.Timedelta(hours=1)]
    return m.drop(columns=["home_display_name", "start_date", "tip_s"])


def market_eval(tg: pd.DataFrame, lines: pd.DataFrame, sch: pd.DataFrame, train_season: int = 2025,
                test_season: int = 2026) -> pd.DataFrame:
    """The team model's walk-forward projections for test_season next to the closing market.
    One row per game: margin/total actual, model, market; FanDuel's lines."""
    base = _team_preds(tg, [train_season], T.Params())
    resid = base["margin"] - base["p_margin"]
    b2b = float((-resid[base["rest"] == 1].mean() + resid[base["rest_away"] == 1].mean()) / 2)
    preds = _team_preds(tg, [test_season], T.Params(b2b_ortg=-b2b))
    return preds.merge(market_lines(lines, sch), on="game_id")


def _weight(y, market, model) -> tuple[float, float]:
    """Least-squares blend weight w in y = market + w (model - market), with its SE."""
    x, r = np.asarray(model - market, float), np.asarray(y - market, float)
    w = float(np.dot(x, r) / np.dot(x, x))
    se = float(np.sqrt(np.mean((r - w * x) ** 2) / np.dot(x, x)))
    return w, se


def market_report(df: pd.DataFrame) -> dict:
    """Does the model add to the closing line? MAE, blend weight, and FanDuel ATS/totals
    records when the model disagrees with the market by 2+/4+ points, by how close to tip."""
    out = {}
    for label, x in (("all", df), ("line within 1h of tip", df[df["hours_before"] <= 1]),
                     ("line 1-6h before tip", df[df["hours_before"] > 1]),
                     ("Nov-Dec", df[pd.to_datetime(df["date"]).dt.month.isin([10, 11, 12])]),
                     ("Jan-Apr", df[pd.to_datetime(df["date"]).dt.month.isin([1, 2, 3, 4])])):
        if len(x) < 30:
            continue
        wm, wm_se = _weight(x["margin"], x["mkt_margin"], x["p_margin"])
        wt, wt_se = _weight(x["total"], x["mkt_total"], x["p_total"])
        out[label] = {"games": len(x),
                      "margin_mae_model": round(float((x["margin"] - x["p_margin"]).abs().mean()), 2),
                      "margin_mae_market": round(float((x["margin"] - x["mkt_margin"]).abs().mean()), 2),
                      "margin_weight": f"{wm:.2f} ({wm_se:.2f})",
                      "total_mae_model": round(float((x["total"] - x["p_total"]).abs().mean()), 2),
                      "total_mae_market": round(float((x["total"] - x["mkt_total"]).abs().mean()), 2),
                      "total_weight": f"{wt:.2f} ({wt_se:.2f})"}
    rows = []
    fd = df.dropna(subset=["fd_spread", "fd_total"])
    for gap in (2, 4, 6):
        # spread: bet the side the model likes at FanDuel's number and price
        g = fd["p_margin"] - (-fd["fd_spread"])
        pick_home = g >= gap
        pick_away = g <= -gap
        cover = fd["margin"] + fd["fd_spread"]
        won = np.where(pick_home, cover > 0, cover < 0)
        push = cover == 0
        sel = (pick_home | pick_away) & ~push
        price = np.where(pick_home, fd["fd_home_price"], fd["fd_away_price"])
        profit = np.where(won, [om.american_to_decimal(p) - 1 for p in price], -1.0)
        rows.append({"market": "spread", "gap_at_least": gap, "bets": int(sel.sum()),
                     "win_rate": round(float(won[sel].mean()), 3) if sel.any() else None,
                     "roi": round(float(profit[sel].mean()), 3) if sel.any() else None})
        g = fd["p_total"] - fd["fd_total"]
        over, under = g >= gap, g <= -gap
        diff = fd["total"] - fd["fd_total"]
        won = np.where(over, diff > 0, diff < 0)
        sel = (over | under) & (diff != 0)
        price = np.where(over, fd["fd_over_price"], fd["fd_under_price"])
        profit = np.where(won, [om.american_to_decimal(p) - 1 for p in price], -1.0)
        rows.append({"market": "total", "gap_at_least": gap, "bets": int(sel.sum()),
                     "win_rate": round(float(won[sel].mean()), 3) if sel.any() else None,
                     "roi": round(float(profit[sel].mean()), 3) if sel.any() else None})
    return {"fit": pd.DataFrame(out).T, "fanduel": pd.DataFrame(rows)}


def _regulars(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["season_type"] == 2) & (df["n_prior"] >= 5) & (df["avg10_min"] >= 15)]


def _logloss(mu, df, k, r) -> float:
    y, line = df[k].to_numpy(float), df[f"med10_{k}"].to_numpy(float) + 0.5
    ok = np.isfinite(y) & np.isfinite(mu) & np.isfinite(line)
    p = np.clip(P.p_over(mu[ok], line[ok], r), 1e-6, 1 - 1e-6)
    o = (y[ok] > line[ok]).astype(float)
    return float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p)))


def tune(train: pd.DataFrame, params: dict) -> dict:
    """Per stat, the matchup/pace exponents, blend with the last-10 average and dispersion
    multiplier with the best log loss at a typical line, on the training season; combos
    get their own dispersion multiplier on top of their components' settings."""
    d = _regulars(train)
    tuning = {}
    for k in P.STATS:
        best = None
        for opp_e, pace_e, blend, mult in itertools.product((0.0, 0.5, 1.0), (0.0, 1.0), (0.5, 0.75, 1.0), (0.6, 0.8, 1.0)):
            t = {k: {"opp_exp": opp_e, "pace_exp": pace_e, "blend": blend}}
            mu = P.predict(d, {**params, "tuning": t})[k]
            ll = _logloss(mu, d, k, params["dispersion"][k] * mult)
            if best is None or ll < best[0]:
                best = (ll, {"opp_exp": opp_e, "pace_exp": pace_e, "blend": blend, "disp_mult": mult})
        tuning[k] = best[1]
    mu = P.predict(d, {**params, "tuning": tuning})
    for c in P.COMBOS:
        tuning[c] = {"disp_mult": min((_logloss(mu[c], d, c, params["dispersion"][c] * m), m)
                                      for m in (0.5, 0.6, 0.8, 1.0))[1]}
    return tuning


VARIANTS = {
    "v1": {"min_features": P.MIN_FEATURES, "usage": False},
    "v2": {"min_features": P.MIN_FEATURES_V2, "usage": True},
    "v3": {"min_features": P.MIN_FEATURES_V3, "usage": True},
    "v3 + lineup": {"min_features": P.MIN_FEATURES_V3 + [P.LINEUP_FEATURE], "usage": True},
}


def _fit_variant(train: pd.DataFrame, kw: dict, train_season: int) -> dict:
    params = P.fit(train, **kw)
    params["tuning"] = tune(train, params)
    params["fit_on"] = train_season
    return params


def player_eval(pg: pd.DataFrame, tg: pd.DataFrame, train_season: int, test_season: int) -> tuple[pd.DataFrame, dict]:
    """Log loss at a typical line for every variant and the naive baseline (rows), minutes
    error; saves the v2 settings before and after the starting lineup."""
    pg = P.add_team_projections(pg[pg["season"].isin([train_season, test_season])], tg)
    train = pg[(pg["season"] == train_season) & (pg["season_type"] == 2)]
    test = _regulars(pg[pg["season"] == test_season])
    keys = list(P.STATS) + list(P.COMBOS)
    rows, saved = [], {}
    for name, kw in VARIANTS.items():
        params = _fit_variant(train, kw, train_season)
        mu = P.predict(test, params)
        row = {"variant": name, "minutes_mae": float((test["minutes"] - mu["minutes"]).abs().mean())}
        for k in keys:
            row[k] = _logloss(mu[k], test, k, params["dispersion"][k] * params["tuning"][k]["disp_mult"])
        rows.append(row)
        saved[name] = params
    ref = saved["v3"]
    naive = {"variant": "naive (last-10 average)", "minutes_mae": float((test["minutes"] - test["avg10_min"]).abs().mean())}
    for k in keys:
        naive[k] = _logloss(test[f"avg10_{k}"].to_numpy(float), test, k, ref["dispersion"][k] * ref["tuning"][k]["disp_mult"])
    rows.append(naive)
    PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PARAMS_PATH.write_text(json.dumps({"pre_lineup": saved["v3"], "lineup": saved["v3 + lineup"]}, indent=2, default=float),
                           encoding="utf-8")
    return pd.DataFrame(rows).round(4), saved
