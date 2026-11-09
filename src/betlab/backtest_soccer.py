"""Walk-forward soccer backtest against the sharp market (`betlab backtest soccer`).

For every league and test season, ratings are refit each week from earlier matches only
(models/soccer.py), and every match gets the model's home/draw/away and over-2.5 chances.
They're compared with:
- **the close**: Pinnacle's no-vig closing price (Betfair Exchange or the books' average
  where Pinnacle is missing). Can the model add anything to the sharpest number?
- **earlier in the week**: Pinnacle's odds when football-data.co.uk collected them (a day
  or more before kickoff). Does the model know where the line is going? That's closing
  line value, the college finding's shape.

Scores: log loss (lower is better) for the model, the market and the best blend
p ∝ market^(1-w) · model^w. The blend weight w is fit on earlier seasons only
(walk-forward), and there's a game-bootstrap SE on the gain.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from betlab.models import soccer as M
from betlab.sources import soccer as S


ODDS_COLUMNS = [f"{p}_{s}" for p in ("pin_open", "pin_close", "bfx_close", "avg_close") for s in "hda"] +     ["pin_open_o25", "pin_open_u25", "pin_close_o25", "pin_close_u25"]


def predict(matches: pd.DataFrame, test_seasons, p: M.Params | None = None) -> pd.DataFrame:
    """One row per test match: model probabilities, the market's (close and earlier), result."""
    p = p or M.Params()
    matches = matches.reindex(columns=list(dict.fromkeys(list(matches.columns) + ODDS_COLUMNS)))
    test = matches[matches["season"].isin(list(test_seasons))].copy()
    test["wk"] = test["date"].dt.to_period("W-MON").dt.start_time
    rows = []
    for wk, g in test.groupby("wk"):
        r = M.fit(matches, wk, p)
        for x in g.itertuples():
            pr = M.probs(r, x.home, x.away)
            rows.append({"idx": x.Index, "m_h": pr["h"], "m_d": pr["d"], "m_a": pr["a"], "m_o25": pr["o25"],
                         "xg_h": pr["xg_h"], "xg_a": pr["xg_a"]})
    out = test.join(pd.DataFrame(rows).set_index("idx"))
    close = S.closing_1x2(out)
    out[["c_h", "c_d", "c_a"]] = close
    op = out[["pin_open_h", "pin_open_d", "pin_open_a"]].to_numpy(float)
    ok = np.isfinite(op).all(axis=1) & (op > 1).all(axis=1)
    o = np.full_like(op, np.nan)
    o[ok] = S.no_vig(op[ok])
    out[["o_h", "o_d", "o_a"]] = o
    for pre, cols in (("c", ("pin_close_o25", "pin_close_u25")), ("o", ("pin_open_o25", "pin_open_u25"))):
        ou = out[list(cols)].to_numpy(float)
        ok = np.isfinite(ou).all(axis=1) & (ou > 1).all(axis=1)
        v = np.full(len(out), np.nan)
        v[ok] = S.no_vig(ou[ok])[:, 0]
        out[f"{pre}_o25"] = v
    out["res"] = np.select([out["hg"] > out["ag"], out["hg"] == out["ag"]], [0, 1], 2)
    out["over25"] = (out["hg"] + out["ag"] > 2.5).astype(float)
    return out


def _ll3(P: np.ndarray, res: np.ndarray) -> np.ndarray:
    return -np.log(np.clip(P[np.arange(len(res)), res], 1e-9, 1))


def _blend(mkt: np.ndarray, mod: np.ndarray, w: float) -> np.ndarray:
    z = (1 - w) * np.log(np.clip(mkt, 1e-9, 1)) + w * np.log(np.clip(mod, 1e-9, 1))
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def best_w(mkt: np.ndarray, mod: np.ndarray, res: np.ndarray) -> float:
    grid = np.linspace(0, 1, 21)
    return float(grid[np.argmin([_ll3(_blend(mkt, mod, w), res).mean() for w in grid])])


def evaluate(pred: pd.DataFrame, against: str = "c", boot: int = 200, seed: int = 0) -> pd.DataFrame:
    """Per league and test season: log loss of the market (`c` close / `o` earlier in the
    week), the model, and the blend with w fit on the league's EARLIER test seasons (the
    first season uses w = 0). Plus the 1X2 gain per match with a bootstrap SE."""
    rng = np.random.default_rng(seed)
    rows = []
    for lg, L in pred.groupby("league"):
        seasons = sorted(L["season"].unique())
        for i, s in enumerate(seasons):
            X = L[L["season"] == s]
            mk = X[[f"{against}_h", f"{against}_d", f"{against}_a"]].to_numpy(float)
            md = X[["m_h", "m_d", "m_a"]].to_numpy(float)
            ok = np.isfinite(mk).all(axis=1) & np.isfinite(md).all(axis=1)
            if ok.sum() < 50:
                continue
            prev = L[L["season"].isin(seasons[:i])]
            pmk = prev[[f"{against}_h", f"{against}_d", f"{against}_a"]].to_numpy(float)
            pmd = prev[["m_h", "m_d", "m_a"]].to_numpy(float)
            pok = np.isfinite(pmk).all(axis=1)
            w = best_w(pmk[pok], pmd[pok], prev["res"].to_numpy()[pok]) if pok.sum() >= 200 else 0.0
            res = X["res"].to_numpy()[ok]
            l_mk, l_md, l_bl = _ll3(mk[ok], res), _ll3(md[ok], res), _ll3(_blend(mk[ok], md[ok], w), res)
            gain = l_mk - l_bl
            bs = [gain[rng.integers(0, len(gain), len(gain))].mean() for _ in range(boot)]
            rows.append({"league": lg, "season": int(s), "matches": int(ok.sum()), "market": l_mk.mean(),
                         "model": l_md.mean(), "w (from earlier seasons)": w, "blend": l_bl.mean(),
                         "gain": gain.mean(), "gain_se": float(np.std(bs))})
    return pd.DataFrame(rows)


def run(leagues=("epl", "la_liga", "serie_a", "bundesliga", "ligue_1", "mls"), first: int = 2017,
        test=(2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026), p: M.Params | None = None) -> pd.DataFrame:
    frames, t0 = [], time.time()
    for lg in leagues:
        m = S.load(lg, range(first, max(test) + 1))
        if m.empty:
            continue
        frames.append(predict(m, test, p))
        print(f"  {lg}: {len(frames[-1])} matches, {time.time() - t0:.0f}s", flush=True)
    return pd.concat(frames, ignore_index=True)


def line_moves(pred: pd.DataFrame, boot: int = 200, seed: int = 0) -> pd.DataFrame:
    """Does the model know where the line is going? Per league: the slope of the home
    chance's move (close - earlier) on the model's disagreement with the earlier line
    (model - earlier), and for disagreements of 5+ points, how often the line moved toward
    the model. A real positive slope would mean early bets in the model's direction beat
    the close."""
    d = pred.dropna(subset=["o_h", "c_h", "m_h"]).copy()
    d["edge"], d["move"] = d["m_h"] - d["o_h"], d["c_h"] - d["o_h"]
    rng = np.random.default_rng(seed)
    rows = []
    for lg, x in list(d.groupby("league")) + [("all", d)]:
        slope = np.polyfit(x["edge"], x["move"], 1)[0]
        bs = [np.polyfit(*x.loc[rng.choice(x.index, len(x)), ["edge", "move"]].to_numpy().T, 1)[0] for _ in range(boot)]
        s = x[x["edge"].abs() >= 0.05]
        rows.append({"league": lg, "matches": len(x), "slope": slope, "se": float(np.std(bs)),
                     "strong_disagreements": len(s),
                     "moved_toward_model": float((np.sign(s["edge"]) == np.sign(s["move"])).mean()) if len(s) else np.nan})
    return pd.DataFrame(rows)
