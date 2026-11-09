"""The shared to-do list and the weekly reviews in the app's database (More > Plan, More > Reviews).

They lived on the claude.ai page until 2026-10-02. `import_page` copies the page's documents once
(insert-only, so it can be repeated); after that Claude reads and writes them with `betlab todo`
and `betlab review`, as the owner (the service connection bypasses row-level security, so every
statement names the user)."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from betlab.publish import ts

TODO_COLS = ("id", "owner", "title", "detail", "due", "status", "done_at", "ord", "added_by", "created_at")


def todo_row(doc_id: str, d: dict) -> dict:
    """A page to-do document as a todos row (the page's `order` is `ord` here)."""
    return {"id": doc_id, "owner": d.get("owner") if d.get("owner") in ("you", "claude") else "you",
            "title": str(d.get("title") or "").strip() or "(untitled)", "detail": str(d.get("detail") or ""),
            "due": d.get("due") or None, "status": "done" if d.get("status") == "done" else "open",
            "done_at": ts(d.get("done_at")), "ord": int(float(d.get("order") or 0)),
            "added_by": d.get("added_by") or "page", "created_at": ts(d.get("created_at")) or datetime.now(timezone.utc)}


def review_row(doc_id: str, d: dict) -> dict:
    return {"id": doc_id, "title": str(d.get("title") or doc_id), "body": str(d.get("body") or ""),
            "created_at": ts(d.get("created_at")) or datetime.now(timezone.utc)}


def _insert(cur, table: str, user_id: str, rows: list[dict]) -> int:
    n = 0
    for r in rows:
        r = {k: v for k, v in r.items() if v is not None} | {"user_id": user_id}
        cols = sorted(r)
        cur.execute(f"insert into {table} ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
                    "on conflict do nothing", [r[c] for c in cols])
        n += max(cur.rowcount or 0, 0)
    return n


def import_page(conn, user_id: str, todos: dict[str, dict], reviews: dict[str, dict]) -> dict[str, int]:
    """Copy the page's to-dos and reviews (doc id -> document) for one user. Insert-only."""
    with conn.transaction(), conn.cursor() as cur:
        return {"todos": _insert(cur, "todos", user_id, [todo_row(k, v) for k, v in todos.items()]),
                "reviews": _insert(cur, "reviews", user_id, [review_row(k, v) for k, v in reviews.items()])}


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or "item"


def list_todos(conn, user_id: str, status: str | None = "open") -> list[dict]:
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cur:
        sql = "select " + ", ".join(TODO_COLS) + " from todos where user_id = %s"
        args: list = [user_id]
        if status:
            sql += " and status = %s"
            args.append(status)
        cur.execute(sql + " order by owner, due nulls last, ord", args)
        return cur.fetchall()


def add_todo(conn, user_id: str, owner: str, title: str, detail: str = "", due: str | None = None,
             todo_id: str | None = None) -> str:
    if owner not in ("you", "claude"):
        raise ValueError("owner is 'you' or 'claude'")
    tid = todo_id or f"{'c' if owner == 'claude' else 'u'}-{slug(title)}"
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("insert into todos (user_id, id, owner, title, detail, due, ord, added_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, 'claude')",
                    [user_id, tid, owner, title, detail, date.fromisoformat(due) if due else None, _ord()])
    return tid


def _ord() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


UPDATABLE = ("title", "detail", "due", "owner")


def update_todo(conn, user_id: str, todo_id: str, *, done: bool | None = None, **fields) -> int:
    """Change a to-do's fields; done=True / False ticks or reopens it."""
    sets, args = [], []
    for k, v in fields.items():
        if k not in UPDATABLE:
            raise ValueError(f"can't set {k}")
        if v is not None:
            sets.append(f"{k} = %s")
            args.append(date.fromisoformat(v) if k == "due" and v else v)
    if done is not None:
        sets += ["status = %s", "done_at = %s"]
        args += ["done" if done else "open", datetime.now(timezone.utc) if done else None]
    if not sets:
        return 0
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(f"update todos set {', '.join(sets)} where user_id = %s and id = %s", [*args, user_id, todo_id])
        return cur.rowcount or 0


def add_review(conn, user_id: str, title: str, body: str, review_id: str | None = None) -> str:
    rid = review_id or f"{datetime.now(ZoneInfo('America/New_York')).date().isoformat()}-{slug(title)}"
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("insert into reviews (user_id, id, title, body) values (%s, %s, %s, %s) "
                    "on conflict (user_id, id) do update set title = excluded.title, body = excluded.body",
                    [user_id, rid, title, body])
    return rid
