"""The Notebook on an NFL game page (cards/notebook_nfl.py): story, changes and opponent patterns."""
import pandas as pd

from betlab.cards import notebook_nfl as NB

name = {"JAX": "Jaguars", "BAL": "Ravens", "CIN": "Bengals", "HOU": "Texans", "LV": "Raiders"}.get


def _row(gid, date, team, opp, pos, rec=0, yds=0, car=0, ryds=0):
    return {"game_id": gid, "date": pd.Timestamp(date), "team": team, "opponent_team": opp, "position": pos,
            "receptions": rec, "receiving_yards": yds, "carries": car, "rushing_yards": ryds}


def _stats():
    rows = []
    # Jacksonville's last three opponents: backs caught 4 for 34, 2 for 25, 11 for 71 (Conch's Nov 5 numbers)
    for gid, date, opp, (c, y) in (("g1", "2026-10-12", "CIN", (11, 71)), ("g2", "2026-10-19", "HOU", (2, 25)),
                                   ("g3", "2026-10-26", "LV", (4, 34))):
        rows.append(_row(gid, date, opp, "JAX", "RB", c, y, 20, 80))
        rows.append(_row(gid, date, opp, "JAX", "WR", 12, 130))
        rows.append(_row(gid, date, "JAX", opp, "RB", 3, 20, 25, 110))
        rows.append(_row(gid, date, "JAX", opp, "WR", 12, 130))
    # the rest of the league: backs catch 3 for 20 a game
    for i in range(10):
        rows.append(_row(f"x{i}", "2026-10-05", "AAA", "BBB", "RB", 3, 20, 24, 100))
        rows.append(_row(f"x{i}", "2026-10-05", "BBB", "AAA", "WR", 12, 140))
    return pd.DataFrame(rows)


def test_a_defense_pattern_reads_as_counts_oldest_first_against_the_league():
    a = NB.allowed(_stats(), "JAX", pd.Timestamp("2026-11-05"))
    assert a[("RB", "receiving")]["games"] == [(11, 71), (2, 25), (4, 34)]
    p = NB.pattern("Jaguars'", "Ravens", a)
    assert p["group"] == "RB" and p["kind"] == "receiving"
    assert p["text"].startswith("Jaguars' defense, last 3 games, running backs' catches: 11 for 71, 2 for 25, 4 for 34")
    assert "league" in p["text"]


def test_no_pattern_when_nothing_runs_well_over_the_league_or_games_are_missing():
    s = _stats()
    s.loc[(s["opponent_team"] == "JAX") & (s["position"] == "RB"), ["receptions", "receiving_yards"]] = [3, 20]
    assert NB.pattern("Jaguars'", "Ravens", NB.allowed(s, "JAX", pd.Timestamp("2026-11-05"))) is None
    assert NB.allowed(s, "JAX", pd.Timestamp("2026-10-01")) == {}          # nothing before the date


def test_the_story_names_the_favorite_and_who_throws_more_and_changes_use_the_previews_words():
    entry = {"home": "BAL", "away": "JAX", "market": {"spread_home": -9.5, "total": 40.0},
             "script_read": {"BAL": {"dropbacks_vs_usual": 0.065}, "JAX": {"dropbacks_vs_usual": -0.029}},
             "qbs": {"BAL": {"change": True, "text": "Joe Fagnano starts for the Ravens in place of Lamar Jackson (out)."},
                     "JAX": {"change": False, "text": ""}},
             "injury_effects": {"JAX": "Without Devin Hamilton the Jaguars' run defense slips."}}
    s = NB.story(entry, name)
    assert s.startswith("The market has the Jaguars by 9.5 in a 40-point game.")
    assert "The Ravens should throw more than usual, about 6% more dropbacks." in s and "Jaguars should" not in s
    assert NB.changes(entry) == ["Joe Fagnano starts for the Ravens in place of Lamar Jackson (out).",
                                 "Without Devin Hamilton the Jaguars' run defense slips."]
    nb = NB.build(entry, _stats(), pd.Timestamp("2026-11-05"), name)
    assert [p["defense"] for p in nb["patterns"]] == ["Jaguars'"]          # Baltimore has no games in the stats
    assert NB.build(entry, None, pd.Timestamp("2026-11-05"), name)["patterns"] == []


def test_one_blowout_is_not_a_pattern():
    s = _stats()
    rb = (s["opponent_team"] == "JAX") & (s["position"] == "RB")
    s.loc[rb, "receiving_yards"] = [143, 10, 12]     # one big game; the average still runs far over the league's 20
    assert NB.pattern("Jaguars'", "Ravens", NB.allowed(s, "JAX", pd.Timestamp("2026-11-05"))) is None
