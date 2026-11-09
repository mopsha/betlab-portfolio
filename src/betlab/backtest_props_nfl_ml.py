"""Does the NFL props ML model (models/props_nfl_ml.py) beat v0.2 and add to the market on real lines?
(`betlab backtest nfl-props-ml`, Oct 10.)

The test set is backtest_props.market_eval's: every FanDuel main line from 2025 weeks 3-18 (the props
backfill), with the market's no-vig chance (Pinnacle, else BetOnline or a consensus) and v0.2's chance
from the same pregame simulation. The ML model trains on 2016-2024 player-games and prices the same
player in the same game. Reported by stat:

- log loss of the market, v0.2 and ML, and of the market with the over-lean correction
  (settings props.market_shift);
- the ML weight in a blend with the corrected market, fit on weeks 3-10 and scored on 11-18
  (out of sample): the only number that could give the model weight in prices (rule 3);
- what betting FanDuel at 5%+ EV would have returned with that blend, weeks 11-18.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab import config
from betlab.models import props_nfl_ml as ML

CACHE = config.DATA_DIR / "cache" / "nfl_props_market_2025.parquet"
STAT_TARGET = {"receptions": "receptions", "receiving_yards": "receiving_yards", "rushing_yards": "rushing_yards",
               "passing_yards": "passing_yards"}


def market_rows(refresh: bool = False) -> pd.DataFrame:
    """market_eval's rows for the 2025 backfill (slow: a pregame simulation per game), cached."""
    from betlab import backtest_props

    if CACHE.exists() and not refresh:
        return pd.read_parquet(CACHE)
    lines = pd.read_parquet(config.DATA_DIR / "odds_history" / "americanfootball_nfl" / "props_2025.parquet")
    m = backtest_props.market_eval(lines)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    m.to_parquet(CACHE, index=False)
    return m


def ml_prices(m: pd.DataFrame, feats: pd.DataFrame, fitted: ML.Fitted) -> pd.Series:
    """The ML model's P(over) for each market row (NaN when the player-game has no features)."""
    rows = feats.set_index(["game_id", "player_id"])
    rows = rows[~rows.index.duplicated()]
    keys = list(zip(m["game_id"], m["player_id"]))
    have = [k in rows.index for k in keys]
    sub = rows.loc[[k for k, h in zip(keys, have) if h]]
    mu = ML.predict(fitted, sub)
    out = []
    j = 0
    for (k, h), r in zip(zip(keys, have), m.itertuples()):
        if not h:
            out.append(np.nan)
            continue
        t = STAT_TARGET[r.stat]
        out.append(ML.p_over(fitted, t, sub.iloc[j]["position"], float(mu.iloc[j][t]), float(r.line)))
        j += 1
    return pd.Series(out, index=m.index)


def _ll(p, y) -> float:
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _shift(p: pd.Series, stat: pd.Series) -> pd.Series:
    """The market with the over-lean correction (log-odds shift per stat, settings props.market_shift)."""
    shift = (config.settings().get("props") or {}).get("market_shift", {})
    lo = np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4))) + stat.map(shift).fillna(0).to_numpy()
    return pd.Series(1 / (1 + np.exp(-lo)), index=p.index)


def report(m: pd.DataFrame) -> dict:
    from betlab import edge
    from betlab import odds_math as om

    m = m[m["p_ml"].notna()].copy()
    m["p_mkt_c"] = _shift(m["p_market"], m["stat"])
    first, second = m[m["week"] <= 10], m[m["week"] >= 11]
    rows = []
    for stat, g in list(m.groupby("stat")) + [("all", m)]:
        y = g["over"].to_numpy()
        tr = first if stat == "all" else first[first["stat"] == stat]
        te = second if stat == "all" else second[second["stat"] == stat]
        w = edge.fit_blend_weight(tr["p_ml"], tr["p_mkt_c"], tr["over"]) if len(tr) else 0.0
        blend_te = edge.blend_prob(te["p_ml"], te["p_mkt_c"], w)
        rows.append({"stat": stat, "n": len(g), "market": _ll(g["p_market"], y), "market corrected": _ll(g["p_mkt_c"], y),
                     "v0.2": _ll(g["p_model"], y), "ML": _ll(g["p_ml"], y), "w_ML (wk 3-10)": round(w, 3),
                     "corrected, wk 11-18": _ll(te["p_mkt_c"], te["over"].to_numpy()),
                     "blend, wk 11-18": _ll(blend_te, te["over"].to_numpy())})
    # betting the out-of-sample blend at 5%+ EV, weeks 11-18
    bets = []
    for stat, te in list(second.groupby("stat")) + [("all", second)]:
        tr = first if stat == "all" else first[first["stat"] == stat]
        w = edge.fit_blend_weight(tr["p_ml"], tr["p_mkt_c"], tr["over"]) if len(tr) else 0.0
        p = edge.blend_prob(te["p_ml"], te["p_mkt_c"], w)
        for side, col, win, pw in (("over", "fd_over", te["over"] == 1, p), ("under", "fd_under", te["over"] == 0, 1 - p)):
            ev = np.array([om.expected_value(a, b) for a, b in zip(pw, te[col])])
            take = ev >= 0.05
            dec = te[col].map(om.american_to_decimal).to_numpy()
            prof = np.where(win, dec - 1, -1.0)[take]
            bets.append({"stat": stat, "side": side, "bets": int(take.sum()), "units": round(float(prof.sum()), 1),
                         "roi": round(float(prof.mean()), 3) if take.any() else None})
    return {"logloss": pd.DataFrame(rows).round(4), "bets": pd.DataFrame(bets)}


def run(first_season: int = 2016) -> dict:
    from betlab import backtest_props

    m = market_rows()
    hist = backtest_props.load(first_season - 1, 2025)
    feats = ML.features(hist.df)
    fitted = ML.fit(feats[feats["season"] < 2025])
    m = m.assign(p_ml=ml_prices(m, feats, fitted))
    return report(m) | {"rows": m}
