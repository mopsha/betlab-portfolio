"""Nov 9 review of grading: bets that could never settle, and graders whose failure stopped the rest or said nothing."""

import json
import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from betlab import fun_ledger as FL
from betlab import grading, watchdog
from betlab.sources import nba, nflverse


# -------------------------------------------------------------------------- one grader can't stop the rest


def test_fun_grade_keeps_every_other_sports_settles_when_nflverse_is_down(monkeypatch, capsys):
    """Nov 9: a 504 from nflverse inside the NFL slips' grader threw away the NBA, NHL, soccer and college settles
    already made (save came after it) and stopped the whole grade step."""
    df = pd.DataFrame([{**{c: None for c in FL.COLUMNS}, "sgp_id": "n1", "sport": "nba", "status": "open", "game_id": "nba|X"},
                       {**{c: None for c in FL.COLUMNS}, "sgp_id": "f1", "sport": "nfl", "status": "open",
                        "game_id": "2026_09_CIN_ATL"}])
    saved = {}
    monkeypatch.setattr(FL, "load", lambda: df.copy())
    monkeypatch.setattr(FL, "save", lambda d: saved.setdefault("df", d))

    def nba_ok(d, todo):
        d.loc[todo.index, "status"] = "won"
        return len(todo)

    def nfl_down(*a, **kw):
        raise ConnectionError("too many 504 error responses")

    monkeypatch.setattr(FL, "GRADERS", {"nba": nba_ok, "nfl": nfl_down})
    monkeypatch.setattr(FL, "_grade_nfl", nfl_down)
    assert FL.grade() == 1
    assert saved["df"].set_index("sgp_id")["status"].to_dict() == {"n1": "won", "f1": "open"}
    out = capsys.readouterr().out
    assert "fun grading nfl: not graded (ConnectionError" in out
    from betlab import cli
    assert any(k in out for k in cli.GRADE_PROBLEM)          # so the grade step warns and alerts the same day


def test_grade_everything_goes_on_past_a_fun_ledger_or_college_reads_failure(monkeypatch, capsys):
    from betlab import (cfb_reads, cli, golive, grading as G, nba_reads, ncaab_reads, td_reads, tracking, tracking_nba,
                        tracking_nhl, tracking_nhl_props, tracking_soccer, tracking_soccer_props, soccer_goal_reads,
                        fun_offers, cfb_dogs)
    from betlab.reports import review

    def down(*a, **kw):
        raise ConnectionError("504")

    for mod in (tracking, tracking_nba, tracking_nhl, tracking_nhl_props, tracking_soccer, tracking_soccer_props,
                soccer_goal_reads, td_reads, nba_reads, ncaab_reads, fun_offers, cfb_dogs, cfb_reads):
        monkeypatch.setattr(mod, "grade", down)
    monkeypatch.setattr(G, "grade_all", lambda *a: 0)
    monkeypatch.setattr(FL, "grade", down)
    monkeypatch.setattr(FL, "write_results", down)
    wrote = {}
    monkeypatch.setattr(review, "build", lambda: {"overall": {"record": "0-0", "units": 0, "avg_clv": None}})
    monkeypatch.setattr(review, "write", lambda r: wrote.setdefault("review", r))
    monkeypatch.setattr(golive, "write", lambda: wrote.setdefault("golive", {"markets": []}))
    cli._grade_everything()
    out = capsys.readouterr().out
    assert "fun parlays not graded (ConnectionError" in out and "college early reads not graded" in out
    assert set(wrote) == {"review", "golive"}                 # the review and scorecard still write


# -------------------------------------------------------------------------- the Clippers


def test_espns_la_clippers_reads_as_our_los_angeles_clippers(monkeypatch):
    """ESPN's schedule and box say "LA Clippers"; our matchups, game ids and slips say "Los Angeles Clippers". No
    Clippers line, NBA read or Clippers-home game id graded for three weeks."""
    sch = pd.DataFrame({"game_id": [1], "season": [2027], "start_date": ["2026-10-23T02:30Z"], "home_abbreviation": ["LAC"],
                        "home_display_name": ["LA Clippers"], "away_abbreviation": ["SAC"],
                        "away_display_name": ["Sacramento Kings"], "home_score": [110.0], "away_score": [100.0],
                        "status_type_completed": [True]})
    monkeypatch.setattr(nba, "_get", lambda kind, season, max_age_hours=None: sch)
    got = nba.load_schedules([2026])
    assert got["home_display_name"].tolist() == ["Los Angeles Clippers"]
    lean = pd.DataFrame([{"matchup": "Sacramento Kings @ Los Angeles Clippers", "commence_time": "2026-10-23T02:30:00Z",
                          "side": "Los Angeles Clippers", "market": "h2h", "point": None, "price": -150.0,
                          "units_flat": 1.0, "status": "open"}])
    monkeypatch.setattr(grading, "nba_close", lambda r, snaps: None)
    out = grading._grade_nba_lines(lean.copy(), lean, got, None)
    assert out.at[0, "status"] == "won"
    box = nba.our_names(pd.DataFrame({"team_display_name": ["LA Clippers", "Boston Celtics"],
                                      "opponent_team_display_name": ["Boston Celtics", "LA Clippers"]}))
    assert box["team_display_name"].tolist() == ["Los Angeles Clippers", "Boston Celtics"]
    assert box["opponent_team_display_name"].tolist() == ["Boston Celtics", "Los Angeles Clippers"]


# -------------------------------------------------------------------------- NBA: a DNP voids, a missing box waits


def _box():
    return pd.DataFrame({
        "game_id": [1, 1, 2, 2],
        "athlete_id": [7, 8, 7, 9],
        "athlete_display_name": ["Kyrie Irving", "Klay Thompson", "Kyrie Irving", "Victor Wembanyama"],
        "team_display_name": ["Dallas Mavericks", "Dallas Mavericks", "Dallas Mavericks", "San Antonio Spurs"],
        "team_abbreviation": ["DAL", "DAL", "DAL", "SA"],
        "game_date": ["2026-10-23", "2026-10-23", "2026-10-24", "2026-10-24"],
        "minutes": [34.0, 30.0, 0.0, 33.0], "points": [25, 14, 0, 30], "rebounds": [4, 3, 0, 12], "assists": [6, 2, 0, 3],
        "three_point_field_goals_made": [3, 4, 0, 2]}).drop(index=2).reset_index(drop=True)   # Oct 24: Kyrie not in it


def test_grade_nba_voids_a_prop_on_a_player_missing_from_his_games_box():
    """Nov 9: Kyrie Irving's under 2.5 threes (Oct 24) sat open 15 days: the box files leave out a player who didn't
    play. Missing from his game's box (both teams in, his team known from his other games): void. A name the season
    never matched, or a game whose box isn't in, stays open."""
    tip = "2026-10-25T00:10:00Z"
    base = {"league": "nba", "event_id": "e", "game_ref": None, "commence_time": tip, "market": "player_threes",
            "side": "Under", "point": 2.5, "price": -142.0, "units_flat": 1.0, "kind": "prop", "status": "open",
            "created_at": "2026-10-24T21:31:04+00:00"}
    box = _box()
    box = pd.concat([box, box.iloc[[2]].assign(athlete_id=10, athlete_display_name="Bench Guy",
                                               team_display_name="Dallas Mavericks", team_abbreviation="DAL", minutes=5.0)])
    picks = pd.DataFrame([base | {"pick_id": "kyrie", "player": "Kyrie Irving", "matchup": "San Antonio Spurs @ Dallas Mavericks"},
                          base | {"pick_id": "nobody", "player": "Who Dat", "matchup": "San Antonio Spurs @ Dallas Mavericks"},
                          base | {"pick_id": "nobox", "player": "Kyrie Irving", "matchup": "Dallas Mavericks @ Boston Celtics"}])
    out = grading.grade_nba(picks, box, now=pd.Timestamp("2026-10-26T06:00:00Z"), snaps=[]).set_index("pick_id")
    assert out.loc["kyrie", "status"] == "void"
    assert out.loc["nobody", "status"] == "open" and out.loc["nobox", "status"] == "open"


def test_fun_nba_leg_waits_for_a_missing_box_and_voids_a_dnp():
    """A box that didn't come (an ESPN hiccup) voided every player leg on it for good, and under Bet Protect+ a lost slip
    read won. Now: no box, the leg waits; a player missing from a box his team is in voids; a name nobody knows waits."""
    sch = pd.DataFrame({"game_id": [2, 3], "start_date": ["2026-10-25T00:10Z", "2026-10-25T00:10Z"],
                        "home_abbreviation": ["DAL", "BOS"], "away_abbreviation": ["SA", "NY"],
                        "home_display_name": ["Dallas Mavericks", "Boston Celtics"],
                        "away_display_name": ["San Antonio Spurs", "New York Knicks"],
                        "home_score": [100.0, 99.0], "away_score": [90.0, 98.0], "status_type_completed": [True, True]})
    ref, other = "nba|DAL|SA|2026-10-25T00:10:00Z", "nba|BOS|NY|2026-10-25T00:10:00Z"
    res = FL.nba_leg_results(["Kyrie Irving over 2.5 threes", "Victor Wembanyama 25+ points", "Who Dat 10+ points",
                              "Jalen Brunson 20+ points"], [ref, ref, ref, other], _box(), sch)
    assert [x["result"] for x in res] == ["void", "won", "open", "open"]


# -------------------------------------------------------------------------- slips' game refs


def test_a_ref_on_the_odds_apis_hex_id_is_found_again_for_college_and_nhl(monkeypatch):
    """Nov 9: the slip reader built "ncaaf:<Odds API id>" refs, which no grader can read (Georgia + Miami, open two days
    after both finals). Such a ref counts as none and is found from the matchup; college basketball and the NHL too."""
    from betlab.sources import cbbd, cfbd, nhl

    assert FL.unusable_ref("ncaaf:0842fcd69fdf5061f6751f876ead09f2") and not FL.unusable_ref("ncaaf:401869927")
    monkeypatch.setattr(cfbd, "games", lambda: pd.DataFrame({"game_id": ["401869927"], "home_team": ["Georgia"],
                                                             "away_team": ["Florida"],
                                                             "kickoff": [pd.Timestamp("2026-11-07 15:30", tz="America/New_York")]}))
    monkeypatch.setattr(cfbd, "team_names", lambda: {"Georgia Bulldogs": "Georgia", "Florida Gators": "Florida"})
    monkeypatch.setattr(cbbd, "games", lambda: pd.DataFrame({"game_id": [7001], "home_team": ["Duke"], "away_team": ["Army"],
                                                             "start": [pd.Timestamp("2026-11-07 23:00", tz="UTC")]}))
    monkeypatch.setattr(cbbd, "team_names", lambda feed_names=None: {"Duke Blue Devils": "Duke", "Army Black Knights": "Army"})
    monkeypatch.setattr(nhl, "load_team_games", lambda seasons, **kw: pd.DataFrame({
        "game_id": [2026020210, 2026020210], "date": pd.to_datetime(["2026-11-07"] * 2), "team": ["NYR", "BOS"],
        "opp": ["BOS", "NYR"], "home": [1, 0]}))
    when, found = "2026-11-07T17:00:00Z", {}
    assert FL._find_ref("ncaaf", "Florida Gators @ Georgia Bulldogs", "ncaaf:0842fcd69fdf5061f6751f876ead09f2", when,
                        found) == "ncaaf:401869927"
    assert FL._find_ref("ncaab", "Army Black Knights @ Duke Blue Devils", "ncaab:" + "a" * 32, when, found) == "ncaab:7001"
    assert FL._find_ref("nhl", "BOS @ NYR", None, when, found) == "nhl:2026020210"
    assert FL._find_ref("nhl", "Boston Bruins @ New York Rangers", "nhl:" + "b" * 32, when, found) == "nhl:2026020210"
    assert FL._find_ref("nhl", "New York Rangers @ Boston Bruins", None, when, found) is None       # the other way round


def test_sync_repairs_a_hex_ref_and_reads_a_ref_less_games_sport(tmp_path, monkeypatch):
    from betlab.sources import cfbd

    monkeypatch.setattr(FL, "PATH", tmp_path / "fun.csv")
    monkeypatch.setattr(nflverse, "load_games", lambda: pd.DataFrame(columns=["game_id", "home_team", "away_team", "date"]))
    monkeypatch.setattr(nflverse, "team_abbr_by_name", lambda: {})
    monkeypatch.setattr(cfbd, "games", lambda: pd.DataFrame({"game_id": ["401869927", "401869930"],
                                                             "home_team": ["Georgia", "Miami"], "away_team": ["Florida", "Duke"],
                                                             "kickoff": [pd.Timestamp("2026-11-07 15:30", tz="America/New_York")] * 2}))
    monkeypatch.setattr(cfbd, "team_names", lambda: {"Georgia Bulldogs": "Georgia", "Florida Gators": "Florida",
                                                     "Miami Hurricanes": "Miami", "Duke Blue Devils": "Duke"})
    old = {"sgp_id": "custom-fd-snap-c850c962", "legs": ["Georgia Bulldogs ML", "Miami Hurricanes ML"], "price": 410,
           "quoted_at": "2026-11-08T00:21:00Z",
           "games": [{"matchup": "Florida Gators @ Georgia Bulldogs", "game_ref": "ncaaf:0842fcd69fdf5061f6751f876ead09f2",
                      "legs": ["Georgia Bulldogs ML"]},
                     {"matchup": "Duke Blue Devils @ Miami Hurricanes", "game_ref": "ncaaf:4aac00e6cc06b8905659f911419540d2",
                      "legs": ["Miami Hurricanes ML"]}]}
    new = {"sgp_id": "custom-fd-snap-new", "legs": ["Georgia Bulldogs ML"], "price": -300, "quoted_at": "2026-11-07T12:00:00Z",
           "games": [{"matchup": "Florida Gators @ Georgia Bulldogs", "sport": "ncaaf", "legs": ["Georgia Bulldogs ML"]}]}
    FL.sync([old, new], [])
    df = FL.load().set_index("sgp_id")
    assert json.loads(df.loc["custom-fd-snap-c850c962", "leg_games"]) == ["ncaaf:401869927", "ncaaf:401869930"]
    assert df.loc["custom-fd-snap-new", "sport"] == "ncaaf"
    assert json.loads(df.loc["custom-fd-snap-new", "leg_games"]) == ["ncaaf:401869927"]


# -------------------------------------------------------------------------- legs only ESPN reads


def test_every_stat_the_trackers_read_has_a_grader():
    """Nov 9: "Trevor Lawrence 2+ passing TDs" sat "unknown" (the NFL grader doesn't read it and ESPN_ONLY left it
    out): an all-win slip with it stays open for good. Every stat word the trackers know needs a grader."""
    from betlab import live_legs as L

    read = set(FL.STAT_OF_LABEL) | set(FL.NBA_STAT) | set(FL.NHL_BOX) | set(FL.SOCCER_KEY) | FL.ESPN_ONLY
    assert [w for w in L.STAT_WORDS if w not in read and not re.fullmatch(r"[1-4][qhp] .+", w)] == []
    assert L.parse_leg("Trevor Lawrence 2+ passing TDs")["stat"] in FL.ESPN_ONLY


def test_a_passing_td_leg_settles_from_espn(monkeypatch):
    from betlab import live_legs as L

    r = pd.Series({"leg_games": json.dumps(["2026_09_JAX_HOU"]), "game_id": "2026_09_JAX_HOU", "matchup": None,
                   "sport": "nfl", "quoted_at": "2026-11-08T17:00:00Z"})
    game = {"state": "post", "id": "1"}
    monkeypatch.setattr(L, "scoreboard", lambda *a, **kw: [game])
    monkeypatch.setattr(L, "find_game", lambda games, matchup: game)
    monkeypatch.setattr(L, "boxscore", lambda g, league, get: {})
    monkeypatch.setattr(L, "judge", lambda label, g, box: {"status": "won", "current": 3.0})
    got = FL.espn_unknown(r, [{"leg": "Trevor Lawrence 2+ passing TDs", "result": "unknown", "value": None}],
                          get=lambda *a: None)
    assert got[0]["result"] == "won" and got[0]["value"] == 3.0


# -------------------------------------------------------------------------- a leg off a screenshot's slip


def test_a_real_slip_with_a_leg_off_and_no_leg_price_waits_for_what_the_book_paid(capsys):
    """A screenshot slip has no leg_p: one leg off and the rest won voided it all (0 profit) while the book paid the
    shorter parlay. A marked slip now waits with a "not graded" warning until its cash-out says what it paid; an
    unmarked one (learning only) still voids."""
    row = {**{c: None for c in FL.COLUMNS}, "sgp_id": "custom-fd-snap-x", "status": "open", "price": 500.0,
           "marked": True, "stake": 1.0, "bonus": False}
    legs = [{"leg": "A over 1.5 receptions", "result": "won", "value": 3.0},
            {"leg": "Over 45 total points", "result": "push", "value": 45.0}]
    df = pd.DataFrame([row])
    assert not FL._finish(df, 0, df.iloc[0], legs, "t") and df.at[0, "status"] == "open"
    assert "custom-fd-snap-x not graded" in capsys.readouterr().out
    df = pd.DataFrame([row | {"cashout": 3.2}])
    assert FL._finish(df, 0, df.iloc[0], legs, "t")
    assert df.at[0, "status"] == "won" and df.at[0, "profit"] == 2.2 and pd.isna(df.at[0, "profit_1u"])
    df = pd.DataFrame([row | {"marked": False}])
    assert FL._finish(df, 0, df.iloc[0], legs, "t") and df.at[0, "status"] == "void"
    df = pd.DataFrame([row])
    lost = legs + [{"leg": "B over 0.5 receptions", "result": "lost", "value": 0.0}]
    assert FL._finish(df, 0, df.iloc[0], lost, "t") and df.at[0, "status"] == "lost"   # a lost leg still settles it


# -------------------------------------------------------------------------- Novig's own bets


def test_synced_novig_bets_settle_as_novig_did_and_are_never_graded_here(tmp_path, monkeypatch):
    monkeypatch.setattr(FL, "PATH", tmp_path / "fun.csv")
    monkeypatch.setattr(nflverse, "load_games", lambda: pd.DataFrame(columns=["game_id", "home_team", "away_team", "date"]))
    monkeypatch.setattr(nflverse, "team_abbr_by_name", lambda: {})
    q = {"sgp_id": "novig-01a1714c", "legs": ["Tulane -10.5"], "price": 111, "matchup": "Tulane @ Charlotte",
         "quoted_at": "2026-10-30T23:00:00Z", "status": "lost", "profit_1u": None, "graded_at": "2026-10-31T03:15:09+00:00"}
    w = q | {"sgp_id": "novig-01a17f52", "legs": ["Jordan Kyrou 1+ goals"], "price": 270, "status": "won"}
    o = q | {"sgp_id": "novig-open", "status": None}
    FL.sync([q, w, o], [{"sgp_id": "novig-01a1714c", "mode": "real", "stake": 1.0, "price": 111},
                        {"sgp_id": "novig-01a17f52", "mode": "real", "stake": 1.0, "price": 270}])
    df = FL.load().set_index("sgp_id")
    assert df.loc["novig-01a1714c", "status"] == "lost" and df.loc["novig-01a1714c", "profit"] == -1.0
    assert df.loc["novig-01a17f52", "status"] == "won" and df.loc["novig-01a17f52", "profit_1u"] == 2.7
    assert df.loc["novig-open", "status"] == "open"
    df.loc["novig-open", "game_id"] = "2026_09_CIN_ATL"
    FL.save(df.reset_index())
    assert FL.grade() == 0                                     # never graded by the ledger itself


# -------------------------------------------------------------------------- the watchdog's stuck bets


def test_watchdog_counts_bets_still_open_long_after_their_last_game():
    now = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    bets = [
        {"bet_id": "a", "label": "$5 cash, 50% profit boost", "placed_at": now - timedelta(days=3),
         "games": [{"game_ref": "ncaaf:0842fcd69fdf5061f6751f876ead09f2"}]},
        {"bet_id": "b", "label": "$1 cash", "placed_at": now - timedelta(days=3),
         "games": [{"game_ref": "nba|DAL|BKN|2026-11-10T00:40:00+00:00"}]},              # last night: not yet stuck
        {"bet_id": "c", "label": "Kyrie under", "placed_at": now - timedelta(days=9), "pick_commence_time": now - timedelta(days=8)},
        {"bet_id": "d", "label": "Sunday parlay", "placed_at": now - timedelta(days=2),
         "games": [{"game_ref": "2026_09_TB_CHI"}, {"game_ref": "2026_10_TB_NO"}]},       # next week's game still to come
    ]
    starts = {"ncaaf:0842fcd69fdf5061f6751f876ead09f2": now - timedelta(days=2, hours=20),
              "nfl:2026_09_TB_CHI": now - timedelta(days=2), "nfl:2026_10_TB_NO": now + timedelta(days=5)}
    lines = watchdog.stale_open(bets, starts, now)
    assert len(lines) == 1 and lines[0].startswith("2 bet(s) still open 36+ hours")
    assert "Kyrie under" in lines[0] and "50% profit boost" in lines[0] and "$1 cash" not in lines[0]
    assert watchdog.stale_open(bets[1:2], starts, now) == []
