"""Football explanations: every factor points the right way and the notes stay honest."""

import pandas as pd

from betlab import explain


def facts(**over):
    recent = pd.DataFrame({"offense_pct": [0.60, 0.65, 0.90], "targets": [5, 6, 9], "receptions": [3, 4, 7],
                           "receiving_yards": [35, 48, 90], "carries": [0, 0, 0], "attempts": [0, 0, 0]})
    defenses = pd.DataFrame({"WR_ypt": [1.12, 1.0, 0.9], "WR_catch": [1.05, 1.0, 0.95], "TE_ypt": [1, 1, 1],
                             "TE_catch": [1, 1, 1], "RB_ypt": [1, 1, 1], "RB_catch": [1, 1, 1],
                             "RB_ypc": [1, 1, 1]}, index=["ATL", "CHI", "DET"])
    base = {"name": "Test Receiver", "position": "WR", "team": "Packers", "opp": "Falcons", "opp_abbr": "ATL",
            "stat": "receiving_yards", "snap": 0.8, "recent": recent, "vol": {"targets": 32, "carries": 26},
            "exp_targets": 7.1, "exp_carries": 0.0, "matchup": {}, "defenses": defenses, "spread": -6.5,
            "implied": 19.0, "total": 44.5, "missing": [{"name": "Other WR", "position": "WR", "t_share": 0.14,
                                                          "c_share": 0.0}], "median": 52.0}
    return base | over


def test_over_story_lists_what_helps_and_hurts():
    s = explain.prop_story(facts(), "Over", 55.5)
    assert "90% of snaps" not in s and "72% of snaps" in s          # recent average, not one game
    assert "For the over:" in s
    assert "snaps are climbing" in s and "Other WR out" in s and "12% more yards per target" in s
    assert "trailing teams throw more" in s                          # a 6.5-point underdog
    assert "no weight yet" in s                                       # honest about why it's a pick


def test_the_story_says_whether_the_price_is_corrected():
    assert "which our fair price corrects for" in explain.prop_story(facts(), "Over", 55.5)
    s = explain.prop_story(facts(), "Over", 55.5, shifted=False)
    assert "uncorrected" in s and "corrects for" not in s


def test_under_story_flips_the_directions():
    s = explain.prop_story(facts(), "Under", 55.5)
    assert "Against it:" in s and "For the under:" not in s


def test_game_line_story_mentions_ratings_rest_and_weight():
    g = {"pts_home": 26.2, "pts_away": 19.8, "model_margin": 6.4, "model_total": 46.0, "rest_diff": 4}
    s = explain.game_line_story(g, "spreads", "GB", "ATL", 5.0, 0.0, False, None)
    assert "26-20" in s and "by 6.4" in s and "4 more days of rest" in s and "only 0% weight" in s
    college = explain.game_line_story(g, "totals", "Florida State", "Central Arkansas", 60.5, 0.0, True, None)
    assert "for Florida State" in college and "the Florida State" not in college
