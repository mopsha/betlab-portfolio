"""The NBA props pipeline: live rows, pricing, the line tracker, grading and closing pulls."""

import numpy as np
import pandas as pd
import pytest

from betlab import grading
from betlab import tracking_nba as TN
from betlab.cards import props_nba as N
from betlab.models import live_nba as L
from betlab.models import player_nba as P
from betlab.models import team_nba as T
from test_nba_models import TEAMS, toy_boxes

NAMES = {t: f"{t.title()} City" for t in TEAMS}


def toy_night():
    """Toy seasons with display names, plus one game the next night (AAA hosts BBB)."""
    sch, tb, pb = toy_boxes()
    home = [tb[(tb["game_id"] == g) & (tb["team_home_away"] == "home")]["team_abbreviation"].iloc[0] for g in sch["game_id"]]
    away = [tb[(tb["game_id"] == g) & (tb["team_home_away"] == "away")]["team_abbreviation"].iloc[0] for g in sch["game_id"]]
    sch = sch.assign(home_abbreviation=home, away_abbreviation=away,
                     home_display_name=[NAMES[t] for t in home], away_display_name=[NAMES[t] for t in away])
    pb = pb.assign(athlete_display_name=[f"Player {a}" for a in pb["athlete_id"]])
    tip = sch["tipoff"].max() + pd.Timedelta(days=1)
    return sch, tb, pb, tip


def params_for(sch, tb, pb):
    pg = P.player_games(pb, T.team_games(tb, sch), sch)
    return P.fit(pg[pg["n_prior"] >= 3])


def snapshot(tip, asof, lines):
    """lines: [(player, market, fd point, sharp point, sharp over price)] -> a props snapshot."""
    rows = []
    for player, market, fd_point, sharp_point, sharp_over in lines:
        for book, point, over, under in (("fanduel", fd_point, -110, -110), ("pinnacle", sharp_point, sharp_over, -sharp_over)):
            for oc, price in (("Over", over), ("Under", under)):
                rows.append({"snapshot_ts": asof.isoformat(), "sport_key": "basketball_nba", "event_id": "ev1",
                             "commence_time": tip.isoformat(), "home_team": NAMES["AAA"], "away_team": NAMES["BBB"],
                             "bookmaker": book, "market": market, "last_update": asof.isoformat(), "outcome": oc,
                             "player": player, "point": point, "price": price})
    return pd.DataFrame(rows)


def test_nb_quote_translation_round_trips():
    r = 12.0
    p = N._p_over(22.0, 21.5, r)
    assert N.mu_for_quote(p, 21.5, r) == pytest.approx(22.0, abs=1e-3)
    q = pd.DataFrame({"point": [21.5, 23.5], "p_over": [0.55, 0.45]})
    same = N.fair_at(q.iloc[:1], 21.5, r)
    assert same == 0.55 and N.fair_at(q.iloc[1:], 21.5, r) > 0.45        # a higher line moved down: over likelier


def test_tonight_rows_and_pricing(monkeypatch):
    sch, tb, pb, tip = toy_night()
    params = params_for(sch, tb, pb)
    monkeypatch.setattr(L, "load_params", lambda kind="pre_lineup": params)
    asof = tip - pd.Timedelta(minutes=45)
    # AAA's second option (athlete 1) is ruled out: AAA's others should gain minutes and usage
    snap = snapshot(tip, asof, [("Player 0", "player_points", 20.5, 20.5, -130),
                                ("Player 0", "player_rebounds_assists", 7.5, 8.5, 100),
                                ("Player 10", "player_points", 19.5, 19.5, 110),
                                ("Nobody Here", "player_points", 9.5, 9.5, -110)])
    offers, rows = N.price(snap, asof, data=(sch, tb, pb), injuries=({1}, set()), live_rosters=False)
    assert len(rows) == 3 and len(offers) == 6                          # the unknown name is skipped, never guessed
    tr = pd.DataFrame(rows).set_index(["player", "stat"])
    assert tr.loc[("Player 0", "points"), "missing_min"] > 20             # his teammate's minutes are out tonight
    assert tr.loc[("Player 10", "points"), "missing_min"] == 0
    assert tr.loc[("Player 0", "points"), "p_market"] == pytest.approx(0.5652, abs=1e-3)   # -130/+130 no-vig
    assert tr.loc[("Player 0", "ra"), "p_market"] < 0.5 + 0.2 and tr.loc[("Player 0", "ra"), "p_market"] > 0.5
    o = offers.set_index(["player", "market", "side"])
    assert set(offers["league"]) == {"nba"} and set(offers["kind"]) == {"prop"} and (offers["w_model"] == 0).all()
    assert o.loc[("Player 0", "player_points", "Over"), "p_final"] == o.loc[("Player 0", "player_points", "Over"), "p_market"]
    assert o.loc[("Player 0", "player_points", "Over"), "ev"] > 0        # FanDuel -110 on a 56.5% over
    # the live features match the backtest's for a player with a normal night
    pg = P.player_games(pb, T.team_games(tb, sch), sch)
    last = pg[pg["athlete_id"] == 10].sort_values("tipoff").iloc[-1]
    assert tr.loc[("Player 10", "points"), "ewm_min"] == pytest.approx(round(0.0 + last["ewm_min"], 1), abs=0.6)
    # stale snapshots price nothing
    assert N.price(snap, asof + pd.Timedelta(hours=3), data=(sch, tb, pb), injuries=(set(), set()), live_rosters=False)[0].empty


def test_confirmed_lineups_price_with_the_lineup_settings(monkeypatch):
    sch, tb, pb, tip = toy_night()
    params = params_for(sch, tb, pb)
    monkeypatch.setattr(L, "load_params", lambda kind="pre_lineup": params)
    monkeypatch.setattr(N, "STARTERS", 2)                        # the toy teams have three players
    asof = tip - pd.Timedelta(minutes=30)
    snap = snapshot(tip, asof, [("Player 0", "player_points", 20.5, 20.5, -130), ("Player 10", "player_points", 19.5, 19.5, 110)])
    roster = L.rosters(pb, sch, {"AAA", "BBB"}, tip)
    lu = []
    for team, nba_abbr in (("AAA", "AAA"), ("BBB", "BBB")):
        names = roster[roster["team_abbreviation"] == team]["athlete_display_name"].tolist()
        for k, name in enumerate(names):
            lu.append({"nba_game_id": "1", "team": nba_abbr, "player": name, "starter": k < 2,
                       "lineup_status": "Confirmed", "roster_status": "Inactive" if name == "Player 1" else "Active",
                       "timestamp": ""})
    lu = pd.DataFrame(lu)
    _, rows = N.price(snap, asof, data=(sch, tb, pb), injuries=(set(), set()), live_rosters=False, lineups=lu)
    tr = pd.DataFrame(rows).set_index("player")
    assert tr["lineup_known"].all() and tr.loc["Player 0", "starter_now"] in (0.0, 1.0)
    assert tr.loc["Player 0", "missing_min"] > 20                 # nba.com's Inactive list sits Player 1
    # an "Expected" lineup is a projection: never used
    _, rows = N.price(snap, asof, data=(sch, tb, pb), injuries=(set(), set()), live_rosters=False,
                      lineups=lu.assign(lineup_status="Expected"))
    assert not pd.DataFrame(rows)["lineup_known"].any()
    # ESPN abbreviations differ for six teams
    assert N.NBA_TO_ESPN["NYK"] == "NY" and N.NBA_TO_ESPN["UTA"] == "UTAH"


def test_lineups_file_parses(monkeypatch):
    from betlab.sources import nba

    class Resp:
        status_code = 200

        def json(self):
            return {"games": [{"gameId": "0022500893", "homeTeam": {"teamAbbreviation": "NYK", "players": [
                {"playerName": "Jalen Brunson", "position": "PG", "lineupStatus": "Confirmed", "rosterStatus": "Active", "timestamp": "t"},
                {"playerName": "Mitchell Robinson", "position": "", "lineupStatus": "Confirmed", "rosterStatus": "Inactive", "timestamp": "t"}]},
                "awayTeam": {"teamAbbreviation": "OKC", "players": []}}]}

    class Session:
        def get(self, url, headers=None, timeout=None):
            assert "00_daily_lineups_20260304" in url
            return Resp()

    df = nba.lineups("20260304", session=Session())
    assert df["starter"].tolist() == [True, False] and df["roster_status"].tolist() == ["Active", "Inactive"]


def test_tracker_records_then_grades_from_box_scores(tmp_path, monkeypatch):
    monkeypatch.setattr(TN, "PATH", tmp_path / "nba_prop_lines.csv")
    tip = pd.Timestamp("2026-10-21T23:30:00Z")
    base = {"event_id": "ev1", "tipoff": tip.isoformat(), "matchup": "B @ A", "team": "AAA", "opp": "BBB",
            "fd_over": -110, "fd_under": -110, "p_market": 0.5, "p_model": 0.55, "market_source": "pinnacle",
            "mu": 21.0, "min_proj": 33.0, "ewm_min": 33.0, "start_share": 1.0, "missing_min": 0.0,
            "missing_points_share": 0.0, "abs_margin": 4.0, "returning": 0.0, "pace_factor": 1.0, "questionable": False}
    rows = [{**base, "player": "Player 0", "athlete_id": 7, "stat": "points", "line": 20.5},
            {**base, "player": "Player 0", "athlete_id": 7, "stat": "pra", "line": 30.5},
            {**base, "player": "Player 9", "athlete_id": 9, "stat": "points", "line": 10.5}]
    assert TN.record(rows, tip - pd.Timedelta(hours=1)) == 3
    assert TN.record([{**rows[0], "line": 21.5}], tip - pd.Timedelta(minutes=20)) == 1   # re-priced: updated, not duplicated
    assert TN.record(rows, tip + pd.Timedelta(minutes=5)) == 0                            # after tip-off: frozen
    df = TN.load()
    assert len(df) == 3 and df.loc[df["stat"] == "points"].sort_values("athlete_id")["line"].iloc[0] == 21.5
    box = pd.DataFrame({"athlete_id": [7, 9], "game_date": ["2026-10-21", "2026-10-21"], "minutes": [35.0, np.nan],
                        "points": [25, 0], "rebounds": [6, 0], "assists": [4, 0], "three_point_field_goals_made": [3, 0]})
    assert TN.grade(box, now=tip + pd.Timedelta(hours=5)) == 3
    df = TN.load().set_index(["athlete_id", "stat"])
    assert df.loc[(7, "points"), "actual"] == 25 and df.loc[(7, "pra"), "actual"] == 35
    assert df.loc[(9, "points"), "status"] == "void"
    s = TN.summary()
    assert s["graded"] == 2 and s["logloss_model"] < s["logloss_market"]      # the model leaned over on two overs


def test_grade_nba_settles_props_and_ignores_the_pick_snapshot_as_close(monkeypatch):
    tip = "2026-10-21T23:30:00Z"
    picks = pd.DataFrame([{"pick_id": "p1", "created_at": "2026-10-21T22:40:00+00:00", "league": "nba", "event_id": "ev1",
                           "game_ref": None, "commence_time": tip, "market": "player_points", "side": "Over",
                           "player": "Player 0", "point": 20.5, "price": -110.0, "units_flat": 1.0, "kind": "prop",
                           "status": "open"},
                          {"pick_id": "p2", "created_at": "2026-10-21T22:40:00+00:00", "league": "nba", "event_id": "ev1",
                           "game_ref": None, "commence_time": tip, "market": "player_points_rebounds_assists",
                           "side": "Under", "player": "Player 9", "point": 30.5, "price": -110.0, "units_flat": 1.0,
                           "kind": "prop", "status": "open"}])
    box = pd.DataFrame({"athlete_id": [7, 9], "athlete_display_name": ["Player 0", "Player 9"],
                        "game_date": ["2026-10-21", "2026-10-21"], "minutes": [35.0, 30.0], "points": [25, 20],
                        "rebounds": [6, 8], "assists": [4, 5], "three_point_field_goals_made": [3, 0]})
    seen = {}
    monkeypatch.setattr(grading, "prop_close", lambda r: seen.setdefault(r["pick_id"], {}) or {})
    out = grading.grade_nba(picks, box, now=pd.Timestamp("2026-10-22T06:00:00Z")).set_index("pick_id")
    assert out.loc["p1", "status"] == "won" and out.loc["p2", "status"] == "lost"   # 25 > 20.5; 33 > 30.5
    assert out.loc["p1", "profit_flat"] == pytest.approx(0.9091, abs=1e-3) and set(seen) == {"p1", "p2"}


def test_prop_close_skips_snapshots_from_before_the_pick(tmp_path, monkeypatch):
    from betlab import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    tip = pd.Timestamp("2026-10-21T23:30:00Z")
    day = tmp_path / "odds" / "basketball_nba" / "2026-10-21"
    day.mkdir(parents=True)
    pick_snap = snapshot(tip, tip - pd.Timedelta(minutes=50), [("Player 0", "player_points", 20.5, 20.5, -130)])
    pick_snap.to_parquet(day / "184000_props.parquet")
    r = pd.Series({"league": "nba", "event_id": "ev1", "commence_time": tip.isoformat(), "market": "player_points",
                   "player": "Player 0", "side": "Over", "point": 20.5, "created_at": "2026-10-21T22:41:00+00:00"})
    assert grading.prop_close(r) == {}                                  # only the pick's own snapshot: no close
    later = snapshot(tip, tip - pd.Timedelta(minutes=10), [("Player 0", "player_points", 20.5, 20.5, -150)])
    later.to_parquet(day / "192000_props.parquet")
    close = grading.prop_close(r)
    assert close["p_close"] == pytest.approx(0.6, abs=1e-3) and close["close_price"] == -110
    assert close["p_close_raw"] == close["p_close"]                      # no over-lean correction for NBA points


def test_nba_pull_prices_the_window_and_closes_open_picks(monkeypatch):
    from betlab import cli
    from betlab.sources import odds_api

    now = pd.Timestamp("2026-10-21T22:20:00Z")
    events = [{"id": "soon", "commence_time": "2026-10-21T23:00:00Z", "home_team": "A", "away_team": "B"},
              {"id": "later", "commence_time": "2026-10-22T02:00:00Z", "home_team": "C", "away_team": "D"},
              {"id": "picked", "commence_time": "2026-10-21T22:30:00Z", "home_team": "E", "away_team": "F"},
              {"id": "started", "commence_time": "2026-10-21T22:00:00Z", "home_team": "G", "away_team": "H"}]
    calls, saved = [], []

    class Client:
        def events(self, sport):
            return events

        def event_odds(self, sport, eid, markets, priority="normal"):
            calls.append((eid, tuple(markets), priority))
            return {"id": eid, "commence_time": "", "home_team": "", "away_team": "", "bookmakers": []}

        def odds(self, sport, markets=None, priority="normal"):
            calls.append(("lines", (), priority))
            return []

        def balance_note(self):
            return "n/a"

    monkeypatch.setattr(cli, "open_prop_markets", lambda league: {"picked": ["player_points"], "started": ["player_assists"]})
    monkeypatch.setattr(odds_api, "save_snapshot", lambda df, sport, ts, kind: saved.append(kind) or type("P", (), {"name": kind})())
    args = type("A", (), {"event": None, "tip_window": None})()
    cli._pull_props_nba(args, Client(), now)
    assert calls == [("soon", odds_api.NBA_PROP_MARKETS + odds_api.NBA_ALT_MARKETS, "normal"), ("picked", ("player_points",), "closing"),
                     ("lines", (), "normal")]
    assert saved == ["props", "pick"]
    calls.clear()
    cli._pull_props_nba(args, Client(), pd.Timestamp("2026-09-25T22:20:00Z"))    # before the season: nothing
    assert calls == []
