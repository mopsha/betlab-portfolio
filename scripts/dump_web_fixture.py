"""Write web/fixtures/today.json: a snapshot of the app database's shared tables for the web
app's local fixture mode (web/lib/mode.ts), so screens can be built and checked without
signing in. Shared market data only, never anyone's bets; the file is git-ignored.

    python scripts/dump_web_fixture.py          (needs SUPABASE_DB_URL in .env)
    python scripts/dump_web_fixture.py --mine   also the owner's bets, prices and parlays, to
                                                web/fixtures/mine.json (for building My bets; also git-ignored)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from betlab import config


def main() -> None:
    url = config.secret("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("SUPABASE_DB_URL is not set")
    now = datetime.now(timezone.utc)
    lo, hi = now - timedelta(days=2), now + timedelta(days=9)
    out: dict = {"dumped_at": now.isoformat()}
    with psycopg.connect(url, prepare_threshold=None, row_factory=dict_row) as conn:
        q = lambda sql, p=None: conn.execute(sql, p).fetchall()
        out["games"] = q("select * from games where commence_time between %s and %s or commence_time is null", [lo, hi])
        ids = [g["game_id"] for g in out["games"]]
        out["offers"] = q("select * from offers where active")
        out["fun_tickets"] = q("select * from fun_tickets where active")
        out["game_analysis"] = q("select * from game_analysis where game_id = any(%s)", [ids])
        out["docs"] = q("select * from docs")
        out["leg_packs"] = q("select * from leg_packs where commence_time > %s", [now])
        out["paper_picks"] = q("select * from paper_picks where current_rule")
        mine = "--mine" in sys.argv
        if mine:                       # the my_bets view and the owner's own tables (the service login sees all users)
            owner = [config.owner_user_id()]
            out["my_bets"] = q("select * from my_bets where user_id = %s", owner)
            out["quotes_rows"] = q("select * from quotes where user_id = %s", owner)
            out["custom_parlays"] = q("select * from custom_parlays where user_id = %s", owner)
            for t in ("todos", "reviews", "user_settings"):
                out[t] = q(f"select * from {t} where user_id = %s", owner)
    path = config.ROOT / "web" / "fixtures" / ("mine.json" if mine else "today.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o)), encoding="utf-8")   # ISO, as the API returns
    print(f"{path}: " + ", ".join(f"{k} {len(v)}" for k, v in out.items() if isinstance(v, list)))


if __name__ == "__main__":
    main()
