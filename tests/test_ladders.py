"""Ladder challenges (ladders.py): the shared cases web/lib/ladder.ts and ios/BetLab/Me/Ladder.swift run too, and the
worker's lock rules (Mike, Oct 26: the day's best step, locked once its game's news is in)."""

import json
from pathlib import Path

import pandas as pd

from betlab import ladders as L

FIX = json.loads((Path(__file__).parent / "fixtures" / "ladder.json").read_text())


def bet(s, i, ladder="L"):
    return {"bet_id": f"b{i}", "ladder_id": ladder, "stake": s["stake"], "price": s["price"], "bonus": s.get("bonus", False),
            "boost": s.get("boost"), "cashout": s.get("cashout"), "placed_at": f"2026-10-2{i}T12:00:00Z",
            "pick_status": None, "ticket_status": s["status"]}


def test_the_shared_states():
    for c in FIX["states"]:
        lad = {"ladder_id": "L", "start_units": c["ladder"]["start"], "target_units": c["ladder"]["target"],
               "status": c["ladder"].get("status", "active")}
        s = L.state(lad, [bet(x, i) for i, x in enumerate(c["steps"])])
        e = c["expect"]
        assert s["phase"] == e["phase"], c["name"]
        assert abs(s["stack"] - e["stack"]) < 1e-4, c["name"]
        assert s["won"] == e["won"], c["name"]
        assert (s["next_stake"] is None) if e["next_stake"] is None else abs(s["next_stake"] - e["next_stake"]) < 1e-4, c["name"]
        if "to_win" in e:
            assert abs(s["to_win"] - e["to_win"]) < 1e-4, c["name"]


def test_the_shared_suggestions():
    for c in FIX["suggest"]:
        got = L.suggest(c["offers"], pd.Timestamp(c["now"]), c.get("skipped", []), c.get("game"),
                        pd.Timestamp(c["before"]) if c.get("before") else None, c.get("book"))
        assert (got["offer_id"] if got else None) == c["expect"], c["name"]
        if "expect_price" in c:
            assert got["price"] == c["expect_price"], c["name"]


def test_wins_in_a_row_to_the_target():
    for c in FIX["steps_to_target"]:
        assert L.steps_to_target(c["stack"], c["target"], c["price"]) == c["expect"]


NOW = pd.Timestamp("2026-10-31T15:00:00Z")      # 11 AM ET
OFFERS = [{"offer_id": "early", "tier": "pick", "label": "Early Side -3", "price": -110, "ev": 0.03, "book": "FanDuel",
           "matchup": "A @ B", "commence_time": "2026-10-31T17:00:00Z", "game_id": "g1", "league": "nfl"},
          {"offer_id": "late", "tier": "pick", "label": "Late Over 44.5", "price": 105, "ev": 0.06, "book": "DraftKings",
           "matchup": "C @ D", "commence_time": "2026-11-01T00:20:00Z", "game_id": "g2", "league": "nfl"}]
GAMES = {"g1": "e1", "g2": "e2", "g3": "e3"}
LAD = {"ladder_id": "L", "start_units": 1, "target_units": 100, "status": "active", "game_id": None, "skipped": [],
       "locked": None, "notice": None, "book": None}     # no book: the decide tests' offers sit at two books


def st(lad=LAD, bets=()):
    return L.state(lad, list(bets))


def test_any_game_holds_the_days_best_until_its_news_is_in():
    assert L.decide(LAD, st(), OFFERS, {"e1"}, GAMES, [], NOW) is None          # the best (late) isn't ready: hold
    d = L.decide(LAD, st(), OFFERS, {"e1", "e2"}, GAMES, [], NOW)
    assert d["locked"]["offer_id"] == "late" and d["locked"]["stake"] == 1 and d["locked"]["step"] == 1
    assert d["locked"]["price"] == 105.0 and d["locked"]["commence_time"] == "2026-11-01T00:20:00Z"
    assert "Late Over 44.5 +105" in d["alert"]["title"] and "Place 1u at DraftKings" in d["alert"]["body"]


def test_a_turned_down_or_banned_best_makes_way():
    d = L.decide(LAD | {"skipped": ["late"]}, st(), OFFERS, {"e1"}, GAMES, [], NOW)
    assert d["locked"]["offer_id"] == "early"
    d = L.decide(LAD, st(), OFFERS, {"e1"}, GAMES, [{"kind": "team", "name": "Late"}], NOW)
    assert d is None or d["locked"]["offer_id"] == "early"


def test_a_chosen_game_locks_its_own_best_or_says_it_has_none():
    lad = LAD | {"game_id": "g1"}
    assert L.decide(lad, st(lad), OFFERS, set(), GAMES, [], NOW) is None        # its news isn't in
    assert L.decide(lad, st(lad), OFFERS, {"e1"}, GAMES, [], NOW)["locked"]["offer_id"] == "early"
    lad3 = LAD | {"game_id": "g3"}
    d = L.decide(lad3, st(lad3), OFFERS, {"e3"}, GAMES, [], NOW)
    assert d["notice"] == "none:g3" and d["locked"] is None and "no step" in d["alert"]["title"]
    assert L.decide(lad3 | {"notice": "none:g3"}, st(lad3), OFFERS, {"e3"}, GAMES, [], NOW) is None   # told once


def test_a_locked_step_waits_clears_when_placed_and_expires_unplaced():
    locked = {"offer_id": "early", "label": "Early Side -3", "commence_time": "2026-10-31T17:00:00Z"}
    lad = LAD | {"locked": locked}
    assert L.decide(lad, st(lad), OFFERS, {"e1", "e2"}, GAMES, [], NOW) is None      # held for him to place
    placed = [bet({"stake": 1, "price": -110, "status": "open"}, 1)]
    assert L.decide(lad, st(lad, placed), OFFERS, {"e1"}, GAMES, [], NOW) == {"locked": None, "notice": None}
    later = pd.Timestamp("2026-10-31T17:05:00Z")
    assert L.decide(lad, st(lad), OFFERS, {"e1"}, GAMES, [], later) == {"locked": None, "notice": "missed:Early Side -3"}


def test_a_climbed_or_busted_ladder_locks_nothing():
    won = [bet({"stake": 1, "price": 100, "status": "won"}, 1)]
    lad = LAD | {"target_units": 2}
    assert L.decide(lad, st(lad, won), OFFERS, {"e1", "e2"}, GAMES, [], NOW) is None


def test_a_ladder_at_one_book_locks_only_what_that_book_posts():
    """Mike, Oct 26: a ladder stays at one book. The late pick is DraftKings' and FanDuel posts it at another number."""
    offers = [OFFERS[0] | {"book": "FanDuel"}, OFFERS[1] | {"point": 44.5, "other_book": "FanDuel", "other_point": 43.5,
                                                             "other_price": -130, "other_ev": -0.02}]
    lad = LAD | {"book": "FanDuel"}
    d = L.decide(lad, st(lad), offers, {"e1", "e2"}, GAMES, [], NOW)
    assert d["locked"]["offer_id"] == "early" and d["locked"]["book"] == "FanDuel"
    same = [offers[0], offers[1] | {"other_point": 44.5, "other_price": 100, "other_ev": 0.03}]
    d = L.decide(lad | {"skipped": ["early"]}, st(lad), same, {"e1", "e2"}, GAMES, [], NOW)
    assert d["locked"]["offer_id"] == "late" and d["locked"]["price"] == 100.0 and d["locked"]["book"] == "FanDuel"


class _Conn:
    """A stand-in for the app database: answers run()'s reads from lists and records its writes."""
    def __init__(self, ladders, bets):
        self.ladders, self.bets, self.writes = ladders, bets, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args=None):
        rows = []
        if sql.startswith("select * from ladders"):
            rows = self.ladders
        elif sql.startswith("select * from my_bets"):
            rows = [b for b in self.bets if b["ladder_id"] == args[1]]
        elif sql.startswith("update"):
            self.writes.append((sql, args))
        return type("R", (), {"fetchall": lambda s: rows, "fetchone": lambda s: None})()


def test_a_busted_ladder_is_closed_so_another_can_start(monkeypatch):
    """Nov 6 (Mike: "I can't start another ladder even though the old ones busted"): a ladder whose last step lost stayed
    'active' and blocked starting one; the worker closes it, and one still climbing is left alone."""
    import sys
    lost = [bet({"stake": 1, "price": 108, "status": "won"}, 1, "dead"), bet({"stake": 2.08, "price": 116, "status": "lost"}, 2, "dead")]
    going = [bet({"stake": 1, "price": 100, "status": "won"}, 3, "live")]
    conn = _Conn([LAD | {"ladder_id": "dead", "user_id": "u"}, LAD | {"ladder_id": "live", "user_id": "u"}], lost + going)
    monkeypatch.setitem(sys.modules, "psycopg", type("P", (), {"connect": staticmethod(lambda *a, **k: conn)}))
    monkeypatch.setitem(sys.modules, "psycopg.rows", type("R", (), {"dict_row": None}))
    out = L.run(now=NOW, send=lambda *a: 200, db_url="postgres://test", private_key="k")
    closes = [args for sql, args in conn.writes if "status = 'stopped'" in sql]
    assert closes == [[NOW, "dead"]]
    assert "1 closed" in out
