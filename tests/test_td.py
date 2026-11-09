"""Anytime TD read: red-zone features from play-by-play, the live read, the blend, ticket
ranking (by Pinnacle's chance since Oct 25), and the tracker."""

import numpy as np
import pandas as pd
import pytest

from betlab import sgp, sgp_plus, td_reads
from betlab.models import td_nfl as T


def season(n_games=8):
    """Team KC: back 'rb' gets most carries inside the 10; receiver 'wr' gets targets outside it."""
    plays, stats = [], []
    for w in range(1, n_games + 1):
        gid = f"2026_{w:02d}_KC_X"
        for i in range(30):
            yl = 5 if i < 6 else 50                       # 6 plays inside the 10 each game
            if i % 2 == 0:
                plays.append({"game_id": gid, "season": 2026, "week": w, "posteam": "KC", "yardline_100": yl,
                              "play_type": "run", "rusher_player_id": "rb", "receiver_player_id": None})
            else:
                plays.append({"game_id": gid, "season": 2026, "week": w, "posteam": "KC", "yardline_100": yl,
                              "play_type": "pass", "rusher_player_id": None, "receiver_player_id": "wr" if yl > 10 else "rb"})
        for pid, pos, td in (("rb", "RB", w % 2), ("wr", "WR", 0)):
            stats.append({"player_id": pid, "player_display_name": pid.upper(), "game_id": gid, "season": 2026, "week": w,
                          "season_type": "REG", "team": "KC", "position": pos, "rushing_tds": td, "receiving_tds": 0})
    return pd.DataFrame(plays), pd.DataFrame(stats)


def test_red_zone_shares_and_live_read():
    pbp, stats = season()
    d = T.rolling(T.player_games(pbp, stats), shift=0)
    last = d.groupby("pid").tail(1).set_index("pid")
    assert last.loc["rb", "rz10_share"] == 1.0 and last.loc["wr", "rz10_share"] == 0.0
    assert 0.4 < last.loc["rb", "opp_share"] < 0.7 and last.loc["rb", "td_rate"] == 0.5
    params = {"coef": [-3.7, -0.5, 0.0, 0.05, 1.3, 0.8, 1.4, 0.0, 0.8], "prior_td": {"RB": 0.24, "WR": 0.18}}
    reads = T.Reads(pbp, stats, params)
    rb, wr = reads.read("rb", "RB", 27.0), reads.read("wr", "WR", 27.0)
    assert rb["p_model"] > wr["p_model"] and reads.read("nobody", "RB", 27.0) is None
    assert reads.read("rb", "RB", 30.0)["p_model"] > rb["p_model"]           # more expected points, more TDs
    assert "100% of KC's touches inside the 10" in T.note(rb, "KC", 27.0)


def test_blend_moves_halfway_in_log_odds():
    assert T.blend(0.5, 0.5) == 0.5
    b = T.blend(0.30, 0.40)
    assert 0.30 < b < 0.40 and abs(b - T.blend(0.30, 0.40, 1.0)) > 0.04


def _td(player, p, p_read, price):
    l = sgp.Leg(key=(player, "tds"), label=f"{player} anytime TD", player=player, team="KC", stat="tds", side="yes",
                point=0.5, price=price, hit=np.ones(10, bool), source="pinnacle")
    l.p = l.p_model = p
    l.p_read = p_read
    return l


def test_td_candidates_are_the_likeliest_scorers_and_the_read_carries_no_weight():
    fav = _td("Fav", 0.54, 0.52, -120)                       # value 0.99, read value 0.95
    role = _td("Role", 0.27, 0.33, 220)                      # value 0.86, read value 1.06: the read likes him
    cands = sgp_plus.td_candidates([fav, role], {"td_min_p": 0.20, "td_per_game": 3})
    assert [c["player"] for c in cands] == ["Fav", "Role"]    # Oct 25: by Pinnacle's chance, not the read's value
    assert T.blend(0.27, 0.40) == pytest.approx(0.27)         # READ_WEIGHT 0: the market's chance unchanged
    assert T.blend(0.27, 0.40, T.TRACK_WEIGHT) > 0.30         # the tracker still tests the half-weight read
    assert sgp_plus.td_chalk([fav, role], {"td_min_p": 0.20})["player"] == "Fav"


def test_tracker_records_grades_and_summarizes(tmp_path, monkeypatch):
    monkeypatch.setattr(td_reads, "PATH", tmp_path / "td_reads.csv")
    base = {"game_id": "2026_04_KC_X", "commence_time": "2026-09-27T17:00:00Z", "matchup": "X @ KC", "team": "KC",
            "position": "RB", "price": 120, "team_pts": 27.0, "rz10_share": 0.5, "rz20_share": 0.4, "opp_share": 0.3,
            "td_rate": 0.5}
    rows = [base | {"player": "A", "player_id": "a", "p_market": 0.40, "p_model": 0.55, "p_read": 0.47},
            base | {"player": "B", "player_id": "b", "p_market": 0.30, "p_model": 0.25, "p_read": 0.27},
            base | {"player": "C", "player_id": "c", "p_market": 0.20, "p_model": 0.20, "p_read": 0.20}]
    assert td_reads.record(rows, pd.Timestamp("2026-09-27T12:00:00Z")) == 3
    stats = pd.DataFrame({"game_id": "2026_04_KC_X", "player_id": ["a", "b"], "rushing_tds": [1, 0], "receiving_tds": [0, 0]})
    snaps = pd.DataFrame({"game_id": "2026_04_KC_X", "player_id": ["a", "b"], "offense_snaps": [40, 30]})
    assert td_reads.grade(stats, snaps, pd.Timestamp("2026-09-28T12:00:00Z")) == 3
    df = td_reads.load().set_index("player")
    assert df.loc["A", "scored"] == 1 and df.loc["B", "scored"] == 0 and df.loc["C", "status"] == "void"
    s = td_reads.summary()
    assert s["graded"] == 2 and s["liked"] == 1 and s["liked_scored"] == 1.0 and s["log_loss_read"] < s["log_loss_market"]
