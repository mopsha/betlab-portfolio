"""Graders must survive the ledgers' mixed rows (Oct 13-14: two daily runs graded no NHL props or soccer lines)."""
import pandas as pd

from betlab import tracking_nhl_props, tracking_soccer
from betlab.sources import soccer


def test_nhl_props_grade_reads_mixed_start_formats(monkeypatch):
    # nhl_prop_lines.csv holds both "...T02:00Z" and "...T23:10:00Z"; pandas inferred the first and failed on the second
    df = pd.DataFrame({"commence_time": ["2026-10-01T02:00Z", "2026-10-10T23:10:00Z"],
                       "status": ["graded", "graded"], "game_ref": ["1", "2"]})
    monkeypatch.setattr(tracking_nhl_props, "load", lambda: df)
    assert tracking_nhl_props.grade(now=pd.Timestamp("2026-10-14T14:00Z")) == 0


def test_soccer_grade_excludes_rows_that_are_not_three_way(monkeypatch):
    base = {"league": "mls", "event_id": "e1", "home": "A", "away": "B", "commence_time": "2026-10-12T23:00:00Z",
            "status": "open", "hg": None, "ag": None, "won": None, "p_close": None, "close_source": None,
            "graded_at": None}
    df = pd.DataFrame([base | {"side": "Yes"}, base | {"side": "A"}])
    saved = {}
    monkeypatch.setattr(tracking_soccer, "load", lambda: df)
    monkeypatch.setattr(tracking_soccer, "save", lambda d: saved.setdefault("df", d))
    lookup = lambda *a: {"hg": 2, "ag": 1, "close": None, "close_source": None}
    assert tracking_soccer.grade(now=pd.Timestamp("2026-10-14T14:00Z"), lookup=lookup) == 2
    assert saved["df"]["status"].tolist() == ["excluded", "graded"]
    assert pd.isna(saved["df"]["won"].iloc[0])


def test_nhl_props_grade_reports_games_whose_box_failed(monkeypatch, capsys):
    monkeypatch.setattr(tracking_nhl_props.time, "sleep", lambda s: None)
    df = pd.DataFrame({"commence_time": ["2026-10-14T00:10:00Z"], "status": ["open"], "game_ref": ["2026020098"],
                       "stat": ["shots"], "player": ["A B"], "actual": [None], "graded_at": [None]})
    monkeypatch.setattr(tracking_nhl_props, "load", lambda: df)
    monkeypatch.setattr(tracking_nhl_props, "save", lambda d: None)

    def boom(gid):
        raise ConnectionError("429")
    assert tracking_nhl_props.grade(skater_box=boom, goalie_box=boom, now=pd.Timestamp("2026-10-14T14:00Z")) == 0
    assert "unavailable for 1 game(s): 2026020098 ConnectionError: 429" in capsys.readouterr().out


FD = pd.DataFrame({"date": pd.to_datetime(["2026-10-10", "2026-10-10", "2026-10-01"]),
                   "home": ["Paris SG", "Lorient", "New York Red Bulls"], "away": ["Le Mans", "Paris FC", "St. Louis City"]})


def test_psg_finds_paris_sg_not_paris_fc():
    m = soccer.find_match(FD, "Paris Saint Germain", "Le Mans FC", pd.Timestamp("2026-10-10T18:45Z"))
    assert m is not None and m["home"] == "Paris SG"


def test_a_match_moved_days_later_is_postponed(monkeypatch):
    monkeypatch.setattr(soccer, "load", lambda league, seasons: FD)
    kick = pd.Timestamp("2026-09-26T23:30Z")
    assert soccer.find_match(FD, "New York Red Bulls", "St. Louis City SC", kick) is None
    assert soccer.postponed("mls", "New York Red Bulls", "St. Louis City SC", kick) == pd.Timestamp("2026-10-01")
    assert soccer.postponed("mls", "Paris Saint Germain", "Le Mans FC", pd.Timestamp("2026-10-10T18:45Z")) is None
