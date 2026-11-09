"""Live Activities (live_activity.py): what the lock screen shows, when the worker starts, updates and ends each one,
and that the pushes reach only the bettor's iPhones. The content's keys are the app's BetActivityAttributes.ContentState."""

import json
from datetime import datetime, timezone

from betlab import leg_alerts as LA
from betlab import live_activity as A
from test_live_legs import BET, _board

NOW = 1_800_000_000.0


def _live(tcu, akron):
    lives: dict = {}
    LA.check([(BET, None)], {"seen:b1"}, get=_board(tcu, akron), lives=lives)
    return lives["b1"][1]


def test_the_content_shows_scores_and_each_leg():
    c = A.content(_live(("post", 30, 27), ("in", 10, 3)))
    assert c["status"] == "lost" and (c["hit"], c["total"], c["more"]) == (0, 2, 0)
    assert c["games"][0] == {"away": "WVU", "home": "TCU", "awayScore": "27", "homeScore": "30", "state": "post", "detail": "Q4", "awayColor": None, "homeColor": None,
                               "awayLogo": None, "homeLogo": None}
    assert [l["label"] for l in c["legs"]] == ["TCU Horned Frogs -10.5", "Akron Zips +2.5"]     # the bet's own order
    assert [l["status"] for l in c["legs"]] == ["lost", "losing"]                       # Akron down 7
    assert c["legs"][1]["value"] == "-7" and c["note"] is None
    assert [l["game"] for l in c["legs"]] == [0, 1]                                  # each under its own game
    assert set(c) == {"status", "hit", "total", "games", "legs", "more", "note"}


def test_a_prop_shows_its_count_and_progress():
    v = A.leg_view({"label": "Josh Allen 250+ passing yds", "status": "live", "current": 180, "target": 250, "unit": "yds",
                    "text": ""})
    assert v == {"label": "Josh Allen 250+ passing yds", "status": "live", "value": "180/250 yds", "progress": 0.72}
    t = A.leg_view({"label": "Over 47.5", "status": "live", "current": 51, "target": 47.5, "unit": "total", "text": ""})
    assert t["value"] == "51/47.5" and t["progress"] == 1.0


def test_every_game_over_with_legs_still_open_is_final():
    live = {"legs": [{"label": "x", "status": "unknown", "current": None, "target": None, "unit": "", "text": ""}],
            "games": [{"sport": "nfl", "state": "post", "detail": "Final", "home": {"abbr": "A", "score": 1},
                       "away": {"abbr": "B", "score": 0}}], "status": "live", "hit": 0, "total": 1}
    assert A.content(live)["status"] == "final"


def _tokens():
    return {"u1": {"start": [("production", "aa" * 32)], "b1": [("production", "bb" * 32)]}}


def test_a_bet_starts_once_its_first_game_is_on():
    lives = {"b1": (BET, _live(("pre", None, None), ("pre", None, None)))}
    assert A.plan(lives, {}, _tokens(), {}, NOW) == []                                    # nothing on yet
    lives = {"b1": (BET, _live(("in", 7, 0), ("pre", None, None)))}
    [a] = A.plan(lives, {}, _tokens(), {}, NOW)
    assert a["event"] == "start" and a["to"] == [("production", "aa" * 32)] and a["priority"] == 10
    aps = a["body"]["aps"]
    assert aps["attributes-type"] == "BetActivityAttributes" and aps["attributes"]["betId"] == "b1"
    assert aps["attributes"]["name"] == "2-leg parlay (+940)" and aps["alert"]["body"] == "Game on: WVU @ TCU"
    assert aps["content-state"]["status"] == "live" and aps["stale-date"] == int(NOW + A.STALE)
    assert A.plan(lives, {}, {"u1": {}}, {}, NOW) == []                                   # no iPhone token: nothing


def test_no_more_than_three_live_at_once():
    lives = {"b1": (BET, _live(("in", 7, 0), ("pre", None, None)))}
    lives |= {f"x{i}": ({**BET, "bet_id": f"x{i}"}, lives["b1"][1]) for i in range(A.MAX_ACTIVE)}
    state = {f"x{i}": {"user_id": "u1", "content": A.content(lives["b1"][1]), "sent_at": NOW, "ended": False}
             for i in range(A.MAX_ACTIVE)}
    assert [a["event"] for a in A.plan(lives, state, _tokens(), {}, NOW) if a["bet_id"] == "b1"] == []


def test_updates_go_on_change_or_heartbeat_and_end_when_settled():
    live = _live(("in", 7, 0), ("pre", None, None))
    row = {"user_id": "u1", "content": A.content(live), "sent_at": NOW - 60, "ended": False}
    assert A.plan({"b1": (BET, live)}, {"b1": row}, _tokens(), {}, NOW) == []             # nothing new
    [a] = A.plan({"b1": (BET, live)}, {"b1": {**row, "sent_at": NOW - A.HEARTBEAT}}, _tokens(), {}, NOW)
    assert a["event"] == "update" and a["priority"] == 5 and a["to"] == [("production", "bb" * 32)]
    moved = _live(("in", 14, 0), ("pre", None, None))                                    # a score: low priority
    [a] = A.plan({"b1": (BET, moved)}, {"b1": row}, _tokens(), {}, NOW)
    assert a["event"] == "update" and a["priority"] == 5
    note = {"title": "Leg hit", "body": "TCU Horned Frogs -10.5 (WVU 0-38 TCU)."}
    hit = _live(("post", 38, 0), ("in", 3, 0))                                            # a leg settled: high
    [a] = A.plan({"b1": (BET, hit)}, {"b1": row}, _tokens(), {"b1": note}, NOW)
    assert a["priority"] == 10 and a["content"]["note"].startswith("Leg hit: TCU")
    done = _live(("post", 38, 0), ("post", 21, 20))
    [a] = A.plan({"b1": (BET, done)}, {"b1": row}, _tokens(), {}, NOW)
    assert a["event"] == "end" and a["body"]["aps"]["dismissal-date"] == int(NOW + A.LINGER)
    assert a["content"]["status"] == "won"


def test_a_bet_that_left_the_open_list_ends_as_final():
    row = {"user_id": "u1", "content": A.content(_live(("in", 7, 0), ("pre", None, None))), "sent_at": NOW, "ended": False}
    [a] = A.plan({}, {"b1": row}, _tokens(), {}, NOW)
    assert a["event"] == "end" and a["content"]["status"] == "final" and a["to"] == [("production", "bb" * 32)]
    assert A.plan({}, {"b1": {**row, "ended": True}}, _tokens(), {}, NOW) == []


class _Cur:
    def __init__(self, rows=()):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, state=(), tokens=()):
        self.state, self.tokens, self.writes = list(state), list(tokens), []

    def execute(self, sql, params=None):
        if sql.startswith("select") and "live_activity_state" in sql:
            return _Cur(self.state)
        if sql.startswith("select") and "live_activity_tokens" in sql:
            assert params == [["u1"]]
            return _Cur(self.tokens)
        self.writes.append((sql.split()[0], sql, params))
        return _Cur()


def test_tick_starts_records_and_drops_gone_tokens():
    lives = {"b1": (BET, _live(("in", 7, 0), ("pre", None, None)))}
    c = _Conn(tokens=[("u1", "aa" * 32, "production", "start", None), ("u1", "cc" * 32, "sandbox", "start", None)])
    posts = []

    def post(env, token, headers, body):
        posts.append((env, token, headers["apns-push-type"], headers["apns-topic"], body["aps"]["event"]))
        return 200 if token == "aa" * 32 else 410

    line = A.tick(c, lives, {}, datetime.fromtimestamp(NOW, timezone.utc), post=post)
    assert posts[0] == ("production", "aa" * 32, "liveactivity", "com.mopsha.betlab.push-type.liveactivity", "start")
    assert line == "live activities: start b1 -> 1 of 2"
    kinds = [(w[0], w[2][0] if w[2] else None) for w in c.writes]
    assert ("delete", "cc" * 32) in kinds and ("insert", "b1") in kinds
    assert json.loads(next(w[2][2] for w in c.writes if w[0] == "insert"))["status"] == "live"


def test_tick_waits_for_an_update_token_and_ends_closed_bets():
    live = _live(("in", 14, 0), ("pre", None, None))
    old = A.content(_live(("in", 7, 0), ("pre", None, None)))
    c = _Conn(state=[("b1", "u1", old, datetime.fromtimestamp(NOW - 60, timezone.utc), None)])
    posts = []
    assert A.tick(c, {"b1": (BET, live)}, {}, post=lambda *a: posts.append(a) or 200) == ""   # no update token yet
    assert posts == [] and c.writes == []
    c = _Conn(state=[("b1", "u1", json.dumps(old), datetime.fromtimestamp(NOW - 60, timezone.utc), None)],
              tokens=[("u1", "bb" * 32, "production", "update", "b1")])
    assert A.tick(c, {}, {}, post=lambda *a: 200) == "live activities: end b1 -> 1 of 1"
    sqls = [w[1] for w in c.writes]
    assert any("ended_at = now()" in s for s in sqls) and any("kind = 'update'" in s for s in sqls)


def test_an_iphone_that_registered_after_the_start_gets_it_once():
    live = _live(("in", 7, 0), ("pre", None, None))
    row = {"user_id": "u1", "content": A.content(live), "sent_at": NOW - 600, "ended": False}
    phone = ("production", "dd" * 32)
    toks = {"u1": {"start": [("sandbox", "aa" * 32), phone], "since": {"aa" * 32: NOW - 900, "dd" * 32: NOW - 60}}}
    [a] = A.plan({"b1": (BET, live)}, {"b1": row}, toks, {}, NOW)
    assert a["event"] == "start" and a["to"] == [phone] and a["body"]["aps"]["alert"]["body"] == "Game on: WVU @ TCU"
    assert A.plan({"b1": (BET, live)}, {"b1": {**row, "sent_at": NOW, "starts": 2}}, toks, {}, NOW) == []  # not again
    toks["u1"]["b1"] = [phone]                                                                   # it started there
    assert A.plan({"b1": (BET, live)}, {"b1": {**row, "sent_at": NOW - A.HEARTBEAT}}, toks, {}, NOW)[0]["event"] == "update"


def test_a_start_no_iphone_confirmed_goes_once_more():
    live = _live(("in", 7, 0), ("pre", None, None))
    row = {"user_id": "u1", "content": A.content(live), "sent_at": NOW - A.RETRY + 30, "ended": False, "starts": 1}
    assert A.plan({"b1": (BET, live)}, {"b1": row}, {"u1": {"start": [("production", "aa" * 32)]}}, {}, NOW) == []
    row["sent_at"] = NOW - A.RETRY
    [a] = A.plan({"b1": (BET, live)}, {"b1": row}, {"u1": {"start": [("production", "aa" * 32)]}}, {}, NOW)
    assert a["event"] == "start" and a["body"]["aps"]["alert"]["title"] == "2-leg parlay (+940)"
    assert A.plan({"b1": (BET, live)}, {"b1": {**row, "starts": A.MAX_STARTS}},
                  {"u1": {"start": [("production", "aa" * 32)]}}, {}, NOW) == []


def test_a_game_to_come_shows_its_time_and_no_score():
    g = A.game_view({"sport": "nba", "state": "pre", "detail": "10/27 - 8:00 PM EDT", "home": {"abbr": "NY", "score": 0},
                     "away": {"abbr": "DET", "score": 0}})
    assert (g["awayScore"], g["homeScore"], g["detail"]) == (None, None, "8:00 PM")
    leg = A.leg_view({"label": "Jalen Brunson over 1.5 threes", "status": "pending", "current": 0, "target": 2,
                      "unit": "3PM", "text": "Not started"})
    assert leg["value"] == "0/2 3s" and leg["progress"] is None


def test_to_win_includes_the_boost():
    assert A.to_win({"price": 806, "stake": 1, "boost": 30}) == "10.48u"
    assert A.to_win({"price": -125, "stake": 2}) == "1.60u" and A.to_win({"price": None}) is None


def test_team_colors_skip_near_black_and_white():
    from betlab import live_legs
    assert live_legs.team_color("002654", "ce1126") == "#002654"
    assert live_legs.team_color("000000", "fdb927") == "#fdb927" and live_legs.team_color("ffffff", None) is None


def test_a_confirmed_card_resets_its_starts_so_a_lost_one_comes_back():
    live = _live(("in", 7, 0), ("pre", None, None))
    old = A.content(live)
    c = _Conn(state=[("b1", "u1", old, datetime.fromtimestamp(NOW - 60, timezone.utc), None, 2)],
              tokens=[("u1", "bb" * 32, "production", "update", "b1", None)])
    A.tick(c, {"b1": (BET, live)}, {}, datetime.fromtimestamp(NOW, timezone.utc), post=lambda *a: 200)
    assert any("starts = 0" in w[1] for w in c.writes)
    lost = {"user_id": "u1", "content": old, "sent_at": NOW - A.RETRY, "ended": False, "starts": 0}
    [a] = A.plan({"b1": (BET, live)}, {"b1": lost}, {"u1": {"start": [("production", "aa" * 32)]}}, {}, NOW)
    assert a["event"] == "start" and a["body"]["aps"]["alert"]
