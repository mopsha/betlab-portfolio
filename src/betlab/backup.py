"""The app database's nightly backup (Nov 4, idea #76): what exists nowhere else, written to `data/backups/app_db.json` by the
day's first pregame tick (after the 3 AM grade), so the worker's commit puts every day's copy in git's history. One row per
line, so a day's commit holds only what changed. Restoring is by hand (docs/OPERATIONS.md).

`TABLES` is a list of what to copy, never "everything": push and Live Activity tokens stay out of the repo. The market's own
tables (games, offers, tickets) stay out too: `publish` rebuilds them from `data/` and `exports/`.

A copy much smaller than the last one is refused and the last one kept: an empty read must not look like a good night.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TABLES = ["bets", "bet_history", "promos", "slip_prices", "custom_parlays", "quotes", "ladders", "challenges", "user_settings", "profiles",
          "friendships", "reviews", "todos"]
SHRINK = 0.5      # fewer rows than this share of the last copy: refused
ET = ZoneInfo("America/New_York")


def _path() -> Path:
    from betlab import config

    return config.DATA_DIR / "backups" / "app_db.json"


def _last(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def dump(tables: dict[str, list[dict]], day: str) -> str:
    lines = [f'{{"day": {json.dumps(day)}, "tables": {{']
    for i, (table, rows) in enumerate(tables.items()):
        lines.append(f"{json.dumps(table)}: [")
        lines += [json.dumps(r, sort_keys=True, ensure_ascii=False) + ("," if j < len(rows) - 1 else "") for j, r in enumerate(rows)]
        lines.append("]" + ("," if i < len(tables) - 1 else ""))
    return "\n".join(lines + ["}}"]) + "\n"


def write(tables: dict[str, list[dict]], day: str, path: Path) -> str:
    """Save the copy (whole or not at all); the line says what happened, "failed" if it was refused (the watchdog reads it)."""
    total = sum(len(r) for r in tables.values())
    before = sum(len(r) for r in (_last(path).get("tables") or {}).values())
    if total < before * SHRINK:
        return f"backup failed: {total} rows against {before} in the last copy, kept the last copy"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(dump(tables, day), encoding="utf-8")   # a full disk cuts this off, not the last good copy (Oct 18)
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(path)
    return f"backup: {total} rows in {len(tables)} tables"


def run(db_url: str | None = None, now: datetime | None = None, path: Path | None = None) -> str:
    """Once a day: a later tick finds today's copy and stops, and a tick missed at dawn is made up by the next one."""
    import psycopg

    from betlab import config

    path = path or _path()
    day = (now or datetime.now(ET)).astimezone(ET).date().isoformat()
    if _last(path).get("day") == day:
        return f"backup: already taken for {day}"
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    if not db_url:
        return "backup: no app database (SUPABASE_DB_URL): skipped"
    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15) as conn:
        tables = {t: [r[0] for r in conn.execute(f"select to_jsonb(x) from {t} x order by to_jsonb(x)::text").fetchall()] for t in TABLES}
    return write(tables, day, path)
