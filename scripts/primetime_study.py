"""Do primetime NFL games (kickoff 7 PM ET or later) play out differently from the market?

Run: .venv/Scripts/python scripts/primetime_study.py   (about a minute; needs network for nflverse)

1. Game totals and sides, regular season 2006-2025, against nflverse's closing lines:
   points minus the total, over rate, favorite and home cover rates, with season-block
   bootstrap intervals and a regression with dome, wind, cold and late-season controls.
2. Primetime unders year by year at -110 (52.4% to break even).
3. Pace (plays and pass rate per game, 2016-2025).
4. Player props, 2025 weeks 3-18 (data/odds_history, ~1 hour before kickoff): Pinnacle's
   no-vig chance of the over against the result. Players with offensive snaps but no
   stats count as zeros; players who didn't play are void.

Findings on 2026-09-27 are in docs/DECISIONS.md ("No primetime adjustment").
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from betlab import config, odds_math as om, players  # noqa: E402
from betlab.sources import nflverse  # noqa: E402

RNG = np.random.default_rng(7)
PRIME_HOUR = 19


def games() -> pd.DataFrame:
    g = nflverse.load_games()
    g = g[(g["game_type"] == "REG") & g["home_pts"].notna() & g["total_line"].notna() & g["season"].between(2006, 2025)].copy()
    g["prime"] = (g["kickoff"].dt.hour + g["kickoff"].dt.minute / 60) >= PRIME_HOUR
    g["slot"] = np.select([~g["prime"], g["weekday"].eq("Thursday"), g["weekday"].eq("Sunday"), g["weekday"].eq("Monday")],
                          ["day", "TNF", "SNF", "MNF"], "other night")
    g["pts"] = g["home_pts"] + g["away_pts"]
    g["tot_res"] = g["pts"] - g["total_line"]
    g["ats_res"] = g["margin"] - g["spread_line"]             # + = home covered
    g["fav_res"] = np.sign(g["spread_line"]) * g["ats_res"]    # + = favorite covered
    g["over"] = np.where(g["tot_res"] == 0, np.nan, (g["tot_res"] > 0).astype(float))
    g["home_cov"] = np.where(g["ats_res"] == 0, np.nan, (g["ats_res"] > 0).astype(float))
    g["fav_cov"] = np.where((g["fav_res"] == 0) | (g["spread_line"] == 0), np.nan, (g["fav_res"] > 0).astype(float))
    g["era"] = pd.cut(g["season"], [2005, 2012, 2018, 2025], labels=["2006-12", "2013-18", "2019-25"])
    return g


def block_boot(df: pd.DataFrame, block: str, stat, n: int = 2000) -> np.ndarray:
    """Bootstrap stat(df) resampling whole blocks (seasons or games)."""
    keys = df[block].unique()
    parts = {k: df[df[block] == k] for k in keys}
    return np.array([stat(pd.concat([parts[k] for k in RNG.choice(keys, len(keys))])) for _ in range(n)])


def ols(df: pd.DataFrame, y: str, xs: list[str]) -> np.ndarray:
    a = np.column_stack([np.ones(len(df))] + [df[c].to_numpy(float) for c in xs])
    return np.linalg.lstsq(a, df[y].to_numpy(float), rcond=None)[0]


def game_study(g: pd.DataFrame) -> None:
    def row(d):
        return {"games": len(d), "avg total": d["total_line"].mean(), "avg pts": d["pts"].mean(),
                "pts - total": d["tot_res"].mean(), "over %": 100 * d["over"].mean(), "SD pts-total": d["tot_res"].std(),
                "home cover %": 100 * d["home_cov"].mean(), "fav cover %": 100 * d["fav_cov"].mean()}

    print("== Games 2006-2025, against the closing line ==")
    print(pd.DataFrame({k: row(d) for k, d in g.groupby("slot")}).round(2).to_string())
    for col, name, scale in (("tot_res", "points vs total", 1), ("over", "over rate (pts)", 100),
                             ("fav_cov", "favorite cover (pts)", 100), ("home_cov", "home cover (pts)", 100)):
        diff = lambda d, c=col: d.loc[d["prime"], c].mean() - d.loc[~d["prime"], c].mean()
        lo, hi = np.nanpercentile(block_boot(g, "season", diff), [2.5, 97.5]) * scale
        print(f"  primetime minus day, {name}: {diff(g) * scale:+.2f}  95% CI [{lo:+.2f}, {hi:+.2f}]")

    d = g.copy()
    d["dome"] = d["roof"].isin(["dome", "closed"]).astype(float)
    d["wind"] = d["wind"].fillna(0).where(d["dome"] == 0, 0)
    d["cold"] = ((d["temp"].fillna(65) < 40) & (d["dome"] == 0)).astype(float)
    d["late"] = (d["week"] >= 13).astype(float)
    d["e2"], d["e3"] = (d["era"] == "2013-18").astype(float), (d["era"] == "2019-25").astype(float)
    d["primef"] = d["prime"].astype(float)
    xs = ["primef", "dome", "wind", "cold", "late", "e2", "e3"]
    for label, dd in (("2006-25", d), ("2019-25", d[d["era"] == "2019-25"])):
        cols = xs if label == "2006-25" else xs[:5]
        coef = ols(dd, "tot_res", cols)[1]
        lo, hi = np.percentile(block_boot(dd, "season", lambda x: ols(x, "tot_res", cols)[1]), [2.5, 97.5])
        print(f"  {label}, points vs total with controls, primetime: {coef:+.2f}  95% CI [{lo:+.2f}, {hi:+.2f}]")

    print("\n== Primetime unders by stretch (-110 needs 52.4%) ==")
    pr = g[g["prime"] & g["over"].notna()]
    for a, b in ((2006, 2012), (2013, 2018), (2019, 2023), (2024, 2025), (2006, 2025)):
        s = pr[pr["season"].between(a, b)]
        u = 1 - s["over"].mean()
        print(f"  {a}-{b}: {len(s)} games, unders {100 * u:.1f}%, {len(s) * (u * 100 / 110 - (1 - u)):+.1f} units")


def pace_study(g: pd.DataFrame) -> None:
    import nflreadpy as nfl

    ts = nfl.load_team_stats(seasons=list(range(2016, 2026))).to_pandas()
    ts["plays"] = ts["attempts"] + ts["sacks_suffered"] + ts["carries"]
    ts["dropbacks"] = ts["attempts"] + ts["sacks_suffered"]
    gg = ts.groupby("game_id")[["plays", "dropbacks"]].sum().reset_index().merge(g[["game_id", "prime", "season"]], on="game_id")
    gg["pass_rate"] = gg["dropbacks"] / gg["plays"]
    print("\n== Pace 2016-2025 (both teams) ==")
    print(gg.groupby("prime")[["plays", "pass_rate"]].mean().round(3).to_string())
    diff = lambda d: d.loc[d["prime"], "plays"].mean() - d.loc[~d["prime"], "plays"].mean()
    lo, hi = np.percentile(block_boot(gg, "season", diff), [2.5, 97.5])
    print(f"  primetime minus day, plays: {diff(gg):+.2f}  95% CI [{lo:+.2f}, {hi:+.2f}]")


STAT = {"player_receptions": "receptions", "player_reception_yds": "receiving_yards",
        "player_rush_yds": "rushing_yards", "player_pass_yds": "passing_yards"}


def props_study() -> None:
    import nflreadpy as nfl

    path = config.ROOT / "data" / "odds_history" / "americanfootball_nfl" / "props_2025.parquet"
    d = pd.read_parquet(path)
    d = d[(d["bookmaker"] == "pinnacle") & d["point"].notna()]
    p = d.pivot_table(index=["game_id", "commence_time", "player", "market", "point"], columns="outcome",
                      values="price", aggfunc="last").dropna().reset_index()
    p["p_over"] = [om.devig([o, u], "multiplicative")[0] for o, u in zip(p["Over"], p["Under"])]
    et = pd.to_datetime(p["commence_time"]).dt.tz_convert("America/New_York")
    p["prime"] = (et.dt.hour + et.dt.minute / 60) >= PRIME_HOUR
    p["key"] = p["player"].map(players.normalize)

    ps = nflverse.load_player_stats([2025])
    ps["key"] = ps["player_display_name"].map(players.normalize)
    stats = ps.drop_duplicates(["game_id", "key"]).set_index(["game_id", "key"])[list(STAT.values())]
    snaps = nfl.load_snap_counts(seasons=[2025]).to_pandas()
    snaps["key"] = snaps["player"].map(players.normalize)
    played = set(zip(snaps.loc[snaps["offense_snaps"] > 0, "game_id"], snaps.loc[snaps["offense_snaps"] > 0, "key"]))

    def actual(r):
        k = (r.game_id, r.key)
        if k in stats.index:
            return float(stats.at[k, STAT[r.market]])
        return 0.0 if k in played else np.nan            # snaps but no stats: zero; no snaps: void

    p["actual"] = [actual(r) for r in p.itertuples()]
    s = p[p["actual"].notna()].copy()
    s["over"] = (s["actual"] > s["point"]).astype(float)
    s["gap"] = s["over"] - s["p_over"]                     # + = overs beat the market's chance
    print(f"\n== Props 2025 (Pinnacle, {len(s)} settled lines, {p['actual'].isna().sum()} void) ==")
    print(s.groupby("prime").agg(lines=("gap", "size"), games=("game_id", "nunique"), market_p_over=("p_over", "mean"),
                                 over_hit=("over", "mean"), gap=("gap", "mean")).round(4).to_string())
    print(s.groupby(["market", "prime"]).agg(lines=("gap", "size"), gap=("gap", "mean")).round(3).to_string())
    diff = lambda x: x.loc[x["prime"], "gap"].mean() - x.loc[~x["prime"], "gap"].mean()
    lo, hi = np.percentile(block_boot(s, "game_id", diff), [2.5, 97.5])
    print(f"  primetime minus day, over gap: {diff(s):+.4f}  95% CI (game bootstrap) [{lo:+.4f}, {hi:+.4f}]")


if __name__ == "__main__":
    g = games()
    game_study(g)
    pace_study(g)
    props_study()
