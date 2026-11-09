"""The college early read's track record: data/ledger/cfb_reads.csv.

One row per (game, kind), kind = spread or total, for every FBS game the college
previews priced. The **first** read is kept as it was first seen (the early number is the
point: the read beat the opener in 2022-25 but was only break-even against the close),
and the **last** line before kickoff is updated on every build. After the game: did the
first read's side win at the first line, and did the line move toward it by the last look
(closing-line value, in points)? Also the training set for a college ML model.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config
from betlab import odds_math as om

PATH = config.DATA_DIR / "ledger" / "cfb_reads.csv"
COLUMNS = ["read_id", "game_id", "season", "week", "kickoff", "matchup", "kind", "book",
           "first_seen", "first_side", "first_label", "first_line", "first_price", "first_strength", "first_edge",
           "updated_at", "last_side", "last_line", "last_price", "last_strength",
           "result", "status", "clv_pts", "graded_at"]
TEXT = ["read_id", "game_id", "kickoff", "matchup", "kind", "book", "first_seen", "first_side", "first_label",
        "updated_at", "last_side", "status", "graded_at"]


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT})


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def record(rows: list[dict], asof: pd.Timestamp) -> int:
    """Rows: game_id, season, week, kickoff (ISO), matchup, kind, book, side, label, line,
    price, strength, edge. First sight fills first_*; every build before kickoff updates last_*."""
    now = asof.isoformat(timespec="seconds")
    df = load().set_index("read_id", drop=False)
    n = 0
    for r in rows:
        if pd.Timestamp(r["kickoff"]) <= asof:
            continue
        rid = f"{r['game_id']}-{r['kind']}"
        last = {"updated_at": now, "last_side": r["side"], "last_line": r["line"], "last_price": r["price"],
                "last_strength": r["strength"]}
        if rid in df.index:
            for k, v in last.items():
                df.at[rid, k] = v
        else:
            new = {"read_id": rid, "game_id": r["game_id"], "season": r["season"], "week": r["week"],
                   "kickoff": r["kickoff"], "matchup": r["matchup"], "kind": r["kind"], "book": r["book"],
                   "first_seen": now, "first_side": r["side"], "first_label": r["label"], "first_line": r["line"],
                   "first_price": r["price"], "first_strength": r["strength"], "first_edge": r["edge"],
                   "status": "open", **last}
            df = pd.concat([df, pd.DataFrame([new]).set_index("read_id", drop=False)])
        n += 1
    for c in COLUMNS:
        if c not in df:
            df[c] = np.nan
    save(df.reset_index(drop=True).sort_values(["kickoff", "game_id", "kind"]))
    return n


def _side_result(kind: str, side: str, line: float, margin: float, total: float) -> str:
    """won / lost / push for the side at the line. Spread lines are home-favored-positive."""
    if kind == "spread":
        diff = (margin - line) if side == "home" else (line - margin)
    else:
        diff = (total - line) if side == "over" else (line - total)
    return "won" if diff > 0 else "lost" if diff < 0 else "push"


def _clv(kind: str, side: str, first: float, last: float) -> float:
    """Points the line moved toward the side between first sight and the last look."""
    move = last - first
    return move if side in ("home", "over") else -move


def grade(games: pd.DataFrame | None = None) -> int:
    """Grade reads whose games are final (the college games table has the score)."""
    from betlab.sources import cfbd

    df = load()
    todo = df[df["status"] == "open"]
    if todo.empty:
        return 0
    games = cfbd.games() if games is None else games
    done = games[games["margin"].notna()].set_index("game_id")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for i, r in todo.iterrows():
        if r["game_id"] not in done.index:
            continue
        g = done.loc[r["game_id"]]
        df.at[i, "result"] = float(g["margin"] if r["kind"] == "spread" else g["home_pts"] + g["away_pts"])
        df.at[i, "status"] = _side_result(r["kind"], r["first_side"], float(r["first_line"]),
                                          float(g["margin"]), float(g["home_pts"] + g["away_pts"]))
        df.at[i, "clv_pts"] = round(_clv(r["kind"], r["first_side"], float(r["first_line"]), float(r["last_line"])), 2)
        df.at[i, "graded_at"] = stamp
        n += 1
    save(df)
    return n


def summary(df: pd.DataFrame | None = None, min_strength: float = 1.0) -> dict:
    """Record of strong first reads (|strength| >= min_strength) by kind: wins, losses,
    average line move toward us, units at the first price."""
    df = load() if df is None else df
    out = {"min_strength": min_strength}
    for kind in ("spread", "total"):
        g = df[(df["kind"] == kind) & df["status"].isin(["won", "lost"])] if len(df) else df
        g = g[g["first_strength"].astype(float).abs() >= min_strength] if len(g) else g
        if g.empty:
            out[kind] = {"n": 0}
            continue
        won = g["status"] == "won"
        dec = g["first_price"].astype(float).map(om.american_to_decimal)
        out[kind] = {"n": int(len(g)), "won": int(won.sum()), "hit_rate": round(float(won.mean()), 3),
                     "clv_pts": round(float(g["clv_pts"].astype(float).mean()), 2),
                     # units at FanDuel's first price; a read first seen on the consensus line has no price
                     "units": round(float(np.where(won, dec - 1, -1.0)[dec.notna().to_numpy()].sum()), 2),
                     "priced": int(dec.notna().sum())}
    out["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out
