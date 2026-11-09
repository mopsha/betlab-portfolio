"""Soccer: the football-data.co.uk loader, the Poisson ratings, and the backtest's scoring."""

import numpy as np
import pandas as pd
import pytest

from betlab import backtest_soccer as B
from betlab.models import soccer as M
from betlab.sources import soccer as S


def toy_league(seasons=(2024, 2025), seed=0):
    """Four teams play each other home and away every few days; STR scores far more."""
    rng = np.random.default_rng(seed)
    strength = {"STR": 0.5, "MID": 0.0, "AVG": 0.0, "WEAK": -0.4}
    teams = list(strength)
    rows, day = [], pd.Timestamp("2023-08-12")
    for s in seasons:
        for rnd in range(18):
            for i, h in enumerate(teams):
                for a in teams[i + 1:]:
                    home, away = (h, a) if rnd % 2 == 0 else (a, h)
                    lh = np.exp(0.25 + 0.25 + strength[home] - strength[away] * 0.5)
                    la = np.exp(0.25 + strength[away] - strength[home] * 0.5)
                    rows.append({"league": "toy", "season": s, "date": day, "home": home, "away": away,
                                 "hg": rng.poisson(lh), "ag": rng.poisson(la), "hst": np.nan, "ast": np.nan})
            day += pd.Timedelta(days=4)
    return pd.DataFrame(rows)


def test_season_codes():
    assert S.season_code(2025) == "2425" and S.season_code(2000) == "9900"
    assert S.current_season(pd.Timestamp("2026-09-25")) == 2027 and S.current_season(pd.Timestamp("2026-05-01")) == 2026


def test_no_vig_and_the_closing_fallback_order():
    m = pd.DataFrame({f"{p}_{s}": [np.nan] for p in ("pin_close", "bfx_close", "avg_close") for s in "hda"})
    m.loc[0, ["avg_close_h", "avg_close_d", "avg_close_a"]] = [2.0, 3.5, 4.0]
    m.loc[0, ["bfx_close_h", "bfx_close_d", "bfx_close_a"]] = [2.1, 3.6, 4.2]
    c = S.closing_1x2(m)[0]
    assert c.sum() == pytest.approx(1) and c[0] == pytest.approx(S.no_vig(np.array([[2.1, 3.6, 4.2]]))[0, 0])


def test_ratings_find_the_strong_team_and_probabilities_add_up():
    m = toy_league()
    r = M.fit(m, "2025-12-01")
    assert max(r.attack, key=r.attack.get) == "STR" and min(r.attack, key=r.attack.get) == "WEAK"
    assert r.home > 0
    pr = M.probs(r, "STR", "WEAK")
    assert pr["h"] + pr["d"] + pr["a"] == pytest.approx(1) and pr["h"] > 0.5
    assert sum(pr["diff"].values()) == pytest.approx(1)
    assert M.score_matrix(1.4, 1.1).sum() == pytest.approx(1)


def test_a_promoted_team_starts_below_average():
    m = toy_league(seasons=(2024,))
    new = m.assign(season=2025, date=m["date"] + pd.Timedelta(days=400))
    new = new[(new["home"] != "WEAK") & (new["away"] != "WEAK")]
    r = M.fit(pd.concat([m, new]), new["date"].min() + pd.Timedelta(days=1))
    lh, _ = r.expected("NEWBIE", "AVG")
    typical = np.exp(r.mu + r.home + np.mean(list(r.attack.values())) - r.defense["AVG"])
    assert "NEWBIE" not in r.attack and lh < typical      # an unknown (promoted) side is expected to score less


def test_backtest_scores_a_perfect_market_as_unbeatable():
    m = toy_league()
    pred = B.predict(m, [2025])
    # a "market" that knows the true probabilities better than any model: the model's own, sharpened
    pred[["c_h", "c_d", "c_a"]] = pred[["m_h", "m_d", "m_a"]].to_numpy()
    ev = B.evaluate(pred.assign(league="toy"), "c", boot=5)
    assert len(ev) == 1 and ev["model"].iloc[0] == pytest.approx(ev["market"].iloc[0])
    assert B.best_w(pred[["c_h", "c_d", "c_a"]].to_numpy(), pred[["m_h", "m_d", "m_a"]].to_numpy(), pred["res"].to_numpy()) in np.linspace(0, 1, 21)


# ---------------------------------------------------------------- live: card, tracker, grading

def snap_3way(home="Leeds United", away="Man United", fd=(150, 240, 190), sharp=(140, 250, 210), when="2026-10-10T14:00:00Z"):
    rows = []
    for book, prices in (("fanduel", fd), ("pinnacle", sharp)):
        for outcome, price in zip((home, "Draw", away), prices):
            rows.append({"snapshot_ts": "2026-10-09T14:00:00Z", "sport_key": "soccer_epl", "event_id": "e1",
                         "commence_time": when, "home_team": home, "away_team": away, "bookmaker": book,
                         "market": "h2h", "last_update": "", "outcome": outcome, "player": None, "point": None,
                         "price": price})
    return pd.DataFrame(rows)


def test_card_prices_three_way_against_the_sharp_no_vig():
    from betlab import odds_math as om
    from betlab.cards import soccer as C

    off = C.evaluate(snap_3way(), pd.Timestamp("2026-10-09T15:00:00Z"))
    assert len(off) == 3 and set(off["league"]) == {"epl"} and (off["w_model"] == 0).all()
    assert off["p_market"].sum() == pytest.approx(1) and (off["p_model"] == off["p_market"]).all()
    home = off.set_index("side").loc["Leeds United"]
    assert home["ev"] == pytest.approx(om.expected_value(home["p_market"], 150))
    assert home["matchup"] == "Leeds United vs Man United" and home["label"] == "Leeds United to win"
    assert C.evaluate(snap_3way(), pd.Timestamp("2026-10-11T00:00:00Z")).empty      # started: nothing


def test_fixture_matching_needs_both_teams_and_the_date():
    fd = pd.DataFrame({"date": pd.to_datetime(["2026-10-10", "2026-10-10", "2026-10-17"]),
                       "home": ["Man United", "Leeds", "Leeds"], "away": ["Everton", "Fulham", "Everton"],
                       "hg": [1, 2, 0], "ag": [0, 2, 1]})
    m = S.find_match(fd, "Leeds United", "Fulham", "2026-10-10T14:00:00Z")
    assert m is not None and m["home"] == "Leeds" and m["hg"] == 2
    assert S.find_match(fd, "Leeds United", "Everton", "2026-10-10T14:00:00Z") is None     # wrong date
    assert S.find_match(fd, "Manchester United", "Everton", "2026-10-10T16:00:00Z")["home"] == "Man United"


def test_tracker_and_picks_grade_from_the_result_and_close(tmp_path, monkeypatch):
    from betlab import grading
    from betlab import tracking_soccer as TS
    from betlab.cards import soccer as C

    monkeypatch.setattr(TS, "PATH", tmp_path / "soccer_lines.csv")
    off = C.evaluate(snap_3way(), pd.Timestamp("2026-10-09T15:00:00Z"))
    assert TS.record(off, pd.Timestamp("2026-10-09T15:00:00Z")) == 3
    later = C.evaluate(snap_3way(fd=(160, 240, 180)), pd.Timestamp("2026-10-10T10:00:00Z"))
    TS.record(later, pd.Timestamp("2026-10-10T10:00:00Z"))
    df = TS.load().set_index("side")
    assert df.loc["Leeds United", "first_price"] == 150 and df.loc["Leeds United", "fd_price"] == 160
    lookup = lambda lg, h, a, k: {"hg": 2, "ag": 1, "close": (0.45, 0.27, 0.28), "close_source": "Betfair Exchange"}
    assert TS.grade(pd.Timestamp("2026-10-11T00:00:00Z"), lookup) == 3
    g = TS.load().set_index("side")
    assert g.loc["Leeds United", "won"] == 1 and g.loc["Draw", "won"] == 0 and g.loc["Man United", "p_close"] == 0.28
    assert TS.summary()["graded"] == 3
    picks = pd.DataFrame([{"league": "epl", "status": "open", "matchup": "Leeds United vs Man United",
                           "side": "Leeds United", "price": 150.0, "units_flat": 1.0, "commence_time": "2026-10-10T14:00:00Z"},
                          {"league": "epl", "status": "open", "matchup": "Leeds United vs Man United",
                           "side": "Draw", "price": 240.0, "units_flat": 1.0, "commence_time": "2026-10-10T14:00:00Z"}])
    out = grading.grade_soccer(picks, "epl", pd.Timestamp("2026-10-11T00:00:00Z"), lookup)
    assert list(out["status"]) == ["won", "lost"] and out.loc[0, "profit_flat"] == 1.5
    assert out.loc[0, "clv"] > 0                                    # +150 against a 45% close


def test_view_lists_every_tracked_match_with_its_three_way_lines():
    from betlab import publish
    from betlab import tracking_soccer as TS

    def line(ev, side, price, p, when="2026-10-09T19:00:00Z"):
        return {"line_id": TS.line_id(ev, side), "league": "la_liga", "event_id": ev, "commence_time": when,
                "home": "Málaga", "away": "Espanyol", "side": side, "first_seen": "2026-10-08T13:56:56+00:00",
                "first_price": price + 10, "first_p_market": p, "updated_at": "2026-10-09T01:15:11+00:00",
                "fd_price": price, "p_market": p, "market_source": "pinnacle", "status": "open"}

    df = pd.DataFrame([line("e1", "Espanyol", 170, 0.36), line("e1", "Draw", 210, 0.30), line("e1", "Málaga", 180, 0.34),
                       line("old", "Draw", 210, 0.30, when="2026-10-01T19:00:00Z")])
    v = TS.view(df, now=pd.Timestamp("2026-10-09T18:00:00Z"))
    assert [g["event_id"] for g in v["games"]] == ["e1"]                  # last week's match is gone
    g = v["games"][0]
    assert g["competition"] == "La Liga" and g["matchup"] == "Málaga vs Espanyol"
    assert [o["side"] for o in g["lines"]] == ["Málaga", "Draw", "Espanyol"]   # home, draw, away
    assert g["lines"][0]["ev"] == pytest.approx(0.34 * 2.8 - 1, abs=1e-4)

    # no pick, lean or ticket: the match still becomes a game, keyed like the card's soccer lines
    rows = publish.build_rows({"soccer": v}, None, None, None, [], current=set())
    game = next(r for r in rows["games"] if r["game_id"] == "soccer:e1")
    assert game["home"] == "Málaga" and game["away"] == "Espanyol" and game["odds_event_id"] == "e1"
    assert any(a["kind"] == "soccer" and a["game_id"] == "soccer:e1" for a in rows["game_analysis"])


def test_tracker_keeps_fanduels_own_price_and_only_three_way_lines(tmp_path, monkeypatch):
    """Oct 13: after books.select a 3-way row could carry DraftKings' price (logged as fd_price), and goals, BTTS
    and scorer rows reached the 3-way tracker keyed only by side."""
    from betlab import tracking_soccer as TS

    monkeypatch.setattr(TS, "PATH", tmp_path / "soccer_lines.csv")
    base = {"league": "ucl", "event_id": "e1", "commence_time": "2026-10-13T19:00:00Z", "matchup": "Villarreal vs Napoli",
            "p_market": 0.29, "market_source": "Pinnacle no-vig"}
    offers = pd.DataFrame([
        base | {"market": "h2h", "side": "Draw", "price": 255.0, "book": "draftkings", "other_book": "fanduel", "other_price": 250.0},
        base | {"market": "h2h", "side": "Villarreal", "price": 115.0, "book": "fanduel", "other_book": "draftkings", "other_price": 115.0},
        base | {"market": "h2h", "side": "Napoli", "price": 235.0, "book": "draftkings", "other_book": None, "other_price": None},
        base | {"market": "btts", "side": "Yes", "price": -125.0, "book": "fanduel", "other_book": None, "other_price": None},
        base | {"market": "player_goal_scorer_anytime", "side": "Yes", "price": -195.0, "book": "draftkings",
                "other_book": None, "other_price": None}])
    assert TS.record(offers, pd.Timestamp("2026-10-13T18:15:00Z")) == 2
    got = TS.load().set_index("side")["fd_price"].to_dict()
    assert got == {"Draw": 250.0, "Villarreal": 115.0}        # FanDuel's price; DraftKings-only and non-3-way left out


def test_tracker_records_with_duplicate_line_ids_already_in_the_file(tmp_path, monkeypatch):
    """Oct 13: goals/scorer rows left two rows per 'Yes' line id, and every card failed from 5:15 PM."""
    from betlab import tracking_soccer as TS

    monkeypatch.setattr(TS, "PATH", tmp_path / "soccer_lines.csv")
    dup = {c: None for c in TS.COLUMNS} | {"line_id": TS.line_id("e0", "Yes"), "league": "ucl", "event_id": "e0",
                                           "side": "Yes", "commence_time": "2026-10-13T19:00:00Z", "status": "open"}
    TS.save(pd.DataFrame([dup, dup | {"fd_price": -150.0}]))
    offers = pd.DataFrame([{"league": "ucl", "event_id": "e1", "commence_time": "2099-01-01T00:00:00Z",
                            "matchup": "A vs B", "side": "Draw", "price": 250.0, "p_market": 0.3,
                            "market_source": "Pinnacle no-vig", "market": "h2h", "book": "fanduel"}])
    assert TS.record(offers, pd.Timestamp("2026-10-13T22:00:00Z")) == 1
