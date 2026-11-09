"""Every anytime TD read the Fun tab makes: data/ledger/td_reads.csv.

One row per (game, player): FanDuel's anytime TD price, Pinnacle's no-vig chance, our TD
read (models/td_nfl.py) and its half-weight blend, the features, and after the game
whether he scored. The read was only tested against outcomes (2025), never against the TD
market, so this is its test: does the blend beat Pinnacle's chance on log loss, and do the
players it likes more than the market score more often than the market said? Rows update
until kickoff (the last read counts) and freeze after. Nothing here is a pick.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config

PATH = config.DATA_DIR / "ledger" / "td_reads.csv"
COLUMNS = ["read_id", "game_id", "commence_time", "matchup", "player", "player_id", "team", "position", "price",
           "p_market", "p_model", "p_read", "team_pts", "rz10_share", "rz20_share", "opp_share", "td_rate",
           "first_seen", "updated_at", "scored", "status", "graded_at"]
TEXT = ["read_id", "game_id", "commence_time", "matchup", "player", "player_id", "team", "position", "first_seen",
        "updated_at", "status", "graded_at"]


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT}).reindex(columns=COLUMNS)


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def record(rows: list[dict], asof: pd.Timestamp) -> int:
    """Add or refresh reads for games not started; started games' rows are frozen."""
    if not rows:
        return 0
    now = asof.isoformat(timespec="seconds")
    df = load()
    new = pd.DataFrame(rows)
    new = new[pd.to_datetime(new["commence_time"], utc=True, format="ISO8601") > asof].copy()
    if new.empty:
        return 0
    new["read_id"] = new["game_id"].astype(str) + ":" + new["player_id"].astype(str)
    first = dict(zip(df["read_id"], df["first_seen"])) if len(df) else {}
    new["first_seen"] = [first.get(r, now) for r in new["read_id"]]
    new["updated_at"], new["status"] = now, "open"
    keep = df[~df["read_id"].isin(new["read_id"])] if len(df) else df
    save(pd.concat([x for x in (keep, new.reindex(columns=COLUMNS)) if len(x)], ignore_index=True))
    return len(new)


def grade(stats: pd.DataFrame | None = None, snaps: pd.DataFrame | None = None, now: pd.Timestamp | None = None) -> int:
    """Scored or not, from nflverse player stats once the game's stats and snaps are out; a
    player who didn't take a snap is void."""
    df = load()
    now = now or pd.Timestamp.now(tz="UTC")
    todo = df[(df["status"] == "open") & (pd.to_datetime(df["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=4))]
    if todo.empty:
        return 0
    if stats is None or snaps is None:
        from betlab.sources import nflverse
        seasons = sorted({int(str(g)[:4]) for g in todo["game_id"]})
        stats, snaps = nflverse.load_player_stats(seasons), nflverse.load_snap_counts(seasons)
    stamp, n = now.isoformat(timespec="seconds"), 0
    for i, r in todo.iterrows():
        s, sn = stats[stats["game_id"] == r["game_id"]], snaps[snaps["game_id"] == r["game_id"]]
        if s.empty or sn.empty:
            continue
        row = s[s["player_id"] == r["player_id"]]
        played = ((sn["player_id"] == r["player_id"]) & (sn["offense_snaps"] > 0)).any()
        if len(row):
            from betlab.sources.nflverse import anytime_tds
            df.at[i, "scored"] = int(anytime_tds(row.iloc[0]) > 0)    # returns and defensive TDs count (both books)
            df.at[i, "status"] = "graded"
        elif played:
            df.at[i, "scored"], df.at[i, "status"] = 0, "graded"
        else:
            df.at[i, "status"] = "void"
        df.at[i, "graded_at"] = stamp
        n += 1
    save(df)
    return n


def summary(df: pd.DataFrame | None = None) -> dict:
    """Log loss of Pinnacle's chance vs our read's blend, and how the players the read
    liked more than the market did."""
    df = load() if df is None else df
    g = df[df["status"] == "graded"].copy() if len(df) else df
    if g.empty:
        return {"reads": int(len(df)), "graded": 0}
    # both chances on the same reads (a missing one would make numpy's mean nan, pandas' skip it)
    g = g[g["p_market"].notna() & g["p_read"].notna() & g["scored"].notna()]
    if g.empty:
        return {"reads": int(len(df)), "graded": 0}
    y = g["scored"].astype(float).to_numpy()
    ll = lambda p: float(np.mean(-(y * np.log(np.clip(p, 1e-4, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-4, 1)))))
    pm, pr = g["p_market"].astype(float).to_numpy(), g["p_read"].astype(float).to_numpy()
    liked = pr - pm >= 0.02
    return {"reads": int(len(df)), "graded": int(len(g)), "log_loss_market": round(ll(pm), 4), "log_loss_read": round(ll(pr), 4),
            "liked": int(liked.sum()), "liked_scored": round(float(y[liked].mean()), 3) if liked.any() else None,
            "liked_market_said": round(float(pm[liked].mean()), 3) if liked.any() else None,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
