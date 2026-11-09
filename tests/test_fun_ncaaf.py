"""College lines-only SGP+ tickets: past games' joint draws, pairs only where legs move together,
New York rules, and grading from CFBD's final scores."""

import json

import numpy as np
import pandas as pd

from betlab import fun_ledger as FL
from betlab.cards import fun_ncaaf as F
from betlab.sources import cfbd

CFG = {"band": [100, 20000], "min_games": 2, "max_games": 4, "max_legs": 10, "leg_p": [0.40, 0.80],
       "allow_unders": False, "pair_lift": 1.05, "minis_per_game": 3, "pool_games": 12}


def history(n=4000, seed=0):
    """Past games where big favorites' blowouts come with high totals (the college pattern)."""
    rng = np.random.default_rng(seed)
    spread = rng.uniform(0, 35, n)
    shock = rng.normal(0, 12, n)                           # a favorite's big day adds to both
    link = np.clip((spread - 14) / 20, 0, 1)
    fav_margin = spread + shock + rng.normal(0, 8, n)
    total = 55 + link * shock + rng.normal(0, 14, n)
    home_fav = rng.random(n) < 0.6
    margin = np.where(home_fav, fav_margin, -fav_margin)
    return pd.DataFrame({"season": 2020, "home_div": "fbs", "away_div": "fbs",
                         "spread_line": np.where(home_fav, spread, -spread), "total_line": 55.0,
                         "home_pts": (total + margin) / 2, "away_pts": (total - margin) / 2,
                         "margin": margin, "total": total})


def test_big_favorites_cover_with_the_over_small_spreads_dont():
    res = F.residuals(history(), 2026)
    lift = {}
    for s in (3.0, 28.0):
        hp, ap = F.draws(res, s, 55.0, n=20000)
        cover, over = (hp - ap) > s, (hp + ap) > 55.0
        lift[s] = (cover & over).mean() / (cover.mean() * over.mean())
    assert lift[28.0] > 1.08 and abs(lift[3.0] - 1) < 0.05
    hp, ap = F.draws(res, -10.0, 60.0, n=4000)             # away favorite: its margin comes out negative for home
    assert np.median(hp - ap) < -5 and abs(np.median(hp + ap) - 60) < 3


def _leg(label, stat, side, p, hit, price=-110):
    from betlab.sgp import Leg
    l = Leg(key=("game", "total" if stat == "total" else "side"), label=label, player="game x", team="", stat=stat,
            side=side, point=0.0, price=price, hit=hit, source="pinnacle")
    l.p = l.p_model = p
    return l


def test_minis_pair_only_legs_that_move_together_and_skip_unders():
    rng = np.random.default_rng(1)
    z = rng.random(10000)
    w = np.full(10000, 1e-4)
    fav = _leg("Big U -24.5", "spread", "yes", 0.5, z < 0.5)
    over = _leg("Over 56.5 total points", "total", "over", 0.5, z < 0.62)       # overlaps the cover: moves with it
    under = _leg("Under 56.5 total points", "total", "under", 0.5, z >= 0.62)
    kinds = [tuple(l["label"] for l in m["legs"]) for m in F.minis([fav, over, under], w, CFG, "e1")]
    assert ("Big U -24.5", "Over 56.5 total points") in kinds
    assert not any("Under" in lab for k in kinds for lab in k)
    solo = F.minis([_leg("Other -3.5", "spread", "yes", 0.5, z < 0.5), _leg("Over 50.5 total points", "total", "over", 0.5,
                                                                            rng.random(10000) < 0.5)], w, CFG, "e2")
    assert all(m["n_legs"] == 1 for m in solo)                                  # independent legs: no pair


def book(event, home, away, when, spread, total):
    rows = []
    for bk in ("fanduel", "pinnacle"):
        for o, pr in ((home, -110), (away, -110)):
            rows.append({"event_id": event, "commence_time": when, "home_team": home, "away_team": away, "bookmaker": bk,
                         "market": "spreads", "outcome": o, "point": spread if o == home else -spread, "price": pr})
        for o in ("Over", "Under"):
            rows.append({"event_id": event, "commence_time": when, "home_team": home, "away_team": away, "bookmaker": bk,
                         "market": "totals", "outcome": o, "point": total, "price": -110})
        for o, pr in ((home, -150), (away, 130)):
            rows.append({"event_id": event, "commence_time": when, "home_team": home, "away_team": away, "bookmaker": bk,
                         "market": "h2h", "outcome": o, "point": None, "price": pr})
    return rows


def test_build_skips_new_york_and_unknown_venues(monkeypatch):
    when = "2026-10-03T19:30:00Z"
    hist = history().assign(game_id="old", date=pd.Timestamp("2020-10-03"), home_team="X", away_team="Y",
                            neutral=False, venue_state="TX")
    upcoming = pd.DataFrame({"game_id": ["g1", "g2", "g3", "g4"], "season": 2026, "home_div": "fbs", "away_div": "fbs",
                             "date": pd.Timestamp("2026-10-03"), "home_team": ["Alpha", "Syracuse", "Gamma", "Delta"],
                             "away_team": ["Beta", "Beta2", "Gamma2", "Delta2"], "neutral": False,
                             "venue_state": ["TX", "NY", None, "OH"], "spread_line": np.nan, "total_line": np.nan,
                             "home_pts": np.nan, "away_pts": np.nan, "margin": np.nan, "total": np.nan})
    monkeypatch.setattr(cfbd, "games", lambda: pd.concat([hist, upcoming], ignore_index=True))
    names = {f"{t} U": t for t in ("Alpha", "Beta", "Syracuse", "Beta2", "Gamma", "Gamma2", "Delta", "Delta2")}
    monkeypatch.setattr(cfbd, "team_names", lambda: names)
    snap = pd.DataFrame(book("e1", "Alpha U", "Beta U", when, -24.5, 56.5) + book("e2", "Syracuse U", "Beta2 U", when, -3.5, 50.5)
                        + book("e3", "Gamma U", "Gamma2 U", when, -7.5, 48.5) + book("e4", "Delta U", "Delta2 U", when, -2.5, 52.5))
    slates = F.build(snap, pd.Timestamp("2026-10-03T12:00:00Z"), CFG)
    assert len(slates) == 1 and slates[0]["lines_only"] and slates[0]["sport"] == "ncaaf"
    t = slates[0]["plus"]
    assert t and {g["event_id"] for g in t["games"]} <= {"e1", "e4"}           # never Syracuse, never an unknown venue
    assert {g["game_ref"] for g in t["games"]} <= {"g1", "g4"} and t["sport"] == "ncaaf"


def test_college_ticket_grades_from_final_scores(tmp_path, monkeypatch):
    monkeypatch.setattr(FL, "PATH", tmp_path / "fun.csv")
    finals = pd.DataFrame({"game_id": ["g1", "g4"], "home_team": ["Alpha", "Delta"], "away_team": ["Beta", "Delta2"],
                           "home_pts": [45.0, 20.0], "away_pts": [14.0, 24.0], "date": pd.Timestamp("2026-10-03")})
    monkeypatch.setattr(cfbd, "games", lambda: finals)
    monkeypatch.setattr(cfbd, "team_names", lambda: {"Alpha U": "Alpha", "Delta2 U": "Delta2"})
    ticket = {"sgp_id": "plus-c1", "sport": "ncaaf", "price": 900, "fair_price": 800, "p_fair": 0.11,
              "matchup": "SGP+ Sat Oct 3 · college football", "quoted_at": "2026-10-03T15:00:00Z",
              "games": [{"matchup": "Beta U @ Alpha U", "game_ref": "g1", "legs": ["Alpha U -24.5", "Over 56.5 total points"]},
                        {"matchup": "Delta2 U @ Delta U", "game_ref": "g4", "legs": ["Delta2 U ML"]}]}
    from betlab.sources import nflverse
    monkeypatch.setattr(nflverse, "load_games", lambda: pd.DataFrame(columns=["game_id", "home_team", "away_team", "date"]))
    monkeypatch.setattr(nflverse, "team_abbr_by_name", lambda: {})
    FL.sync([ticket], [])
    row = FL.load().iloc[0]
    assert row["sport"] == "ncaaf" and json.loads(row["leg_games"]) == ["g1", "g1", "g4"]
    assert FL.grade() == 1
    r = FL.load().iloc[0]
    assert r["status"] == "won" and r["profit_1u"] == 9.0      # Alpha by 31 (covers 24.5), 59 points (over), Delta2 won
