import numpy as np
import pytest

from betlab.models import props_nfl as P


VOL = {"targets": 34.0, "carries": 26.0, "attempts": 35.0}


def profile(**over):
    base = {"t_share": 0.22, "c_share": 0.02, "catch": 0.66, "ypt": 8.5, "ypc": 5.0,
            "ypa": 7.0, "a_share": 0.97, "games": 10}
    return base | over


def test_draws_are_sane_for_every_position():
    p = P.PropParams()
    for pos in P.SKILL:
        d = P.simulate(VOL, profile(), pos, p, n=3000, seed=1)
        assert (d["receptions"] <= d["targets"]).all()
        assert (d["targets"] >= 0).all() and (d["carries"] >= 0).all()
        assert ((d["receptions"] == 0) <= (d["receiving_yards"] == 0)).all()  # no catches, no yards
        assert ("passing_yards" in d) == (pos == "QB")


def test_bigger_role_means_more_volume():
    p = P.PropParams()
    small = P.simulate(VOL, profile(t_share=0.10), "WR", p, n=4000, seed=2)["targets"].mean()
    big = P.simulate(VOL, profile(t_share=0.28), "WR", p, n=4000, seed=2)["targets"].mean()
    assert big > 2 * small


def test_prob_over_handles_pushes():
    draws = np.array([4, 5, 5, 6, 7])
    over, push = P.prob_over(draws, 5)
    assert push == pytest.approx(0.4) and over == pytest.approx(2 / 3)  # 2 of the 3 non-push draws are over
