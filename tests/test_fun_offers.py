"""One-story slips (Mike, Oct 11) and the tracker of every offered slip (fun_offers.csv)."""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from betlab import explain, fun_offers, sgp


def _legs(n=20000, seed=3):
    """A and B rise together; C pulls against them (a QB's yards vs the other team winning)."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    a, b, c = z + 0.6 * rng.normal(size=n), z + 0.6 * rng.normal(size=n), -0.3 * z + rng.normal(size=n)
    d = rng.normal(size=n)
    w = np.full(n, 1 / n)

    def leg(name, hit, price=-180):
        lg = sgp.Leg(key=(name, "receptions"), label=f"{name} over 3.5 receptions", player=name, team="AAA",
                     stat="receptions", side="over", point=3.5, price=price, hit=hit)
        lg.p = lg.p_model = float(w[hit].sum())
        return lg

    return [leg("A", a > -0.5), leg("B", b > -0.5), leg("C", c > -0.5, -200), leg("D", d > -0.5)], w, z


def test_each_slip_records_its_weakest_pair_and_one_story_excludes_legs_that_pull_apart():
    legs, w, _ = _legs()
    found = sgp.search(legs, w, band=(100, 5000), min_legs=3, max_legs=3, min_leg_p=0.55)
    by = {frozenset(l.player for l in f["legs"]): f for f in found}
    with_c = by[frozenset("ABC")]
    without_c = by[frozenset("ABD")]
    assert with_c["min_lift"] < 0.97 and not sgp.one_story(with_c)
    assert without_c["min_lift"] >= 0.97 and sgp.one_story(without_c)
    doc = sgp.to_doc(without_c, "e1")
    assert doc["one_story"] is True and doc["min_pair_lift"] >= 0.97
    assert doc["sgp_id"] == sgp.slip_id(without_c["legs"], "e1")


def test_the_script_names_the_game_a_slip_needs():
    legs, w, z = _legs()
    sim = SimpleNamespace(points={"HOM": 24 + 7 * z, "AWY": np.full(len(z), 21.0)},
                          team={"HOM": {"pass_yds": 230 + 40 * z}, "AWY": {"pass_yds": np.full(len(z), 220.0)}})
    sc = sgp.script(legs[:2], w, sim, "HOM", "AWY")
    assert sc["p_home_hit"] > sc["p_home"] + 0.05 and sc["total_hit"] > sc["total"]
    text = explain.script_story(sc, {})
    assert text.startswith("One story: this slip needs") and "throwing more" in text
    assert explain.script_story(None, {}) == ""


def _game(sgps, kickoff="2026-10-18T17:00:00Z"):
    return {"event_id": "e1", "game_ref": "2026_07_AAA_BBB", "matchup": "B @ A", "commence_time": kickoff, "sgps": sgps}


def _doc(sid, style, legs):
    return {"sgp_id": sid, "style": style, "one_story": style == "story", "min_pair_lift": 1.0, "lift": 1.2,
            "theme": "Correlated overs", "n_legs": len(legs), "p_fair": 0.3, "fair_price": 233, "naive_price": 300,
            "legs": [{"label": l, "price": -150, "p_fair": 0.6} for l in legs]}


def test_offers_are_logged_once_and_graded_leg_by_leg(tmp_path, monkeypatch):
    monkeypatch.setattr(fun_offers, "PATH", tmp_path / "fun_offers.csv")
    asof = pd.Timestamp("2026-10-18T12:00:00Z")
    legs = ["Al Pha over 3.5 receptions", "Be Ta over 3.5 receptions"]
    g = _game([_doc("s1", "value", legs), _doc("s2", "story", legs[:1])])
    assert fun_offers.record([g], asof) == 2
    assert fun_offers.record([g], asof) == 0                      # logged once, at the first offer
    assert fun_offers.record([_game([_doc("s3", "value", legs)], "2026-10-18T11:00:00Z")], asof) == 0  # started

    ps = pd.DataFrame({"game_id": ["2026_07_AAA_BBB"] * 2, "player_id": ["p1", "p2"],
                       "player_display_name": ["Al Pha", "Be Ta"], "receptions": [5, 2],
                       "rushing_tds": [0, 0], "receiving_tds": [0, 0]})
    sn = pd.DataFrame({"game_id": ["2026_07_AAA_BBB"] * 2, "player_id": ["p1", "p2"], "player": ["Al Pha", "Be Ta"],
                       "offense_snaps": [50, 40]})
    finals = pd.DataFrame(index=pd.Index([], name="game_id"))
    n = fun_offers.grade(ps, sn, finals, {}, now=pd.Timestamp("2026-10-19T12:00:00Z"))
    assert n == 2
    df = fun_offers.load().set_index("sgp_id")
    assert df.loc["s1", "status"] == "lost" and df.loc["s2", "status"] == "won"
    assert float(df.loc["s2", "profit_1u"]) == round(1 / 1.5, 4) and float(df.loc["s1", "profit_1u"]) == -1.0
    s = fun_offers.summary().set_index("group")
    assert s.loc["style story", "hits"] == 1 and s.loc["not one story", "slips"] == 1


def test_a_void_leg_comes_off_the_slip():
    legs = [{"label": "x", "price": 100, "p": 0.5}, {"label": "y", "price": -200, "p": 0.6}]
    assert fun_offers.settle(legs, [{"result": "void"}, {"result": "won"}]) == ("won", 0.6, 0.5)
    assert fun_offers.settle(legs, [{"result": "void"}, {"result": "push"}]) == ("void", None, 0.0)
    assert fun_offers.settle(legs, [{"result": "open"}, {"result": "won"}]) is None


def test_nba_slips_grade_from_box_scores_beside_nfl_ones(tmp_path, monkeypatch):
    """Oct 20: NBA lone-game slips logged here too; their game_id is "nba|HOME|AWAY|tipoff", which the NFL path would
    have read as a season (int("nba|")) and stopped every slip's grading. NBA rows grade from ESPN's box scores."""
    monkeypatch.setattr(fun_offers, "PATH", tmp_path / "fun_offers.csv")
    ref = "nba|NY|OKC|2026-03-04T00:00:00+00:00"
    g = {"event_id": "n1", "game_ref": ref, "matchup": "OKC @ NY", "commence_time": "2026-03-04T00:00:00Z",
         "sgps": [_doc("n-slip", "value", ["Josh Hart 5+ assists", "New York Knicks ML"])]}
    assert fun_offers.record([g], pd.Timestamp("2026-03-03T23:00:00Z")) == 1
    sch = pd.DataFrame([{"game_id": 9, "home_abbreviation": "NY", "away_abbreviation": "OKC", "home_display_name": "New York Knicks",
                         "away_display_name": "Oklahoma City Thunder", "start_date": "2026-03-04T00:00Z", "home_score": 110,
                         "away_score": 104, "status_type_completed": True}])
    box = pd.DataFrame([{"game_id": 9, "athlete_id": 1, "athlete_display_name": "Josh Hart", "minutes": "36", "points": 12,
                         "rebounds": 9, "assists": 7, "three_point_field_goals_made": 1, "game_date": "2026-03-03"}])
    assert fun_offers.grade(now=pd.Timestamp("2026-03-05T12:00:00Z"), nba_box=box, nba_sch=sch) == 1
    row = fun_offers.load().iloc[0]
    assert row["status"] == "won" and float(row["profit_1u"]) == pytest.approx((1 + 100 / 150) ** 2 - 1, abs=1e-4)
