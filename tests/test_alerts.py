"""Pick alerts (alerts.py): which picks are new, the notification text, and the send loop (fake database)."""

import pandas as pd
import pytest

from betlab import alerts

NOW = pd.Timestamp("2026-10-21T15:00:00Z")


def _picks(n=1, **kw):
    rows = [{"pick_id": f"p{i}", "created_at": "2026-10-21T14:00:00+00:00", "league": "nba",
             "commence_time": "2026-10-21T23:30:00Z", "matchup": "New York Knicks @ Boston Celtics",
             "label": f"Boston Celtics -{i}.5", "price": -110.0, "ev": 0.03 + i / 100, "units_tier": 1.0,
             "status": "open"} | kw for i in range(n)]
    return pd.DataFrame(rows)


def test_only_new_open_unstarted_unsent_picks():
    p = pd.concat([_picks(2),
                   _picks(1, pick_id="old", created_at="2026-10-21T06:00:00+00:00"),       # logged 9 h ago
                   _picks(1, pick_id="started", commence_time="2026-10-21T14:30:00Z"),
                   _picks(1, pick_id="graded", status="won")], ignore_index=True)
    out = alerts.pending(p, sent={"p0"}, now=NOW)
    assert list(out["pick_id"]) == ["p1"]


def test_one_notification_each_or_one_summary():
    one = alerts.messages(_picks(1))
    assert one[0]["title"] == "NBA pick: Boston Celtics -0.5 · FanDuel -110"
    assert one[0]["body"] == "New York Knicks @ Boston Celtics · Wed 7:30 PM ET · EV +3.0% · 1u at FanDuel"
    many = alerts.messages(alerts.pending(_picks(5), set(), NOW))
    assert len(many) == 1 and many[0]["title"] == "5 new BetLab picks" and "Boston Celtics -4.5" in many[0]["body"]


class FakeConn:
    def __init__(self, sent=(), subs=()):
        self.sent, self.subs, self.sql = set(sent), list(subs), []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.sql.append((sql.split()[0], params))
        rows = []
        if sql.startswith("select pick_id from alerts_sent"):
            rows = [(x,) for x in self.sent]
        elif sql.startswith("select user_id, endpoint"):
            rows = self.subs
        elif sql.startswith("insert into alerts_sent"):
            self.sent.add(params[0])
        elif sql.startswith("delete from push_subscriptions"):
            self.subs = [s for s in self.subs if s[1] != params[1]]
        return type("R", (), {"fetchall": lambda _self: rows})()


@pytest.fixture
def db(monkeypatch):
    import psycopg

    conn = FakeConn(subs=[("u1", "https://push/a", "k", "s"), ("u1", "https://push/gone", "k", "s")])
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(alerts.ledger, "load", lambda path=None: _picks(2))
    monkeypatch.setattr(alerts, "fun_slates", lambda: [])      # no locked tickets (never the repo's fun.json)
    return conn


def test_run_sends_marks_sent_and_drops_gone_devices(db):
    sent = []

    def send(sub, msg, key):
        sent.append((sub["endpoint"], msg["tag"]))
        return 410 if sub["endpoint"].endswith("gone") else 201

    out = alerts.run(now=NOW, send=send, db_url="postgres://x", private_key="k")
    assert out == "alerts: 2 new pick(s) sent to 1 of 2 device(s); 1 gone device(s) removed"
    assert ("https://push/a", "p1") in sent and ("https://push/a", "p0") in sent
    assert db.sent == {"p0", "p1"} and [s[1] for s in db.subs] == ["https://push/a"]
    assert alerts.run(now=NOW, send=send, db_url="postgres://x", private_key="k") == "alerts: no new picks or locked tickets"


def test_no_keys_or_database_does_nothing(monkeypatch):
    monkeypatch.setattr(alerts.config, "secret", lambda name: None)
    assert "skipped" in alerts.run(now=NOW, send=None)
    assert "VAPID" in alerts.run(now=NOW, send=None, db_url="postgres://x")


def test_the_confirmation_goes_to_new_devices_only(monkeypatch):
    import psycopg

    conn = FakeConn(subs=[("u1", "https://push/new", "k", "s")])
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: conn)
    got = []
    out = alerts.test(send=lambda sub, msg, key: got.append((sub["endpoint"], msg["title"])) or 201,
                      db_url="postgres://x", private_key="k")
    assert out == "alerts: test sent to 1 of 1 new device(s)" and got == [("https://push/new", "BetLab alerts are on")]


def test_a_locked_ticket_is_pushed_once(db, monkeypatch):
    """Mike, Oct 10: a notification when a slice's tickets lock (15 minutes before it starts)."""
    monkeypatch.setattr(alerts.ledger, "load", lambda path=None: _picks(0))
    kick = (NOW + pd.Timedelta(minutes=14)).isoformat()
    monkeypatch.setattr(alerts, "fun_slates", lambda: [
        {"slate": "d-ncaaf-noon", "sport": "ncaaf", "title": "College football noon games", "kickoff": kick, "locked_at": "t",
         "plus": {"n_games": 4, "n_legs": 5, "fair_price": 1173}},
        {"slate": "d-ncaaf-night", "sport": "ncaaf", "kickoff": kick, "plus": {"n_games": 3}}])     # not locked yet
    tags = []
    out = alerts.run(now=NOW, send=lambda sub, msg, key: tags.append(msg["tag"]) or 201, db_url="postgres://x", private_key="k")
    assert out.startswith("alerts: 0 new pick(s) and 1 locked ticket(s) sent")
    assert set(tags) == {"lock-d-ncaaf-noon"} and "lock:d-ncaaf-noon" in db.sent
    assert alerts.run(now=NOW, send=lambda *a: 201, db_url="postgres://x", private_key="k") == "alerts: no new picks or locked tickets"


def test_a_watched_games_slips_lock_and_alert_by_their_game():
    """Nov 7 (Mike): an account hears of the slips of the games it watches, when they lock, and "locks on a sgp
    shouldn't depend on slices at all": a game's slips lock and alert by its own start; slice alerts are tickets only."""
    from betlab import alerts

    now = pd.Timestamp("2026-10-12T00:00:30Z")
    base = {"event_id": "e1", "matchup": "Baltimore Ravens @ Atlanta Falcons", "commence_time": "2026-10-12T00:20:00Z",
            "sport": "nfl", "locked_at": "2026-10-12T00:00:10+00:00"}
    slips = [base | {"sgp_id": f"s{p}", "fair_price": p} for p in (271, 239, 306)]
    slips.append(base | {"sgp_id": "long", "fair_price": 4007, "longshot": True})
    later = {"sgp_id": "k1", "event_id": "e2", "matchup": "New York Knicks @ Cleveland Cavaliers", "sport": "nba",
             "commence_time": "2026-10-12T01:10:00Z", "fair_price": 300}            # same slice, its own lock still ahead
    night = {"slate": "2026-10-11-night", "title": "NFL night games", "sport": "nfl", "kickoff": "2026-10-12T00:20:00Z",
             "n_games": 2, "plus": None, "td": None, "sgps": slips + [later], "locked_at": "2026-10-12T00:00:10+00:00"}
    assert alerts.locked([night], set(), now) == [] and alerts.lock_message(night) is None   # no ticket: no slice alert
    got = alerts.slip_locks([night], set(), now)
    assert list(got) == ["e1"] and len(got["e1"]) == 4                                       # e2 isn't locked yet
    msg = alerts.slips_message(got["e1"])
    assert msg["title"] == "Locked: Ravens @ Falcons slips"
    assert msg["body"].startswith("Baltimore Ravens @ Atlanta Falcons: 3 slips, fair +239 to +306 plus a long shot. Start 8:20 PM ET")
    assert alerts.slip_locks([night], {"slips:e1"}, now) == {}                              # announced once
    single = alerts.slips_message([later | {"style": "single"}])
    assert single["title"] == "Locked: Knicks @ Cavaliers pick" and "best single" in single["body"] and "Tip-off 9:10 PM" in single["body"]
    # next to a ticket, the slice's alert names only the ticket
    noon = night | {"title": "NFL early games", "plus": {"n_games": 2, "n_legs": 6, "fair_price": 900}}
    assert alerts.lock_message(noon)["title"] == "Locked: NFL early games SGP+"


def test_a_pick_alert_carries_both_books_prices():
    """Mike, Oct 12: alerts show both books' prices, the better first."""
    p = _picks(1).assign(market="spreads", point=-0.5, book="draftkings", other_book="fanduel", other_point=-0.5, other_price=-115.0, price=-105.0)
    m = alerts.messages(p)[0]
    assert m["title"] == "NBA pick: Boston Celtics -0.5 · DraftKings -105 · FanDuel -115"
    assert m["body"].endswith("1u at DraftKings")
    moved = _picks(1).assign(market="spreads", point=-0.5, book="fanduel", other_book="draftkings", other_point=-1.5, other_price=105.0)
    assert alerts.messages(moved)[0]["title"].endswith("· FanDuel -110 · DraftKings (-1.5) +105")


def test_an_account_with_a_book_off_is_alerted_at_its_own_books():
    """Nov 6 (0043): the ledger keeps the first book a pick qualified at; the card's books list re-reads it per account."""
    import pandas as pd

    from betlab import alerts as al
    rows = pd.DataFrame([{"pick_id": "p1", "tier": "pick", "league": "nfl", "book": "novig", "price": 120.0, "point": 3.5,
                          "ev": 0.05, "units_tier": 1.5, "label": "Bills +3.5", "market": "spreads",
                          "matchup": "Bills @ Jets", "commence_time": "2026-11-08T18:00:00Z"}])
    reads = {"p1": {"books": [{"book": "FanDuel", "price": -110.0, "point": 3.5, "ev": 0.005, "tier": None},
                              {"book": "DraftKings", "price": 105.0, "point": 3.5, "ev": 0.035, "tier": "lean", "units_tier": None},
                              {"book": "Novig", "price": 120.0, "point": 3.5, "ev": 0.05, "tier": "pick", "units_tier": 1.5}]}}
    assert al.at_account_books(rows, [], reads) is rows
    got = al.at_account_books(rows, ["Novig"], reads).iloc[0]
    assert (got["book"], got["price"], got["tier"], got["other_book"]) == ("draftkings", 105.0, "lean", "fanduel")
    assert al.at_account_books(rows, ["Novig", "DraftKings"], reads).empty
    assert al.at_account_books(rows, ["Novig"], {}).empty                 # no card read: its book is off, so nothing


def test_a_lock_alert_says_where_it_opens_at_the_accounts_books():
    from betlab import alerts as al
    assert al._open_at(None) == " Open BetLab to open it in FanDuel or price it at DraftKings."
    assert al._open_at(["DraftKings", "Novig"]) == " Open BetLab to price it at DraftKings."
    assert al._open_at(["Novig"]) == " Open BetLab to price it at Novig."
