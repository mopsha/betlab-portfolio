"""Every NBA prop line BetLab priced at Mike's books: data/ledger/nba_prop_lines.csv.

One row per (event, player, stat, book): the book's line and prices (`fd_over` / `fd_under` hold the row's own
book's prices, named before DraftKings; `book` is empty for FanDuel rows logged before Oct 12), the market's fair P(over),
player model v3's P(over) and projection, and every feature it used, then the result once
the box score is out. This is the NBA ML layer's training set (docs/NBA_PLAN.md): the model
learns what the market misses from these rows. Rows update with each pricing until tip-off
and then freeze. Nothing here is a pick.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from betlab.timefmt import utc_starts
from betlab import config

PATH = config.DATA_DIR / "ledger" / "nba_prop_lines.csv"
FEATURES = ["mu", "min_proj", "ewm_min", "start_share", "missing_min", "missing_points_share", "abs_margin",
            "returning", "pace_factor", "questionable", "lineup_known", "starter_now"]
COLUMNS = (["line_id", "event_id", "tipoff", "matchup", "book", "player", "athlete_id", "team", "opp", "stat", "line",
            "fd_over", "fd_under", "p_market", "p_model", "market_source"] + FEATURES
           + ["first_seen", "updated_at", "actual", "status", "graded_at"])
TEXT = ["line_id", "event_id", "tipoff", "matchup", "book", "player", "team", "opp", "stat", "market_source",
        "first_seen", "updated_at", "status", "graded_at"]
COMBOS = {"pra": ("points", "rebounds", "assists"), "pr": ("points", "rebounds"),
          "pa": ("points", "assists"), "ra": ("rebounds", "assists")}
BOX = {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes": "three_point_field_goals_made"}


def line_id(event_id, athlete_id, stat, book: str | None = "fanduel") -> str:
    """FanDuel's ids are unchanged from before DraftKings; another book's line adds its name."""
    key = f"{event_id}|{athlete_id}|{stat}" + ("" if book in (None, "fanduel") or pd.isna(book) else f"|{book}")
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def fanduel(df: pd.DataFrame) -> pd.DataFrame:
    """FanDuel's rows (an empty book is FanDuel: rows from before Oct 12)."""
    return df[df["book"].fillna("fanduel") == "fanduel"] if "book" in df else df


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(PATH, dtype={c: "object" for c in TEXT}).reindex(columns=COLUMNS)
    df["actual"] = df["actual"].astype(float)
    return df


def save(df: pd.DataFrame) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    utc_starts(df[COLUMNS]).to_csv(PATH, index=False)


def record(rows: list[dict], asof: pd.Timestamp) -> int:
    """Upsert lines for games that haven't tipped; returns rows written."""
    new = pd.DataFrame(rows)
    if new.empty:
        return 0
    new = new[pd.to_datetime(new["tipoff"], utc=True, format="ISO8601") > asof].copy()
    if new.empty:
        return 0
    now = asof.isoformat(timespec="seconds")
    if "book" not in new:
        new["book"] = "fanduel"
    new["line_id"] = [line_id(e, a, s, b) for e, a, s, b in zip(new["event_id"], new["athlete_id"], new["stat"], new["book"])]
    new["updated_at"], new["status"] = now, "open"
    old = load()
    first = old.set_index("line_id")["first_seen"] if len(old) else pd.Series(dtype=str)
    new["first_seen"] = new["line_id"].map(first).fillna(now)
    keep = old[~old["line_id"].isin(new["line_id"])] if len(old) else old
    for c in COLUMNS:
        if c not in new:
            new[c] = np.nan
    save(pd.concat([keep, new[COLUMNS]], ignore_index=True).sort_values(["tipoff", "event_id", "player"]))
    return len(new)


def grade(box: pd.DataFrame | None = None, now: pd.Timestamp | None = None) -> int:
    """Fill `actual` from ESPN box scores (the player's game on the tip-off's Eastern date):
    the stat (or the combo's sum), or void if he didn't play. Returns rows graded."""
    df = load()
    if df.empty:
        return 0
    now = now or pd.Timestamp.now(tz="UTC")
    todo = df[(df["status"] == "open") & (pd.to_datetime(df["tipoff"], utc=True, format="ISO8601") < now - pd.Timedelta(hours=4))]
    if todo.empty:
        return 0
    if box is None:
        from betlab.sources import nba
        box = nba.load_player_box([nba.current_season()], max_age_hours=1.0)   # last night's games
    b = box.copy()
    b["date"] = pd.to_datetime(b["game_date"]).dt.strftime("%Y-%m-%d")
    b["minutes"] = pd.to_numeric(b["minutes"], errors="coerce")
    b = b.set_index(["athlete_id", "date"])
    stamp = now.isoformat(timespec="seconds")
    n = 0
    for i, r in todo.iterrows():
        day = pd.Timestamp(r["tipoff"]).tz_convert("America/New_York").strftime("%Y-%m-%d")
        key = (int(float(r["athlete_id"])), day)
        if key not in b.index:
            continue  # not published yet
        g = b.loc[key]
        g = g.iloc[0] if isinstance(g, pd.DataFrame) else g
        if not (g["minutes"] > 0):
            df.at[i, "status"] = "void"
        else:
            parts = COMBOS.get(r["stat"], (r["stat"],))
            df.at[i, "actual"] = float(sum(float(g[BOX[p]]) for p in parts))
            df.at[i, "status"] = "graded"
        df.at[i, "graded_at"] = stamp
        n += 1
    save(df)
    return n


def summary(df: pd.DataFrame | None = None) -> dict:
    """How the model's lean and the market did on graded lines (for the page): FanDuel's lines, so the record
    stays comparable with the weeks before DraftKings (its lines are counted)."""
    df = load() if df is None else df
    n_dk = int((df["book"] == "draftkings").sum()) if len(df) and "book" in df else 0
    df = fanduel(df) if len(df) else df
    g = df[(df["status"] == "graded") & df["actual"].notna()] if len(df) else df
    g = g[g["actual"] != g["line"].astype(float)] if len(g) else g
    if g.empty:
        return {"lines": int(len(df)), "graded": 0}
    # the model and the market on the same lines (pandas' mean skips missing chances, so each would be over its own)
    g = g[pd.to_numeric(g["p_market"], errors="coerce").notna() & pd.to_numeric(g["p_model"], errors="coerce").notna()]
    if g.empty:
        return {"lines": int(len(df)), "graded": 0, "draftkings_lines": n_dk}
    over = (g["actual"] > g["line"].astype(float)).astype(float)
    ll = lambda p: float(-np.mean(over * np.log(np.clip(p, 1e-6, 1)) + (1 - over) * np.log(np.clip(1 - p, 1e-6, 1))))
    return {"lines": int(len(df)), "graded": int(len(g)), "draftkings_lines": n_dk,
            "logloss_market": ll(g["p_market"].astype(float)), "logloss_model": ll(g["p_model"].astype(float)),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
