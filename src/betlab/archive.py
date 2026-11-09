"""The closing-line archive (Nov 4, idea #22): every saved odds pull boiled down to one row per book and bet, its first and last price
before the start, for studies that would otherwise read every file. Built on demand from data/odds (committed, so it's never the only
copy), into data/cache (gitignored): `betlab archive`. Each bet: sport, event, market, book, outcome, player, point, with the first and
last price and when each was seen, and how many pulls saw it. "last" is our last look, not the book's true close: a game pulled once
has first = last, and a close means more the nearer `last_at` is to `commence_time`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

KEYS = ["sport_key", "event_id", "market", "bookmaker", "outcome", "player", "point"]
COLUMNS = KEYS + ["commence_time", "home_team", "away_team", "snapshot_ts", "price"]


def path() -> Path:
    from betlab import config

    return config.CACHE_DIR / "archive" / "lines.parquet"


def boil(rows: pd.DataFrame) -> pd.DataFrame:
    """Many pulls' rows -> one per bet. A row seen at or after its game's start is no price you could have had, so it's left out."""
    r = rows.copy()
    for c in ("snapshot_ts", "commence_time"):
        r[c] = pd.to_datetime(r[c], utc=True, format="ISO8601", errors="coerce")
    r = r[r["snapshot_ts"] < r["commence_time"]].dropna(subset=["price"])
    r[["player", "point"]] = r[["player", "point"]].astype(object).where(r[["player", "point"]].notna(), None)
    r["player"], r["point"] = r["player"].fillna(""), pd.to_numeric(r["point"], errors="coerce").fillna(-9999.0)
    r = r.sort_values("snapshot_ts", kind="stable")
    g = r.groupby(KEYS, sort=False, dropna=False)
    out = g.agg(commence_time=("commence_time", "last"), home_team=("home_team", "last"), away_team=("away_team", "last"),
                first_price=("price", "first"), last_price=("price", "last"), first_at=("snapshot_ts", "first"), last_at=("snapshot_ts", "last"),
                pulls=("price", "size")).reset_index()
    out["point"] = out["point"].where(out["point"] != -9999.0)
    return out


def build(kinds: tuple[str, ...] = ("pick", "props", "goals"), root: Path | None = None) -> pd.DataFrame:
    """Everything in data/odds of these kinds, one file at a time so a season of props fits in memory."""
    from betlab import config

    root = root or config.DATA_DIR / "odds"
    parts = []
    for kind in kinds:
        for f in sorted(root.glob(f"*/*/*_{kind}.parquet")):
            try:
                parts.append(pd.read_parquet(f, columns=COLUMNS))
            except (OSError, ValueError, KeyError) as exc:     # a bad file is one pull missing, not the archive
                print(f"archive: skipped {f.name} ({type(exc).__name__})")
    return boil(pd.concat(parts, ignore_index=True)) if parts else pd.DataFrame()


def run() -> str:
    a = build()
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    a.to_parquet(p, compression="zstd", index=False)
    return f"archive: {len(a):,} bets across {a['event_id'].nunique():,} events, {p.stat().st_size / 2**20:.1f} MB at {p}"
