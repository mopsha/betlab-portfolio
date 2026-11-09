"""The daily soccer SGP+ ticket (cards/fun_soccer.py) and how its legs settle (fun_ledger)."""

import json

import numpy as np
import pandas as pd
import pytest

from betlab import fun_ledger
from betlab.cards import fun_soccer as F
from betlab.models import soccer as S

CFG = {"leg_p": [0.45, 0.85], "pair_lift": 1.05, "pair_min_p": 0.3, "minis_per_game": 3, "band": [400, 3000],
       "min_games": 3, "max_games": 5, "max_legs": 8, "pool_games": 12, "max_fit_error": 0.03}


def market_from(lh, la):
    sm = S.score_matrix(lh, la)
    i, j = np.indices(sm.shape)
    return {"h": sm[i > j].sum(), "d": sm[i == j].sum(), "a": sm[i < j].sum(),
            "overs": {2.5: sm[i + j > 2.5].sum(), 3.5: sm[i + j > 3.5].sum()}, "fd": [-150, 280, 400]}


def test_the_score_grid_is_fit_back_to_the_market():
    lh, la, err = F.fit_goals(market_from(1.9, 0.9))
    assert lh == pytest.approx(1.9, abs=0.02) and la == pytest.approx(0.9, abs=0.02) and err < 0.001


def test_legs_move_together_and_a_winner_with_goals_comes_first():
    sm = S.score_matrix(1.9, 0.9)
    legs = F.legs(sm, "Home FC", "Away FC", [-150, 280, 400])
    by = {l["label"]: l for l in legs}
    assert by["Home FC to win"]["price"] == -150 and by["Over 2.5 goals"]["price"] is None
    assert by["Over 1.5 goals"]["p"] > by["Over 2.5 goals"]["p"] > by["Over 3.5 goals"]["p"]
    pieces = F.minis(legs, sm, CFG, "e1")
    first = [l["label"] for l in pieces[0]["legs"]]
    assert "Home FC to win" in first and len(first) == 2 and pieces[0]["lift"] >= 1.05
    for m in pieces:                                   # never two goals lines, never both teams to win
        stats = [l["stat"] for l in m["legs"]]
        assert len(stats) == len(set(stats))


def snapshot(home=1.2):
    rows, rng = [], np.random.default_rng(1)
    for k in range(4):
        lh, la = home + 0.25 * k, 1.1
        t = market_from(lh, la)
        base = {"event_id": f"e{k}", "commence_time": pd.Timestamp("2026-10-10T14:00:00Z") + pd.Timedelta(minutes=10 * k),   # one kickoff cluster (slices, Oct 13)
                "home_team": f"Home{k}", "away_team": f"Away{k}", "sport_key": "soccer_epl",
                "snapshot_ts": "2026-10-10T08:00:00Z"}
        for book, margin in (("pinnacle", 1.02), ("fanduel", 1.07)):
            for outcome, p in ((f"Home{k}", t["h"]), ("Draw", t["d"]), (f"Away{k}", t["a"])):
                dec = 1 / (p * margin)
                rows.append(base | {"bookmaker": book, "market": "h2h", "outcome": outcome, "point": None,
                                    "price": (dec - 1) * 100 if dec >= 2 else -100 / (dec - 1)})
        for line, p in t["overs"].items():
            for outcome, q in (("Over", p), ("Under", 1 - p)):
                dec = 1 / (q * 1.02)
                rows.append(base | {"bookmaker": "pinnacle", "market": "totals", "outcome": outcome, "point": line,
                                    "price": (dec - 1) * 100 if dec >= 2 else -100 / (dec - 1)})
    return pd.DataFrame(rows)


def test_one_ticket_a_day_with_real_fanduel_prices_only():
    slates = F.build({"epl": snapshot()}, pd.Timestamp("2026-10-10T10:00:00Z"), CFG)
    assert len(slates) == 1 and slates[0]["sport"] == "soccer"
    t = slates[0]["plus"]
    assert t is not None and t["sport"] == "soccer" and t["naive_price"] is None and 3 <= t["n_games"] <= 5
    for leg in t["legs"]:
        assert "_price" not in leg
        assert (leg["price"] is None) == (leg["stat"] != "moneyline")     # goals legs have no FanDuel price
    assert all(g["game_ref"].startswith("epl|Home") for g in t["games"])


def test_conference_league_matches_join_a_ticket_on_winners_only():
    """Its goals and shots aren't in FanDuel's or DraftKings' feed, so those legs could never get a link (Nov 5: 7 of 8)."""
    asof, cfg = pd.Timestamp("2026-10-10T10:00:00Z"), CFG | {"band": [100, 3000], "min_games": 1}
    t = F.build({"uecl": snapshot(home=2.2)}, asof, cfg)[0]["plus"]
    assert t is not None and {leg["stat"] for leg in t["legs"]} == {"moneyline"}
    assert all(leg["price"] is not None for leg in t["legs"])
    assert {leg["stat"] for leg in F.build({"uel": snapshot(home=2.2)}, asof, cfg)[0]["plus"]["legs"]} - {"moneyline"}


def test_conference_league_gets_its_own_ticket_and_the_lock_alert_names_it():
    from betlab import alerts
    asof, cfg = pd.Timestamp("2026-10-10T10:00:00Z"), CFG | {"band": [100, 3000], "min_games": 1}
    uel, uecl = snapshot(home=2.2), snapshot(home=2.2)
    uecl["event_id"] = "c" + uecl["event_id"]
    for col in ("home_team", "away_team", "outcome"):
        uecl[col] = uecl[col].str.replace(r"^(Home|Away)", r"Cup\1", regex=True)
    s = F.build({"uel": uel, "uecl": uecl}, asof, cfg)[0]
    assert {g["event_id"] for g in s["plus"]["games"]} <= {f"e{k}" for k in range(4)} and "cup" not in s["plus"]
    assert {g["event_id"] for g in s["plus_short"]["games"]} <= {f"ce{k}" for k in range(4)}
    assert s["plus_short"]["cup"] == "Conference League" and "(Conference League)" in s["plus_short"]["matchup"]
    assert "Conference League: " in alerts.lock_message(s | {"locked_at": "x"})["body"]


def test_a_slice_with_no_ticket_keeps_its_build_packs():
    slate = F.build({"uecl": snapshot()}, pd.Timestamp("2026-10-10T10:00:00Z"), CFG)[0]      # even matches: no winner in the band
    assert slate["plus"] is None and len(slate["packs"]) == 4 and slate["kickoff"]


def test_stale_or_far_off_snapshots_build_nothing():
    # Sep 28: a Sep 25 EPL snapshot priced Oct 10 matches and left empty slates on the page
    assert F.build({"epl": snapshot()}, pd.Timestamp("2026-10-12T10:00:00Z"), CFG) == []      # 2 days old
    far = snapshot().assign(snapshot_ts="2026-10-07T08:00:00Z")
    assert F.build({"epl": far}, pd.Timestamp("2026-10-07T09:00:00Z"), CFG) == []            # matches 3 days out


def test_soccer_legs_settle_from_the_final_score():
    assert fun_ledger.settle_soccer("Home FC to win", "Home FC", "Away FC", 2, 1) == "won"
    assert fun_ledger.settle_soccer("Away FC to win", "Home FC", "Away FC", 2, 1) == "lost"
    assert fun_ledger.settle_soccer("Both teams to score", "Home FC", "Away FC", 2, 0) == "lost"
    assert fun_ledger.settle_soccer("Over 2.5 goals", "Home FC", "Away FC", 2, 1) == "won"
    assert fun_ledger.settle_soccer("Draw", "Home FC", "Away FC", 1, 1) == "won"            # a builder leg since Sep 30
    assert fun_ledger.settle_soccer("Corner kicks", "Home FC", "Away FC", 1, 1) == "unknown"


def test_a_soccer_ticket_waits_for_every_result_then_grades():
    refs = ["epl|Home FC|Away FC|2026-10-10T14:00:00+00:00", "epl|B|C|2026-10-10T16:30:00+00:00"]
    df = pd.DataFrame([{**{c: None for c in fun_ledger.COLUMNS}, "sgp_id": "plus-x", "sport": "soccer", "status": "open",
                        "legs": json.dumps(["Home FC to win", "Over 1.5 goals"]), "leg_games": json.dumps(refs),
                        "game_id": refs[0], "price": 250.0, "marked": False}])
    scores = {"Home FC": {"hg": 2, "ag": 0}}
    lookup = lambda lg, h, a, k: scores.get(h)
    assert fun_ledger._grade_soccer(df, df, lookup) == 0 and df.at[0, "status"] == "open"
    scores["B"] = {"hg": 1, "ag": 1}
    assert fun_ledger._grade_soccer(df, df, lookup) == 1
    assert df.at[0, "status"] == "won" and df.at[0, "profit_1u"] == pytest.approx(2.5)


def test_goals_lines_pull_each_ticket_match_once(monkeypatch, tmp_path):
    """The ticket's matches get FanDuel's goals ladder and btts (2 credits each) once; the pre-game
    rebuilds of the same ticket pull nothing (Oct 10)."""
    import pandas as pd

    from betlab import cli, config
    from betlab.sources import odds_api

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    calls = []

    class Client:
        def event_odds(self, key, eid, markets):
            calls.append((key, eid, markets))
            return {"id": eid, "commence_time": "2026-10-11T00:30:00Z", "home_team": "H", "away_team": "A",
                    "bookmakers": [{"key": "fanduel", "markets": [{"key": "btts", "outcomes": [
                        {"name": "Yes", "price": -150, "link": "https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=2"}]}]}]}

        def balance_note(self):
            return "n/a"

    monkeypatch.setattr(odds_api, "OddsApiClient", Client)
    monkeypatch.setattr(odds_api, "any_key", lambda: True)
    snap = pd.DataFrame({"event_id": ["m1", "m2", "x9"]})
    slates = [{"plus": {"games": [{"event_id": "m1"}, {"event_id": "m2"}]}}]
    now = pd.Timestamp("2026-10-10T15:00:00Z")
    cli._soccer_goals_lines(slates, {"mls": snap}, now)
    assert sorted(c[1] for c in calls) == ["m1", "m2"]
    assert calls[0][2] == ("alternate_totals", "btts")
    cli._soccer_goals_lines(slates, {"mls": snap}, now)          # a pre-game rebuild: nothing new
    assert len(calls) == 2
    saved = cli.latest_snapshot(config.settings()["leagues"]["mls"]["sport_key"], "goals")
    assert set(saved["event_id"]) == {"m1", "m2"}


def _lines():
    """Props tracker rows for match e1: a starter the model likes more than the market, one it likes
    less, a bench player, and a rung outside the band."""
    base = {"event_id": "e1", "stat": "shots", "starter": "True", "fd_price": -150.0, "last_fd_price": -140.0,
            "p_fd_fair": 0.62, "team": "Home1"}
    return pd.DataFrame([base | {"player": "Liked Striker", "line": 1.5, "p_market": 0.55, "p_model": 0.63},
                         base | {"player": "Doubted Winger", "line": 1.5, "p_market": 0.60, "p_model": 0.48},
                         base | {"player": "Bench Forward", "line": 1.5, "p_market": 0.55, "p_model": 0.70, "starter": "nan"},
                         base | {"player": "Liked Striker", "line": 3.5, "p_market": 0.15, "p_model": 0.25},
                         base | {"player": "Keeper Only FD", "line": 0.5, "stat": "sot", "p_market": None,
                                 "p_fd_fair": 0.40, "p_model": 0.42}])


def test_shot_rungs_only_where_the_model_agrees_with_the_market():
    """Oct 10 (Mike: shot overs in the soccer tickets): starters only, the fair chance in the band, and the
    model at least the fair chance, never a fake over. Fair is BetRivers', else FanDuel's own margin off."""
    r = F.shot_rungs(_lines(), "e1", (0.35, 0.80))
    assert {x["label"] for x in r} == {"Liked Striker 2+ shots", "Keeper Only FD 1+ shots on target"}
    assert r[0]["player"] == "Liked Striker"                       # the model's biggest agreement first (+8 pts)
    striker = [x for x in r if x["player"] == "Liked Striker"][0]
    assert striker["p"] == 0.55 and striker["price"] == -140.0 and striker["source"] == "BetRivers' ladder"
    assert [x for x in r if x["player"] == "Keeper Only FD"][0]["source"] == "FanDuel's ladder, margin off"
    m = F.shot_minis(r, "e1")
    assert all(x["n_legs"] == 1 and x["legs"][0]["_price"] == x["legs"][0]["price"] for x in m)


def test_a_slice_gets_shot_overs_and_shot_legs_stand_alone_in_the_ticket():
    slates = F.build({"epl": snapshot()}, pd.Timestamp("2026-10-10T10:00:00Z"), CFG | {"over_p": [0.35, 0.8]}, _lines())
    s = slates[0]
    assert {o["label"] for o in s["overs"]} == {"Liked Striker 2+ shots", "Keeper Only FD 1+ shots on target"}
    o = [o for o in s["overs"] if o["player"] == "Liked Striker"][0]
    assert o["kind"] == "over" and o["p_model"] == 0.63 and o["games"][0]["event_id"] == "e1"
    for g in s["plus"]["games"]:                        # a match with a shot leg has nothing else on the ticket
        stats = {l["stat"] for l in g["legs"]}
        assert not (stats & {"shots", "sot"}) or len(g["legs"]) == 1


def test_shot_legs_settle_from_espn():
    ref = "epl|Home FC|Away FC|2026-10-10T14:00:00+00:00"
    df = pd.DataFrame([{**{c: None for c in fun_ledger.COLUMNS}, "sgp_id": "plus-s", "sport": "soccer", "status": "open",
                        "legs": json.dumps(["Home FC to win", "Liked Striker 2+ shots"]), "leg_games": json.dumps([ref, ref]),
                        "game_id": ref, "price": 300.0, "marked": False}])
    lookup = lambda lg, h, a, k: {"hg": 2, "ag": 0}
    state = {"v": ("open", None)}
    shots = lambda lg, h, a, k, player, stat: state["v"]
    assert fun_ledger._grade_soccer(df, df, lookup, shots) == 0                      # ESPN not final yet
    state["v"] = ("ok", 3.0)
    assert fun_ledger._grade_soccer(df, df, lookup, shots) == 1 and df.at[0, "status"] == "won"
    df.at[0, "status"] = "open"
    state["v"] = ("ok", 1.0)
    fun_ledger._grade_soccer(df, df, lookup, shots)
    assert df.at[0, "status"] == "lost"


def test_a_primetime_match_is_its_own_slice_with_a_parlay_priced_on_its_grid():
    """El Clásico as a prime-time game (Mike, Oct 25): its own slice, and 2-3 legs priced together on its grid."""
    from betlab import sgp_plus
    assert sgp_plus.slice_of("2026-10-25T20:00:00Z", "soccer", "Barcelona", "Real Madrid") == ("2026-10-25", "prime")
    assert sgp_plus.slice_of("2026-10-25T20:00:00Z", "soccer", "Real Madrid", "Barcelona") == ("2026-10-25", "prime")
    assert sgp_plus.slice_of("2026-10-25T19:45:00Z", "soccer", "Udinese", "AC Milan") == ("2026-10-25", "three")
    n = sgp_plus.slice_names("soccer", "2026-10-25", "prime", 1, "2026-10-25T20:00:00Z", feature="El Clásico")
    assert n["slate"] == "2026-10-25-soccer-prime" and n["title"] == "El Clásico · 4 PM"
    slate = {"slate": "2026-10-25-soccer-prime", "sport": "soccer", "kickoff": "2026-10-25T20:00:00Z"}
    assert sgp_plus.lock_due([slate], pd.Timestamp("2026-10-25T19:36:00Z")) == ["2026-10-25-soccer-prime"]   # it locks
    sm = S.score_matrix(1.6, 1.3)
    minis = F.prime_minis(F.legs(sm, "Barcelona", "Real Madrid", None), sm,
                                   {"band_primetime": [150, 1500]}, "e1")
    assert minis and all(2 <= m["n_legs"] <= 3 for m in minis)
    for m in minis:
        stats = [l["stat"] for l in m["legs"]]
        assert stats.count("goals") <= 1 and stats.count("moneyline") <= 1
        assert 1 / (1 + 1500 / 100) <= m["p_fair"] <= 1 / (1 + 150 / 100)


def test_an_anytime_goalscorer_settles_from_espn_goals():
    """Oct 25: "Lamine Yamal anytime goalscorer" from a slip reads as 1+ goals, from ESPN's player line."""
    ref = "la_liga|Barcelona|Real Madrid|2026-10-25T20:00:00+00:00"
    df = pd.DataFrame([{**{c: None for c in fun_ledger.COLUMNS}, "sgp_id": "custom-fd-snap-g", "sport": "soccer", "status": "open",
                        "legs": json.dumps(["Lamine Yamal anytime goalscorer"]), "leg_games": json.dumps([ref]),
                        "game_id": ref, "price": 110.0, "marked": False}])
    asked = []
    def shots(lg, h, a, k, player, stat):
        asked.append((player, stat))
        return ("ok", 1.0)
    assert fun_ledger._grade_soccer(df, df, lambda *a: {"hg": 2, "ag": 1}, shots) == 1
    assert asked == [("Lamine Yamal", "goals")] and df.at[0, "status"] == "won"


def _totals_rows(book, point, over=-110, under=-110):
    return [{"market": "totals", "bookmaker": book, "point": point, "outcome": o, "price": q, "name": o}
            for o, q in (("Over", over), ("Under", under))]


def _h2h_rows(book="pinnacle"):
    return [{"market": "h2h", "bookmaker": book, "point": None, "outcome": n, "price": q, "name": n}
            for n, q in (("Home FC", -300), ("Draw", 500), ("Away FC", 800))]


def test_a_high_scoring_games_only_sharp_line_anchors_the_grid():
    far = pd.DataFrame(_h2h_rows() + _totals_rows("lowvig", 4.5, 115, -135) + _totals_rows("pinnacle", 4.25))
    t = F.targets(far, "Home FC", "Away FC")
    assert list(t["overs"]) == [4.5]                       # Barcelona-Aston Villa, Nov 3: 4.5 and 4.25, no pack at all
    lh, la, err = F.fit_goals(t)
    assert err < 0.03 and lh + la > 3
    assert all(l["label"] != "Over 4.5 goals" for l in F.legs(S.score_matrix(lh, la), "Home FC", "Away FC", None))   # never a leg


def test_a_nearer_line_keeps_4_5_out_of_the_fit():
    both = pd.DataFrame(_h2h_rows() + _totals_rows("lowvig", 4.5) + _totals_rows("pinnacle", 3.5))
    assert list(F.targets(both, "Home FC", "Away FC")["overs"]) == [3.5]


def test_quarter_lines_alone_still_anchor_nothing():
    assert not F.targets(pd.DataFrame(_h2h_rows() + _totals_rows("pinnacle", 3.25)), "Home FC", "Away FC")["overs"]



def test_settle_soccer_reads_a_slip_s_wording():
    """Nov 4: a slip's own wording stayed "unknown", holding a winning slip open for good."""
    s = fun_ledger.settle_soccer
    for label, want in [("Arsenal ML", "won"), ("Arsenal or Draw", "won"), ("Slavia Praha or draw", "lost"), ("Over 2.5 total goals", "won"),
                        ("Under 2.5", "lost"), ("Over 3 goals", "push"), ("BTTS", "won"), ("Both teams to score: yes", "won"),
                        ("Both Teams To Score", "won"), ("Both teams to score: no", "lost"), ("draw", "lost"),
                        ("Arsenal -1.5", "lost"), ("Arsenal -0.5", "won"), ("Arsenal -1", "push"), ("Slavia Praha +1.5", "won"),
                        ("Arsenal -0.75", "unknown"), ("Chelsea to win", "unknown")]:
        assert s(label, "Arsenal", "Slavia Praha", 2, 1) == want, label


def test_settle_soccer_reads_espn_s_name_for_a_book_s_club():
    s = fun_ledger.settle_soccer
    assert s("Stade Rennais to win", "Rennes", "Nice", 2, 1) == "won"            # one way through CLUB_ALIASES
    assert s("Rennes to win", "Stade Rennais", "Nice", 2, 1) == "won"            # and the other
    assert s("Paris Saint-Germain to win", "Paris Saint Germain", "Barcelona", 1, 2) == "lost"
    assert s("Manchester to win", "Manchester City", "Manchester United", 2, 1) == "unknown"     # names either: names neither


def test_grade_soccer_settles_score_or_assist_and_over_under_props():
    def run(legs, shots):
        refs = ["epl|Home FC|Away FC|2026-11-01T15:00:00Z"] * len(legs)
        df = pd.DataFrame([{**{c: None for c in fun_ledger.COLUMNS}, "sgp_id": "x", "sport": "soccer", "legs": json.dumps(legs),
                            "leg_games": json.dumps(refs), "game_id": refs[0], "status": "open", "price": 150.0, "marked": False}])
        fun_ledger._grade_soccer(df, df, lambda *a: {"hg": 2, "ag": 1}, shots)
        return df.at[0, "status"], json.loads(df.at[0, "leg_results"]) if isinstance(df.at[0, "leg_results"], str) else None

    line = {"goals": 0.0, "assists": 1.0, "shots": 3.0, "sot": 1.0}
    played = lambda l, h, a, k, p, stat: ("ok", line[stat])                     # noqa: E731
    assert run(["Bukayo Saka to score or assist"], played)[0] == "won"
    assert run(["Bukayo Saka over 2.5 shots"], played)[0] == "won"
    assert run(["Bukayo Saka under 0.5 shots on target"], played)[0] == "lost"
    assert run(["Bukayo Saka to score or assist"], lambda *a: ("open", None))[0] == "open"
    line.update(goals=0.0, assists=0.0)
    assert run(["Bukayo Saka to score or assist"], played)[0] == "lost"
