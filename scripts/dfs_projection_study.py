"""Do the DFS optimizer's market projections beat a player's own average? (Nov 5, idea #38; free, reads saved props and ESPN.)

For every NBA game with a props pull this season: each player's DraftKings points at the market's expected stats (dfs.py's
method: a sharp book's line nearest even, the season so far for steals, blocks and turnovers), against his average before
that game and against what he really scored. Salaries from the past aren't kept anywhere free, so this tests the projections
only, never the lineups. Run: .venv/bin/python scripts/dfs_projection_study.py
"""

from __future__ import annotations

import glob

import numpy as np
import pandas as pd

from betlab import config, dfs, players
from betlab.sources import nba


STATS = ["points", "rebounds", "assists", "steals", "blocks", "turnovers", "three_point_field_goals_made"]


def _actual(r) -> float:
    c = sum(getattr(r, k) >= 10 for k in ("points", "rebounds", "assists", "steals", "blocks"))
    return dfs.dk_nba({"points": r.points, "threes": r.three_point_field_goals_made, "rebounds": r.rebounds, "assists": r.assists,
                       "steals": r.steals, "blocks": r.blocks, "turnovers": r.turnovers, "dd": float(c >= 2), "td": float(c >= 3)})


def main() -> None:
    box = nba.load_player_box([nba.current_season()], max_age_hours=12)
    box = box[box["did_not_play"] != True].copy()  # noqa: E712
    box[STATS] = box[STATS].astype(float).fillna(0)
    box["game_date"] = box["game_date"].astype(str)
    box["key"] = box["athlete_display_name"].map(players.normalize)
    box["dk"] = [_actual(r) for r in box.itertuples()]
    box["cats"] = (box[["points", "rebounds", "assists", "steals", "blocks"]] >= 10).sum(axis=1)
    box = box.sort_values("game_date")
    days = sorted({f.split("/")[-2] for f in glob.glob(str(config.DATA_DIR / "odds" / "basketball_nba" / "*" / "*_props.parquet"))})
    rows = []
    for day in days:
        means = dfs.best_means(dfs.odds_quotes("nba", day))
        tonight = box[box["game_date"] == day]
        earlier = box[box["game_date"] < day]
        for r in tonight.itertuples():
            m, past = means.get(r.key), earlier[earlier["key"] == r.key]
            if not m or "points" not in m or len(past) < 3:
                continue
            extra = {"steals": past["steals"].mean(), "blocks": past["blocks"].mean(), "turnovers": past["turnovers"].mean(),
                     "threes": past["three_point_field_goals_made"].mean(), "rebounds": past["rebounds"].mean(), "assists": past["assists"].mean(), "dd": (past["cats"] >= 2).mean(), "td": (past["cats"] >= 3).mean()}
            rows.append({"day": day, "player": r.key, "actual": r.dk, "market": dfs.dk_nba({**extra, **m}), "average": past["dk"].mean(),
                         "full_line": all(k in m for k in ("rebounds", "assists"))})
    df = pd.DataFrame(rows)
    def line(name, d):
        err = {k: d[k] - d["actual"] for k in ("market", "average")}
        print(f"{name}: {len(d)} player-games over {d['day'].nunique()} days; "
              f"MAE market {err['market'].abs().mean():.2f}, average {err['average'].abs().mean():.2f}; "
              f"RMSE market {np.sqrt((err['market']**2).mean()):.2f}, average {np.sqrt((err['average']**2).mean()):.2f}; "
              f"bias market {err['market'].mean():+.2f}, average {err['average'].mean():+.2f}; "
              f"corr market {d['market'].corr(d['actual']):.3f}, average {d['average'].corr(d['actual']):.3f}")
    line("All", df)
    line("Points, rebounds and assists all priced", df[df["full_line"]])
    mid = df["day"].sort_values().iloc[len(df) // 2]
    line("First half of the days", df[df["day"] <= mid])
    line("Second half of the days", df[df["day"] > mid])


if __name__ == "__main__":
    main()
