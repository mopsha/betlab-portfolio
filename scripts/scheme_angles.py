"""Scheme angles vs the prop market (Nov 6, 2026; DECISIONS 2026-11-06). Do scheme tendencies (blitz, two-high shells, box count, heavy personnel) add anything to the prop market?

Mike, Nov 6: test the Conch-style angles. Five hypotheses fixed before looking (sign in brackets):
  H1 opp blitz rate      -> RB receptions        [-]  (fewer blitzes: backs run routes, check-downs)
  H2 opp two-high rate   -> RB receptions        [+]  (two-high shells open the underneath)
  H3 opp two-high rate   -> WR receiving yards   [-]  (shells take away the deep shot)
  H4 opp box count       -> RB rushing yards     [-]  (more men in the box)
  H5 team 2+ TE rate     -> TE receptions        [+]  (heavier sets put tight ends on the field)
Bar: the hypothesis's sign and |t| >= 2 in BOTH 2024 and 2025, beyond the market's no-vig chance at FanDuel's line.
Features are walk-forward: the season's games before that week, shrunk toward last season (150 plays' weight).
Data, all free: the saved FanDuel lines (betlab backfill props), nflverse play-by-play, FTN charting (blitzers, box)
and participation (coverage type, personnel; published after each season, so 2026 can join about Feb 2027).

    .venv/bin/python scripts/scheme_angles.py      # about 40 minutes the first time (one simulation per game)

Result, Nov 6: no angle passed. H3 had the right sign in both seasons (t -1.1, -2.5), H4 too but weaker (-1.8, -1.0);
H5 flipped (+1.5, -2.5). Ten tests, so one |t| of 2.5 is within chance.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import nflreadpy as nfl

from betlab import backfill_props, backtest_props as B

OUT = Path(__file__).resolve().parents[1] / "data" / "cache" / "scheme_angles"      # gitignored
OUT.mkdir(parents=True, exist_ok=True)
K = 150.0
TWO_HIGH = {"COVER_2", "2_MAN", "COVER_4", "COVER_6"}
SINGLE = {"COVER_0", "COVER_1", "COVER_3"}


def lines(season):
    f = OUT / f"m_{season}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    m = B.market_eval(pd.read_parquet(backfill_props.path(season)))
    m.to_parquet(f)
    return m


def plays(seasons):
    f = OUT / "plays.parquet"
    if f.exists():
        return pd.read_parquet(f)
    cols = ["game_id", "play_id", "season", "week", "season_type", "posteam", "defteam", "qb_dropback", "rush", "pass"]
    pbp = nfl.load_pbp(seasons=seasons).to_pandas()[cols]
    pbp = pbp[(pbp["season_type"] == "REG") & pbp["posteam"].notna()]
    ftn = nfl.load_ftn_charting(seasons=seasons).to_pandas()[["nflverse_game_id", "nflverse_play_id", "n_blitzers", "n_defense_box"]]
    ftn = ftn.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})
    par = nfl.load_participation(seasons=seasons).to_pandas()[["nflverse_game_id", "play_id", "defense_coverage_type", "offense_personnel"]]
    par = par.rename(columns={"nflverse_game_id": "game_id"})
    d = pbp.merge(ftn, on=["game_id", "play_id"], how="left").merge(par, on=["game_id", "play_id"], how="left")
    d.to_parquet(f)
    return d


def te_count(s):
    if not isinstance(s, str):
        return np.nan
    for part in s.split(","):
        part = part.strip()
        if part.endswith(" TE"):
            return int(part.split()[0])
    return 0


def team_week(d):
    """Per (season, week, team): the raw sums each feature needs, as defense and as offense."""
    d = d.copy()
    db = d["qb_dropback"] == 1
    d["blitz"] = np.where(db & d["n_blitzers"].notna(), (d["n_blitzers"] > 0).astype(float), np.nan)
    cov = d["defense_coverage_type"].where(d["defense_coverage_type"].isin(TWO_HIGH | SINGLE))
    d["twohigh"] = np.where(db & cov.notna(), cov.isin(TWO_HIGH).astype(float), np.nan)
    d["box"] = np.where((d["rush"] == 1) & d["n_defense_box"].notna(), d["n_defense_box"], np.nan)
    tes = d["offense_personnel"].map(te_count)
    d["heavy"] = np.where(tes.notna(), (tes >= 2).astype(float), np.nan)
    agg = lambda g, c: pd.Series({f"{c}_s": g[c].sum(), f"{c}_n": g[c].notna().sum()})
    dfn = d.groupby(["season", "week", "defteam"]).apply(lambda g: pd.concat([agg(g, "blitz"), agg(g, "twohigh"), agg(g, "box")]))
    off = d.groupby(["season", "week", "posteam"]).apply(lambda g: agg(g, "heavy"))
    return dfn.reset_index().rename(columns={"defteam": "team"}), off.reset_index().rename(columns={"posteam": "team"})


def walk_forward(tw, feats):
    """Each team's rate entering each week: this season's earlier weeks plus last season's rate at K plays' weight."""
    rows = []
    for (season, team), g in tw.groupby(["season", "team"]):
        prev = tw[(tw["season"] == season - 1) & (tw["team"] == team)]
        for wk in range(1, 19):
            before = g[g["week"] < wk]
            r = {"season": season, "team": team, "week": wk}
            for c in feats:
                ps, pn = prev[f"{c}_s"].sum(), prev[f"{c}_n"].sum()
                prior = ps / pn if pn else (tw[f"{c}_s"].sum() / tw[f"{c}_n"].sum())
                r[c] = (before[f"{c}_s"].sum() + K * prior) / (before[f"{c}_n"].sum() + K)
            rows.append(r)
    return pd.DataFrame(rows)


def fit(r, feat, boot=300, seed=0):
    x = (r[feat] - r[feat].mean()) / r[feat].std()
    p = r["p_market"].clip(0.02, 0.98)
    off = np.log(p / (1 - p)).to_numpy()
    X = np.column_stack([np.ones(len(r)), x])
    b = B._logit_offset(r["over"].to_numpy(), X, off)
    idx = r.assign(_x=x, _off=off).set_index("game_id")
    ids, rng, bs = idx.index.unique(), np.random.default_rng(seed), []
    for _ in range(boot):
        s = idx.loc[rng.choice(ids, len(ids))]
        bs.append(B._logit_offset(s["over"].to_numpy(), np.column_stack([np.ones(len(s)), s["_x"]]), s["_off"].to_numpy())[1])
    se = float(np.std(bs))
    return b[1], se


def main():
    seasons = [2023, 2024, 2025]
    d = plays(seasons)
    dfn, off = team_week(d)
    D = walk_forward(dfn, ["blitz", "twohigh", "box"])
    O = walk_forward(off, ["heavy"])
    pos = nfl.load_player_stats(seasons=[2024, 2025]).to_pandas()[["player_id", "position"]].drop_duplicates("player_id")
    tests = [("H1", "blitz", "D", "RB", "receptions", -1), ("H2", "twohigh", "D", "RB", "receptions", +1),
             ("H3", "twohigh", "D", "WR", "receiving_yards", -1), ("H4", "box", "D", "RB", "rushing_yards", -1),
             ("H5", "heavy", "O", "TE", "receptions", +1)]
    out = []
    for season in (2024, 2025):
        m = lines(season).merge(pos, on="player_id", how="left")
        parts = m["game_id"].str.split("_", expand=True)
        m["opp"] = np.where(m["team"] == parts[3], parts[2], parts[3])
        m["season"] = season
        m = m.merge(D.rename(columns={"team": "opp"}), on=["season", "week", "opp"], how="left")
        m = m.merge(O, on=["season", "week", "team"], how="left")
        for h, feat, side, p, stat, sign in tests:
            r = m[(m["position"] == p) & (m["stat"] == stat) & m[feat].notna()]
            b, se = fit(r, feat)
            out.append({"test": h, "season": season, "feature": feat, "lines": len(r), "games": r["game_id"].nunique(),
                        "coef_per_sd": round(b, 4), "se": round(se, 4), "t": round(b / se, 2), "expected_sign": sign,
                        "overs_hit": round(r["over"].mean(), 3), "market": round(r["p_market"].mean(), 3)})
        print(f"{season}: {len(m)} lines, features found for {m['blitz'].notna().mean():.0%} (blitz), "
              f"{m['twohigh'].notna().mean():.0%} (two-high)", flush=True)
    res = pd.DataFrame(out)
    pd.set_option("display.width", 200)
    print(res.to_string(index=False))
    res.to_csv(OUT / "results.csv", index=False)
    # coverage of the features themselves: does the spread across teams look real?
    print(D[D["week"] == 10].groupby("season")[["blitz", "twohigh", "box"]].describe().round(3).T.to_string())


if __name__ == "__main__":
    main()
