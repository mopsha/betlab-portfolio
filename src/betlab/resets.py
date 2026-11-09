"""Bet resets: a lost bet's stake comes back as a bonus bet in the wallet (Mike, Nov 1).

A bet with `bets.reset` (FanDuel's BET RESET TOKEN) that loses counts as the loss it is, and its stake, in dollars, goes
in the owner's wallet as a bonus bet. The database's `issue_resets()` (migration 0031) does the work and takes back an
unused token when a grade changes. Free: it runs on every pre-game tick, like ladders.
"""

from __future__ import annotations

from betlab import config


def run(db_url: str | None = None) -> str:
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    if not db_url:
        return "bet resets: no app database (SUPABASE_DB_URL): skipped"
    import psycopg

    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
        added = c.execute("select issue_resets()").fetchone()[0]
    return f"bet resets: {added} bonus bets added"
