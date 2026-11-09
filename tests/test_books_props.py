"""DraftKings day 2 (Oct 12, docs/DRAFTKINGS_PLAN.md): props at both books, the same player under each book's
spelling, and the trackers keeping FanDuel's history unchanged."""

import pandas as pd

from betlab import books, ledger, props_market as PM
from betlab.cards import props_nhl as PNHL
from betlab.cards import props_soccer


def _prop(book, player, ev, price, side="Over", point=4.5):
    return {"league": "nfl", "event_id": "e1", "market": "player_receptions", "side": side, "player": player,
            "point": point, "price": price, "ev": ev, "book": book, "label": f"{player} {side.lower()} {point:g} receptions"}


def test_one_player_spelled_two_ways_is_one_bet_with_fanduels_spelling():
    df = pd.DataFrame([_prop("fanduel", "A.J. Brown", 0.01, -110), _prop("draftkings", "AJ Brown", 0.04, 100, point=5.5)])
    s = books.select(df)
    assert len(s) == 1
    r = s.iloc[0]
    assert r["book"] == "draftkings" and r["point"] == 5.5 and r["other_book"] == "fanduel"
    assert r["player"] == "A.J. Brown" and r["label"].startswith("A.J. Brown")      # FanDuel's spelling: pick ids hold
    assert ledger.pick_id(r) == ledger.pick_id(df.iloc[0])


def test_a_roster_id_matches_players_whose_names_differ_more():
    df = pd.DataFrame([_prop("fanduel", "Gabe Davis", 0.01, -110) | {"player_key": "00-1"},
                       _prop("draftkings", "Gabriel Davis", 0.03, -105) | {"player_key": "00-1"}])
    assert len(books.select(df)) == 1


def test_ledger_never_logs_one_bet_twice_under_two_spellings(tmp_path):
    path = tmp_path / "picks.csv"
    base = {"league": "nfl", "event_id": "e1", "market": "player_receptions", "side": "Over", "point": 4.5,
            "price": -110, "label": "x", "book": "fanduel", "kind": "prop"}
    assert len(ledger.add_picks(pd.DataFrame([base | {"player": "Kenneth Walker III"}]), "2026-10-13T12:00:00Z", path)) == 1
    again = ledger.add_picks(pd.DataFrame([base | {"player": "Kenneth Walker", "book": "draftkings"}]), "2026-10-13T13:00:00Z", path)
    assert again.empty


def test_book_main_reads_each_books_own_number():
    rows = [("fanduel", "Over", 4.5, -110), ("fanduel", "Under", 4.5, -110),
            ("draftkings", "Over", 5.5, 120), ("draftkings", "Under", 5.5, -150), ("draftkings", "Under", 4.5, -105)]
    snap = pd.DataFrame([{"bookmaker": b, "market": "player_receptions", "player": "A", "outcome": o, "point": pt, "price": pr}
                         for b, o, pt, pr in rows])
    dk = PM.book_main(snap, "draftkings").iloc[0]
    assert dk["point"] == 5.5 and dk["over"] == 120 and dk["under"] == -150          # the under at the over's number
    assert PM.book_main(snap).iloc[0]["point"] == 4.5


def test_draftkings_scorer_names_find_pinnacles_price():
    rows = [("pinnacle", "Vinícius Júnior", "Yes", 150), ("pinnacle", "Vinícius Júnior", "No", -180),
            ("fanduel", "Vinícius Júnior", "Yes", 160), ("draftkings", "Vinicius Junior", "Yes", 175)]
    snap = pd.DataFrame([{"event_id": "m1", "commence_time": "2026-10-18T19:00:00Z", "home_team": "Real Madrid",
                          "away_team": "Getafe", "bookmaker": b, "market": props_soccer.SCORER, "player": p,
                          "outcome": o, "point": None, "price": pr} for b, p, o, pr in rows])
    asof = pd.Timestamp("2026-10-18T12:00:00Z")
    dk = props_soccer.scorer_offers(snap, "laliga", asof, book="draftkings")
    fd = props_soccer.scorer_offers(snap, "laliga", asof)
    assert len(dk) == 1 and dk.iloc[0]["book"] == "draftkings" and dk.iloc[0]["p_market"] == fd.iloc[0]["p_market"]
    s = books.select(pd.concat([fd, dk], ignore_index=True))
    assert len(s) == 1 and s.iloc[0]["book"] == "draftkings" and s.iloc[0]["player"] == "Vinícius Júnior"


def test_nhl_points_are_priced_at_draftkings_and_each_book_is_tracked(monkeypatch):
    rows = []
    for b, o, pt, pr in [("fanduel", "Over", 2.5, -120), ("fanduel", "Under", 2.5, -110),
                         ("draftkings", "Over", 2.5, -105), ("draftkings", "Under", 2.5, -125),
                         ("betmgm", "Over", 2.5, -110), ("betmgm", "Under", 2.5, -110)]:
        rows.append({"market": "player_shots_on_goal", "player": "Sidney Crosby", "bookmaker": b, "outcome": o, "point": pt, "price": pr})
    for b, o, pr in [("draftkings", "Over", 110), ("draftkings", "Under", -140), ("pinnacle", "Over", 100), ("pinnacle", "Under", -120)]:
        rows.append({"market": "player_points", "player": "Sidney Crosby", "bookmaker": b, "outcome": o, "point": 0.5, "price": pr})
    props = pd.DataFrame(rows).assign(event_id="ev1", commence_time="2026-10-13T23:00:00Z")
    games = {"ev1": {"matchup": "PIT @ PHI", "commence_time": "2026-10-13T23:00:00Z", "game_ref": "1",
                     "home": "PHI", "away": "PIT", "read": {}}}
    offers, track = PNHL.price(props, pd.Timestamp("2026-10-13T12:00:00Z"), games, pd.DataFrame(), None, {}, {})
    assert {(t["book"], t["stat"]) for t in track} == {("fanduel", "shots"), ("draftkings", "shots"), ("draftkings", "points")}
    pts = offers[offers["market"] == "player_points"]
    assert set(pts["book"]) == {"draftkings"} and len(pts) == 2
    shots = offers[(offers["market"] == "player_shots_on_goal")]
    assert set(shots["market_source"]) == {"consensus of 1 books"}                      # BetMGM only: never FanDuel or DraftKings


def test_tracker_ids_for_fanduel_are_unchanged(tmp_path, monkeypatch):
    from betlab import tracking_nba, tracking_nhl_props

    assert tracking_nba.line_id("e1", 7, "points") == tracking_nba.line_id("e1", 7, "points", "fanduel")
    assert tracking_nba.line_id("e1", 7, "points", "draftkings") != tracking_nba.line_id("e1", 7, "points")
    monkeypatch.setattr(tracking_nhl_props, "PATH", tmp_path / "nhl.csv")
    row = {"event_id": "ev1", "game_ref": "1", "commence_time": "2026-10-13T23:00:00Z", "matchup": "PIT @ PHI",
           "player": "Sidney Crosby", "team": "PIT", "stat": "shots", "line": 2.5, "fd_over": -120, "fd_under": -110,
           "p_market": 0.5, "books": 2, "p_model": None, "model_mean": None, "read": ""}
    tracking_nhl_props.record([row, row | {"book": "draftkings", "fd_over": -105}], pd.Timestamp("2026-10-13T12:00:00Z"))
    df = tracking_nhl_props.load()
    assert set(df["line_id"]) == {"ev1|Sidney Crosby|shots", "ev1|Sidney Crosby|shots|draftkings"}
    assert set(df["book"]) == {"fanduel", "draftkings"}
    assert tracking_nhl_props.summary(df)["draftkings_lines"] == 1


def test_a_moved_number_is_a_lean_at_most_at_either_book():
    from betlab import picks

    g = pd.DataFrame([
        {"bookmaker": "betmgm", "outcome": "Over", "point": 3.5, "price": 120},
        {"bookmaker": "betmgm", "outcome": "Under", "point": 3.5, "price": -150}])
    mv: list = []
    PNHL._consensus(g, 2.5, size=21.0, moved=mv)
    assert mv == [True]
    mv = []
    PNHL._consensus(g, 3.5, size=21.0, moved=mv)
    assert mv == [False]
    offers = pd.DataFrame([{"league": "nfl", "event_id": "e1", "commence_time": "2026-10-18T17:00:00Z", "market": "player_receptions",
                            "side": "Over", "player": "A", "point": 3.5, "price": 131, "book": b, "kind": "prop", "ev": 0.10,
                            "p_final": 0.47, "p_market": 0.47, "p_model": 0.47, "p_push": 0.0, "w_model": 0.0,
                            "lean_only": lean, "market_source": "pinnacle"} for b, lean in (("draftkings", True), ("fanduel", False))])
    tiers = picks.classify(offers.assign(event_id=["e1", "e2"]), pd.Timestamp("2026-10-18T12:00:00Z")).set_index("book")["tier"]
    assert tiers["draftkings"] == "lean" and tiers["fanduel"] == "pick"


def test_the_card_keeps_each_bets_book_and_the_other_books_price():
    from betlab.reports import card as card_report

    df = pd.DataFrame([_prop("draftkings", "A.J. Brown", 0.06, 100) | {"tier": "pick", "pick_id": "p1", "other_book": "fanduel",
                                                                        "other_point": 4.5, "other_price": -110, "other_ev": 0.01}])
    row = card_report.build(df, "now", None, [])["picks"][0]
    assert row["book"] == "draftkings" and row["other_book"] == "fanduel" and row["other_price"] == -110
