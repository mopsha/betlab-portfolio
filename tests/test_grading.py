import pandas as pd

from betlab.grading import settle_prop
import pytest

from betlab import grading


@pytest.mark.parametrize("side_margin,point,expected", [
    (7, -3.5, "won"),     # won by 7, laid 3.5
    (3, -3.0, "push"),    # won by exactly 3 at -3
    (2, -3.0, "lost"),
    (-2, 2.5, "won"),     # lost by 2 getting 2.5
    (-3, 2.5, "lost"),
    (0, 0, "push"),       # moneyline tie is refunded
])
def test_settle(side_margin, point, expected):
    assert grading.settle(side_margin, point) == expected


def test_profit():
    assert grading.profit("won", -110, 1) == pytest.approx(0.9091, abs=1e-4)
    assert grading.profit("won", 150, 2) == pytest.approx(3.0)
    assert grading.profit("lost", 150, 2) == -2
    assert grading.profit("push", -110, 1) == 0


def test_football_retains_the_closing_push_chance_without_changing_clv(monkeypatch):
    from types import SimpleNamespace
    from betlab.cards import nfl

    games = pd.DataFrame([{"game_id": "g", "home_team": "SEA", "away_team": "NE", "margin": 3,
                           "total": 23, "spread_line": 3, "total_line": 23,
                           "home_spread_odds": -110, "away_spread_odds": -110,
                           "over_odds": -110, "under_odds": -110}])
    dist = SimpleNamespace(center_for=lambda *args: 0, over_push_under=lambda *args: (0.45, 0.1, 0.45))
    params = SimpleNamespace(market_margin_sd=10, market_total_sd=10)
    monkeypatch.setattr(nfl.LEAGUE, "load_games", lambda: games)
    monkeypatch.setattr(nfl, "load_model", lambda _: (params, dist, dist))
    base = {"league": "nfl", "game_ref": "g", "kind": "game", "units_flat": 1,
            "status": "open", "price": 120}
    rows = pd.DataFrame([base | {"market": "spreads", "side": "SEA", "point": -3},
                         base | {"market": "totals", "side": "Over", "point": 23}])
    result = grading.grade_football(rows)
    assert result["status"].tolist() == ["push", "push"]
    assert result["close_push"].tolist() == pytest.approx([0.1, 0.1])
    assert result["clv"].tolist() == pytest.approx([0.09, 0.09])
    assert result["price"].tolist() == [120, 120]


def test_grade_nfl_real_week_one():
    """2026 week 1: NE 10 @ SEA 13, closed SEA -3. A SEA -3 bet pushes; SEA -2.5 wins."""
    base = {"league": "nfl", "event_id": "x", "game_ref": "2026_01_NE_SEA", "market": "spreads",
            "player": None, "units_flat": 1.0, "status": "open"}
    picks = pd.DataFrame([
        base | {"side": "SEA", "point": -3.0, "price": -110},
        base | {"side": "SEA", "point": -2.5, "price": -120},
        base | {"side": "NE", "point": 3.5, "price": -105},
        base | {"market": "totals", "side": "Over", "point": 44.5, "price": -110},
    ])
    graded = grading.grade_nfl(picks)
    assert graded["status"].tolist() == ["push", "won", "won", "lost"]
    # getting NE +3.5 when the market closed +3 is a better number than the close: positive CLV
    assert graded.loc[2, "clv"] > 0
    assert graded["graded_at"].notna().all()


def test_settle_prop_overs_unders_and_pushes():
    assert settle_prop(5, "Over", 4.5) == "won" and settle_prop(4, "Over", 4.5) == "lost"
    assert settle_prop(0, "Under", 0.5) == "won" and settle_prop(47, "Under", 46.5) == "lost"
    assert settle_prop(40, "Over", 40) == "push"



def test_one_leagues_failure_does_not_block_the_others(tmp_path, monkeypatch, capsys):
    """Oct 21 risk: the NBA's new-season box-score file isn't published yet (404). Before, the error
    stopped grade_all before saving, so NFL picks went ungraded and the worker's daily run stopped."""
    from betlab import ledger

    path = tmp_path / "picks.csv"
    rows = pd.DataFrame([{"pick_id": "n1", "league": "nba", "status": "open"},
                         {"pick_id": "f1", "league": "nfl", "status": "open"}])
    monkeypatch.setattr(ledger, "load", lambda p=None: rows.copy())
    saved = {}
    monkeypatch.setattr(ledger, "save", lambda df, p=None: saved.setdefault("df", df))
    monkeypatch.setattr(grading, "fill_close_source", lambda df: df)

    def nba_down(df):
        raise RuntimeError("404 player_box_2027.parquet")

    def nfl_ok(df):
        df = df.copy()
        df.loc[df["league"] == "nfl", "status"] = "won"
        return df

    monkeypatch.setattr(grading, "GRADERS", {"nba": nba_down, "nfl": nfl_ok})
    assert grading.grade_all(path) == 1
    assert saved["df"].set_index("pick_id")["status"].to_dict() == {"n1": "open", "f1": "won"}
    assert "grading nba: not graded" in capsys.readouterr().out
