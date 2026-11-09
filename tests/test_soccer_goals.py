"""Soccer goals and both teams to score (Oct 12): FanDuel against Pinnacle's no-vig, market-only."""

import pandas as pd

from betlab import grading
from betlab.cards import soccer_goals as G


def _rows():
    r = []
    for book, o, u, y, n in (("pinnacle", -110, -110, -105, -115), ("fanduel", 120, -150, -110, -120)):
        r += [{"bookmaker": book, "market": "alternate_totals", "outcome": "Over", "point": 2.5, "price": o},
              {"bookmaker": book, "market": "alternate_totals", "outcome": "Under", "point": 2.5, "price": u},
              {"bookmaker": book, "market": "btts", "outcome": "Yes", "point": None, "price": y},
              {"bookmaker": book, "market": "btts", "outcome": "No", "point": None, "price": n}]
    r.append({"bookmaker": "fanduel", "market": "alternate_totals", "outcome": "Over", "point": 0.5, "price": -1000})
    return pd.DataFrame(r).assign(event_id="m1", commence_time="2026-10-18T14:00:00Z", home_team="Arsenal",
                                  away_team="Chelsea", snapshot_ts="2026-10-18T13:20:00Z")


def test_fanduel_is_priced_against_pinnacle_at_the_same_number():
    o = G.evaluate(_rows(), "epl", pd.Timestamp("2026-10-18T13:25:00Z")).set_index("label")
    assert set(o.index) == {"Over 2.5 goals", "Under 2.5 goals", "Both teams to score", "Both teams to score: No"}
    assert abs(o.loc["Over 2.5 goals", "p_market"] - 0.5) < 1e-9            # Pinnacle -110/-110
    assert o.loc["Over 2.5 goals", "ev"] > 0.09 and o.loc["Under 2.5 goals", "ev"] < 0   # FanDuel +120 on a coin flip
    assert (o["market_source"] == "Pinnacle no-vig").all() and (o["w_model"] == 0).all()
    assert o.loc["Over 2.5 goals", "market"] == "totals" and o.loc["Both teams to score", "market"] == "btts"


def test_settlement():
    assert G.settle("totals", "Over", 2.5, 2, 1) == "won" and G.settle("totals", "Under", 2.5, 2, 1) == "lost"
    assert G.settle("totals", "Over", 2.0, 1, 1) == "push"
    assert G.settle("btts", "Yes", None, 1, 1) == "won" and G.settle("btts", "No", None, 2, 0) == "won"


def test_goals_picks_grade_from_the_score_with_clv_against_the_last_pull():
    picks = pd.DataFrame([{"pick_id": "p1", "league": "epl", "status": "open", "matchup": "Arsenal vs Chelsea",
                           "commence_time": "2026-10-18T14:00:00Z", "market": "totals", "side": "Over", "point": 2.5,
                           "price": 120.0, "units_flat": 1.0, "event_id": "m1"}])
    out = grading.grade_soccer(picks, "epl", now=pd.Timestamp("2026-10-19T12:00:00Z"),
                               goals_result=lambda *a: {"hg": 2, "ag": 1}, goals_close=lambda *a: 0.52).iloc[0]
    assert out["status"] == "won" and out["profit_flat"] == 1.2
    assert abs(out["clv"] - (0.52 * 2.2 - 1)) < 1e-4


def test_goals_and_scorer_close_need_a_pull_after_the_pick(tmp_path, monkeypatch):
    """Oct 13: the pull a pick came from only repeats its own EV, so it isn't a close."""
    from betlab import config
    from betlab.cards import props_soccer, soccer_goals
    from betlab.sources import odds_api

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    key = config.settings()["leagues"]["ucl"]["sport_key"]
    rows = [{"event_id": "e1", "market": m, "player": "Harry Kane", "bookmaker": "pinnacle", "outcome": o, "point": 2.5,
             "price": -110, "snapshot_ts": "2026-10-13T18:15:04+00:00", "commence_time": "2026-10-13T19:00:00Z"}
            for m in ("alternate_totals", "player_goal_scorer_anytime") for o in ("Over", "Under", "Yes", "No")]
    odds_api.save_snapshot(pd.DataFrame(rows), key, "2026-10-13T18:15:04+00:00", "props")
    logged = "2026-10-13T18:15:26+00:00"
    assert soccer_goals.close("ucl", "e1", "totals", "Over", 2.5, "2026-10-13T19:00:00Z", logged) is None
    assert props_soccer.scorer_close("ucl", "e1", "Harry Kane", "2026-10-13T19:00:00Z", logged) is None
