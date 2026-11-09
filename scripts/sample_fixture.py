"""Write web/fixtures/today.json without the database: the same rows `betlab publish` would send, built from
the repo's own exports and ledgers (publish.build_rows). For the web's local fixture preview on a machine with
no SUPABASE_DB_URL (the Mac). Shared market data only, never anyone's bets; the file is git-ignored.

    python scripts/sample_fixture.py
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from betlab import cli, config, fun_ledger, ledger, publish
from betlab.golive import current_rule


def _plain(v):
    """JSON the browser can parse: missing numbers as null (NaN isn't JSON), dates as ISO."""
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if v is None or isinstance(v, (str, int, bool)):
        return v
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return str(v)


def main() -> None:
    products = cli.page_products(novig=False)                 # no network: Novig's parlay prices are left out
    packs = [(doc_id, body) for coll, doc_id, body in cli.page_docs(products) if coll == "fun_legs"]
    picks, leans = ledger.load(), ledger.load(ledger.LEANS)
    current = set(current_rule(picks)["pick_id"]) | set(current_rule(leans, picks=False)["pick_id"])
    rows = publish.build_rows(products, picks, leans, fun_ledger.load(), packs, current, {})
    now = datetime.now(timezone.utc).isoformat()
    out: dict = {"dumped_at": now}
    for table in ("games", "offers", "fun_tickets", "game_analysis", "docs", "leg_packs", "paper_picks"):
        out[table] = [{"active": True, "published_at": now, "updated_at": now, **r} for r in rows[table]]
    out["paper_picks"] = [r for r in out["paper_picks"] if r.get("current_rule")]
    path = config.ROOT / "web" / "fixtures" / "today.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_plain(out), allow_nan=False), encoding="utf-8")
    print(f"{path}: " + ", ".join(f"{k} {len(v)}" for k, v in out.items() if isinstance(v, list)))


if __name__ == "__main__":
    main()
