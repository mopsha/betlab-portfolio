"""Novig's side of every parlay (Oct 28): legs found on Novig's catalog, each slip priced by its parlay pricer. No network."""

import pandas as pd
import pytest

from betlab import novig_parlays as NP

START = "2099-10-29T00:10:00Z"


def market(mid, kind, desc, strike, *outcomes):
    return {"marketId": mid, "marketType": kind, "description": desc, "strike": strike, "status": "OPEN",
            "outcomes": [{"outcomeId": f"{mid}-{i}", "name": n, **({"bid": {"price": b, "qty": q}} if b else {})}
                         for i, (n, b, q) in enumerate(outcomes)]}


MARKETS = [
    market("ml", "MONEY", "CHI", "0", ("CHI", "0.285", 540154), ("NYK", "0.71", 57512)),
    market("sp", "SPREAD", "CHI +3.5", "3.5", ("CHI +3.5", "0.48", 100000), ("NYK -3.5", "0.50", 100000)),
    market("t", "TOTAL", "NYK @ CHI t214.5", "214.5", ("Over 214.5", "0.48", 100000), ("Under 214.5", "0.48", 100)),
    market("kat", "POINTS", "Karl-Anthony Towns 24.5 POINTS", "24.5", ("Over 24.5", None, 0), ("Under 24.5", None, 0)),
    market("kat2", "POINTS", "Karl-Anthony Towns 29.5 POINTS", "29.5", ("Over 29.5", None, 0), ("Under 29.5", None, 0)),
    market("mpj", "REBOUNDS", "Michael Porter Jr. 5.5 REBOUNDS", "5.5", ("Over 5.5", None, 0), ("Under 5.5", None, 0)),
]
GAME = {"home": "Chicago Bulls", "away": "New York Knicks", "start": START, "sport": "nba"}


def leg(label, stat, side, point=None, player="game side", team=""):
    return {"label": label, "stat": stat, "side": side, "point": point, "player": player, "team": team}


@pytest.mark.parametrize("l, want", [
    (leg("New York Knicks ML", "moneyline", "yes", 0.0, team="NY"), "ml-1"),          # away: listed second
    (leg("Chicago Bulls ML", "moneyline", "yes", 0.0, team="CHI"), "ml-0"),
    (leg("New York Knicks -3.5", "spread", "yes", -3.5, team="NY"), "sp-1"),
    (leg("Chicago Bulls +3.5", "spread", "yes", 3.5, team="CHI"), "sp-0"),
    (leg("Chicago Bulls -3.5", "spread", "yes", -3.5, team="CHI"), None),            # not Novig's number
    (leg("Over 214.5 total points", "total", "over", 214.5), "t-0"),
    (leg("Karl-Anthony Towns 25+ points", "points", "over", 24.5, "Karl-Anthony Towns", "NY"), "kat-0"),
    (leg("Michael Porter Jr under 5.5 rebounds", "rebounds", "under", 5.5, "Michael Porter Jr", "BKN"), "mpj-1"),
    (leg("Josh Hart over 7.5 rebounds", "rebounds", "over", 7.5, "Josh Hart", "NY"), None),
    (leg("Knicks or draw", "double chance", "yes", None, team="New York Knicks"), None),   # Novig takes no NO side
])
def test_each_leg_finds_its_one_novig_outcome(l, want):
    o = NP.leg_outcome(l, GAME, MARKETS)
    assert (o["outcomeId"] if o else None) == want


def test_a_soccer_winner_draw_and_btts():
    game = {"home": "Atalanta BC", "away": "Parma", "start": START, "sport": "soccer"}
    mk = [market("w", "MONEYLINE_3_WAY_WIN", "Parma MONEYLINE_3_WAY_WIN", "0", ("Yes", None, 0), ("No", None, 0)),
          market("w2", "MONEYLINE_3_WAY_WIN", "Atalanta MONEYLINE_3_WAY_WIN", "0", ("Yes", None, 0), ("No", None, 0)),
          market("d", "MONEYLINE_3_WAY_DRAW", "Parma @ Atalanta MONEYLINE_3_WAY_DRAW", "0", ("Yes", None, 0), ("No", None, 0)),
          market("b", "BOTH_TEAMS_TO_SCORE", "Parma @ Atalanta BOTH_TEAMS_TO_SCORE", "0", ("Yes", None, 0), ("No", None, 0))]
    assert NP.leg_outcome(leg("Atalanta to win", "moneyline", "yes", team="Atalanta"), game, mk)["outcomeId"] == "w2-0"
    assert NP.leg_outcome(leg("Draw", "draw", "yes"), game, mk)["outcomeId"] == "d-0"
    assert NP.leg_outcome(leg("Both teams to score", "btts", "yes"), game, mk)["outcomeId"] == "b-0"


def test_a_legs_own_price_needs_50_dollars_behind_it():
    """Oct 28: the over 214.5 showed -614 off a thin book; books.min_limit is the rule for every Novig price."""
    ml = NP.leg_outcome(leg("New York Knicks ML", "moneyline", "yes", 0.0, team="NY"), GAME, MARKETS)
    assert NP._ask(ml) == pytest.approx(1 - 0.285)
    over = NP.leg_outcome(leg("Over 214.5 total points", "total", "over", 214.5), GAME, MARKETS)
    assert NP._ask(over) is None                      # the under's bid has $0.52 behind it
    kat = NP.leg_outcome(leg("KAT", "points", "over", 24.5, "Karl-Anthony Towns"), GAME, MARKETS)
    assert NP._ask(kat) is None                       # no bid at all


class Reply:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def json(self):
        return self._body


def test_the_answer_is_american_odds_and_a_no_price_is_not_asked_again(monkeypatch):
    """Oct 30: Novig's pricer moved to /rfq/v2/quote/unauthenticated: {outcomeIds} in, {price, expiresAt} out."""
    monkeypatch.setattr(NP.time, "sleep", lambda s: None)
    sent = []

    def post(body):
        sent.append(body)
        return Reply(200, {"price": "0.333", "expiresAt": 1, "serverNow": 0})
    assert NP.price(["a", "b"], post=post) == {"price": 200, "p": 0.333}
    assert sent == [{"outcomeIds": ["a", "b"]}]
    for status in (400, 404):                             # won't combine / no price right now: one ask, no error
        sent.clear()
        assert NP.price(["a", "b"], post=lambda body: sent.append(body) or Reply(status, {"message": "no price"})) is None
        assert len(sent) == 1


def test_a_rate_limit_waits_and_asks_again(monkeypatch):
    waits = []
    monkeypatch.setattr(NP.time, "sleep", waits.append)
    answers = iter([Reply(429, {}, {"Retry-After": "2"}), Reply(200, {"price": "0.5"})])
    assert NP.price(["a", "b"], post=lambda body: next(answers)) == {"price": 100, "p": 0.5}
    assert waits == [2.0]


def test_a_dead_pricer_is_an_error_not_a_refusal(monkeypatch, tmp_path):
    """Oct 29-30: the old route answered 404 "Cannot POST" and every slip read as refused, with nothing in the log."""
    monkeypatch.setattr(NP.time, "sleep", lambda s: None)
    monkeypatch.setattr(NP, "CACHE", tmp_path / "novig.json")
    gone = lambda body: Reply(404, {"statusCode": 404, "message": "Cannot POST /rfq/v2/quote/unauthenticated"})
    with pytest.raises(NP.PricerError, match="Cannot POST"):
        NP.price(["a", "b"], post=gone)
    with pytest.raises(NP.PricerError, match="all 2 asks failed"):
        NP.price_all([["a", "b"], ["c", "d"]], post=gone)
    assert not (tmp_path / "novig.json").exists() or "a,b" not in (tmp_path / "novig.json").read_text()
    mixed = lambda body: gone(body) if body["outcomeIds"] == ["a", "b"] else Reply(200, {"price": "0.25"})
    got = NP.price_all([["a", "b"], ["c", "d"]], post=mixed)  # one failure among answers: no error, not cached
    assert got == {"a,b": None, "c,d": {"price": 300, "p": 0.25}}


def test_slips_get_novigs_price_and_one_link_and_say_when_novig_lacks_a_leg(monkeypatch, tmp_path):
    monkeypatch.setattr(NP, "CACHE", tmp_path / "novig.json")
    rows = pd.DataFrame([{"event_id": "e1", "home_team": "Chicago Bulls", "away_team": "New York Knicks",
                          "commence_time": START, "sport_key": "basketball_nba"}])
    listed = [{"eventId": "n1", "description": "New York Knicks @ Chicago Bulls",
               "startsTs": pd.Timestamp(START).timestamp() * 1000}]
    idx = NP.Index(rows, listed=listed, markets=lambda nid: MARKETS)
    a = leg("New York Knicks ML", "moneyline", "yes", 0.0, team="NY")
    b = leg("Karl-Anthony Towns 25+ points", "points", "over", 24.5, "Karl-Anthony Towns", "NY")
    c = leg("Josh Hart over 7.5 rebounds", "rebounds", "over", 7.5, "Josh Hart", "NY")
    doc = {"slates": [{"sgps": [{"sgp_id": "s1", "event_id": "e1", "legs": [a, b]},
                                {"sgp_id": "s2", "event_id": "e1", "legs": [dict(a), c]}]}]}
    sent = []

    def post(body):
        sent.append(body["outcomeIds"])
        return Reply(200, {"price": "0.30", "expiresAt": 1, "serverNow": 0})
    assert NP.attach(doc, idx, post=post) == (1, 1)    # s2 lacks a leg: not asked
    s1, s2 = doc["slates"][0]["sgps"]
    assert sent == [["ml-1", "kat-0"]]
    assert s1["nv"]["price"] == 233 and "stake_max" not in s1["nv"]
    assert s1["nv"]["link"] == "https://novig.com/events/ml-1,kat-0/oddsapi/5"
    assert a["nv_id"] == "ml-1" and a["nv_price"] == -251
    assert s2["nv"] == {"legs": 1, "of": 2}               # Novig doesn't list Josh Hart's 7.5
    sent.clear()
    NP.attach(doc, idx, post=post)                        # within 30 minutes: from the cache, nothing asked
    assert sent == [] and doc["slates"][0]["sgps"][0]["nv"]["price"] == 233


def test_a_started_game_is_not_priced(monkeypatch, tmp_path):
    monkeypatch.setattr(NP, "CACHE", tmp_path / "novig.json")
    past = "2020-01-01T00:00:00Z"
    rows = pd.DataFrame([{"event_id": "e1", "home_team": "Chicago Bulls", "away_team": "New York Knicks",
                          "commence_time": past, "sport_key": "basketball_nba"}])
    listed = [{"eventId": "n1", "description": "New York Knicks @ Chicago Bulls", "startsTs": pd.Timestamp(past).timestamp() * 1000}]
    idx = NP.Index(rows, listed=listed, markets=lambda nid: MARKETS)
    doc = {"slates": [{"sgps": [{"sgp_id": "s1", "event_id": "e1", "legs": [
        leg("New York Knicks ML", "moneyline", "yes", 0.0, team="NY"), leg("Over 214.5 total points", "total", "over", 214.5)]}]}]}
    assert NP.attach(doc, idx, post=lambda body: pytest.fail("asked Novig for a started game")) == (0, 0)


def test_game_page_tables_get_novigs_price_and_ev():
    """Oct 28: Novig in the game pages' book tables (NBA player lines here): its price where $50+ stands behind it,
    with the EV against the row's own sharp chance; a thin side shows nothing."""
    mk = MARKETS + [market("hart", "REBOUNDS", "Josh Hart 7.5 REBOUNDS", "7.5", ("Over 7.5", "0.45", 100000), ("Under 7.5", "0.52", 100000))]
    idx = NP.Index(pd.DataFrame(), listed=[{"eventId": "n1", "description": "New York Knicks @ Chicago Bulls",
                                            "startsTs": pd.Timestamp(START).timestamp() * 1000}], markets=lambda nid: mk)
    row = {"player": "Josh Hart", "stat": "rebounds", "line": 7.5, "p_market": 0.5}
    products = {"nba": {"games": [{"home": "Chicago Bulls", "away": "New York Knicks", "tipoff": START, "lines": [row, dict(row, player="Nobody")]}]}}
    assert NP.attach_tables(products, idx) == 1
    assert row["nv_over"] == 108 and row["nv_under"] == -122                  # asks 1 - 0.52 and 1 - 0.45
    assert row["nv_ev_over"] == pytest.approx(0.5 * 2.08 - 1, abs=1e-4)
    assert products["nba"]["games"][0]["lines"][1]["nv_over"] is None
