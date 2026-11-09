"""Every FanDuel main prop line the Games tab has seen: data/ledger/prop_lines.csv.

One row per (game, player, stat): FanDuel's line and prices, the market's fair P(over),
every feature we compute (pass matchup, projected dropbacks, the QB and weather
adjustment, the receiver matchups), our reads (script lean, matchup note) and, after
the game, what happened. Two uses:

- **Track record.** The script lean and the matchup notes were each fit on one season
  (2025). Grading every line this season makes 2026 their second test, for free.
- **Training data.** A future machine-learning props model learns from exactly these
  rows: the market's price, the features, the result (docs/ROADMAP.md).

Rows update with each preview build until kickoff, so the latest read before the game is
the one that counts (the market is sharpest then), and freeze after. Unlike the pick
ledger this isn't a betting record: nothing here was a pick.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config

PATH = config.DATA_DIR / "ledger" / "prop_lines.csv"
KEY = ["game_id", "player_id", "stat"]
COLUMNS = [
    "line_id", "season", "week", "game_id", "commence_time", "matchup", "player", "player_id", "team", "opp",
    "stat", "line", "fd_over", "fd_under", "p_market", "pass_edge", "dropbacks_log", "pass_adj", "ypt", "deep",
    "p_script", "script_side", "matchup_score", "p_matchup", "matchup_side", "first_seen", "updated_at",
    "actual", "status", "graded_at",
]
READS = {"script": ("script_side", "p_script"), "matchup": ("matchup_side", "p_matchup")}


def line_id(game_id: str, player_id: str, stat: str) -> str:
    return hashlib.sha1(f"{game_id}|{player_id}|{stat}".encode()).hexdigest()[:12]


TEXT = ["line_id", "game_id", "commence_time", "matchup", "player", "player_id", "team", "opp", "stat",
        "script_side", "matchup_side", "first_seen", "updated_at", "status", "graded_at"]


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(PATH, dtype={c: "object" for c in TEXT})
    df["actual"] = df["actual"].astype(float)
    return df


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def record(rows: list[dict], asof: pd.Timestamp) -> int:
    """Upsert this build's lines for games that haven't kicked off; returns rows written."""
    now = asof.isoformat(timespec="seconds")
    new = pd.DataFrame(rows)
    if new.empty:
        return 0
    new = new[pd.to_datetime(new["commence_time"], utc=True, format="ISO8601") > asof].copy()
    if new.empty:
        return 0
    new["line_id"] = [line_id(*k) for k in new[KEY].itertuples(index=False)]
    new["updated_at"], new["status"] = now, "open"
    old = load()
    first = old.set_index("line_id")["first_seen"] if len(old) else pd.Series(dtype=str)
    new["first_seen"] = new["line_id"].map(first).fillna(now)
    keep = old[~old["line_id"].isin(new["line_id"])] if len(old) else old
    for c in COLUMNS:
        if c not in new:
            new[c] = np.nan
    save(pd.concat([keep, new[COLUMNS]], ignore_index=True).sort_values(["commence_time", "game_id", "player"]))
    return len(new)


def grade(now: pd.Timestamp | None = None) -> int:
    """Fill `actual` for lines whose game ended (4+ hours after kickoff) once nflverse has
    the stats and snap counts: the stat, 0 for a player who played without one, or void
    if he didn't play. Returns how many rows were graded."""
    from betlab.sources import nflverse

    df = load()
    if df.empty:
        return 0
    now = now or pd.Timestamp.now(tz="UTC")
    todo = df[(df["status"] == "open") & (pd.to_datetime(df["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=4))]
    if todo.empty:
        return 0
    seasons = sorted({int(s) for s in todo["season"]})
    ps, sn = nflverse.load_player_stats(seasons), nflverse.load_snap_counts(seasons)
    stamp = now.isoformat(timespec="seconds")
    n = 0
    for gid, g in todo.groupby("game_id"):
        g_ps, g_sn = ps[ps["game_id"] == gid], sn[sn["game_id"] == gid]
        if g_ps.empty or g_sn.empty:
            continue  # not published yet
        stats = g_ps.drop_duplicates("player_id").set_index("player_id")
        played = set(g_sn.loc[(g_sn["offense_snaps"] > 0), "player_id"])
        for i, r in g.iterrows():
            if r["player_id"] in stats.index:
                df.at[i, "actual"], df.at[i, "status"] = float(stats.at[r["player_id"], r["stat"]]), "graded"
            elif r["player_id"] in played:
                df.at[i, "actual"], df.at[i, "status"] = 0.0, "graded"
            else:
                df.at[i, "status"] = "void"
            df.at[i, "graded_at"] = stamp
            n += 1
    save(df)
    return n


def summary(df: pd.DataFrame | None = None) -> dict:
    """Each read's record on graded lines: how often its side hit, what the market gave
    that side, and flat 1-unit profit at FanDuel's price (for learning, not a bet record)."""
    from betlab import odds_math as om

    df = load() if df is None else df
    out = {}
    g = df[(df["status"] == "graded") & df["actual"].notna()] if len(df) else df
    for kind, (side_col, p_col) in READS.items():
        s = g[g[side_col].isin(["over", "under"])] if len(g) else g
        s = s[s["actual"] != s["line"]] if len(s) else s  # pushes out
        if s.empty:
            out[kind] = {"n": 0}
            continue
        over = s[side_col] == "over"
        hit = np.where(over, s["actual"] > s["line"], s["actual"] < s["line"])
        p_mkt = np.where(over, s["p_market"], 1 - s["p_market"])
        p_read = np.where(over, s[p_col], 1 - s[p_col])
        price = np.where(over, s["fd_over"], s["fd_under"])
        dec = np.array([om.american_to_decimal(float(x)) for x in price])
        out[kind] = {"n": int(len(s)), "hits": int(hit.sum()), "hit_rate": round(float(hit.mean()), 3),
                     "market": round(float(p_mkt.mean()), 3), "read": round(float(p_read.mean()), 3),
                     "units": round(float(np.where(hit, dec - 1, -1.0).sum()), 2)}
    out["lines"] = int(len(df))
    out["graded"] = int(len(g))
    out["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out
