"""Two books (Oct 12, docs/DRAFTKINGS_PLAN.md): each priced against the same sharp market, one offer per bet."""

import pandas as pd

from betlab import books, market
from betlab.cards import nhl


def _offer(book, ev, price, point=None, side="Bills", market_="spreads", player=None):
    return {"league": "nfl", "event_id": "e1", "market": market_, "side": side, "player": player, "point": point,
            "price": price, "ev": ev, "book": book, "label": f"{side} {point}"}


def test_one_offer_per_bet_the_higher_ev_and_the_other_price_attached():
    df = pd.DataFrame([_offer("fanduel", 0.01, -110, 3.5), _offer("draftkings", 0.03, -105, 3.5),
                       _offer("fanduel", 0.02, -110, None, side="Over", market_="totals"),
                       _offer("draftkings", 0.02, -110, None, side="Over", market_="totals")])
    s = books.select(df).set_index("market")
    assert len(s) == 2
    assert s.loc["spreads", "book"] == "draftkings" and s.loc["spreads", "other_book"] == "fanduel"
    assert s.loc["spreads", "other_price"] == -110 and s.loc["spreads", "other_ev"] == 0.01
    assert s.loc["totals", "book"] == "fanduel"                    # a tie goes to FanDuel (Mike, Oct 12)


def test_different_numbers_are_one_bet_and_each_keeps_its_own_line():
    df = pd.DataFrame([_offer("fanduel", 0.012, -110, 3.5), _offer("draftkings", 0.004, -110, 3.0)])
    s = books.select(df).iloc[0]
    assert s["book"] == "fanduel" and s["point"] == 3.5 and s["other_point"] == 3.0


def test_a_bet_only_one_book_posts_passes_through():
    s = books.select(pd.DataFrame([_offer("draftkings", 0.02, 150, None, side="Kucherov", market_="player_points",
                                          player="Nikita Kucherov")])).iloc[0]
    assert s["book"] == "draftkings" and s["other_book"] is None


def test_neither_book_is_ever_the_others_market():
    ev = pd.DataFrame([{"market": "h2h", "bookmaker": b} for b in ("fanduel", "draftkings", "betmgm", "betrivers")])
    for target in ("fanduel", "draftkings"):
        used, source = market.reference_books(ev, "h2h", ["pinnacle"], target)
        assert set(used) == {"betmgm", "betrivers"} and source == "consensus of 2 books"


def test_an_evaluator_prices_draftkings_at_its_own_prices():
    rows = []
    for book, h, a in (("fanduel", -150, 130), ("draftkings", -140, 120), ("pinnacle", -145, 135)):
        rows += [{"event_id": "g1", "commence_time": "2026-10-20T23:00:00Z", "home_team": "Boston Bruins",
                  "away_team": "Buffalo Sabres", "bookmaker": book, "market": "h2h", "outcome": "Boston Bruins",
                  "point": None, "price": h},
                 {"event_id": "g1", "commence_time": "2026-10-20T23:00:00Z", "home_team": "Boston Bruins",
                  "away_team": "Buffalo Sabres", "bookmaker": book, "market": "h2h", "outcome": "Buffalo Sabres",
                  "point": None, "price": a}]
    snap = pd.DataFrame(rows)
    sched = pd.DataFrame({"game_id": ["n1"], "home": ["BOS"], "away": ["BUF"], "start": ["2026-10-20T23:00:00Z"]})
    codes = {"boston bruins": "BOS", "buffalo sabres": "BUF"}
    asof = pd.Timestamp("2026-10-20T12:00:00Z")
    both = books.price_all(nhl.evaluate, snap, asof, sched, codes)
    dk = both[both["book"] == "draftkings"].set_index("side")
    fd = both[both["book"] == "fanduel"].set_index("side")
    assert len(dk) == 2 and set(dk["price"]) == {-140, 120}
    assert (dk["p_market"].values == fd["p_market"].values).all()   # the same sharp market for both books
    assert "DraftKings -140" in dk.iloc[0]["context"] or "DraftKings +120" in dk.iloc[0]["context"]


def test_novig_is_a_third_book_for_game_lines_with_its_bet_limit():
    """Oct 22: Novig, the sports exchange, priced like the sportsbooks; its offers carry the dollars behind each price."""
    rows = []
    for book, h, a, lim in (("fanduel", -150, 130, None), ("draftkings", -140, 120, None), ("pinnacle", -145, 135, None),
                            ("novig", -142, 140, (900, 30))):
        for team, price, limit in (("Boston Bruins", h, lim and lim[0]), ("Buffalo Sabres", a, lim and lim[1])):
            rows.append({"event_id": "g1", "commence_time": "2026-10-20T23:00:00Z", "home_team": "Boston Bruins",
                         "away_team": "Buffalo Sabres", "bookmaker": book, "market": "h2h", "outcome": team,
                         "point": None, "price": price, "bet_limit": limit})
    snap = pd.DataFrame(rows)
    sched = pd.DataFrame({"game_id": ["n1"], "home": ["BOS"], "away": ["BUF"], "start": ["2026-10-20T23:00:00Z"]})
    codes = {"boston bruins": "BOS", "buffalo sabres": "BUF"}
    every = books.price_all(nhl.evaluate, snap, pd.Timestamp("2026-10-20T12:00:00Z"), sched, codes)
    nv = every[every["book"] == "novig"].set_index("price")
    assert set(nv.index) == {-142, 140} and nv.loc[-142, "bet_limit"] == 900 and nv.loc[140, "bet_limit"] == 30
    best = books.select(every).set_index("price")
    # Buffalo +140 at Novig has the best price but only $30 behind it: the sportsbooks' +130 stands
    assert 140 not in best.index and best.loc[130, "book"] == "fanduel"
    assert books.name("novig") == "Novig"


def test_an_exchange_price_with_no_limit_found_never_wins():
    df = pd.DataFrame([_offer("fanduel", 0.01, -110, 3.5), _offer("novig", 0.04, 105, 3.5)])
    assert books.select(df).iloc[0]["book"] == "fanduel"
    df["bet_limit"] = [None, 500.0]
    s = books.select(df).iloc[0]
    assert s["book"] == "novig" and s["other_book"] == "fanduel" and s["bet_limit"] == 500


def test_props_stay_at_the_sportsbooks():
    assert books.targets() == ["fanduel", "draftkings", "novig"]
    assert books.targets("props") == ["fanduel", "draftkings"]


def test_novig_links_fill_in_the_stake():
    from betlab import links

    url = "https://novig.com/events/01a15f1c-280f/oddsapi/{wager}"
    assert links.book_link(url) == "https://novig.com/events/01a15f1c-280f/oddsapi/5"


def test_each_book_reads_every_bet_on_its_own_for_accounts_with_books_off():
    """Nov 6 (books.per_book): Novig has the best price, DraftKings the next, FanDuel the worst; each book's own tier comes
    from the same rules on its offers alone, and a Novig price under the limit is no bet there."""
    def read(d):          # a stand-in classify: a pick from 3% EV, a lean from 1%
        d = d.copy()
        d["tier"] = ["pick" if e >= 0.03 else "lean" if e >= 0.01 else "" for e in d["ev"]]
        d["units_tier"] = [1.0 if t == "pick" else None for t in d["tier"]]
        return d

    nv = _offer("novig", 0.05, 120, 3.5) | {"bet_limit": 400.0}
    df = pd.DataFrame([_offer("fanduel", 0.005, -110, 3.5), _offer("draftkings", 0.035, 105, 3.5), nv,
                       _offer("draftkings", 0.02, -105, None, side="Over", market_="totals"),
                       _offer("novig", 0.06, 110, None, side="Over", market_="totals") | {"bet_limit": 20.0}])
    chosen = books.select(df)
    reads = dict(zip(chosen["market"], books.per_book(df, chosen, read)))
    assert [(e["book"], e["tier"], e["price"]) for e in reads["spreads"]] == \
        [("FanDuel", None, -110.0), ("DraftKings", "pick", 105.0), ("Novig", "pick", 120.0)]
    assert reads["spreads"][2]["bet_limit"] == 400.0
    assert [e["book"] for e in reads["totals"]] == ["DraftKings"]           # Novig's $20 isn't a bet
    assert books.per_book(df.iloc[0:0], chosen, read) == [[], []]


def test_a_card_bet_at_the_books_an_account_has_on():
    """tests/fixtures/books_off.json, the web's and the iPhone's cases too."""
    import json, pathlib
    fx = json.loads((pathlib.Path(__file__).parent / "fixtures" / "books_off.json").read_text())

    def check(offer, off, want, case=""):
        got = books.at_books(offer, off)
        if want is None:
            assert got is None, case
            return
        assert got is not None, case
        for k, v in want.items():
            assert got.get(k) == v, f"{case}: {k} {got.get(k)!r} != {v!r}"

    for c in fx["cases"]:
        check(fx["offer"], c["off"], c["want"], c["case"])
    check(fx["lean"]["offer"], fx["lean"]["off"], fx["lean"]["want"], "lean")
    for c in fx["old"]["cases"]:
        check(fx["old"]["offer"], c["off"], c["want"], "old")
    for c in fx["on"]:
        assert books.on_books(c["off"]) == c["want"]
