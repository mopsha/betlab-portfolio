"""UFC (Oct 23): fights matched to ESPN's card, market-only pricing, grading and the closing look. No network."""

import json

import numpy as np
import pandas as pd
import pytest

from betlab import config, grading, pregame
from betlab.cards import ufc
from betlab.sources import espn_ufc as src

CARD = pd.DataFrame([
    {"fight_id": "1", "start": "2026-10-24T18:00Z", "rounds": 5, "a_name": "Alexander Volkanovski", "b_name": "Movsar Evloev"},
    {"fight_id": "2", "start": "2026-10-24T14:00Z", "rounds": 3, "a_name": "Iasmin Lucindo", "b_name": "Nicolle Caliari"},
    {"fight_id": "3", "start": "2026-10-24T18:00Z", "rounds": 3, "a_name": "Lone'er Kavanagh", "b_name": "Ramazan Temirov"},
])


def _rows(eid, home, away, ts, book_prices, totals=None):
    rows = []
    for bk, (ph, pa) in book_prices.items():
        rows += [{"event_id": eid, "home_team": home, "away_team": away, "commence_time": "2026-10-24T14:00:00Z",
                  "bookmaker": bk, "market": "h2h", "outcome": home, "point": None, "price": ph, "snapshot_ts": ts},
                 {"event_id": eid, "home_team": home, "away_team": away, "commence_time": "2026-10-24T14:00:00Z",
                  "bookmaker": bk, "market": "h2h", "outcome": away, "point": None, "price": pa, "snapshot_ts": ts}]
    for bk, (line, po, pu) in (totals or {}).items():
        for side, pr in (("Over", po), ("Under", pu)):
            rows.append({"event_id": eid, "home_team": home, "away_team": away, "commence_time": "2026-10-24T14:00:00Z",
                         "bookmaker": bk, "market": "totals", "outcome": side, "point": line, "price": pr, "snapshot_ts": ts})
    return pd.DataFrame(rows)


def test_fights_match_on_last_names_in_either_order():
    assert src.same_fight("Ramazonbek Temirov", "Lone'er Kavanagh", "Lone'er Kavanagh", "Ramazan Temirov")
    assert src.same_fight("Alex Volkanovski", "Movsar Evloev", "Alexander Volkanovski", "Movsar Evloev")
    assert not src.same_fight("Robbie Lawler", "Khamzat Chimaev", "Alexander Volkanovski", "Movsar Evloev")
    assert src.find(CARD, "Movsar Evloev", "Alex Volkanovski")["fight_id"] == "1"


def test_align_keeps_ufc_fights_at_their_segment_start():
    """The feed mixes promotions and gives every fight the card's first start (10 AM)."""
    events = [{"id": "e1", "home_team": "Movsar Evloev", "away_team": "Alex Volkanovski", "commence_time": "2026-10-24T14:00:00Z"},
              {"id": "e2", "home_team": "Robbie Lawler", "away_team": "Khamzat Chimaev", "commence_time": "2026-10-24T00:30:00Z"}]
    out = ufc.align(events, CARD)
    assert [e["id"] for e in out] == ["e1"] and out[0]["commence_time"] == "2026-10-24T18:00:00Z"


def test_evaluate_prices_moneyline_and_total_rounds_against_pinnacle():
    snap = _rows("e1", "Movsar Evloev", "Alex Volkanovski", "2026-10-24T13:00:00Z",
                 {"pinnacle": (-110, -110), "draftkings": (105, -125)},
                 {"pinnacle": (4.5, 120, -140), "draftkings": (4.5, 130, -160)})
    out = ufc.evaluate(snap, pd.Timestamp("2026-10-24T13:10Z"), fights=CARD, book="draftkings")
    assert set(out["market"]) == {"h2h", "totals"}
    ev = out[out["side"] == "Movsar Evloev"].iloc[0]
    assert ev["matchup"] == "Alex Volkanovski vs Movsar Evloev" and ev["commence_time"] == "2026-10-24T18:00:00Z"
    assert abs(ev["p_final"] - 0.5) < 1e-9 and ev["ev"] > 0 and ev["w_model"] == 0
    assert "past 4:30 into round 5" in out[out["side"] == "Over"].iloc[0]["context"]
    # FanDuel hangs no total: only its moneyline
    assert set(ufc.evaluate(snap.assign(bookmaker=snap["bookmaker"].replace("draftkings", "fanduel")).query(
        "market == 'h2h' or bookmaker == 'pinnacle'"), pd.Timestamp("2026-10-24T13:10Z"), fights=CARD)["market"]) == {"h2h"}


def test_a_started_segment_is_not_priced():
    snap = _rows("e2", "Nicolle Caliari", "Iasmin Lucindo", "2026-10-24T13:00:00Z", {"pinnacle": (300, -400), "fanduel": (330, -430)})
    assert ufc.evaluate(snap, pd.Timestamp("2026-10-24T14:05Z"), fights=CARD).empty


def _fight(**kw):
    base = {"done": True, "a_name": "Alexander Volkanovski", "b_name": "Movsar Evloev", "a_win": True, "b_win": False,
            "seconds": 1500.0}
    return pd.Series(base | kw)


def test_outcomes_moneyline_draw_and_rounds():
    ml = {"market": "h2h", "side": "Alex Volkanovski"}
    assert grading.ufc_outcome(_fight(), ml) == "won"
    assert grading.ufc_outcome(_fight(a_win=False, b_win=True), ml) == "lost"
    assert grading.ufc_outcome(_fight(a_win=False, b_win=False), ml) == "push"          # draw / no contest
    over = {"market": "totals", "side": "Over", "point": 4.5}
    assert grading.ufc_outcome(_fight(seconds=4 * 300 + 151), over) == "won"             # 2:31 of round 5
    assert grading.ufc_outcome(_fight(seconds=4 * 300 + 149), over) == "lost"
    assert grading.ufc_outcome(_fight(done=False), over) is None


def test_close_only_from_a_pull_after_the_bet():
    r = {"event_id": "e1", "commence_time": "2026-10-24T18:00:00Z", "created_at": "2026-10-24T13:00:30+00:00",
         "market": "h2h", "side": "Movsar Evloev", "book": "draftkings", "point": None}
    own = _rows("e1", "Movsar Evloev", "Alex Volkanovski", "2026-10-24T13:00:00Z", {"pinnacle": (-110, -110)})
    assert grading.ufc_close(r, [own]) is None
    later = _rows("e1", "Movsar Evloev", "Alex Volkanovski", "2026-10-24T17:50:00Z", {"pinnacle": (-150, 130)})
    assert grading.ufc_close(r, [own, later]) > 0.55
    after_start = _rows("e1", "Movsar Evloev", "Alex Volkanovski", "2026-10-24T18:05:00Z", {"pinnacle": (-300, 250)})
    assert grading.ufc_close(r, [own, later, after_start]) < 0.65


def test_grade_ufc_settles_and_closes():
    picks = pd.DataFrame([{"league": "ufc", "status": "open", "commence_time": "2026-10-24T18:00:00Z", "event_id": "e1",
                           "matchup": "Alex Volkanovski vs Movsar Evloev", "market": "h2h", "side": "Movsar Evloev",
                           "price": 105.0, "units_flat": 1.0, "book": "draftkings", "point": None,
                           "created_at": "2026-10-24T13:00:30+00:00", "profit_flat": None, "p_close": None, "clv": None,
                           "graded_at": None}])
    fights = pd.DataFrame([_fight(a_win=False, b_win=True)])
    later = _rows("e1", "Movsar Evloev", "Alex Volkanovski", "2026-10-24T17:50:00Z", {"pinnacle": (-110, -110)})
    out = grading.grade_ufc(picks, fights=fights, now=pd.Timestamp("2026-10-25T03:00Z"), snaps=[later])
    assert out.loc[0, "status"] == "won" and out.loc[0, "profit_flat"] == 1.05 and out.loc[0, "clv"] > 0


def test_open_ufc_lines_get_a_closing_look(monkeypatch):
    rows = pd.DataFrame([{"league": "ufc", "status": "open", "kind": "game_line", "market": "totals", "event_id": "e1",
                          "created_at": "2026-10-24T13:00:30+00:00"},
                         {"league": "nhl", "status": "open", "kind": "game_line", "market": "totals", "event_id": "n1",
                          "created_at": "2026-10-24T13:00:30+00:00"}])
    monkeypatch.setattr("betlab.ledger.load", lambda path=None: rows)
    assert list(pregame.open_rows("ufc")["event_id"]) == ["e1", "e1"]      # picks and leans files
    assert pregame.open_rows("nhl").empty


NOW = pd.Timestamp("2026-10-24T13:00:00Z")      # 9 AM ET, UFC 333 day
MMA = "mma_mixed_martial_arts"


def _ev(eid, home, away, start="2026-10-24T14:00:00Z"):
    return {"id": eid, "commence_time": start, "home_team": home, "away_team": away}


class FakeClient:
    def __init__(self, events):
        self._events, self.calls = events, []

    def events(self, sport):
        return self._events if sport == MMA else []

    def odds(self, sport, markets=None, priority="normal", event_ids=None):
        self.calls.append(("odds", tuple(event_ids or ()), tuple(markets or ())))
        return [{**e, "bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
            {"name": e["home_team"], "price": -110}, {"name": e["away_team"], "price": -110}]}]}]}
                for e in self._events if e["id"] in (event_ids or [])]

    def event_odds(self, sport, eid, markets, priority="normal"):
        self.calls.append(("event", eid, tuple(markets)))
        e = next(x for x in self._events if x["id"] == eid)
        return {**e, "bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
            {"name": e["home_team"], "price": -150}, {"name": e["away_team"], "price": 130}]}]}]}


@pytest.fixture
def ufc_day(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setitem(config.settings()["schedule"], "pregame", {"ufc": [20, 60]})
    monkeypatch.setattr(ufc, "card_fights", lambda now: CARD)
    monkeypatch.setattr(pregame, "open_rows", lambda league: pd.DataFrame(columns=["event_id", "market", "created_at"]))
    return tmp_path



def test_pregame_pulls_ufc_fights_by_their_own_segment(ufc_day):
    """The feed says 10 AM for every fight and mixes in other promotions; the main card waits for its own window."""
    client = FakeClient([_ev("prelim", "Nicolle Caliari", "Iasmin Lucindo"), _ev("main", "Movsar Evloev", "Alex Volkanovski"),
                         _ev("other", "Robbie Lawler", "Khamzat Chimaev", "2026-10-24T13:40:00Z")])
    out = pregame.run(client, NOW)
    assert client.calls == [("odds", ("prelim",), ("h2h", "totals"))] and out[0].startswith("ufc: 1 game(s)")
    client.calls.clear()
    pregame.run(client, pd.Timestamp("2026-10-24T17:00:00Z"))              # 1 PM ET: the main card's window
    assert client.calls == [("odds", ("main",), ("h2h", "totals"))]
    snap = pregame.latest(MMA, "pick")
    assert set(snap.loc[snap["event_id"] == "main", "commence_time"]) == {"2026-10-24T18:00:00Z"}


def test_an_open_ufc_bet_gets_a_closing_look_with_the_lines(ufc_day, monkeypatch):
    client = FakeClient([_ev("main", "Movsar Evloev", "Alex Volkanovski")])
    t = pd.Timestamp("2026-10-24T17:00:00Z")
    pregame.run(client, t)                                                   # the main card's pull, 1 PM
    # logged after that pull: pulls are stamped with the real clock, not the test's `now` (this read a fixed
    # 17:00:30 and failed once the real clock passed it, Oct 24)
    logged = (pd.Timestamp.now(tz="UTC") + pd.Timedelta(minutes=1)).isoformat()
    monkeypatch.setattr(pregame, "open_rows", lambda league: pd.DataFrame(
        [{"event_id": "main", "market": "h2h", "created_at": logged}]))
    client.calls.clear()
    out = pregame.run(client, pd.Timestamp("2026-10-24T17:45:00Z"))         # last tick before 2 PM
    assert client.calls == [("event", "main", ("h2h",))] and "closing look" in out[0]
    snap = pregame.latest(MMA, "pick")
    assert set(snap.loc[snap["event_id"] == "main", "price"]) == {-150, 130}


from betlab import publish  # noqa: E402
from betlab.cards import analysis_ufc  # noqa: E402


def test_dk_method_chances_drop_the_margin_and_follow_our_fighter_order():
    f = pd.Series({"a_ko": 450, "a_sub": 2000, "a_dec": 175, "b_ko": 1000, "b_sub": 1200, "b_dec": 130,
                   "distance_yes": -275, "distance_no": 200, "total_line": 4.5, "over": -298, "under": 220,
                   "a_ml": -112, "b_ml": -108})
    dk = analysis_ufc.dk_props(f)
    assert abs(sum(v["p"] for v in dk["method"].values()) - 1) < 1e-3 and 0.15 < dk["method_margin"] < 0.25
    sw = analysis_ufc._swap(dk)
    assert sw["method"]["a_dec"] == dk["method"]["b_dec"] and abs(sw["ml"]["p_a"] - (1 - dk["ml"]["p_a"])) < 1e-6


def test_form_and_class_rates_from_past_fights():
    hist = pd.DataFrame([
        {"a_id": "1", "b_id": "2", "a_name": "X", "b_name": "Y", "a_win": True, "b_win": False, "result": "kotko",
         "period": 1, "event_start": "2025-01-01T00:00Z", "note": "Featherweight", "rounds": 3},
        {"a_id": "3", "b_id": "1", "a_name": "Z", "b_name": "X", "a_win": True, "b_win": False, "result": "decision---split",
         "period": 3, "event_start": "2026-01-01T00:00Z", "note": "Featherweight", "rounds": 3}] * 10)
    fm = analysis_ufc.fighter_form(hist, "1", pd.Timestamp("2026-10-24T18:00Z"))
    assert fm["fights"] == 20 and fm["wins"] == {"ko": 10} and fm["losses"] == {"dec": 10} and fm["last"][0]["result"] == "L"
    assert analysis_ufc.class_rates(hist, "Featherweight", 3) == {"n": 20, "distance": 0.5, "ko": 0.5, "sub": 0.0}
    assert analysis_ufc.class_rates(hist, "Featherweight", 5) is None             # too few fights


def test_a_fight_page_and_its_offers_share_one_game():
    rows = publish.build_rows({"ufc": {"games": [{"event_id": "e1", "commence_time": "2026-10-24T18:00:00Z",
                                                  "matchup": "Alex Volkanovski vs Movsar Evloev"}]},
                               "card": {"leans": [{"pick_id": "p1", "league": "ufc", "event_id": "e1", "commence_time": "2026-10-24T18:00:00Z",
                                                   "matchup": "Alex Volkanovski vs Movsar Evloev", "market": "h2h", "label": "Movsar Evloev ML",
                                                   "price": 100, "ev": 0.01, "book": "novig"}]}},
                              None, None, None, [], set())
    assert [g["game_id"] for g in rows["games"]] == ["ufc:e1"]
    assert rows["offers"][0]["game_id"] == "ufc:e1" and rows["game_analysis"][0]["kind"] == "ufc"


from betlab.models import ufc as fight_model  # noqa: E402


def _hist(n=400, seed=1):
    """Synthetic fights: fighter i beats j when i < j (a strict ladder), by KO half the time."""
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n):
        i, j = sorted(rng.choice(40, 2, replace=False))
        a_first = rng.random() < 0.5
        a, b = (i, j) if a_first else (j, i)
        rows.append({"fight_id": str(k), "event_start": (pd.Timestamp("2021-01-01") + pd.Timedelta(days=3 * k)).isoformat(),
                     "a_id": str(a), "b_id": str(b), "a_name": f"F{a}", "b_name": f"F{b}", "a_win": a_first, "b_win": not a_first,
                     "result": "kotko" if k % 2 else "decision---unanimous", "seconds": 300.0 if k % 2 else 900.0,
                     "rounds": 3, "note": "Lightweight", **{f"{s}_{c}": 10.0 for s in "ab" for c in ("sig", "sig_att", "td", "td_att", "kd", "subatt", "ctrl")}})
    return pd.DataFrame(rows)



def test_features_use_only_earlier_fights():
    f = fight_model.features(_hist(50))
    first = f.iloc[0]
    assert first["a_elo"] == first["b_elo"] == fight_model.ELO_START and first["debut_a"] and first["debut_b"]
    winner = first["a_name"] if first["a_win"] else first["b_name"]
    later = f[(f["a_name"] == winner) | (f["b_name"] == winner)].iloc[1:2]
    if len(later):
        side = "a" if later.iloc[0]["a_name"] == winner else "b"
        assert later.iloc[0][f"{side}_elo"] > fight_model.ELO_START


def test_the_win_model_learns_a_ladder_and_ignores_listing_order():
    f = fight_model.features(_hist(600))
    model = fight_model.fit_win(f.iloc[:500])
    test = f.iloc[500:]
    p = fight_model.predict_win(model, test)
    assert np.mean((p > 0.5) == test["a_win"].to_numpy()) > 0.7
    swapped = test.rename(columns=lambda c: "b_" + c[2:] if c.startswith("a_") else "a_" + c[2:] if c.startswith("b_") else c)
    assert np.allclose(fight_model.predict_win(model, swapped), 1 - p)


def test_same_fight_parlays_add_up_and_follow_how_a_fighter_wins():
    fight = {"rounds": 3, "fighters": [{"name": "Finisher"}, {"name": "Grinder"}],
             "books": [{"label": "Finisher ML", "p_market": 0.7}, {"label": "Grinder ML", "p_market": 0.3}],
             "dk": {"method": {"a_ko": {"p": 0.5, "price": 100}, "a_sub": {"p": 0.1, "price": 600}, "a_dec": {"p": 0.1, "price": 500},
                               "b_ko": {"p": 0.03, "price": 2500}, "b_sub": {"p": 0.02, "price": 3000}, "b_dec": {"p": 0.25, "price": 250}}}}
    timing = {3: [60.0 * k for k in range(1, 15)]}                       # finishes spread over 14 minutes
    rows = {c["label"]: c for c in analysis_ufc.same_fight(fight, timing, (1.5, 0.5, "pinnacle"))}
    assert abs(rows["Finisher wins inside the distance"]["p"] + rows["Finisher wins by decision"]["p"] - 0.7) < 1e-3
    assert abs(rows["Finisher wins + under 1.5 rounds"]["p"] + rows["Finisher wins + over 1.5 rounds"]["p"] - 0.7) < 1e-3
    assert rows["Finisher wins + under 1.5 rounds"]["p"] > rows["Finisher wins + under 1.5 rounds"]["naive"]   # 0.35
    assert rows["Grinder wins + over 1.5 rounds"]["p"] > rows["Grinder wins + over 1.5 rounds"]["naive"]


from betlab import tracking_ufc  # noqa: E402


def test_the_tracker_keeps_first_and_last_looks_then_grades(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking_ufc, "PATH", tmp_path / "ufc_lines.csv")
    g = {"game_ref": "ufc:600061267:401999", "commence_time": "2026-10-24T18:00:00Z", "event": "UFC 333", "segment": "Main card",
         "weight_class": "Featherweight", "rounds": 5,
         "fighters": [{"name": "Alex Volkanovski"}, {"name": "Movsar Evloev"}],
         "books": [{"label": "Alex Volkanovski ML", "p_market": 0.49}],
         "dk": {"ml": {"a": -112, "b": -108, "p_a": 0.5}, "distance": {"yes": -275, "no": 200, "p_yes": 0.7}},
         "model": {"p_a": 0.47, "p_dist": 0.6, "debut_a": False, "debut_b": False}}
    assert tracking_ufc.record([g], pd.Timestamp("2026-10-23T20:00Z")) == 1
    g2 = g | {"dk": {"ml": {"a": -130, "b": 110, "p_a": 0.55}}}
    tracking_ufc.record([g2], pd.Timestamp("2026-10-24T17:00Z"))
    tracking_ufc.record([g2 | {"dk": {"ml": {"a": -200, "b": 170, "p_a": 0.65}}}], pd.Timestamp("2026-10-24T18:30Z"))   # started
    row = tracking_ufc.load().iloc[0]
    assert row["first_a_ml"] == -112 and row["last_a_ml"] == -130 and row["first_distance_yes"] == -275
    fc = pd.DataFrame([{"fight_id": "401999", "done": True, "a_name": "Movsar Evloev", "b_name": "Alexander Volkanovski",
                        "a_win": True, "b_win": False, "result": "decision---unanimous", "period": 5, "seconds": 1500.0}])
    assert tracking_ufc.grade(pd.Timestamp("2026-10-25T03:00Z"), fights_of=lambda eid: fc) == 1
    row = tracking_ufc.load().iloc[0]
    assert row["winner"] == "b" and row["kind"] == "dec"                 # Evloev is our b
    assert "1 graded fights" in tracking_ufc.summary()[0]


def test_a_cancelled_fight_voids_its_bet_once_the_card_is_over():
    picks = pd.DataFrame([{"league": "ufc", "status": "open", "commence_time": "2026-10-24T18:00:00Z", "event_id": "e9",
                           "matchup": "Gone Fighter vs Other Guy", "market": "h2h", "side": "Gone Fighter", "price": 150.0,
                           "units_flat": 1.0, "book": "fanduel", "point": None, "created_at": "2026-10-24T13:00:00+00:00",
                           "profit_flat": None, "p_close": None, "clv": None, "graded_at": None}])
    fights = pd.DataFrame([_fight()])                                # the card, finished, without that fight
    early = grading.grade_ufc(picks, fights=fights, now=pd.Timestamp("2026-10-24T22:00Z"), snaps=[])
    assert early.loc[0, "status"] == "open"                          # waits 12 hours after its start
    out = grading.grade_ufc(picks, fights=fights, now=pd.Timestamp("2026-10-25T09:00Z"), snaps=[])
    assert out.loc[0, "status"] == "void" and out.loc[0, "profit_flat"] == 0


def test_the_ufc_news_source_changes_when_the_card_does(monkeypatch):
    from betlab import news

    card = {"cards": {"main": {"competitions": [{"note": "Featherweight", "status": {"type": {"detail": "Scheduled"}},
        "competitors": [{"athlete": {"displayName": "Alex Volkanovski"}}, {"athlete": {"displayName": "Movsar Evloev"}}]}]}}}
    monkeypatch.setattr(src, "scheduled", lambda day: pd.DataFrame({"espn_event": ["1"]}))
    monkeypatch.setattr(src, "_get", lambda url, params=None: card)
    before = news.fingerprint({"card": news._ufc_card("20261024")}, "Movsar Evloev", "Alex Volkanovski")
    card["cards"]["main"]["competitions"][0]["note"] = "Catchweight (150 lbs)"
    after = news.fingerprint({"card": news._ufc_card("20261024")}, "Movsar Evloev", "Alex Volkanovski")
    assert news.changed(before, after) == ["card"]


def test_ufc_parlay_grades_moneylines_and_total_rounds():
    """+ Add's UFC slips (Oct 25): a leg is a fighter's moneyline or the fight's total rounds, by its ESPN fight ref."""
    from betlab import fun_ledger
    fights = pd.DataFrame([{"fight_id": "1", **_fight(seconds=400.0)}, {"fight_id": "2", **_fight(a_win=False, b_win=True)}])
    df = pd.DataFrame([{**{c: None for c in fun_ledger.COLUMNS}, "sgp_id": "custom-fd-snap-x", "sport": "ufc",
                        "status": "open", "price": 300.0, "stake": 1.0, "marked": True,
                        "legs": json.dumps(["Alexander Volkanovski ML", "Under 1.5 rounds", "Over 2.5 rounds"]),
                        "leg_games": json.dumps(["ufc:600:1", "ufc:600:1", "ufc:600:2"]), "game_id": "ufc:600:1",
                        "book": "fanduel"}])
    assert fun_ledger._grade_ufc(df, df, fights) == 1
    assert [x["result"] for x in json.loads(df.at[0, "leg_results"])] == ["won", "won", "won"]
    assert df.at[0, "status"] == "won"
