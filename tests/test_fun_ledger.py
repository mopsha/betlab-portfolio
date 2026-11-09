"""The fun ledger: leg labels parse, slips sync from the page's quotes and marks, and grade leg by leg."""

import json

import pandas as pd
import pytest

from betlab import fun_ledger as FL
from betlab.sources import nflverse


@pytest.mark.parametrize("label,expected", [
    ("Drake London over 5.5 receptions", ("Drake London", "receptions", "over", 5.5)),
    ("MarShawn Lloyd under 1.5 receptions", ("MarShawn Lloyd", "receptions", "under", 1.5)),
    ("Christian Watson 40+ receiving yds", ("Christian Watson", "receiving_yards", "over", 39.5)),
    ("Michael Penix Jr. over 204.5 passing yds", ("Michael Penix Jr.", "passing_yards", "over", 204.5)),
    ("Bijan Robinson anytime TD", ("Bijan Robinson", "tds", "over", 0.5)),
    ("Aaron Rodgers Over 229.5 passing yds", ("Aaron Rodgers", "passing_yards", "over", 229.5)),   # a slip's capital
])
def test_parse_leg(label, expected):
    leg = FL.parse_leg(label)
    assert (leg["player"], leg["stat"], leg["side"], leg["point"]) == expected
    assert FL.parse_leg("Something odd") is None


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(FL, "PATH", tmp_path / "fun.csv")
    games = pd.DataFrame({"game_id": ["2026_03_ATL_GB"], "home_team": ["GB"], "away_team": ["ATL"],
                          "date": [pd.Timestamp("2026-09-24")]})
    monkeypatch.setattr(nflverse, "load_games", lambda: games)
    monkeypatch.setattr(nflverse, "team_abbr_by_name", lambda: {"Green Bay Packers": "GB", "Atlanta Falcons": "ATL"})
    ps = pd.DataFrame({"game_id": "2026_03_ATL_GB", "player_id": ["a", "b", "c"],
                       "player_display_name": ["Wide Out", "Run Back", "Quarter Back"],
                       "receptions": [6, 2, 0], "receiving_yards": [71.0, 12.0, 0.0], "rushing_yards": [0.0, 88.0, 5.0],
                       "passing_yards": [0.0, 0.0, 250.0], "rushing_tds": [0, 1, 0], "receiving_tds": [0, 0, 0]})
    sn = pd.DataFrame({"game_id": "2026_03_ATL_GB", "player_id": ["a", "b", "c", "d"],
                       "player": ["Wide Out", "Run Back", "Quarter Back", "Sat Out"], "offense_snaps": [60, 40, 65, 0]})
    monkeypatch.setattr(nflverse, "load_player_stats", lambda seasons: ps)
    monkeypatch.setattr(nflverse, "load_snap_counts", lambda seasons: sn)
    return FL


def quote(sid, legs, price=300, **kw):
    return {"sgp_id": sid, "legs": legs, "price": price, "fair_price": 250, "p_fair": 0.3, "naive_price": 350,
            "matchup": "Atlanta Falcons @ Green Bay Packers", "event_id": "e1", "quoted_at": "2026-09-24T20:00:00Z"} | kw


def test_sync_and_grade(ledger):
    won = quote("w", ["Wide Out 50+ receiving yds", "Run Back anytime TD", "Quarter Back over 224.5 passing yds"])
    lost = quote("l", ["Wide Out over 6.5 receptions", "Run Back 70+ rushing yds"])
    void = quote("v", ["Wide Out over 5.5 receptions", "Sat Out over 2.5 receptions"])
    assert ledger.sync([won, lost, void], [{"sgp_id": "w", "mode": "paper", "stake": 1, "price": 300}]) == 3
    df = ledger.load().set_index("sgp_id")
    assert df.loc["w", "game_id"] == "2026_03_ATL_GB" and df.loc["w", "marked"]
    assert ledger.grade() == 3
    df = ledger.load().set_index("sgp_id")
    assert df.loc["w", "status"] == "won" and df.loc["w", "profit_1u"] == 3.0 and df.loc["w", "profit"] == 3.0
    assert df.loc["l", "status"] == "lost" and df.loc["l", "profit_1u"] == -1.0
    assert df.loc["v", "status"] == "void"
    s = ledger.summary()
    assert s["graded"] == 2 and s["won"] == 1 and s["units_at_quoted_price"] == 2.0
    # a later sync keeps the grades
    ledger.sync([won, lost, void], [])
    assert ledger.load().set_index("sgp_id").loc["w", "status"] == "won"


def test_a_bonus_bet_loss_costs_nothing(ledger):
    """Oct 19: a bonus bet's stake is the book's credit. A win pays the profit only (profit_1u x stake, as for cash),
    a loss is 0, not -stake; flagging a slip as bonus after grading changes its profit on the next sync."""
    won = quote("w", ["Wide Out 50+ receiving yds"], price=400)
    lost = quote("l", ["Wide Out over 6.5 receptions"], price=400)
    marks = [{"sgp_id": "w", "mode": "real", "stake": 2, "price": 400, "bonus": True},
             {"sgp_id": "l", "mode": "real", "stake": 2, "price": 400}]
    ledger.sync([won, lost], marks)
    ledger.grade()
    df = ledger.load().set_index("sgp_id")
    assert df.loc["w", "profit"] == 8.0 and bool(df.loc["w", "bonus"])
    assert df.loc["l", "profit"] == -2.0
    marks[1]["bonus"] = True                                   # ticked Bonus bet in My bets after it was graded
    ledger.sync([won, lost], marks)
    assert ledger.load().set_index("sgp_id").loc["l", "profit"] == 0.0


def test_a_price_edited_after_grading_reprices_the_win(ledger):
    """Nov 9: Edit works on settled bets, so a misread price can be fixed after the grade; the win's profit follows the
    new price (as the apps work it out), a loss stays -stake."""
    won = quote("w", ["Wide Out 50+ receiving yds"], price=925)
    lost = quote("l", ["Wide Out over 6.5 receptions"], price=925)
    marks = [{"sgp_id": "w", "mode": "real", "stake": 1, "price": 925}, {"sgp_id": "l", "mode": "real", "stake": 1, "price": 925}]
    ledger.sync([won, lost], marks)
    ledger.grade()
    assert ledger.load().set_index("sgp_id").loc["w", "profit"] == 9.25
    for m in marks:
        m["price"] = 295                                       # the slip said +295
    ledger.sync([won, lost], marks)
    df = ledger.load().set_index("sgp_id")
    assert df.loc["w", "profit_1u"] == 2.95 and df.loc["w", "profit"] == 2.95
    assert df.loc["l", "profit"] == -1.0
    assert FL._repriced(0.5, 200, 100, "won") == pytest.approx(0.0)       # a dropped leg's share (0.5 of 3.0) carries over


def test_sgp_plus_ticket_grades_each_leg_from_its_own_game(tmp_path, monkeypatch):
    monkeypatch.setattr(FL, "PATH", tmp_path / "fun.csv")
    games = pd.DataFrame({"game_id": ["2026_04_ATL_GB", "2026_04_NE_NYJ"], "home_team": ["GB", "NYJ"],
                          "away_team": ["ATL", "NE"], "date": [pd.Timestamp("2026-09-27")] * 2})
    monkeypatch.setattr(nflverse, "load_games", lambda: games)
    monkeypatch.setattr(nflverse, "team_abbr_by_name", lambda: {"Green Bay Packers": "GB", "Atlanta Falcons": "ATL",
                                                               "New York Jets": "NYJ", "New England Patriots": "NE"})
    ps = pd.DataFrame({"game_id": ["2026_04_ATL_GB", "2026_04_NE_NYJ"], "player_id": ["a", "b"],
                       "player_display_name": ["Wide Out", "Tight End"], "receptions": [6, 5],
                       "receiving_yards": [71.0, 44.0], "rushing_yards": [0.0, 0.0], "passing_yards": [0.0, 0.0],
                       "rushing_tds": [0, 0], "receiving_tds": [0, 1]})
    sn = pd.DataFrame({"game_id": ["2026_04_ATL_GB", "2026_04_NE_NYJ"], "player_id": ["a", "b"],
                       "player": ["Wide Out", "Tight End"], "offense_snaps": [60, 50]})
    monkeypatch.setattr(nflverse, "load_player_stats", lambda seasons: ps)
    monkeypatch.setattr(nflverse, "load_snap_counts", lambda seasons: sn)
    ticket = {"sgp_id": "plus-1", "price": 1200, "fair_price": 900, "p_fair": 0.1, "matchup": "SGP+ Sun early window",
              "quoted_at": "2026-09-27T15:00:00Z",
              "games": [{"matchup": "Atlanta Falcons @ Green Bay Packers", "legs": [{"label": "Wide Out over 5.5 receptions"}]},
                        {"matchup": "New England Patriots @ New York Jets",
                         "legs": [{"label": "Tight End anytime TD"}, {"label": "Tight End 40+ receiving yds"}]}]}
    assert FL.sync([ticket], []) == 1
    row = FL.load().iloc[0]
    assert row["n_legs"] == 3 and row["leg_games"] == '["2026_04_ATL_GB", "2026_04_NE_NYJ", "2026_04_NE_NYJ"]'
    assert FL.grade() == 1 and FL.load().iloc[0]["status"] == "won" and FL.load().iloc[0]["profit_1u"] == 12.0

    # one game's stats not out yet: the ticket waits
    FL.PATH.unlink()
    monkeypatch.setattr(nflverse, "load_player_stats", lambda seasons: ps[ps["game_id"] == "2026_04_ATL_GB"])
    FL.sync([ticket | {"sgp_id": "plus-2"}], [])
    assert FL.grade() == 0 and FL.load().iloc[0]["status"] == "open"


def test_game_line_legs_settle_from_the_final_score(ledger, monkeypatch):
    finals = pd.DataFrame({"game_id": ["2026_03_ATL_GB"], "home_team": ["GB"], "away_team": ["ATL"],
                           "date": [pd.Timestamp("2026-09-24")], "home_pts": [27.0], "away_pts": [20.0]})
    monkeypatch.setattr(nflverse, "load_games", lambda: finals)
    assert FL.parse_leg("Green Bay Packers -3.5") == {"team": "Green Bay Packers", "stat": "spread", "side": "yes", "point": -3.5}
    assert FL.parse_leg("Over 44.5 total points")["side"] == "over"
    won = quote("gw", ["Green Bay Packers ML", "Green Bay Packers -6.5", "Over 44.5 total points", "Wide Out over 5.5 receptions"])
    lost = quote("gl", ["Atlanta Falcons +6.5", "Run Back anytime TD"])
    push = quote("gp", ["Green Bay Packers -7", "Wide Out over 5.5 receptions"])
    ledger.sync([won, lost, push], [])
    assert ledger.grade() == 3
    df = ledger.load().set_index("sgp_id")
    assert (df.loc["gw", "status"], df.loc["gl", "status"], df.loc["gp", "status"]) == ("won", "lost", "void")

    # a game without a final score leaves the slip open
    FL.PATH.unlink()
    monkeypatch.setattr(nflverse, "load_games", lambda: finals.assign(home_pts=[None], away_pts=[None]))
    ledger.sync([quote("go", ["Green Bay Packers ML"])], [])
    assert ledger.grade() == 0


def test_a_void_leg_comes_off_the_slip_as_fanduel_settles_it():
    """Oct 10: a void (or pushed) leg no longer voids the whole slip. The rest stands at the price with that
    leg taken out at its fair chance; every leg void voids it; an unknown fair chance falls back to void."""
    import json

    import pandas as pd

    from betlab import fun_ledger as FL

    def row(price, leg_p):
        return pd.DataFrame([{**{c: None for c in FL.COLUMNS}, "sgp_id": "x", "price": price, "marked": False,
                              "leg_p": json.dumps(leg_p) if leg_p is not None else None}])
    res = lambda *o: [{"leg": f"L{i}", "result": r, "value": None} for i, r in enumerate(o)]
    df = row(500.0, [0.6, 0.5, 0.7])
    assert FL._finish(df, 0, df.iloc[0], res("won", "void", "won"), "t")
    assert df.at[0, "status"] == "won" and df.at[0, "profit_1u"] == pytest.approx(6 * 0.5 - 1)
    assert json.loads(df.at[0, "leg_results"])[1]["p"] == 0.5
    df = row(500.0, [0.6, 0.5, 0.7])
    FL._finish(df, 0, df.iloc[0], res("lost", "void", "won"), "t")
    assert df.at[0, "status"] == "lost"
    df = row(500.0, [0.6, 0.5])
    FL._finish(df, 0, df.iloc[0], res("void", "push"), "t")
    assert df.at[0, "status"] == "void" and df.at[0, "profit_1u"] == 0
    df = row(500.0, None)
    FL._finish(df, 0, df.iloc[0], res("won", "void"), "t")
    assert df.at[0, "status"] == "void"


def test_a_novig_void_leg_counts_at_its_fair_value():
    """Oct 28 (docs.novig.com, RFQ > Settlement): Novig pays the pot times each leg's value, a void leg at its fair
    value; it can pay back less than the stake, and all legs void still pays that share. A lost leg loses it all."""
    import json

    import pandas as pd

    from betlab import fun_ledger as FL

    def row(price, leg_p):
        return pd.DataFrame([{**{c: None for c in FL.COLUMNS}, "sgp_id": "x", "book": "novig", "price": price,
                              "marked": False, "leg_p": json.dumps(leg_p)}])
    res = lambda *o: [{"leg": f"L{i}", "result": r, "value": None} for i, r in enumerate(o)]
    df = row(100.0, [0.6, 0.4])                       # +100: a 2.0 pot; one leg void at 0.4 pays back 0.8
    FL._finish(df, 0, df.iloc[0], res("won", "void"), "t")
    assert df.at[0, "status"] == "won" and df.at[0, "profit_1u"] == pytest.approx(2.0 * 0.4 - 1)
    df = row(500.0, [0.6, 0.5])
    FL._finish(df, 0, df.iloc[0], res("void", "push"), "t")
    assert df.at[0, "status"] == "void" and df.at[0, "profit_1u"] == pytest.approx(6 * 0.3 - 1)
    df = row(500.0, [0.6, 0.5])
    FL._finish(df, 0, df.iloc[0], res("lost", "void"), "t")
    assert df.at[0, "status"] == "lost" and df.at[0, "profit_1u"] == -1
    df = row(500.0, [0.6, 0.5])
    FL._finish(df, 0, df.iloc[0], res("won", "won"), "t")
    assert df.at[0, "profit_1u"] == pytest.approx(5.0)


def test_soccer_scores_fall_back_to_espn_when_football_data_lags(monkeypatch):
    """Oct 12: football-data.co.uk's 2026-27 files stopped at Sep 20, so soccer tickets stayed open."""
    from betlab import fun_ledger as F
    from betlab.sources import espn_soccer, soccer

    monkeypatch.setattr(soccer, "result", lambda *a: None)
    monkeypatch.setattr(espn_soccer, "final_score", lambda *a: (3, 0))
    assert F._soccer_result("serie_a", "Inter Milan", "Parma", "2026-10-10T16:00:00Z") == {"hg": 3, "ag": 0}
    monkeypatch.setattr(espn_soccer, "final_score", lambda *a: None)      # not over yet
    assert F._soccer_result("serie_a", "Inter Milan", "Parma", "2026-10-10T16:00:00Z") is None
    monkeypatch.setattr(soccer, "result", lambda *a: {"hg": 1, "ag": 1, "close": None})
    assert F._soccer_result("serie_a", "Inter Milan", "Parma", "2026-10-10T16:00:00Z")["hg"] == 1   # football-data first


def test_the_quote_model_learns_fanduels_parlay_pricing():
    """Oct 12: FanDuel's quote vs our fair odds, from fair odds, legs, cross-game and its own leg prices."""
    import numpy as np

    from betlab import fun_ledger as F
    from betlab import odds_math as om

    rng = np.random.default_rng(0)
    rows = []
    for i in range(80):
        legs = int(rng.integers(2, 8)); fair = float(rng.uniform(150, 3000)); naive = fair * float(rng.uniform(0.8, 1.4))
        fd = om.american_to_decimal(fair); nd = om.american_to_decimal(naive)
        ratio = np.exp(0.05 - 0.07 * legs + 0.3 * np.log(nd / fd))             # the true pricing rule
        price = om.prob_to_american(1 / (fd * ratio))
        rows.append({"sgp_id": f"s{i}", "book": "fanduel", "price": price, "fair_price": fair, "naive_price": naive, "n_legs": legs})
    m = F.quote_model(pd.DataFrame(rows), ridge=1e-6)
    assert m["quotes"] == 80 and abs(m["coef"]["legs"] + 0.07) < 0.01 and abs(m["coef"]["naive_gap"] - 0.3) < 0.02
    r = rows[0]
    assert abs(F.likely_price(m, r["fair_price"], r["naive_price"], r["n_legs"], False) - r["price"]) <= 2
    assert F.quote_model(pd.DataFrame(rows[:10])) is None                      # too few quotes: the bands stay
    assert F.likely_price(m, 500, None, 4, False) is None


def test_anytime_td_counts_return_and_defensive_tds():
    """Both books settle anytime TD on any TD the player scores himself except passing (Oct 13)."""
    import pandas as pd
    from betlab.sources.nflverse import anytime_tds

    returner = pd.Series({"rushing_tds": 0, "receiving_tds": 0, "passing_tds": 2, "special_teams_tds": 1})
    assert anytime_tds(returner) == 1.0                       # a kick return counts, his passing TDs don't
    assert anytime_tds(pd.Series({"rushing_tds": 0, "receiving_tds": 0, "def_tds": float("nan")})) == 0.0
    frame = pd.DataFrame({"rushing_tds": [1, 0], "receiving_tds": [0, 0], "fumble_recovery_tds": [0, 1]})
    assert anytime_tds(frame).tolist() == [1, 1]


def test_custom_bets_take_their_sport_from_the_game_refs():
    """Oct 20: the app's bets rows carry no sport, so Mike's soccer and NBA parlays were read as NFL."""
    assert FL.sport_of_refs(["nba|DET|BOS|2026-10-20T19:00:00+00:00"]) == "nba"
    assert FL.sport_of_refs(["ucl|Porto|PSV Eindhoven|2026-10-20T19:00:00Z", "serie_a|Parma|Torino|x"]) == "soccer"
    assert FL.sport_of_refs(["2026_07_KC_LV"]) is None and FL.sport_of_refs([]) is None
    assert FL.sport_of_refs(["uel|Juventus|Rennes|x", "ncaaf:401871056"]) == "mixed"
    assert [FL.leg_sport(r) for r in ("nhl:2026020123", "ncaab:401", "2026_07_KC_LV", "401871056")] == ["nhl", "ncaab", "nfl", None]
    assert FL._bare("ncaaf:401871056") == "401871056" and FL._bare("2026_07_KC_LV") == "2026_07_KC_LV"


def test_a_parlay_across_sports_grades_each_leg_by_its_own_sport(tmp_path, monkeypatch):
    """Oct 22: Mike's Europa League + college football parlay; before, it went to the NFL grader, which would have
    failed on the soccer ref and stopped NFL fun grading."""
    from betlab.sources import cfbd, nflverse

    monkeypatch.setattr(FL, "PATH", tmp_path / "fun.csv")
    monkeypatch.setattr(nflverse, "load_games", lambda: pd.DataFrame(columns=["game_id", "home_team", "away_team", "date"]))
    monkeypatch.setattr(nflverse, "team_abbr_by_name", lambda: {})
    finals = pd.DataFrame({"game_id": ["401871056", "401862807"], "home_team": ["Kennesaw State", "Memphis"],
                           "away_team": ["Liberty", "East Carolina"], "home_pts": [None, None], "away_pts": [None, None]})
    monkeypatch.setattr(cfbd, "games", lambda: finals)
    monkeypatch.setattr(cfbd, "team_names", lambda: {"Liberty": "Liberty", "Memphis": "Memphis"})
    scores = {"Lech Poznań": {"hg": 2, "ag": 1}, "Juventus": {"hg": 2, "ag": 0}}
    monkeypatch.setattr(FL, "_soccer_result", lambda league, home, away, kickoff: scores.get(home))
    bet = {"sgp_id": "custom-fd-uelcfb4-1022", "price": 376, "stake": 1.0, "mode": "real", "placed_at": "2026-10-22T04:33:00Z",
           "matchup": "Parlay Thu Oct 22", "games": [
               {"legs": ["Over 1.5 goals"], "game_ref": "uel|Lech Poznań|Sunderland|2026-10-22T16:45:00+00:00"},
               {"legs": ["Juventus to win"], "game_ref": "uel|Juventus|Rennes|2026-10-22T16:45:00+00:00"},
               {"legs": ["Liberty ML"], "game_ref": "ncaaf:401871056"},
               {"legs": ["Memphis ML"], "game_ref": "ncaaf:401862807"}]}
    FL.sync([], [bet])
    assert FL.load().iloc[0]["sport"] == "mixed"
    assert FL.grade() == 0                                    # soccer won, college not final: open
    assert FL.load().iloc[0]["status"] == "open"
    finals.loc[:, ["home_pts", "away_pts"]] = [[20.0, 31.0], [35.0, 14.0]]   # Liberty won away, Memphis won at home
    assert FL.grade() == 1
    r = FL.load().iloc[0]
    assert r["status"] == "won" and r["profit"] == pytest.approx(3.76)
    assert [x["result"] for x in json.loads(r["leg_results"])] == ["won"] * 4
    finals.loc[1, ["home_pts", "away_pts"]] = [10.0, 14.0]
    df = FL.load()
    df.loc[0, "status"] = "open"
    FL.save(df)
    assert FL.grade() == 1 and FL.load().iloc[0]["status"] == "lost"


def test_a_lost_leg_settles_the_slip_even_with_a_leg_the_grader_cant_read():
    df = pd.DataFrame([{**{c: None for c in FL.COLUMNS}, "sgp_id": "custom-x", "status": "open", "price": 1501.0,
                        "marked": True, "mode": "real", "stake": 2.0, "bonus": True}])
    lost = [{"leg": "Barcelona to win", "result": "lost"}, {"leg": "A Player to score or assist", "result": "unknown"}]
    assert FL._finish(df, 0, df.iloc[0], lost, "t") and df.at[0, "status"] == "lost"
    df.at[0, "status"] = "open"
    waiting = [{"leg": "Over 5.5 goals", "result": "won"}, {"leg": "A Player to score or assist", "result": "unknown"}]
    assert not FL._finish(df, 0, df.iloc[0], waiting, "t") and df.at[0, "status"] == "open"


def test_a_cashed_out_slip_is_settled_at_what_the_book_paid_back():
    """Oct 22: an 8-leg SGP+ marked for 1u, cashed out for $5.29 on $5 (1.058u back)."""
    r = {"marked": True, "stake": 1.0, "bonus": False, "cashout": 1.058}
    assert FL.marked_profit(-1.0, r) == pytest.approx(0.06) and FL.marked_profit(13.98, r) == pytest.approx(0.06)
    assert FL.marked_profit(None, r) == pytest.approx(0.06)
    assert FL.marked_profit(-1.0, r | {"cashout": None}) == -1.0
    assert FL.marked_profit(-1.0, r | {"bonus": True}) == pytest.approx(1.06)


def test_a_profit_boost_multiplies_a_marked_wins_profit():
    r = {"marked": True, "stake": 2.0, "bonus": False, "cashout": None, "boost": 100}
    assert FL.marked_profit(1.78, r) == pytest.approx(7.12) and FL.marked_profit(-1.0, r) == -2.0


def test_a_leg_with_no_game_is_found_and_a_lost_leg_settles_the_slip(ledger):
    """Oct 25: slips read from screenshots left some legs' games unnamed (Jordan Love, Joe Burrow), and the NFL grader
    kept them open though another leg had lost. The player's game comes from that week's stats now."""
    lost = quote("nl", ["Quarter Back 225+ passing yds", "Run Back 100+ rushing yds"])
    found = quote("nf", ["Quarter Back 225+ passing yds", "Wide Out Over 5.5 receptions"])
    ledger.sync([lost, found], [])
    df = ledger.load()
    df["leg_games"] = json.dumps([None, "2026_03_ATL_GB"])
    ledger.save(df)
    assert ledger.grade() == 2
    df = ledger.load().set_index("sgp_id")
    assert df.loc["nl", "status"] == "lost" and df.loc["nf", "status"] == "won"
    assert json.loads(df.loc["nf", "leg_results"])[0] == {"leg": "Quarter Back 225+ passing yds", "result": "won",
                                                          "value": 250.0}


def test_slips_with_only_matchups_find_their_game_refs(tmp_path, monkeypatch):
    """Oct 22-24: slips entered by hand carried matchups but no game refs (and soccer refs without a kickoff), so
    none ever graded. The sync finds each ref from the matchup and the slip's date."""
    from betlab import tracking_soccer
    from betlab.sources import cfbd, nba

    sch = pd.DataFrame({"start_date": ["2026-10-23T23:00Z", "2026-10-30T23:00Z"],
                        "home_display_name": ["Boston Celtics"] * 2, "away_display_name": ["New York Knicks"] * 2,
                        "home_abbreviation": ["BOS"] * 2, "away_abbreviation": ["NY"] * 2})
    monkeypatch.setattr(nba, "load_schedules", lambda seasons, **kw: sch)
    games = pd.DataFrame({"game_id": ["401858271"], "home_team": ["Virginia"], "away_team": ["Duke"],
                          "kickoff": [pd.Timestamp("2026-10-23 19:00", tz="America/New_York")]})
    monkeypatch.setattr(cfbd, "games", lambda: games)
    monkeypatch.setattr(cfbd, "team_names", lambda: {"Duke Blue Devils": "Duke", "Virginia Cavaliers": "Virginia"})
    lines = tmp_path / "soccer_lines.csv"
    pd.DataFrame({"league": ["epl"], "home": ["Arsenal"], "away": ["Everton"],
                  "commence_time": ["2026-10-24T14:00:00Z"]}).to_csv(lines, index=False)
    monkeypatch.setattr(tracking_soccer, "PATH", lines)
    when, found = "2026-10-23T22:48:00Z", {}
    assert FL._find_ref("nba", "New York Knicks @ Boston Celtics", None, when, found) == "nba|BOS|NY|2026-10-23T23:00Z"
    assert FL._find_ref("ncaaf", "Duke Blue Devils @ Virginia Cavaliers", None, when, found) == "ncaaf:401858271"
    assert FL._find_ref("soccer", "Everton @ Arsenal", "epl|Arsenal|Everton", when, found) == \
        "epl|Arsenal|Everton|2026-10-24T14:00:00+00:00"
    assert FL._find_ref("nba", "Utah Jazz @ Boston Celtics", None, when, found) is None      # no such game
    assert FL._find_ref("nba", "x", "nba|BOS|NY|2026-10-23T23:00Z", when, found) == "nba|BOS|NY|2026-10-23T23:00Z"


def test_first_td_scorer_legs_grade_from_the_games_first_touchdown(ledger):
    """Oct 22: Mike's "Drake Maye first TD scorer" at Novig. Won only if his was the game's first TD; a player who
    didn't play voids it; open until the play-by-play is out."""
    assert FL.parse_leg("Drake Maye first TD scorer") == {"player": "Drake Maye", "stat": "first_td", "side": "over",
                                                          "point": 0.5}
    ps = nflverse.load_player_stats([2026])
    sn = nflverse.load_snap_counts([2026])
    finals = pd.DataFrame().rename_axis("game_id")
    labels = ["Run Back first TD scorer", "Wide Out first TD scorer", "Sat Out first TD scorer"]
    gids = ["2026_03_ATL_GB"] * 3
    res = FL.nfl_leg_results(labels, gids, ps, sn, finals, {}, {"2026_03_ATL_GB": "b"})
    assert [x["result"] for x in res] == ["won", "lost", "void"]
    assert FL.nfl_leg_results(labels[:1], gids[:1], ps, sn, finals, {}, {})[0]["result"] == "open"


def test_bet_protect_counts_a_did_not_play_leg_as_won_and_takes_its_fee():
    """Oct 26: Oct 19's +911 bonus parlay was "INJURY COVERED, WON ON FANDUEL" (Chigoziem Okonkwo sat; $91.15 paid),
    but BetLab voided it. A protected slip's did-not-play leg now counts as won; the 3% fee comes off every settled
    slip but a void, in cash even on a bonus bet."""
    row = {**{c: None for c in FL.COLUMNS}, "sgp_id": "custom-p", "status": "open", "price": 911.0, "marked": True,
           "mode": "real", "stake": 2.0, "bonus": True, "protect": True}
    legs = [{"leg": "Mike Evans 40+ receiving yds", "result": "won", "value": 94.0},
            {"leg": "Chigoziem Okonkwo 30+ receiving yds", "result": "void", "value": None}]
    df = pd.DataFrame([row])
    assert FL._finish(df, 0, df.iloc[0], legs, "t") and df.at[0, "status"] == "won"
    assert df.at[0, "profit"] == round(2 * 9.11 - 0.06, 2)
    assert "Bet Protect+" in json.loads(df.at[0, "leg_results"])[1]["note"]
    df = pd.DataFrame([row | {"protect": False}])
    # unprotected (Nov 9): the book pays the rest at a price only it knows: the slip waits for its cash-out
    assert not FL._finish(df, 0, df.iloc[0], legs, "t") and df.at[0, "status"] == "open"
    df = pd.DataFrame([row | {"protect": "True", "bonus": False}])
    FL._finish(df, 0, df.iloc[0], [{"leg": "A over 1.5 receptions", "result": "lost", "value": 1.0}], "t")
    assert df.at[0, "profit"] == -2.06                                         # a cash loss pays the fee too


def test_a_night_game_grades_from_espn_before_nflverse_posts():
    """Oct 27: nflverse hadn't posted Monday night at the 3 AM grade; ESPN's final box grades it. A player missing
    from ESPN's box stays open (nflverse decides), not void."""
    def summary(state):
        return {"header": {"competitions": [{"status": {"type": {"state": state}},
                                             "competitors": [{"homeAway": "home", "score": "21"},
                                                             {"homeAway": "away", "score": "38"}]}]},
                "boxscore": {"players": [{"statistics": [
                    {"keys": ["rushingAttempts", "rushingYards", "rushingTouchdowns"],
                     "athletes": [{"athlete": {"displayName": "Saquon Barkley"}, "stats": ["7", "62", "1"]}]},
                    {"keys": ["receptions", "receivingYards", "receivingTouchdowns"],
                     "athletes": [{"athlete": {"displayName": "Jake Ferguson"}, "stats": ["0", "0", "0"]}]}]}]}}
    gid = "2026_07_DAL_PHI"
    finals = pd.DataFrame([{"game_id": gid, "espn": 401873009, "home_team": "PHI", "away_team": "DAL",
                            "home_pts": None, "away_pts": None}]).set_index("game_id")
    empty = pd.DataFrame(columns=["game_id", "player_id", "player_display_name", "player", "offense_snaps"])
    ps, sn, fin, fe = FL.with_espn([gid], empty, empty, finals, get=lambda url, ttl=None: summary("in"))
    assert fe == set()                                            # not final yet: waits
    ps, sn, fin, fe = FL.with_espn([gid], empty, empty, finals, get=lambda url, ttl=None: summary("post"))
    assert fe == {gid} and fin.loc[gid, "home_pts"] == 21
    labels = ["Saquon Barkley under 64.5 rushing yds", "Saquon Barkley anytime TD", "Jake Ferguson 40+ receiving yds",
              "Dallas Cowboys ML", "Tanner McKee 175+ passing yds"]
    got = FL.nfl_leg_results(labels, [gid] * 5, ps, sn, fin, {"Dallas Cowboys": "DAL"}, None, fe)
    assert [(x["result"], x["value"]) for x in got] == [("won", 62.0), ("won", 1.0), ("lost", 0.0), ("won", 17.0),
                                                         ("open", None)]


def test_espn_replaces_a_half_posted_nflverse_game():
    """Oct 30: nflverse had Thursday night's player stats but not its snap counts at the 3 AM grade; mixing them with
    ESPN's box read every player as 0 (Matthew Golden's TD and Bryce Young's 209 yards graded lost)."""
    summary = {"header": {"competitions": [{"status": {"type": {"state": "post"}},
                                            "competitors": [{"homeAway": "home", "score": "19"},
                                                            {"homeAway": "away", "score": "27"}]}]},
               "boxscore": {"players": [{"statistics": [
                   {"keys": ["receptions", "receivingYards", "receivingTouchdowns"],
                    "athletes": [{"athlete": {"displayName": "Matthew Golden"}, "stats": ["7", "79", "1"]}]}]}]}}
    gid = "2026_08_CAR_GB"
    finals = pd.DataFrame([{"game_id": gid, "espn": 401873023, "home_team": "GB", "away_team": "CAR",
                            "home_pts": 19, "away_pts": 27}]).set_index("game_id")
    ps = pd.DataFrame([{"game_id": gid, "player_id": "00-0040667", "player_display_name": "Matthew Golden",
                        "receiving_yards": 79.0, "receiving_tds": 1.0, "receptions": 7.0}])
    empty = pd.DataFrame(columns=["game_id", "player_id", "player", "offense_snaps"])
    ps, sn, fin, fe = FL.with_espn([gid], ps, empty, finals, get=lambda url, ttl=None: summary)
    assert fe == {gid} and set(ps["game_id"]) == {gid} and len(ps) == 1          # ESPN's box alone
    got = FL.nfl_leg_results(["Matthew Golden anytime TD", "Matthew Golden 60+ receiving yds"], [gid] * 2,
                             ps, sn, fin, {}, None, fe)
    assert [(x["result"], x["value"]) for x in got] == [("won", 1.0), ("won", 79.0)]


def test_a_book_full_first_name_grades_against_the_box_score_short_one():
    """Nov 1: FanDuel's slip said "Chigoziem Okonkwo", nflverse and ESPN say "Chig Okonkwo": the leg stayed open and a
    won $100 parlay never settled. config/player_aliases.yaml carries the book's name across."""
    gid = "2026_08_PHI_WAS"
    ps = pd.DataFrame([{"game_id": gid, "player_id": "00-0037809", "player_display_name": "Chig Okonkwo",
                        "receiving_yards": 32.0}])
    sn = pd.DataFrame([{"game_id": gid, "player_id": "00-0037809", "player": "Chig Okonkwo", "offense_snaps": 40}])
    finals = pd.DataFrame().rename_axis("game_id")
    got = FL.nfl_leg_results(["Chigoziem Okonkwo 30+ receiving yds", "Chig Okonkwo 60+ receiving yds"], [gid] * 2,
                             ps, sn, finals, {})
    assert [(x["result"], x["value"]) for x in got] == [("won", 32.0), ("lost", 32.0)]


def test_recently_settled_nfl_slips_are_checked_again():
    """Oct 30: a settled slip was never looked at again, so a wrong 3 AM grade stood; NFL slips settled in the last
    3 days are graded again and change only when a leg's result or value did."""
    from datetime import datetime, timezone
    now = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)
    base = {c: None for c in FL.COLUMNS}
    df = pd.DataFrame([base | {"sgp_id": "a", "status": "lost", "game_id": "2026_08_CAR_GB", "graded_at": "2026-10-30T07:02:03+00:00"},
                       base | {"sgp_id": "b", "status": "lost", "game_id": "2026_05_X_Y", "graded_at": "2026-10-20T07:00:00+00:00"},
                       base | {"sgp_id": "c", "status": "open", "game_id": "2026_08_CAR_GB", "graded_at": None},
                       base | {"sgp_id": "d", "status": "won", "game_id": "nba|NYK|BOS|t", "sport": "nba",
                               "graded_at": "2026-10-30T07:00:00+00:00"}])
    assert list(FL._settled_nfl(df, now)["sgp_id"]) == ["a"]
    old = json.dumps([{"leg": "Matthew Golden anytime TD", "result": "lost", "value": 0.0}])
    assert FL._same_legs(old, [{"leg": "Matthew Golden anytime TD", "result": "lost", "value": 0.0}])
    assert not FL._same_legs(old, [{"leg": "Matthew Golden anytime TD", "result": "won", "value": 1.0}])
