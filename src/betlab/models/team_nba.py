"""NBA team model: opponent-adjusted efficiency and pace, rest, and a game projection.

1. **Team-games** (`team_games`): per team per game, possessions (FGA - OREB + TOV +
   0.44 FTA, averaged with the opponent's), pace (possessions per 48 minutes, overtime
   removed), offensive rating (points per 100 possessions), rest days, back-to-backs.
2. **Ratings** (`fit_ratings`): the football engine's weighted ridge (stat = league + home
   edge + offense[team] + defense[opponent]) on games before the date, for offensive
   rating and pace; recency half-life 45 days, ridge 6 games (settings in `Params`).
3. **Projection** (`project`): pace, each team's points per 100 and points, margin and
   total, with a back-to-back adjustment fit on earlier seasons (`fit_rest`).

Walk-forward only. Backtest: `backtest_nba.team_eval` (`betlab backtest nba`). There are no
historical NBA lines to compare with (docs/NBA_PLAN.md), so it's scored against naive
baselines; the market comparison comes from lines logged from opening night.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from betlab.models.game_nfl import _ridge

STATS = ("ortg", "pace")


@dataclass
class Params:
    half_life_days: float = 45.0
    ridge: float = 6.0
    b2b_ortg: float = 0.0        # points per 100 when a team is on the second night of a back-to-back
    extra_rest_ortg: float = 0.0  # per extra day of rest beyond one (capped at 3)


@dataclass
class Ratings:
    date: pd.Timestamp
    league: dict
    home: dict
    off: pd.DataFrame
    dfn: pd.DataFrame
    params: Params = field(default_factory=Params)


def team_games(team_box: pd.DataFrame, schedules: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, team): points, possessions, pace, offensive rating, home, rest."""
    tb = team_box.copy()
    tb["poss_est"] = (tb["field_goals_attempted"] - tb["offensive_rebounds"] + tb["total_turnovers"]
                      + 0.44 * tb["free_throws_attempted"])
    opp = tb[["game_id", "team_id", "poss_est"]].rename(columns={"team_id": "opponent_team_id", "poss_est": "opp_poss"})
    tb = tb.merge(opp, on=["game_id", "opponent_team_id"], how="left")
    tb = tb.merge(schedules[["game_id", "tipoff", "neutral_site", "periods"]], on="game_id", how="left")
    minutes = 48 + 5 * (tb["periods"].fillna(4).clip(lower=4) - 4)
    t = pd.DataFrame({
        "game_id": tb["game_id"], "season": tb["season"], "season_type": tb["season_type"],
        "tipoff": tb["tipoff"], "date": tb["tipoff"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize(),
        "team": tb["team_abbreviation"], "opp": tb["opponent_team_abbreviation"],
        "home": np.where(tb["neutral_site"].fillna(False).astype(bool), 0.0, np.where(tb["team_home_away"] == "home", 1.0, -1.0)),
        "points": tb["team_score"].astype(float), "opp_points": tb["opponent_team_score"].astype(float),
    })
    poss = (tb["poss_est"] + tb["opp_poss"].fillna(tb["poss_est"])) / 2
    t["poss"] = poss
    t["pace"] = poss * 48 / minutes
    t["ortg"] = 100 * t["points"] / poss
    t = t.sort_values(["team", "tipoff"])
    t["rest"] = t.groupby("team")["date"].diff().dt.days
    t["b2b"] = (t["rest"] == 1).astype(float)
    return t.sort_values(["tipoff", "game_id"]).reset_index(drop=True)


def fit_ratings(tg: pd.DataFrame, date, p: Params | None = None) -> Ratings:
    """Offense, defense (allowed) and pace effects from games strictly before `date`."""
    p = p or Params()
    date = pd.Timestamp(date)
    h = tg[(tg["date"] < date) & (tg["date"] >= date - pd.Timedelta(days=400))]
    teams = sorted(set(h["team"]) | set(h["opp"]))
    idx = {t: i for i, t in enumerate(teams)}
    w = 0.5 ** ((date - h["date"]).dt.days.to_numpy() / p.half_life_days)
    league, home, off, dfn = {}, {}, {}, {}
    for stat in STATS:
        y = h[stat].to_numpy(float)
        ok = np.isfinite(y)
        mu, he, o, d = _ridge(y[ok], w[ok], h["team"].map(idx).to_numpy()[ok], h["opp"].map(idx).to_numpy()[ok],
                              h["home"].to_numpy()[ok], len(teams), p.ridge)
        league[stat], home[stat], off[stat], dfn[stat] = mu, he, o, d
    return Ratings(date, league, home, pd.DataFrame(off, index=teams), pd.DataFrame(dfn, index=teams), p)


def _rest_adj(p: Params, rest) -> float:
    if rest is None or not np.isfinite(rest):
        return 0.0
    if rest <= 1:
        return p.b2b_ortg
    return p.extra_rest_ortg * min(rest - 1, 2)


def project(r: Ratings, home: str, away: str, neutral: bool = False, rest_home=None, rest_away=None) -> dict:
    """Pace, each team's offensive rating and points, margin and total."""
    h = 0.0 if neutral else 1.0
    side = {}
    for team, opp, hh, rest in ((home, away, h, rest_home), (away, home, -h, rest_away)):
        ortg = (r.league["ortg"] + r.home["ortg"] * hh + float(r.off["ortg"].get(team, 0.0))
                + float(r.dfn["ortg"].get(opp, 0.0)) + _rest_adj(r.params, rest))
        pace = (r.league["pace"] + float(r.off["pace"].get(team, 0.0)) + float(r.dfn["pace"].get(opp, 0.0)))
        side[team] = {"ortg": ortg, "pace": pace}
    pace = (side[home]["pace"] + side[away]["pace"]) / 2
    hp, ap = side[home]["ortg"] * pace / 100, side[away]["ortg"] * pace / 100
    return {"home": home, "away": away, "pace": pace, "home_ortg": side[home]["ortg"], "away_ortg": side[away]["ortg"],
            "home_points": hp, "away_points": ap, "margin": hp - ap, "total": hp + ap}


def ranks(r: Ratings) -> pd.DataFrame:
    """1 = best offense (most points per 100), best defense (fewest allowed), fastest pace."""
    return pd.DataFrame({"off_ortg": r.off["ortg"].rank(ascending=False, method="min"),
                         "def_ortg": r.dfn["ortg"].rank(ascending=True, method="min"),
                         "pace": (r.off["pace"] + r.dfn["pace"]).rank(ascending=False, method="min")})
