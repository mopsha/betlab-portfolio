"""NBA fun tickets: the copula simulator, alt-rung legs, the window's slate, grading and the page docs."""

import json

import numpy as np
import pandas as pd
import pytest
from scipy import stats as st

from betlab import alerts, fun_ledger, sgp_plus
from betlab.cards import fun_nba
from betlab.cards import fun_nba as F
from betlab.models import game_sim_nba as G
from betlab.reports import nba as R

TIP = pd.Timestamp("2026-03-04T00:00:00Z")


def players(team_a="NY", team_b="OKC"):
    rows = []
    for team, names in ((team_a, ("A1", "A2", "A3")), (team_b, ("B1", "B2", "B3"))):
        for k, name in enumerate(names):
            for stat, mu in (("points", 22 - 5 * k), ("rebounds", 7 - k), ("assists", 5 - k), ("threes", 2.5 - 0.5 * k)):
                rows.append({"player": name, "team": team, "stat": stat, "mu": mu, "r": 12.0})
    return pd.DataFrame(rows)


def test_copula_keeps_each_market_mean_and_the_measured_links():
    sim = G.simulate(players(), "NY", "OKC", 4.0, 225.0, n=40000, seed=1)
    assert sim.get("A1", "points").mean() == pytest.approx(22, rel=0.02)
    assert (sim.get("A1", "pra") == sim.get("A1", "points") + sim.get("A1", "rebounds") + sim.get("A1", "assists")).all()
    rank = lambda x: st.norm.ppf((st.rankdata(x) - 0.5) / len(x))
    rho = lambda a, b: np.corrcoef(rank(a), rank(b))[0, 1]
    assert rho(sim.get("A1", "points"), sim.get("A1", "threes")) == pytest.approx(0.60, abs=0.06)   # discrete: a bit lower
    total = sim.points["NY"] + sim.points["OKC"]
    assert total.mean() == pytest.approx(225, abs=0.5) and total.std() == pytest.approx(G.TOTAL_SD, rel=0.03)
    assert rho(sim.get("A1", "points"), total) == pytest.approx(0.15, abs=0.03)
    margin = sim.points["NY"] - sim.points["OKC"]
    assert rho(sim.get("B1", "points"), margin) < -0.07          # the other team's scorer goes with NY losing
    c = G.correlation(players(), "NY")
    assert np.allclose(np.diag(c), 1) and np.linalg.eigvalsh(c).min() > 0


def tracker_rows():
    out = []
    for p in players().itertuples():
        line = float(np.floor(p.mu) + 0.5)
        out.append({"event_id": "ev1", "tipoff": TIP.isoformat(), "matchup": "Oklahoma City Thunder @ New York Knicks",
                    "player": p.player, "team": p.team, "stat": p.stat, "line": line, "fd_over": -110, "fd_under": -110,
                    "p_market": 0.5, "p_model": 0.52, "mu": p.mu, "min_proj": 32.0, "questionable": p.player == "A3",
                    "market_source": "pinnacle", "home": "NY", "away": "OKC", "home_name": "New York Knicks",
                    "away_name": "Oklahoma City Thunder", "disp": 12.0})
    return out


def pick_snap():
    rows = []
    for book in ("pinnacle", "fanduel"):
        for oc, pt in (("New York Knicks", -4.0), ("Oklahoma City Thunder", 4.0)):
            rows.append({"event_id": "ev1", "home_team": "New York Knicks", "away_team": "Oklahoma City Thunder",
                         "commence_time": TIP.isoformat(), "bookmaker": book, "market": "spreads", "outcome": oc,
                         "point": pt, "price": -110})
        for oc in ("Over", "Under"):
            rows.append({"event_id": "ev1", "home_team": "New York Knicks", "away_team": "Oklahoma City Thunder",
                         "commence_time": TIP.isoformat(), "bookmaker": book, "market": "totals", "outcome": oc,
                         "point": 225.0, "price": -110})
    return pd.DataFrame(rows)


def alt_snap():
    rows = []
    for player, rung, fd, dk in (("A1", 17.5, -230, -300), ("B1", 17.5, -230, None), ("A2", 3.5, -250, -240)):
        for book, price in (("fanduel", fd), ("draftkings", dk)):
            if price is not None:
                rows.append({"event_id": "ev1", "bookmaker": book, "market": "player_points_alternate" if rung > 10
                             else "player_assists_alternate", "outcome": "Over", "player": player, "point": rung, "price": price})
    return pd.DataFrame(rows)


def test_alt_rungs_are_capped_by_other_books_and_uncapped_ones_by_the_players_ratio():
    rows = pd.DataFrame(tracker_rows())
    sim = G.simulate(F.game_inputs(rows), "NY", "OKC", 4.0, 225.0, n=20000)
    w = np.full(sim.n, 1 / sim.n)
    legs = {l.label: l for l in F.alt_legs(alt_snap(), sim, w, rows)}
    a1 = legs["A1 18+ points"]
    assert a1.p <= a1.p_model and a1.source == "draftkings"
    assert a1.p == pytest.approx(min(a1.p_model, (300 / 400) / 1.07), abs=1e-6)       # DK -300 shrunk by 7%
    assert legs["B1 18+ points"].source == "model shape"                                # no other book: model's shape
    assert legs["A2 4+ assists"].team == "NY"


# the NFL's slip settings (config/settings.yaml fun:) plus the NBA ticket's (fun.nba)
FUN = {"band": [150, 1000], "min_legs": 4, "max_legs": 5, "per_game": 5, "min_leg_p": 0.55, "max_leg_p": 0.80,
       "under_min_p": 0.75, "under_max_p": 0.92, "max_unders": 1, "one_leg_per_player": True, "sims": 8000,
       "longshot": {"band": [1500, 6000], "min_legs": 2, "max_legs": 4, "min_leg_p": 0.12},
       "nba": {"band": [100, 4000], "min_games": 2, "max_games": 4, "max_legs": 10, "mini_legs": [2, 3],
               "mini_band": [1, 400], "max_unders_mini": 0, "minis_per_game": 3, "over_p": [0.3, 0.8],
               "overs_per_game": 3, "overs_per_slate": 6, "min_pair_lift": 1.0, "min_leg_p": 0.45}}


def test_a_games_own_slips_ride_on_its_slate_lock_and_alert_its_watchers():
    """Oct 19 (Mike: "count them like primetime games"): a lone game's own same-game slips lock, alert, publish and
    grade like the NFL's prime-time slips. Since Nov 7 every game's do, and an account sees and hears of the ones for
    the games it watches."""
    from betlab import alerts, sgp_plus

    # the fixture is thin (three players with a leg at 55-80%), so the slips here take 3+ legs down to 35%
    fun = FUN | {"min_legs": 3, "min_leg_p": 0.35, "band": [100, 2000]}
    slates = F.build(tracker_rows(), pick_snap(), fun, {}, alt_snap())
    assert len(slates) == 1
    s = slates[0]
    assert s["plus"] is None and s["n_games"] == 1 and s["sgps"]
    labels = [{l["label"] for l in x["legs"]} for x in s["sgps"]]
    assert len({frozenset(x) for x in labels}) == len(labels)                        # no two slips alike
    for x in s["sgps"]:
        assert x["sport"] == "nba" and x["games"][0]["game_ref"] == "nba|NY|OKC|2026-03-04T00:00:00+00:00"
        assert x["games"][0]["legs"] == [l["label"] for l in x["legs"]]
    # Nov 7 (Mike: "locks on a sgp shouldn't depend on slices at all"): the slips lock at their own game's lock time
    tip = pd.Timestamp(s["sgps"][0]["commence_time"])
    preview = sgp_plus.keep_tickets([s], [], tip - pd.Timedelta(minutes=40), sports=("nba",))
    assert not any(x.get("locked_at") for x in preview[0]["sgps"])
    locked = sgp_plus.keep_tickets([s], preview, tip - pd.Timedelta(minutes=20), sports=("nba",))
    assert all(x.get("locked_at") for x in locked[0]["sgps"])
    msg = alerts.slips_message(alerts.slip_locks(locked, set(), tip - pd.Timedelta(minutes=20))[s["sgps"][0]["event_id"]])
    assert msg["title"] == "Locked: Thunder @ Knicks slips" and "Tip-off 7:00 PM ET" in msg["body"]
    # a later build can't change them
    rebuilt = sgp_plus.keep_tickets([s | {"sgps": []}], locked, tip - pd.Timedelta(minutes=2), sports=("nba",))
    assert rebuilt[0]["sgps"] == locked[0]["sgps"]


def test_slips_lock_by_their_own_game_not_their_slice():
    """Nov 7: a 7:00 tip leads a slice with an 8:40 game; the slice's ticket locks at 6:35, the 8:40 game's slips at 8:15."""
    def slip(eid, start, sid):
        return {"sgp_id": sid, "event_id": eid, "commence_time": start, "matchup": "A @ B", "sport": "nba"}
    new = [{"slate": "d-nba-early", "sport": "nba", "kickoff": "2026-11-08T00:00:00Z", "plus": {"sgp_id": "p1"},
            "sgps": [slip("e1", "2026-11-08T00:00:00Z", "a1"), slip("e3", "2026-11-08T01:40:00Z", "c1")]}]
    at = lambda hhmm: pd.Timestamp(f"2026-11-08T{hhmm}:00Z")
    first = sgp_plus.keep_tickets(new, [], pd.Timestamp("2026-11-07T23:36:00Z"))[0]
    assert first["locked_at"] and [bool(x.get("locked_at")) for x in first["sgps"]] == [True, False]
    newer = [new[0] | {"plus": {"sgp_id": "p2"}, "sgps": [slip("e3", "2026-11-08T01:40:00Z", "c2")]}]   # e1 has begun
    second = sgp_plus.keep_tickets(newer, [first], at("00:30"))[0]
    assert second["plus"]["sgp_id"] == "p1"                                    # the ticket kept its lock
    assert [x["sgp_id"] for x in second["sgps"]] == ["c2", "a1"]               # e3 still follows the builds
    assert not second["sgps"][0].get("locked_at") and second["sgps"][1]["locked_at"]
    third = sgp_plus.keep_tickets(newer, [second], at("01:16"))[0]
    assert {x["sgp_id"]: bool(x.get("locked_at")) for x in third["sgps"]} == {"c2": True, "a1": True}


def test_lone_game_slips_use_the_nbas_pair_lift(monkeypatch):
    """Oct 20: the lone-game search ran at search's NFL default (1.10), which NBA pairs across players rarely reach,
    so the 3 PM opener showed only its long shot."""
    from betlab import sgp

    seen = []
    monkeypatch.setattr(sgp, "search", lambda *a, **k: seen.append(k["min_pair_lift"]) or [])
    F.game_slips([], np.ones(1), FUN | {"nba": FUN["nba"] | {"min_pair_lift": 1.03}}, {})
    assert seen == [1.03, 1.03]                     # the value slips and the long shot


def test_a_window_slate_with_a_ticket_national_tv_overs_and_game_refs():
    fun = FUN | {"nba": FUN["nba"] | {"min_games": 1}}     # a one-game ticket, so the slate's ticket is testable
    slates = F.build(tracker_rows(), pick_snap(), fun, {("NY", "OKC"): ["ESPN"]}, alt_snap())
    assert len(slates) == 1
    s = slates[0]
    assert s["sport"] == "nba" and s["overs"] and s["slate"].startswith("2026-03-03-nba-")
    game = F.build_game(pd.DataFrame(tracker_rows()), pick_snap(), fun, {}, ev=alt_snap())
    assert game["game_ref"] == "nba|NY|OKC|2026-03-04T00:00:00+00:00" and game["overs"] == []   # overs only on national TV
    assert game["minis"], "the game should offer pieces for the window's ticket"


def test_nba_legs_parse_and_grade_from_box_scores():
    assert fun_ledger.parse_nba_leg("Josh Hart 5+ assists")["point"] == 4.5
    assert fun_ledger.parse_nba_leg("Jalen Brunson over 32.5 pts + reb + ast")["parts"] == ("points", "rebounds", "assists")
    assert fun_ledger.parse_nba_leg("New York Knicks ML")["stat"] == "moneyline"
    ref = "nba|NY|OKC|2026-03-04T00:00:00+00:00"
    sch = pd.DataFrame([{"game_id": 9, "home_abbreviation": "NY", "away_abbreviation": "OKC", "home_display_name": "New York Knicks",
                         "away_display_name": "Oklahoma City Thunder", "start_date": "2026-03-04T00:00Z", "home_score": 110,
                         "away_score": 104, "status_type_completed": True}])
    box = pd.DataFrame([{"game_id": 9, "athlete_id": 1, "athlete_display_name": "Josh Hart", "minutes": "36", "points": 12,
                         "rebounds": 9, "assists": 7, "three_point_field_goals_made": 1, "game_date": "2026-03-03"},
                        {"game_id": 9, "athlete_id": 2, "athlete_display_name": "Mitchell Robinson", "minutes": "0", "points": 0,
                         "rebounds": 0, "assists": 0, "three_point_field_goals_made": 0, "game_date": "2026-03-03"}])
    legs = ["Josh Hart 5+ assists", "New York Knicks ML", "Over 210.5 total points", "Mitchell Robinson 8+ rebounds"]
    df = pd.DataFrame([{**{c: None for c in fun_ledger.COLUMNS}, "sgp_id": "plus-n", "sport": "nba", "status": "open",
                        "legs": json.dumps(legs), "leg_games": json.dumps([ref] * 4), "game_id": ref, "price": 300.0, "marked": False}])
    assert fun_ledger._grade_nba(df, df, box=box, sch=sch) == 1
    res = {x["leg"]: x["result"] for x in json.loads(df.at[0, "leg_results"])}
    assert res == {"Josh Hart 5+ assists": "won", "New York Knicks ML": "won", "Over 210.5 total points": "won",
                   "Mitchell Robinson 8+ rebounds": "void"}
    assert df.at[0, "status"] == "void"                       # a leg on a player who didn't play: check the app


def test_the_page_docs_merge_across_the_nights_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(R.config, "EXPORTS_DIR", tmp_path)
    rows = tracker_rows()
    R.write(rows, [{"slate": "s1", "kickoff": TIP.isoformat()}], {"ev1": (4.0, 225.0)}, {("NY", "OKC"): ["ESPN"]}, TIP - pd.Timedelta(hours=1))
    later = [r | {"event_id": "ev2", "tipoff": (TIP + pd.Timedelta(hours=3)).isoformat()} for r in rows]
    R.write(later, [{"slate": "s2", "kickoff": later[0]["tipoff"]}], {}, {}, TIP + pd.Timedelta(hours=2))
    view = json.loads((tmp_path / "nba.json").read_text())
    assert [g["event_id"] for g in view["games"]] == ["ev1", "ev2"] and view["games"][0]["national_tv"] == ["ESPN"]
    assert view["games"][0]["lines"][0]["gap"] == pytest.approx(0.02)
    fun = json.loads((tmp_path / "fun_nba.json").read_text())
    assert [s["slate"] for s in fun["slates"]] == ["s1", "s2"]
    R.write([], [], {}, {}, TIP + pd.Timedelta(hours=20))       # the next day: last night's games drop off
    assert json.loads((tmp_path / "nba.json").read_text())["games"] == []


def test_every_game_keeps_its_slips_and_a_slice_gets_a_likelier_ticket():
    """Oct 21 (Mike): "just want a mix": next to the regular SGP+ a likelier one in the short band, from the games the
    regular one left out when it can. Every game's own slips ride along (Nov 7: watched games, no Knicks rule; their
    legs can still sit on the SGP+ tickets)."""
    from betlab.cards import fun_nba

    def mini(eid, p):
        return {"sgp_id": f"m-{eid}-{p}", "n_legs": 2, "p_fair": p, "fair_price": 0, "leg_value": 1.0, "theme": "",
                "legs": [{"label": f"{eid} leg {p}", "price": -150}, {"label": f"{eid} leg2 {p}", "price": -150}]}

    tip = "2026-10-21T23:00:00+00:00"
    game = lambda eid, home, p: {"event_id": eid, "matchup": eid, "commence_time": tip, "game_ref": f"nba|{home}|X|{tip}",
                                 "minis": [mini(eid, p)], "overs": [],
                                 "sgps": [{"sgp_id": f"s-{eid}", "matchup": eid, "legs": [{"label": "x"}, {"label": "y"}]}]}
    fun = {"nba": {"min_games": 2, "max_games": 2, "max_legs": 10, "band": [500, 4000], "overs_per_slate": 3,
                   "short": {"band": [150, 500], "max_games": 2}}}
    games = [game("a", "BOS", 0.30), game("b", "MIA", 0.30), game("c", "NY", 0.55), game("d", "DET", 0.55)]
    s = fun_nba._slate(games, fun)
    assert {g["event_id"] for g in s["plus"]["games"]} == {"a", "b"}                 # 9%: +1011
    assert {g["event_id"] for g in s["plus_short"]["games"]} == {"c", "d"}           # 30%: +231, the games left out
    assert s["plus_short"]["style"] == "likelier" and "(likelier)" in s["plus_short"]["matchup"]
    assert [x["sgp_id"] for x in s["sgps"]] == ["s-a", "s-b", "s-c", "s-d"]           # every game's own slips
    assert fun_nba._slate(games[:2], fun | {"nba": fun["nba"] | {"short": None}})["plus_short"] is None


def test_a_5pm_tip_is_its_own_slice_and_a_lock_under_the_old_hours_reopens():
    # Nov 7: a 5:10 tip led the NBA early slice, which locked at 4:45 with the 8:10 Knicks game in it
    assert fun_nba.slice_key("2026-11-07T22:10:00Z") == ("2026-11-07", "dusk")
    assert fun_nba.slice_key("2026-11-08T01:10:00Z") == ("2026-11-07", "early")
    assert sgp_plus.slice_names("nba", "2026-11-07", "dusk", 1, kickoff="2026-11-07T22:10:00Z")["title"] == "NBA 5:10 PM game"
    sid = "2026-11-07-nba-early"
    old = [{"slate": sid, "sport": "nba", "kickoff": "2026-11-07T22:10:00Z", "locked_at": "2026-11-07T21:45:26+00:00",
            "plus": {"sgp_id": "old"}}]
    new = [{"slate": sid, "sport": "nba", "kickoff": "2026-11-08T00:40:00Z", "plus": {"sgp_id": "new"}}]
    now = pd.Timestamp("2026-11-07T22:15:00Z")
    out = sgp_plus.keep_tickets(new, old, now)[0]
    assert out["plus"]["sgp_id"] == "new" and not out.get("locked_at") and out["resliced"]
    later = sgp_plus.keep_tickets(new, [out], pd.Timestamp("2026-11-08T00:15:00Z"))[0]
    assert later["locked_at"] and later["resliced"]
    assert alerts.lock_key(later) == f"lock:{sid}:r"
    kept = sgp_plus.keep_tickets([new[0] | {"plus": {"sgp_id": "newer"}}], [later], pd.Timestamp("2026-11-08T00:30:00Z"))[0]
    assert kept["plus"]["sgp_id"] == "new" and kept["locked_at"] == later["locked_at"]
    # reopened once: a relock whose kickoff is still the old first start keeps (Nov 7: the NBA's merge kept the 5:10 game)
    stuck = sgp_plus.keep_tickets([new[0] | {"kickoff": old[0]["kickoff"]}], [later | {"kickoff": old[0]["kickoff"]}],
                                  pd.Timestamp("2026-11-07T22:30:00Z"))[0]
    assert stuck["locked_at"] == later["locked_at"] and stuck["plus"]["sgp_id"] == "new"
