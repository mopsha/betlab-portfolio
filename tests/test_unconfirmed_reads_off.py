"""Oct 19 (Mike): the three 2025-only reads that 2024 lines didn't confirm are off (DECISIONS 2026-10-19)."""

from betlab import config
from betlab import props_market as PM
from betlab.cards import preview_nfl


def test_the_over_lean_shift_is_off_everywhere():
    assert PM.over_shift(0.5, "receptions") == 0.5 and PM.over_shift(0.5, "receiving_yards") == 0.5
    assert config.settings()["props"]["shift_in_picks"] is False


def test_fun_slips_skip_the_script_read():
    assert config.settings()["fun"]["script_read"] is False


def test_the_games_tab_shows_no_matchup_notes():
    row = {"matchup_side": "over", "_mf": {}, "fd_over": -110, "fd_under": -110, "opp": "BUF", "player": "X",
           "stat": "receiving_yards", "line": 50.5, "team": "MIA"}
    assert preview_nfl._matchup_notes([row], lambda t: t) == []


def test_the_games_tab_shows_no_lines_that_fit_the_script():
    """Oct 28 (Mike): below the market on 2026's lines too; the rows stay tracked."""
    row = {"script_side": "over", "p_script": 0.56, "p_market": 0.5, "fd_over": -110, "fd_under": -110, "player": "X",
           "stat": "receptions", "line": 4.5, "team": "MIA"}
    assert preview_nfl._script_lines([row], {"MIA": "why"}) == []
