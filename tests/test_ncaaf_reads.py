"""College previews and the early read: lines, the read's direction and drivers, and its tracker."""

import pandas as pd

from betlab import cfb_reads
from betlab.cards import preview_ncaaf as PV
from betlab.models import game_ncaaf as GC

FIT = {"luck_coef": 50.0,
       "spread": {"coef": [0.0, 10.0, 0.0, 0.0, 0.0, 5.0, 0.0], "pred_sd": 1.5},
       "total": {"coef": [15.0, 8.0, 0.1, 0.0, -0.3], "pred_sd": 1.4}}


def test_lines_and_spread_labels():
    ev = pd.DataFrame([
        {"bookmaker": "fanduel", "market": "spreads", "outcome": "Home U", "point": -7.0, "price": -110},
        {"bookmaker": "fanduel", "market": "spreads", "outcome": "Away U", "point": 7.0, "price": -110},
        {"bookmaker": "draftkings", "market": "spreads", "outcome": "Home U", "point": -6.5, "price": -110},
        {"bookmaker": "fanduel", "market": "totals", "outcome": "Over", "point": 51.5, "price": -108},
        {"bookmaker": "fanduel", "market": "totals", "outcome": "Under", "point": 51.5, "price": -112},
    ])
    ln = PV._lines(ev, "Home U")
    assert ln["spread_home"] == 6.75 and ln["fd_spread_home"] == 7.0 and ln["fd_total"] == 51.5
    assert PV._fmt_spread("Home U", 7.0, True) == "Home U -7" and PV._fmt_spread("Away U", 7.0, False) == "Away U +7"


def test_early_read_direction_and_drivers():
    f = {"net_success": 0.2, "net_epa": 0.0, "net_points": 0.0, "net_stuff_rate": 0.0, "net_line_yards": 0.3,
         "sum_epa": 0.5, "sum_plays": 5.0, "sum_success": 0.0}
    rd = GC.early_read(f, 3.0, 50.0, FIT)
    assert rd["spread"]["edge_pts"] == 3.5 and rd["spread"]["strength"] > 2        # home covers
    assert rd["spread"]["drivers"] == ["success rate", "line play (line yards)"]
    assert rd["total"]["edge_pts"] > 0 and "the total itself (extreme totals drift back)" in rd["total"]["drivers"]
    assert GC.early_read(f, None, None, FIT) == {}


def test_tracker_keeps_the_first_read_and_grades_it(tmp_path, monkeypatch):
    monkeypatch.setattr(cfb_reads, "PATH", tmp_path / "cfb_reads.csv")
    base = {"game_id": "1", "season": 2026, "week": 5, "kickoff": "2026-10-03T16:00:00+00:00", "matchup": "A @ H",
            "book": "fanduel"}
    first = [{**base, "kind": "spread", "side": "home", "label": "H -7", "line": 7.0, "price": -110, "strength": 1.5, "edge": 2.0},
             {**base, "kind": "total", "side": "under", "label": "Under 55", "line": 55.0, "price": -110, "strength": -1.2, "edge": -1.8}]
    assert cfb_reads.record(first, pd.Timestamp("2026-09-29T14:00Z")) == 2
    later = [{**first[0], "line": 8.5, "strength": 0.4}, {**first[1], "line": 53.0}]
    cfb_reads.record(later, pd.Timestamp("2026-10-03T15:00Z"))
    df = cfb_reads.load().set_index("read_id")
    assert df.loc["1-spread", "first_line"] == 7.0 and df.loc["1-spread", "last_line"] == 8.5
    games = pd.DataFrame({"game_id": ["1"], "margin": [10.0], "home_pts": [31.0], "away_pts": [21.0]})
    assert cfb_reads.grade(games) == 2
    df = cfb_reads.load().set_index("read_id")
    assert df.loc["1-spread", "status"] == "won" and df.loc["1-spread", "clv_pts"] == 1.5   # line moved to -8.5: our way
    assert df.loc["1-total", "status"] == "won" and df.loc["1-total", "clv_pts"] == 2.0     # 52 < 55, total fell to 53
    s = cfb_reads.summary()
    assert s["spread"]["won"] == 1 and s["total"]["n"] == 1
