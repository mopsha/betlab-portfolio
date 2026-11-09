from datetime import datetime, timezone

import pandas as pd

from betlab import archive, wind_watch as W

NOW = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)


def rows():
    base = {"sport_key": "nfl", "event_id": "e", "market": "totals", "bookmaker": "fanduel", "outcome": "Over", "player": None, "point": 45.5,
            "commence_time": "2026-11-08T18:00:00Z", "home_team": "H", "away_team": "A"}
    return pd.DataFrame([base | {"snapshot_ts": "2026-11-08T14:00:00+00:00", "price": -110}, base | {"snapshot_ts": "2026-11-08T17:30:00+00:00", "price": -125},
                         base | {"snapshot_ts": "2026-11-08T18:05:00+00:00", "price": 400},      # after the start: no price you could have had
                         base | {"snapshot_ts": "2026-11-08T14:00:00+00:00", "price": -105, "point": 46.5},
                         base | {"snapshot_ts": "2026-11-08T14:00:00+00:00", "price": 150, "market": "player_tds", "player": "Joe", "point": None}])


def test_a_bet_keeps_its_first_and_last_price_before_the_start():
    a = archive.boil(rows())
    assert len(a) == 3
    r = a[a["point"] == 45.5].iloc[0]
    assert (r["first_price"], r["last_price"], r["pulls"]) == (-110, -125, 2)
    assert a[a["point"] == 46.5].iloc[0]["pulls"] == 1
    assert pd.isna(a[a["player"] == "Joe"].iloc[0]["point"])       # no number stays no number


def game(**kw):
    return {"game_id": "2026_10_A_H", "gameday": "2026-11-08", "gametime": "13:00", "home_team": "H", "away_team": "A", "stadium_id": "X", "stadium": "X", "total": None, "total_line": None} | kw


OUT = lambda *_: {"lat": 1, "lon": 1, "roof": "outdoors"}     # noqa: E731


def test_only_a_windy_outdoor_game_today_is_logged_and_only_once(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_path", lambda: tmp_path / "w.csv")
    games = pd.DataFrame([game()])
    windy = lambda *_: {"wind_mph": 16.2, "gust_mph": 25}          # noqa: E731
    assert len(W.record(games, None, NOW, windy, lambda *_: {"lat": 1, "lon": 1, "roof": "dome"})) == 0
    assert len(W.record(games, None, NOW, lambda *_: {"wind_mph": 9.0}, OUT)) == 0
    assert len(W.record(pd.DataFrame([game(gameday="2026-11-09")]), None, NOW, windy, OUT)) == 0
    d = W.record(games, None, NOW, windy, OUT)
    assert d.iloc[0]["wind_mph"] == 16.2 and d.iloc[0]["matchup"] == "A @ H"
    d.to_csv(tmp_path / "w.csv", index=False)
    assert len(W.record(games, None, NOW, windy, OUT)) == 1


def test_the_grade_is_the_under_against_the_close_and_a_push_is_neither(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_path", lambda: tmp_path / "w.csv")
    d = W.record(pd.DataFrame([game()]), None, NOW, lambda *_: {"wind_mph": 16.0}, OUT)
    assert W.grade(d, pd.DataFrame([game()]), NOW)["graded_at"].isna().all()    # not played
    won = W.grade(d, pd.DataFrame([game(total=30.0, total_line=44.5)]), NOW).iloc[0]
    assert won["under_won"] is True and won["total_close"] == 44.5
    assert W.grade(d, pd.DataFrame([game(total=50.0, total_line=44.5)]), NOW).iloc[0]["under_won"] is False
    assert W.grade(d, pd.DataFrame([game(total=44.0, total_line=44.0)]), NOW).iloc[0]["under_won"] is None
