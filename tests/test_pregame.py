"""The new schedule's pre-game pulls (pregame.py): each game once, inside its sport's window, merged
into the latest snapshot so other games keep their morning prices (fake odds client, temp data)."""

import pandas as pd
import pytest

from betlab import config, news, pregame
from betlab.sources import odds_api

NOW = pd.Timestamp("2026-10-25T16:00:00Z")          # Sunday 12:00 PM ET


def _event(eid, mins, home="Home", away="Away"):
    return {"id": eid, "commence_time": (NOW + pd.Timedelta(minutes=mins)).isoformat().replace("+00:00", "Z"),
            "home_team": home, "away_team": away}


def _payload(ev, market="spreads", price=-110):
    return {**ev, "bookmakers": [{"key": "fanduel", "markets": [{"key": market, "outcomes": [
        {"name": ev["home_team"], "price": price, "point": -3.5}, {"name": ev["away_team"], "price": price, "point": 3.5}]}]}]}


class FakeClient:
    def __init__(self, events):
        self.events_by_sport, self.calls = events, []

    def events(self, sport):
        return self.events_by_sport.get(sport, [])

    def odds(self, sport, markets=None, priority="normal", event_ids=None):
        self.calls.append(("odds", sport, tuple(event_ids or ())))
        return [_payload(e, price=-105) for e in self.events_by_sport[sport] if e["id"] in (event_ids or [])]

    def event_odds(self, sport, eid, markets, priority="normal"):
        self.calls.append(("props", sport, eid))
        ev = next(e for e in self.events_by_sport[sport] if e["id"] == eid)
        return _payload(ev, market="player_receptions")


NEWS = {"injuries": {"home": ["A Starter:Questionable"], "away": []}}


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(news, "sources", lambda league, now: {k: dict(v) for k, v in NEWS.items()})
    s = config.settings()
    monkeypatch.setitem(s["schedule"], "pregame", {"nfl": [30, 85], "ncaaf": [30, 85], "soccer": [15, 55]})
    return tmp_path


def test_each_game_once_inside_its_window_with_props_only_where_allowed(data):
    nfl = "americanfootball_nfl"
    client = FakeClient({nfl: [_event("now", 60), _event("later", 260), _event("soon", 20)],
                         "americanfootball_ncaaf": [_event("cfb", 70)]})
    out = pregame.run(client, NOW)
    assert ("odds", nfl, ("now",)) in client.calls and ("props", nfl, "now") in client.calls
    assert not any(c[0] == "props" and c[1].endswith("ncaaf") for c in client.calls)   # NY: no college props
    assert len(out) == 2 and out[0].startswith("nfl: 1 game(s) in the 30-85 min window")
    client.calls.clear()
    assert pregame.run(client, NOW + pd.Timedelta(minutes=15)) == []                  # already pulled
    assert client.calls == []


def test_one_league_failing_still_pulls_the_others(data):
    nfl = "americanfootball_nfl"

    class Flaky(FakeClient):
        def events(self, sport):
            if sport == nfl:
                raise odds_api.OddsApiError("/sports/americanfootball_nfl/events failed (free key): HTTP 502")
            return super().events(sport)

    client = Flaky({nfl: [_event("now", 60)], "americanfootball_ncaaf": [_event("cfb", 70)]})
    with pytest.raises(pregame.PregameError) as exc:
        pregame.run(client, NOW)
    assert ("odds", "americanfootball_ncaaf", ("cfb",)) in client.calls
    assert exc.value.done[0].startswith("ncaaf: 1 game(s)") and exc.value.failed[0].startswith("nfl: ")


def test_one_games_refused_props_leave_it_for_the_next_tick(data, monkeypatch):
    """Nov 2: one 429 on an NBA props call stopped the 8 PM tick, every league after it included."""
    monkeypatch.setitem(config.settings()["schedule"], "pregame", {"nfl": [15, 90], "ncaaf": [15, 90]})
    nfl = "americanfootball_nfl"

    class Refuses(FakeClient):
        refuse = True

        def event_odds(self, sport, eid, markets, priority="normal"):
            if self.refuse and eid == "bad":
                raise odds_api.OddsApiError("failed on every key: paid: HTTP 429")
            return super().event_odds(sport, eid, markets, priority)

    client = Refuses({nfl: [_event("bad", 60), _event("good", 60)], "americanfootball_ncaaf": [_event("cfb", 70)]})
    with pytest.raises(pregame.PregameError) as exc:
        pregame.run(client, NOW)
    assert ("odds", "americanfootball_ncaaf", ("cfb",)) in client.calls               # the next league still ran
    assert len(exc.value.failed) == 1 and "bad" in exc.value.failed[0]
    client.calls.clear()
    client.refuse = False
    pregame.run(client, NOW + pd.Timedelta(minutes=15))
    assert ("odds", nfl, ("bad",)) in client.calls                                    # only the missed game again
    assert not any(c[0] == "odds" and "good" in c[2] for c in client.calls)


def test_a_pull_keeps_the_other_games_morning_prices(data):
    nfl = "americanfootball_nfl"
    morning = pd.DataFrame([{"snapshot_ts": "2026-10-25T14:00:00Z", "event_id": e, "commence_time": t,
                             "bookmaker": "fanduel", "market": "spreads", "outcome": "Home", "price": -110}
                            for e, t in (("now", "2026-10-25T17:00:00Z"), ("later", "2026-10-25T20:20:00Z"),
                                         ("done", "2026-10-25T13:00:00Z"))])
    new = morning.iloc[:1].assign(snapshot_ts="2026-10-25T16:00:00Z", price=-105)
    merged = pregame.merge_latest(new, morning, NOW).set_index("event_id")
    assert merged.loc["now", "price"] == -105 and merged.loc["later", "price"] == -110
    assert "done" not in merged.index                                                  # started: dropped


def test_leagues_before_their_season_are_skipped(data, monkeypatch):
    monkeypatch.setitem(config.settings()["schedule"], "pregame", {"nba": [15, 45]})
    client = FakeClient({"basketball_nba": [_event("tip", 30)]})
    assert pregame.run(client, pd.Timestamp("2026-10-06T22:30:00Z")) == []            # preseason
    assert client.calls == []


def test_soccer_window_covers_every_league():
    w = pregame.windows()
    assert w["epl"] == w["mls"] == tuple(config.settings()["schedule"]["pregame"]["soccer"])


def test_changed_news_re_pulls_that_game_at_most_twice(data, monkeypatch):
    nfl = "americanfootball_nfl"
    client = FakeClient({nfl: [_event("g", 60)]})
    pregame.run(client, NOW)                                                          # the pre-game pull
    client.calls.clear()
    assert pregame.run(client, NOW + pd.Timedelta(minutes=15)) == []                  # same news: nothing
    for i, status in enumerate(("Out", "Questionable", "Out")):
        monkeypatch.setattr(news, "sources", lambda league, now, st=status: {"injuries": {"home": [f"A Starter:{st}"]}})
        out = pregame.run(client, NOW + pd.Timedelta(minutes=20 + i))
        assert bool(out) == (i < pregame.MAX_REPULLS), i
    assert [c for c in client.calls if c[0] == "odds"] == [("odds", nfl, ("g",))] * pregame.MAX_REPULLS
    assert pregame.load_state(nfl, NOW)["pulled"]["g"]["repulls"] == pregame.MAX_REPULLS


def test_a_news_outage_is_not_news(data, monkeypatch):
    nfl = "americanfootball_nfl"
    client = FakeClient({nfl: [_event("g", 60)]})
    pregame.run(client, NOW)
    client.calls.clear()
    monkeypatch.setattr(news, "sources", lambda league, now: {})                       # ESPN down
    assert pregame.run(client, NOW + pd.Timedelta(minutes=15)) == [] and client.calls == []


def test_fingerprints_match_team_names_across_sources():
    src = {"injuries": {"clippers": ["X:Out"], "canadiens": []}}
    assert news.team_key("LA Clippers") == news.team_key("Los Angeles Clippers") == "clippers"
    assert news.team_key("Montréal Canadiens") == "canadiens"
    a = news.fingerprint(src, "Los Angeles Clippers", "Montréal Canadiens")
    b = news.fingerprint({"injuries": {"clippers": ["X:Questionable"]}}, "LA Clippers", "Montreal Canadiens")
    assert news.changed(a, b) == ["injuries"] and news.changed(a, {}) == [] and news.changed(None, a) == []


def test_the_first_state_file_format_still_reads(data):
    nfl = "americanfootball_nfl"
    p = pregame._state_path(nfl, NOW)
    p.parent.mkdir(parents=True)
    p.write_text('["old"]')
    assert pregame.pulled_today(nfl, NOW) == {"old"}


def _open(rows):
    return lambda league: pd.DataFrame(rows, columns=["event_id", "market", "created_at"])


def test_nba_closing_look_at_open_prop_picks_happens_once(data, monkeypatch):
    """Picks logged before the new schedule (no pre-game pull of their game) get one closing look."""
    nba = "basketball_nba"
    monkeypatch.setitem(config.settings()["schedule"], "pregame", {"nba": [40, 45]})   # the window has passed
    monkeypatch.setattr(pregame, "open_rows", _open([("picked", "player_points", "2026-10-21T15:00:00+00:00")]))
    when = pd.Timestamp("2026-10-21T23:05:00Z")
    tip = {"id": "picked", "commence_time": "2026-10-21T23:30:00Z", "home_team": "Home", "away_team": "Away"}
    client = FakeClient({nba: [tip]})
    pregame.run(client, when)                                    # 25 min out: too early for the closing look
    assert client.calls == []
    pregame.run(client, when + pd.Timedelta(minutes=15))         # 10 min out: the last tick before tip
    pregame.run(client, when + pd.Timedelta(minutes=20))
    assert client.calls == [("props", nba, "picked")]


def _props_snapshot(sport, eids, ts, markets=("player_receptions", "player_rush_yds")):
    rows = [{"event_id": eid, "commence_time": "2026-10-25T17:00:00Z", "bookmaker": "fanduel", "market": m,
             "player": "A Back", "outcome": "Over", "point": 2.5, "price": -110, "snapshot_ts": ts} for eid in eids for m in markets]
    odds_api.save_snapshot(pd.DataFrame(rows), sport, ts, "props")


def test_a_pick_logged_in_the_final_pull_gets_one_closing_look(data, monkeypatch):
    """Oct 12: Monday night's prop leans logged from the last pre-game pull had no later snapshot, so no close.
    A game whose props were pulled after the pick needs none; the look keeps the game's other markets."""
    nfl = "americanfootball_nfl"
    monkeypatch.setitem(config.settings()["schedule"], "pregame", {"nfl": [30, 85]})
    _props_snapshot(nfl, ["late", "closed"], "2026-10-25T15:40:00+00:00")
    monkeypatch.setattr(pregame, "open_rows", _open([
        ("late", "player_receptions", "2026-10-25T15:45:00+00:00"),      # logged after the game's last pull
        ("closed", "player_receptions", "2026-10-25T15:30:00+00:00"),    # a later pull already closes it
        ("far", "player_receptions", "2026-10-25T15:45:00+00:00")]))     # starts in 3 hours
    pregame._save_state(nfl, NOW, {"pulled": {"late": {}, "closed": {}}, "closing": []})
    client = FakeClient({nfl: [_event("late", 10), _event("closed", 10), _event("far", 180)]})
    saved = []
    real_save = odds_api.save_snapshot
    monkeypatch.setattr(odds_api, "save_snapshot", lambda df, *a: saved.append(df) or real_save(df, *a))
    pregame.run(client, NOW)
    assert client.calls == [("props", nfl, "late")]
    late = saved[-1][saved[-1]["event_id"] == "late"]
    assert set(late["market"]) == {"player_receptions", "player_rush_yds"}     # the other market is kept
    assert (late["market"] == "player_receptions").sum() == 2                   # fresh (FakeClient's two sides), not old
    assert set(saved[-1]["event_id"]) == {"late", "closed"}
    pregame.run(client, NOW + pd.Timedelta(minutes=5))
    assert client.calls == [("props", nfl, "late")]                             # once per game


def test_open_rows_maps_soccer_goals_bets_to_their_feed(data, monkeypatch):
    from betlab import ledger

    rows = pd.DataFrame([
        {"league": "ucl", "status": "open", "kind": "prop", "event_id": "e1", "market": "player_goal_scorer_anytime", "created_at": "t"},
        {"league": "ucl", "status": "open", "kind": "game_line", "event_id": "e1", "market": "totals", "created_at": "t"},
        {"league": "ucl", "status": "open", "kind": "game_line", "event_id": "e1", "market": "h2h", "created_at": "t"},
        {"league": "ucl", "status": "won", "kind": "prop", "event_id": "e2", "market": "player_shots", "created_at": "t"}])
    monkeypatch.setattr(ledger, "load", lambda path=None: rows if path is None else pd.DataFrame())
    got = pregame.open_rows("ucl")
    assert sorted(got["market"]) == ["alternate_totals", "h2h", "player_goal_scorer_anytime"]   # the cups' 3-way too
    assert "h2h" not in set(pregame.open_rows("epl")["market"])        # domestic 3-way closes from football-data


def test_a_cup_3way_bet_logged_in_the_last_lines_pull_gets_a_closing_look_at_h2h(data, monkeypatch):
    """Oct 13 and 15: the Viking draw and the Nijmegen lean were logged in their game's last lines pull, so close_3way
    (our own lines pulls) had nothing after them. One h2h look in the last tick, saved with the game lines."""
    ucl = config.settings()["leagues"]["ucl"]["sport_key"]
    monkeypatch.setitem(config.settings()["schedule"], "pregame", {"soccer": [15, 55]})
    ts = "2026-10-25T15:40:00+00:00"
    odds_api.save_snapshot(pd.DataFrame([{"event_id": eid, "commence_time": "2026-10-25T16:10:00Z", "bookmaker": "pinnacle",
                                          "market": "h2h", "outcome": "Home", "point": None, "price": 150, "snapshot_ts": ts}
                                         for eid in ("cup", "other")]), ucl, ts, "pick")
    monkeypatch.setattr(pregame, "open_rows", _open([("cup", "h2h", "2026-10-25T15:45:00+00:00")]))
    pregame._save_state(ucl, NOW, {"pulled": {"cup": {}, "other": {}}, "closing": []})
    client = FakeClient({ucl: [_event("cup", 10), _event("other", 10)]})
    client.event_odds = lambda sport, eid, markets, priority="normal": (
        client.calls.append(("event", sport, eid, tuple(markets))) or _payload(_event(eid, 10), market="h2h", price=120))
    saved = []
    real_save = odds_api.save_snapshot
    monkeypatch.setattr(odds_api, "save_snapshot", lambda df, *a: saved.append((df, a[-1])) or real_save(df, *a))
    out = pregame.run(client, NOW)
    assert client.calls == [("event", ucl, "cup", ("h2h",))]
    assert "(1 at 3-way)" in out[0]
    assert [kind for _, kind in saved] == ["pick"]                      # with the game lines, not the props
    snap = saved[0][0]
    assert set(snap["event_id"]) == {"cup", "other"}                    # the other game keeps its earlier lines
    assert set(snap.loc[snap["event_id"] == "cup", "price"]) == {120}   # the fresh close, not the old price
    pregame.run(client, NOW + pd.Timedelta(minutes=5))
    assert len(client.calls) == 1                                       # once per game


def test_a_start_the_feed_moves_a_few_minutes_later_keeps_its_first_time(data, monkeypatch):
    """Oct 12: at 8:15 PM the feed moved Monday night to 8:18, so the 8:15 tick re-pulled a game already kicking
    off and the card logged leans at 8:15:31. The first start seen today sticks for moves of up to 30 minutes."""
    nfl = "americanfootball_nfl"
    monkeypatch.setattr(pregame, "open_rows", _open([]))
    game = _event("mnf", 60)
    client = FakeClient({nfl: [game]})
    pregame.run(client, NOW)                                             # pulled 60 minutes out, start recorded
    assert ("props", nfl, "mnf") in client.calls
    client.calls.clear()
    moved = game | {"commence_time": (NOW + pd.Timedelta(minutes=63)).isoformat().replace("+00:00", "Z")}
    client.events_by_sport[nfl] = [moved]
    NEWS["injuries"]["home"].append("Late Scratch:Out")                  # news changes right at kickoff
    try:
        pregame.run(client, NOW + pd.Timedelta(minutes=61))              # after the first start, before the moved one
    finally:
        NEWS["injuries"]["home"].pop()
    assert client.calls == []                                            # treated as started: no re-pull
    state = pregame.load_state(nfl, NOW)
    assert state["start"]["mnf"] == game["commence_time"]
    later = game | {"commence_time": (NOW + pd.Timedelta(minutes=180)).isoformat().replace("+00:00", "Z")}
    assert pregame.stick_starts([later], state)[0]["commence_time"] == later["commence_time"]   # a real delay is taken


def test_pulled_rows_carry_the_sticky_start():
    ev = [{"id": "g", "commence_time": "2026-10-13T00:15:00Z"}]
    df = pd.DataFrame({"event_id": ["g", "other"], "commence_time": ["2026-10-13T00:18:00Z", "2026-10-13T01:00:00Z"]})
    assert pregame._sticky(df, ev)["commence_time"].tolist() == ["2026-10-13T00:15:00Z", "2026-10-13T01:00:00Z"]


def test_nba_games_are_pulled_with_their_slices_first_tip():
    """Oct 21 (Mike: early and late NBA slices): a slice locks 10-25 minutes before its first tip, so every game in it is
    pulled once that first tip is 15-45 minutes away; the late slice waits for its own first tip."""
    import pandas as pd

    from betlab import pregame

    tip = lambda hm: pd.Timestamp(f"2026-10-21 {hm}", tz="America/New_York").tz_convert("UTC").isoformat()
    events = [{"id": e, "commence_time": tip(t)} for e, t in
              (("a", "19:00"), ("b", "19:40"), ("c", "20:40"), ("d", "22:00"), ("e", "22:40"))]
    now = pd.Timestamp(tip("18:30"))
    assert [e["id"] for e in pregame.due_by_slice(events, now, (15, 45), set(), "nba")] == ["a", "b", "c"]
    assert [e["id"] for e in pregame.due_by_slice(events, now, (15, 45), {"a", "b", "c"}, "nba")] == []
    later = pd.Timestamp(tip("21:30"))
    assert [e["id"] for e in pregame.due_by_slice(events, later, (15, 45), {"a", "b", "c"}, "nba")] == ["d", "e"]
    assert [e["id"] for e in pregame.due(events, now, (15, 45), set())] == ["a"]      # what each game's own window did


def test_each_tick_keeps_the_nba_and_college_schedule_for_publish(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    assert pregame.schedule() == {}                                       # a cleared cache: nothing, no error
    pregame.save_schedule("ncaab", [_event("a", 600)])
    assert [e["id"] for e in pregame.schedule()["ncaab"]] == ["a"]
    (tmp_path / "schedule" / "nba.json").write_text("{cut off")           # a full disk's half-written file is a miss
    assert set(pregame.schedule()) == {"ncaab"}
