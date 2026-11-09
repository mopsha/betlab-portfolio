import numpy as np
import pandas as pd
import pytest

from betlab import staking
from betlab.models.margins import KeyNumberDist
from betlab.models.ratings import fit_ratings

TIERS = [{"min_ev": 0.03, "units": 1.0}, {"min_ev": 0.06, "units": 1.5}, {"min_ev": 0.09, "units": 2.0}]


def test_tier_units():
    assert staking.tier_units(0.02, TIERS) == 0
    assert staking.tier_units(0.05, TIERS) == 1.0
    assert staking.tier_units(0.07, TIERS) == 1.5
    assert staking.tier_units(0.12, TIERS) == 2.0


def test_quarter_kelly_units():
    # full Kelly at 55% / -110 is 5.5% of bankroll; a quarter is 1.375%; 1u = 1%
    assert staking.kelly_units(0.55, -110, 0, 0.01, 0.25, 2) == pytest.approx(1.38, abs=0.01)
    assert staking.kelly_units(0.70, -110, 0, 0.01, 0.25, 2) == 2  # capped


def test_exposure_caps():
    picks = pd.DataFrame({"event_id": ["a", "a", "b", "c", "d"], "ev": [0.09, 0.05, 0.08, 0.07, 0.04],
                          "units": [2.0, 2.0, 2.0, 2.0, 2.0]})
    capped = staking.apply_exposure_caps(picks, "units", max_per_game=2, max_per_day=5).set_index("ev")
    assert capped.loc[0.09, "units"] == 2 and capped.loc[0.05, "units"] == 0  # game a is full
    assert capped["units"].sum() == 5                                         # day cap


@pytest.fixture(scope="module")
def nfl_like_dist():
    rng = np.random.default_rng(0)
    # margins with extra mass on 3 and 7, like real football
    base = np.rint(rng.normal(1.5, 13.5, 20000)).astype(int)
    keys = rng.choice([3, -3, 7, -7], 5000)
    return KeyNumberDist.fit(np.concatenate([base, keys]), -70, 70, symmetric=True)


def test_key_numbers_get_extra_weight(nfl_like_dist):
    w = dict(zip(nfl_like_dist.support, nfl_like_dist.weights))
    assert w[3] > 1.5 and w[7] > 1.5 and w[5] < 1.2


def test_median_centered_at_prediction(nfl_like_dist):
    # when our number equals a half-point line, each side is exactly 50%
    over, push, under = nfl_like_dist.over_push_under(3.5, 13.5, 3.5)
    assert over == pytest.approx(under, abs=1e-6) and push == 0
    # on an integer line the push takes its share and the rest splits evenly
    over, push, under = nfl_like_dist.over_push_under(3.0, 13.5, 3.0)
    assert push > 0.05 and over == pytest.approx(under, abs=1e-6)


def test_crossing_a_key_number_is_worth_more(nfl_like_dist):
    # buying from -3.5 to -2.5 crosses 3; -5.5 to -4.5 doesn't
    gain_3 = nfl_like_dist.over_push_under(4, 13.5, 2.5)[0] - nfl_like_dist.over_push_under(4, 13.5, 3.5)[0]
    gain_5 = nfl_like_dist.over_push_under(4, 13.5, 4.5)[0] - nfl_like_dist.over_push_under(4, 13.5, 5.5)[0]
    assert gain_3 > 1.5 * gain_5


def test_center_for_round_trips(nfl_like_dist):
    center = nfl_like_dist.center_for(3.0, 13.0, 0.55)
    over, push, under = nfl_like_dist.over_push_under(center, 13.0, 3.0)
    # pmf caches on the center rounded to 0.001 points, hence the tolerance
    assert over / (over + under) == pytest.approx(0.55, abs=1e-4)


def test_ratings_recover_known_strengths():
    rng = np.random.default_rng(1)
    true_off = {"A": 5, "B": 0, "C": -5}
    rows = []
    for d in range(300):
        h, a = rng.choice(list(true_off), 2, replace=False)
        rows.append({"date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=d), "home_team": h, "away_team": a,
                     "neutral": False, "home_pts": 21 + 1.5 + true_off[h] + rng.normal(0, 3),
                     "away_pts": 21 - 1.5 + true_off[a] + rng.normal(0, 3)})
    r = fit_ratings(pd.DataFrame(rows), pd.Timestamp("2026-01-01"), "home_pts", "away_pts",
                    half_life_days=1e9, ridge=0.1, lookback_days=10_000)
    assert r.off["A"] - r.off["C"] == pytest.approx(10, abs=1)
    assert r.home_edge == pytest.approx(3, abs=1)
