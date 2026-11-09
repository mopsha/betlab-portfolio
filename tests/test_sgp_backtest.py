"""The parlay backtest's measuring tools and the simulator settings it fitted."""

import numpy as np
import pandas as pd
import pytest

from betlab import backtest_sgp as S
from betlab.models import game_sim_nfl as G
from test_sgp import FEATURED, history, rosters


def sim_with(**kw):
    return G.simulate_game(history(), "BBB", "AAA", 3.0, 45.0, rosters(), FEATURED, n=8000, seed=3,
                           sp=G.SimParams(**kw))


def test_pit_ranks_are_uniform_even_with_ties():
    rng = np.random.default_rng(0)
    tds = rng.poisson(0.3, 20000).astype(float)          # mostly zeros
    u = S.pit_draws(tds, rng)
    assert abs(u.mean() - 0.5) < 0.01 and abs((u > S.Q).mean() - (1 - S.Q)) < 0.01
    assert S.pit_value(np.array([0.0, 0.0, 1.0, 2.0]), 1.0, 0.5) == 0.5 + 0.5 * 0.25


def test_roles_pick_the_starter_top_targets_and_lead_back():
    sim = sim_with()
    r = S.roles(sim, "AAA")
    assert r == {"QB": "AAA-QB", "T1": "AAA-WR1", "T2": "AAA-WR2", "RB1": "AAA-RB"}


def test_volume_trade_off_makes_a_teams_passing_and_rushing_move_apart():
    # v0: half the pregame script coefficients, no trade-off; the default is the 2021-24 fit
    base, fitted = sim_with(surprise_targets=-0.175, surprise_carries=0.15, vol_corr=0.0), sim_with()
    rho = lambda s: np.corrcoef(s.get("AAA-QB", "passing_yards"), s.get("AAA-RB", "rushing_yards"))[0, 1]
    assert rho(fitted) < rho(base) - 0.05 and rho(fitted) < 0


def test_efficiency_ties_yards_to_points_and_other_td_zero_gives_listed_players_every_td():
    lo, hi = sim_with(eff_beta=0.0), sim_with(eff_beta=0.25)
    link = lambda s: np.corrcoef(s.get("AAA-QB", "passing_yards"), s.points["AAA"])[0, 1]
    assert link(hi) > link(lo) + 0.05
    base, listed = sim_with(other_td=1.0), sim_with()
    total = lambda s: sum(s.get(f"AAA-{r}", "tds").mean() for r in ("QB", "WR1", "WR2", "TE", "RB"))
    assert total(listed) > total(base)
    assert abs(total(listed) - G.SimParams().td_per_point * listed.points["AAA"].mean()) < 0.06   # sampling noise ~0.017


def test_a_game_over_its_total_gives_both_offenses_more_targets():
    # Sep 28: real games tie a QB's yards to the game total 0.34; without this link, 0.24
    off, on = sim_with(surprise_total_targets=0.0, surprise_total_carries=0.0), sim_with()
    total = lambda s: s.points["AAA"] + s.points["BBB"]
    link = lambda s, qb: np.corrcoef(s.get(qb, "passing_yards"), total(s))[0, 1]
    for qb in ("AAA-QB", "BBB-QB"):
        assert link(on, qb) > link(off, qb) + 0.03
    assert on.get("AAA-QB", "passing_yards").mean() == pytest.approx(off.get("AAA-QB", "passing_yards").mean(), rel=0.02)


def test_passing_bends_down_in_blowouts_and_keeps_its_average():
    sp = G.SimParams()
    m = np.array([-35.0, -21.0, -7.0, 0.0, 14.0, 35.0])
    b = G.margin_bend(m, sp)
    assert b[3] == pytest.approx(1.0)                        # a tie: no bend
    assert b[2] > 1.04 and b[4] < 0.96 and b[0] < 0.9        # trailing by a TD throws more; blowouts less
    assert b[0] == pytest.approx(b[1])                       # flat below -21
    assert np.allclose(G.margin_bend(m, G.SimParams(margin_bend=(0, 0, 0, 0))), 1.0)
    off, on = sim_with(margin_bend=(0.0, 0.0, 0.0, 0.0)), sim_with()
    qb = lambda s: s.get("AAA-QB", "passing_yards")
    assert qb(on).mean() == pytest.approx(qb(off).mean(), rel=0.02)
    big_win = lambda s: (s.points["AAA"] - s.points["BBB"]) > 14
    assert qb(on)[big_win(on)].mean() < qb(off)[big_win(off)].mean() * 0.97


def test_a_big_passing_day_brings_more_passing_touchdowns():
    link = lambda s: np.corrcoef(s.team["AAA"]["pass_yds"], s.team["AAA"]["pass_tds"])[0, 1]
    rush = lambda s: np.corrcoef(s.team["AAA"]["pass_yds"], s.team["AAA"]["rush_tds"])[0, 1]
    old, new = sim_with(pass_share_beta=0.0, td_yds_gamma=0.0), sim_with()
    assert link(new) > link(old) + 0.15 and abs(rush(new)) < 0.1
    tds = lambda s: (s.team["AAA"]["pass_tds"] + s.team["AAA"]["rush_tds"]).mean()
    assert tds(new) == pytest.approx(tds(old), abs=0.08)            # the tilt keeps the average


def test_market_pair_kinds():
    k = lambda a, b: S._kind({"team": a[0], "stat": a[1]}, {"team": b[0], "stat": b[1]})
    assert k(("A", "passing_yards"), ("A", "receptions")) == "QB + his receiver"
    assert k(("A", "receiving_yards"), ("A", "receptions")) == "two receivers, same team"
    assert k(("A", "rushing_yards"), ("A", "receiving_yards")) == "rusher + a teammate"
    assert k(("A", "passing_yards"), ("B", "passing_yards")) == "both QBs"
    assert k(("A", "rushing_yards"), ("B", "passing_yards")) == "rusher + the other team"


def test_report_on_a_tiny_synthetic_result():
    pairs = pd.DataFrame({"game_id": ["g1", "g2", "g3", "g4"] * 25, "pair": "qb_t1", "sim_rho": 0.4,
                          "sim_joint": 0.55, "ua": np.linspace(0.01, 0.99, 100), "ub": np.linspace(0.02, 0.98, 100)})
    slips = pd.DataFrame({"game_id": ["g1", "g2"] * 10, "slip": "x", "sim_all": 0.3, "hit": [1.0, 0.0] * 10,
                          "legs_hit": [4, 2] * 10, **{f"leg{i}": [1.0, 0.5] * 10 for i in range(4)}})
    tds = pd.DataFrame({"game_id": ["g1"] * 4, "position": "WR", "p_td": [0.1, 0.2, 0.3, 0.4], "td": [0, 0, 1, 1.0]})
    teams = pd.DataFrame({"game_id": ["g1"], "sim_tds": [2.3], "tds": [2.0]})
    rep = S.report({"pairs": pairs, "slips": slips, "tds": tds, "teams": teams}, boot=5)
    row = rep["pairs"].iloc[0]
    assert row["real_together"] > 0.99 and row["sim_lift"] == round(0.55 / 0.49, 3)
    assert rep["slips"].iloc[0]["real_all_4"] == 0.5
    tail = S.report({"pairs": pairs.assign(sim_joint_tail=0.1), "slips": slips, "tds": tds, "teams": teams}, boot=5)
    row = tail["pairs"].iloc[0]
    assert row["sim_tail_lift"] == round(0.1 / 0.0625, 3) and row["real_tail_lift"] > 3.5   # ranks move as one


def test_game_line_pairs_use_the_final_score():
    # The GAME role's legs are the game's total and each team's margin (moneyline/spread legs).
    games = [k for k, _, (ra, _), _, _ in S.PAIRS if ra == "GAME"]
    assert {"tot_qb", "win_qb", "win_oqb"} <= set(games)
    assert all(st in ("total", "margin") for _, _, (ra, st), _, _ in S.PAIRS if ra == "GAME")
