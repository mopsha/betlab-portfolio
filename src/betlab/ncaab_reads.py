"""College basketball reads: data/ledger/ncaab_reads.csv.

One row per game where our efficiency margin and the posted spread (FanDuel's; DraftKings'
from ESPN while college basketball runs on free lines, the `book` column) differed by 3+ points
(cards/ncaab.py; the gap is kept, so each size can be judged). The FIRST sighting is kept as it was (that's the number the backtest's
edge is about: the line moved toward the model after the opener); the latest FanDuel line
updates until tip-off. After the game, from CollegeBasketballData:
- **clv_pts:** how far the closing consensus spread moved toward the read's side from the
  first line (the backtest: +0.38 pts at 3+ disagreement, +0.56 at 5+),
- **result:** won / lost / push against the first line.
Reads are not picks: they earn that only if live CLV confirms the backtest.

Totals (Oct 12, `kind` "total"; spreads are "spread", the default for older rows): our total against the
posted total when they differ by 4+ points (cards/ncaab TOTAL_READ_MIN). The backtest saw totals move toward
the model too, but less (+0.2 to +0.35 pts, about +0.5% to +0.8% CLV), so these are tracked to see whether
that's enough. For a total, side is Over / Under, the lines are totals, `model_total` is our number and
`home_margin` holds the final total; clv_pts is the close's move in the read's direction.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config

PATH = config.DATA_DIR / "ledger" / "ncaab_reads.csv"
COLUMNS = ["read_id", "event_id", "game_id", "commence_time", "matchup", "home", "away", "first_seen",
           "side", "first_line", "first_price", "first_gap", "model_margin", "roster_shift", "market_center",
           "updated_at", "last_line", "last_price", "last_gap", "close_line", "home_margin", "result", "clv_pts",
           "status", "graded_at", "book", "kind", "model_total"]
TEXT = ["read_id", "event_id", "game_id", "commence_time", "matchup", "home", "away", "first_seen", "side",
        "updated_at", "result", "status", "graded_at", "book", "kind"]


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT}).reindex(columns=COLUMNS)


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def record(reads: list[dict], asof: pd.Timestamp) -> int:
    """Log new reads (first sighting kept) and update the latest line of known ones."""
    if not reads:
        return 0
    now = asof.isoformat(timespec="seconds")
    df = load().set_index("read_id", drop=False)
    n = 0
    for r in reads:
        if pd.Timestamp(r["commence_time"]) <= asof:
            continue
        kind = r.get("kind", "spread")
        rid = str(r["event_id"]) if kind == "spread" else f"{r['event_id']}:total"
        same = rid in df.index and (kind == "total" or r["side"] == df.at[rid, "side"])
        last = {"updated_at": now, "last_line": r["line"] if same else -r["line"],
                "last_price": r["price"], "last_gap": r["gap"]} if rid in df.index else None
        if last:
            for k, v in last.items():
                df.at[rid, k] = v
        else:
            row = {c: np.nan for c in COLUMNS} | {
                "read_id": rid, "event_id": r["event_id"], "game_id": r.get("game_id"),
                "commence_time": r["commence_time"], "matchup": r["matchup"], "home": r["home"], "away": r["away"],
                "first_seen": now, "side": r["side"], "first_line": r["line"], "first_price": r["price"],
                "first_gap": r["gap"], "model_margin": r.get("model_margin"), "roster_shift": r.get("roster_shift"),
                "kind": kind, "model_total": r.get("model_total"),
                "market_center": r["market_center"], "book": r.get("book", "fanduel"),
                "updated_at": now, "last_line": r["line"], "last_price": r["price"], "last_gap": r["gap"],
                "status": "open"}
            df = pd.concat([df, pd.DataFrame([row]).set_index("read_id", drop=False)])
        n += 1
    save(df.reset_index(drop=True))
    return n


def grade(games: pd.DataFrame | None = None, now: pd.Timestamp | None = None) -> int:
    """Result and closing-line move for reads whose game is final (from the saved CBBD
    history, refreshed daily)."""
    df = load()
    if df.empty:
        return 0
    now = now or pd.Timestamp.now(tz="UTC")
    todo = df[(df["status"] == "open") & (pd.to_datetime(df["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=4))]
    if todo.empty:
        return 0
    if games is None:
        from betlab.sources import cbbd
        games = cbbd.games()
    stamp, n = now.isoformat(timespec="seconds"), 0
    for i, r in todo.iterrows():
        by_id = "game_id" in games and pd.notna(r.get("game_id"))
        g = games[games["game_id"].astype(str) == str(r["game_id"])] if by_id else games.iloc[:0]
        if g.empty:
            day = pd.Timestamp(r["commence_time"]).tz_convert("America/New_York").tz_localize(None).normalize()
            g = games[(games["home_team"] == r["home"]) & (games["away_team"] == r["away"])
                      & ((games["date"] - day).abs() <= pd.Timedelta(days=1))]
        if g.empty:
            continue
        g = g.iloc[0]
        if str(r.get("kind") or "spread") == "total":
            line, over = float(r["first_line"]), r["side"] == "Over"
            final = float(g["home_pts"]) + float(g["away_pts"]) if "home_pts" in g else float(g["total"])
            res = (final - line) * (1 if over else -1)
            df.at[i, "home_margin"] = final
            df.at[i, "result"] = "won" if res > 0 else "lost" if res < 0 else "push"
            if pd.notna(g.get("total_line")):
                close = float(g["total_line"])
                df.at[i, "close_line"] = close
                df.at[i, "clv_pts"] = round((close - line) * (1 if over else -1), 2)   # the close moved our way
            df.at[i, "status"], df.at[i, "graded_at"] = "graded", stamp
            n += 1
            continue
        flip = 1.0 if g["home_team"] == r["home"] else -1.0   # neutral sites: the feeds can swap home and away
        home_side = r["side"] == r["home"]
        sign = 1.0 if home_side else -1.0
        margin = flip * float(g["margin"])                    # the read's home team's margin
        line = float(r["first_line"])                          # the read side's own spread (home or away)
        res = sign * margin + line
        df.at[i, "home_margin"] = margin
        df.at[i, "result"] = "won" if res > 0 else "lost" if res < 0 else "push"
        if pd.notna(g.get("spread_line")):
            close_home_pts = -flip * float(g["spread_line"])   # the close as the read's home team's spread
            close_side = close_home_pts if home_side else -close_home_pts
            df.at[i, "close_line"] = close_side
            df.at[i, "clv_pts"] = round(line - close_side, 2)  # a close that asks more of our side is value for us
        df.at[i, "status"], df.at[i, "graded_at"] = "graded", stamp
        n += 1
    save(df)
    return n


def summary(df: pd.DataFrame | None = None, kind: str | None = None) -> dict:
    """The record; `kind` "spread" or "total" for one kind (None: spreads and totals each, and all)."""
    df = load() if df is None else df
    if kind is None and len(df):
        k = df["kind"].fillna("spread")
        out = summary(df[k == "spread"], "spread")
        if (k == "total").any():
            out["totals"] = summary(df[k == "total"], "total")
        return out
    g = df[df["status"] == "graded"] if len(df) else df
    if g.empty:
        return {"reads": int(len(df)), "graded": 0}
    decided = g[g["result"].isin(["won", "lost"])]
    clv = pd.to_numeric(g["clv_pts"], errors="coerce").dropna()
    return {"reads": int(len(df)), "graded": int(len(g)), "won": int((decided["result"] == "won").sum()),
            "lost": int((decided["result"] == "lost").sum()),
            "avg_clv_pts": round(float(clv.mean()), 2) if len(clv) else None,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
