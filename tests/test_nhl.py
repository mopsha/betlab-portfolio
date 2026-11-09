"""NHL: ESPN odds parsing, the score grid, the model's inputs, the tracker (all offline)."""

import numpy as np
import pandas as pd
import pytest

from betlab import tracking_nhl
from betlab.models import nhl as M
from betlab.sources import nhl as src

PICKCENTER = {
    "provider": {"name": "DraftKings"},
    "moneyline": {"home": {"close": {"odds": "+105"}, "open": {"odds": "-115"}},
                  "away": {"close": {"odds": "-125"}, "open": {"odds": "-105"}}},
    "pointSpread": {"home": {"close": {"line": "+1.5", "odds": "-245"}}, "away": {"close": {"line": "-1.5", "odds": "+200"}}},
    "total": {"over": {"close": {"line": "o6.5", "odds": "-102"}, "open": {"line": "o6.5", "odds": "+105"}},
              "under": {"close": {"line": "u6.5", "odds": "-118"}, "open": {"line": "u6.5", "odds": "-125"}}},
}


def test_odds_row_reads_open_and_close():
    r = src._odds_row(PICKCENTER)
    assert r["book"] == "DraftKings"
    assert (r["ml_home_open"], r["ml_home_close"], r["ml_away_close"]) == (-115, 105, -125)
    assert (r["total_close"], r["over_close"], r["under_close"], r["over_open"]) == (6.5, -102, -118, 105)
    assert (r["pl_home_close"], r["pl_home_close_price"]) == (1.5, -245)
    assert src._am("EVEN") == 100 and src._am("OFF") is None and src._am("-5") is None


def test_odds_row_falls_back_to_flat_fields():
    r = src._odds_row({"homeTeamOdds": {"moneyLine": -148}, "awayTeamOdds": {"moneyLine": 124},
                       "overUnder": 6.5, "overOdds": 110, "underOdds": -130})
    assert (r["ml_home_close"], r["ml_away_close"], r["total_close"], r["over_close"]) == (-148, 124, 6.5, 110)


def test_grid_is_a_distribution():
    p = M.Params()
    g = M.grid(3.2, 2.8, p)
    assert abs(sum(g["totals"].values()) - 1) < 1e-9 and abs(sum(g["margins"].values()) - 1) < 1e-9
    assert 0.5 < g["p_home"] < 0.65
    assert 0 not in g["margins"]                       # someone always wins
    over, push = M.p_over(g, 6.5)
    assert push == 0 and 0.3 < over < 0.7
    # Home -1.5 needs a 2+ goal win, so it's less likely than winning at all.
    assert M.p_cover(g, -1.5) < g["p_home"]
    # Equal teams: overtime is a coin flip and the win chance is 50%.
    even = M.grid(3.0, 3.0, p)
    assert abs(even["p_home"] - 0.5) < 1e-9


def test_team_games_removes_empty_net_and_shootout_goals():
    raw = pd.DataFrame({
        "game_id": [1, 1], "season": [2026, 2026], "date": pd.to_datetime(["2025-10-08"] * 2),
        "team": ["AAA", "BBB"], "opp": ["BBB", "AAA"], "home": [1, 0],
        "gf": [4.0, 3.0], "ga": [3.0, 4.0], "sf": [30.0, 25.0], "sa": [25.0, 30.0],
        "cf": [50.0, 45.0], "ca": [45.0, 50.0], "ff": [40.0, 35.0], "fa": [35.0, 40.0],
        "en_goals": [0.0, 0.0], "win": [1, 0], "so_win": [1, 0], "reg_win": [0, 0],
        "extra": [1, 1], "shootout": [1, 1], "gf_play": [3.0, 3.0], "ga_play": [3.0, 3.0],
    })
    t = M.team_games(raw)
    assert list(t["goals"]) == [3.0, 3.0]              # the shootout "goal" isn't a goal


def _tracker_row(**kw):
    base = {"game_id": "2026020006", "espn_id": "401891821", "start": "2026-10-01T23:00:00Z", "home": "PHI",
            "away": "PIT", "book": "DraftKings", "ml_home": -148.0, "ml_away": 124.0, "total": 6.5, "over": 110.0,
            "under": -130.0, "p_mkt": 0.577, "p_model": 0.53, "p_over_mkt": 0.45, "p_over_model": 0.43,
            "home_goalie": "Dan Vladar", "away_goalie": "Arturs Silovs", "home_goalie_status": "probable",
            "away_goalie_status": "confirmed", "home_xg": 3.0, "away_xg": 2.8, "exp_total": 6.1}
    return base | kw


def test_tracker_keeps_first_look_and_grades(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking_nhl, "PATH", tmp_path / "nhl_lines.csv")
    t0 = pd.Timestamp("2026-10-01T14:00:00Z")
    assert tracking_nhl.record([_tracker_row()], t0) == 1
    assert tracking_nhl.record([_tracker_row(ml_home=-160.0, home_goalie_status="confirmed")], t0 + pd.Timedelta(hours=4)) == 1
    df = tracking_nhl.load()
    assert len(df) == 1 and df["first_ml_home"].iloc[0] == -148 and df["last_ml_home"].iloc[0] == -160
    tg = pd.DataFrame({"game_id": [2026020006], "home": [1], "gf": [2.0], "ga": [3.0], "win": [0], "extra": [0]})
    closes = {"401891821": {"ml_home_close": -160.0, "ml_away_close": 135.0, "total_close": 6.5,
                            "over_close": 105.0, "under_close": -125.0}}
    n = tracking_nhl.grade(team_games=tg, closes=closes, now=pd.Timestamp("2026-10-02T12:00:00Z"), read_min=0.04)
    assert n == 1
    g = tracking_nhl.load().iloc[0]
    assert g["read_side"] == "PIT" and int(g["read_won"]) == 1           # model liked PIT by 4.7 pts; PIT won
    assert float(g["read_clv"]) < 0                                     # +124 when PIT closed +135: the line went against us
    s = tracking_nhl.summary()
    assert s["graded"] == 1 and s["reads"]["n"] == 1


CODES = {"pittsburgh penguins": "PIT", "philadelphia flyers": "PHI", "st louis blues": "STL", "montreal canadiens": "MTL"}


def _snap(ts="2026-10-01T20:00:00Z", fd_home=-120, pin_home=-140, fd_total=(6.5, -105, -115), pin_total=(6.5, -110, -110)):
    rows = []
    base = {"sport_key": "icehockey_nhl", "event_id": "ev1", "commence_time": "2026-10-01T23:00:00Z",
            "home_team": "Philadelphia Flyers", "away_team": "Pittsburgh Penguins", "player": None, "snapshot_ts": ts}
    for bk, ml_h, tot in (("fanduel", fd_home, fd_total), ("pinnacle", pin_home, pin_total)):
        ml_a = 100 if bk == "fanduel" else (120 if ml_h <= -140 else 110)   # Pinnacle's tight two-way price
        rows += [base | {"bookmaker": bk, "market": "h2h", "outcome": "Philadelphia Flyers", "point": None, "price": ml_h},
                 base | {"bookmaker": bk, "market": "h2h", "outcome": "Pittsburgh Penguins", "point": None, "price": ml_a},
                 base | {"bookmaker": bk, "market": "totals", "outcome": "Over", "point": tot[0], "price": tot[1]},
                 base | {"bookmaker": bk, "market": "totals", "outcome": "Under", "point": tot[0], "price": tot[2]},
                 base | {"bookmaker": bk, "market": "spreads", "outcome": "Philadelphia Flyers", "point": -1.5, "price": 190},
                 base | {"bookmaker": bk, "market": "spreads", "outcome": "Pittsburgh Penguins", "point": 1.5, "price": -230}]
    return pd.DataFrame(rows)


def test_names_match_the_feed():
    assert src.code_for("St Louis Blues", CODES) == "STL" and src.code_for("Montréal Canadiens", CODES) == "MTL"
    assert src.code_for("Nobody Nowhere", CODES) is None


def test_card_prices_fanduel_against_pinnacle():
    from betlab.cards import nhl as card

    sched = pd.DataFrame({"game_id": [2026020010], "start": ["2026-10-01T23:00:00Z"], "home": ["PHI"], "away": ["PIT"]})
    offers = card.evaluate(_snap(), pd.Timestamp("2026-10-01T14:00:00Z"), sched=sched, codes=CODES)
    ml = offers[offers["market"] == "h2h"].set_index("side")
    assert set(offers["market"]) == {"h2h", "totals", "spreads"} and (offers["w_model"] == 0).all()
    assert ml.loc["PHI", "ev"] > 0 > ml.loc["PIT", "ev"]          # FanDuel -120 on a -140 favorite
    assert set(offers["game_ref"]) == {"2026020010"} and offers["matchup"].iloc[0] == "PIT @ PHI"
    # A sharp total at a different number is skipped, not guessed.
    off2 = card.evaluate(_snap(pin_total=(5.5, -130, 110)), pd.Timestamp("2026-10-01T14:00:00Z"), sched=sched, codes=CODES)
    assert "totals" not in set(off2["market"])


def test_grade_nhl_settles_and_measures_clv(monkeypatch):
    from betlab import grading
    from betlab.cards import nhl as card

    monkeypatch.setattr(src, "team_codes", lambda: CODES)
    sched = pd.DataFrame({"game_id": [2026020010], "start": ["2026-10-01T23:00:00Z"], "home": ["PHI"], "away": ["PIT"]})
    offers = card.evaluate(_snap(), pd.Timestamp("2026-10-01T14:00:00Z"), sched=sched, codes=CODES)
    pick = offers[(offers["market"] == "h2h") & (offers["side"] == "PHI")].assign(status="open", units_flat=1.0)
    tg = pd.DataFrame({"game_id": [2026020010], "home": [1], "team": ["PHI"], "opp": ["PIT"],
                       "date": [pd.Timestamp("2026-10-01")], "gf": [4.0], "ga": [2.0]})
    close = _snap(ts="2026-10-01T22:30:00Z", pin_home=-160)       # the market moved further toward PHI
    out = grading.grade_nhl(pick, team_games=tg, now=pd.Timestamp("2026-10-02T12:00:00Z"), snaps=[_snap(), close])
    r = out.iloc[0]
    assert r["status"] == "won" and r["profit_flat"] > 0 and r["clv"] > 0


def test_grade_nhl_reads_start_times_with_and_without_seconds(monkeypatch):
    """Oct 1: NHL prop leans carry "2026-10-02T01:30Z" (no seconds) beside the odds feed's
    "...:00Z", and pandas refused the mix, so the whole grading step crashed."""
    from betlab import grading
    from betlab.cards import nhl as card

    monkeypatch.setattr(src, "team_codes", lambda: CODES)
    sched = pd.DataFrame({"game_id": [2026020010], "start": ["2026-10-01T23:00:00Z"], "home": ["PHI"], "away": ["PIT"]})
    offers = card.evaluate(_snap(), pd.Timestamp("2026-10-01T14:00:00Z"), sched=sched, codes=CODES)
    pick = offers[(offers["market"] == "h2h") & (offers["side"] == "PHI")].assign(status="open", units_flat=1.0)
    pick = pd.concat([pick.assign(commence_time="2026-10-01T23:00:00Z"),
                      pick.assign(commence_time="2026-10-01T23:00Z")], ignore_index=True)
    tg = pd.DataFrame({"game_id": [2026020010], "home": [1], "team": ["PHI"], "opp": ["PIT"],
                       "date": [pd.Timestamp("2026-10-01")], "gf": [4.0], "ga": [2.0]})
    out = grading.grade_nhl(pick, team_games=tg, now=pd.Timestamp("2026-10-02T12:00:00Z"), snaps=[_snap()])
    assert list(out["status"]) == ["won", "won"]


def test_fun_ticket_and_shots_overs(monkeypatch):
    from betlab.cards import fun_nhl
    from betlab.cards import nhl as card
    from betlab import config

    monkeypatch.setattr(src, "team_codes", lambda: CODES | {"new york rangers": "NYR", "boston bruins": "BOS"})
    monkeypatch.setattr(card, "_game_ids", lambda asof: pd.DataFrame(
        {"game_id": [11, 12], "start": ["2026-10-01T23:00:00Z", "2026-10-01T23:30:00Z"], "home": ["PHI", "BOS"], "away": ["PIT", "NYR"]}))
    a = _snap()
    b = _snap().assign(event_id="ev2", commence_time="2026-10-01T23:30:00Z",
                       home_team=lambda d: d["home_team"].str.replace("Philadelphia Flyers", "Boston Bruins"),
                       away_team=lambda d: d["away_team"].str.replace("Pittsburgh Penguins", "New York Rangers"))
    b["outcome"] = b["outcome"].replace({"Philadelphia Flyers": "Boston Bruins", "Pittsburgh Penguins": "New York Rangers"})
    snap = pd.concat([a, b], ignore_index=True)
    prop = lambda bk, side, price, player="Sidney Crosby", eid="ev1": {
        "event_id": eid, "commence_time": "2026-10-01T23:00:00Z", "home_team": "Philadelphia Flyers",
        "away_team": "Pittsburgh Penguins", "bookmaker": bk, "market": "player_shots_on_goal", "outcome": side,
        "player": player, "point": 2.5, "price": price, "snapshot_ts": "2026-10-01T14:00:00Z", "sport_key": "icehockey_nhl"}
    props = pd.DataFrame([prop("fanduel", "Over", 110), prop("fanduel", "Under", -140),
                          prop("betmgm", "Over", -105), prop("betmgm", "Under", -115)])
    cfg = config.settings()["fun"]["nhl"] | {"band": [100, 5000]}
    slates = fun_nhl.build(snap, props, pd.Timestamp("2026-10-01T14:00:00Z"), cfg)
    assert len(slates) == 1 and slates[0]["sport"] == "nhl"
    t = slates[0]["plus"]
    assert t and t["n_games"] == 2 and {g["game_ref"] for g in t["games"]} == {"11", "12"}
    assert all(leg["side"] != "under" for leg in t["legs"])
    o = slates[0]["overs"][0]
    assert o["label"] == "Sidney Crosby over 2.5 shots" and o["ev"] > 0 and o["games"][0]["game_ref"] == "11"


def test_a_shootout_winner_gets_the_goal_books_credit(monkeypatch):
    raw = pd.DataFrame({"gameId": [9, 9, 8, 8], "teamId": [1, 2, 1, 2], "opponentTeamAbbrev": ["EDM", "NJD", "EDM", "NJD"],
                        "gameDate": ["2026-11-03"] * 4, "homeRoad": ["H", "R", "H", "R"], "goalsFor": [3, 3, 4, 2],
                        "goalsAgainst": [3, 3, 2, 4], "shotsForPerGame": [30] * 4, "shotsAgainstPerGame": [30] * 4,
                        "satFor": [50] * 4, "satAgainst": [50] * 4, "usatFor": [40] * 4, "usatAgainst": [40] * 4,
                        "emptyNetGoals": [0] * 4, "wins": [1, 0, 1, 0], "winsInShootout": [1, 0, 0, 0],
                        "winsInRegulation": [0, 0, 1, 0]})
    monkeypatch.setattr(src, "_cached", lambda *a, **k: raw)
    tg = src.load_team_games([2027]).set_index(["game_id", "team"])
    so, reg = tg.loc[(9, "NJD")], tg.loc[(8, "NJD")]
    assert (so["gf"], so["ga"], so["gf_play"], so["ga_play"]) == (4, 3, 3, 3)      # Nov 3: NJD beat EDM in the shootout
    assert (tg.loc[(9, "EDM"), "gf"], tg.loc[(9, "EDM"), "ga"], tg.loc[(9, "EDM"), "gf_play"]) == (3, 4, 3)
    assert (reg["gf"], reg["ga"], reg["gf_play"]) == (4, 2, 4)                      # a regulation game is untouched


def test_a_slips_full_team_names_settle_too():
    from betlab.fun_ledger import settle_nhl

    assert settle_nhl("New York Rangers ML", "NYR", "STL", 4, 2) == ("won", 2.0)      # Nov 3's slip stayed open for good
    assert settle_nhl("St. Louis Blues ML", "NYR", "STL", 4, 2) == ("lost", -2.0)
    assert settle_nhl("New York Rangers -1.5", "NYR", "STL", 4, 2)[0] == "won"
    assert settle_nhl("St. Louis Blues +1.5", "NYR", "STL", 4, 2)[0] == "lost"
    assert settle_nhl("NYR ML", "NYR", "STL", 4, 2)[0] == "won"
    assert settle_nhl("New York Islanders ML", "NYR", "STL", 4, 2) == ("unknown", None)   # a team not in this game
    assert settle_nhl("Sidney Crosby over 2.5 shots", "NYR", "STL", 4, 2)[0] == "unknown"  # no box yet, not a team


def test_nhl_legs_settle_like_the_books():
    from betlab.fun_ledger import settle_nhl

    shots = pd.DataFrame({"plain": ["sidney crosby"], "shots": [4.0]})
    assert settle_nhl("PHI to win", "PHI", "PIT", 3, 2)[0] == "won"
    assert settle_nhl("PHI -1.5", "PHI", "PIT", 3, 2)[0] == "lost"
    assert settle_nhl("PIT +1.5", "PHI", "PIT", 3, 2)[0] == "won"
    assert settle_nhl("Over 5.5 goals", "PHI", "PIT", 3, 3)[0] == "won"
    assert settle_nhl("Sidney Crosby over 2.5 shots", "PHI", "PIT", 3, 2, shots) == ("won", 4.0)
    assert settle_nhl("Somebody Else over 2.5 shots", "PHI", "PIT", 3, 2, shots)[0] == "void"
    assert settle_nhl("Under 5.5 goals", "PHI", "PIT", 3, 2)[0] == "won"
    assert settle_nhl("Sidney Crosby under 4.5 shots", "PHI", "PIT", 3, 2, shots)[0] == "won"
    box = pd.DataFrame({"plain": ["dan vladar"], "saves": [31.0]})
    assert settle_nhl("Dan Vladar over 27.5 saves", "PHI", "PIT", 3, 2, box) == ("won", 31.0)


def test_soccer_builder_legs_settle():
    from betlab.fun_ledger import settle_soccer

    assert settle_soccer("Draw", "A", "B", 1, 1) == "won"
    assert settle_soccer("B or draw", "A", "B", 1, 1) == "won" and settle_soccer("A or draw", "A", "B", 0, 1) == "lost"
    assert settle_soccer("Under 2.5 goals", "A", "B", 1, 1) == "won"
    assert settle_soccer("Both teams to score: no", "A", "B", 2, 0) == "won"


def test_props_features_use_only_earlier_games():
    from betlab.models import props_nhl as P

    rows = []
    for k, shots in enumerate([1, 3, 5]):
        rows.append({"game_id": 100 + k, "season": 2026, "date": pd.Timestamp("2025-10-01") + pd.Timedelta(days=2 * k),
                     "player_id": 1, "player": "A B", "pos": "C", "team": "AAA", "opp": "BBB", "home": 1,
                     "toi": 1200.0, "ev_toi": 1000.0, "pp_toi": 200.0, "sh_toi": 0.0, "shots": float(shots),
                     "goals": 0.0, "assists": 0.0, "points": 0.0, "pp_points": 0.0})
    f = P.features(pd.DataFrame(rows))
    assert np.isnan(f["shots60_l"].iloc[0])                     # first game: no history
    assert f["shots60_s"].iloc[1] == 3.0                        # 1 shot in 20 minutes = 3 per 60
    assert f["games_prior"].tolist() == [0, 1, 2]


def test_consensus_moves_other_books_to_fanduels_number():
    from betlab.cards import props_nhl as PN

    g = pd.DataFrame([
        {"bookmaker": "fanduel", "outcome": "Over", "point": 2.5, "price": -120},
        {"bookmaker": "fanduel", "outcome": "Under", "point": 2.5, "price": -110},
        {"bookmaker": "draftkings", "outcome": "Over", "point": 2.5, "price": 150},
        {"bookmaker": "draftkings", "outcome": "Under", "point": 2.5, "price": -200},
        {"bookmaker": "betmgm", "outcome": "Over", "point": 3.5, "price": 120},
        {"bookmaker": "betmgm", "outcome": "Under", "point": 3.5, "price": -150}])
    assert PN._consensus(g, 2.5)[0] is None                    # a different number is skipped; DraftKings never counts
    p, n = PN._consensus(g, 2.5, size=21.0)
    assert n == 1 and 0.5 < p < 0.75                            # over 2.5 is likelier than BetMGM's over 3.5 (~42%)


def test_coverage_table_parses_for_the_markets_tab():
    from betlab.cli import coverage_doc

    d = coverage_doc()
    assert d and d["updated"] and d["columns"][0] == "Market" and len(d["rows"]) >= 6
    assert all(len(r) == len(d["columns"]) for r in d["rows"])
    assert any(r[0] == "NHL" for r in d["rows"]) and d["key"]


def test_coverage_table_comes_from_the_data_repo_on_the_worker(tmp_path, monkeypatch):
    """The worker's image has no docs/: the table must come from the repo clone its data lives in (Oct 14)."""
    from betlab import cli, config

    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "COVERAGE.md").write_text("Last updated: 2026-10-14\n\n| Market | Analysis: game lines |\n|---|---|\n| NBA | ✓ |\n",
                                               encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", repo / "data")
    monkeypatch.setattr(config, "ROOT", tmp_path / "app")        # the image: code only
    d = cli.coverage_doc()
    assert d["updated"] == "2026-10-14" and d["rows"] == [["NBA", "✓"]]


def test_nhl_prop_close_must_come_after_the_pick_was_logged():
    """Oct 13: 32 of 52 graded NHL prop leans were 'closed' against the pull they were logged from, so their CLV
    was just their EV. Only a later pull (the pre-game closing look) counts."""
    from betlab import grading

    pick = pd.Series({"event_id": "e1", "game_ref": "2026020001", "market": "player_shots_on_goal", "player": "A Skater",
                      "side": "Over", "point": 2.5, "price": 120, "units_flat": 1.0,
                      "created_at": "2026-10-01T23:00:30+00:00", "commence_time": "2026-10-01T23:30:00Z"})
    box = (pd.DataFrame({"plain": ["a skater"], "shots": [4.0]}), pd.DataFrame())

    def snap(ts, over, under):
        return pd.DataFrame([{"event_id": "e1", "market": "player_shots_on_goal", "player": "A Skater", "bookmaker": b,
                              "outcome": o, "point": 2.5, "price": p, "snapshot_ts": ts}
                             for b in ("pinnacle", "betmgm") for o, p in (("Over", over), ("Under", under))])

    same = snap("2026-10-01T23:00:00+00:00", 100, -120)            # the pull the pick came from
    out = grading._grade_nhl_prop(pd.DataFrame([pick]), 0, pick, {"2026020001": box}, snaps=[same])
    assert out.at[0, "status"] == "won" and ("clv" not in out or pd.isna(out.at[0, "clv"]))
    later = snap("2026-10-01T23:10:00+00:00", -130, 110)            # the closing look
    out = grading._grade_nhl_prop(pd.DataFrame([pick]), 0, pick, {"2026020001": box}, snaps=[same, later])
    assert out.at[0, "clv"] > 0


def test_nhl_pieces_reuse_a_leg_at_most_twice():
    """Oct 19: a game's pieces are the ticket's alternatives, so one leg (say the favorite's win) fills at most 2."""
    import numpy as np
    from betlab.cards import fun_nhl

    final = np.zeros((10, 10))
    final[4, 1] = 0.35   # a big home favorite in a high-scoring game: the win, -1.5 and the over all move together
    final[3, 2] = 0.25
    final[2, 1] = 0.15
    final[1, 3] = 0.15
    final[2, 2] = 0.10
    fd = {("ml", "BOS"): -200, ("ml", "NYR"): 170, ("pl", "BOS", -1.5): 130, ("pl", "NYR", 1.5): -150,
          ("total", 5.5): -110}
    legs = fun_nhl.legs(final, "BOS", "NYR", fd)
    cfg = {"leg_p": [0.40, 0.80], "pair_lift": 1.0, "pair_min_p": 0.3, "minis_per_game": 3}
    pieces = fun_nhl.minis(legs, final, cfg, "ev1")
    counts = {}
    for p in pieces:
        for leg in p["legs"]:
            counts[leg["label"]] = counts.get(leg["label"], 0) + 1
    assert pieces and max(counts.values()) <= 2


def test_summary_compares_the_model_and_market_on_the_same_games():
    """Oct 20: the model's log loss over all 135 graded games sat beside the first look's over 32 (DraftKings-via-ESPN
    games have no first market chance), so the model looked better than the market when on the same games it wasn't."""
    df = pd.DataFrame({"status": "graded", "home_win": [1, 0, 1], "first_p_model": [0.6, 0.4, 0.9],
                       "first_p_mkt": [0.55, None, None], "p_close": [0.58, 0.45, 0.5], "read_side": None})
    s = tracking_nhl.summary(df)
    assert s["vs_first_look"]["n"] == 1 and s["vs_close"]["n"] == 3
    assert s["vs_first_look"]["model"] == pytest.approx(-np.log(0.6), abs=1e-4)   # game 1 only, not all three


def test_tracker_first_look_waits_for_a_price(tmp_path, monkeypatch):
    # Oct 12 - Nov 1: a game seen before it had a line kept an empty first look, so it could never have a read
    monkeypatch.setattr(tracking_nhl, "PATH", tmp_path / "nhl_lines.csv")
    t0 = pd.Timestamp("2026-10-01T14:00:00Z")
    none = {c: None for c in ("ml_home", "ml_away", "total", "over", "under", "p_mkt", "p_over_mkt", "book")}
    tracking_nhl.record([_tracker_row(**none)], t0)
    tracking_nhl.record([_tracker_row(ml_home=-160.0, p_mkt=0.6)], t0 + pd.Timedelta(hours=4))
    tracking_nhl.record([_tracker_row(ml_home=-170.0, p_mkt=0.62)], t0 + pd.Timedelta(hours=5))
    r = tracking_nhl.load().iloc[0]
    assert r["first_ml_home"] == -160 and r["first_p_mkt"] == 0.6 and r["book"] == "DraftKings"
    assert r["last_ml_home"] == -170 and r["first_seen"].startswith("2026-10-01T18")


def test_settle_nhl_reads_every_slip_wording_of_a_player_prop():
    """Nov 4: only "over 2.5 shots" settled; a screenshot's "3+ shots" or "1+ goals" held a winning slip open for good."""
    from betlab.fun_ledger import settle_nhl

    box = pd.DataFrame({"plain": ["sidney crosby"], "shots": [4.0], "goals": [1.0], "assists": [0.0], "points": [1.0],
                        "saves": [float("nan")]})
    for label, want in [("Sidney Crosby 3+ shots", "won"), ("Sidney Crosby 5+ shots", "lost"),
                        ("Sidney Crosby over 2.5 shots on goal", "won"), ("Sidney Crosby under 2.5 shots", "lost"),
                        ("Sidney Crosby 1+ goals", "won"), ("Sidney Crosby anytime goalscorer", "won"),
                        ("Sidney Crosby over 0.5 assists", "lost"), ("Sidney Crosby 1+ points", "won"),
                        ("Sidney Crosby over 4 shots", "push"), ("Somebody Else 1+ goals", "void"),
                        ("Sidney Crosby over 20.5 saves", "void")]:
        assert settle_nhl(label, "PIT", "PHI", 3, 2, box)[0] == want, label
    assert settle_nhl("Sidney Crosby 1+ goals", "PIT", "PHI", 3, 2)[0] == "unknown"     # no box yet


def test_settle_nhl_reads_a_total_however_a_slip_words_it():
    from betlab.fun_ledger import settle_nhl

    for label in ("Over 4.5 goals", "Over 4.5 total goals", "Over 4.5", "over 4.5 goals"):
        assert settle_nhl(label, "PIT", "PHI", 3, 2)[0] == "won", label
    assert settle_nhl("Under 5 goals", "PIT", "PHI", 3, 2)[0] == "push"


def test_grade_nhl_fetches_the_box_for_a_slip_prop():
    from betlab import fun_ledger

    games = pd.DataFrame({"game_id": [11], "home": [1], "team": ["PIT"], "opp": ["PHI"], "gf": [3.0], "ga": [2.0]})
    box = pd.DataFrame({"plain": ["sidney crosby"], "goals": [1.0]})
    df = pd.DataFrame([{**{c: None for c in fun_ledger.COLUMNS}, "sgp_id": "x", "sport": "nhl", "legs": '["Sidney Crosby 1+ goals"]',
                        "leg_games": '["nhl:11"]', "game_id": "nhl:11", "status": "open", "price": 150.0, "marked": False}])
    assert fun_ledger._grade_nhl(df, df, games, lambda gid: box) == 1 and df.at[0, "status"] == "won"
