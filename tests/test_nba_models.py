"""NBA team and player models on small synthetic seasons."""

import numpy as np
import pandas as pd

from betlab.models import player_nba as P
from betlab.models import team_nba as T

TEAMS = ["AAA", "BBB", "CCC", "DDD"]


def toy_boxes(n_days=40, seed=0):
    """Round-robin games; AAA scores far more per possession than everyone else."""
    rng = np.random.default_rng(seed)
    sched, tbox, pbox = [], [], []
    gid = 0
    for d in range(n_days):
        day = pd.Timestamp("2025-11-01", tz="UTC") + pd.Timedelta(days=d, hours=23)
        pairs = [(TEAMS[d % 4], TEAMS[(d + 1) % 4]), (TEAMS[(d + 2) % 4], TEAMS[(d + 3) % 4])]
        for h, a in pairs:
            gid += 1
            sched.append({"game_id": gid, "tipoff": day, "neutral_site": False, "periods": 4.0})
            pts = {t: (125 if t == "AAA" else 108) + rng.normal(0, 4) for t in (h, a)}
            for team, opp, ha in ((h, a, "home"), (a, h, "away")):
                tid, oid = TEAMS.index(team), TEAMS.index(opp)
                tbox.append({"game_id": gid, "season": 2026, "season_type": 2, "team_id": tid, "opponent_team_id": oid,
                             "team_abbreviation": team, "opponent_team_abbreviation": opp, "team_home_away": ha,
                             "team_score": pts[team], "opponent_team_score": pts[opp], "field_goals_attempted": 88,
                             "offensive_rebounds": 10, "total_turnovers": 14, "free_throws_attempted": 20})
                for j in range(3):
                    mins = [34.0, 28.0, 20.0][j]
                    pbox.append({"game_id": gid, "season": 2026, "season_type": 2, "athlete_id": tid * 10 + j,
                                 "team_id": tid, "team_abbreviation": team, "opponent_team_id": oid, "minutes": mins,
                                 "starter": j < 2, "did_not_play": False, "reason": None,
                                 "athlete_position_abbreviation": "G", "points": round(mins * 0.6 + rng.normal(0, 2)),
                                 "rebounds": 5, "assists": 3, "three_point_field_goals_made": 2})
    return pd.DataFrame(sched), pd.DataFrame(tbox), pd.DataFrame(pbox)


def test_team_games_and_ratings():
    sch, tb, _ = toy_boxes()
    tg = T.team_games(tb, sch)
    assert np.allclose(tg["poss"], 88 - 10 + 14 + 0.44 * 20) and (tg["pace"] == tg["poss"]).all()   # 48 minutes
    assert tg.groupby("team")["rest"].min().min() >= 1
    r = T.fit_ratings(tg, pd.Timestamp("2025-12-15"))
    assert T.ranks(r).loc["AAA", "off_ortg"] == 1
    pr = T.project(r, "AAA", "BBB")
    assert pr["margin"] > 5 and abs(pr["total"] - (pr["home_points"] + pr["away_points"])) < 1e-9
    tired = T.project(T.fit_ratings(tg, "2025-12-15", T.Params(b2b_ortg=-2.0)), "AAA", "BBB", rest_home=1)
    assert tired["margin"] < pr["margin"]


def test_player_features_are_walk_forward_and_predict_sensibly():
    sch, tb, pb = toy_boxes()
    tg = T.team_games(tb, sch)
    pg = P.player_games(pb, tg, sch)
    first = pg.sort_values("tipoff").groupby("athlete_id").head(1)
    assert first["ewm_min"].isna().all() and (first["n_prior"] == 0).all()     # nothing known before game 1
    later = pg[pg["n_prior"] >= 5]
    assert np.allclose(later["avg10_min"], later["minutes"], atol=1e-9)        # steady minutes -> exact
    params = P.fit(pg)
    mu = P.predict(later, params)
    assert np.abs(mu["minutes"] - later["minutes"]).mean() < 1.0
    blend = P.predict(later, {**params, "tuning": {"points": {"blend": 0.5, "opp_exp": 0.0, "pace_exp": 0.0}}})
    assert np.all(np.isfinite(blend["points"]))


def test_negative_binomial_helpers():
    mu = np.array([5.0, 20.0, 20.0])
    p = P.p_over(mu, np.array([4.5, 19.5, 24.5]), 8.0)
    assert 0.5 < p[0] < 0.7 and p[2] < p[1]
    assert np.all(P.crps(mu, np.array([5.0, 20.0, 40.0]), 8.0)[:2] < P.crps(mu, np.array([5.0, 20.0, 40.0]), 8.0)[2])


def test_v2_teammates_out_usage_blowout_and_combos():
    sch, tb, pb = toy_boxes()
    last = pb["game_id"].max()
    star = (pb["athlete_id"] == 0) & (pb["game_id"] == last)
    if not star.any():                                   # AAA's star sits the last game AAA plays
        last = pb.loc[pb["athlete_id"] == 0, "game_id"].max()
        star = (pb["athlete_id"] == 0) & (pb["game_id"] == last)
    pb.loc[star, ["minutes", "did_not_play", "reason"]] = [np.nan, True, "LEFT ANKLE SPRAIN"]
    tg = T.team_games(tb, sch)
    pg = P.player_games(pb, tg, sch)
    mates = pg[(pg["game_id"] == last) & (pg["team"] == "AAA")]
    assert (mates["missing_min"] > 25).all() and (mates["missing_points_share"] > 0).all()
    pg = P.with_blowout(pg, np.full(len(pg), 10.0))
    known = pg["start_share"].notna()                   # no start history before his first game
    assert np.allclose((pg["blowout_starter"] + pg["blowout_bench"])[known], 10.0)
    params = P.fit(pg, min_features=P.MIN_FEATURES_V2, usage=True)
    assert set(params["usage_beta"]) == set(P.STATS) and set(P.COMBOS) <= set(params["dispersion"])
    mu = P.predict(pg[pg["n_prior"] >= 5], params)
    assert np.allclose(mu["pra"], mu["points"] + mu["rebounds"] + mu["assists"])


def test_v3_returning_counts_games_missed_right_before():
    sch, tb, pb = toy_boxes()
    games = sorted(pb.loc[pb["athlete_id"] == 11, "game_id"].unique())
    sat = games[10:13]                                                   # he misses three straight games
    pb.loc[(pb["athlete_id"] == 11) & pb["game_id"].isin(sat), ["minutes", "did_not_play", "reason"]] = [np.nan, True, "ILLNESS"]
    pg = P.player_games(pb, T.team_games(tb, sch), sch).set_index(["athlete_id", "game_id"])
    assert pg.loc[(11, games[13]), "returning"] == 3 and pg.loc[(11, games[14]), "returning"] == 0
    assert pg.loc[(11, games[9]), "returning"] == 0 and pg.loc[(11, games[13]), "long_absence"] == 0
