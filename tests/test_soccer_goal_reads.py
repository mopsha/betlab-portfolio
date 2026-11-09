"""The soccer lineup goals read (Oct 12): tracked against the market, no weight."""

import math

import pandas as pd

from betlab import soccer_goal_reads as R


def test_poisson_over_and_btts():
    o, b = R.probs(1.5, 1.0)
    assert abs(o - (1 - math.exp(-2.5) * (1 + 2.5 + 2.5 ** 2 / 2))) < 1e-12
    assert abs(b - (1 - math.exp(-1.5)) * (1 - math.exp(-1.0))) < 1e-12
    r = R.read([{"xg": 2.14, "goals_model": 1.82}, {"xg": 0.95, "goals_model": 1.04}])
    assert r["p_over25"] < r["p_over25_mkt"]                  # the lineup read has fewer goals
    assert R.read([{"xg": 1.2, "goals_model": None}, {"xg": 1.1, "goals_model": 1.0}]) is None


def test_reads_log_once_and_grade_from_the_score(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "PATH", tmp_path / "reads.csv")
    row = {"event_id": "m1", "league": "serie_a", "matchup": "Atalanta BC vs Venezia", "home": "Atalanta BC",
           "away": "Venezia", "commence_time": "2026-10-12T18:45:00Z",
           **R.read([{"xg": 2.14, "goals_model": 1.82}, {"xg": 0.95, "goals_model": 1.04}])}
    asof = pd.Timestamp("2026-10-12T18:00:00Z")
    assert R.record([row], asof) == 1 and R.record([row], asof) == 0
    assert R.grade(result=lambda *a: {"hg": 3, "ag": 1}, now=pd.Timestamp("2026-10-13T10:00:00Z")) == 1
    s = R.summary()
    assert s["graded"] == 1 and set(s["over25"]) == {"read", "market"}
    assert s["over25"]["read"] > s["over25"]["market"]        # 4 goals: the market's higher over chance did better
