import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("backtest_drift", Path(__file__).parents[1] / "scripts" / "backtest_drift.py")
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)

SOCCER = """  epl: 3040 matches, 6s
    league  season  matches  market  model  w (from earlier seasons)  blend    gain  gain_se
bundesliga    2024      306  0.9442 0.9805                      0.05 0.9453 -0.0012   0.0004
   serie_a    2026      200  0.9895 1.0124                      0.00 0.9895  0.0000   0.0000
       all    13425 -0.0001 0.0042                  5884              0.4871
"""
NFL = """sp {'n': 1698, 'market': 0.6918, 'model': 0.713, 'blend': 0.6922, 'w_model': 0.09}
market  min_ev   record  win_pct  units    roi
    sp    0.00  80-71-3    0.530    3.7  0.024
"""


def test_only_closed_soccer_seasons_are_read():
    assert D.parse_soccer(SOCCER) == {"soccer bundesliga 2024 market": 0.9442, "soccer bundesliga 2024 model": 0.9805}


def test_nfl_summary_lines_are_read():
    assert D.parse_nfl(NFL) == {"nfl sp market": 0.6918, "nfl sp model": 0.713}


def test_drift_is_a_closed_season_moving_or_a_number_going_missing():
    base = {"soccer epl 2024 model": 0.98, "nfl sp model": 0.713, "soccer epl 2023 model": 0.97}
    assert D.compare(dict(base), base) == []
    assert D.compare({**base, "soccer epl 2025 model": 0.9}, base) == []                 # a newly closed season
    assert D.compare({**base, "nfl sp model": 0.716}, base) == []                        # NFL has room for this season
    assert len(D.compare({**base, "nfl sp model": 0.72}, base)) == 1
    assert "0.98 -> 0.982" in D.compare({**base, "soccer epl 2024 model": 0.982}, base)[0]
    assert "missing" in D.compare({"soccer epl 2024 model": 0.98, "nfl sp model": 0.713}, base)[0]
