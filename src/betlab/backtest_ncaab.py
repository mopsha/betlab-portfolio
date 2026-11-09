"""Walk-forward college basketball backtest against the market (`betlab backtest ncaab`).

Ratings (models/ncaab.py) are refit every week from earlier games only; every game with a
line gets the model's margin (plus the roster-change shift, when rosters are passed) and
total. Then:
- **vs the close:** margin and total error, model vs the closing line, and the best blend
  (closing line + w x (model - line)), with w fit on earlier seasons only.
- **vs the opener** (2024-25 and 2025-26, where openers exist): does the model's
  disagreement with the opening spread predict where the line closes (a move toward the
  model), and does the side the model favors cover the OPENING number more than half the
  time? That's the college football early-read finding's shape.
Settings are tuned on 2023-24 (`tune`); 2024-25 and 2025-26 are the test.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from betlab.models import ncaab as M
from betlab.sources import cbbd


def predict(games: pd.DataFrame, tg: pd.DataFrame, seasons, p: M.Params | None = None,
            roster: tuple | None = None) -> pd.DataFrame:
    """One row per game in `seasons`: the model's margin and total. roster: (players, rosters[, recruits]) adds the
    roster-change shift to the margin (`m_margin_base` keeps the rest); recruits count freshmen."""
    p = p or M.Params()
    g = games[games["season"].isin(list(seasons))].copy()
    g["wk"] = g["date"].dt.to_period("W-MON").dt.start_time
    dval = {s: M.roster_dval(roster[0], roster[1], s, roster[2] if len(roster) > 2 else None)
            for s in g["season"].unique()} if roster else {}
    rows = []
    for wk, x in g.groupby("wk"):
        r = M.fit(tg, wk, p)
        for a in x.itertuples():
            pr = r.project(a.home_team, a.away_team, bool(a.neutral))
            shift = M.roster_shift(dval.get(a.season, {}), a.home_team, a.away_team, M.season_day(a.date, a.season))
            rows.append({"game_id": a.game_id, "m_margin": pr["margin"] + shift, "m_margin_base": pr["margin"],
                         "roster_shift": shift, "m_total": pr["total"]})
    return g.merge(pd.DataFrame(rows), on="game_id")


def tune(games, tg, season=2024, grid=None) -> pd.DataFrame:
    """Margin and total error on one season for each settings combination."""
    grid = grid or [dict(ridge_eff=r, ridge_pace=r, half_life_days=h, carry=c)
                    for r in (1.0, 3.0, 8.0) for h in (45.0, 90.0, 180.0) for c in (0.35, 0.7)]
    out = []
    for kw in grid:
        pr = predict(games, tg, [season], M.Params(**kw))
        x = pr.dropna(subset=["spread_line", "total_line"])
        out.append(kw | {"margin_mae": (x["m_margin"] - x["margin"]).abs().mean(),
                         "total_mae": (x["m_total"] - x["total"]).abs().mean(),
                         "market_margin_mae": (x["spread_line"] - x["margin"]).abs().mean(),
                         "market_total_mae": (x["total_line"] - x["total"]).abs().mean(), "n": len(x)})
    return pd.DataFrame(out).sort_values("margin_mae")


def vs_close(pred: pd.DataFrame) -> pd.DataFrame:
    """Per season: model and market error; the blend weight fit on earlier seasons and its error."""
    rows = []
    seasons = sorted(pred["season"].unique())
    for what, line, model, y in (("margin", "spread_line", "m_margin", "margin"), ("total", "total_line", "m_total", "total")):
        d = pred.dropna(subset=[line])
        for i, s in enumerate(seasons):
            x, prev = d[d["season"] == s], d[d["season"].isin(seasons[:i])]
            w = 0.0
            if len(prev) > 500:
                dev, res = (prev[model] - prev[line]).to_numpy(), (prev[y] - prev[line]).to_numpy()
                w = float(np.clip((dev * res).sum() / (dev * dev).sum(), 0, 1))
            blend = x[line] + w * (x[model] - x[line])
            rows.append({"target": what, "season": int(s), "games": len(x), "model_mae": (x[model] - x[y]).abs().mean(),
                         "market_mae": (x[line] - x[y]).abs().mean(), "w": round(w, 3),
                         "blend_mae": (blend - x[y]).abs().mean()})
    return pd.DataFrame(rows).round(3)


def vs_open(pred: pd.DataFrame, cut: float = 3.0, boot: int = 500, seed: int = 0) -> dict:
    """Where the opener exists: does model - open predict close - open, and does the model's
    side cover the opening spread (and total) when it disagrees by `cut` points or more?"""
    rng = np.random.default_rng(seed)
    out = {}
    for what, open_, close, model, y in (("spread", "spread_open", "spread_line", "m_margin", "margin"),
                                         ("total", "total_open", "total_line", "m_total", "total")):
        d = pred.dropna(subset=[open_, close])
        edge, move = d[model] - d[open_], d[close] - d[open_]
        slope = float(np.polyfit(edge, move, 1)[0])
        strong = d[edge.abs() >= cut]
        e = (strong[model] - strong[open_]).to_numpy()
        res = (strong[y] - strong[open_]).to_numpy()
        win = np.sign(e) == np.sign(res)
        push = res == 0
        rate = win[~push].mean() if (~push).any() else np.nan
        bs = [win[~push][rng.integers(0, (~push).sum(), (~push).sum())].mean() for _ in range(boot)]
        toward = float((np.sign(strong[close] - strong[open_]) == np.sign(e)).mean())
        out[what] = {"games_with_open": len(d), "move_slope": round(slope, 3), "strong": len(strong),
                     "cover_rate_vs_open": round(float(rate), 4), "se": round(float(np.std(bs)), 4),
                     "line_moved_toward_model": round(toward, 3),
                     "by_season": {int(s): round(float((np.sign(x[model] - x[open_]) == np.sign(x[y] - x[open_]))[
                         (x[y] != x[open_])].mean()), 4) for s, x in strong.groupby("season")}}
    return out


def run(test=(2025, 2026), p: M.Params | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    t0 = time.time()
    g, tg = cbbd.games(), cbbd.team_games()
    pred = predict(g, tg, list(test), p)
    print(f"  {len(pred)} games predicted, {time.time() - t0:.0f}s", flush=True)
    return pred, vs_close(pred)


def line_moves(pred: pd.DataFrame, cuts=(2, 3, 5, 7), boot: int = 1000, seed: int = 0) -> pd.DataFrame:
    """Where openers exist: how far the line moved toward the model's side (close - open,
    signed by the model's disagreement with the opener), by disagreement size, with a
    bootstrap SE and the implied CLV (a point near the center is worth pdf(0)/SD)."""
    from scipy.stats import norm

    rng = np.random.default_rng(seed)
    rows = []
    for what, op, cl, mod, sd in (("spread", "spread_open", "spread_line", "m_margin", 11.0),
                                  ("total", "total_open", "total_line", "m_total", 16.5)):
        x = pred.dropna(subset=[op, cl]).copy()
        x["edge"] = x[mod] - x[op]
        x["move"] = np.sign(x["edge"]) * (x[cl] - x[op])
        for cut in cuts:
            s = x[x["edge"].abs() >= cut]
            m = s["move"].to_numpy()
            if len(m) < 30:
                continue
            bs = [m[rng.integers(0, len(m), len(m))].mean() for _ in range(boot)]
            rows.append({"market": what, "disagreement": f"{cut}+ pts", "games": len(m),
                         "move_toward_model": round(float(m.mean()), 3), "se": round(float(np.std(bs)), 3),
                         "implied_clv": round(float(norm.cdf(m.mean() / sd) - 0.5), 4),
                         **{f"move_{int(k)}": round(float(v["move"].mean()), 3) for k, v in s.groupby("season")}})
    return pd.DataFrame(rows)

