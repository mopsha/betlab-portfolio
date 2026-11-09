"""The NBA data loader: season naming and the local cache."""

import io

import pandas as pd

from betlab.sources import nba


def test_current_season_flips_in_august():
    assert nba.current_season(pd.Timestamp("2026-09-25", tz="America/New_York")) == 2027
    assert nba.current_season(pd.Timestamp("2027-04-10", tz="America/New_York")) == 2027
    assert nba.current_season(pd.Timestamp("2027-08-01", tz="America/New_York")) == 2028


def test_get_caches_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(nba, "CACHE", tmp_path)
    buf = io.BytesIO()
    pd.DataFrame({"game_id": [1, 2]}).to_parquet(buf)
    calls = []

    class Session:
        def get(self, url, timeout):
            calls.append(url)

            class R:
                content = buf.getvalue()

                def raise_for_status(self):
                    pass
            return R()

    df = nba._get("schedules", 2025, session=Session())
    assert len(df) == 2 and calls[0].endswith("/espn_nba_schedules/nba_schedule_2025.parquet")
    nba._get("schedules", 2025, session=Session())          # a past season: served from the cache
    assert len(calls) == 1 and (tmp_path / "nba_schedule_2025.parquet").exists()


def test_player_box_can_ask_for_a_fresh_copy(monkeypatch):
    """Grading passes max_age_hours so a box-score file cached the night before is re-downloaded."""
    seen = []
    frame = pd.DataFrame({"game_id": [1], "team_abbreviation": ["BOS"], "minutes": ["30"]})
    monkeypatch.setattr(nba, "_get", lambda kind, season, max_age_hours=None, session=None: seen.append(max_age_hours) or frame)
    monkeypatch.setattr(nba, "current_season", lambda today=None: 2027)
    monkeypatch.setattr(nba, "load_schedules", lambda seasons, max_age_hours=None: _sched(done=False))
    nba.load_player_box([2027], max_age_hours=1.0)
    nba.load_player_box([2027])
    assert seen == [1.0, None]


def _sched(done=True, tip="2026-10-20T19:00:00Z"):
    return pd.DataFrame({"game_id": [401], "season": [2027], "season_type": [2], "home_id": [8], "away_id": [2],
                         "home_abbreviation": ["DET"], "away_abbreviation": ["BOS"],
                         "home_display_name": ["Detroit Pistons"], "away_display_name": ["Boston Celtics"],
                         "home_score": [0.0], "away_score": [0.0], "periods": [0], "status_type_completed": [done],
                         "tipoff": [pd.Timestamp(tip)]})


def _summary():
    keys = ["minutes", "points", "fieldGoalsMade-fieldGoalsAttempted",
            "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "freeThrowsMade-freeThrowsAttempted",
            "rebounds", "assists", "turnovers", "steals", "blocks", "offensiveRebounds", "defensiveRebounds",
            "fouls", "plusMinus"]

    def team(tid, abbr, athletes):
        return {"team": {"id": str(tid), "abbreviation": abbr, "displayName": abbr}, "statistics": [{"keys": keys, "athletes": athletes}]}

    played = {"athlete": {"id": "11", "displayName": "Jayson Tatum"}, "starter": True, "didNotPlay": False,
              "stats": ["36", "28", "10-20", "4-9", "4-5", "9", "6", "2", "1", "0", "1", "8", "2", "+7"]}
    dnp = {"athlete": {"id": "12", "displayName": "Bench Guy"}, "starter": False, "didNotPlay": True,
           "reason": "COACH'S DECISION", "stats": []}
    other = {"athlete": {"id": "21", "displayName": "Cade Cunningham"}, "starter": True, "didNotPlay": False,
             "stats": ["38", "31", "11-22", "3-7", "6-7", "5", "9", "4", "2", "1", "0", "5", "3", "-7"]}
    return {"boxscore": {"players": [team(2, "BOS", [played, dnp]), team(8, "DET", [other])]}}


def test_espn_box_rows_match_the_file_columns():
    """ESPN's summary becomes sportsdataverse's columns: what grading and the trackers read (Oct 19, 2026)."""
    g = next(_sched().assign(home_score=[101.0], away_score=[108.0]).itertuples())
    b = nba.espn_box_rows(_summary(), g).set_index("athlete_id")
    t = b.loc[11.0]
    assert (t["minutes"], t["points"], t["rebounds"], t["assists"], t["three_point_field_goals_made"]) == (36, 28, 9, 6, 4)
    assert t["team_abbreviation"] == "BOS" and t["home_away"] == "away" and t["team_score"] == 108
    assert t["game_date"] == "2026-10-20" and bool(t["starter"])
    assert bool(b.loc[12.0, "did_not_play"]) and pd.isna(b.loc[12.0, "minutes"])
    assert b.loc[21.0, "home_away"] == "home" and b.loc[21.0, "opponent_team_abbreviation"] == "BOS"


def test_schedule_takes_espn_finals_for_games_the_file_lacks():
    now = pd.Timestamp("2026-10-21T14:00:00Z")
    seen = []
    finals = lambda day: seen.append(day) or {401: {"home_score": 101.0, "away_score": 108.0, "periods": 4}}
    out = nba._with_espn_finals(_sched(done=False), now=now, finals=finals)
    assert seen == ["20261020"]
    assert bool(out["status_type_completed"].iloc[0]) and out["away_score"].iloc[0] == 108
    # a game that tipped under two hours ago isn't asked about
    seen.clear()
    nba._with_espn_finals(_sched(done=False, tip="2026-10-21T13:00:00Z"), now=now, finals=finals)
    assert seen == []


def test_player_box_falls_back_to_espn_before_the_file_exists(monkeypatch):
    """The 2027 file was a 404 on Oct 19, 2026: finished games come from ESPN instead."""
    import requests

    def missing(kind, season, max_age_hours=None, session=None):
        raise requests.HTTPError("404")

    g = next(_sched().assign(home_score=[101.0], away_score=[108.0]).itertuples())
    monkeypatch.setattr(nba, "current_season", lambda today=None: 2027)
    monkeypatch.setattr(nba, "_get", missing)
    monkeypatch.setattr(nba, "load_schedules", lambda seasons, max_age_hours=None: _sched())
    monkeypatch.setattr(nba, "_espn_box", lambda gid, game, session=None: nba.espn_box_rows(_summary(), g))
    box = nba.load_player_box([2027], max_age_hours=1.0)
    assert set(box["athlete_id"]) == {11.0, 12.0, 21.0}
    # before any game is final there is nothing: callers that tolerate a missing season still get an error
    monkeypatch.setattr(nba, "load_schedules", lambda seasons, max_age_hours=None: _sched(done=False))
    try:
        nba.load_player_box([2027])
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass
