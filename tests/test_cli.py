import pandas as pd

from betlab import cli


def event(kickoff: str) -> dict:
    return {"commence_time": kickoff, "home_team": "Green Bay Packers", "away_team": "Atlanta Falcons"}


def test_prime_time_window():
    kickoff = "2026-09-25T00:15:00Z"  # Thursday 8:15 PM EDT
    games = [event(kickoff)]
    at = lambda t: pd.Timestamp(t, tz="UTC")
    assert cli.prime_time_events(games, at("2026-09-24T22:52")) == games      # 6:52 PM: 83 min before
    assert cli.prime_time_events(games, at("2026-09-24T23:40")) == games      # delayed cron: 35 min before
    assert cli.prime_time_events(games, at("2026-09-24T23:52")) == []         # 23 min before: too late
    assert cli.prime_time_events(games, at("2026-09-24T21:52")) == []         # 143 min before: too early
