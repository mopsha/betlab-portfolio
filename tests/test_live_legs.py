"""Leg push alerts (Oct 24): the Python port of the live tracker and the alert loop."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from betlab import leg_alerts as LA
from betlab import live_legs as L

FIX = json.loads((Path(__file__).parent / "fixtures" / "live_legs.json").read_text(encoding="utf-8"))


def _game(spec: dict, key: str = "g1") -> dict:
    side = lambda s: {"name": s[0], "abbr": s[1], "score": s[2]}   # noqa: E731
    g = {"key": key, "sport": spec["sport"], "espn_id": "1", "state": spec["state"], "detail": "Q3 4:12",
         "start": "2026-10-24T16:00:00Z", "home": side(spec["home"]), "away": side(spec["away"])}
    if "winner" in spec:
        g["winner"] = spec["winner"]
    return g


@pytest.mark.parametrize("case", FIX["parse"], ids=lambda c: c["label"])
def test_labels_parse_as_the_web_tracker_does(case):
    assert L.parse_leg(case["label"]) == case["expect"]


@pytest.mark.parametrize("case", FIX["judge"], ids=lambda c: f"{c['label']} {c['game']['state']}")
def test_legs_judge_as_the_web_tracker_does(case):
    got = L.judge(case["label"], _game(case["game"]), case.get("box"))
    assert {k: got[k] for k in case["expect"]} == case["expect"]


@pytest.mark.parametrize("case", FIX["days"], ids=lambda c: c["why"])
def test_a_bets_game_is_looked_for_on_its_own_days(case):
    now = datetime.fromisoformat(case["now"].replace("Z", "+00:00"))
    assert L.search_days(case["bet"], case["group"], case["open"], now, case["single"]) == case["expect"]


def test_a_dead_heat_or_a_push_never_settles_at_the_full_price():
    won, heat, void = {"status": "won"}, {"status": "won", "deadHeat": True}, {"status": "void"}
    post = [{"state": "post"}]
    assert L.rollup([won, won], post)["settle"] == "won"
    assert "settle" not in L.rollup([won, heat], post) and L.rollup([won, heat], post)["status"] == "won"
    assert "settle" not in L.rollup([won, void], post)
    assert L.rollup([won, {"status": "lost"}], post)["settle"] == "lost"


def test_one_leg_left_counts_a_pushed_leg_out():
    legs = [{"status": "void", "label": "A +3"}, {"status": "won", "label": "B ML"}, {"status": "winning", "label": "C ML"}]
    evs = LA.events("v1", {"legs": legs, "status": "live", "hit": 1}, set())
    assert ("bet:v1:one_left", "one_left") in evs
    lost = [{"status": "lost", "label": "A +3"}, {"status": "won", "label": "B ML"}, {"status": "winning", "label": "C ML"}]
    assert ("bet:v1:one_left", "one_left") not in LA.events("v2", {"legs": lost, "status": "lost", "hit": 1}, set())


def test_an_open_bet_is_looked_for_on_its_games_days_in_the_worker(monkeypatch):
    asked = []
    bet = {**BET, "placed_at": "2026-11-08T00:21:00Z", "games": [{**BET["games"][0], "game_ref": "ncaaf:9"}]}
    bet["game_starts"] = {"ncaaf:9": "2026-11-08T00:30:00Z"}
    LA.check([(bet, None)], set(), now=datetime(2026, 11, 9, 10, tzinfo=L.ET), get=lambda u, t=None: asked.append(u) or {})
    assert sorted(u.split("dates=")[1][:8] for u in asked) == ["20261107", "20261108"]


def test_teams_and_games_match_like_the_web():
    assert L.is_team("NJD", {"name": "New Jersey Devils", "abbr": "NJ"})
    assert L.is_team("Borussia Monchengladbach", {"name": "Borussia Mönchengladbach", "abbr": "BMG"})
    assert not L.is_team("Celta Vigo", {"name": "Celtic", "abbr": "CEL"})
    games = [_game({"sport": "ncaaf", "state": "pre", "home": ["Kent State Golden Flashes", "KENT", None],
                    "away": ["Akron Zips", "AKR", None]})]
    assert L.find_game(games, "Akron Zips @ Kent State Golden Flashes") is games[0]
    assert L.find_game(games, "Ohio Bobcats @ Kent State Golden Flashes") is None


def test_the_best_named_game_wins_over_a_shared_word():
    # Oct 24: "State" is in both pairs; the live Sacramento State game must not take Boise State's leg
    sac = _game({"sport": "ncaaf", "state": "in", "home": ["Ball State Cardinals", "BALL", 0], "away": ["Sacramento State Hornets", "SAC", 3]})
    boise = _game({"sport": "ncaaf", "state": "pre", "home": ["Washington State Cougars", "WSU", None], "away": ["Boise State Broncos", "BSU", None]})
    assert L.find_game([sac, boise], "Boise State Broncos @ Washington State Cougars") is boise


def test_ref_sport_reads_every_ref_shape():
    assert L.ref_sport("ncaaf:401856841") == ("ncaaf", None)
    assert L.ref_sport("epl|Chelsea|Tottenham Hotspur|2026-10-24T16:30:00+00:00") == ("soccer", "epl")
    assert L.ref_sport("2026_07_NE_CHI") == ("nfl", None)
    assert L.ref_sport("ufc:600061267:401911639") == ("ufc", None)


# ------------------------------------------------------------------------------------------------ the alerts

BET = {"bet_id": "b1", "user_id": "u1", "kind": "custom", "sgp_id": "custom-x", "price": 940, "label": "Bonus bet $5",
       "matchup": "Parlay", "legs": None, "league": None, "sport": None,
       "games": [{"legs": ["TCU Horned Frogs -10.5"], "matchup": "West Virginia Mountaineers @ TCU Horned Frogs",
                  "game_ref": "ncaaf:1"},
                 {"legs": ["Akron Zips +2.5"], "matchup": "Akron Zips @ Kent State Golden Flashes", "game_ref": "ncaaf:2"}]}


def _board(tcu: tuple, akron: tuple):
    """A fake ESPN getter: the college board with these two games ((state, home score, away score) each)."""
    def comp(cid, state, home, away, hs, as_):
        return {"id": cid, "date": "2026-10-24T16:00:00Z", "status": {"type": {"state": state, "shortDetail": "Q4"}},
                "competitors": [{"homeAway": "home", "score": "" if hs is None else str(hs),
                                 "team": {"displayName": home[0], "abbreviation": home[1]}},
                                {"homeAway": "away", "score": "" if as_ is None else str(as_),
                                 "team": {"displayName": away[0], "abbreviation": away[1]}}]}
    board = {"events": [
        {"id": "1", "competitions": [comp("1", tcu[0], ("TCU Horned Frogs", "TCU"), ("West Virginia Mountaineers", "WVU"), tcu[1], tcu[2])]},
        {"id": "2", "competitions": [comp("2", akron[0], ("Kent State Golden Flashes", "KENT"), ("Akron Zips", "AKR"), akron[1], akron[2])]}]}

    def get(url, ttl=None):
        return board if "college-football/scoreboard" in url else {}
    return get


def _run(get, sent):
    found = LA.check([(BET, None)], sent, get=get)
    for _, keys, _ in found:
        sent |= set(keys)
    return [m for _, _, m in found]


def test_first_look_is_silent_then_each_event_fires_once():
    sent: set = set()
    assert _run(_board(("pre", None, None), ("pre", None, None)), sent) == [None]          # first look: recorded only
    assert "seen:b1" in sent
    msgs = _run(_board(("post", 38, 20), ("in", 17, 14)), sent)                           # TCU covers, Akron still going
    assert len(msgs) == 1 and msgs[0]["title"] == "One leg left"
    assert "TCU Horned Frogs -10.5" in msgs[0]["body"] and "needs Akron Zips +2.5" in msgs[0]["body"]
    assert _run(_board(("post", 38, 20), ("in", 17, 14)), sent) == []                     # nothing new: no repeat
    msgs = _run(_board(("post", 38, 20), ("post", 21, 20)), sent)                         # Akron covers: a winner
    assert [m["title"] for m in msgs] == ["Winner"]
    assert _run(_board(("post", 38, 20), ("post", 21, 20)), sent) == []


def test_a_lost_leg_ends_the_bet_and_its_alerts():
    sent = {"seen:b1"}
    msgs = _run(_board(("post", 30, 27), ("in", 10, 3)), sent)                            # TCU won by 3: -10.5 lost
    assert msgs[0]["title"] == "Leg lost" and "is done" in msgs[0]["body"]
    assert _run(_board(("post", 30, 27), ("post", 10, 13)), sent) == []                   # Akron wins later: silence


def test_a_bet_entered_after_a_leg_hit_does_not_replay_it():
    sent: set = set()
    assert _run(_board(("post", 38, 20), ("in", 17, 14)), sent) == [None]
    assert "leg:b1:0:won" in sent and "bet:b1:one_left" in sent
    assert _run(_board(("post", 38, 20), ("in", 17, 14)), sent) == []


def test_a_single_bet_only_says_won_or_lost():
    single = {**BET, "bet_id": "s1", "price": 250, "games": [BET["games"][1]]}
    sent = {"seen:s1"}
    found = LA.check([(single, None)], sent, get=_board(("pre", None, None), ("post", 24, 20)))
    assert found[0][2]["title"] == "Bet lost" and found[0][1] == ["leg:s1:0:lost"]


def test_run_sends_to_the_bettors_devices_only(monkeypatch):
    calls = []

    class Cur:
        def __init__(self, rows=()):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            if "from my_bets" in sql:
                return Cur([("b1", "u1", "custom", "custom-x", 940, "Bonus bet $5", "Parlay", None, json.dumps(BET["games"]),
                             None, None, None)])
            if "from alerts_sent" in sql:
                return Cur([("seen:b1",)])
            if "from push_subscriptions" in sql:
                assert params == ["u1"]
                return Cur([("u1", "apns:production:tok", None, None)])
            calls.append((sql.split()[0], params))
            return Cur()

    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: Conn())
    sent = []
    line = LA.run(send=lambda sub, msg, key: sent.append((sub["endpoint"], msg["title"])) or 200, db_url="postgres://x",
                  get=_board(("post", 38, 20), ("in", 17, 14)))
    assert sent == [("apns:production:tok", "One leg left")]
    assert "1 of 1 device(s)" in line
    assert {p[0] for s, p in calls if s == "insert"} == {"leg:b1:0:won", "bet:b1:one_left"}


def test_a_pink_account_hears_the_same_facts_in_diva_words():
    """Mike, Oct 25: the Pink theme's account (his girlfriend's) gets "diva" alerts, gentler on a loss."""
    pink = {**BET, "theme": "pink"}
    sent = {"seen:b1"}
    found = LA.check([(pink, None)], sent, get=_board(("post", 30, 27), ("in", 10, 3)))
    msg = found[0][2]
    assert msg["title"] == "Not this one, diva 💔" and "TCU Horned Frogs -10.5 didn't come through" in msg["body"]
    sent = {"seen:b1", "leg:b1:0:won", "bet:b1:one_left"}
    found = LA.check([(pink, None)], sent, get=_board(("post", 38, 20), ("post", 21, 20)))
    assert found[0][2]["title"] == "DIVA, YOU WON 💅💸" and "Obviously" in found[0][2]["body"]
    assert LA.check([(BET, None)], {"seen:b1"}, get=_board(("post", 30, 27), ("in", 10, 3)))[0][2]["title"] == "Leg lost"


def test_rush_plus_rec_grades_as_the_sum():
    """Mike, Oct 25: "rushing + receiving ... it's literally addition". The grader reads a slip's wording too."""
    import pandas as pd
    from betlab import fun_ledger
    assert fun_ledger.parse_leg("Christian McCaffrey 100+ rushing + receiving yds") == \
        {"player": "Christian McCaffrey", "stat": "rush_rec_yards", "side": "over", "point": 99.5}
    assert fun_ledger.parse_leg("Bijan Robinson 50+ rushing yards")["stat"] == "rushing_yards"
    ps = pd.DataFrame([{"game_id": "g", "player_id": "cmc", "player_display_name": "Christian McCaffrey",
                        "rushing_yards": 62.0, "receiving_yards": 41.0}])
    sn = pd.DataFrame([{"game_id": "g", "player_id": "cmc", "player": "Christian McCaffrey", "offense_snaps": 50}])
    res = fun_ledger.nfl_leg_results(["Christian McCaffrey 100+ rushing + receiving yds"], ["g"], ps, sn,
                                     pd.DataFrame().rename_axis("game_id"), {})
    assert res[0]["value"] == 103.0 and res[0]["result"] == "won"


def test_bet_names_follow_the_shared_cases():
    # tests/fixtures/bet_names.json: the same cases web/tests/gameday.test.mjs and GameDayTests.swift run
    from betlab import leg_alerts
    fix = json.loads((Path(__file__).parent / "fixtures" / "bet_names.json").read_text())
    for c in fix["cases"]:
        legs = c.get("legs") or []
        n = c.get("n") or len(legs or ([c["label"]] if c.get("label") else []))
        if n > 1:
            name = leg_alerts.parlay_name(legs, n)
            price = c.get("price")
            want = c["name"] if price is None else c["name"].rsplit(" ", 1)[0]
            assert name == want, legs


def test_new_stats_settle_from_espns_box_when_a_grader_cant_read_them():
    """Nov 6: a slip leg on a stat the sport grader doesn't read (longest reception, "most receiving yards") settles from
    ESPN's final box through the trackers' reader instead of sitting "unknown" (which holds a winning slip open for good)."""
    from betlab import fun_ledger as F
    board = {"events": [{"id": "9", "date": "2026-11-06T01:15Z", "status": {"type": {"state": "post", "detail": "Final"}},
                         "competitions": [{"competitors": [
                             {"homeAway": "home", "score": "10", "team": {"displayName": "Baltimore Ravens", "abbreviation": "BAL", "shortDisplayName": "Ravens"}},
                             {"homeAway": "away", "score": "33", "team": {"displayName": "Jacksonville Jaguars", "abbreviation": "JAX", "shortDisplayName": "Jaguars"}}]}]}]}
    summary = {"boxscore": {"players": [{"statistics": [
        {"name": "receiving", "keys": ["receptions", "receivingYards", "longReception"],
         "athletes": [{"athlete": {"displayName": "Parker Washington"}, "stats": ["2", "61", "50"]},
                      {"athlete": {"displayName": "Justice Hill"}, "stats": ["3", "7", "3"]}]}]}]}}
    get = lambda url, *a: board if "scoreboard" in url else summary
    r = {"leg_games": json.dumps(["2026_09_JAX_BAL"] * 3), "matchup": "", "sport": "nfl", "quoted_at": "2026-11-05T23:00:00Z"}
    legs = [{"leg": "Parker Washington over 40.5 longest reception", "result": "unknown", "value": None},
            {"leg": "Parker Washington most receiving yards", "result": "unknown", "value": None},
            {"leg": "Justice Hill 2+ receptions", "result": "won", "value": 3}]
    out = F.espn_unknown(r, legs, get)
    assert [x["result"] for x in out] == ["won", "won", "won"]
    assert out[0]["value"] == 50 and out[1]["value"] == 61


@pytest.mark.parametrize("case", FIX["plays"], ids=lambda c: c["sport"])
def test_the_shared_play_by_play_gives_the_same_stats(case):
    """Nov 6: quarter and period stats, first basket / goal / TD, longest completion and power-play points from ESPN's
    play-by-play (play_stats); web and iPhone parse the same summaries to the same rows."""
    assert L.parse_box(case["summary"], case["sport"]) == case["expect"]
