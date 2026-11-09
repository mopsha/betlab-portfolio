"""The morning NBA listing (Oct 12): tonight's games on the app before any is priced."""

import json

import pandas as pd

from betlab import config
from betlab.reports import nba as R


def _snap():
    rows = []
    for book, sp, tot in (("fanduel", -4.5, 221.5), ("pinnacle", -5.0, 222.5), ("draftkings", -4.5, 221.5)):
        for market, outcome, point in (("spreads", "Detroit Pistons", sp), ("spreads", "Boston Celtics", -sp),
                                       ("totals", "Over", tot), ("totals", "Under", tot)):
            rows.append({"event_id": "ev1", "commence_time": "2026-10-20T23:30:00Z", "home_team": "Detroit Pistons",
                         "away_team": "Boston Celtics", "bookmaker": book, "market": market, "outcome": outcome, "point": point})
    rows.append({"event_id": "ev2", "commence_time": "2026-10-23T02:00:00Z", "home_team": "Los Angeles Clippers",
                 "away_team": "Golden State Warriors", "bookmaker": "fanduel", "market": "h2h", "outcome": "Los Angeles Clippers", "point": None})
    return pd.DataFrame(rows)


ESPN = [{"home_name": "Detroit Pistons", "home": "DET", "away_name": "Boston Celtics", "away": "BOS", "national_tv": ["ESPN"]}]


def test_tonights_games_are_listed_with_the_line_and_tv(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path)
    asof = pd.Timestamp("2026-10-20T13:55:00Z")
    games = R.schedule_games(_snap(), ESPN, asof)
    assert [g["event_id"] for g in games] == ["ev1"]                 # ev2 tips more than 36 hours out
    g = games[0]
    assert (g["home"], g["away"], g["national_tv"], g["lines"], g["priced"]) == ("DET", "BOS", ["ESPN"], [], False)
    assert g["spread_home"] == 4.5 and g["total"] == 221.5           # median across books; home favored by 4.5
    assert R.schedule(_snap(), ESPN, asof) == 1
    assert R.schedule(_snap(), ESPN, asof) == 0                      # listed once


def test_a_priced_game_is_never_replaced_by_its_listing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path)
    priced = {"event_id": "ev1", "matchup": "Boston Celtics @ Detroit Pistons", "tipoff": "2026-10-20 23:30:00+00:00",
              "lines": [{"player": "Jayson Tatum", "stat": "points", "line": 27.5}]}
    (tmp_path / "nba.json").write_text(json.dumps({"games": [priced]}), encoding="utf-8")
    assert R.schedule(_snap(), ESPN, pd.Timestamp("2026-10-20T22:45:00Z")) == 0
    assert json.loads((tmp_path / "nba.json").read_text(encoding="utf-8"))["games"][0]["lines"]


def test_espn_short_names_match_by_nickname():
    assert R._nick("Los Angeles Clippers") == R._nick("LA Clippers") == "clippers"


def test_reads_are_logged_once_and_graded_against_the_close_and_the_result(tmp_path, monkeypatch):
    from betlab import nba_reads as NR

    monkeypatch.setattr(NR, "PATH", tmp_path / "nba_reads.csv")
    asof = pd.Timestamp("2026-10-20T13:55:00Z")
    e = {"event_id": "ev1", "home": "DET", "away": "BOS", "matchup": "Boston Celtics @ Detroit Pistons",
         "tipoff": "2026-10-20T23:30:00+00:00", "spread_home": -3.5, "total": 221.5,
         "model": {"margin": 2.0, "total": 218.0, "early": True}}
    rows = NR.rows([e], asof)
    assert [(r["kind"], r["gap"], r["side"]) for r in rows] == [("spread", 5.5, "DET"), ("total", -3.5, "Under")]
    assert NR.record(rows, asof) == 2 and NR.record(rows, asof) == 0
    close = _snap().assign(event_id="ev1", snapshot_ts="2026-10-20T23:10:00Z")
    close.loc[close["outcome"] == "Detroit Pistons", "point"] = -2.5           # the line moved toward Detroit (now favored)
    close.loc[close["outcome"] == "Boston Celtics", "point"] = 2.5
    close.loc[close["market"] == "totals", "point"] = 219.5
    n = NR.grade(finals={("Detroit Pistons", "Boston Celtics", "2026-10-20"): (108.0, 110.0)}, snaps=[close],
                 now=pd.Timestamp("2026-10-21T04:00:00Z"))
    df = NR.load().set_index("kind")
    assert n == 2
    assert df.loc["spread", "result"] == "won" and df.loc["spread", "moved_pts"] == 6.0   # BOS by 2 < 3.5; -3.5 -> +2.5
    assert df.loc["total", "result"] == "won" and df.loc["total", "moved_pts"] == 2.0     # 218 under 221.5; 221.5 -> 219.5
    s = NR.summary()
    assert s["spread"]["n"] == 1 and s["spread"]["won"] == 1.0


def test_regulars_out_tonight_are_listed_and_counted():
    from betlab import nba_reads as NR

    inj = pd.DataFrame([{"athlete_id": 1, "athlete_display_name": "Star Guard", "team": "LA Clippers", "sits": True},
                        {"athlete_id": 2, "athlete_display_name": "Bench Big", "team": "LA Clippers", "sits": True},
                        {"athlete_id": 3, "athlete_display_name": "Wing", "team": "Golden State Warriors", "sits": False}])
    pb = pd.DataFrame({"athlete_id": [1] * 5 + [2] * 5 + [3] * 5, "minutes": [34] * 5 + [12] * 5 + [30] * 5,
                       "game_date": list(pd.date_range("2026-03-01", periods=5)) * 3})
    e = [{"event_id": "e2", "matchup": "Golden State Warriors @ Los Angeles Clippers"}]
    o = NR.absences(e, pd.Timestamp("2026-10-20T14:00:00Z"), injuries=inj, player_box=pb)["e2"]
    assert o["home"] == [{"name": "Star Guard", "minutes": 34.0}] and o["away"] == [] and o["key_out"] == 1


def test_absences_sort_mixed_date_types():
    """Last season's sportsdataverse rows carry dates, this season's ESPN fill strings (Oct 24: the sort failed)."""
    import datetime as dt

    from betlab import nba_reads as NR

    inj = pd.DataFrame([{"athlete_id": 1, "athlete_display_name": "Star Guard", "team": "LA Clippers", "sits": True}])
    pb = pd.DataFrame({"athlete_id": [1, 1], "minutes": [30, 36],
                       "game_date": [dt.date(2026, 3, 1), "2026-10-22"]})
    e = [{"event_id": "e2", "matchup": "Golden State Warriors @ Los Angeles Clippers"}]
    o = NR.absences(e, pd.Timestamp("2026-10-24T14:00:00Z"), injuries=inj, player_box=pb)["e2"]
    assert o["home"] == [{"name": "Star Guard", "minutes": 33.0}]
