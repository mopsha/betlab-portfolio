"""The NBA team model against historical closing lines (backtest_nba.market_lines/_weight)."""

import numpy as np
import pandas as pd
import pytest

from betlab import backtest_nba as B

TIP = pd.Timestamp("2026-01-10T00:00:00Z")


def line_rows():
    rows = []
    for book, spread, total in (("pinnacle", -5.5, 221.5), ("lowvig", -6.5, 222.5), ("fanduel", -5.0, 220.5)):
        for outcome, point, price in (("Los Angeles Clippers", spread, -110), ("Boston Celtics", -spread, -110)):
            rows.append({"event_id": "e1", "commence_time": TIP, "home_team": "Los Angeles Clippers",
                         "away_team": "Boston Celtics", "bookmaker": book, "market": "spreads",
                         "outcome": outcome, "point": point, "price": price, "hours_before": 0.5})
        for outcome in ("Over", "Under"):
            rows.append({"event_id": "e1", "commence_time": TIP, "home_team": "Los Angeles Clippers",
                         "away_team": "Boston Celtics", "bookmaker": book, "market": "totals",
                         "outcome": outcome, "point": total, "price": -105 if outcome == "Over" else -115,
                         "hours_before": 0.5})
    return pd.DataFrame(rows)


def test_market_lines_use_the_sharp_median_and_match_espn_names_and_tips():
    sch = pd.DataFrame({"game_id": ["g1", "g2"], "home_display_name": ["LA Clippers", "LA Clippers"],
                        "start_date": [(TIP + pd.Timedelta(minutes=10)).isoformat(),
                                       (TIP + pd.Timedelta(days=2)).isoformat()]})
    m = B.market_lines(line_rows(), sch)
    assert m["game_id"].tolist() == ["g1"]                         # the other Clippers home game is days away
    r = m.iloc[0]
    assert r["mkt_margin"] == pytest.approx(6.0) and r["mkt_total"] == pytest.approx(222.0)   # Pinnacle + LowVig
    assert r["fd_spread"] == -5.0 and r["fd_total"] == 220.5 and r["fd_under_price"] == -115


def test_blend_weight_recovers_the_truth():
    rng = np.random.default_rng(0)
    market = rng.normal(0, 6, 4000)
    model = market + rng.normal(0, 3, 4000)
    y = market + 0.3 * (model - market) + rng.normal(0, 10, 4000)
    w, se = B._weight(y, market, model)
    assert abs(w - 0.3) < 3 * se and se < 0.1
