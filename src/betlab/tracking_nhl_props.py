"""Every NHL prop line we price at Mike's books: data/ledger/nhl_prop_lines.csv.

One row per (game, player, stat, book): FanDuel's and, from Oct 12, DraftKings' (the only book in the feed with
NHL points). `fd_*` columns hold the row's own book's prices (named before DraftKings); an empty `book` is a
FanDuel row from before Oct 12. The first look keeps the book's line and prices, the
consensus no-vig chance, our model's chance and every feature (the ML training set: the
market layer learns what the market misses from these rows); the last look before the
start updates the prices; after the game the result is filled from the NHL's box scores.
Nothing here is a pick (picks are in the ledger); `read` marks lines our game analysis
pointed at, so we learn whether it helps against the market.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config
from betlab.models import props_nhl as P

PATH = config.DATA_DIR / "ledger" / "nhl_prop_lines.csv"
KEY = ["event_id", "player", "stat"]
BASE = ["line_id", "event_id", "game_ref", "commence_time", "matchup", "book", "player", "team", "stat", "line",
        "fd_over", "fd_under", "p_market", "books", "p_model", "model_mean", "read", "first_seen",
        "updated_at", "last_line", "last_fd_over", "last_fd_under", "last_p_market"]
COLUMNS = BASE + P.PLAYER_FEATURES + P.GAME_FEATURES + ["actual", "status", "graded_at"]
TEXT = ["line_id", "event_id", "game_ref", "commence_time", "matchup", "book", "player", "team", "stat", "read",
        "first_seen", "updated_at", "status", "graded_at"]


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(PATH, dtype={c: "object" for c in TEXT}).reindex(columns=COLUMNS)


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def record(rows: list[dict], asof: pd.Timestamp) -> int:
    now = asof.isoformat(timespec="seconds")
    df = load().set_index("line_id", drop=False)
    n = 0
    for r in rows:
        if pd.Timestamp(r["commence_time"]) <= asof:
            continue
        book = r.get("book") or "fanduel"
        lid = f"{r['event_id']}|{r['player']}|{r['stat']}" + ("" if book == "fanduel" else f"|{book}")   # FanDuel's ids as before
        r = r | {"book": book}
        if lid in df.index:
            for k, v in {"updated_at": now, "last_line": r["line"], "last_fd_over": r["fd_over"],
                         "last_fd_under": r["fd_under"], "last_p_market": r["p_market"]}.items():
                df.at[lid, k] = v
        else:
            row = {c: np.nan for c in COLUMNS} | {k: v for k, v in r.items() if k in COLUMNS} | {
                "line_id": lid, "first_seen": now, "updated_at": now, "last_line": r["line"],
                "last_fd_over": r["fd_over"], "last_fd_under": r["fd_under"], "last_p_market": r["p_market"],
                "status": "open"}
            df = pd.concat([df, pd.DataFrame([row]).set_index("line_id", drop=False)])
        n += 1
    save(df.reset_index(drop=True))
    return n


def grade(skater_box=None, goalie_box=None, now: pd.Timestamp | None = None) -> int:
    """Fill each line's actual value once its game is in the NHL's stats. skater_box(game_id)
    and goalie_box(game_id) return per-player shots/points and saves (the NHL stats API)."""
    df = load()
    if df.empty:
        return 0
    now = now or pd.Timestamp.now(tz="UTC")
    todo = df[(df["status"] == "open") & (pd.to_datetime(df["commence_time"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=4))
              & df["game_ref"].notna()]
    if todo.empty:
        return 0
    from betlab.sources import nhl

    skater_box = skater_box or nhl.skater_box
    goalie_box = goalie_box or nhl.goalie_box
    cache, failed, stamp, n = {}, {}, now.isoformat(timespec="seconds"), 0
    for i, r in todo.iterrows():
        gid = str(r["game_ref"])
        if gid not in cache:
            cache[gid] = (pd.DataFrame(), pd.DataFrame())
            for attempt in range(2):          # Oct 14: the worker's calls failed for the night's last 8 games
                try:
                    cache[gid] = (skater_box(gid), goalie_box(gid))
                    break
                except Exception as exc:
                    failed[gid] = f"{type(exc).__name__}: {exc}"[:120]
                    if attempt == 0:
                        time.sleep(2)
            if not cache[gid][0].empty or not cache[gid][1].empty:
                failed.pop(gid, None)
        sk, gl = cache[gid]
        box = gl if r["stat"] == "saves" else sk
        if box is None or box.empty:
            continue
        row = box[box["plain"] == nhl._plain(r["player"])]
        if row.empty:
            df.at[i, "status"], df.at[i, "graded_at"] = "did not play", stamp
            n += 1
            continue
        df.at[i, "actual"] = float(row[r["stat"]].iloc[0])
        df.at[i, "status"], df.at[i, "graded_at"] = "graded", stamp
        n += 1
    save(df)
    if failed:   # left open for the next grade; say why instead of skipping silently
        print(f"NHL box scores unavailable for {len(failed)} game(s): " + "; ".join(f"{g} {e}" for g, e in failed.items()))
    return n


def summary(df: pd.DataFrame | None = None) -> dict:
    """Graded lines: log loss of the consensus, FanDuel's own no-vig price and our model on
    the over, and the over hit rate for lines that fit the read. FanDuel's lines, comparable with the weeks before
    DraftKings; DraftKings' are counted (`draftkings_lines`)."""
    df = load() if df is None else df
    n_dk = int((df["book"] == "draftkings").sum()) if len(df) else 0
    df = df[df["book"].fillna("fanduel") == "fanduel"] if len(df) else df
    g = df[df["status"] == "graded"] if len(df) else df
    out = {"lines": int(len(df)), "graded": int(len(g)), "draftkings_lines": n_dk, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if g.empty:
        return out
    y = (pd.to_numeric(g["actual"]) > pd.to_numeric(g["line"])).astype(float)

    def ll(p):
        p = pd.to_numeric(p, errors="coerce")
        ok = p.notna()
        if not ok.any():
            return None
        q = np.clip(p[ok], 1e-6, 1 - 1e-6)
        return round(float(-np.mean(y[ok] * np.log(q) + (1 - y[ok]) * np.log(1 - q))), 4)

    # the same lines for both (Oct 20: over all rows, 0.518 model vs 0.640 market compared different lines, since about
    # 40% have no two-sided market price: on the same 1,717 lines the model was the worse, 0.649 vs 0.640)
    both = pd.to_numeric(g["p_market"], errors="coerce").notna() & pd.to_numeric(g["p_model"], errors="coerce").notna()
    out |= {"logloss_market": ll(g["p_market"].where(both)), "logloss_model": ll(g["p_model"].where(both)),
            "compared": int(both.sum()), "over_rate": round(float(y.mean()), 3)}
    priced = pd.to_numeric(g["p_market"], errors="coerce").notna()
    reads = g[(g["read"].fillna("") != "") & priced]           # hit rates beside the market's chance on the same lines
    if len(reads):
        up = reads["read"].str.contains("above")
        yr = (pd.to_numeric(reads["actual"]) > pd.to_numeric(reads["line"])).astype(float)
        out["reads"] = {"n": int(len(reads)), "over_hit_when_above": round(float(yr[up].mean()), 3) if up.any() else None,
                        "over_hit_when_below": round(float(yr[~up].mean()), 3) if (~up).any() else None,
                        "market_over_when_above": round(float(pd.to_numeric(reads.loc[up, "p_market"]).mean()), 3) if up.any() else None}
    return out
