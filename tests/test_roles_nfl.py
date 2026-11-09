"""Props model v0.2: roles from snap share, matchups, absences, robust team volume (synthetic data)."""

import numpy as np
import pandas as pd
import pytest

from betlab.models import props_nfl as P
from betlab.models import roles_nfl as R

# One team (AAA) over 8 games against BBB/CCC. Per game: position, targets, carries, snap %
ROLES = {
    "WR1": ("WR", 9, 0, 0.90), "WR2": ("WR", 5, 0, 0.75), "WR5": ("WR", 0, 0, 0.08),
    "TE": ("TE", 4, 0, 0.80), "RB": ("RB", 3, 16, 0.65), "QB": ("QB", 0, 3, 1.0),
}


def build(weeks=8, rested_week=None, easy_defense=None):
    ps, snaps, games = [], [], []
    for w in range(1, weeks + 1):
        opp = "BBB" if w % 2 else "CCC"
        gid = f"2025_{w:02d}_AAA_{opp}"
        games.append({"game_id": gid, "season": 2025, "week": w, "date": pd.Timestamp("2025-09-07") + pd.Timedelta(weeks=w),
                      "home_team": "AAA", "away_team": opp, "spread_line": 0.0, "total_line": 44.0,
                      "home_pts": 20, "away_pts": 20})
        rested = w == rested_week
        for name, (pos, tg, ca, pct) in ROLES.items():
            tg_, ca_ = (1 if tg else 0, 1 if ca else 0) if rested else (tg, ca)
            ypt = 12.0 if easy_defense == opp else 8.0
            ps.append({"player_id": f"AAA-{name}", "player_display_name": name, "position": pos, "game_id": gid,
                       "team": "AAA", "attempts": (10 if rested else 34) if pos == "QB" else 0, "completions": 0,
                       "passing_yards": 0, "passing_tds": 0, "carries": ca_, "rushing_yards": ca_ * 4, "rushing_tds": 0,
                       "targets": tg_, "receptions": round(tg_ * 0.65), "receiving_yards": tg_ * ypt,
                       "receiving_tds": 0})
            snaps.append({"player_id": f"AAA-{name}", "game_id": gid, "team": "AAA", "position": pos,
                          "player": name, "offense_snaps": 60 * pct, "offense_pct": pct})
        # The opponents' own offense, so the defenses have something to be compared against.
        for name, (pos, tg, ca, pct) in ROLES.items():
            ps.append({"player_id": f"{opp}-{name}", "player_display_name": name, "position": pos, "game_id": gid,
                       "team": opp, "attempts": 34 if pos == "QB" else 0, "completions": 0, "passing_yards": 0,
                       "passing_tds": 0, "carries": ca, "rushing_yards": ca * 4, "rushing_tds": 0, "targets": tg,
                       "receptions": round(tg * 0.65), "receiving_yards": tg * 8.0, "receiving_tds": 0})
    df = R.prepare(pd.DataFrame(ps).query("targets + carries + attempts > 0"), pd.DataFrame(games), pd.DataFrame(snaps))
    return R.History(df), df


BEFORE = pd.Timestamp("2025-12-31")


def test_players_who_played_without_stats_are_kept_as_zeros():
    hist, df = build()
    wr5 = df[df["player_id"] == "AAA-WR5"]
    assert len(wr5) == 8 and (wr5["targets"] == 0).all()        # never in player stats, still in history


def test_backups_get_backup_shares_and_the_team_adds_up():
    hist, _ = build()
    rp, p = R.RoleParams(fill_shares=True, snap_prior_games=0.1, rate_prior=12.0), P.PropParams()
    roster = pd.DataFrame([{"player_id": f"AAA-{n}", "name": n, "position": ROLES[n][0]} for n in ROLES])
    pl = R.team_inputs(hist, "AAA", "BBB", BEFORE, roster, 0.0, 44.0, rp, p)["players"].set_index("name")
    assert pl.loc["WR1", "t_share"] > 0.3 > pl.loc["WR2", "t_share"] > pl.loc["WR5", "t_share"]
    assert pl.loc["WR5", "t_share"] < 0.03                       # 8% of snaps, no targets: a backup's share
    assert pl["t_share"].sum() == pytest.approx(0.96)
    assert pl.loc["RB", "c_share"] > 0.7


def test_a_missing_regular_leaves_his_share_to_teammates():
    hist, _ = build()
    rp, p = R.RoleParams(fill_shares=False), P.PropParams()
    full = pd.DataFrame([{"player_id": f"AAA-{n}", "name": n, "position": ROLES[n][0]} for n in ROLES])
    base = R.team_inputs(hist, "AAA", "BBB", BEFORE, full, 0.0, 44.0, rp, p)["players"].set_index("name")
    without = R.team_inputs(hist, "AAA", "BBB", BEFORE, full[full["name"] != "WR1"], 0.0, 44.0, rp, p,
                            frozenset({"AAA-WR1"}))["players"].set_index("name")
    assert without.loc["WR2", "t_share"] > base.loc["WR2", "t_share"] * 1.3


def test_the_markets_qb_starts_over_the_snap_leader():
    # Sep 27: snaps picked Carson Wentz over Kyler Murray (new to the team), whose rushing
    # line then had no carries behind it and the game's parlays were skipped.
    hist, _ = build()
    rp, p = R.RoleParams(), P.PropParams()
    roster = pd.DataFrame([{"player_id": f"AAA-{n}", "name": n, "position": ROLES[n][0]} for n in ROLES]
                          + [{"player_id": "NEW-QB", "name": "NEWQB", "position": "QB"}])
    by_snaps = R.team_inputs(hist, "AAA", "BBB", BEFORE, roster, 0.0, 44.0, rp, p)["players"].set_index("name")
    assert by_snaps.loc["QB", "is_qb"] and by_snaps.loc["NEWQB", "c_share"] == 0.0
    listed = R.team_inputs(hist, "AAA", "BBB", BEFORE, roster, 0.0, 44.0, rp, p,
                           starter="NEW-QB")["players"].set_index("name")
    assert listed.loc["NEWQB", "is_qb"] and not listed.loc["QB", "is_qb"]
    assert listed.loc["NEWQB", "c_share"] > 0.05 and listed.loc["QB", "c_share"] == 0.0
    # a starter who isn't on the roster falls back to snaps
    assert R.team_inputs(hist, "AAA", "BBB", BEFORE, roster, 0.0, 44.0, rp, p,
                         starter="GONE")["players"].set_index("name").loc["QB", "is_qb"]


def test_robust_volume_ignores_a_game_where_starters_rested():
    hist, _ = build(rested_week=8)
    p = P.PropParams()
    roster = pd.DataFrame([{"player_id": "AAA-WR1", "name": "WR1", "position": "WR"}])
    plain = R.team_inputs(hist, "AAA", "BBB", BEFORE, roster, 0.0, 44.0, R.RoleParams(robust_volume=False), p)["volume"]
    robust = R.team_inputs(hist, "AAA", "BBB", BEFORE, roster, 0.0, 44.0, R.RoleParams(robust_volume=True), p)["volume"]
    assert robust["targets"] > plain["targets"] + 2


def test_an_easy_defense_raises_efficiency():
    hist, _ = build(easy_defense="CCC")
    rp = R.RoleParams()
    easy, hard = R.matchup(hist, "CCC", BEFORE, rp), R.matchup(hist, "BBB", BEFORE, rp)
    assert easy["WR"]["ypt"] > 1.0 > hard["WR"]["ypt"]
    assert R.matchup(hist, "CCC", BEFORE, R.RoleParams(use_matchup=False))["WR"]["ypt"] == 1.0
