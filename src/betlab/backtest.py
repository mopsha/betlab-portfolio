"""Walk-forward backtests: fit on early seasons, judge on later ones.

The honest benchmark is the closing line. Beating it on log loss, or finding
picks that win above break-even at closing prices, is the bar. Most models
don't clear it, and the report says so.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import odds_math as om
from betlab.edge import blend_prob, log_loss
from betlab.models import football


def _pick_log(m: pd.DataFrame, key: str, w: float, prices: pd.DataFrame, thresholds) -> list[dict]:
    """Bet whichever side has EV >= threshold at the closing price."""
    sub = m.dropna(subset=[f"{key}_model", f"{key}_market"]).merge(prices, on="game_id")
    p_final = blend_prob(sub[f"{key}_model"], sub[f"{key}_market"], w)
    push = sub.get(f"{key}_push", pd.Series(0.0, index=sub.index)).fillna(0)
    out = []
    for th in thresholds:
        wins = losses = pushes = 0
        units = 0.0
        for pf, pu, y, a_price, b_price in zip(p_final, push, sub[f"{key}_y"], sub["a_price"], sub["b_price"]):
            p_a, p_b = pf * (1 - pu), (1 - pf) * (1 - pu)
            for p_side, price, side_wins in ((p_a, a_price, 1.0), (p_b, b_price, 0.0)):
                if om.expected_value(p_side, price, pu) >= th:
                    if np.isnan(y):
                        pushes += 1
                    elif y == side_wins:
                        wins += 1
                        units += om.american_to_decimal(price) - 1
                    else:
                        losses += 1
                        units -= 1
        n = wins + losses
        out.append({"market": key, "min_ev": th, "record": f"{wins}-{losses}-{pushes}",
                    "win_pct": round(wins / n, 3) if n else None, "units": round(units, 1),
                    "roi": round(units / (n + pushes), 3) if n else None})
    return out


def nfl(train_seasons=range(2009, 2019), test_seasons=range(2019, 2026), first_season=2006):
    """NFL: fit on 2009-2018, judge on 2019-2025 (results in docs/MODELS.md)."""
    from betlab.sources import nflverse

    return run_football(nflverse.games_with_epa(first_season), train_seasons, test_seasons)


def ncaaf(train_seasons=range(2016, 2022), test_seasons=range(2022, 2026), p=None):
    """College: fit on 2016-2021, judge on 2022-2025. Pass p to try other rating settings."""
    from betlab.sources import cfbd

    return run_football(cfbd.games(), train_seasons, test_seasons, p)


def run_football(games: pd.DataFrame, train_seasons, test_seasons, p=None):
    """Walk-forward backtest of the shared football model on any league's games table.

    Returns (report, test_predictions, market_rows). report holds the fitted params,
    log loss per market (market vs model vs blend) and pick results at several EV
    thresholds, bet at the closing price.
    """
    p = p or football.GameParams()
    wf = football.walk_forward(games, list(train_seasons) + list(test_seasons), p)
    train, test = wf[wf["season"].isin(train_seasons)], wf[wf["season"].isin(test_seasons)]
    md, td = football.fit_distributions(games[games["season"] < min(test_seasons)])
    p = football.fit_params(train, p, md, td)

    test = football.apply(test.dropna(subset=["margin", "total"]), p)
    m = football.market_rows(test, p, md, td)
    report = {"params": p, "log_loss": {}, "picks": []}
    thresholds = (0.0, 0.02, 0.03, 0.05)
    price_cols = {
        "sp": ("home_spread_odds", "away_spread_odds"),
        "to": ("over_odds", "under_odds"),
        "ml": ("home_moneyline", "away_moneyline"),
    }
    for key, w in (("sp", p.w_spread), ("to", p.w_total), ("ml", p.w_ml)):
        sub = m.dropna(subset=[f"{key}_model", f"{key}_market", f"{key}_y"])
        report["log_loss"][key] = {
            "n": len(sub),
            "market": round(log_loss(sub[f"{key}_market"], sub[f"{key}_y"]), 4),
            "model": round(log_loss(sub[f"{key}_model"], sub[f"{key}_y"]), 4),
            "blend": round(log_loss(blend_prob(sub[f"{key}_model"], sub[f"{key}_market"], w), sub[f"{key}_y"]), 4),
            "w_model": w,
        }
        a, b = price_cols[key]
        prices = test[["game_id", a, b]].rename(columns={a: "a_price", b: "b_price"})
        report["picks"] += _pick_log(m, key, w, prices, thresholds)
    return report, test, m
