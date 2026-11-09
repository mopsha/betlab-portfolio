"""College basketball's lines-only SGP+ ticket (Oct 12): DraftKings' free lines until Mar 1, never New York."""

import json

import numpy as np
import pandas as pd

from betlab import config, fun_ledger
from betlab.cards import fun_ncaab as FB

TEAMS = [("Duke Blue Devils", "Duke", "Army Black Knights", "Army", -22.5, 141.5, "NC"),
         ("Kansas Jayhawks", "Kansas", "Howard Bison", "Howard", -18.5, 150.5, "KS"),
         ("Gonzaga Bulldogs", "Gonzaga", "Pepperdine Waves", "Pepperdine", -20.5, 155.5, "WA"),
         ("Kentucky Wildcats", "Kentucky", "Louisville Cardinals", "Louisville", -4.5, 147.5, "KY"),
         ("Syracuse Orange", "Syracuse", "Colgate Raiders", "Colgate", -10.5, 140.5, "NY")]     # New York: never


def _history(n=6000, seed=1):
    rng = np.random.default_rng(seed)
    sp = rng.uniform(-28, 28, n)
    tot = rng.uniform(125, 165, n)
    margin = sp + rng.normal(0, 11, n)
    total = tot + rng.normal(0, 16, n) + 0.15 * np.abs(margin - sp) * (np.abs(sp) > 19)
    hp, ap = (total + margin) / 2, (total - margin) / 2
    return pd.DataFrame({"season": 2025, "spread_line": sp, "total_line": tot, "home_pts": hp, "away_pts": ap,
                         "margin": margin, "total": total})


def _snap():
    rows = []
    for i, (hn, _, an, _, sp, tot, _) in enumerate(TEAMS):
        base = {"event_id": f"e{i}", "commence_time": "2026-11-10T00:00:00Z", "home_team": hn, "away_team": an,
                "bookmaker": "draftkings", "snapshot_ts": "2026-11-09T15:00:00Z"}
        rows += [base | {"market": "spreads", "outcome": hn, "point": sp, "price": -110},
                 base | {"market": "spreads", "outcome": an, "point": -sp, "price": -110},
                 base | {"market": "totals", "outcome": "Over", "point": tot, "price": -110},
                 base | {"market": "totals", "outcome": "Under", "point": tot, "price": -110},
                 base | {"market": "h2h", "outcome": hn, "point": None, "price": -3000 if abs(sp) > 15 else -200},
                 base | {"market": "h2h", "outcome": an, "point": None, "price": 1200 if abs(sp) > 15 else 165}]
    return pd.DataFrame(rows)


def _data():
    sched = pd.DataFrame([{"game_id": 100 + i, "date": pd.Timestamp("2026-11-09"), "home_team": h, "away_team": a,
                           "neutral": False, "state": st} for i, (_, h, _, a, _, _, st) in enumerate(TEAMS)])
    names = {hn: h for hn, h, _, _, _, _, _ in TEAMS} | {an: a for _, _, an, a, _, _, _ in TEAMS}
    return _history(), sched, names


def test_a_lines_only_ticket_from_draftkings_never_new_york():
    cfg = config.settings()["fun"]["ncaab"]
    slates = FB.build(_snap(), pd.Timestamp("2026-11-09T16:00:00Z"), cfg, data=_data())
    assert len(slates) == 1 and slates[0]["slate"] == "2026-11-09-ncaab-evening"   # 7 PM ET tips
    s = slates[0]
    assert s["book"] == "draftkings" and s["lines_only"] and s["sport"] == "ncaab"
    priced = {p["matchup"] for p in s["packs"]}
    assert not any(x in m for m in priced for x in ("Syracuse", "Colgate", "Army")) and len(priced) == 3   # Army: West Point, NY
    t = s["plus"]
    assert t is not None and t["n_games"] == 3 and "DraftKings" in t["why"]
    for g in t["games"]:
        assert all(l["stat"] in ("moneyline", "spread", "total") for l in g["legs"])


def test_ncaab_ticket_legs_grade_from_cbbd_scores():
    df = pd.DataFrame([{"sgp_id": "plus-x", "sport": "ncaab", "status": "open", "game_id": "100",
                        "legs": json.dumps(["Duke Blue Devils -22.5", "Over 141.5 total points"]),
                        "leg_games": json.dumps(["100", "100"]), "price": 250.0, "marked": False, "stake": None,
                        "leg_p": json.dumps([0.5, 0.5])}])
    finals = pd.DataFrame([{"game_id": 100, "home_team": "Duke", "away_team": "Army", "home_pts": 90.0, "away_pts": 60.0}])
    n = fun_ledger._grade_ncaab(df, df, finals=finals, names={"Duke Blue Devils": "Duke"})
    assert n == 1 and df.loc[0, "status"] == "won"           # Duke by 30 covers 22.5; 150 goes over 141.5


def test_a_morning_tip_is_its_own_slice_and_locks_before_it():
    """The Nov 1 opener in Rome (9:30 AM ET) and 11 AM tournament games lock on their own (Oct 27): the afternoon's
    noon-4:30 games would otherwise go on a ticket locked at 9:15, before their pre-game pulls."""
    from betlab import sgp_plus
    assert sgp_plus.slice_of("2026-11-01T14:30:00Z", "ncaab") == ("2026-11-01", "morning")    # 9:30 AM EST
    assert sgp_plus.slice_of("2026-11-25T16:00:00Z", "ncaab") == ("2026-11-25", "morning")    # 11 AM
    assert sgp_plus.slice_of("2026-11-25T17:00:00Z", "ncaab") == ("2026-11-25", "afternoon")  # noon
    assert sgp_plus.slice_of("2026-11-10T06:00:00Z", "ncaab") == ("2026-11-09", "late")       # 1 AM: the night before
    n = sgp_plus.slice_names("ncaab", "2026-11-01", "morning", 1, "2026-11-01T14:30:00Z")
    assert n["slate"] == "2026-11-01-ncaab-morning"
    slate = {"slate": "2026-11-01-ncaab-morning", "sport": "ncaab", "kickoff": "2026-11-01T14:30:00Z"}
    assert sgp_plus.lock_due([slate], pd.Timestamp("2026-11-01T14:16:00Z")) == ["2026-11-01-ncaab-morning"]
