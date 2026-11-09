"""Anytime TD read: who scores, from red-zone role, usage and the team's expected points.

Mike (2026-09-26): the TD ticket shouldn't just take the likeliest scorer, "get some
analysis in there". Logistic regression on 2022-25 regular-season player-games
(RB, WR, TE, QB; rushing or receiving TD):

- **Features** (each from the player's games before the one predicted): his share of his
  team's run/pass opportunities over his last 6 games (`opp_share`), his share of the
  team's red-zone (inside the 20) and goal-to-go-range (inside the 10) opportunities
  (`rz20_share`, `rz10_share`), how often he scored in his last 8 games (`td_rate`), his
  position, and the market's expected points for his team (log).
- **Evidence** (trained on 2023-24, tested on 2025, 5,473 player-games; game bootstrap):
  against usage and team points alone, red-zone role improves log loss by +0.0015
  (SE 0.0004), recent TD rate +0.0019 (SE 0.0008), both +0.0023 (SE 0.0008).
  Calibration is close except the top eighth (predicted 46%, scored 42%).
- **Not tested against the TD market:** the 2025 prop backfill has no anytime TD prices.
  So the fun tickets use it at half weight toward Pinnacle's no-vig chance (`blend`), and
  every read is tracked against the market this season (td_reads.py) before it earns more.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from betlab import config

PARAMS = config.DATA_DIR / "models" / "td_params.json"
FEATURES = ["is_RB", "is_WR", "is_TE", "lpts", "lopp", "rz20_share", "rz10_share", "td_rate"]
SHARE_GAMES, TD_GAMES = 6, 8
READ_WEIGHT = 0.0    # the read's weight in the TD tickets: none since Oct 25 (it never beat Pinnacle; MODEL_CHANGELOG)
TRACK_WEIGHT = 0.5   # the half-weight blend td_reads.csv keeps testing against Pinnacle, so it can earn weight back


def _opportunities(pbp: pd.DataFrame) -> pd.DataFrame:
    """Per game, team and player: run/pass opportunities (carries + targets), inside the 20
    and inside the 10, with the team's totals for the game."""
    pbp = pbp[pbp["play_type"].isin(["run", "pass"]) & pbp["posteam"].notna()]
    cols = ["game_id", "season", "week", "posteam", "yardline_100"]
    long = pd.concat([pbp[cols + ["rusher_player_id"]].rename(columns={"rusher_player_id": "pid"}),
                      pbp[cols + ["receiver_player_id"]].rename(columns={"receiver_player_id": "pid"})]).dropna(subset=["pid"])
    long["rz20"], long["rz10"] = long["yardline_100"] <= 20, long["yardline_100"] <= 10
    per = long.groupby(["game_id", "season", "week", "posteam", "pid"]).agg(
        opp=("pid", "size"), rz20=("rz20", "sum"), rz10=("rz10", "sum")).reset_index()
    team = per.groupby(["game_id", "posteam"])[["opp", "rz20", "rz10"]].sum().add_prefix("t_").reset_index()
    return per.merge(team, on=["game_id", "posteam"])


def player_games(pbp: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    """One row per player-game (regular season) with the TD outcome and the player's and his
    team's opportunities, sorted by player and date."""
    ps = stats[stats["season_type"] == "REG"] if "season_type" in stats else stats
    ps = ps.assign(td=((ps["rushing_tds"].fillna(0) + ps["receiving_tds"].fillna(0)) > 0).astype(int))
    ps = ps[["player_id", "player_display_name", "game_id", "season", "week", "team", "position", "td"]].rename(
        columns={"player_id": "pid", "team": "posteam"})
    opp = _opportunities(pbp)
    team = opp.drop_duplicates(["game_id", "posteam"])[["game_id", "posteam", "t_opp", "t_rz20", "t_rz10"]]
    d = ps.merge(opp[["game_id", "pid", "opp", "rz20", "rz10"]], on=["game_id", "pid"], how="left").fillna(
        {"opp": 0, "rz20": 0, "rz10": 0})
    d = d.merge(team, on=["game_id", "posteam"], how="left")
    return d.sort_values(["pid", "season", "week"]).reset_index(drop=True)


def rolling(d: pd.DataFrame, shift: int = 1) -> pd.DataFrame:
    """Shares and TD rate over each player's previous games (shift=1: before each game, for
    training; shift=0: through his latest game, for the next one)."""
    out = d.copy()
    grp = out.groupby("pid")
    for c in ("opp", "rz20", "rz10", "t_opp", "t_rz20", "t_rz10"):
        out["r_" + c] = grp[c].transform(lambda s: s.shift(shift).rolling(SHARE_GAMES, min_periods=2).sum())
    out["td_rate"] = grp["td"].transform(lambda s: s.shift(shift).rolling(TD_GAMES, min_periods=2).mean())
    out["opp_share"] = out["r_opp"] / out["r_t_opp"]
    out["rz20_share"] = (out["r_rz20"] / out["r_t_rz20"].replace(0, np.nan)).fillna(0)
    out["rz10_share"] = (out["r_rz10"] / out["r_t_rz10"].replace(0, np.nan)).fillna(0)
    return out


def design(d: pd.DataFrame, team_pts, prior_td: dict | None = None) -> np.ndarray:
    """The model's columns for rows with position, opp_share, shares, td_rate and team points."""
    pos = d["position"].to_numpy()
    td_rate = d["td_rate"].to_numpy(float)
    if prior_td is not None:  # a player with too few games gets his position's average rate
        td_rate = np.where(np.isnan(td_rate), [prior_td.get(p, 0.2) for p in pos], td_rate)
    return np.column_stack([(pos == "RB").astype(float), (pos == "WR").astype(float), (pos == "TE").astype(float),
                            np.log(np.clip(np.asarray(team_pts, float), 8, 40)),
                            np.log(np.clip(d["opp_share"].to_numpy(float), 0.005, 1)),
                            d["rz20_share"].to_numpy(float), d["rz10_share"].to_numpy(float), td_rate])


def fit(X: np.ndarray, y: np.ndarray, l2: float = 1e-3, iters: int = 50) -> np.ndarray:
    """Logistic regression by Newton steps (intercept first)."""
    X = np.column_stack([np.ones(len(X)), X])
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ b))
        H = X.T @ (X * (p * (1 - p))[:, None]) + l2 * np.eye(X.shape[1])
        b += np.linalg.solve(H, X.T @ (y - p) - l2 * b)
    return b


def predict(b, X: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(np.column_stack([np.ones(len(X)), X]) @ np.asarray(b))))


def blend(p_market: float, p_model: float, weight: float = READ_WEIGHT) -> float:
    """The market's chance moved toward the model's in log-odds."""
    lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
    return float(1 / (1 + np.exp(-(lg(p_market) + weight * (lg(p_model) - lg(p_market))))))


def load_params() -> dict | None:
    return json.loads(PARAMS.read_text()) if PARAMS.exists() else None


class Reads:
    """Live TD reads for the week: each player's shares and TD rate through his latest game."""

    def __init__(self, pbp: pd.DataFrame, stats: pd.DataFrame, params: dict):
        d = rolling(player_games(pbp, stats), shift=0)
        self.latest = d.groupby("pid").tail(1).set_index("pid")
        self.params = params

    def read(self, pid: str, position: str, team_pts: float) -> dict | None:
        """{p_model, rz10_share, rz20_share, opp_share, td_rate, games} or None when the player
        has too little history."""
        if pid not in self.latest.index:
            return None
        r = self.latest.loc[[pid]].assign(position=position if position in ("RB", "WR", "TE", "QB") else "WR")
        if pd.isna(r["opp_share"].iloc[0]):
            return None
        p = float(predict(self.params["coef"], design(r, [team_pts], self.params["prior_td"]))[0])
        row = r.iloc[0]
        return {"p_model": p, "rz10_share": float(row["rz10_share"]), "rz20_share": float(row["rz20_share"]),
                "opp_share": float(row["opp_share"]), "td_rate": None if pd.isna(row["td_rate"]) else float(row["td_rate"])}


def note(r: dict, team: str, team_pts: float) -> str:
    """The TD read's case in one line."""
    parts = [f"{r['rz10_share']:.0%} of {team}'s touches inside the 10 and {r['rz20_share']:.0%} inside the 20 lately",
             f"team expected {team_pts:.1f} points"]
    if r.get("td_rate") is not None:
        parts.append(f"scored in {r['td_rate']:.0%} of his last games")
    return " · ".join(parts)
