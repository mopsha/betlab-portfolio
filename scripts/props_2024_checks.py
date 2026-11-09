"""Do 2025's three NFL prop findings hold on 2024 lines? (to-do c-props-2024; Mike, Oct 19)

Free once the lines are saved: reads data/odds_history/americanfootball_nfl/props_<season>.parquet (betlab backfill
props), nflverse play-by-play and stats. Runs each season the same way, side by side:

1. **Over lean**: how often overs hit on FanDuel's main lines against the plain market's no-vig chance (Pinnacle,
   else the other books, moved to FanDuel's line), by stat, and what the over-lean correction (props_market.over_shift)
   said. The correction is off in picks since Sep 30 (DECISIONS); it can come back only if a second season shows it.
2. **Script lean**: backtest_props.script_eval (logit P(over) = corrected market + matchup edge + volume).
3. **Receiving-yards matchups** (models/matchups_nfl.py: yards per target allowed to the position group, deep-ball
   fit), fit jointly with the script lean on the corrected market, per SD of each feature, game-bootstrap SEs, and
   the combined read's strong side (settings preview.matchup_read) against the market.

    python scripts/props_2024_checks.py [--seasons 2024 2025] [--boot 300]

About 15-30 minutes a season (one game simulation per game, as the props backtest).
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from betlab import backfill_props, config
from betlab import backtest_props as B
from betlab import props_market as PM
from betlab.models import matchups_nfl as MN
from betlab.sources import nflverse


def over_lean(m: pd.DataFrame) -> pd.DataFrame:
    out = []
    for stat, g in list(m.groupby("stat")) + [("all", m)]:
        hit, plain = g["over"].mean(), g["p_market"].mean()
        shifted = np.mean([PM.over_shift(p, s) for p, s in zip(g["p_market"], g["stat"])])
        out.append({"stat": stat, "lines": len(g), "overs_hit": hit, "plain_market": plain, "corrected": shifted,
                    "hit_minus_plain": hit - plain, "se": float(np.sqrt(plain * (1 - plain) / len(g)))})
    return pd.DataFrame(out).round(4)


def matchup_lines(d: pd.DataFrame, season: int) -> pd.DataFrame:
    """script_eval's receiving-yards lines with each receiver's ypt and deep features, walk-forward."""
    games = nflverse.load_games()
    pbp = nflverse.load_pbp(range(season - 1, season + 1))
    stats = nflverse.load_player_stats(range(season - 1, season + 1))
    positions = stats.drop_duplicates("player_id").set_index("player_id")["position"]
    t = MN.targets(pbp, games, positions)
    g = games.set_index("game_id")
    r = d[d["stat"] == "receiving_yards"].copy()
    feats, cache = [], {}
    for x in r.itertuples():
        gm = g.loc[x.game_id]
        if gm["date"] not in cache:
            cache[gm["date"]] = MN.ratings(t, gm["date"])
        opp = gm["away_team"] if x.team == gm["home_team"] else gm["home_team"]
        f = MN.features(cache[gm["date"]], x.player_id, positions.get(x.player_id), opp)
        feats.append({"ypt": f.get("ypt", 0.0), "deep": f.get("deep", 0.0)})
    return pd.concat([r.reset_index(drop=True), pd.DataFrame(feats)], axis=1)


def matchup_fit(r: pd.DataFrame, boot: int, seed: int = 0) -> dict:
    cfg = config.settings()["preview"]["matchup_read"]
    sd = {k: float(r[k].std()) for k in ("ypt", "deep")}
    p = r["p_mkt"].clip(0.02, 0.98)
    off = np.log(p / (1 - p)).to_numpy()
    X = lambda s: np.column_stack([np.ones(len(s)), s["matchup"], s["volume"], s["ypt"] / sd["ypt"], s["deep"] / sd["deep"]])
    b = B._logit_offset(r["over"].to_numpy(), X(r), off)
    idx = r.set_index("game_id")
    ids, rng, bs = idx.index.unique(), np.random.default_rng(seed), []
    for _ in range(boot):
        s = idx.loc[rng.choice(ids, len(ids))]
        ps = s["p_mkt"].clip(0.02, 0.98)
        bs.append(B._logit_offset(s["over"].to_numpy(), X(s), np.log(ps / (1 - ps)).to_numpy()))
    bs = np.array(bs)
    # the live read (2025's coefficients and SDs) and its strong side against the market
    reads = [MN.read(pm, {"ypt": a, "deep": c}, cfg) for pm, a, c in zip(r["p_mkt"], r["ypt"], r["deep"])]
    score = np.array([s for _, s in reads])
    k = np.abs(score) >= float(cfg["show_min"])
    over_side = score > 0
    hit = np.where(over_side, r["over"], 1 - r["over"])[k]
    mkt = np.where(over_side, r["p_mkt"], 1 - r["p_mkt"])[k]
    return {"lines": len(r), "sd": {k: round(v, 4) for k, v in sd.items()},
            "ypt": (round(b[3], 3), round(float(bs[:, 3].std()), 3)), "deep": (round(b[4], 3), round(float(bs[:, 4].std()), 3)),
            "strong_side": {"n": int(k.sum()), "hit": round(float(hit.mean()), 3) if k.any() else None,
                            "market": round(float(mkt.mean()), 3) if k.any() else None}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="+", default=[2025, 2024])
    ap.add_argument("--boot", type=int, default=300)
    a = ap.parse_args()
    pd.set_option("display.width", 200)
    for season in a.seasons:
        lines = pd.read_parquet(backfill_props.path(season))
        m = B.market_eval(lines)
        print(f"\n=========== {season}: {lines['game_id'].nunique()} games, {len(m)} FanDuel main lines with a result")
        print("\n1) over lean (overs hit vs the plain market; corrected = what over_shift said)")
        print(over_lean(m).to_string(index=False))
        rep = B.script_eval(m, boot=a.boot)
        print("\n2) script lean (log-odds per unit; pass game bootstrap below)")
        print(rep["fits"].to_string(index=False))
        print("   pass game bootstrap:", {k: round(v, 3) for k, v in rep["bootstrap"].items()})
        print(rep["halves"].to_string(index=False))
        print("   strong matchups (|edge| >= 1):", {k: (round(v, 3) if isinstance(v, float) else v)
                                                   for k, v in rep["strong_matchups"].items()})
        r = matchup_lines(rep["lines"], season)
        print("\n3) receiving-yards matchups, joint with the script lean (coef per SD, game-bootstrap SE):")
        print("  ", matchup_fit(r, a.boot))


if __name__ == "__main__":
    main()
