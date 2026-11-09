"""Soccer player props: shots and shots on target (Mike, 2026-10-10: "we can win money on shots").

This first part reads the books. FanDuel and BetRivers post shots and shots on target as over-only
ladders ("2+ shots", "3+ shots" ...), so there is no over/under pair to take the vig off. Each
book's ladder is read as one negative binomial plus a margin: the mean and margin that best
reproduce every rung (`ladder_fit`). On Oct 10's six matches the fits were tight (residuals
under 0.01), FanDuel's margin was about 16% and BetRivers' 6-10%, and the two books' means added
up to the same 25-30 shots a match but split them differently between players.

The ML model (gradient-boosted trees on ESPN's player history, as in models/props_nhl.py) comes
next; until it beats the market on graded lines it has no weight.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import optimize

from betlab import odds_math as om
from betlab.models.props_nhl import p_over

STATS = {"player_shots": "shots", "player_shots_on_target": "sot", "player_goal_scorer_anytime": "scorer",
         "player_assists": "assists", "player_to_score_or_assist": "ga"}
# Negative binomial size for the ladder fits, until the model's residuals give one per stat
SIZE = {"shots": 8.0, "sot": 8.0}


def ladder_fit(points, prices, size: float) -> tuple[float, float] | None:
    """(mean, margin) of one book's over-only ladder for one player: implied chance of each rung =
    P(over) under a negative binomial with that mean, times (1 + margin). Needs 2+ rungs."""
    pts = np.asarray(points, dtype=float)
    imp = np.array([om.implied_prob(float(p)) for p in prices])
    if len(pts) < 2:
        return None

    def loss(x):
        q = np.clip(p_over(np.exp(x[0]), pts, size) * (1 + x[1]), 1e-6, 0.9999)
        return float(np.sum((np.log(q) - np.log(imp)) ** 2))

    res = optimize.minimize(loss, [np.log(max(pts.mean(), 0.3)), 0.08], method="Nelder-Mead")
    return float(np.exp(res.x[0])), float(res.x[1])


def p_line(mean: float | None, line: float, size: float) -> float | None:
    return None if mean is None else float(p_over(mean, line, size)[()])


# ------------------------------------------------------------------------------------ the shots model
# Features for a player-match, all from matches before it (ESPN's player history, all six leagues):
# his shots and shots on target per 90 (short and long EWMA by appearance), minutes in recent starts,
# appearances so far, his share of his team's shots, position; the team's and the opponent's recent
# shots for and against; the market's expected goals for both teams (the close's 1X2 and over/under
# 2.5 fit to a score grid, cards/fun_soccer.fit_goals); home, rest days, league.
# goals, assists and goal involvements (goals + assists: FanDuel's "to score or assist", which isn't in the
# odds feed) since Oct 10 (Mike)
TARGETS = ("shots", "sot", "goals", "assists", "ga")
SHORT, LONG = 5, 20
POS = {"G": 0, "D": 1, "M": 2, "F": 3}
PLAYER_FEATURES = ["shots90_s", "shots90_l", "sot90_s", "sot90_l", "goals90_l", "assists90_l", "ga90_s", "ga90_l",
                   "start_min", "apps_prior", "share_s", "share_l", "pos_group", "formation_place"]
TEAM_FEATURES = ["team_shots_for", "team_shots_against", "opp_shots_for", "opp_shots_against", "team_xg", "opp_xg",
                 "home", "rest_days", "league_code"]
LEAGUE_CODE = {"epl": 0, "la_liga": 1, "serie_a": 2, "bundesliga": 3, "ligue_1": 4, "mls": 5}


def pos_group(abbr) -> float:
    """ESPN's position abbreviation (G, CD-L, RB, DM, AM-R, CF ...) -> 0 keeper, 1 defender,
    2 midfielder, 3 forward; NaN for SUB (filled from the player's usual starting slot)."""
    a = str(abbr or "").upper()
    if a == "G":
        return 0.0
    if a.startswith(("CD", "LB", "RB", "LWB", "RWB", "D")):
        return 1.0
    if a.startswith(("DM", "CM", "AM", "LM", "RM", "M")):
        return 2.0
    if a.startswith(("F", "CF", "LW", "RW", "S")) and a != "SUB":
        return 3.0
    return np.nan


def _ewm_prior(s: pd.Series, groups: pd.Series, span: int) -> pd.Series:
    """EWMA of earlier rows within each group (this row excluded)."""
    return s.groupby(groups).transform(lambda x: x.shift(1).ewm(span=span, min_periods=1).mean())


def features(pg: pd.DataFrame, xg: pd.DataFrame | None = None) -> pd.DataFrame:
    """Feature rows for every player-match in `pg` (espn_soccer.box rows, many matches). xg: optional
    [event_id, team, team_xg, opp_xg] from the market."""
    df = pg.copy()
    df["kickoff"] = pd.to_datetime(df["kickoff"], utc=True, format="ISO8601")
    df = df.sort_values(["kickoff", "event_id"]).reset_index(drop=True)
    for c in ("shots", "sot", "minutes", "goals", "assists"):
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else np.nan
    df["ga"] = df["goals"] + df["assists"]
    df["pos_group"] = df["position"].map(pos_group)
    usual = df[df["starter"]].groupby("player_id")["pos_group"].agg(lambda x: x.dropna().median() if x.notna().any() else np.nan)
    df["pos_group"] = df["pos_group"].fillna(df["player_id"].map(usual))
    df["league_code"] = df["league"].map(LEAGUE_CODE)

    # team-match totals
    tm = df.groupby(["event_id", "team"], as_index=False).agg(kickoff=("kickoff", "first"), opponent=("opponent", "first"),
                                                             home=("home", "first"), t_shots=("shots", "sum"),
                                                             t_sot=("sot", "sum"))
    opp = tm[["event_id", "team", "t_shots"]].rename(columns={"team": "opponent", "t_shots": "t_against"})
    tm = tm.merge(opp, on=["event_id", "opponent"], how="left").sort_values("kickoff")
    tm["team_shots_for"] = _ewm_prior(tm["t_shots"], tm["team"], 10)
    tm["team_shots_against"] = _ewm_prior(tm["t_against"], tm["team"], 10)
    tm["rest_days"] = tm.groupby("team")["kickoff"].diff().dt.total_seconds() / 86400
    o = tm[["event_id", "team", "team_shots_for", "team_shots_against"]].rename(
        columns={"team": "opponent", "team_shots_for": "opp_shots_for", "team_shots_against": "opp_shots_against"})
    tm = tm.merge(o, on=["event_id", "opponent"], how="left")
    df = df.merge(tm[["event_id", "team", "t_shots", "team_shots_for", "team_shots_against", "opp_shots_for",
                      "opp_shots_against", "rest_days"]], on=["event_id", "team"], how="left")
    if xg is not None and len(xg):
        df = df.merge(xg[["event_id", "team", "team_xg", "opp_xg"]], on=["event_id", "team"], how="left")
    else:
        df["team_xg"], df["opp_xg"] = np.nan, np.nan

    # player rates over earlier appearances (minutes > 0)
    df = df.sort_values(["kickoff", "event_id"]).reset_index(drop=True)
    app = df["minutes"] > 0
    a = df[app].copy()
    for c, span, name in (("shots", SHORT, "s_s"), ("shots", LONG, "s_l"), ("sot", SHORT, "o_s"), ("sot", LONG, "o_l"),
                          ("minutes", SHORT, "m_s"), ("minutes", LONG, "m_l"), ("goals", LONG, "g_l"),
                          ("assists", LONG, "a_l"), ("ga", SHORT, "ga_s"), ("ga", LONG, "ga_l")):
        a[name] = _ewm_prior(a[c], a["player_id"], span)
    a["share"] = a["shots"] / a["t_shots"].replace(0, np.nan)
    a["share_s"] = _ewm_prior(a["share"], a["player_id"], SHORT)
    a["share_l"] = _ewm_prior(a["share"], a["player_id"], LONG)
    a["apps_prior"] = a.groupby("player_id").cumcount()
    st = a[a["starter"]].copy()
    st["start_min"] = _ewm_prior(st["minutes"], st["player_id"], 10)
    a["shots90_s"] = a["s_s"] / a["m_s"] * 90
    a["shots90_l"] = a["s_l"] / a["m_l"] * 90
    a["sot90_s"] = a["o_s"] / a["m_s"] * 90
    a["sot90_l"] = a["o_l"] / a["m_l"] * 90
    a["goals90_l"] = a["g_l"] / a["m_l"] * 90
    a["assists90_l"] = a["a_l"] / a["m_l"] * 90
    a["ga90_s"] = a["ga_s"] / a["m_s"] * 90
    a["ga90_l"] = a["ga_l"] / a["m_l"] * 90
    df = df.merge(a[["event_id", "player_id", "shots90_s", "shots90_l", "sot90_s", "sot90_l", "goals90_l", "assists90_l",
                     "ga90_s", "ga90_l", "share_s", "share_l", "apps_prior"]], on=["event_id", "player_id"], how="left")
    df = df.merge(st[["event_id", "player_id", "start_min"]], on=["event_id", "player_id"], how="left")
    return df


@dataclass
class Fitted:
    models: dict = field(default_factory=dict)
    dispersion: dict = field(default_factory=dict)
    features: list = field(default_factory=list)


def fit(train: pd.DataFrame, feats: list[str] | None = None) -> Fitted:
    """One Poisson-loss tree model per target on starters with history, and its dispersion."""
    from betlab.models.props_nhl import _model, nb_size

    feats = feats or PLAYER_FEATURES + TEAM_FEATURES
    train = train[train["starter"] & (train["apps_prior"] >= 1)]
    # a feature with one value (the league code in a one-league model, xG where a league has none) can't split
    feats = [c for c in feats if train[c].nunique(dropna=True) > 1]
    f = Fitted(features=list(feats))
    for t in TARGETS:
        y = train[t].fillna(0)
        m = _model().fit(train[feats], y)
        f.models[t] = m
        f.dispersion[t] = nb_size(y.to_numpy(float), m.predict(train[feats]))
    return f


def predict(f: Fitted, df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({t: f.models[t].predict(df[f.features]) for t in f.models}, index=df.index)
