"""College basketball: efficiency ratings and the backtest's line-move measure."""

import numpy as np
import pandas as pd

from betlab import backtest_ncaab as B
from betlab.models import ncaab as M


def toy(n_days=60, seed=0):
    """Six teams; A is far better on offense, F on defense, B plays fast."""
    rng = np.random.default_rng(seed)
    off = {"A": 12, "B": 0, "C": 0, "D": 0, "E": -4, "F": 0}
    dfn = {"A": 0, "B": 0, "C": 0, "D": 0, "E": -4, "F": 10}
    pace = {"A": 0, "B": 6, "C": 0, "D": 0, "E": 0, "F": 0}
    teams, rows = list(off), []
    for d in range(n_days):
        day = pd.Timestamp("2025-11-05", tz="UTC") + pd.Timedelta(days=d)
        order = rng.permutation(teams)                   # a fresh set of matchups every day
        for i in range(3):
            h, a = order[2 * i], order[2 * i + 1]
            poss = 68 + pace[h] + pace[a] + rng.normal(0, 2)
            gid = f"{d}-{i}"
            for team, opp, home in ((h, a, True), (a, h, False)):
                ortg = 105 + (2 if home else -2) + off[team] - dfn[opp] + rng.normal(0, 6)
                rows.append({"game_id": gid, "season": 2026, "start": day, "team": team, "opp": opp,
                             "is_home": home, "neutral": False, "poss": poss, "ortg": ortg})
    return pd.DataFrame(rows)


def test_ratings_recover_offense_defense_pace_and_home_court():
    r = M.fit(toy(), "2026-01-10")
    assert max(r.off, key=r.off.get) == "A" and max(r.dfn, key=r.dfn.get) == "F"
    assert min(r.off, key=r.off.get) == "E" and max(r.pace, key=r.pace.get) == "B"
    assert 2 < r.home < 6                               # 4 points per 100 between home and away sides
    pr = r.project("A", "E")
    assert pr["margin"] > 10 and 120 < pr["total"] < 170
    assert r.project("A", "E", neutral=True)["margin"] < pr["margin"]


def test_line_moves_measures_the_move_toward_the_model():
    pred = pd.DataFrame({"season": 2026, "m_margin": [8.0, -8.0, 1.0] * 20, "spread_open": [2.0, -2.0, 1.0] * 20,
                         "spread_line": [3.0, -3.5, 1.0] * 20, "m_total": 140.0, "total_open": 140.0,
                         "total_line": 140.0})
    lm = B.line_moves(pred, cuts=(5,)).set_index("market")
    assert lm.loc["spread", "games"] == 40 and lm.loc["spread", "move_toward_model"] == 1.25
    assert lm.loc["spread", "implied_clv"] > 0


# ---------------------------------------------------------------- live: names, card, reads, grading
import json
from pathlib import Path

import pytest

from betlab import grading, ncaab_reads
from betlab.cards import ncaab as C
from betlab.sources import cbbd


def test_every_current_feed_name_matches_a_school():
    names = json.loads((Path(__file__).parent / "ncaab_feed_names.json").read_text())
    tn = cbbd.team_names(feed_names=names)
    missing = [n for n in names if n not in tn]
    assert missing == ["St. Francis (PA) Red Flash"]              # left Division I for 2026-27
    assert tn["Florida St Seminoles"] == "Florida State" and tn["IUPUI Jaguars"] == "IU Indianapolis"
    assert tn["Army Knights"] == "Army" and tn["St John's Red Storm"] == "St. John's"


def book(event, home, away, when, fd_spread, sharp_spread, fd_total=140.5, sharp_total=140.5):
    rows = []
    for bk, sp, tot in (("fanduel", fd_spread, fd_total), ("pinnacle", sharp_spread, sharp_total)):
        for outcome, pt, pr in ((home, sp, -110), (away, -sp, -110)):
            rows.append({"event_id": event, "commence_time": when, "home_team": home, "away_team": away,
                         "bookmaker": bk, "market": "spreads", "outcome": outcome, "point": pt, "price": pr,
                         "player": None, "sport_key": "basketball_ncaab", "snapshot_ts": when})
        for outcome, pr in (("Over", -110), ("Under", -110)):
            rows.append({"event_id": event, "commence_time": when, "home_team": home, "away_team": away,
                         "bookmaker": bk, "market": "totals", "outcome": outcome, "point": tot, "price": pr,
                         "player": None, "sport_key": "basketball_ncaab", "snapshot_ts": when})
    return rows


def test_card_reads_and_new_york_rules():
    tg = toy()
    when = "2026-01-10T00:00:00Z"
    snap = pd.DataFrame(book("e1", "A Aces", "E Eagles", when, -3.5, -3.5)         # model: A by 20ish -> read
                        + book("e2", "B Bees", "C Cats", when, -2.5, -4.5)          # FanDuel lags the sharp line
                        + book("e3", "Syracuse Orange", "D Dogs", when, -1.5, -1.5)  # New York college
                        + book("e4", "F Foxes", "D Dogs", when, -1.5, -1.5)         # played in New York
                        + book("e5", "C Cats", "E Eagles", when, -1.5, -1.5)        # venue unknown
                        + book("e6", "D Dogs", "B Bees", when, -1.5, -1.5)          # not on the schedule
                        + book("e7", "A Aces", "C Cats", when, -9.5, -9.5))         # neutral, feeds swap home
    sched = pd.DataFrame({"game_id": ["g1", "g2", "g3", "g4", "g5", "g7"],
                          "home_team": ["A", "B", "Syracuse", "F", "C", "C"],
                          "away_team": ["E", "C", "D", "D", "E", "A"], "date": pd.Timestamp("2026-01-09"),
                          "neutral": [False, False, False, True, False, True],
                          "state": ["NC", "TX", "NY", "NY", None, "NV"]})
    names = {"A Aces": "A", "E Eagles": "E", "B Bees": "B", "C Cats": "C", "Syracuse Orange": "Syracuse",
             "D Dogs": "D", "F Foxes": "F"}
    offers, reads, notes = C.price(snap, pd.Timestamp("2026-01-09T12:00:00Z"), data=(sched, tg, names))
    assert set(offers["event_id"]) == {"e1", "e2", "e7"}            # New York games and unknown venues skipped
    assert set(offers.loc[offers["event_id"] == "e7", "game_ref"]) == {"g7"}
    assert any("skipped 2 under New York rules" in n for n in notes)
    assert any("skipped 2 with no confirmed venue" in n for n in notes)
    assert (offers["w_model"] == 0).all() and set(offers["league"]) == {"ncaab"}
    lag = offers[(offers["event_id"] == "e2") & (offers["market"] == "spreads")].set_index("side")
    assert lag.loc["B", "p_market"] > 0.5 and lag.loc["B", "ev"] > 0.03   # FanDuel -2.5 vs a -4.5 market
    reads = [r for r in reads if r.get("kind", "spread") == "spread"]   # totals reads are tracked too (Oct 12)
    assert reads[0]["event_id"] == "e1" and reads[0]["side"] == "A" and reads[0]["gap"] >= C.READ_MIN
    assert "e2" not in {r["event_id"] for r in reads}


def test_reads_grade_with_clv_and_result(tmp_path, monkeypatch):
    monkeypatch.setattr(ncaab_reads, "PATH", tmp_path / "ncaab_reads.csv")
    read = {"event_id": "e1", "game_id": "g1", "commence_time": "2026-01-10T00:00:00Z", "matchup": "E @ A",
            "home": "A", "away": "E", "side": "A", "line": -3.5, "price": -110, "home_line": -3.5,
            "model_margin": 12.0, "market_center": 4.0, "gap": 8.5}
    swapped = read | {"event_id": "e2", "game_id": "g2", "matchup": "C @ B (neutral)", "home": "B", "away": "C",
                      "side": "B", "line": 2.5, "home_line": 2.5}   # CBBD lists this neutral game as B @ C
    assert ncaab_reads.record([read, swapped], pd.Timestamp("2026-01-09T12:00:00Z")) == 2
    games = pd.DataFrame({"game_id": ["g1", "g2"], "home_team": ["A", "C"], "away_team": ["E", "B"],
                          "date": pd.Timestamp("2026-01-09"),
                          "margin": [7.0, -4.0], "spread_line": [5.5, 1.0]})   # A -5.5, won by 7; C -1, B won by 4
    assert ncaab_reads.grade(games, pd.Timestamp("2026-01-11T00:00:00Z")) == 2
    r = ncaab_reads.load().set_index("read_id")
    assert r.at["e1", "result"] == "won" and float(r.at["e1", "clv_pts"]) == 2.0 and float(r.at["e1", "close_line"]) == -5.5
    assert r.at["e2", "result"] == "won" and float(r.at["e2", "close_line"]) == 1.0 and float(r.at["e2", "clv_pts"]) == 1.5
    assert ncaab_reads.summary()["avg_clv_pts"] == 1.75


def test_ncaab_picks_settle_with_closing_value():
    picks = pd.DataFrame([
        {"league": "ncaab", "status": "open", "game_ref": "g1", "market": "spreads", "side": "A", "point": -3.5,
         "price": -110.0, "units_flat": 1.0, "commence_time": "2026-01-10T00:00:00Z"},
        {"league": "ncaab", "status": "open", "game_ref": "g1", "market": "totals", "side": "Under", "point": 150.5,
         "price": -110.0, "units_flat": 1.0, "commence_time": "2026-01-10T00:00:00Z"}])
    games = pd.DataFrame({"game_id": ["g1"], "home_team": ["A"], "margin": [7.0], "total": [141.0],
                          "spread_line": [5.5], "total_line": [146.5], "home_moneyline": [np.nan],
                          "away_moneyline": [np.nan]})
    out = grading.grade_ncaab(picks, games, pd.Timestamp("2026-01-11T00:00:00Z"))
    assert list(out["status"]) == ["won", "won"]
    assert out.loc[0, "clv"] > 0 and out.loc[1, "clv"] > 0          # closed -5.5 and 146.5: both beat


# ---------------------------------------------------------------- roster change (early-season ratings)
def test_roster_value_follows_players_and_transfers():
    players = pd.DataFrame({"season": 2025, "team": ["X", "X", "Y"], "player_id": ["p1", "p2", "p3"],
                            "games": [30, 30, 30], "minutes": [900, 300, 800], "porpag": [4.0, 1.0, 2.0]})
    roster = pd.DataFrame({"season": 2026, "team": ["X", "Y", "Y", "Y"], "player_id": ["p2", "p3", "p1", "fresh"]})
    v = M.roster_value(players, roster, 2026)
    assert v.loc["X", "dval"] == -4.0 and v.loc["X", "ret_min"] == 0.25      # lost its best player
    assert v.loc["Y", "dval"] == 4.0 and v.loc["Y", "ret_min"] == 1.0        # gained him; the freshman counts 0
    assert M.roster_dval(players, roster, 2026) == {"X": -4.0}               # all of Y's minutes back: a stale list


def test_freshmen_add_their_expected_value_by_recruit_rating():
    """Oct 20: freshmen counted 0, so teams built on top recruits looked weaker in November than they were. A class's
    expected first-season value comes from its recruits' ratings (FRESHMAN_BANDS); only the class of season - 1."""
    players = pd.DataFrame({"season": 2025, "team": ["X", "X"], "player_id": ["p1", "p2"],
                            "games": [30, 30], "minutes": [900, 300], "porpag": [4.0, 1.0]})
    roster = pd.DataFrame({"season": 2026, "team": ["X"], "player_id": ["p2"]})
    recruits = pd.DataFrame({"year": [2025, 2025, 2024, 2025], "name": ["A", "B", "Old", "C"],
                             "team": ["X", "X", "X", None], "rating": [0.9990, 0.92, 0.9999, 0.99]})
    assert M.freshman_value(0.9990) == 1.95 and M.freshman_value(0.92) == 0.40 and M.freshman_value(None) == 0.24
    assert M.freshmen(recruits, 2026) == {"X": pytest.approx(2.35)}        # last year's class and the uncommitted: no
    v = M.roster_value(players, roster, 2026, recruits)
    assert v.loc["X", "val_fresh"] == pytest.approx(2.35) and v.loc["X", "dval"] == pytest.approx(-4.0 + 2.35)
    assert M.roster_value(players, roster, 2026).loc["X", "dval"] == -4.0   # without recruits: as before


def test_roster_shift_fades_and_needs_both_teams():
    dval = {"X": -4.0, "Y": 4.0}
    first = M.roster_shift(dval, "Y", "X", 0)
    assert first == M.ROSTER_BETA * 8 and M.roster_shift(dval, "X", "Y", 0) == -first
    assert 0 < M.roster_shift(dval, "Y", "X", 60) < first / 2                # fades as games come in
    assert M.roster_shift(dval, "Y", "Z", 0) == 0.0                          # unknown team: no shift
    assert M.season_day("2025-11-01", 2026) == 0 and M.season_day(pd.Timestamp("2026-01-01T03:00Z"), 2026) == 60


def test_card_applies_the_roster_shift():
    tg = toy()
    when = "2026-01-10T00:00:00Z"
    snap = pd.DataFrame(book("e1", "A Aces", "E Eagles", when, -3.5, -3.5))
    sched = pd.DataFrame({"game_id": ["g1"], "home_team": ["A"], "away_team": ["E"], "date": pd.Timestamp("2026-01-09"),
                          "neutral": [False], "state": ["NC"]})
    names = {"A Aces": "A", "E Eagles": "E"}
    asof = pd.Timestamp("2026-01-09T12:00:00Z")
    base = C.price(snap, asof, data=(sched, tg, names))
    shifted = C.price(snap, asof, data=(sched, tg, names, {"A": -20.0, "E": 0.0}))
    assert any("no rosters saved" in n for n in base[2]) and not any("no rosters" in n for n in shifted[2])
    want = M.ROSTER_BETA * np.exp(-69 / M.ROSTER_TAU) * -20.0
    assert abs(shifted[1][0]["roster_shift"] - want) < 0.01                  # stored to 2 decimals
    assert abs(shifted[1][0]["model_margin"] - (base[1][0]["model_margin"] + want)) < 0.01
    assert "roster change" in shifted[0]["model_number"].iloc[0]


def test_free_draftkings_lines_give_reads_but_no_offers():
    tg = toy()
    when = "2026-01-10T00:00:00Z"
    snap = pd.DataFrame(book("e1", "A Aces", "E Eagles", when, -3.5, -3.5))
    snap = snap[snap["bookmaker"] == "fanduel"].assign(bookmaker="draftkings")   # ESPN's free feed: one book
    sched = pd.DataFrame({"game_id": ["g1"], "home_team": ["A"], "away_team": ["E"], "date": pd.Timestamp("2026-01-09"),
                          "neutral": [False], "state": ["NC"]})
    offers, reads, _ = C.price(snap, pd.Timestamp("2026-01-09T12:00:00Z"), data=(sched, tg, {"A Aces": "A", "E Eagles": "E"}))
    assert offers.empty                                             # no FanDuel price, no sharp book: nothing to bet
    reads = [r for r in reads if r.get("kind", "spread") == "spread"]   # totals reads are tracked too (Oct 12)
    assert len(reads) == 1 and reads[0]["book"] == "draftkings" and reads[0]["market_center"] == 3.5


def test_every_book_is_priced_and_the_better_one_wins():
    """Oct 30: the card priced FanDuel only, so a better DraftKings or Novig number never reached it."""
    from betlab import books
    from betlab.cards import ncaab as C
    tg = toy()
    when = "2026-01-10T00:00:00Z"
    rows = book("e2", "B Bees", "C Cats", when, -4.5, -4.5)
    rows += [r | {"bookmaker": "draftkings"}
             for r in rows if r["bookmaker"] == "fanduel" and r["market"] == "spreads"]
    for r in rows:                                     # DraftKings hangs B -3.5: a point better than the market
        if r["bookmaker"] == "draftkings":
            r["point"] = -3.5 if r["outcome"] == "B Bees" else 3.5
    rows += [r | {"bookmaker": "novig", "price": -105, "bet_limit": 20.0}
             for r in rows if r["bookmaker"] == "fanduel" and r["market"] == "spreads"]
    snap = pd.DataFrame(rows)
    sched = pd.DataFrame({"game_id": ["g2"], "home_team": ["B"], "away_team": ["C"], "date": pd.Timestamp("2026-01-09"),
                          "neutral": [False], "state": ["TX"]})
    offers, _, _ = C.price(snap, pd.Timestamp("2026-01-09T12:00:00Z"), data=(sched, tg, {"B Bees": "B", "C Cats": "C"}))
    assert set(offers["book"]) == {"fanduel", "draftkings", "novig"}
    assert offers.loc[offers["book"] == "novig", "bet_limit"].eq(20.0).all()
    best = books.select(offers).set_index("side")
    assert best.loc["B", "book"] == "draftkings" and best.loc["B", "point"] == -3.5
    assert best.loc["C", "book"] == "fanduel"          # Novig's -105 has only $20 behind it: never the pick


def test_week_one_unmatched_names_now_match():
    import pandas as pd

    from betlab.sources import cbbd

    t = pd.DataFrame({"school": ["Purdue Fort Wayne", "George Washington"], "mascot": ["Mastodons", "Revolutionaries"],
                      "display": ["Purdue Fort Wayne Mastodons", "George Washington Revolutionaries"], "conference": ["Horizon", "A-10"]})
    names = cbbd.team_names(t, feed_names=["Fort Wayne Mastodons", "GW Revolutionaries"])
    assert names["Fort Wayne Mastodons"] == "Purdue Fort Wayne" and names["GW Revolutionaries"] == "George Washington"
