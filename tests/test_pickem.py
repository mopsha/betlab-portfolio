"""FanDuel's College Football Pick'em (Nov 7): matching FanDuel's short names to the week's games, the side at the frozen
line, grading, the flips worth an alert. The worker's run() (database, ESPN, alerts) isn't tested here."""

import pandas as pd
import pytest

from betlab import pickem as P


EVS = [{"event_id": "e1", "home": "Northwestern Wildcats", "away": "Iowa Hawkeyes", "start": "2026-11-08T00:30:00Z"},
       {"event_id": "e2", "home": "Notre Dame Fighting Irish", "away": "Miami Hurricanes", "start": "2026-11-08T00:30:00Z"},
       {"event_id": "e3", "home": "Miami (OH) RedHawks", "away": "Ohio Bobcats", "start": "2026-11-11T01:00:00Z"},
       {"event_id": "e4", "home": "Missouri Tigers", "away": "Texas Longhorns", "start": "2026-11-07T17:00:00Z"},
       {"event_id": "e5", "home": "Texas Tech Red Raiders", "away": "West Virginia Mountaineers", "start": "2026-11-08T02:30:00Z"},
       {"event_id": "e6", "home": "Ole Miss Rebels", "away": "Georgia Bulldogs", "start": "2026-11-08T00:30:00Z"}]


@pytest.mark.parametrize("first, second, eid, swapped", [
    ("#19 Iowa", "Northwestern", "e1", False),          # away listed first, as FanDuel does
    ("Northwestern", "#19 Iowa", "e1", True),           # the other way round: the worker swaps
    ("#1 Miami", "#11 Notre Dame", "e2", False),        # Miami, not Miami (OH): both names must fit one game
    ("Ohio", "Miami", "e3", False),
    ("#7 Texas", "#18 Missouri", "e4", False),          # Texas Longhorns before Texas Tech: the closer fit
    ("West Virginia", "Texas Tech", "e5", False),
    ("#2 Georgia", "#10 Ole Miss", "e6", False),
])
def test_a_pair_of_short_names_finds_its_game(first, second, eid, swapped):
    ev, sw = P.match_event(EVS, first, second)
    assert ev["event_id"] == eid and sw is swapped


def test_a_pair_that_fits_no_game_is_none():
    assert P.match_event(EVS, "Alabama", "LSU") is None
    assert P.match_event(EVS, "Texas", "Iowa") is None            # each fits a game, not the same one


def test_the_week_is_the_coming_saturday():
    sat = pd.Timestamp("2026-11-07T15:00:00Z")                      # Saturday 10 AM ET
    assert P.week_of(sat) == pd.Timestamp("2026-11-07").date()
    assert P.week_of(pd.Timestamp("2026-11-08T05:00:00Z")) == pd.Timestamp("2026-11-14").date()   # Sunday 12 AM ET
    assert P.week_of(pd.Timestamp("2026-11-11T14:00:00Z")) == pd.Timestamp("2026-11-14").date()   # Wednesday


def test_the_frozen_line_settles_on_the_final():
    assert P.settle(-2.5, 24, 20) == "home"       # home -2.5, won by 4
    assert P.settle(-2.5, 21, 20) == "away"       # won by 1
    assert P.settle(5.5, 20, 24) == "home"        # home +5.5, lost by 4
    assert P.settle(-3, 23, 20) == "push"


def test_the_final_comes_from_espn_once_the_game_is_post():
    board = [{"state": "post", "home": {"name": "Northwestern Wildcats", "abbr": "NW", "score": "27"},
              "away": {"name": "Iowa Hawkeyes", "abbr": "IOWA", "score": "24"}},
             {"state": "in", "home": {"name": "Notre Dame Fighting Irish", "abbr": "ND", "score": "7"},
              "away": {"name": "Miami Hurricanes", "abbr": "MIA", "score": "3"}}]
    assert P.final_score(board, "Northwestern Wildcats", "Iowa Hawkeyes") == (27, 24)
    assert P.team_logos(board, "Northwestern Wildcats", "Iowa Hawkeyes") == (None, None)
    assert P.final_score(board, "Notre Dame Fighting Irish", "Miami Hurricanes") is None
    assert P.final_score(board, "Ole Miss Rebels", "Georgia Bulldogs") is None


def test_our_side_is_the_likelier_one_and_none_under_new_york_rules():
    assert P.our_side(0.606, "Northwestern Wildcats", "Iowa Hawkeyes") == ("home", None)
    assert P.our_side(0.47, "Northwestern Wildcats", "Iowa Hawkeyes") == ("away", None)
    assert P.our_side(None, "Northwestern Wildcats", "Iowa Hawkeyes")[0] is None
    side, why = P.our_side(0.6, "Syracuse Orange", "Pittsburgh Panthers")
    assert side is None and "New York" in why


def test_flips_and_the_score():
    rows = [{"home": "Northwestern", "away": "Iowa", "home_line": -2.5, "pick": "home", "ours": "away", "p_home": 0.394},
            {"home": "LSU", "away": "Alabama", "home_line": -5.5, "pick": "away", "ours": "home", "p_home": 0.51},
            {"home": "Utah", "away": "BYU", "home_line": -4.5, "pick": "home", "ours": "home", "p_home": 0.511},
            {"home": "Ole Miss", "away": "Georgia", "home_line": 3.5, "pick": None, "ours": "away", "p_home": 0.5}]
    to_flip, unpicked = P.flips(rows)
    assert [r["away"] for r in to_flip] == ["Iowa"]                # LSU at 51% isn't worth an alert
    assert [r["home"] for r in unpicked] == ["Ole Miss"]
    assert P.side_label(rows[0], "away") == "Iowa +2.5" and P.side_label(rows[1], "home") == "LSU -5.5"
    graded = [dict(r, result=res) for r, res in zip(rows, ["away", "home", "push", "away"])]
    assert P.score(graded) == {"games": 4, "picked": 3, "graded": 4, "yours": 1, "ours": 4}


def test_pricing_the_frozen_line_against_the_sharp_market():
    """Nov 7: Iowa @ Northwestern froze at Northwestern -2.5 on Wednesday; by Saturday Pinnacle had Iowa -3."""
    from betlab.cards import ncaaf
    p, md, _ = ncaaf.load_model(ncaaf.LEAGUE.load_games())
    snap = pd.DataFrame([
        {"event_id": "e1", "home_team": "Northwestern Wildcats", "away_team": "Iowa Hawkeyes", "bookmaker": "pinnacle",
         "market": "spreads", "outcome": "Northwestern Wildcats", "point": 3.0, "price": -110},
        {"event_id": "e1", "home_team": "Northwestern Wildcats", "away_team": "Iowa Hawkeyes", "bookmaker": "pinnacle",
         "market": "spreads", "outcome": "Iowa Hawkeyes", "point": -3.0, "price": -102}])
    px = P.price(snap, "Northwestern Wildcats", "Iowa Hawkeyes", -2.5, md, p.market_margin_sd, ["pinnacle"])
    assert 0.35 < px["p_home"] < 0.45 and px["fair_line"] == pytest.approx(2.8, abs=0.3) and px["source"] == "pinnacle"
    assert P.price(snap.iloc[:0], "Northwestern Wildcats", "Iowa Hawkeyes", -2.5, md, p.market_margin_sd, ["pinnacle"]) is None


def test_the_shared_fixture():
    """tests/fixtures/pickem.json: the same cases in the web (pickem.ts) and the iPhone app (Pickem.swift)."""
    import json
    from pathlib import Path

    fx = json.loads(Path(__file__).with_name("fixtures").joinpath("pickem.json").read_text())
    rows = fx["rows"]
    assert P.score(rows) == fx["score"]
    to_flip, unpicked = P.flips(rows)
    assert [P.side_label(r, r["ours"]) for r in to_flip] == fx["flips"]
    assert [r["n"] for r in unpicked] == fx["unpicked"]
    for key, label in fx["labels"].items():
        n, side = key.split(":")
        assert P.side_label(next(r for r in rows if r["n"] == int(n)), side) == label
