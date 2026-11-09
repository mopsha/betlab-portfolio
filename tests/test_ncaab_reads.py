"""College basketball reads: spreads and, from Oct 12, totals (ncaab_reads.py)."""

import pandas as pd


def test_totals_reads_are_tracked_beside_spreads(tmp_path, monkeypatch):
    """Oct 12: our total vs the posted total, graded on the final total and the close's move."""
    from betlab import ncaab_reads as NR

    monkeypatch.setattr(NR, "PATH", tmp_path / "ncaab_reads.csv")
    asof = pd.Timestamp("2026-11-10T15:00:00Z")
    base = {"event_id": "e1", "game_id": 7, "commence_time": "2026-11-11T00:00:00Z", "matchup": "Army @ Duke",
            "home": "Duke", "away": "Army", "book": "draftkings"}
    spread = base | {"side": "Duke", "line": -20.5, "price": -110, "model_margin": 25.0, "market_center": 20.5, "gap": 4.5}
    total = base | {"kind": "total", "side": "Over", "line": 141.5, "price": -110, "model_total": 147.0,
                    "market_center": 141.5, "gap": 5.5}
    assert NR.record([spread, total], asof) == 2
    df = NR.load()
    assert sorted(df["read_id"]) == ["e1", "e1:total"]
    games = pd.DataFrame([{"game_id": 7, "home_team": "Duke", "away_team": "Army", "home_pts": 85.0, "away_pts": 62.0,
                           "margin": 23.0, "total": 147.0, "spread_line": 21.5, "total_line": 143.5,
                           "date": pd.Timestamp("2026-11-10")}])
    assert NR.grade(games, now=pd.Timestamp("2026-11-11T12:00:00Z")) == 2
    t = NR.load().set_index("read_id").loc["e1:total"]
    assert t["result"] == "won" and float(t["clv_pts"]) == 2.0 and float(t["home_margin"]) == 147.0
    s = NR.summary()
    assert s["graded"] == 1 and s["totals"]["graded"] == 1 and s["totals"]["avg_clv_pts"] == 2.0
