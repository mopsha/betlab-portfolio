"""NHL player props pricing (cards/props_nhl.py)."""


def test_anytime_scorer_is_priced_against_pinnacle():
    """Oct 10 (Mike): NHL anytime goal scorer. FanDuel posts Yes only; Pinnacle's two-way no-vig is the fair
    chance; the offer is a prop 'Yes' (picks from the normal prop rules)."""
    import pandas as pd

    from betlab.cards import props_nhl as PN

    base = {"event_id": "g1", "commence_time": "2026-10-10T23:00:00Z", "market": PN.SCORER, "player": "Jack Hughes",
            "point": None}
    props = pd.DataFrame([base | {"bookmaker": "fanduel", "outcome": "Yes", "price": 130.0},
                          base | {"bookmaker": "pinnacle", "outcome": "Yes", "price": 105.0},
                          base | {"bookmaker": "pinnacle", "outcome": "No", "price": -125.0}])
    games = {"g1": {"matchup": "VAN @ NJD", "commence_time": "2026-10-10T23:00:00Z", "game_ref": "2026020100",
                    "home": "NJD", "away": "VAN", "read": {}}}
    offers, track = PN.price(props, pd.Timestamp("2026-10-10T22:30:00Z"), games, pd.DataFrame(), None, {}, {})
    assert len(offers) == 1 and offers.iloc[0]["side"] == "Yes" and offers.iloc[0]["label"] == "Jack Hughes to score"
    assert 0.45 < offers.iloc[0]["p_market"] < 0.5 and offers.iloc[0]["market_source"] == "Pinnacle no-vig"
    assert track[0]["stat"] == "goals" and track[0]["line"] == 0.5 and track[0]["fd_over"] == 130.0


def test_lines_carry_the_odds_feeds_puck_drop():
    """Oct 10: the NHL lists a 6:10 PM puck drop as 6:00, so the 6:00 tick dropped that game's lines as started.
    Tracked lines and offers now carry the odds feed's commence time."""
    import pandas as pd

    from betlab.cards import props_nhl as PN

    base = {"event_id": "g1", "commence_time": "2026-10-10T22:10:00Z", "market": "player_shots_on_goal",
            "player": "Sam Reinhart", "point": 2.5}
    props = pd.DataFrame([base | {"bookmaker": "fanduel", "outcome": "Over", "price": -120.0},
                          base | {"bookmaker": "fanduel", "outcome": "Under", "price": -110.0}])
    games = {"g1": {"matchup": "MIN @ FLA", "commence_time": "2026-10-10T22:00Z", "game_ref": "2026020120",
                    "home": "FLA", "away": "MIN", "read": {}}}
    _, track = PN.price(props, pd.Timestamp("2026-10-10T22:00:11Z"), games, pd.DataFrame(), None, {}, {})
    assert track[0]["commence_time"] == "2026-10-10T22:10:00Z"
