"""The game-flow engine: walk-forward ratings, the market's game script, matchups and the prop script lean."""

import numpy as np
import pandas as pd

from betlab import props_market as PM
from betlab.models import game_nfl as GN

TEAMS = ["AAA", "BBB", "CCC", "DDD"]


def toy_team_games(n_weeks: int = 16, seed: int = 0) -> pd.DataFrame:
    """Round-robin team-games where AAA passes much better than everyone and DDD defends the pass worst."""
    rng = np.random.default_rng(seed)
    rows = []
    start = pd.Timestamp("2025-09-07")
    for wk in range(n_weeks):
        for i, (h, a) in enumerate([(TEAMS[(wk + k) % 4], TEAMS[(wk + k + 1 + wk % 2) % 4]) for k in (0, 2)]):
            if h == a:
                continue
            for team, opp, home in ((h, a, 1), (a, h, 0)):
                pass_epa = 0.05 + (0.30 if team == "AAA" else 0) + (0.15 if opp == "DDD" else 0) + rng.normal(0, 0.05)
                dropbacks = 36 + rng.normal(0, 3)
                rushes = 26 + rng.normal(0, 3)
                plays = dropbacks + rushes
                total_epa = pass_epa * dropbacks
                rows.append({"date": start + pd.Timedelta(days=7 * wk), "team": team, "opp": opp, "home": home,
                             "pass_epa": pass_epa, "rush_epa": -0.05 + rng.normal(0, 0.05),
                             "pass_success": 0.45, "rush_success": 0.40, "pressure": 0.15 + rng.normal(0, 0.01),
                             "explosive": 0.08, "neutral_pass": 0.58, "proe": 0.0, "sec_per_play": 30 + rng.normal(0, 1),
                             "plays": plays, "rz_td": 0.55, "turnovers": 1.2, "points": 21 + 20 * total_epa / 36,
                             "dropbacks": dropbacks, "rushes": rushes, "rz_trips": 3.0, "total_epa": total_epa})
    return pd.DataFrame(rows)


def test_ratings_use_only_earlier_games_and_rank_the_best_passer_first():
    tg = toy_team_games()
    date = pd.Timestamp("2025-12-01")
    r = GN.fit_ratings(tg, date)
    later = tg.iloc[:4].assign(date=date + pd.Timedelta(days=3), pass_epa=9.0)
    assert GN.fit_ratings(pd.concat([tg, later]), date).off["pass_epa"].equals(r.off["pass_epa"])
    rk = GN.ranks(r)
    assert rk.loc["AAA", "off_pass_epa"] == 1
    assert rk.loc["DDD", "def_pass_epa"] == 4                    # allows the most: worst pass defense


def test_market_script_makes_leaders_run_and_trailers_throw():
    r = GN.fit_ratings(toy_team_games(), "2025-12-01")
    even = GN.project(r, "BBB", "CCC", market_margin_home=0.0)
    fav = GN.project(r, "BBB", "CCC", market_margin_home=10.0)
    assert fav["sides"]["BBB"]["pass_rate"] < even["sides"]["BBB"]["pass_rate"]
    assert fav["sides"]["CCC"]["pass_rate"] > even["sides"]["CCC"]["pass_rate"]
    assert abs(fav["sides"]["BBB"]["dropbacks"] + fav["sides"]["BBB"]["rushes"] - fav["sides"]["BBB"]["plays"]) < 1e-9


def test_matchups_and_script_features_point_the_same_way():
    tg = toy_team_games()
    date = pd.Timestamp("2025-12-01")
    r = GN.fit_ratings(tg, date)
    pr = GN.project(r, "DDD", "AAA", market_margin_home=0.0)
    ms = GN.matchups(r, "DDD", "AAA", lambda t: t)
    assert [abs(m["size"]) for m in ms] == sorted((abs(m["size"]) for m in ms), reverse=True)
    top = next(m for m in ms if m["offense"] == "AAA" and m["stat"] == "pass_epa")
    assert top["edge"] == "AAA" and "edge AAA" in top["text"]
    f = GN.script_features(r, tg, pr, "AAA", "DDD", date)
    assert f["pass_epa"] > 1.0                                   # great passer vs the worst pass defense
    assert abs(f["dropbacks"]) < 0.3 and np.isfinite(f["rushes"])


def test_script_lean_moves_only_pass_game_props():
    coef = {"stats": ["receptions", "receiving_yards", "passing_yards"], "matchup": 0.073, "volume": 0.94}
    good = {"pass_epa": 1.5, "rush_epa": 0.0, "dropbacks": 0.05, "rushes": 0.0}
    bad = {**good, "pass_epa": -1.5, "dropbacks": -0.05}
    assert PM.script_lean(0.5, "receptions", good, coef) > 0.53
    assert PM.script_lean(0.5, "receptions", bad, coef) < 0.47
    assert PM.script_lean(0.5, "rushing_yards", good, coef) == 0.5
    assert PM.script_lean(0.5, "receptions", {**good, "pass_epa": 0.0, "dropbacks": 0.0}, coef) == 0.5


def toy_qb_games(tg: pd.DataFrame) -> pd.DataFrame:
    """AAA's starter S1 (strong) plays every game; BBB's backup B2 has one game at the end."""
    rows = []
    for x in tg.itertuples():
        qb = {"AAA": "S1", "BBB": "B1", "CCC": "C1", "DDD": "D1"}[x.team]
        if x.team == "BBB" and x.date == tg["date"].max():
            qb = "B2"
        rows.append({"game_id": f"{x.date:%Y%m%d}_{x.team}", "team": x.team, "opp": x.opp, "passer_id": qb,
                     "dropbacks": 36, "epa": x.pass_epa * 36, "name": qb, "date": x.date, "home": x.home,
                     "starter": True})
    return pd.DataFrame(rows)


def test_qb_adjust_is_zero_for_the_usual_starter_and_negative_for_an_unknown_backup():
    tg = toy_team_games()
    qg = toy_qb_games(tg)
    date = pd.Timestamp("2025-12-01")
    r = GN.fit_ratings(tg, date)
    qbr = GN.qb_ratings(qg, r, date)
    assert qbr.loc["S1", "est"] > qbr.loc["D1", "est"]              # the great passer rates highest
    same = GN.qb_adjust(qg, qbr, "AAA", "S1", date)
    assert abs(same["adj"]) < 0.01 and same["last_id"] == "S1"
    new = GN.qb_adjust(qg, qbr, "AAA", "NOBODY", date)             # no record: a typical backup
    assert new["adj"] < -0.05
    assert GN.qb_adjust(qg, qbr, "AAA", None, date)["adj"] == 0.0   # starter unknown: no change


def test_weather_effects_scale_with_wind_rain_and_cold():
    assert GN.weather_effects(None) == {}
    calm = GN.weather_effects({"wind_mph": 8, "precip_prob": 0.0, "temp_f": 60})
    assert calm["pass_epa"] == 0 and calm["neutral_pass"] == 0
    windy = GN.weather_effects({"wind_mph": 20, "precip_prob": 0.0, "temp_f": 60})
    gale = GN.weather_effects({"wind_mph": 45, "precip_prob": 0.0, "temp_f": 60})
    assert windy["pass_epa"] < 0 and gale["pass_epa"] == GN.weather_effects({"wind_mph": 25, "temp_f": 60})["pass_epa"]
    wet_cold = GN.weather_effects({"wind_mph": 5, "precip_prob": 1.0, "temp_f": 20})
    assert wet_cold["neutral_pass"] < -0.03 and wet_cold["pass_epa"] < 0
    assert GN.weather_effects({"wind_mph": float("nan"), "precip_prob": None, "temp_f": float("nan")})["pass_epa"] == 0


def test_project_applies_adjustments_to_the_right_team():
    r = GN.fit_ratings(toy_team_games(), "2025-12-01")
    base = GN.project(r, "BBB", "CCC", market_margin_home=0.0)
    adj = GN.project(r, "BBB", "CCC", market_margin_home=0.0, adjust={"BBB": {"pass_epa": -0.1}})
    assert adj["sides"]["BBB"]["pass_epa"] == base["sides"]["BBB"]["pass_epa"] - 0.1
    assert adj["sides"]["CCC"]["pass_epa"] == base["sides"]["CCC"]["pass_epa"]
    assert adj["sides"]["BBB"]["pass_adj"] == -0.1 and adj["home_points"] < base["home_points"]
