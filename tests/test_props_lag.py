"""The morning-line CLV study (props_lag): morning FanDuel price vs the sharp close."""

import pandas as pd
import pytest

from betlab import odds_math as om
from betlab import props_lag as L

KICK = pd.Timestamp("2026-09-27T17:00:00Z")


def quotes(ts, book, point, over, under, player="A. Receiver", market="player_receptions"):
    base = {"snapshot_ts": ts, "sport_key": "americanfootball_nfl", "event_id": "e1", "commence_time": KICK,
            "home_team": "Home", "away_team": "Away", "bookmaker": book, "market": market,
            "last_update": ts, "player": player, "point": point}
    return [{**base, "outcome": "Over", "price": over}, {**base, "outcome": "Under", "price": under}]


def snaps():
    morning, close, early = KICK - pd.Timedelta(hours=3.5), KICK - pd.Timedelta(hours=1), KICK - pd.Timedelta(hours=20)
    rows = (quotes(early, "fanduel", 4.5, -110, -110) + quotes(early, "pinnacle", 4.5, -110, -110)
            # morning: FanDuel's over is stale at +120 while Pinnacle has it -130
            + quotes(morning, "fanduel", 4.5, 120, -150) + quotes(morning, "pinnacle", 4.5, -130, 110)
            # a player Pinnacle quotes at another point, and one only FanDuel has: both skipped
            + quotes(morning, "fanduel", 50.5, -110, -110, market="player_reception_yds")
            + quotes(morning, "pinnacle", 52.5, -110, -110, market="player_reception_yds")
            + quotes(morning, "fanduel", 1.5, -110, -110, player="B. Back")
            # close: Pinnacle holds, FanDuel moves to -125
            + quotes(close, "fanduel", 4.5, -125, 100) + quotes(close, "pinnacle", 4.5, -135, 115)
            + quotes(close, "pinnacle", 52.5, -110, -110, market="player_reception_yds"))
    df = pd.DataFrame(rows)
    df["snapshot_ts"] = pd.to_datetime(df["snapshot_ts"], utc=True)
    df["commence_time"] = pd.to_datetime(df["commence_time"], utc=True)
    return df


def test_morning_price_is_judged_against_the_sharp_close_at_the_same_point():
    p = L.pairs(snaps())
    assert len(p) == 2 and set(p["side"]) == {"over", "under"}              # only the same-point line
    over = p[p["side"] == "over"].iloc[0]
    assert over["hours_before"] == 3.5                                     # the latest morning look, not the day-before one
    fair_m = om.no_vig_two_way(-130, 110)[0]
    fair_c = om.no_vig_two_way(-135, 115)[0]
    assert over["ev_morning"] == pytest.approx(fair_m * om.american_to_decimal(120) - 1)
    assert over["clv"] == pytest.approx(fair_c * om.american_to_decimal(120) - 1)
    assert over["clv"] > over["ev_morning"] > 0.1                          # the sharp side moved further its way
    assert over["fd_close"] > over["fd_morning"]                           # FanDuel caught up


def test_report_counts_morning_qualifiers():
    rep = L.report(L.pairs(snaps()), thresholds=(0.05,))
    row = rep[(rep["morning_ev_at_least"] == 0.05) & (rep["side"] == "all")].iloc[0]
    assert row["n"] == 1 and row["beat_close"] == 1.0
    assert rep.iloc[-1]["morning_ev_at_least"] == "every side" and rep.iloc[-1]["n"] == 2


def test_a_game_without_a_close_is_skipped():
    df = snaps()
    assert L.pairs(df[df["snapshot_ts"] < KICK - pd.Timedelta(hours=2)]).empty
