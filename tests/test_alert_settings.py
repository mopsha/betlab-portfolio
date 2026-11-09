"""Alert settings (alert_prefs.py), leg news (leg_news.py) and key rotation reminders (rotation.py), Nov 2."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from betlab import alert_prefs as ap, alerts, leg_alerts, leg_news, rotation

NOW = pd.Timestamp("2026-10-21T15:00:00Z")
UID = "u1"


def _picks(rows=None):
    base = {"created_at": "2026-10-21T14:00:00+00:00", "league": "nba", "commence_time": "2026-10-21T23:30:00Z",
            "matchup": "Knicks @ Celtics", "label": "Celtics -3.5", "price": -110.0, "ev": 0.05, "units_tier": 1.0, "status": "open"}
    return pd.DataFrame([base | r for r in ([{"pick_id": "p1"}] if rows is None else rows)])


class Conn:
    def __init__(self, notify=None, sent=(), held=()):
        self.notify, self.sent, self.held = notify, set(sent), list(held)
        self.subs = [(UID, "https://push/a", "k", "s")]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        rows = []
        if sql.startswith("select pick_id from alerts_sent"):
            rows = [(x,) for x in self.sent]
        elif sql.startswith("select user_id, bans, notify"):
            rows = [(UID, [], self.notify)]
        elif sql.startswith("select user_id, endpoint"):
            rows = self.subs
        elif sql.startswith("insert into alerts_sent"):
            self.sent.add(params[0])
        elif sql.startswith("insert into alerts_held"):
            self.held.append((len(self.held) + 1, params[0], params[1], params[2], self.notify))
        elif sql.startswith("select h.id"):
            rows = self.held
        elif sql.startswith("delete from alerts_held"):
            self.held = [h for h in self.held if h[0] != params[0]]
        return type("R", (), {"fetchall": lambda _self: rows})()


@pytest.fixture
def run(monkeypatch):
    import psycopg

    def go(notify=None, picks=None, leans=None, slates=(), now=NOW, **conn):
        c = Conn(notify, **conn)
        monkeypatch.setattr(psycopg, "connect", lambda *a, **k: c)
        monkeypatch.setattr(alerts.ledger, "load", lambda path=None: (leans if path is not None else picks) if (leans if path is not None else picks) is not None else _picks([]))
        monkeypatch.setattr(alerts, "fun_slates", lambda: list(slates))
        monkeypatch.setattr(alerts, "fun_games", lambda: [])
        got = []
        out = alerts.run(now=now, send=lambda sub, msg, key: got.append(msg["title"]) or 201, db_url="x", private_key="k")
        return out, got, c
    return go


def test_defaults_keep_todays_alerts():
    p = ap.clean(None)
    assert p["picks"] and p["locks"] and p["legs"] and p["news"] and not p["leans"]
    assert p["min_ev"] is None and p["quiet"] is None and not p["off"]
    assert ap.wants(p, "nba", 0.001) and not ap.wants(p, "nba", 0.5, "lean")


def test_bad_values_count_as_not_set():
    p = ap.clean({"min_ev": "lots", "quiet": {"from": "25:00", "to": "08:00"}, "sports": ["nfl"]})
    assert p["min_ev"] is None and p["quiet"] is None and not p["off"]
    assert ap.clean({"quiet": {"from": "08:00", "to": "08:00"}})["quiet"] is None


def test_every_soccer_competition_is_one_sport():
    p = ap.clean({"sports": {"soccer": False, "nba": True}})
    assert not ap.wants(p, "ucl", 0.1) and not ap.wants(p, "epl", 0.1) and ap.wants(p, "nba", 0.1)
    assert not ap.wants_lock(p, "soccer") and ap.wants_lock(p, None)


def test_min_ev_is_in_percent():
    p = ap.clean({"min_ev": 4})
    assert not ap.wants(p, "nfl", 0.039) and ap.wants(p, "nfl", 0.04)


@pytest.mark.parametrize("hour,minute,quiet", [(22, 59, False), (23, 0, True), (2, 0, True), (7, 59, True), (8, 0, False)])
def test_quiet_hours_cross_midnight_in_eastern_time(hour, minute, quiet):
    p = ap.clean({"quiet": {"from": "23:00", "to": "08:00"}})
    assert ap.in_quiet(p, datetime(2026, 11, 3, hour, minute, tzinfo=ZoneInfo("America/New_York"))) is quiet


def test_quiet_hours_within_a_day():
    p = ap.clean({"quiet": {"from": "09:00", "to": "17:00"}})
    et = ZoneInfo("America/New_York")
    assert ap.in_quiet(p, datetime(2026, 11, 3, 12, tzinfo=et)) and not ap.in_quiet(p, datetime(2026, 11, 3, 18, tzinfo=et))


def test_a_sport_turned_off_gets_no_pick_but_the_pick_is_marked(run):
    out, got, c = run({"sports": {"nba": False}}, _picks())
    assert got == [] and "p1" in c.sent


def test_picks_off_keeps_locks(run):
    slate = {"slate": "d-nba-early", "sport": "nba", "kickoff": "2026-10-21T23:00:00Z", "locked_at": "t",
             "plus": {"n_games": 3, "n_legs": 4, "fair_price": 500}}
    _, got, _ = run({"picks": False}, _picks(), slates=[slate])
    assert len(got) == 1 and got[0].startswith("Locked")
    _, got, _ = run({"locks": False}, _picks(), slates=[slate])
    assert len(got) == 1 and "pick" in got[0]


def test_leans_only_for_who_asks_and_keyed_apart(run):
    leans = _picks([{"pick_id": "p1", "label": "Celtics -2.5", "ev": 0.02}])
    _, got, c = run(None, _picks([]), leans)
    assert got == [] and not any(k.startswith("lean:") for k in c.sent)
    _, got, c = run({"leans": True}, _picks([]), leans)
    assert got == ["NBA lean: Celtics -2.5 · FanDuel -110"] and c.sent == {"lean:p1"}
    _, got, c = run({"leans": True}, _picks([]), leans, sent={"lean:p1"})
    assert got == []


def test_a_lean_that_became_a_pick_still_alerts(run):
    _, got, c = run({"leans": True}, _picks(), _picks(), sent={"lean:p1"})
    assert got == ["NBA pick: Celtics -3.5 · FanDuel -110"]


def test_quiet_hours_hold_then_release(run, monkeypatch):
    quiet = {"quiet": {"from": "10:00", "to": "12:00"}}            # 15:00 UTC is 11 AM ET
    out, got, c = run(quiet, _picks())
    assert got == [] and "p1" in c.sent and len(c.held) == 1 and "held for 1 account" in out
    sent = []
    send = lambda sub, msg, key: sent.append(msg["title"]) or 201
    assert "0 held alert(s) sent" in alerts.release(now=NOW, send=send, db_url="x", private_key="k")
    assert sent == [] and len(c.held) == 1
    later = pd.Timestamp("2026-10-21T17:00:00Z")
    assert "1 held alert(s) sent" in alerts.release(now=later, send=send, db_url="x", private_key="k")
    assert sent == ["NBA pick: Celtics -3.5 · FanDuel -110"] and c.held == []


def test_a_held_alert_for_a_started_game_is_dropped(run):
    quiet = {"quiet": {"from": "10:00", "to": "12:00"}}
    _, _, c = run(quiet, _picks())
    sent = []
    out = alerts.release(now=pd.Timestamp("2026-10-22T01:00:00Z"), send=lambda *a: sent.append(a) or 201, db_url="x", private_key="k")
    assert sent == [] and c.held == [] and "1 dropped" in out


def test_leg_alerts_are_recorded_not_sent_in_quiet_hours():
    now = datetime(2026, 11, 3, 1, tzinfo=ZoneInfo("America/New_York"))
    bet = {"bet_id": "b", "user_id": UID, "kind": "pick", "label": "Knicks ML", "legs": None, "matchup": "Knicks @ Celtics",
           "league": "nba", "price": 100, "notify": {"quiet": {"from": "23:00", "to": "08:00"}}, "alerts": True}
    game = {"key": "g", "sport": "nba", "state": "post", "detail": "Final", "home": {"name": "Boston Celtics", "abbr": "BOS", "score": 90},
            "away": {"name": "New York Knicks", "abbr": "NYK", "score": 100}}
    import betlab.live_legs as ll
    orig = ll.live_bet
    ll.live_bet = lambda b, t, board, box, now=None: {"legs": [{"status": "won", "label": "Knicks ML", "game": "g"}], "games": [game], "status": "won", "hit": 1}
    try:
        out = leg_alerts.check([(bet, None)], {"seen:b"}, now, get=lambda u, t=None: None)
    finally:
        ll.live_bet = orig
    assert len(out) == 1 and out[0][1] == ["leg:b:0:won"] and out[0][2] is None


# ---------------------------------------------------------------- leg news
GAME = {"key": "g", "state": "pre", "start": "2026-11-05T01:15:00Z", "home": {"name": "Baltimore Ravens", "abbr": "BAL"},
        "away": {"name": "Jacksonville Jaguars", "abbr": "JAX"}}
OUTS = {"nfl": {"ravens": {"mark andrews": "Out"}, "bills": {"josh allen": "Out"}}}


def _bet(*legs, book="FanDuel", **kw):
    return {"bet_id": "b1", "user_id": UID, "book": book, "price": 250, "league": "nfl", "matchup": "Jacksonville Jaguars @ Baltimore Ravens",
            "legs": list(legs)} | kw


def _board(game=GAME):
    return lambda sport, league: [game] if sport == "nfl" else []


def test_a_player_out_on_this_game_is_found():
    hits = leg_news.scan(_bet("Mark Andrews over 40.5 receiving yards", "Baltimore Ravens ML"), None, OUTS, _board())
    assert [h["key"] for h in hits] == ["mark andrews"] and hits[0]["status"] == "Out"


def test_a_namesake_on_another_team_is_not():
    assert leg_news.scan(_bet("Josh Allen over 200.5 passing yards"), None, OUTS, _board()) == []


def test_a_started_game_is_ignored():
    assert leg_news.scan(_bet("Mark Andrews anytime TD"), None, OUTS, _board(GAME | {"state": "in"})) == []


def test_an_initial_on_a_slip_matches_only_one_player():
    assert leg_news.scan(_bet("M. Andrews anytime TD"), None, OUTS, _board())[0]["key"] == "mark andrews"
    two = {"nfl": {"ravens": {"mark andrews": "Out", "mike andrews": "Out"}}}
    assert leg_news.scan(_bet("M. Andrews anytime TD"), None, two, _board()) == []


def test_only_out_statuses_count():
    assert all(leg_news.is_out(s) for s in ("Out", "Injured Reserve", "suspended", "Inactive"))
    assert not any(leg_news.is_out(s) for s in ("Questionable", "Doubtful", "Day-To-Day", ""))


def test_the_rule_follows_the_book_and_the_bet():
    assert "FanDuel voids" in leg_news.rule("FanDuel", 1)
    assert "DraftKings takes that leg off" in leg_news.rule("DraftKings", 3)
    assert "Novig's own rules" in leg_news.rule("Novig", 3)
    assert "counts as won" in leg_news.rule("FanDuel", 3, True)


def test_the_message_names_player_leg_and_rule():
    m = leg_news.message(_bet("Mark Andrews anytime TD", "Ravens ML"), {"player": "Mark Andrews", "status": "Out", "label": "Mark Andrews anytime TD"}, 2)
    assert m["title"] == "Mark Andrews is out" and "2-leg parlay (+250)" in m["body"] and "reprices" in m["body"]
    assert len(m["body"]) <= 240


# ---------------------------------------------------------------- key rotation
CFG = {"every_days": 180, "keys": [{"name": "Odds API keys", "where": "Railway", "rotated": date(2026, 10, 23)}]}


def test_a_key_is_due_after_its_time_and_not_before():
    assert rotation.due(CFG, [], date(2027, 4, 20)) == []
    assert rotation.due(CFG, [], date(2027, 4, 21))[0]["slug"] == "odds-api-keys"


def test_an_open_todo_stops_a_second_one_and_a_done_one_restarts_the_clock():
    assert rotation.due(CFG, [("u-rotate-odds-api-keys-20270421", None)], date(2027, 6, 1)) == []
    done = [("u-rotate-odds-api-keys-20270421", date(2027, 4, 25))]
    assert rotation.due(CFG, done, date(2027, 6, 1)) == []
    assert rotation.due(CFG, done, date(2027, 10, 22))[0]["last"] == date(2027, 4, 25)


def test_the_real_config_holds_names_and_dates_only():
    cfg = rotation.load()
    assert cfg["every_days"] and all(isinstance(k["rotated"], date) and set(k) == {"name", "where", "rotated"} for k in cfg["keys"])
