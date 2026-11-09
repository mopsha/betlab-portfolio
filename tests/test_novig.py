"""Novig's public catalog (Oct 22): its soccer prices as snapshot rows, matched to the pulled events."""

import pandas as pd
import pytest

from betlab.sources import novig

EVENT = {"id": "e1", "home_team": "Ipswich Town", "away_team": "Nottingham Forest", "commence_time": "2026-10-23T19:00:00Z"}
START = int(pd.Timestamp("2026-10-23T19:00:00Z").timestamp() * 1000)


def _yes_no(kind, desc, yes_bid, no_bid, no_qty=100_000):
    return {"marketType": kind, "description": desc, "status": "OPEN", "outcomes": [
        {"outcomeId": f"{desc}-yes", "name": "Yes", "bid": {"price": str(yes_bid), "qty": 50_000}},
        {"outcomeId": f"{desc}-no", "name": "No", "bid": {"price": str(no_bid), "qty": no_qty}}]}


MARKETS = [
    _yes_no("MONEYLINE_3_WAY_WIN", "Nottm Forest MONEYLINE_3_WAY_WIN", 0.42, 0.575, 177_267),
    _yes_no("MONEYLINE_3_WAY_WIN", "Ipswich Town MONEYLINE_3_WAY_WIN", 0.29, 0.70),
    _yes_no("MONEYLINE_3_WAY_DRAW", "Nottm Forest @ Ipswich Town MONEYLINE_3_WAY_DRAW", 0.275, 0.715),
    {"marketType": "TOTAL", "strike": "2.5", "status": "OPEN", "description": "t2.5", "outcomes": [
        {"outcomeId": "o", "name": "Over 2.5", "bid": {"price": "0.54", "qty": 28_400}},
        {"outcomeId": "u", "name": "Under 2.5", "bid": {"price": "0.45", "qty": 49_656}}]},
]


def test_team_names_match_across_novig_and_the_feed():
    assert novig._same_team("Nottm Forest", "Nottingham Forest")
    assert novig._same_team("Ipswich Town FC", "Ipswich Town")
    assert novig._same_team("Bayern München", "Bayern Munich")
    assert not novig._same_team("Inter Miami", "Inter Milan")
    assert not novig._same_team("Manchester City", "Manchester United")


def test_an_event_matches_by_both_teams_and_the_start():
    listed = [{"eventId": "n1", "description": "Nottingham Forest FC @ Ipswich Town FC", "startsTs": START},
              {"eventId": "n2", "description": "Nottingham Forest FC @ Ipswich Town FC", "startsTs": START + 86_400_000}]
    assert novig.match(EVENT, listed)["eventId"] == "n1"
    assert novig.match(EVENT, listed[1:]) is None                     # a day off is another match


def test_rows_buy_at_one_minus_the_other_sides_bid():
    rows = pd.DataFrame(novig.rows_for(EVENT, MARKETS, "soccer_epl", "2026-10-23T12:00:00Z"))
    h2h = rows[rows.market == "h2h"].set_index("outcome")
    assert set(h2h.index) == {"Nottingham Forest", "Ipswich Town", "Draw"}
    # Forest to win: 1 - 0.575 = 42.5% (+135); $753 behind it (1,772.67 contracts at 42.5 cents)
    assert h2h.loc["Nottingham Forest", "price"] == 135 and h2h.loc["Nottingham Forest", "bet_limit"] == pytest.approx(753.39, abs=0.01)
    assert h2h.loc["Nottingham Forest", "link"] == "https://novig.com/events/Nottm Forest MONEYLINE_3_WAY_WIN-yes/oddsapi/{wager}"
    tot = rows[rows.market == "totals"].set_index("outcome")
    assert tot.loc["Over", "point"] == 2.5 and tot.loc["Over", "price"] == round(-100 * 0.55 / 0.45)   # 55% to buy over
    assert (rows.bookmaker == "novig").all() and (rows.event_id == "e1").all()


def test_a_three_way_result_missing_a_side_is_left_out():
    rows = novig.rows_for(EVENT, MARKETS[1:], "soccer_epl", "t")
    assert not [r for r in rows if r["market"] == "h2h"] and [r for r in rows if r["market"] == "totals"]


def test_a_pull_that_already_has_novig_is_left_alone(monkeypatch):
    df = pd.DataFrame([{"event_id": "e1", "bookmaker": "novig", "home_team": "A", "away_team": "B",
                        "commence_time": "2030-01-01T00:00:00Z"}])
    monkeypatch.setattr(novig, "events", lambda sport="SOCCER": (_ for _ in ()).throw(AssertionError("no catalog read")))
    assert novig.add_rows(df, "soccer_epl", "t") is df
