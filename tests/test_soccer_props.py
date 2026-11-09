"""Soccer props (Oct 10): ESPN box scores, the books' ladder fits and the line tracker."""

import numpy as np
import pandas as pd
import pytest

from betlab import tracking_soccer_props as T
from betlab.models import props_soccer as PS
from betlab.models.props_nhl import p_over
from betlab.sources import espn_soccer as E


def test_a_ladder_fit_recovers_the_mean_and_margin():
    from betlab import odds_math as om

    pts = [0.5, 1.5, 2.5, 3.5, 4.5]
    prices = [om.prob_to_american(min(0.97, float(p_over(2.4, x, 8.0)) * 1.15)) for x in pts]
    mean, margin = PS.ladder_fit(pts, prices, 8.0)
    assert mean == pytest.approx(2.4, abs=0.15) and margin == pytest.approx(0.15, abs=0.03)
    assert PS.ladder_fit([1.5], [-150], 8.0) is None


def _summary():
    def p(pid, name, starter, sub_in=False, sub_out=False, shots=0, sot=0, goals=0):
        return {"athlete": {"id": pid, "displayName": name}, "starter": starter, "subbedIn": sub_in, "subbedOut": sub_out,
                "position": {"abbreviation": "F"}, "formationPlace": "9",
                "stats": [{"name": "totalShots", "value": shots}, {"name": "shotsOnTarget", "value": sot},
                          {"name": "totalGoals", "value": goals}]}
    return {"header": {"id": "e1", "competitions": [{"date": "2026-10-10T18:45Z", "competitors": [
                {"homeAway": "home", "score": "2"}, {"homeAway": "away", "score": "0"}]}]},
            "keyEvents": [{"type": {"text": "Substitution"}, "clock": {"displayValue": "63'"},
                           "participants": [{"athlete": {"id": "3"}}, {"athlete": {"id": "1"}}]},
                          {"type": {"text": "Substitution"}, "clock": {"displayValue": "90'+2'"},
                           "participants": [{"athlete": {"id": "4"}}, {"athlete": {"id": "2"}}]}],
            "rosters": [{"homeAway": "home", "team": {"displayName": "Napoli"}, "roster": [
                            p("1", "Rasmus Højlund", True, sub_out=True, shots=3, sot=2, goals=1),
                            p("2", "Matteo Politano", True, sub_out=True, shots=1),
                            p("3", "Lorenzo Lucca", False, sub_in=True, shots=2, sot=1),
                            p("4", "Noa Lang", False, sub_in=True), p("5", "Unused Sub", False)]},
                        {"homeAway": "away", "team": {"displayName": "Frosinone"}, "roster": [
                            p("9", "Alessio Zerbin", True, shots=1)]}]}


def test_box_minutes_from_the_substitutions():
    b = E.box(_summary(), "serie_a").set_index("player")
    assert b.loc["Rasmus Højlund", "minutes"] == 63 and b.loc["Lorenzo Lucca", "minutes"] == 27
    assert b.loc["Matteo Politano", "minutes"] == 92 and b.loc["Noa Lang", "minutes"] == 1    # 90'+2' off / on
    assert b.loc["Unused Sub", "minutes"] == 0 and b.loc["Alessio Zerbin", "minutes"] == 90
    assert b.loc["Rasmus Højlund", "team_goals"] == 2 and b.loc["Alessio Zerbin", "opponent"] == "Napoli"


def test_feed_names_match_espn_names_or_nothing():
    squad = pd.DataFrame({"player": ["Rasmus Højlund", "Alisson Santos", "Kevin De Bruyne", "Luca Marianucci",
                                     "Luca Mazzitelli"]})
    assert E.match_player("Rasmus Hojlund", squad)["player"] == "Rasmus Højlund"
    assert E.match_player("Alisson de Almeida Santos", squad)["player"] == "Alisson Santos"
    assert E.match_player("K. De Bruyne", squad)["player"] == "Kevin De Bruyne"
    assert E.match_player("Luca Rossi", squad) is None                 # two Lucas, neither a Rossi


def _props():
    rows = []
    for book, ladder in (("fanduel", [(0.5, -7000), (1.5, -1000), (2.5, -290), (3.5, -125), (4.5, 185)]),
                         ("betrivers", [(0.5, -5000), (1.5, -240), (2.5, 125), (3.5, 250)])):
        rows += [{"bookmaker": book, "market": "player_shots", "player": "Matteo Politano", "outcome": "Over",
                  "point": pt, "price": pr} for pt, pr in ladder]
    rows += [{"bookmaker": "fanduel", "market": "player_goal_scorer_anytime", "player": "Matteo Politano",
              "outcome": "Yes", "point": None, "price": 190},
             {"bookmaker": "pinnacle", "market": "player_goal_scorer_anytime", "player": "Matteo Politano",
              "outcome": "Yes", "point": None, "price": 240},
             {"bookmaker": "pinnacle", "market": "player_goal_scorer_anytime", "player": "Matteo Politano",
              "outcome": "No", "point": None, "price": -300}]
    return pd.DataFrame(rows)


def test_rows_record_and_grade(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "PATH", tmp_path / "soccer_prop_lines.csv")
    info = {"event_id": "o1", "espn_id": "e1", "commence_time": "2026-10-10T18:45:00Z", "matchup": "Frosinone @ Napoli"}
    squad = E.box(_summary(), "serie_a")
    rows = T.rows(_props(), "serie_a", info, squad)
    shots = [r for r in rows if r["stat"] == "shots"]
    assert [r["line"] for r in shots] == [0.5, 1.5, 2.5, 3.5, 4.5] and all(r["team"] == "Napoli" for r in rows)
    assert shots[2]["fd_mean"] > shots[2]["mkt_mean"]                 # FanDuel expects more shots than BetRivers
    assert shots[2]["br_price"] == 125 and shots[4]["br_price"] is None and shots[0]["books"] == 1
    scorer = [r for r in rows if r["stat"] == "scorer"][0]
    assert scorer["fd_price"] == 190 and 0.2 < scorer["p_market"] < 0.3
    assert T.record(rows, pd.Timestamp("2026-10-10T17:50:00Z")) == len(rows)
    T.record(rows, pd.Timestamp("2026-10-10T18:20:00Z"))                # a second look: no duplicates
    assert len(T.load()) == len(rows)
    assert T.grade(pd.Timestamp("2026-10-11T12:00:00Z"), box_for=lambda lg, eid: squad) == len(rows)
    g = T.load().set_index("line_id")
    assert g.loc["o1|Matteo Politano|shots|0.5", "status"] == "won"    # 1 shot
    assert g.loc["o1|Matteo Politano|shots|1.5", "status"] == "lost"
    assert g.loc["o1|Matteo Politano|scorer|0.5", "status"] == "lost"
    assert T.summary()["shots"]["n"] == 5


def test_summary_compares_sources_on_the_same_rungs():
    """Oct 20: each source's log loss was over its own rungs (model 0.427 on 5,633 shots rungs vs FanDuel 0.470 on 7,726)."""
    rows = pd.DataFrame({"stat": ["shots"] * 4 + ["assists"] * 2, "status": ["won", "lost", "won", "lost", "lost", "won"],
                         "p_model": [0.6, 0.3, np.nan, 0.4, 0.2, 0.3], "p_fd_fair": [0.7, 0.4, 0.9, 0.5, np.nan, np.nan],
                         "p_market": [0.65, np.nan, 0.8, np.nan, np.nan, np.nan]})
    s = T.summary(rows)["shots"]
    assert s["same"]["n"] == 1 and set(s["same"]) == {"n", "model", "fanduel", "other_books"}   # only rung 1 has all three
    assert s["model_vs_fanduel"]["n"] == 3 and s["model_vs_other_books"]["n"] == 1
    a = T.summary(rows)["assists"]
    assert a["model"]["n"] == 2 and "same" not in a                    # the model alone: its own log loss, nothing beside it


def test_features_use_only_earlier_matches():
    """A player's rates for a match come from his matches before it (no leakage of tonight's shots)."""
    rows = []
    for i, (shots, mins) in enumerate([(4, 90), (0, 90), (2, 45)]):
        k = pd.Timestamp("2026-08-01T15:00Z") + pd.Timedelta(days=7 * i)
        for team, opp, home in (("A", "B", True), ("B", "A", False)):
            rows.append({"event_id": f"m{i}", "league": "epl", "kickoff": k, "team": team, "opponent": opp, "home": home,
                         "player_id": "p1" if team == "A" else "q1", "player": "x", "position": "F",
                         "formation_place": 9, "starter": True, "came_on": False,
                         "minutes": mins if team == "A" else 90, "shots": shots if team == "A" else 1, "sot": 0})
    f = PS.features(pd.DataFrame(rows)).set_index(["event_id", "player_id"])
    assert pd.isna(f.loc[("m0", "p1"), "shots90_l"]) and f.loc[("m0", "p1"), "apps_prior"] == 0
    assert f.loc[("m1", "p1"), "shots90_l"] == pytest.approx(4.0)            # only match 0
    assert f.loc[("m1", "p1"), "team_shots_for"] == pytest.approx(4.0)
    assert f.loc[("m2", "p1"), "apps_prior"] == 2 and f.loc[("m2", "p1"), "shots90_l"] < 4.0


def test_tonight_means_use_the_lineup_and_history():
    """cards/props_soccer.means: tonight's starters get the model's shots / SOT (SOT scaled to the books'
    counts); bench players get nothing (the model learned starters)."""
    import numpy as np

    from betlab.cards import props_soccer as C

    class Stub:                                       # predicts the player's long shots rate
        def predict(self, X):
            return np.nan_to_num(X["shots90_l"].to_numpy(float), nan=0.5)

    model = PS.Fitted(models={"shots": Stub(), "sot": Stub()}, dispersion={"shots": 8.0, "sot": 8.0},
                      features=["shots90_l"])
    hist = E.box(_summary(), "serie_a").assign(season=2027)
    tonight = E.box(_summary(), "serie_a").assign(event_id="e2", shots=np.nan, sot=np.nan, minutes=np.nan)
    tonight["kickoff"] = pd.Timestamp("2026-10-17T18:45Z")
    out = C.means([(tonight, "serie_a", (2.1, 0.8))], history=hist, model=model)["e2"]
    hojlund = tonight.set_index("player").loc["Rasmus Højlund", "player_id"]
    assert out[str(hojlund)]["shots"] == pytest.approx(3 / 63 * 90)            # from the earlier match only
    assert out[str(hojlund)]["sot"] == pytest.approx(3 / 63 * 90 * C.SOT_SCALE)
    lucca = tonight.set_index("player").loc["Lorenzo Lucca", "player_id"]
    assert str(lucca) not in out                                                # a sub: not priced


def test_the_soccer_analysis_builds_from_lineups_or_last_xis(monkeypatch):
    """cards/analysis_soccer.build: projected shots from the starters (scaled up for subs), shot form,
    rotation once the lineup is out, the likeliest shooters with FanDuel's rungs, and a short story."""
    import numpy as np

    from betlab.cards import analysis_soccer as A
    from betlab.cards import props_soccer as C

    class Stub:
        def predict(self, X):
            return np.full(len(X), 1.5)

    model = PS.Fitted(models={"shots": Stub(), "sot": Stub()}, dispersion={"shots": 8.0, "sot": 8.0},
                      features=["shots90_l"])
    monkeypatch.setattr(C, "fitted", lambda: model)
    hist = E.box(_summary(), "serie_a").assign(season=2027)
    game = {"event_id": "o2", "league": "serie_a", "home": "Napoli", "away": "Frosinone",
            "commence_time": "2026-10-17T18:45:00Z"}
    now = pd.Timestamp("2026-10-17T12:00:00Z")
    lines = pd.DataFrame([{"event_id": "o2", "player": "Rasmus Hojlund", "stat": "shots", "line": 1.5,
                           "fd_price": -150.0, "p_model": 0.5, "p_fd_fair": 0.55}])
    build = lambda: A.build([game], now, picks={}, lines=lines, history=hist,
                            find=lambda *a: "e2", lineup=lambda *a: pd.DataFrame())   # lineups not out yet
    t = build()["o2"]["teams"][0]
    assert t["shots"] is None and t["goals_model"] is None            # 2 known starters of 11: no team totals
    monkeypatch.setattr(A, "MIN_KNOWN_STARTERS", 1)                    # the fixture's small sides
    d = build()["o2"]
    assert d["lineup"] == "expected" and [t["team"] for t in d["teams"]] == ["Napoli", "Frosinone"]
    share = A.starter_share(hist)["shots"]
    assert d["teams"][0]["shots"] == pytest.approx(round(2 * 1.5 / share, 1))        # 2 Napoli starters last time
    assert d["teams"][0]["rotation"] is None and "shots to" in d["script"]
    hoj = [s for s in d["shooters"] if s["player"] == "Rasmus Højlund"][0]
    assert hoj["fd_shots"][0]["fd_price"] == -150.0

    squad = E.box(_summary(), "serie_a").assign(event_id="e2")
    squad.loc[squad["player"] == "Matteo Politano", "starter"] = False                # dropped tonight
    squad = pd.concat([squad] + [squad.assign(player_id=squad["player_id"] + f"x{i}") for i in range(10)])
    docs = A.build([game], now, picks={}, lines=lines, history=hist, find=lambda *a: "e2", lineup=lambda *a: squad)
    rot = docs["o2"]["teams"][0]["rotation"]
    assert docs["o2"]["lineup"] == "confirmed" and rot["changes"] == 1


def test_anytime_scorer_offers_against_pinnacle_and_their_grading():
    """Oct 10 (Mike): FanDuel's anytime-scorer price against Pinnacle's two-way no-vig chance, market-only;
    picks follow the normal prop rules. Graded from ESPN's box score (void if he didn't play), CLV against
    Pinnacle's last pre-kickoff price."""
    from betlab import grading
    from betlab.cards import props_soccer as C

    base = {"event_id": "o1", "commence_time": "2026-10-10T16:30:00Z", "home_team": "Barcelona", "away_team": "Getafe",
            "market": C.SCORER, "player": "Lamine Yamal", "point": None, "snapshot_ts": "2026-10-10T16:00:00Z"}
    snap = pd.DataFrame([base | {"bookmaker": "fanduel", "outcome": "Yes", "price": -110.0},
                         base | {"bookmaker": "pinnacle", "outcome": "Yes", "price": -150.0},
                         base | {"bookmaker": "pinnacle", "outcome": "No", "price": 130.0},
                         base | {"bookmaker": "fanduel", "outcome": "Yes", "price": 400.0, "player": "No Pinnacle"}])
    o = C.scorer_offers(snap, "la_liga", pd.Timestamp("2026-10-10T16:05:00Z"))
    assert list(o["player"]) == ["Lamine Yamal"] and o.iloc[0]["kind"] == "prop" and o.iloc[0]["w_model"] == 0
    assert 0.55 < o.iloc[0]["p_market"] < 0.6 and o.iloc[0]["ev"] > 0.05                # -110 against ~58%
    from betlab import picks
    assert picks.classify(o, pd.Timestamp("2026-10-10T16:05:00Z")).iloc[0]["tier"] == "pick"

    led = o.assign(status="open", units_flat=1.0, profit_flat=None, p_close=None, clv=None, graded_at=None)
    row = pd.Series({"goals": 1.0, "minutes": 90})
    g = grading.grade_soccer(led, "la_liga", pd.Timestamp("2026-10-11T12:00:00Z"),
                             scorer=lambda *a: ("ok", row), scorer_close=lambda *a: 0.60)
    assert g.iloc[0]["status"] == "won" and g.iloc[0]["profit_flat"] == pytest.approx(100 / 110, abs=1e-4)
    assert g.iloc[0]["p_close"] == 0.60 and g.iloc[0]["clv"] > 0
    g = grading.grade_soccer(led, "la_liga", pd.Timestamp("2026-10-11T12:00:00Z"),
                             scorer=lambda *a: ("void", None), scorer_close=lambda *a: None)
    assert g.iloc[0]["status"] == "void" and g.iloc[0]["profit_flat"] == 0


def test_espn_events_match_when_espn_spells_a_club_its_own_way(monkeypatch):
    t = pd.Timestamp("2026-10-11T02:30:00Z")
    evs = [{"event_id": "1", "home": "LAFC", "away": "Vancouver Whitecaps", "kickoff": t},
           {"event_id": "2", "home": "Colorado Rapids", "away": "San Jose Earthquakes", "kickoff": t - pd.Timedelta(hours=1)}]
    monkeypatch.setattr(E, "scoreboard", lambda slug, day: None)
    monkeypatch.setattr(E, "events", lambda sb: evs)
    assert E.find_event("mls", "Los Angeles FC", "Vancouver Whitecaps FC", t) == "1"
    # one name agreeing isn't enough at a different kickoff
    assert E.find_event("mls", "Los Angeles FC", "Vancouver Whitecaps FC", t + pd.Timedelta(hours=1)) is None
    assert E.find_event("mls", "Real Salt Lake", "FC Dallas", t) is None


def test_finished_summaries_are_cached_gzipped_and_old_plain_files_still_read(tmp_path, monkeypatch):
    """Oct 20: a plain summary is ~440 KB, and the worker's cache of them helped fill its volume; gzip is ~1/12."""
    import gzip
    import json

    monkeypatch.setattr(E, "CACHE", tmp_path)
    done = {"header": {"competitions": [{"status": {"type": {"completed": True}}}]}, "x": "y" * 1000}
    calls = []
    monkeypatch.setattr(E, "_get", lambda url: calls.append(url) or done)
    assert E.summary("eng.1", "1") == done
    cached = tmp_path / "eng.1" / "1.json.gz"
    assert json.loads(gzip.decompress(cached.read_bytes())) == done and cached.stat().st_size < 200
    assert E.summary("eng.1", "1") == done and len(calls) == 1        # from the cache
    (tmp_path / "eng.1" / "2.json").write_text(json.dumps({"old": 1}), encoding="utf-8")
    assert E.summary("eng.1", "2") == {"old": 1} and len(calls) == 1  # a plain file cached before Oct 20
    (tmp_path / "eng.1" / "4.json").write_text("", encoding="utf-8")       # left empty by a full disk (Oct 17)
    (tmp_path / "eng.1" / "5.json.gz").write_bytes(bytes.fromhex("1f8b"))            # cut off mid-write
    assert E.summary("eng.1", "4") == done and E.summary("eng.1", "5") == done and len(calls) == 3
    assert not (tmp_path / "eng.1" / "4.json").exists() and (tmp_path / "eng.1" / "4.json.gz").exists()
    live = {"header": {"competitions": [{"status": {"type": {"completed": False}}}]}}
    monkeypatch.setattr(E, "_get", lambda url: live)
    E.summary("eng.1", "3")
    assert not (tmp_path / "eng.1" / "3.json.gz").exists()             # a match not finished isn't cached
