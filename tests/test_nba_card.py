"""NBA game lines on the card (cards/nba.py) and their grading (grading.grade_nba), offline."""

import pandas as pd
import pytest

from betlab import grading
from betlab import odds_math as om
from betlab.cards import nba as card

HOME, AWAY = "Boston Celtics", "New York Knicks"
TIP = "2026-10-21T23:30:00Z"
ASOF = pd.Timestamp("2026-10-21T14:00:00Z")


def _snap(ts="2026-10-21T14:00:00Z", tip=TIP, pin_ml=(-150, 130), pin_spread=(-3.5, -105, -115),
          pin_total=(224.5, -110, -110), fd_ml=(-135, 115), fd_spread=(-3.5, -110, -110), fd_total=(224.5, -110, -110)):
    base = {"snapshot_ts": ts, "sport_key": "basketball_nba", "event_id": "e1", "commence_time": tip,
            "home_team": HOME, "away_team": AWAY, "player": None}
    rows = []
    for bk, ml, sp, tot in (("pinnacle", pin_ml, pin_spread, pin_total), ("fanduel", fd_ml, fd_spread, fd_total)):
        rows += [base | {"bookmaker": bk, "market": "h2h", "outcome": HOME, "point": None, "price": ml[0]},
                 base | {"bookmaker": bk, "market": "h2h", "outcome": AWAY, "point": None, "price": ml[1]},
                 base | {"bookmaker": bk, "market": "spreads", "outcome": HOME, "point": sp[0], "price": sp[1]},
                 base | {"bookmaker": bk, "market": "spreads", "outcome": AWAY, "point": -sp[0], "price": sp[2]},
                 base | {"bookmaker": bk, "market": "totals", "outcome": "Over", "point": tot[0], "price": tot[1]},
                 base | {"bookmaker": bk, "market": "totals", "outcome": "Under", "point": tot[0], "price": tot[2]}]
    return pd.DataFrame(rows)


def test_shift_keeps_the_same_number_and_moves_the_right_way():
    assert card.shift("totals", 0.52, 224.5, 224.5) == pytest.approx(0.52, abs=1e-6)
    assert card.shift("spreads", 0.47, -4.0, -4.0) == pytest.approx(0.47, abs=1e-6)  # whole numbers too
    # a lower total is easier to go over; a home favorite giving fewer points covers more often
    assert card.shift("totals", 0.50, 224.5, 223.5) > 0.50 > card.shift("totals", 0.50, 224.5, 225.5)
    assert card.shift("spreads", 0.50, -4.5, -3.5) > 0.50
    # half a point on an 18-point spread of totals is worth about 1 point of chance
    assert 0.008 < card.shift("totals", 0.50, 224.5, 224.0) - 0.50 < 0.015


def test_card_prices_fanduel_against_pinnacle():
    offers = card.evaluate(_snap(), ASOF, game_ids={(HOME, "2026-10-21"): "401"})
    assert set(offers["market"]) == {"h2h", "spreads", "totals"} and (offers["w_model"] == 0).all()
    ml = offers[offers["market"] == "h2h"].set_index("side")
    assert ml.loc[HOME, "ev"] > 0 > ml.loc[AWAY, "ev"]            # FanDuel -135 on a -150 favorite
    assert offers["matchup"].iloc[0] == f"{AWAY} @ {HOME}" and set(offers["game_ref"]) == {"401"}
    sp = offers[offers["market"] == "spreads"].set_index("side")
    assert sp.loc[HOME, "label"] == f"{HOME} -3.5" and sp.loc[HOME, "p_push"] == 0
    assert "same number" in sp.loc[HOME, "context"]


def test_a_nearby_sharp_number_is_moved_and_a_far_one_skipped():
    # Pinnacle 226.5 even, FanDuel 225 -110: FanDuel's over is 1.5 points easier, and 225 can push
    offers = card.evaluate(_snap(pin_total=(226.5, -105, -105), fd_total=(225.0, -110, -110)), ASOF, game_ids={})
    tot = offers[offers["market"] == "totals"].set_index("side")
    assert tot.loc["Over", "p_final"] > 0.53 and tot.loc["Over", "p_push"] == card.PUSH["totals"]
    assert tot.loc["Over", "ev"] == pytest.approx(
        om.expected_value(tot.loc["Over", "p_final"] * (1 - card.PUSH["totals"]), -110, card.PUSH["totals"]))
    assert "pinnacle hangs 226.5" in tot.loc["Over", "context"]
    far = card.evaluate(_snap(pin_total=(227.0, -110, -110), fd_total=(225.0, -110, -110)), ASOF, game_ids={})
    assert "totals" not in set(far["market"])


def test_preseason_games_are_skipped():
    assert card.evaluate(_snap(tip="2026-10-06T23:30:00Z"), pd.Timestamp("2026-10-06T14:00:00Z"), game_ids={}).empty


def _sched(hs, as_):
    return pd.DataFrame({"home_display_name": [HOME], "away_display_name": [AWAY], "home_score": [hs],
                         "away_score": [as_], "status_type_completed": [True], "tipoff": [pd.Timestamp(TIP)]})


def _open(offers, market, side):
    return offers[(offers["market"] == market) & (offers["side"] == side)].assign(status="open", units_flat=1.0)


def test_grade_settles_lines_and_measures_clv():
    offers = card.evaluate(_snap(), ASOF, game_ids={})
    picks = pd.concat([_open(offers, "h2h", HOME), _open(offers, "spreads", AWAY), _open(offers, "totals", "Over")],
                      ignore_index=True)
    close = _snap(ts="2026-10-21T23:00:00Z", pin_ml=(-170, 150))   # the market moved toward Boston
    out = grading.grade_nba(picks, now=pd.Timestamp("2026-10-22T14:00:00Z"), sched=_sched(110, 107),
                            snaps=[_snap(), close], box=pd.DataFrame())
    r = out.set_index("market")
    assert r.loc["h2h", "status"] == "won" and r.loc["h2h", "clv"] > 0
    assert r.loc["spreads", "status"] == "won"                       # NY +3.5 loses by 3
    assert r.loc["totals", "status"] == "lost" and r.loc["totals", "close_push"] == 0


def test_grade_waits_for_the_final_and_pushes_whole_numbers():
    offers = card.evaluate(_snap(fd_spread=(-3.0, -110, -110), pin_spread=(-3.0, -110, -110)), ASOF, game_ids={})
    pick = _open(offers, "spreads", HOME)
    later = pd.Timestamp("2026-10-22T14:00:00Z")
    out = grading.grade_nba(pick, now=later, sched=_sched(110, 107).assign(status_type_completed=False),
                            snaps=[_snap()], box=pd.DataFrame())
    assert out["status"].iloc[0] == "open"
    out = grading.grade_nba(pick, now=later, sched=_sched(110, 107), snaps=[_snap()], box=pd.DataFrame())
    assert out["status"].iloc[0] == "push" and out["close_push"].iloc[0] == card.PUSH["spreads"]


def test_a_moved_number_is_never_more_than_a_lean():
    from betlab import picks

    # FanDuel's over 222.5 at +100 against Pinnacle's 223.5: about 4% EV once moved, but untested
    offers = card.evaluate(_snap(pin_total=(223.5, -110, -110), fd_total=(222.5, 100, -120)), ASOF, game_ids={})
    over = offers[(offers["market"] == "totals") & (offers["side"] == "Over")]
    assert over["ev"].iloc[0] >= 0.03 and over["lean_only"].iloc[0]
    tiers = picks.classify(offers, ASOF).set_index("label")["tier"]
    assert tiers["Over 222.5"] == "lean"
    # the same edge at the same number is a pick
    same = card.evaluate(_snap(pin_total=(222.5, -125, 105), fd_total=(222.5, 100, -120)), ASOF, game_ids={})
    assert picks.classify(same, ASOF).set_index("label")["tier"]["Over 222.5"] == "pick"
