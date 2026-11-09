"""Does the joint NHL model get pairs of legs right? (models/joint_nhl.py)

For every 2025-26 game (held out: the joint settings were fit on 2022-24), the game model's
walk-forward projection gives the score grid and projected shots; each team's four biggest
shooters (by prior shot share) get their expected shots; each starter's saves come out of the
simulation. For pairs of legs a parlay could hold:
- a shooter over 2.5 shots with his team winning, or with the game over 6.5;
- two teammates both over 2.5 shots;
- a starter over his saves line (his expected saves rounded, minus a half) with his team winning,
  or with the game over 6.5;
the observed joint count is compared with the joint model's expected count and with the
independent-legs product (each leg's model chance multiplied). `lift` = joint / independent; a
model lift near the observed lift means the model moves the legs together correctly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betlab.cards.preview_nhl import load_params
from betlab.models import joint_nhl as J
from betlab.models import nhl as M


def run(games: pd.DataFrame, feats: pd.DataFrame, gg: pd.DataFrame, season: int = 2026, n: int = 2000,
        jp: J.JointParams | None = None, mean_scale: float = 0.962) -> pd.DataFrame:
    """games: backtest_nhl.walk rows with sf/sa/gf/ga merged; feats: props_nhl.features rows."""
    p = load_params()
    g = games[games["season"] == season]
    f = feats[(feats["season"] == season) & (feats["games_prior"] >= 5) & feats["share_l"].notna()]
    starters = gg[gg["started"] == 1][["game_id", "team", "saves"]]
    rows = []
    for k, r in enumerate(g.itertuples()):
        grid = M.grid(r.home_xg * p.goal_scale, r.away_xg * p.goal_scale, p)
        final = grid["final"]
        players = []
        for side, team, proj in (("home", r.home, r.home_shots), ("away", r.away, r.away_shots)):
            fp = f[(f["game_id"] == r.game_id) & (f["team"] == team)].nlargest(4, "share_l")
            norm = fp["share_present"].clip(lower=0.5)
            # share-based means for the four biggest shooters run 4% high (2.61 vs 2.51 in 2025-26:
            # picked on a high prior share); the live model uses the props ML means instead
            for q in fp.assign(mean=fp["share_l"] / norm * proj * mean_scale).itertuples():
                players.append({"key": q.player_id, "side": side, "mean": q.mean, "actual": q.shots, "team": team})
        sim = J.simulate(final, (r.home_shots, r.away_shots), (r.home_xg * p.goal_scale, r.away_xg * p.goal_scale),
                         players, jp, n=n, seed=k)
        home_win = sim["home_goals"] > sim["away_goals"]
        over = sim["home_goals"] + sim["away_goals"] > 6.5
        act_home_win, act_over = float(r.gf > r.ga), float(r.gf + r.ga > 6.5)
        for pl in players:
            y = sim["players"][pl["key"]] >= 3
            win = home_win if pl["side"] == "home" else ~home_win
            act_win = act_home_win if pl["side"] == "home" else 1 - act_home_win
            a = float(pl["actual"] >= 3)
            rows.append({"pair": "shooter 3+ & team wins", "joint": float((y & win).mean()), "indep": y.mean() * win.mean(),
                         "obs": a * act_win})
            rows.append({"pair": "shooter 3+ & over 6.5", "joint": float((y & over).mean()), "indep": y.mean() * over.mean(),
                         "obs": a * act_over})
        for side in ("home", "away"):
            mates = [pl for pl in players if pl["side"] == side][:2]
            if len(mates) == 2:
                y1, y2 = (sim["players"][m["key"]] >= 3 for m in mates)
                rows.append({"pair": "two teammates 3+", "joint": float((y1 & y2).mean()), "indep": y1.mean() * y2.mean(),
                             "obs": float(mates[0]["actual"] >= 3) * float(mates[1]["actual"] >= 3)})
        for side, team in (("home", r.home), ("away", r.away)):
            sv = starters[(starters["game_id"] == r.game_id) & (starters["team"] == team)]
            if sv.empty:
                continue
            saves = sim[f"{side}_saves"]
            line = np.round(saves.mean()) - 0.5
            y = saves > line
            win = home_win if side == "home" else ~home_win
            act_win = act_home_win if side == "home" else 1 - act_home_win
            a = float(sv["saves"].iloc[0] > line)
            rows.append({"pair": "goalie over saves & his team wins", "joint": float((y & win).mean()),
                         "indep": y.mean() * win.mean(), "obs": a * act_win})
            rows.append({"pair": "goalie over saves & over 6.5", "joint": float((y & over).mean()),
                         "indep": y.mean() * over.mean(), "obs": a * act_over})
    df = pd.DataFrame(rows)
    out = df.groupby("pair").agg(n=("obs", "size"), observed=("obs", "sum"), joint_model=("joint", "sum"),
                                 independent=("indep", "sum"))
    out["obs_lift"] = out["observed"] / out["independent"]
    out["model_lift"] = out["joint_model"] / out["independent"]
    out["obs_se"] = np.sqrt(out["observed"]) / out["independent"]
    return out.round(3)
