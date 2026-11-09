"""The European cups (Mike, Oct 12): priced like the leagues, graded from ESPN's score and our own close."""

import numpy as np
import pandas as pd

from betlab import config, grading
from betlab.cards import fun_soccer, soccer
from betlab.models import soccer as S


def _snap(event_id="c1", kickoff="2026-10-13T19:00:00Z", ts="2026-10-13T18:30:00Z"):
    rows = []
    for b, prices in (("pinnacle", (150, 240, 190)), ("fanduel", (160, 230, 180)), ("draftkings", (145, 250, 185))):
        for team, pr in zip(("Arsenal", "Draw", "Olympiacos"), prices):
            rows.append({"snapshot_ts": ts, "sport_key": "soccer_uefa_champs_league", "event_id": event_id,
                         "commence_time": kickoff, "home_team": "Arsenal", "away_team": "Olympiacos", "bookmaker": b,
                         "market": "h2h", "outcome": team, "player": None, "point": None, "price": pr})
    return pd.DataFrame(rows)


def test_the_cups_are_soccer_leagues_everywhere():
    from betlab import alerts, pregame, publish
    from betlab.sources import espn_soccer

    for lg in soccer.CUPS:
        assert lg in soccer.LEAGUES and lg in pregame.SOCCER and lg in publish.SOCCER and lg in grading.GRADERS
        assert lg in espn_soccer.SLUGS and lg in alerts.LEAGUE and lg in soccer.NAMES
        assert config.settings()["leagues"][lg]["family"] == "soccer"
        assert publish.league_of(lg) == "soccer"
    assert soccer.league_of("soccer_uefa_europa_conference_league") == "uecl"
    assert set(soccer.DOMESTIC).isdisjoint(soccer.CUPS)


def test_a_cup_match_prices_at_both_books():
    offers = pd.concat([soccer.evaluate(_snap(), pd.Timestamp("2026-10-13T12:00:00Z"), book=b)
                        for b in ("fanduel", "draftkings")], ignore_index=True)
    assert set(offers["league"]) == {"ucl"} and len(offers) == 6
    assert set(offers["market_source"]) == {"pinnacle"}


def test_cup_picks_grade_from_espn_and_our_own_close(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    day = tmp_path / "odds" / "soccer_uefa_champs_league" / "2026-10-13"
    day.mkdir(parents=True)
    _snap().to_parquet(day / "143000_pick.parquet")
    _snap(ts="2026-10-13T19:30:00Z").assign(price=999).to_parquet(day / "153000_pick.parquet")   # after kickoff: ignored
    import betlab.fun_ledger as FL
    monkeypatch.setattr(FL, "_soccer_result", lambda lg, h, a, k: {"hg": 2, "ag": 1})
    picks = pd.DataFrame([{"league": "ucl", "event_id": "c1", "commence_time": "2026-10-13T19:00:00Z",
                           "matchup": "Arsenal vs Olympiacos", "market": "h2h", "side": "Arsenal", "price": 160.0,
                           "units_flat": 1.0, "status": "open", "player": None, "point": None}])
    out = grading.grade_soccer(picks, "ucl", now=pd.Timestamp("2026-10-14T00:00:00Z"))
    r = out.iloc[0]
    assert r["status"] == "won" and r["profit_flat"] == 1.6
    close = soccer.close_3way("ucl", "c1", "2026-10-13T19:00:00Z")
    assert close is not None and abs(sum(close) - 1) < 1e-9 and r["p_close"] == round(close[0], 4)


def test_a_cup_bet_gets_no_close_from_the_pull_it_came_from(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    day = tmp_path / "odds" / "soccer_uefa_champs_league" / "2026-10-13"
    day.mkdir(parents=True)
    _snap(ts="2026-10-13T18:15:00Z").to_parquet(day / "141500_pick.parquet")
    import betlab.fun_ledger as FL
    monkeypatch.setattr(FL, "_soccer_result", lambda lg, h, a, k: {"hg": 1, "ag": 1})
    picks = pd.DataFrame([{"league": "ucl", "event_id": "c1", "commence_time": "2026-10-13T19:00:00Z",
                           "created_at": "2026-10-13T18:15:26+00:00", "matchup": "Arsenal vs Olympiacos",
                           "market": "h2h", "side": "Draw", "price": 230.0, "units_flat": 1.0, "status": "open",
                           "player": None, "point": None}])
    r = grading.grade_soccer(picks, "ucl", now=pd.Timestamp("2026-10-14T00:00:00Z")).iloc[0]
    assert r["status"] == "won" and pd.isna(r.get("p_close")) and pd.isna(r.get("clv"))
    _snap(ts="2026-10-13T18:50:00Z").to_parquet(day / "145000_pick.parquet")        # a later pull is a close
    r = grading.grade_soccer(picks, "ucl", now=pd.Timestamp("2026-10-14T00:00:00Z")).iloc[0]
    assert r["p_close"] == round(soccer.close_3way("ucl", "c1", "2026-10-13T19:00:00Z")[1], 4)


def test_a_whole_number_goals_line_is_read_with_its_push():
    sm = S.score_matrix(1.6, 1.2)
    i, j = np.indices(sm.shape)
    over3, push3 = sm[i + j > 3].sum(), sm[i + j == 3].sum()
    t = {"h": float(sm[i > j].sum()), "a": float(sm[i < j].sum()), "overs": {3.0: float(over3 / (1 - push3))}}
    lh, la, err = fun_soccer.fit_goals(t)
    assert err < 0.005 and abs(lh - 1.6) < 0.1 and abs(la - 1.2) < 0.1


def test_cup_players_are_read_with_their_own_league():
    from betlab.cards import props_soccer

    seen = {}

    class Fake:
        dispersion = {}

    def fake_features(df, xg=None):
        seen["leagues"] = df[df["event_id"] == "e9"].set_index("player_id")["league"].to_dict()
        return df.assign(starter=True).iloc[0:0]

    import betlab.cards.props_soccer as PSC
    hist = pd.DataFrame({"event_id": ["h1", "h2"], "player_id": ["10", "20"], "league": ["epl", "serie_a"],
                         "kickoff": ["2026-10-01", "2026-10-02"], "season": [2027, 2027], "starter": [True, True]})
    squad = pd.DataFrame({"event_id": ["e9"] * 3, "player_id": ["10", "20", "30"], "team": ["A", "A", "B"],
                          "home": [1, 1, 0], "starter": [True] * 3})
    orig = PSC.PS.features
    PSC.PS.features = fake_features
    try:
        assert props_soccer.means([(squad, "ucl", None)], history=hist, model=Fake()) == {}
    finally:
        PSC.PS.features = orig
    assert seen["leagues"] == {"10": "epl", "20": "serie_a"}                  # player 30 has no history: no read
