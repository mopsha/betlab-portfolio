"""Receiver-vs-defense matchups for receiving-yards props (UNCONFIRMED; Games tab notes only).

Two matchups looked promising on 2025 FanDuel lines beyond the market and the script
lean (docs/MODELS.md, "Matchup research"), out of seven tried:

- **Yards per target allowed to the position group** (`ypt`): the defense's receiving
  yards per WR / TE / RB target, shrunk toward the league (30 targets), as a log ratio to
  the league.
- **Deep-ball fit** (`deep`): the receiver's share of targets 15+ air yards downfield
  (shrunk toward the league, 10 targets) x the log ratio of the defense's yards per deep
  attempt to the league's (shrunk, 40 attempts).

Walk-forward from play-by-play before the game date, recency half-life 200 days, so the
current season's weeks count most. Settings `preview.matchup_read` turn the two into a
lean on the over; it's shown and tracked, never priced, until a second season agrees.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HALF_LIFE = 200.0
GROUPS = ("WR", "TE", "RB")
DEEP_AIR_YARDS = 15


def _w(dates: pd.Series, before: pd.Timestamp) -> np.ndarray:
    return 0.5 ** ((before - dates).dt.days.to_numpy() / HALF_LIFE)


def targets(pbp: pd.DataFrame, games: pd.DataFrame, positions: pd.Series) -> pd.DataFrame:
    """Targeted dropbacks: date, offense, defense, receiver, his position group, air yards,
    and receiving yards (0 on incompletions)."""
    p = pbp[pbp["play_type"].eq("pass") & (pbp["two_point_attempt"].fillna(0) == 0)
            & pbp["receiver_player_id"].notna()].copy()
    from betlab.models.game_nfl import RELOCATED

    for c in ("posteam", "defteam"):
        p[c] = p[c].replace(RELOCATED)
    p = p.merge(games[["game_id", "date"]], on="game_id")
    p["group"] = p["receiver_player_id"].map(positions).replace({"FB": "RB"})
    p = p[p["group"].isin(GROUPS)]
    p["rec_yds"] = np.where(p["complete_pass"] == 1, p["yards_gained"], 0.0)
    return p[["game_id", "date", "posteam", "defteam", "receiver_player_id", "group", "air_yards", "rec_yds"]]


def ratings(t: pd.DataFrame, before) -> dict:
    """Defense yards per target by group, receivers' deep shares, defense yards per deep
    attempt, and the league references, from targets before `before`."""
    before = pd.Timestamp(before)
    t = t[t["date"] < before].assign(w=lambda x: _w(x["date"], before))
    out = {"ypt_lg": {}, "ypt_def": {}}
    for g in GROUPS:
        tg = t[t["group"] == g]
        if tg["w"].sum() <= 0:
            continue
        lg = float((tg["rec_yds"] * tg["w"]).sum() / tg["w"].sum())
        by = tg.assign(v=tg["rec_yds"] * tg["w"]).groupby("defteam")[["v", "w"]].sum()
        out["ypt_lg"][g] = lg
        out["ypt_def"][g] = (by["v"] + 30 * lg) / (by["w"] + 30)
    ta = t[t["air_yards"].notna()].assign(deep=lambda x: (x["air_yards"] >= DEEP_AIR_YARDS).astype(float))
    deep_lg = float((ta["deep"] * ta["w"]).sum() / ta["w"].sum())
    by = ta.assign(v=ta["deep"] * ta["w"]).groupby("receiver_player_id")[["v", "w"]].sum()
    out["deep_share"] = (by["v"] + 10 * deep_lg) / (by["w"] + 10)
    out["deep_lg"] = deep_lg
    dp = ta[ta["deep"] == 1]
    ypa_lg = float((dp["rec_yds"] * dp["w"]).sum() / dp["w"].sum())
    by = dp.assign(v=dp["rec_yds"] * dp["w"]).groupby("defteam")[["v", "w"]].sum()
    out["deep_ypa_def"] = (by["v"] + 40 * ypa_lg) / (by["w"] + 40)
    out["deep_ypa_lg"] = ypa_lg
    return out


def features(rt: dict, player_id: str, group: str | None, opp: str) -> dict:
    """ypt and deep for one receiver against one defense (missing when unknown), plus the
    raw numbers the notes quote."""
    f = {}
    if group in rt["ypt_def"]:
        allowed = float(rt["ypt_def"][group].get(opp, rt["ypt_lg"][group]))
        f.update(ypt=float(np.log(allowed / rt["ypt_lg"][group])), ypt_allowed=allowed,
                 ypt_rank=int(rt["ypt_def"][group].rank(method="min").get(opp, 16)))
    if player_id in rt["deep_share"].index:
        share = float(rt["deep_share"][player_id])
        ypa = float(rt["deep_ypa_def"].get(opp, rt["deep_ypa_lg"]))
        f.update(deep=share * float(np.log(ypa / rt["deep_ypa_lg"])), deep_share=share, deep_ypa=ypa,
                 deep_rank=int(rt["deep_ypa_def"].rank(method="min").get(opp, 16)), deep_lg=rt["deep_lg"])
    return f


def read(p_over: float, f: dict, cfg: dict) -> tuple[float, float]:
    """(P(over) moved by the matchups, the combined score in log-odds). Missing features count as 0."""
    s = sum(cfg[k]["coef"] * f[k] / cfg[k]["sd"] for k in ("ypt", "deep") if k in f and k in cfg)
    p = float(np.clip(p_over, 1e-4, 1 - 1e-4))
    return float(1 / (1 + np.exp(-(np.log(p / (1 - p)) + s)))), float(s)
