"""College basketball team ratings: opponent-adjusted efficiency and pace (KenPom-style).

From every team-game (sources/cbbd.py team games):
- **Efficiency:** points per 100 possessions = league + home edge + offense[team] - defense[opp],
  fit by weighted ridge. Weights halve every `half_life_days`; last season's games also
  count at `carry` weight, so November ratings start from last year pulled toward average.
- **Pace:** possessions per game = league + pace[team] + pace[opp], same weighting.
- **Projection:** each side's efficiency times the expected possessions: margin (home minus
  away) and total. Neutral sites get no home edge.
- **Roster change** (`roster_value`, `roster_shift`): November ratings are mostly last
  season's team, but rosters turn over (about 40-70% of minutes leave each year, more since
  the transfer portal). Each team's roster is valued at its players' previous-season PORPAG
  (points over replacement per game; transfers count for their new team, freshmen 0), minus
  what the team had. The margin moves by ROSTER_BETA x the difference, fading with
  ROSTER_TAU days as this season's games teach the ratings (fit on 2022-23 and 2023-24).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import lsqr


@dataclass
class Params:
    # Tuned on 2023-24 margin error (backtest_ncaab.tune); 2024-25 and 2025-26 are the test.
    half_life_days: float = 180.0
    carry: float = 0.7           # weight of last season's games (on top of the time decay)
    ridge_eff: float = 0.2       # ridge per team rating, efficiency (in weighted team-games)
    ridge_pace: float = 2.0
    history_days: int = 500


@dataclass
class Ratings:
    off: dict
    dfn: dict
    pace: dict
    mu: float
    home: float
    pace_mu: float

    def project(self, home: str, away: str, neutral: bool = False) -> dict:
        h = 0.0 if neutral else self.home
        e_h = self.mu + h / 2 + self.off.get(home, 0.0) - self.dfn.get(away, 0.0)
        e_a = self.mu - h / 2 + self.off.get(away, 0.0) - self.dfn.get(home, 0.0)
        poss = self.pace_mu + self.pace.get(home, 0.0) + self.pace.get(away, 0.0)
        return {"margin": (e_h - e_a) * poss / 100, "total": (e_h + e_a) * poss / 100, "poss": poss,
                "eff_home": e_h, "eff_away": e_a}


def _design(tg: pd.DataFrame, teams: dict, home_col: np.ndarray, two_sided: bool):
    n, k = len(tg), len(teams)
    rows = np.arange(n)
    ti, oi = tg["team"].map(teams).to_numpy(), tg["opp"].map(teams).to_numpy()
    cols = [np.zeros(n, int), ti + 2, oi + 2 + (0 if two_sided else k)]
    vals = [np.ones(n), np.ones(n), np.ones(n) if two_sided else -np.ones(n)]
    data = np.concatenate(vals + [home_col])
    r = np.concatenate([rows] * 3 + [rows])
    c = np.concatenate(cols + [np.ones(n, int)])
    return csr_matrix((data, (r, c)), shape=(n, 2 + (k if two_sided else 2 * k)))


def fit(team_games: pd.DataFrame, date, p: Params | None = None) -> Ratings:
    """Ratings from team-games before `date` (columns: start, season, team, opp, is_home,
    neutral, poss, ortg)."""
    p = p or Params()
    date = pd.Timestamp(date)
    date = date.tz_localize("UTC") if date.tzinfo is None else date
    tg = team_games[(team_games["start"] < date) & (team_games["start"] >= date - pd.Timedelta(days=p.history_days))]
    tg = tg.dropna(subset=["poss", "ortg"])
    tg = tg[(tg["poss"] > 40) & (tg["poss"] < 100)]
    if tg.empty:
        return Ratings({}, {}, {}, 104.0, 3.0, 68.0)
    season_now = tg["season"].max()
    w = 0.5 ** ((date - tg["start"]).dt.days.to_numpy() / p.half_life_days)
    w = w * np.where(tg["season"].to_numpy() < season_now, p.carry, 1.0)
    teams = {t: i for i, t in enumerate(sorted(set(tg["team"]) | set(tg["opp"])))}
    k = len(teams)
    home = np.where(tg["neutral"].fillna(False).to_numpy(), 0.0, np.where(tg["is_home"].to_numpy(), 0.5, -0.5))
    sw = np.sqrt(w)

    def solve(X, y, ridge, n_rated):
        Xw = X.multiply(sw[:, None]).tocsr()
        # ridge rows on the team parameters only
        R = csr_matrix((np.full(n_rated, np.sqrt(ridge)), (np.arange(n_rated), np.arange(2, 2 + n_rated))),
                       shape=(n_rated, X.shape[1]))
        from scipy.sparse import vstack
        A = vstack([Xw, R]).tocsr()
        b = np.concatenate([y * sw, np.zeros(n_rated)])
        x0 = np.zeros(X.shape[1])
        x0[0] = np.average(y, weights=w)
        return lsqr(A, b - A @ x0, atol=1e-8, btol=1e-8, iter_lim=5000)[0] + x0

    X = _design(tg, teams, home, two_sided=False)
    b = solve(X, tg["ortg"].to_numpy(float), p.ridge_eff, 2 * k)
    Xp = _design(tg, teams, np.zeros(len(tg)), two_sided=True)
    bp = solve(Xp, tg["poss"].to_numpy(float), p.ridge_pace, k)
    names = sorted(teams, key=teams.get)
    # y = mu + home + off[team] - def[opp]: a positive defense rating lowers the opponent's efficiency
    return Ratings(off=dict(zip(names, b[2:2 + k])), dfn=dict(zip(names, b[2 + k:2 + 2 * k])),
                   pace=dict(zip(names, bp[2:2 + k])), mu=float(b[0]), home=float(b[1]), pace_mu=float(bp[0]))


# ---------------------------------------------------------------- roster change
ROSTER_BETA = 0.65   # margin points per point of roster value change on Nov 1 (0.6-0.7 in each tuning season)
ROSTER_TAU = 60.0    # days for the shift to fade by 1/e: the ratings learn the new roster from games
STALE_RET = 0.85     # more returning minutes than this is last season's list, not a new roster: ESPN's
                     # preseason pages lag (Sep 26: 72% of teams); real rosters top 85% about 2% of the time


# a freshman's expected first-season value (PORPAG x games / 30) by recruit rating: the mean of 2022-23 and 2023-24
# recruits matched to their first season (unmatched: 0). Fit Oct 20; the shift's beta fit on the same seasons came out
# 0.73, close to ROSTER_BETA, so freshmen count like any other player value (MODEL_CHANGELOG).
FRESHMAN_BANDS = ((0.995, 1.95), (0.98, 0.84), (0.95, 0.65), (0.90, 0.40), (0.0, 0.24))


def freshman_value(rating) -> float:
    r = float(rating) if rating is not None and pd.notna(rating) else 0.0
    return next(v for lo, v in FRESHMAN_BANDS if r >= lo)


def freshmen(recruits: pd.DataFrame | None, season: int) -> dict:
    """{team: expected value of its incoming class} for `season` (recruits of year season - 1, by commitment)."""
    if recruits is None or recruits.empty:
        return {}
    r = recruits[(recruits["year"].astype(int) == season - 1) & recruits["team"].notna()]
    return r.assign(v=r["rating"].map(freshman_value)).groupby("team")["v"].sum().to_dict()


def roster_value(players: pd.DataFrame, roster: pd.DataFrame, season: int,
                 recruits: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per team (index): the share of last season's minutes on this season's roster
    (`ret_min`), last season's player value (`val_prev`, PORPAG x games / 30: points per game
    over replacement), the value of this season's roster from the same season (`val_now`),
    `dval` = val_now - val_prev, and `stale` (ret_min above STALE_RET: not updated yet, so
    no shift). players: season, team, player_id, games, minutes, porpag; roster: season,
    team, player_id (ESPN ids in both). recruits (cbbd.recruits): freshmen add their expected value to `val_now`
    (`val_fresh`); without them freshmen count 0, as before Oct 20."""
    prev = players[players["season"] == season - 1].copy()
    prev["val"] = prev["porpag"].fillna(0) * prev["games"].fillna(0) / 30.0
    by_player = prev.groupby("player_id")["val"].sum()
    ro = roster[roster["season"] == season].drop_duplicates(["team", "player_id"])
    fresh = freshmen(recruits, season)
    rows = []
    for team, r in ro.groupby("team"):
        had = prev[prev["team"] == team]
        if had.empty or had["minutes"].sum() <= 0:
            continue
        ids = set(r["player_id"])
        val_fresh = float(fresh.get(team, 0.0))
        val_now = float(by_player.reindex(sorted(ids)).fillna(0).sum()) + val_fresh
        rows.append({"team": team, "ret_min": had.loc[had["player_id"].isin(ids), "minutes"].sum() / had["minutes"].sum(),
                     "val_prev": had["val"].sum(), "val_now": val_now, "val_fresh": val_fresh,
                     "dval": val_now - had["val"].sum()})
    out = pd.DataFrame(rows, columns=["team", "ret_min", "val_prev", "val_now", "val_fresh", "dval"]).set_index("team")
    out["stale"] = out["ret_min"] > STALE_RET
    return out


def roster_dval(players: pd.DataFrame, roster: pd.DataFrame, season: int, recruits: pd.DataFrame | None = None) -> dict:
    """{team: dval} for teams with a current (not stale) roster."""
    v = roster_value(players, roster, season, recruits)
    return v.loc[~v["stale"], "dval"].to_dict()


def season_day(date, season: int) -> float:
    """Days since Nov 1 of the season's first year (0 before it)."""
    date = pd.Timestamp(date)
    date = date.tz_convert("America/New_York").tz_localize(None) if date.tzinfo else date
    return max(0.0, float((date.normalize() - pd.Timestamp(f"{season - 1}-11-01")).days))


def roster_shift(dval: dict, home: str, away: str, days: float) -> float:
    """Points to add to the home margin for roster change; 0 unless both teams are valued."""
    if home not in dval or away not in dval:
        return 0.0
    return ROSTER_BETA * float(np.exp(-days / ROSTER_TAU)) * (dval[home] - dval[away])
