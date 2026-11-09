"""Non-QB absences: who counts as a regular, who's missing, and what it moves."""

import numpy as np
import pandas as pd
import pytest

from betlab import injuries_nfl as I


def season(n_games=5, drop=None):
    """One team's snaps and stats over n games; drop = {game_index: [names who sat]}."""
    drop = drop or {}
    snaps, stats = [], []
    players = [("Lee Tackle", "T", 1.0, 0.0), ("Max Guard", "G", 0.95, 0.0), ("Sam Backup", "G", 0.1, 0.0),
               ("Dee Corner", "CB", 0.0, 0.9), ("Ray Rusher", "DE", 0.0, 0.7), ("Wes Wideout", "WR", 0.9, 0.0),
               ("Tim End", "TE", 0.7, 0.0), ("Bo Back", "RB", 0.6, 0.0)]
    for g in range(n_games):
        gid = f"2025_{g + 1:02d}_AAA_BBB"
        date = pd.Timestamp("2025-09-07") + pd.Timedelta(weeks=g)
        for name, pos, off, dfn in players:
            if name in drop.get(g, []):
                continue
            snaps.append({"game_id": gid, "season": 2025, "week": g + 1, "player": name, "position": pos, "team": "AAA",
                          "offense_pct": off, "defense_pct": dfn, "date": date})
            stats.append({"game_id": gid, "season": 2025, "week": g + 1, "player_display_name": name, "position": pos,
                          "team": "AAA", "date": date, "targets": {"WR": 9, "TE": 3, "RB": 2}.get(pos, 0),
                          "carries": 15 if pos == "RB" else 0, "def_sacks": 1.0 if pos == "DE" else 0.0,
                          "def_qb_hits": 1.0 if pos == "DE" else 0.0})
    return pd.DataFrame(snaps), pd.DataFrame(stats)


def test_names_match_on_initial_and_last_name():
    assert I.key("Matthew Judon") == I.key("Matt Judon") == "m judon"
    assert I.key("Michael Penix Jr.") == "m penix"


def test_backtest_absences_count_regulars_who_sat_from_game_four():
    sn, st = season(5, drop={4: ["Lee Tackle", "Wes Wideout", "Ray Rusher", "Sam Backup"]})
    ab = I.absences(sn.drop(columns="date"), st.drop(columns="date")).set_index("game_id")
    first3 = ab.iloc[:3]
    assert first3["ol_out"].isna().all()                      # no regulars before game 4
    last = ab.loc["2025_05_AAA_BBB"]
    assert last["ol_out"] == 1                                # the backup guard doesn't count
    assert last["top_target_out"] == 1 and last["rusher_out"] == 1 and last["back_out"] == 0
    assert ab.loc["2025_04_AAA_BBB", "ol_out"] == 0


def test_live_uses_the_report_and_the_roster():
    sn, st = season(3)
    before = pd.Timestamp("2025-10-01")
    roster = pd.DataFrame({"full_name": ["Lee Tackle", "Max Guard", "Dee Corner", "Ray Rusher", "Tim End", "Bo Back"],
                           "status": ["ACT", "RES", "INA", "ACT", "ACT", "ACT"]})
    # Wes Wideout isn't on the roster any more (traded); Max Guard is on reserve; Dee Corner is
    # only inactive for the last game (not known this morning); Lee Tackle is Out on the report.
    c = I.live(sn, st, "AAA", before, {"Lee Tackle"}, roster)
    assert c["ol_out"] == 2 and c["top_target_out"] == 1 and c["back_out"] == 0 and c["rusher_out"] == 0
    assert c["who"]["ol"] == ["Lee Tackle", "Max Guard"]
    assert I.live(sn[sn["week"] == 1], st[st["week"] == 1], "AAA", before, set()) == {}     # one game: too early


def test_adjustments_and_sentence():
    counts = {"AAA": {"ol_out": 1, "top_target_out": 1.0, "rusher_out": 0.0, "back_out": 0,
                      "who": {"ol": ["Lee Tackle"], "top_target": ["Wes Wideout"], "rusher": [], "back": []}},
              "BBB": {"ol_out": 0, "top_target_out": 0.0, "rusher_out": 1.0, "back_out": 2,
                      "who": {"ol": [], "top_target": [], "rusher": ["Ray Rusher"], "back": ["X", "Y"]}}}
    a = I.adjustments(counts, "AAA", "BBB")
    e = I.EFFECTS
    assert a["pass_epa"] == pytest.approx(e["own"]["ol_out"]["pass_epa"] + e["own"]["top_target_out"]["pass_epa"]
                                          + 2 * e["opp"]["back_out"]["pass_epa"])
    assert a["pressure"] == pytest.approx(e["opp"]["rusher_out"]["pressure"] + 2 * e["opp"]["back_out"]["pressure"])
    assert I.adjustments(counts, "BBB", "AAA") == {}          # AAA's missing players are all on offense
    text = I.sentence(counts, "AAA", "BBB", lambda t: {"AAA": "Aces", "BBB": "Bees"}[t])
    assert "Wes Wideout (top target)" in text and "Lee Tackle (line starter)" in text
    assert "Ray Rusher (top pass rusher)" in text and "helps Aces' passing game" in text
    assert I.sentence({}, "AAA", "BBB", str) == ""
