"""The prop-line tracker (the Games tab's track record and future training data) and the receiver matchups."""

import numpy as np
import pandas as pd

from betlab import tracking
from betlab.models import matchups_nfl as MU
from betlab.sources import nflverse


def row(player_id="p1", stat="receiving_yards", line=50.5, kickoff="2026-09-27T17:00:00+00:00", **kw):
    base = {"season": 2026, "week": 3, "game_id": "2026_03_AAA_BBB", "commence_time": kickoff, "matchup": "AAA @ BBB",
            "player": f"Player {player_id}", "player_id": player_id, "team": "AAA", "opp": "BBB", "stat": stat,
            "line": line, "fd_over": -110, "fd_under": -110, "p_market": 0.5, "pass_edge": 0.0, "dropbacks_log": 0.0,
            "pass_adj": 0.0, "ypt": None, "deep": None, "p_script": 0.53, "script_side": "over",
            "matchup_score": 0.0, "p_matchup": None, "matchup_side": None}
    return base | kw


def test_record_updates_until_kickoff_then_freezes(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking, "PATH", tmp_path / "prop_lines.csv")
    t1 = pd.Timestamp("2026-09-26T14:00Z")
    assert tracking.record([row(), row("p2")], t1) == 2
    assert tracking.record([row(line=51.5)], pd.Timestamp("2026-09-27T12:00Z")) == 1
    df = tracking.load()
    assert len(df) == 2 and df.loc[df.player_id == "p1", "line"].item() == 51.5
    assert df.loc[df.player_id == "p1", "first_seen"].item() == t1.isoformat(timespec="seconds")
    assert tracking.record([row(line=60.5)], pd.Timestamp("2026-09-27T18:00Z")) == 0   # after kickoff: frozen
    assert tracking.load().loc[lambda d: d.player_id == "p1", "line"].item() == 51.5


def test_grade_and_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking, "PATH", tmp_path / "prop_lines.csv")
    tracking.record([row("p1", line=50.5), row("p2", line=40.5, script_side="under", p_script=0.47),
                     row("p3", line=30.5), row("p4", line=20.5)], pd.Timestamp("2026-09-26T14:00Z"))
    ps = pd.DataFrame({"player_id": ["p1", "p2"], "game_id": "2026_03_AAA_BBB", "receiving_yards": [61.0, 12.0]})
    sn = pd.DataFrame({"player_id": ["p1", "p2", "p3"], "game_id": "2026_03_AAA_BBB", "offense_snaps": [50, 40, 10]})
    monkeypatch.setattr(nflverse, "load_player_stats", lambda seasons: ps)
    monkeypatch.setattr(nflverse, "load_snap_counts", lambda seasons: sn)
    assert tracking.grade(pd.Timestamp("2026-09-28T12:00Z")) == 4
    df = tracking.load().set_index("player_id")
    assert df.loc["p3", "actual"] == 0.0 and df.loc["p4", "status"] == "void"   # played without a catch; didn't play
    s = tracking.summary()
    assert s["script"]["n"] == 3 and s["script"]["hits"] == 2          # p1 over hit, p2 under hit, p3 over missed
    assert s["script"]["market"] == 0.5 and s["matchup"] == {"n": 0}


def test_matchup_features_and_read():
    rng = np.random.default_rng(0)
    rows = []
    for i in range(400):
        d = "AAA" if i % 2 else "BBB"                    # AAA's defense gives up far more to wide receivers
        rows.append({"game_id": f"g{i // 20}", "date": pd.Timestamp("2026-09-01") + pd.Timedelta(days=i // 40),
                     "posteam": "XXX", "defteam": d, "receiver_player_id": "deep1" if i % 4 < 2 else "short1",
                     "group": "WR", "air_yards": 25.0 if i % 4 < 2 else 5.0,
                     "rec_yds": (14.0 if d == "AAA" else 6.0) + rng.normal(0, 1)})
    t = pd.DataFrame(rows)
    rt = MU.ratings(t, "2026-09-30")
    soft, hard = MU.features(rt, "deep1", "WR", "AAA"), MU.features(rt, "deep1", "WR", "BBB")
    assert soft["ypt"] > 0 > hard["ypt"] and soft["ypt_rank"] == 2
    assert soft["deep"] > 0 > hard["deep"] and soft["deep_share"] > rt["deep_lg"]
    cfg = {"ypt": {"coef": 0.043, "sd": 0.085}, "deep": {"coef": 0.065, "sd": 0.017}}
    p_up, s_up = MU.read(0.5, soft, cfg)
    assert p_up > 0.5 and s_up > 0 and MU.read(0.5, {}, cfg) == (0.5, 0.0)
