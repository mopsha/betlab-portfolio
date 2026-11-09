"""Key rotation reminders (Mike's #83, Nov 2): config/key_rotation.yaml says when each key last changed; a key past
`every_days` gets a to-do for Mike and one alert. Finishing the to-do counts as rotating it. This file only ever sees a key's
name and where it lives, never its value, and Claude never does the rotating (CLAUDE.md, hard rule 1).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import yaml

from betlab import alert_prefs, config

PREFIX = "u-rotate-"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load() -> dict:
    return yaml.safe_load((config.CONFIG_DIR / "key_rotation.yaml").read_text(encoding="utf-8"))


def due(cfg: dict, todos: list[tuple[str, date | None]], today: date) -> list[dict]:
    """Keys past their time with no open to-do. `todos`: (id, done date or None) of the rotation to-dos."""
    every = timedelta(days=int(cfg["every_days"]))
    out = []
    for k in cfg["keys"]:
        s = slug(k["name"])
        mine = [t for t in todos if t[0].startswith(f"{PREFIX}{s}-")]
        last = max([k["rotated"]] + [d for _, d in mine if d])
        if today >= last + every and not any(d is None for _, d in mine):
            out.append(k | {"slug": s, "last": last})
    return out


def run(db_url: str | None = None, owner: str | None = None, today: date | None = None, alert=None) -> str:
    from betlab import alerts

    db_url = db_url or config.secret("SUPABASE_DB_URL")
    owner = owner or config.owner_user_id()
    if not (db_url and owner):
        return "key rotation: no app database or owner: skipped"
    today = today or datetime.now(alert_prefs.ET).date()
    cfg = load()
    import psycopg

    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
        rows = c.execute("select id, done_at from todos where user_id = %s and id like %s", [owner, PREFIX + "%"]).fetchall()
        todos = [(i, d.date() if d else None) for i, d in rows]
        keys = due(cfg, todos, today)
        for k in keys:
            c.execute("insert into todos (user_id, id, owner, title, detail, due, added_by) values (%s, %s, 'you', %s, %s, %s, 'claude') "
                      "on conflict do nothing",
                      [owner, f"{PREFIX}{k['slug']}-{today:%Y%m%d}", f"Rotate the {k['name']}",
                       f"Last changed {k['last']}. Where it lives: {k['where']}. Mark this done once it's changed.", today])
    if keys:
        (alert or alerts.problem)("key rotation", [f"rotate the {k['name']}" for k in keys])
    return f"key rotation: {len(cfg['keys'])} keys, {len(keys)} newly due"
