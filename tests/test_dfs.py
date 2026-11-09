"""The DFS optimizer (dfs.py): scoring, the market's expected stats, and legal lineups."""

from datetime import datetime, timezone

import pytest

from betlab import dfs


def _p(i, pos, salary, proj, team="AAA", game="AAA@BBB", status=""):
    return dfs.Player(id=str(i), name=f"P{i}", team=team, game=game, start=None, positions=pos.split("/"), salary=salary,
                      average=proj, status=status, proj=proj)


def _nba_pool():
    out, i = [], 0
    for g, teams in (("AAA@BBB", "AAA"), ("CCC@DDD", "CCC")):
        for pos in ("PG/G/UTIL", "SG/G/UTIL", "SF/F/UTIL", "PF/F/UTIL", "C/UTIL"):
            for salary, proj in ((9000, 50), (6000, 30), (3500, 14)):
                i += 1
                out.append(_p(i, pos, salary, proj, teams, g))
    return out


def test_draftkings_scoring():
    assert dfs.dk_nba({"points": 20, "threes": 2, "rebounds": 10, "assists": 4, "steals": 1, "blocks": 1, "turnovers": 2, "dd": 1}) \
        == pytest.approx(20 + 1 + 12.5 + 6 + 2 + 2 - 1 + 1.5)
    assert dfs.dk_nfl({"pass_yards": 250, "pass_tds": 2, "ints": 1, "rush_yards": 10, "rec_yards": 50, "receptions": 5, "tds": 1}) \
        == pytest.approx(10 + 8 - 1 + 1 + 5 + 5 + 6)


def test_a_line_at_even_is_its_own_mean_and_a_likely_over_is_above_it():
    assert dfs.mean_from_line("points", 24.5, 0.5) == pytest.approx(24.5)
    assert dfs.mean_from_line("points", 24.5, 0.6) > 24.5 > dfs.mean_from_line("points", 24.5, 0.4)


def test_the_better_source_wins_then_the_line_nearest_even():
    m = dfs.best_means([("A B", "points", 30.5, 0.2, 1), ("A B", "points", 24.5, 0.5, 1), ("A B", "points", 20.5, 0.6, 0),
                        ("A B", "points", 18.5, 0.8, 0)])
    assert m["a b"]["points"] == pytest.approx(dfs.mean_from_line("points", 20.5, 0.6))


def test_a_player_without_his_main_line_stays_on_his_average():
    pool = [_p(1, "PG", 5000, 0), _p(2, "PG", 5000, 0)]
    pool[0].name, pool[1].name = "Has Line", "No Line"
    pool[0].average, pool[1].average = 30, 22
    dfs.project(pool, "nba", {"has line": {"points": 20}, "no line": {"rebounds": 9}}, {"has line": {"rebounds": 4}})
    assert (pool[0].basis, pool[0].proj) == ("market", 25.0)
    assert (pool[1].basis, pool[1].proj) == ("average", 22)


def test_the_export_is_read_as_draftkings_writes_it():
    text = ("﻿Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status,Starting\n"
            "PF,G A (1),G A,1,PF/F/UTIL,11000,MIA@GSW 11/05/2026 10:00PM ET,MIA,57.2,OUT,\n")
    p = dfs.parse_csv(text)[0]
    assert (p.id, p.salary, p.positions, p.status, p.game) == ("1", 11000, ["PF", "F", "UTIL"], "OUT", "MIA@GSW")
    assert p.start.astimezone(timezone.utc) == datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)


def test_novig_markets_read_both_sides():
    m = {"description": "Jalen Brunson 24.5 POINTS", "strike": "24.5",
         "outcomes": [{"name": "Over 24.5", "bid": {"price": "0.48"}}, {"name": "Under 24.5", "bid": {"price": "0.48"}}]}
    assert dfs.novig_row(m, "points") == ("Jalen Brunson", "points", 24.5, pytest.approx(0.5), 1)
    m["outcomes"][1].pop("bid")
    assert dfs.novig_row(m, "points") is None


def test_lineups_are_legal_and_different():
    pool = _nba_pool() + [_p(99, "PG/G/UTIL", 3000, 500, status="OUT")]
    found = dfs.optimize_lineups(pool, "nba", n=3)
    assert len(found) == 3
    seen = []
    for lu in found:
        ids = {p.id for _, p in lu}
        assert len(ids) == 8 and "99" not in ids
        assert sum(p.salary for _, p in lu) <= dfs.CAP
        assert all(slot in p.positions for slot, p in lu)
        assert len({p.game for _, p in lu}) >= 2
        assert all(len(ids & s) <= 6 for s in seen)
        seen.append(ids)


def test_an_nfl_quarterback_has_a_receiver_with_him():
    pool, i = [], 0
    for team, game in (("AAA", "AAA@BBB"), ("CCC", "CCC@DDD")):
        for pos, n, sal, pr in (("QB", 1, 6000, 20 if team == "AAA" else 19), ("RB/FLEX", 3, 5000, 12), ("TE/FLEX", 2, 3000, 6), ("DST", 1, 2500, 7)):
            for _ in range(n):
                i += 1
                pool.append(_p(i, pos, sal, pr, team, game))
        for k in range(4):                     # team AAA's receivers are the poor ones: only the rule puts one in the lineup
            i += 1
            pool.append(_p(i, "WR/FLEX", 4000, 3 if team == "AAA" else 12 + k, team, game))
    lu = dfs.optimize_lineups(pool, "nfl", n=1)[0]
    qb = next(p for s, p in lu if s == "QB")
    assert any(p.team == qb.team and {"WR", "TE"} & set(p.positions) for s, p in lu if s != "QB")


def test_grade_fills_results_from_the_box(tmp_path, monkeypatch):
    from betlab import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    (tmp_path / "ledger").mkdir()
    pool = [_p(1, "PG", 5000, 30), _p(2, "SG", 5000, 20)]
    doc = dfs.lineup_doc([("PG", pool[0]), ("SG", pool[1])])
    lock = datetime(2026, 11, 5, 23, 0, tzinfo=timezone.utc)
    dfs.log_slate("nba:1", "nba", "Main", lock, [doc], pool)
    dfs.log_slate("nba:1", "nba", "Main", lock, [doc], pool)         # a later build replaces, it doesn't add
    monkeypatch.setattr(dfs, "actual_points", lambda lg, days: {("2026-11-05", "p1"): 41.5})
    assert dfs.grade(now=datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)) == "dfs grade: 2 of 2 players graded"
    import pandas as pd

    lu = pd.read_csv(tmp_path / "ledger" / "dfs_lineups.csv")
    assert len(lu) == 1 and lu.loc[0, "actual"] == 41.5                  # p2 not in the box: he didn't play
    assert "dfs grade: 0 of 0" in dfs.grade(now=datetime(2026, 11, 6, 13, 0, tzinfo=timezone.utc))
