"""The soccer game page's moneyline read (Mike, Oct 15): the market, its move, the best book, Europe nearby."""

import pandas as pd

from betlab.cards import analysis_soccer as A


def _game(**kw):
    lines = [
        {"side": "Arsenal", "price": 150.0, "ev": -0.02, "dk_price": 160.0, "dk_ev": 0.012, "p_market": 0.39, "first_p_market": 0.35},
        {"side": "Draw", "price": 240.0, "ev": -0.03, "dk_price": None, "dk_ev": None, "p_market": 0.28, "first_p_market": 0.29},
        {"side": "Chelsea", "price": 190.0, "ev": -0.04, "dk_price": 185.0, "dk_ev": -0.05, "p_market": 0.33, "first_p_market": 0.36}]
    return {"event_id": "e1", "league": "epl", "home": "Arsenal", "away": "Chelsea",
            "commence_time": "2026-10-18T15:00:00Z", "first_seen": "2026-10-13T14:00:00Z", "lines": lines} | kw


def test_the_read_names_the_market_its_move_and_the_best_book():
    ml = A.moneyline(_game())
    s = {x["side"]: x for x in ml["sides"]}
    assert s["Arsenal"]["best_book"] == "draftkings" and s["Arsenal"]["move"] == 0.04
    assert s["Draw"]["best_book"] == "fanduel"                       # DraftKings posted no draw
    assert "Arsenal 39%, the draw 28% and Chelsea 33%" in ml["summary"]
    assert "moved 4 points toward Arsenal" in ml["summary"]
    assert "Arsenal at DraftKings +160, +1.2% EV, under the 3%" in ml["summary"]
    assert A.moneyline(_game(lines=_game()["lines"][:2])) is None    # a 3-way needs all three sides


def test_europe_within_four_days_either_side():
    cups = pd.DataFrame({"league": ["ucl", "uel", "ucl"], "event_id": ["c1", "c2", "c3"],
                         "home": ["Arsenal", "Chelsea", "Chelsea"], "away": ["PSV", "Lyon", "Porto"],
                         "t": pd.to_datetime(["2026-10-15T19:00:00Z", "2026-10-22T19:00:00Z", "2026-10-21T16:45:00Z"], utc=True)})
    ml = A.moneyline(_game(), cups=cups)
    assert ml["europe"]["Arsenal"] == {"competition": "Champions League", "opponent": "PSV", "days": -2.8}
    assert ml["europe"]["Chelsea"]["opponent"] == "Porto" and ml["europe"]["Chelsea"]["days"] == 3.1   # the nearer
    assert "Arsenal played PSV in the Champions League 3 days ago." in ml["summary"]
    assert "Chelsea play Porto in the Champions League in 3 days." in ml["summary"]


def test_the_lineup_read_carries_its_record_and_no_weight():
    teams = [{"team": "Arsenal", "goals_model": 2.4}, {"team": "Chelsea", "goals_model": 0.7}]
    rec = {"n": 27, "log_loss": 1.09, "log_loss_mkt": 0.90}
    ml = A.moneyline(_game(), teams, record=rec, confirmed=True)
    h, d, a = (x["p_lineup"] for x in ml["sides"])
    assert abs(h + d + a - 1) < 1e-3 and h > 0.6
    assert "lineup read leans Arsenal" in ml["summary"] and "worse than the market so far" in ml["summary"]
    assert "lineup read" not in A.moneyline(_game(), teams, record=rec, confirmed=False)["summary"]   # guesses stay quiet


def test_the_record_scores_both_reads_on_graded_matches():
    reads = pd.DataFrame({"xg_home": [1.5, 1.0], "xg_away": [1.0, 1.0], "xg_home_mkt": [1.5, 1.2],
                          "xg_away_mkt": [1.0, 1.1], "home_goals": [2, None], "away_goals": [0, None]})
    r = A.lineup_record(reads)
    assert r["n"] == 1 and r["log_loss"] == r["log_loss_mkt"]
