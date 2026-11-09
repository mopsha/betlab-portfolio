"""Game Previews: who starts at QB, who's hurt, and the kickoff weather."""

import pandas as pd

from betlab.cards import preview_nfl as PV
from betlab.sources import weather

DEPTH = pd.DataFrame({"team": ["NYG", "NYG", "NYG"], "player_id": ["dart", "winston", "third"],
                      "name": ["Jaxson Dart", "Jameis Winston", "Third QB"], "rank": [1, 2, 3]})


def inj(rows):
    return pd.DataFrame(rows, columns=["team", "gsis_id", "full_name", "position", "report_status",
                                       "report_primary_injury", "practice_status"])


def test_starter_skips_qbs_ruled_out():
    none = inj([])
    assert PV._starter("NYG", DEPTH, none)[:2] == ("dart", "Jaxson Dart")
    out = inj([["NYG", "dart", "Jaxson Dart", "QB", "Out", "Ankle", None]])
    assert PV._starter("NYG", DEPTH, out) == ("winston", "Jameis Winston", ["Jaxson Dart"])
    assert PV._starter("NYG", None, out) == (None, None, [])


def test_injured_lists_regulars_by_status_then_role():
    report = inj([["NYG", "a", "Starter WR", "WR", "Questionable", "Hamstring", None],
                  ["NYG", "b", "Star LB", "LB", "Out", "Knee", None],
                  ["NYG", "c", "Backup TE", "TE", "Out", "Foot", None],               # not a regular
                  ["NYG", "d", "Backup QB", "QB", None, None, "Did Not Participate In Practice"],
                  ["NYG", "e", "Healthy RB", "RB", None, None, "Full Participation in Practice"]])
    roles = pd.Series({"a": 0.9, "b": 0.8, "c": 0.1, "d": 0.0, "e": 0.7})
    got = PV._injured(report, "NYG", roles)
    assert [(x["name"], x["status"]) for x in got] == [("Star LB", "Out"), ("Starter WR", "Questionable"),
                                                       ("Backup QB", "Missed practice")]


def test_venues_match_by_name_first_and_know_the_roof():
    assert weather.venue("NYC01")["roof"] == "outdoors"
    assert weather.venue("DET00")["roof"] == "dome"
    assert weather.venue("JAX00", "Tottenham Hotspur Stadium")["id"] == "LON02"   # nflverse files it under JAX
    assert weather.venue("XXX00") is None


def test_forecast_averages_the_kickoff_window():
    ko = pd.Timestamp.now(tz="UTC").floor("h") + pd.Timedelta(days=2)
    hours = pd.date_range(ko - pd.Timedelta(hours=2), periods=8, freq="h")

    class Session:
        def get(self, url, params, timeout):
            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    n = len(hours)
                    return {"hourly": {"time": [h.strftime("%Y-%m-%dT%H:%M") for h in hours],
                                       "temperature_2m": [50.0] * n, "precipitation_probability": [10, 20, 30, 80, 40, 90, 5, 5],
                                       "precipitation": [0.0, 0.0, 0.1, 0.2, 0.1, 0.5, 0.0, 0.0],
                                       "wind_speed_10m": [5, 5, 18, 20, 22, 40, 5, 5], "wind_gusts_10m": [9] * 5 + [60, 9, 9]}}
            return R()

    f = weather.forecast(40.8, -74.1, ko, session=Session())
    assert f == {"temp_f": 50.0, "wind_mph": 20.0, "gust_mph": 9.0, "precip_prob": 0.8, "precip_in": 0.4}
    assert weather.forecast(40.8, -74.1, ko + pd.Timedelta(days=30), session=Session()) is None


def test_forecast_stops_calling_after_repeated_failures(monkeypatch):
    """Oct 6: every call stalled on the worker and the preview ran out its 25 minutes."""
    monkeypatch.setattr(weather, "_fails", 0)
    ko = pd.Timestamp.now(tz="UTC").floor("h") + pd.Timedelta(days=2)
    calls = []

    class Down:
        def get(self, url, params, timeout):
            calls.append(timeout)
            raise TimeoutError("stalled")

    for _ in range(6):
        assert weather.forecast(40.8, -74.1, ko, session=Down()) is None
    assert len(calls) == weather.MAX_FAILS
    assert calls[0] == weather.TIMEOUT
