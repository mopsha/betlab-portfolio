"""FanDuel betslip links: each bet gets its one FanDuel outcome, or none (never a wrong one)."""

import pandas as pd

from betlab import links

ROWS = pd.DataFrame([
    {"event_id": "e1", "market": "h2h", "outcome": "Philadelphia Flyers", "player": None, "point": None, "price": -110.0, "link": "L-PHI"},
    {"event_id": "e1", "market": "h2h", "outcome": "Pittsburgh Penguins", "player": None, "point": None, "price": -110.0, "link": "L-PIT"},
    {"event_id": "e1", "market": "totals", "outcome": "Over", "player": None, "point": 6.5, "price": -110.0, "link": "L-O65"},
    {"event_id": "e1", "market": "player_shots_on_goal", "outcome": "Over", "player": "Sidney Crosby", "point": 2.5, "price": 120.0, "link": "L-SC"},
])


def test_matches_by_price_number_player_and_side(monkeypatch):
    monkeypatch.setattr(links, "_CODES", {"philadelphia flyers": "PHI", "pittsburgh penguins": "PIT"})
    m = links.Matcher(ROWS)
    assert m.find("e1", -110, None, None, "yes", "PHI ML") == "L-PHI"           # same price both sides: the team decides
    assert m.find("e1", -110, 0.0, None, "yes", "PIT to win") == "L-PIT"        # a builder leg's 0 matches a blank number
    assert m.find("e1", -110, 6.5, None, "over", "Over 6.5 goals") == "L-O65"
    assert m.find("e1", 120, 2.5, "Sidney Crosby", "over", "Sidney Crosby over 2.5 shots") == "L-SC"
    assert m.find("e1", -105, 6.5, None, "over", "Over 6.5 goals") is None       # FanDuel's price moved: no link
    assert m.find("e2", -110, None, None, "yes", "PHI ML") is None


def test_attach_fun_reaches_tickets_overs_and_packs():
    m = links.Matcher(ROWS)
    doc = {"slates": [{"plus": {"games": [{"event_id": "e1", "legs": [{"label": "Over 6.5 goals", "price": -110, "point": 6.5, "side": "over"}]}]},
                       "overs": [{"event_id": "e1", "label": "Sidney Crosby over 2.5 shots", "price": 120, "point": 2.5,
                                  "player": "Sidney Crosby", "side": "over"}],
                       "packs": [{"event_id": "e1", "legs": [{"label": "Over 6.5 goals", "price": -110, "point": 6.5, "side": "over"}]}]}]}
    assert links.attach_fun(doc, m) == 3
    assert doc["slates"][0]["overs"][0]["link"] == "L-SC"


def test_game_legs_ignore_the_placeholder_player(monkeypatch):
    monkeypatch.setattr(links, "_CODES", {})
    rows = pd.DataFrame([{"event_id": "e9", "market": "spreads", "outcome": "SMU Mustangs", "player": None, "point": -20.5, "price": -110.0, "link": "L-SMU"},
                         {"event_id": "e9", "market": "spreads", "outcome": "Boston College Eagles", "player": None, "point": 20.5, "price": -110.0, "link": "L-BC"}])
    leg = {"label": "SMU Mustangs -20.5", "player": "game side", "stat": "spread", "side": "yes", "point": -20.5, "price": -110}
    links._leg(links.Matcher(rows), leg, "e9")
    assert leg["link"] == "L-SMU"


def test_main_line_and_ladder_rung_at_the_same_price():
    rows = pd.DataFrame([
        {"event_id": "e5", "market": "player_receptions", "outcome": "Over", "player": "DK Metcalf", "point": 3.5, "price": -122.0, "link": "L-MAIN"},
        {"event_id": "e5", "market": "player_receptions_alternate", "outcome": "Over", "player": "DK Metcalf", "point": 3.5, "price": -122.0, "link": "L-ALT"}])
    m = links.Matcher(rows)
    # always the ladder's rung: a main market's link follows its line when it moves (Oct 30, Brunson 1.5 -> 2.5)
    assert m.find("e5", -122, 3.5, "DK Metcalf", "over", "DK Metcalf over 3.5 receptions") == "L-ALT"
    assert m.find("e5", -122, 3.5, "DK Metcalf", "over", "DK Metcalf 4+ receptions") == "L-ALT"


def test_a_moved_main_line_never_links_a_ladder_leg_to_another_number():
    """Oct 30: FanDuel's main Brunson threes market (one id) was 1.5 at 6:45 and 2.5 by 6:52; the ticket's over 1.5
    took the main market's link, and it opened as Over 2.5. The ladder's 1.5 rung (its own id) is the link."""
    rows = pd.DataFrame([
        {"event_id": "n1", "market": "player_threes", "outcome": "Over", "player": "Jalen Brunson", "point": 1.5, "price": -186.0, "link": "MAIN"},
        {"event_id": "n1", "market": "player_threes_alternate", "outcome": "Over", "player": "Jalen Brunson", "point": 1.5, "price": -186.0, "link": "ALT-15"},
        {"event_id": "n1", "market": "player_threes_alternate", "outcome": "Over", "player": "Jalen Brunson", "point": 2.5, "price": 172.0, "link": "ALT-25"}])
    leg = {"label": "Jalen Brunson over 1.5 threes", "stat": "threes", "player": "Jalen Brunson", "side": "over", "point": 1.5, "price": -186}
    links._leg(links.Matcher(rows), leg, "n1")
    assert leg["link"].endswith("ALT-15") and "link_main" not in leg


def test_a_main_market_only_link_is_flagged_and_a_moneyline_is_not(monkeypatch):
    """Mike, Oct 30 ("Keep, flag them"): an under or a combo FanDuel lists only in its main market keeps its link,
    marked `link_main` so the apps say to check the line; a moneyline has no number to move."""
    monkeypatch.setattr(links, "_CODES", {})
    rows = pd.DataFrame([
        {"event_id": "n1", "market": "player_points_rebounds_assists", "outcome": "Under", "player": "Jalen Brunson", "point": 38.5, "price": -110.0, "link": "PRA"},
        {"event_id": "n1", "market": "h2h", "outcome": "New York Knicks", "player": None, "point": None, "price": -150.0, "link": "ML"}])
    m = links.Matcher(rows)
    pra = {"label": "Jalen Brunson under 38.5 pts+reb+ast", "stat": "pra", "player": "Jalen Brunson", "side": "under", "point": 38.5, "price": -110}
    ml = {"label": "New York Knicks ML", "stat": "moneyline", "side": "yes", "point": 0.0, "price": -150}
    links._leg(m, pra, "n1")
    links._leg(m, ml, "n1")
    assert pra["link"].endswith("PRA") and pra["link_main"] is True
    assert ml["link"].endswith("ML") and "link_main" not in ml
    t = {"games": [{"legs": [pra, ml]}], "legs": [dict(pra, link=None, link_main=None), dict(ml)]}
    links.copy_flat_links(t)
    assert t["legs"][0]["link_main"] is True and "link_main" not in t["legs"][1]


def test_links_go_to_the_new_york_host():
    """The bare host shows FanDuel's "pick your state" screen; the ny. subdomain skips it (Oct 1)."""
    u = "https://sportsbook.fanduel.com/addToBetslip?marketId=42.6&selectionId=25"
    assert links.ny_link(u) == "https://ny.sportsbook.fanduel.com/addToBetslip?marketId=42.6&selectionId=25"
    assert links.ny_link(links.ny_link(u)) == links.ny_link(u)
    assert links.ny_link("https://nj.sportsbook.fanduel.com/x").startswith("https://ny.sportsbook.fanduel.com/")


def test_a_parlay_leg_keeps_its_link_when_the_price_moves(monkeypatch):
    """Oct 9 rehearsal: SGP+ moneyline legs built in the morning lost their links once FanDuel's price moved
    (an NHL ticket showed 'Open in FanDuel 1/4'). Parlay legs match the selection; straight bets still don't."""
    monkeypatch.setattr(links, "_CODES", {"philadelphia flyers": "PHI", "pittsburgh penguins": "PIT"})
    m = links.Matcher(ROWS)
    assert m.find("e1", -122, 0.0, None, "yes", "PHI to win") is None                       # a straight bet: no
    assert m.find("e1", -122, 0.0, None, "yes", "PHI to win", any_price=True) == "L-PHI"   # a parlay leg: yes
    assert m.find("e1", -105, 6.5, None, "over", "Over 6.5 goals", any_price=True) == "L-O65"
    assert m.find("e1", -105, 7.5, None, "over", "Over 7.5 goals", any_price=True) is None  # a different line: never
    leg = {"label": "PIT to win", "stat": "moneyline", "price": -130, "point": 0.0, "side": "yes"}
    links._leg(m, leg, "e1")
    assert leg["link"] == "L-PIT"


def test_soccer_ticket_legs_link_from_the_goals_pull(monkeypatch):
    """Oct 10 (Mike: soccer bets in one button): goals and both-teams-to-score legs have no FanDuel price
    (the bulk feed lacks them), so they match by selection in the event pull's alt goals ladder and btts."""
    monkeypatch.setattr(links, "_CODES", {})
    rows = pd.DataFrame([
        {"event_id": "s1", "market": "h2h", "outcome": "Minnesota United FC", "player": None, "point": None, "price": 140.0, "link": "L-MIN"},
        {"event_id": "s1", "market": "h2h", "outcome": "Draw", "player": None, "point": None, "price": 260.0, "link": "L-DRAW"},
        {"event_id": "s1", "market": "h2h", "outcome": "Houston Dynamo", "player": None, "point": None, "price": 175.0, "link": "L-HOU"},
        {"event_id": "s1", "market": "btts", "outcome": "Yes", "player": None, "point": None, "price": -156.0, "link": "L-BY"},
        {"event_id": "s1", "market": "btts", "outcome": "No", "player": None, "point": None, "price": 122.0, "link": "L-BN"},
        {"event_id": "s1", "market": "alternate_totals", "outcome": "Over", "player": None, "point": 2.5, "price": -122.0, "link": "L-O25"},
        {"event_id": "s1", "market": "alternate_totals", "outcome": "Under", "player": None, "point": 2.5, "price": 100.0, "link": "L-U25"},
        {"event_id": "s1", "market": "alternate_totals", "outcome": "Over", "player": None, "point": 3.5, "price": 210.0, "link": "L-O35"},
    ])
    m = links.Matcher(rows)

    def link(**leg):
        leg = {"player": None, "point": 0.0, "price": None, "side": "yes"} | leg
        links._leg(m, leg, "s1")
        return leg.get("link")

    assert link(label="Both teams to score", stat="btts") == "L-BY"
    assert link(label="Both teams to score: no", stat="btts", side="no") == "L-BN"
    assert link(label="Over 2.5 goals", stat="goals", side="over", point=2.5) == "L-O25"
    assert link(label="Under 2.5 goals", stat="goals", side="under", point=2.5) == "L-U25"
    assert link(label="Over 1.5 goals", stat="goals", side="over", point=1.5) is None       # not pulled: no link
    assert link(label="Minnesota United FC to win", stat="moneyline", price=140.0) == "L-MIN"  # never btts' "Yes"
    assert link(label="Draw", stat="draw", point=None, price=260.0) == "L-DRAW"
    assert link(label="Minnesota United FC or draw", stat="double chance") is None          # never another market
    assert m.find("s1", None, 2.5, None, "over", "Over 2.5 goals") is None                  # a straight bet needs a price


def test_soccer_game_legs_never_match_a_players_prop_or_another_market():
    """Oct 12: soccer tickets opened wrong bets. "RB Leipzig to win" -190 matched a player's shots line at
    -190, "Over 2.5 goals" also matched players' over 2.5 shots (so got no link), and a winner matched
    both-teams-to-score Yes in a pull without the winner market."""
    rows = pd.DataFrame([
        {"event_id": "s1", "market": "h2h", "outcome": "RB Leipzig", "player": None, "point": None, "price": -190.0, "link": "L-WIN"},
        {"event_id": "s1", "market": "alternate_totals", "outcome": "Over", "player": None, "point": 2.5, "price": -385.0, "link": "L-O25"},
        {"event_id": "s1", "market": "player_shots", "outcome": "Over", "player": "Xavi Simons", "point": 2.5, "price": -190.0, "link": "L-SHOTS"},
        {"event_id": "s1", "market": "btts", "outcome": "Yes", "player": None, "point": None, "price": 100.0, "link": "L-BTTS"},
        {"event_id": "s2", "market": "btts", "outcome": "Yes", "player": None, "point": None, "price": 100.0, "link": "L-BTTS2"},
    ])
    m = links.Matcher(rows)
    win = {"label": "RB Leipzig to win", "stat": "moneyline", "side": "yes", "point": 0.0, "price": -190.0}
    over = {"label": "Over 2.5 goals", "stat": "goals", "side": "over", "point": 2.5, "price": None}
    links._leg(m, win, "s1"); links._leg(m, over, "s1")
    assert win["link"] == "L-WIN" and over["link"] == "L-O25"
    only_btts = {"label": "Inter Milan to win", "stat": "moneyline", "side": "yes", "point": 0.0, "price": 100.0}
    links._leg(m, only_btts, "s2")
    assert "link" not in only_btts                     # no winner market in the pull: no link, never BTTS Yes


def test_a_tickets_flat_legs_take_their_own_matchs_link():
    """The same label in two matches ("Both teams to score") must not share one match's link."""
    t = {"games": [{"legs": [{"label": "Both teams to score", "link": "A"}, {"label": "Over 2.5 goals", "link": "A2"}]},
                   {"legs": [{"label": "Both teams to score", "link": "B"}, {"label": "Over 2.5 goals"}]}],
         "legs": [{"label": "Both teams to score"}, {"label": "Over 2.5 goals"},
                  {"label": "Both teams to score", "link": "stale"}, {"label": "Over 2.5 goals", "link": "stale"}]}
    links.copy_flat_links(t)
    assert [l.get("link") for l in t["legs"]] == ["A", "A2", "B", None]


def test_card_rows_match_only_their_own_market():
    rows = pd.DataFrame([
        {"event_id": "m1", "market": "h2h", "outcome": "Arsenal", "player": None, "point": None, "price": -110.0, "link": "L-ARS"},
        {"event_id": "m1", "market": "btts", "outcome": "Yes", "player": None, "point": None, "price": -110.0, "link": "L-BTTS"},
        {"event_id": "m1", "market": "alternate_totals", "outcome": "Over", "player": None, "point": 2.5, "price": 120.0, "link": "L-O25"}])
    card = {"picks": [{"event_id": "m1", "market": "btts", "side": "Yes", "label": "Both teams to score", "price": -110.0, "point": None},
                      {"event_id": "m1", "market": "totals", "side": "Over", "label": "Over 2.5 goals", "price": 120.0, "point": 2.5}]}
    links.attach_card(card, links.Matcher(rows))
    assert [r.get("link") for r in card["picks"]] == ["L-BTTS", "L-O25"]


def test_an_anytime_td_leg_finds_fanduels_yes_without_a_number():
    rows = pd.DataFrame([
        {"event_id": "e1", "market": "player_anytime_td", "outcome": "Yes", "player": "Puka Nacua", "point": None,
         "price": -125.0, "link": "https://sportsbook.fanduel.com/addToBetslip?marketId=42.6&selectionId=4212"},
        {"event_id": "e1", "market": "player_anytime_td", "outcome": "Yes", "player": "Kyren Williams", "point": None,
         "price": -160.0, "link": "https://sportsbook.fanduel.com/addToBetslip?marketId=42.6&selectionId=3710"}])
    doc = {"games": [{"event_id": "e1", "sgps": [{"legs": [
        {"label": "Puka Nacua anytime TD", "stat": "tds", "side": "yes", "point": 0.5, "price": -125, "player": "Puka Nacua"}]}]}]}
    links.attach_fun(doc, links.Matcher(rows))
    assert doc["games"][0]["sgps"][0]["legs"][0]["link"].endswith("selectionId=4212")
def test_each_card_row_takes_the_link_of_its_own_book():
    fd = pd.DataFrame([{"event_id": "e1", "market": "spreads", "outcome": "Buffalo Bills", "player": None, "point": 3.5,
                        "price": -110.0, "link": "https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=2"}])
    dk = pd.DataFrame([{"event_id": "e1", "market": "spreads", "outcome": "Buffalo Bills", "player": None, "point": 3.0,
                        "price": -105.0, "link": "https://sportsbook.draftkings.com/?outcomes=0HC123_1"}])
    card = {"picks": [{"event_id": "e1", "market": "spreads", "side": "Buffalo Bills", "label": "Bills +3", "price": -105.0,
                       "point": 3.0, "book": "draftkings"}],
            "leans": [{"event_id": "e1", "market": "spreads", "side": "Buffalo Bills", "label": "Bills +3.5", "price": -110.0,
                       "point": 3.5, "book": "fanduel"}]}
    assert links.attach_card(card, {"fanduel": links.Matcher(fd), "draftkings": links.Matcher(dk)}) == 2
    assert card["picks"][0]["link"] == "https://sportsbook.draftkings.com/?outcomes=0HC123_1"      # DraftKings' host as given
    assert card["leans"][0]["link"].startswith("https://ny.sportsbook.fanduel.com/")
    card["picks"][0].pop("link")
    links.attach_card(card, links.Matcher(fd))                  # FanDuel's matcher alone: a DraftKings row gets none
    assert "link" not in card["picks"][0]
