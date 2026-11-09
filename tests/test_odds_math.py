import pytest

from betlab import odds_math as om


def test_conversions_round_trip():
    assert om.american_to_decimal(-110) == pytest.approx(1.9090909)
    assert om.american_to_decimal(150) == pytest.approx(2.5)
    assert om.decimal_to_american(2.5) == pytest.approx(150)
    for american in (-250, -110, 100, 120, 450):
        assert om.decimal_to_american(om.american_to_decimal(american)) == pytest.approx(american)


def test_invalid_odds_rejected():
    with pytest.raises(ValueError):
        om.american_to_decimal(50)
    with pytest.raises(ValueError):
        om.prob_to_american(1.2)


def test_break_even_probabilities():
    assert om.implied_prob(-110) == pytest.approx(0.5238095)
    assert om.implied_prob(150) == pytest.approx(0.4)
    assert om.prob_to_american(0.5) == pytest.approx(100)


def test_hold_of_standard_market():
    assert om.hold([-110, -110]) == pytest.approx(0.04545, abs=1e-4)
    assert om.overround([-110, -110]) == pytest.approx(0.047619, abs=1e-5)


@pytest.mark.parametrize("method", ["multiplicative", "power", "shin"])
def test_devig_symmetric_market_is_fifty_fifty(method):
    assert om.devig([-110, -110], method) == pytest.approx([0.5, 0.5])


@pytest.mark.parametrize("method", ["multiplicative", "power", "shin"])
def test_devig_sums_to_one(method):
    assert sum(om.devig([-200, 170], method)) == pytest.approx(1)
    assert sum(om.devig([150, 230, 190], method)) == pytest.approx(1)  # soccer 1X2


def test_power_and_shin_take_more_vig_off_the_longshot():
    multiplicative = om.devig([-200, 170], "multiplicative")
    assert om.devig([-200, 170], "power")[1] < multiplicative[1]
    assert om.devig([-200, 170], "shin")[1] < multiplicative[1]


def test_expected_value():
    assert om.expected_value(0.55, -110) == pytest.approx(0.05)
    assert om.expected_value(om.implied_prob(-110), -110) == pytest.approx(0)
    # a push returns the stake: 50% win, 10% push, 40% loss at even money
    assert om.expected_value(0.5, 100, p_push=0.1) == pytest.approx(0.1)


def test_kelly_fraction():
    assert om.kelly_fraction(0.55, -110) == pytest.approx(0.055)
    assert om.kelly_fraction(0.50, -110) == 0.0


def test_bonus_bet_value():
    # a $1 bonus bet on a fair +300 shot (25%) is worth 75 cents
    assert om.bonus_bet_value(0.25, 300) == pytest.approx(0.75)


def test_parlay_house_edge_compounds():
    single_leg_edge = om.expected_value(0.5, -110)  # -4.55%
    four_leg = om.parlay_ev([0.5] * 4, [-110] * 4)
    assert four_leg == pytest.approx(-(1 - (1 + single_leg_edge) ** 4))
    assert four_leg < 3.5 * single_leg_edge  # roughly 4x worse than one bet


def test_clv_sign():
    p_close = om.devig([-125, 105])[0]  # market closed around -125 on our side
    assert om.clv(-105, p_close) > 0    # we got a better price than the close
    assert om.clv(-130, p_close) < 0    # we paid more than the close
