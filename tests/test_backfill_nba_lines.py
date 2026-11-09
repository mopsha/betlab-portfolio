"""The NBA game-lines backfill: which snapshot times it buys."""

import pandas as pd

from betlab import backfill_nba_lines as B


def schedule(rows):
    return pd.DataFrame([{"season_type": st, "status_type_completed": done,
                          "start_date": pd.Timestamp(ts, tz="America/New_York").tz_convert("UTC").isoformat()}
                         for ts, st, done in rows])


def test_one_evening_look_plus_a_west_coast_look_when_two_late_games():
    s = schedule([("2026-01-10 15:30", 2, True),                           # afternoon: not covered
                  ("2026-01-10 19:00", 2, True), ("2026-01-10 19:30", 2, True),
                  ("2026-01-10 22:00", 2, True), ("2026-01-10 22:30", 2, True),
                  ("2026-01-11 19:00", 2, True), ("2026-01-11 22:00", 2, True),  # one late game: no second look
                  ("2026-04-20 20:00", 3, True),                           # playoffs: not bought
                  ("2026-01-12 19:00", 2, False)])                         # never played
    times = [t.tz_convert("America/New_York").strftime("%m-%d %H:%M") for t in B.plan(s)]
    assert times == ["01-10 18:45", "01-10 21:45", "01-11 18:45"]
