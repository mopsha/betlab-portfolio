"""Novig challenges (Oct 28): Novig's words parsed, a bet ripe at the right time, the live-price rule. No network."""

import pandas as pd
import pytest

from betlab import challenges as C

ET = "America/New_York"


@pytest.mark.parametrize("text, want", [
    ("Place a straight trade on CFB (Min. $5)", {"kind": "straight", "sport": "ncaaf", "market": None, "min_stake": 5.0}),
    ("Place a parlay on Pro BB (M) (Min. 3 legs, 4.00x, $5)",
     {"kind": "parlay", "sport": "nba", "min_legs": 3, "min_dec": 4.0, "min_stake": 5.0}),
    ("Place a straight trade on Hockey Player Goals (Min. $5)", {"kind": "straight", "sport": "nhl", "market": "player_goals"}),
    ("Place a parlay on Pro BB (W) (Min. 2 legs, 3.00x, $10)", {"sport": "wnba", "min_legs": 2, "min_dec": 3.0, "min_stake": 10.0}),
    ("Place a straight trade on College BB (M) Spread (Min. $5)", {"sport": "ncaab", "market": "spreads"}),
    ("Place a straight trade on Pro FB (Min. $5)", {"sport": "nfl"}),
])
def test_novigs_words_become_rules(text, want):
    got = C.parse(text)
    assert {k: got[k] for k in want} == want


def at(hhmm: str, day: str = "2026-10-28") -> pd.Timestamp:
    return pd.Timestamp(f"{day} {hhmm}", tz=ET).tz_convert("UTC")


def bet(eid, start, ev, label="X"):
    return {"event_id": eid, "start": start, "ev": ev, "label": label}


def test_a_straight_is_ripe_after_its_news_and_at_the_hours_bar():
    tonight = at("19:00").isoformat()
    bets = [bet("a", tonight, 0.02), bet("b", tonight, 0.005)]
    rules = {"kind": "straight"}
    assert C.decide(rules, bets, set(), at("13:00")) == (None, bets[0])          # news not in: watching
    assert C.decide(rules, bets, {"a"}, at("13:00"))[0] is bets[0]                 # +2% clears the early bar
    assert C.decide(rules, [bet("b", tonight, 0.005), bet("c", tonight, 0.0)], {"b"}, at("13:00"))[0] is None
    assert C.decide(rules, [bet("b", tonight, 0.005)], {"b"}, at("17:30"))[0]["event_id"] == "b"   # evening bar: 0


def test_only_todays_games_and_nothing_better_coming_takes_the_best():
    """Oct 28 (Mike): "from now on novig bets are only for day of events"."""
    legs = [{"start": at("19:00", "2026-10-30").isoformat(), "label": "Thursday"}, {"start": at("19:00").isoformat(), "label": "tonight"},
            {"start": at("00:30", "2026-10-29").isoformat(), "label": "after midnight"}]
    assert [l["label"] for l in C.today_only(legs, at("10:00"))] == ["tonight"]
    tonight = at("19:00").isoformat()
    only = [bet("a", tonight, -0.01)]
    assert C.decide({"kind": "straight"}, only, {"a"}, at("13:00"))[0] is only[0]  # nothing unready left
    assert C.decide({"kind": "parlay"}, [bet("a", at("23:30").isoformat(), -0.2)], {"a"}, at("22:15"))[0] is not None


def test_a_bet_starting_within_15_minutes_is_never_ripe():
    soon = at("13:10").isoformat()
    assert C.decide({"kind": "straight"}, [bet("a", soon, 0.05)], {"a"}, at("13:00")) == (None, {"event_id": "a", "start": soon, "ev": 0.05, "label": "X"})


def test_a_parlay_is_ripe_only_when_every_games_news_is_in():
    tonight = at("19:00").isoformat()
    p = {"events": ["a", "b"], "legs": [{"start": tonight}, {"start": tonight}], "start": tonight, "ev": -0.02, "label": "P"}
    assert C.decide({"kind": "parlay"}, [p], {"a"}, at("14:00"))[0] is None
    assert C.decide({"kind": "parlay"}, [p], {"a", "b"}, at("14:00"))[0] is p


def test_a_live_price_counts_at_the_worse_of_it_and_the_pull():
    """Oct 28: Middle Tennessee -2.5 went -102 to +122 against the morning's Pinnacle line: no fake +15%."""
    b = {"event_id": "e", "oid": "o1", "price": -102.0, "p": 0.518, "ev": 0.026, "label": "MTSU -2.5"}
    got = C.live([b], 5.0, asks={"o1": (100 / 222, 500.0)})[0]
    assert got["price"] == 122 and got["ev"] == pytest.approx(0.518 * (1 + 100 / 102) - 1)
    worse = C.live([b], 5.0, asks={"o1": (0.6, 500.0)})[0]                       # -150 now: counted at -150
    assert worse["ev"] == pytest.approx(0.518 / 0.6 - 1, abs=0.01)
    assert C.live([b], 5.0, asks={"o1": (0.5, 3.0)}) == []                       # $3 behind it: not a $5 trade
    assert C.live([b], 5.0, asks={}) == []


def test_parlays_take_different_games_and_reach_the_minimum_at_novigs_own_price():
    leg = lambda oid, game, teams, p, ev: {"oid": oid, "game": game, "teams": set(teams), "p": p, "ev": ev, "label": oid,
                                           "start": "2099-01-01T00:00:00Z", "price": -150.0, "event_id": game}
    legs = [leg("a", "g1", "AB", 0.62, 0.01), leg("b", "g2", "CD", 0.62, 0.0), leg("c", "g3", "EF", 0.62, 0.0),
            leg("d", "g1", "AB", 0.7, 0.02), leg("e", "g4", "AG", 0.6, 0.0)]          # e shares team A with g1
    asked = []

    def price_all(sets):
        asked.extend(sets)
        return {",".join(s): {"p": 0.24, "price": 317, "stake_max": 50.0} for s in sets}
    out = C.parlays(legs, 3, 4.0, price_all)
    assert out and all(len({l["event_id"] for l in o["legs"]}) == 3 for o in out)
    assert not any({"a", "e"} <= set(s) or {"d", "e"} <= set(s) or {"a", "d"} <= set(s) for s in asked)
    assert out[0]["price"] == 317 and out[0]["dec"] == pytest.approx(1 / 0.24, abs=0.001)
    assert C.parlays(legs, 3, 4.0, lambda sets: {",".join(s): {"p": 0.26, "price": 285} for s in sets}) == []   # 3.85x
