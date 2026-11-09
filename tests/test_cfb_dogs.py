"""College moneyline dogs at 20-40% (cfb_dogs.py): logged at first sight, updated to the close, graded from CFBD."""

import pandas as pd
import pytest

from betlab import cfb_dogs as D


def snap(ts, home_price, away_price, pin=(-250, 210), kickoff="2026-10-31T19:30:00Z"):
    rows = []
    for book, (h, a) in {"pinnacle": pin, "fanduel": (home_price, away_price), "draftkings": (-260, 205),
                         "novig": (-235, 235)}.items():
        for team, price in (("Home Hawks", h), ("Away Owls", a)):
            rows.append({"snapshot_ts": ts, "event_id": "e1", "commence_time": kickoff, "home_team": "Home Hawks",
                         "away_team": "Away Owls", "bookmaker": book, "market": "h2h", "outcome": team,
                         "price": price, "bet_limit": 120.0 if book == "novig" else None})
    rows.append({**rows[0], "market": "spreads", "price": -110})
    return pd.DataFrame(rows)


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "PATH", tmp_path / "cfb_dogs.csv")
    return D


def test_a_dog_is_logged_once_and_updated_to_the_close(ledger):
    asof = pd.Timestamp("2026-10-27T14:00:00Z")
    assert ledger.record(snap("2026-10-27T13:55:00+00:00", -240, 200), asof) == 1      # only the 20-40% side
    row = ledger.load().iloc[0]
    assert (row["dog"], row["side"], row["first_source"], row["first_fanduel"], row["first_novig_limit"]) == \
        ("Away Owls", "away", "pinnacle", 200, 120.0)
    assert 0.2 <= row["first_p"] < 0.4
    later = pd.Timestamp("2026-10-31T18:50:00Z")
    ledger.record(snap("2026-10-31T18:45:00+00:00", -200, 170, pin=(-190, 165)), later)
    row = ledger.load().iloc[0]
    assert len(ledger.load()) == 1 and row["last_fanduel"] == 170 and row["last_p"] > row["first_p"]
    # after kickoff nothing changes
    ledger.record(snap("2026-10-31T20:00:00+00:00", -500, 400, pin=(-600, 450)), pd.Timestamp("2026-10-31T20:00:00Z"))
    assert ledger.load().iloc[0]["last_fanduel"] == 170


def test_a_side_outside_the_band_is_not_logged(ledger):
    asof = pd.Timestamp("2026-10-27T14:00:00Z")
    assert ledger.record(snap("t", -900, 600, pin=(-900, 650)), asof) == 0               # the dog is under 20%
    assert ledger.record(snap("t", -120, 100, pin=(-120, 100)), asof) == 0               # both near 50%


def test_grading_from_cfbd_and_clv_only_from_a_later_pull(ledger):
    asof = pd.Timestamp("2026-10-27T14:00:00Z")
    ledger.record(snap("2026-10-27T13:55:00+00:00", -240, 200), asof)
    ledger.record(snap("2026-10-31T18:45:00+00:00", -200, 170, pin=(-190, 165)), pd.Timestamp("2026-10-31T18:50:00Z"))
    games = pd.DataFrame({"game_id": ["401"], "home_team": ["Home"], "away_team": ["Away"], "home_pts": [17.0],
                          "away_pts": [24.0], "date": [pd.Timestamp("2026-10-31")]})
    names = {"Home Hawks": "Home", "Away Owls": "Away"}
    assert ledger.grade(games, names) == 1
    row = ledger.load().iloc[0]
    assert row["status"] == "graded" and row["won"] == 1.0 and row["game_id"] == "401" and row["clv"] > 0
    s = ledger.summary()
    assert s["n"] == 1 and s["won"] == 1 and s["units_fanduel"] == 2.0 and s["n_novig"] == 1


def test_no_clv_when_the_close_is_the_first_pull(ledger):
    asof = pd.Timestamp("2026-10-31T18:50:00Z")
    ledger.record(snap("2026-10-31T18:45:00+00:00", -240, 200), asof)
    games = pd.DataFrame({"game_id": ["401"], "home_team": ["Home"], "away_team": ["Away"], "home_pts": [30.0],
                          "away_pts": [3.0], "date": [pd.Timestamp("2026-10-31")]})
    ledger.grade(games, {"Home Hawks": "Home", "Away Owls": "Away"})
    row = ledger.load().iloc[0]
    assert row["won"] == 0.0 and pd.isna(row["clv"])
