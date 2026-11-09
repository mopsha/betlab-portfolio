"""Early locks (Mike, Oct 12): a slice locks once the news is in for every one of its games."""

import json

import pandas as pd

from betlab import config, pregame, sgp_plus


def _slate(sid="2026-10-18-early", kickoff="2026-10-18T17:00:00Z"):
    return {"slate": sid, "sport": "nfl", "kickoff": kickoff, "plus": {"legs": ["a"]}, "td": None}


def test_a_settled_slice_locks_before_its_lock_time():
    now = pd.Timestamp("2026-10-18T15:46:00Z")            # 11:46 AM: 74 minutes before the 1 PM kickoff
    assert sgp_plus.lock_due([_slate()], now) == []
    assert sgp_plus.lock_due([_slate()], now, early={"2026-10-18-early"}) == ["2026-10-18-early"]
    kept = sgp_plus.keep_tickets([_slate()], [], now, early={"2026-10-18-early"})
    assert kept[0]["locked_at"] == now.isoformat(timespec="seconds")
    assert "locked_at" not in sgp_plus.keep_tickets([_slate()], [], now)[0]      # not settled: still a preview


def _write_world(tmp_path, monkeypatch, pulled_ids, games):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    day = tmp_path / "odds" / "americanfootball_nfl" / "2026-10-18"
    day.mkdir(parents=True)
    pd.DataFrame([{"event_id": e, "commence_time": t, "home_team": h, "away_team": a} for e, t, h, a in games]
                 ).to_parquet(day / "095500_pick.parquet")
    (day / "pregame.json").write_text(json.dumps({"pulled": {e: {} for e in pulled_ids}}), encoding="utf-8")
    real = config.settings()
    monkeypatch.setattr(config, "settings", lambda: {**real, "leagues": {"nfl": real["leagues"]["nfl"]}})


GAMES = [("g1", "2026-10-18T17:00:00Z", "Tampa Bay Buccaneers", "Pittsburgh Steelers"),
         ("g2", "2026-10-18T17:00:00Z", "Miami Dolphins", "New York Jets"),
         ("g3", "2026-10-18T20:25:00Z", "Seattle Seahawks", "Arizona Cardinals")]


def test_a_slice_is_settled_only_when_every_game_has_had_its_news_pull(tmp_path, monkeypatch):
    now = pd.Timestamp("2026-10-18T15:46:00Z")
    _write_world(tmp_path, monkeypatch, ["g1"], GAMES)
    assert pregame.settled_slates(now) == set()                       # g2 still waits for its news
    (tmp_path / "odds" / "americanfootball_nfl" / "2026-10-18" / "pregame.json").write_text(
        json.dumps({"pulled": {"g1": {}, "g2": {}}}), encoding="utf-8")
    assert pregame.settled_slates(now) == {"2026-10-18-early"}       # the late slice (g3) isn't


def test_nhl_slices_also_need_both_goalies_confirmed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    day = tmp_path / "odds" / "icehockey_nhl" / "2026-10-18"
    day.mkdir(parents=True)
    pd.DataFrame([{"event_id": "h1", "commence_time": "2026-10-18T23:00:00Z", "home_team": "Buffalo Sabres",
                   "away_team": "Florida Panthers"}]).to_parquet(day / "095500_pick.parquet")
    (day / "pregame.json").write_text(json.dumps({"pulled": {"h1": {}}}), encoding="utf-8")
    real = config.settings()
    monkeypatch.setattr(config, "settings", lambda: {**real, "leagues": {"nhl": real["leagues"]["nhl"]}})
    now = pd.Timestamp("2026-10-18T22:15:00Z")
    assert pregame.settled_slates(now, goalies={"sabres": True, "panthers": False}) == set()
    assert pregame.settled_slates(now, goalies={"sabres": True, "panthers": True}) == {"2026-10-18-nhl-evening"}


def test_new_news_reopens_an_early_lock_until_the_usual_lock_time():
    """Mike, Oct 12: a locked ticket must still follow late news (a late scratch after an early lock)."""
    locked_at = "2026-10-18T15:45:00+00:00"
    prev = _slate() | {"plus": {"legs": ["old"]}, "locked_at": locked_at}
    new = _slate() | {"plus": {"legs": ["new"]}}
    sid = {"2026-10-18-early"}
    at = pd.Timestamp("2026-10-18T16:15:00Z")                              # 12:15 PM: before the 12:45 lock
    kept = sgp_plus.keep_tickets([new], [prev], at, early=sid, reopen=sid)[0]
    assert kept["plus"]["legs"] == ["new"] and kept["updated"] == 1 and kept["locked_at"] == at.isoformat(timespec="seconds")
    unsettled = sgp_plus.keep_tickets([new], [prev], at, reopen=sid)[0]    # news not all in anymore: a preview again
    assert "locked_at" not in unsettled and unsettled["updated"] == 1
    late = pd.Timestamp("2026-10-18T16:46:00Z")                            # from the usual lock on, it's final
    assert sgp_plus.keep_tickets([new], [prev], late, early=sid, reopen=sid)[0]["plus"]["legs"] == ["old"]
    assert sgp_plus.keep_tickets([new], [prev], at, early=sid)[0]["plus"]["legs"] == ["old"]   # no new news: kept


def test_reopened_slates_need_news_after_the_lock(tmp_path, monkeypatch):
    _write_world(tmp_path, monkeypatch, ["g1", "g2"], GAMES)
    path = tmp_path / "odds" / "americanfootball_nfl" / "2026-10-18" / "pregame.json"
    path.write_text(json.dumps({"pulled": {"g1": {"news_at": "2026-10-18T16:00:00+00:00"}, "g2": {}}}), encoding="utf-8")
    now = pd.Timestamp("2026-10-18T16:05:00Z")
    assert pregame.reopened_slates({"2026-10-18-early": "2026-10-18T15:45:00+00:00"}, now) == {"2026-10-18-early"}
    assert pregame.reopened_slates({"2026-10-18-early": "2026-10-18T16:01:00+00:00"}, now) == set()


def test_an_update_gets_its_own_alert():
    from betlab import alerts

    s = _slate() | {"locked_at": "2026-10-18T16:15:00+00:00", "updated": 1,
                    "plus": {"n_games": 2, "n_legs": 4, "fair_price": 900}, "title": "NFL early games"}
    now = pd.Timestamp("2026-10-18T16:16:00Z")
    assert alerts.lock_key(s) == "lock:2026-10-18-early:u1"
    assert alerts.locked([s], {"lock:2026-10-18-early"}, now) == [s]       # the first lock's alert doesn't cover it
    assert alerts.lock_message(s)["title"].startswith("Updated on new news: NFL early games")


def test_a_college_slice_locks_once_its_first_tip_is_pulled(tmp_path, monkeypatch):
    """Nov 2: no props and no news check to wait for, so the later games don't hold the slice."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    now = pd.Timestamp("2026-11-02T22:20:00Z")                       # 5:20 PM ET
    games = [("c1", "2026-11-02T23:00:00Z"), ("c2", "2026-11-03T00:30:00Z")]    # 6 PM and 7:30 PM: the evening slice
    monkeypatch.setattr(pregame, "SLICE_SPORT", {"ncaab": "ncaab"})
    monkeypatch.setattr(pregame, "latest", lambda *_: pd.DataFrame(
        [{"event_id": e, "commence_time": t, "home_team": "H", "away_team": "A"} for e, t in games]))
    key = config.settings()["leagues"]["ncaab"]["sport_key"]
    assert pregame.settled_slates(now) == set()
    pregame._save_state(key, now, pregame.load_state(key, now) | {"pulled": {"c1": {}}})
    assert pregame.settled_slates(now) == {"2026-11-02-ncaab-evening"}
