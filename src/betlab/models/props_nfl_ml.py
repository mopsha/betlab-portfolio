"""NFL player props, machine learning (Mike, 2026-10-10: "are we doing ML for NFL player props, if not we
should be").

The hand-built model (models/props_nfl.py + roles_nfl.py, v0.2) simulates volume x share x efficiency.
This one learns the same stats directly from every player-game since 2016 (nflverse), as the soccer and
NHL shots models do, and is tested on real 2025 prop lines against v0.2 and the market
(backtest_props_nfl_ml.py).

**Targets:** receptions, receiving yards, rushing yards, passing yards, touchdowns (rushing + receiving).

**Features** (`features`), all from games before this one:
- the player's volume and role: targets, carries and pass attempts a game, snap share, target and carry
  share of his team (short and long EWMA by game), games played;
- his efficiency: catch rate, yards per target, per carry, per attempt (long EWMA);
- his recent output: each target stat a game (short and long);
- his team's volume (targets, carries, attempts a game) and the opponent's: yards allowed to his
  position a game;
- this game: the closing spread from his team's side and total, home, position;
- who's missing: the share of his team's recent targets and carries belonging to regulars who didn't
  play (known after inactives, as the live card knows it).

**Model:** gradient-boosted trees with a Poisson loss per target (yards are non-negative, so the Poisson
deviance still fits a mean). P(over a line) comes from the target's own residual shape: actual / predicted
ratios on the training seasons, by position, scaled by tonight's mean (`p_over`). Receptions and TDs use
the same; TDs read P(1+).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TARGETS = ("receptions", "receiving_yards", "rushing_yards", "passing_yards", "tds")
POS = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}
SHORT, LONG = 4, 12


def _ewm(s: pd.Series, groups: pd.Series, span: int) -> pd.Series:
    """EWMA of earlier rows in each group (this row excluded)."""
    return s.groupby(groups).transform(lambda x: x.shift(1).ewm(span=span, min_periods=1).mean())


def features(df: pd.DataFrame) -> pd.DataFrame:
    """Feature rows for every player-game in roles_nfl.prepare's frame (several seasons)."""
    d = df.sort_values(["date", "game_id"]).reset_index(drop=True).copy()
    d["tds"] = d["rushing_tds"] + d["receiving_tds"]
    d["played"] = (d["offense_pct"].fillna(0) > 0) | (d["targets"] + d["carries"] + d["attempts"] > 0)
    d["pos"] = d["position"].map(POS)
    d["home"] = (d["team"] == d["home_team"]).astype(float)
    d["t_share"] = d["targets"] / d["team_targets"].replace(0, np.nan)
    d["c_share"] = d["carries"] / d["team_carries"].replace(0, np.nan)
    p = d[d["played"]].copy()
    pid = p["player_id"]
    for c in ("targets", "carries", "attempts", "receptions", "receiving_yards", "rushing_yards", "passing_yards",
              "tds", "offense_pct", "t_share", "c_share"):
        p[f"{c}_s"] = _ewm(p[c], pid, SHORT)
        p[f"{c}_l"] = _ewm(p[c], pid, LONG)
    for num, den, name in (("receptions", "targets", "catch"), ("receiving_yards", "targets", "ypt"),
                           ("rushing_yards", "carries", "ypc"), ("passing_yards", "attempts", "ypa")):
        p[name] = _ewm(p[num], pid, LONG) / _ewm(p[den], pid, LONG).replace(0, np.nan)
    p["games_prior"] = p.groupby("player_id").cumcount()
    p["season_games"] = p.groupby(["player_id", "season"]).cumcount()
    cols = [c for c in p.columns if c.endswith(("_s", "_l"))] + ["catch", "ypt", "ypc", "ypa", "games_prior",
                                                                  "season_games"]
    d = d.merge(p[["game_id", "player_id"] + cols], on=["game_id", "player_id"], how="left")

    # team volume and the opponent's yards allowed to this position (earlier games)
    tm = d[d["played"]].groupby(["game_id", "team"], as_index=False).agg(
        date=("date", "first"), opp=("opp", "first"), team_targets=("team_targets", "first"),
        team_carries=("team_carries", "first"), team_attempts=("team_attempts", "first")).sort_values("date")
    for c in ("team_targets", "team_carries", "team_attempts"):
        tm[f"{c}_l"] = _ewm(tm[c], tm["team"], LONG)
    d = d.merge(tm[["game_id", "team", "team_targets_l", "team_carries_l", "team_attempts_l"]], on=["game_id", "team"],
                how="left")
    allowed = d[d["played"]].groupby(["game_id", "opp", "position"], as_index=False).agg(
        date=("date", "first"), rec_yds=("receiving_yards", "sum"), rush_yds=("rushing_yards", "sum"),
        pass_yds=("passing_yards", "sum")).sort_values("date")
    key = allowed["opp"] + "|" + allowed["position"]
    for c in ("rec_yds", "rush_yds", "pass_yds"):
        allowed[f"opp_{c}_allowed"] = _ewm(allowed[c], key, LONG)
    d = d.merge(allowed[["game_id", "opp", "position", "opp_rec_yds_allowed", "opp_rush_yds_allowed",
                         "opp_pass_yds_allowed"]], on=["game_id", "opp", "position"], how="left")

    # who's missing: recent target / carry shares of the team's regulars who didn't play this game
    d = d.merge(_missing(d), on=["game_id", "team"], how="left")
    d[["missing_t_share", "missing_c_share"]] = d[["missing_t_share", "missing_c_share"]].fillna(0)
    return d


def _missing(d: pd.DataFrame) -> pd.DataFrame:
    """Per team-game: the summed recent (short EWMA) target and carry shares of players who played one of
    the team's previous two games with 50%+ of snaps and didn't play this one."""
    rows = []
    for team, t in d.sort_values("date").groupby("team"):
        games = t.drop_duplicates("game_id")[["game_id"]].reset_index(drop=True)
        by_game = {g: x for g, x in t.groupby("game_id")}
        for k in range(2, len(games)):
            gid = games.loc[k, "game_id"]
            prev = pd.concat([by_game[games.loc[k - 1, "game_id"]], by_game[games.loc[k - 2, "game_id"]]])
            regs = set(prev.loc[prev["offense_pct"].fillna(0) >= 0.5, "player_id"])
            now = by_game[gid]
            out = regs - set(now.loc[now["played"], "player_id"])
            last = prev.drop_duplicates("player_id", keep="first").set_index("player_id")
            rows.append({"game_id": gid, "team": team,
                         "missing_t_share": float(last.reindex(list(out))["t_share_s"].fillna(0).sum()) if out else 0.0,
                         "missing_c_share": float(last.reindex(list(out))["c_share_s"].fillna(0).sum()) if out else 0.0})
    return pd.DataFrame(rows, columns=["game_id", "team", "missing_t_share", "missing_c_share"])


FEATURES = ["pos", "home", "exp_margin", "total_line", "games_prior", "season_games",
            "targets_s", "targets_l", "carries_s", "carries_l", "attempts_s", "attempts_l",
            "receptions_s", "receptions_l", "receiving_yards_s", "receiving_yards_l", "rushing_yards_s",
            "rushing_yards_l", "passing_yards_s", "passing_yards_l", "tds_s", "tds_l", "offense_pct_s",
            "offense_pct_l", "t_share_s", "t_share_l", "c_share_s", "c_share_l", "catch", "ypt", "ypc", "ypa",
            "team_targets_l", "team_carries_l", "team_attempts_l", "opp_rec_yds_allowed", "opp_rush_yds_allowed",
            "opp_pass_yds_allowed", "missing_t_share", "missing_c_share"]


@dataclass
class Fitted:
    models: dict = field(default_factory=dict)
    ratios: dict = field(default_factory=dict)      # (target, position) -> actual / predicted on training rows
    features: list = field(default_factory=list)


def _model():
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(loss="poisson", learning_rate=0.05, max_iter=400, max_leaf_nodes=31,
                                         min_samples_leaf=200, l2_regularization=1.0, random_state=0)


def fit(train: pd.DataFrame, feats: list[str] | None = None) -> Fitted:
    """One Poisson tree model per target, on players who played with 1+ earlier game."""
    feats = feats or FEATURES
    tr = train[train["played"] & (train["games_prior"] >= 1)]
    f = Fitted(features=list(feats))
    for t in TARGETS:
        y = tr[t].clip(lower=0)              # a loss on a carry: negative yards, which Poisson can't take
        m = _model().fit(tr[feats], y)
        f.models[t] = m
        mu = np.clip(m.predict(tr[feats]), 1e-3, None)
        r = tr[t].to_numpy(float) / mu        # the real ratios (negatives included) for the over chance
        for pos, idx in tr.groupby("position").indices.items():
            f.ratios[(t, pos)] = np.sort(r[idx])
    return f


def predict(f: Fitted, df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({t: np.clip(f.models[t].predict(df[f.features]), 1e-3, None) for t in f.models}, index=df.index)


def p_over(f: Fitted, target: str, position: str, mu: float, line: float) -> float:
    """P(stat > line): the share of training residual ratios (by position) that, scaled by mu, clear the line."""
    r = f.ratios.get((target, position))
    if r is None or not len(r):
        return float("nan")
    # ratios are sorted: count those above line / mu
    k = np.searchsorted(r, line / mu, side="right")
    return float(np.clip((len(r) - k) / len(r), 1e-4, 1 - 1e-4))
