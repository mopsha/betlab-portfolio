"""Live CLV on open bets (Oct 28, idea #2): singles, app parlays and cross-game slips priced at the current sharp chance."""

import pytest

from betlab import clv_now as C

PACKS = [{"event_id": "e1", "matchup": "New York Knicks @ Chicago Bulls", "commence_time": "2099-01-01T00:00:00Z",
          "legs": [{"label": "New York Knicks ML", "p": 0.62}, {"label": "Jalen Brunson 3+ threes", "p": 0.55}]},
         {"event_id": "e2", "matchup": "Tulane @ Charlotte", "commence_time": "2099-01-02T00:00:00Z",
          "legs": [{"label": "Tulane Green Wave -10.5", "p": 0.52}, {"label": "Tulane Green Wave -3.5", "p": 0.7}]}]
CARD = {"picks": [{"pick_id": "p1", "p_market": 0.6, "commence_time": "2099-01-01T00:00:00Z"}]}
M = C.Market(CARD, PACKS)


def test_a_pick_on_the_card_uses_its_offer():
    got = C.estimate({"pick_id": "p1", "price": -110}, M, {})
    assert got["clv"] == pytest.approx(0.6 * (1 + 100 / 110) - 1, abs=1e-4)


def test_a_single_finds_its_leg_in_its_games_pack_in_any_wording():
    b = {"price": 111, "legs": ["Tulane -10.5"], "games": [{"matchup": "Tulane @ Charlotte", "legs": ["Tulane -10.5"]}]}
    assert C.estimate(b, M, {})["clv"] == pytest.approx(0.52 * 2.11 - 1, abs=1e-4)
    over = {"price": 120, "legs": ["Jalen Brunson over 2.5 threes"], "matchup": "New York Knicks @ Chicago Bulls", "odds_event_id": "e1"}
    assert C.estimate(over, M, {})["p_now"] == 0.55                       # "over 2.5" is the pack's "3+"


def test_an_app_parlay_moves_its_fair_chance_by_each_legs_change():
    t = {"t1": {"games": [{"event_id": "e1", "legs": [{"label": "New York Knicks ML", "p_fair": 0.6},
                                                     {"label": "Jalen Brunson 3+ threes", "p_fair": 0.5}]}]}}
    got = C.estimate({"sgp_id": "t1", "price": 300, "p_fair": 0.28}, M, t)
    assert got["p_now"] == pytest.approx(0.28 * (0.62 / 0.6) * (0.55 / 0.5), abs=1e-4)
    assert got["clv"] == pytest.approx(got["p_now"] * 4 - 1, abs=1e-3)


def test_a_slip_parlay_needs_every_leg_in_a_different_game():
    cross = {"price": 200, "games": [{"matchup": "New York Knicks @ Chicago Bulls", "legs": ["New York Knicks ML"]},
                                     {"matchup": "Tulane @ Charlotte", "legs": ["Tulane -10.5"]}]}
    assert C.estimate(cross, M, {})["p_now"] == pytest.approx(0.62 * 0.52, abs=1e-4)
    same = {"price": 300, "games": [{"matchup": "New York Knicks @ Chicago Bulls", "legs": ["New York Knicks ML", "Jalen Brunson 3+ threes"]}]}
    assert C.estimate(same, M, {}) is None                                 # no correlation to start from
    unknown = {"price": 100, "games": [{"matchup": "Tulane @ Charlotte", "legs": ["Somebody 1+ goals"]}]}
    assert C.estimate(unknown, M, {}) is None


NHL = C.Market({}, [{"event_id": "n1", "matchup": "STL @ NYR", "commence_time": "2099-01-01T00:00:00Z",
                     "legs": [{"label": "NYR to win", "p": 0.58}, {"label": "STL to win", "p": 0.42}, {"label": "NYR -1.5", "p": 0.3},
                              {"label": "Over 5.5 goals", "p": 0.55}]},
                    {"event_id": "n2", "matchup": "EDM @ NJD", "commence_time": "2099-01-01T00:40:00Z",
                     "legs": [{"label": "NJD to win", "p": 0.6}]}])


def test_an_nhl_slips_full_names_find_the_packs_codes():
    b = {"price": 150, "games": [{"matchup": "STL @ NYR", "legs": ["New York Rangers ML"]},
                                 {"matchup": "EDM @ NJD", "legs": ["New Jersey Devils ML"]}]}
    assert C.estimate(b, NHL, {})["p_now"] == pytest.approx(0.58 * 0.6, abs=1e-4)
    assert NHL.leg("St. Louis Blues ML", None, "St. Louis Blues @ New York Rangers")[0] == 0.42   # a matchup in full names too
    assert NHL.leg("New York Rangers -1.5", None, "STL @ NYR")[0] == 0.3
    assert NHL.leg("New York Rangers +1.5", None, "STL @ NYR") is None      # never the other number
    assert NHL.leg("Pittsburgh Penguins ML", None, "STL @ NYR") is None     # never a team not in the game
    assert NHL.leg("New York Rangers ML", None, "PIT @ BUF") is None        # nor another game


def test_a_moneyline_is_the_same_bet_as_to_win():
    m = C.Market({}, [{"event_id": "s1", "matchup": "AS Roma @ Manchester United", "commence_time": "2099-01-01T00:00:00Z",
                       "legs": [{"label": "Manchester United to win", "p": 0.46}]}])
    assert m.leg("Manchester United ML", None, "AS Roma @ Manchester United")[0] == 0.46

