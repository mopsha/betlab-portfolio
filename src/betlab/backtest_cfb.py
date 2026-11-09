"""College football: does the efficiency read beat the market, and when? (`betlab backtest cfb`)

Walk-forward by week (ratings from games before the week), FBS-vs-FBS games with lines,
week 3 on, 2016-2025. For each game: the early-read features (models/game_ncaaf.py),
the closing and opening lines (CFBD consensus), and what happened.

- **Against the close** (2016-25): does the read predict margin - closing spread, or
  points - closing total?
- **Against the open** (2021-25, when CFBD has openers): fit on earlier seasons, predict
  the next, and score the side of strong reads (1+ SD) against the opening number, plus
  how far the line moved toward that side by the close.

`fit_early` refits on every season with openers and saves data/models/ncaaf_early.json,
which the college previews read.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.models import game_ncaaf as GC
from betlab.sources import cfbd


def table(first: int = 2016, last: int = 2025, min_week: int = 3) -> pd.DataFrame:
    games = cfbd.games()
    tg = GC.team_games(cfbd.advanced(), games)
    g = games[(games["home_div"] == "fbs") & (games["away_div"] == "fbs") & games["spread_line"].notna()
              & games["margin"].notna() & games["season"].between(first, last) & (games["week"] >= min_week)]
    rows = []
    for (season, week), gw in g.groupby(["season", "week"]):
        r = GC.fit_ratings(tg, gw["date"].min())
        for x in gw.itertuples():
            f = GC.early_features(r, x.home_team, x.away_team)
            rows.append({"game_id": x.game_id, "season": season, "week": week, **f,
                         "spread": x.spread_line, "total": x.total_line, "open": x.spread_open, "topen": x.total_open,
                         "ats": x.margin - x.spread_line, "tot": x.home_pts + x.away_pts - x.total_line,
                         "ats_open": x.margin - x.spread_open, "tot_open": x.home_pts + x.away_pts - x.total_open,
                         "move": x.spread_line - x.spread_open, "tmove": x.total_line - x.total_open})
    return pd.DataFrame(rows)


def _ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    X = np.column_stack([np.ones(len(y)), X])
    return np.linalg.lstsq(X, y, rcond=None)[0]


def _luck_coef(d: pd.DataFrame) -> float:
    return float(np.polyfit(d["net_epa"], d["net_points"], 1)[0])


def _design(d: pd.DataFrame, kind: str, luck_coef: float) -> tuple[np.ndarray, str, str]:
    if kind == "spread":
        d = d.assign(luck=d["net_points"] - luck_coef * d["net_epa"])
        return d[GC.SIDE_FEATURES + ["open"]].to_numpy(), "ats_open", "move"
    return d[GC.TOTAL_FEATURES + ["topen"]].to_numpy(), "tot_open", "tmove"


def evaluate(t: pd.DataFrame, thresholds=(1.0, 1.5)) -> pd.DataFrame:
    """Rolling out-of-sample record of strong reads against the opening line, by kind."""
    d = t.dropna(subset=["open", "topen"])
    out = []
    for kind in ("spread", "total"):
        preds = []
        for s in sorted(d["season"].unique())[1:]:
            tr, te = d[d["season"] < s], d[d["season"] == s]
            lc = _luck_coef(tr)
            Xtr, ycol, mcol = _design(tr, kind, lc)
            b = _ols(tr[ycol].to_numpy(), Xtr)
            Xte, _, _ = _design(te, kind, lc)
            p = np.column_stack([np.ones(len(te)), Xte]) @ b
            preds.append(pd.DataFrame({"season": s, "y": te[ycol].to_numpy(), "p": p, "move": te[mcol].to_numpy(),
                                       "y_close": te["ats" if kind == "spread" else "tot"].to_numpy()}))
        P = pd.concat(preds)
        for thr in thresholds:
            k = P["p"].abs() >= thr * P["p"].std()
            s = P[k]
            hit = lambda y: float((np.sign(y) == np.sign(s["p"]))[y != 0].mean())
            out.append({"kind": kind, "strength": f">= {thr} SD", "n": int(k.sum()), "hit vs open": hit(s["y"]),
                        "hit vs close": hit(s["y_close"]), "line moved our way (pts)": float((np.sign(s["p"]) * s["move"]).mean()),
                        **{f"hit {int(y)}": float((np.sign(g["y"]) == np.sign(g["p"]))[g["y"] != 0].mean())
                           for y, g in s.groupby("season")}})
    return pd.DataFrame(out).round(3)


def fit_early(t: pd.DataFrame) -> dict:
    """Fit the early read on every season with openers and save it for the previews."""
    d = t.dropna(subset=["open", "topen"])
    lc = _luck_coef(d)
    fit = {"luck_coef": lc, "seasons": sorted(int(s) for s in d["season"].unique()), "n": int(len(d)),
           "fitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "note": "Early-week read (models/game_ncaaf.py). Tracked on the Games tab; not priced."}
    for kind in ("spread", "total"):
        X, ycol, _ = _design(d, kind, lc)
        b = _ols(d[ycol].to_numpy(), X)
        pred = np.column_stack([np.ones(len(d)), X]) @ b
        fit[kind] = {"coef": [float(v) for v in b], "pred_sd": float(pred.std()),
                     "features": (GC.SIDE_FEATURES + ["open"]) if kind == "spread" else (GC.TOTAL_FEATURES + ["topen"])}
    GC.EARLY_PATH.parent.mkdir(parents=True, exist_ok=True)
    GC.EARLY_PATH.write_text(json.dumps(fit, indent=2), encoding="utf-8")
    return fit
