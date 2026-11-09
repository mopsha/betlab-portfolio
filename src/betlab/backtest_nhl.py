"""NHL backtest: does the game model know anything DraftKings' lines don't?

Walk-forward: ratings are refit every `REFIT_DAYS` days from games before that date, and
every game is projected with the goalies who actually started (live pricing uses ESPN's
probable or confirmed starters instead, so live is slightly harder than this).

1. **Settings** (`tune`): the empty-net rates, the tie weight and the overtime lean are
   measured on the training seasons; the rating settings (recency, ridge, goalie
   shrinkage, the goals/shots blend, back-to-backs) are chosen by moneyline log loss on
   the training seasons only.
2. **Against the market** (`market_eval`), on the held-out seasons, where ESPN has lines:
   - log loss of the model, DraftKings' opening and closing no-vig prices, and blends;
   - totals: the model's P(over) at the closing line against the result;
   - **the line's move**: does the model's gap to the opening price predict where the
     line closes, and does taking the model's side at the open beat the close (CLV)?
     That's the college-basketball pattern (a read that loses to the close can still beat
     the opener).

`betlab backtest nhl` prints the report; `docs/MODELS.md` ("NHL") keeps the findings.
"""

from __future__ import annotations

import itertools
from dataclasses import replace

import numpy as np
import pandas as pd

from betlab import odds_math as om
from betlab.models import nhl as m
from betlab.sources import nhl as src

SEASONS = range(2019, 2027)          # 2019 = 2018-19 (history for the first test season)
TRAIN = (2022, 2023, 2024)
TEST = (2025, 2026)
REFIT_DAYS = 7


def prepare(seasons=SEASONS):
    tg = m.team_games(src.load_team_games(seasons))
    gg = src.load_goalie_games(seasons)
    return tg, gg


def starters(gg: pd.DataFrame) -> pd.DataFrame:
    """(game_id, team) -> the goalie who started."""
    s = gg[gg["started"] == 1].sort_values("toi", ascending=False).drop_duplicates(["game_id", "team"])
    return s[["game_id", "team", "goalie"]]


def games(tg: pd.DataFrame, gg: pd.DataFrame) -> pd.DataFrame:
    """One row per game: teams, starters, back-to-backs and the result."""
    st = starters(gg)
    h = tg[tg["home"] == 1].merge(st, on=["game_id", "team"], how="left").rename(columns={"goalie": "home_goalie"})
    a = tg[tg["home"] == 0][["game_id", "team", "b2b"]].rename(columns={"team": "opp", "b2b": "away_b2b"})
    h = h.merge(a, on=["game_id", "opp"], how="left")
    h = h.merge(st.rename(columns={"team": "opp", "goalie": "away_goalie"}), on=["game_id", "opp"], how="left")
    return pd.DataFrame({
        "game_id": h["game_id"], "season": h["season"], "date": h["date"], "home": h["team"], "away": h["opp"],
        "home_goalie": h["home_goalie"], "away_goalie": h["away_goalie"],
        "home_b2b": h["b2b"].fillna(0).astype(bool), "away_b2b": h["away_b2b"].fillna(0).astype(bool),
        "home_win": h["win"].astype(int), "total": (h["gf"] + h["ga"]).astype(float),
        "margin": (h["gf"] - h["ga"]).astype(float), "extra": h["extra"].astype(int),
        "reg_margin": (h["goals"] - h["goals_against"]).astype(float),
    }).sort_values(["date", "game_id"]).reset_index(drop=True)


def walk(tg, gg, gm: pd.DataFrame, p: m.Params, seasons) -> pd.DataFrame:
    """Project every game in `seasons` with ratings refit every REFIT_DAYS days."""
    rows = []
    for season in seasons:
        sg = gm[gm["season"] == season]
        if sg.empty:
            continue
        start = sg["date"].min()
        for t0 in pd.date_range(start, sg["date"].max() + pd.Timedelta(days=1), freq=f"{REFIT_DAYS}D"):
            week = sg[(sg["date"] >= t0) & (sg["date"] < t0 + pd.Timedelta(days=REFIT_DAYS))]
            if week.empty:
                continue
            r = m.fit(tg, gg, t0, p)
            for g in week.itertuples():
                pr = m.project(r, g.home, g.away, g.home_goalie, g.away_goalie, g.home_b2b, g.away_b2b)
                rows.append({"game_id": g.game_id, "p_home": pr["p_home"], "exp_total": pr["exp_total"],
                             "home_xg": pr["home_xg"], "away_xg": pr["away_xg"], "p_tie_reg": pr["p_tie_reg"],
                             "home_shots": pr["home_shots"], "away_shots": pr["away_shots"],
                             "home_goalie_sv": pr["home_goalie_sv"], "away_goalie_sv": pr["away_goalie_sv"],
                             "totals": pr["totals"], "margins": pr["margins"]})
    return gm.merge(pd.DataFrame(rows), on="game_id")


def log_loss(p, y) -> float:
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibrate(gm: pd.DataFrame, seasons=TRAIN) -> dict:
    """Empty-net rates, the tie rate and overtime home share from the training seasons."""
    g = gm[gm["season"].isin(seasons)]
    rm = g["reg_margin"]
    en_lead = (g["margin"] - rm).abs()          # empty-net goals the leader added (final minus non-EN margin)
    return {"en_rate_1": float(en_lead[(rm.abs() == 1) & (g["extra"] == 0)].mean()),
            "en_rate_2": float(en_lead[(rm.abs() == 2) & (g["extra"] == 0)].mean()),
            "tie_rate": float(g["extra"].mean()),
            "ot_home": float(g.loc[g["extra"] == 1, "home_win"].mean())}


def tune(tg, gg, gm, base: m.Params | None = None, grid: dict | None = None, seasons=TRAIN):
    """Moneyline log loss on the training seasons for each setting in the grid; the best first."""
    base = base or m.Params()
    grid = grid or {"w_goals": [0.0, 0.25, 0.5, 0.75], "half_life_days": [45.0, 90.0, 150.0],
                    "goalie_k": [800.0, 1500.0, 3000.0]}
    keys = list(grid)
    out = []
    for vals in itertools.product(*(grid[k] for k in keys)):
        p = replace(base, **dict(zip(keys, vals)))
        w = walk(tg, gg, gm, p, seasons)
        out.append({**dict(zip(keys, vals)), "log_loss": log_loss(w["p_home"], w["home_win"]), "n": len(w)})
    return pd.DataFrame(out).sort_values("log_loss").reset_index(drop=True)


def fit_tie_boost(tg, gg, gm, p: m.Params, target: float, seasons=TRAIN) -> float:
    """The tie weight that makes the grid's 60-minute tie rate match the training seasons'."""
    w = walk(tg, gg, gm, p, seasons)
    ratio = target / w["p_tie_reg"].mean()
    # The boost scales tie cells before renormalizing, so a little over the ratio is needed.
    return float(p.tie_boost * ratio / (1 - w["p_tie_reg"].mean() * (ratio - 1)))


def _novig(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    out = np.full(len(a), np.nan)
    for i in np.where(ok)[0]:
        out[i] = om.no_vig_two_way(a[i], b[i])[0]
    return out


def market_eval(w: pd.DataFrame, lines: pd.DataFrame) -> dict:
    """The model against DraftKings (or whatever book ESPN carried) on games with lines."""
    df = w.merge(lines.drop(columns=["season", "home", "away", "date"], errors="ignore"), on="game_id", how="inner")
    # ESPN's older lines (Unibet, 2022-24) aren't real two-way prices: the sides imply ~82%
    # together. Keep only moneylines with a normal margin.
    over = df["ml_home_close"].map(lambda x: om.implied_prob(x) if pd.notna(x) else np.nan) \
        + df["ml_away_close"].map(lambda x: om.implied_prob(x) if pd.notna(x) else np.nan)
    bad = ~over.between(1.0, 1.12)
    df.loc[bad, ["ml_home_close", "ml_away_close", "ml_home_open", "ml_away_open"]] = np.nan
    t_over = df["over_close"].map(lambda x: om.implied_prob(x) if pd.notna(x) else np.nan) \
        + df["under_close"].map(lambda x: om.implied_prob(x) if pd.notna(x) else np.nan)
    df.loc[~t_over.between(1.0, 1.12), ["over_close", "under_close"]] = np.nan
    df["p_close"] = _novig(df["ml_home_close"].to_numpy(float), df["ml_away_close"].to_numpy(float))
    df["p_open"] = _novig(df["ml_home_open"].to_numpy(float), df["ml_away_open"].to_numpy(float))
    res = {"games_with_close": int(df["p_close"].notna().sum()), "games_with_open": int(df["p_open"].notna().sum())}
    c = df[df["p_close"].notna()]
    if len(c):
        res["ml_close"] = {"n": len(c), "model": log_loss(c["p_home"], c["home_win"]),
                           "market_close": log_loss(c["p_close"], c["home_win"])}
        best = min(((wt, log_loss((1 - wt) * c["p_close"] + wt * c["p_home"], c["home_win"])) for wt in np.arange(0, 0.55, 0.05)),
                   key=lambda x: x[1])
        res["ml_close"]["best_blend_weight"], res["ml_close"]["best_blend"] = round(float(best[0]), 2), best[1]
    o = df[df["p_open"].notna() & df["p_close"].notna()]
    if len(o):
        gap = o["p_home"] - o["p_open"]
        move = o["p_close"] - o["p_open"]
        res["open"] = {"n": len(o), "market_open": log_loss(o["p_open"], o["home_win"]),
                       "market_close": log_loss(o["p_close"], o["home_win"]),
                       "model": log_loss(o["p_home"], o["home_win"]),
                       "corr_gap_move": float(np.corrcoef(gap, move)[0, 1]),
                       "move_per_gap": float(np.polyfit(gap, move, 1)[0])}
        rows = []
        for t in (0.02, 0.03, 0.04, 0.05, 0.07):
            sel = o[gap.abs() >= t]
            if not len(sel):
                continue
            home_side = (sel["p_home"] > sel["p_open"]).to_numpy()
            price = np.where(home_side, sel["ml_home_open"], sel["ml_away_open"])
            p_close = np.where(home_side, sel["p_close"], 1 - sel["p_close"])
            won = np.where(home_side, sel["home_win"], 1 - sel["home_win"])
            clv = np.array([om.clv(pr, pc) for pr, pc in zip(price, p_close)])
            profit = np.where(won == 1, [om.american_to_decimal(x) - 1 for x in price], -1.0)
            moved = np.where(home_side, sel["p_close"] - sel["p_open"], sel["p_open"] - sel["p_close"])
            rows.append({"gap": t, "n": len(sel), "won": float(won.mean()), "units": float(profit.sum()),
                         "roi": float(profit.mean()), "clv": float(clv.mean()), "beat_close": float((clv > 0).mean()),
                         "moved_our_way": float((moved > 0).mean())})
        res["open_reads"] = rows
    t = df[df["total_close"].notna() & df["over_close"].notna() & df["under_close"].notna()].copy()
    if len(t):
        po = np.array([m.p_over({"totals": d}, ln) for d, ln in zip(t["totals"], t["total_close"])])
        p_over, p_push = po[:, 0], po[:, 1]
        mkt = _novig(t["over_close"].to_numpy(float), t["under_close"].to_numpy(float))
        dec = t["total"] != t["total_close"]
        y = (t["total"] > t["total_close"]).astype(float)
        cond = p_over / np.clip(1 - p_push, 1e-6, None)
        res["totals_close"] = {"n": int(dec.sum()), "model": log_loss(cond[dec], y[dec]),
                               "market_close": log_loss(mkt[dec], y[dec]),
                               "over_rate": float(y[dec].mean()), "market_over": float(np.nanmean(mkt[dec])),
                               "model_over": float(cond[dec].mean())}
    return res


def report(p: m.Params | None = None, do_tune: bool = True) -> dict:
    """The full backtest: calibrate, tune on 2022-24, evaluate on 2025-26 against the lines."""
    tg, gg = prepare()
    gm = games(tg, gg)
    cal = calibrate(gm)
    p = replace(p or m.Params(), en_rate_1=cal["en_rate_1"], en_rate_2=cal["en_rate_2"])
    tuned = None
    if do_tune:
        tuned = tune(tg, gg, gm, p)
        best = tuned.iloc[0]
        p = replace(p, **{k: float(best[k]) for k in ("w_goals", "half_life_days", "goalie_k")})
    p = replace(p, tie_boost=fit_tie_boost(tg, gg, gm, p, cal["tie_rate"]))
    w = walk(tg, gg, gm, p, TEST)
    lines = src.load_lines()
    out = {"params": p, "calibration": cal, "tuning": tuned,
           "test": {"n": len(w), "model": log_loss(w["p_home"], w["home_win"]),
                    "home_rate": log_loss(np.full(len(w), w["home_win"].mean()), w["home_win"]),
                    "tie_rate_model": float(w["p_tie_reg"].mean()), "tie_rate_real": float(w["extra"].mean()),
                    "total_model": float(w["exp_total"].mean()), "total_real": float(w["total"].mean())},
           "market": market_eval(w, lines) if len(lines) else {}, "walk": w}
    return out


def save_params(p: m.Params, note: dict | None = None) -> None:
    """Write the tuned settings where the live view reads them (data/models/nhl.json)."""
    import json
    from dataclasses import asdict

    from betlab.cards.preview_nhl import PARAMS

    PARAMS.parent.mkdir(parents=True, exist_ok=True)
    PARAMS.write_text(json.dumps({"params": asdict(p), "note": note or {}}, indent=2, default=str), encoding="utf-8")
