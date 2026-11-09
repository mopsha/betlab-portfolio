"""The calendar's schedule (Nov 4, idea #54): every game ESPN lists for the next `DAYS` days into `schedule_games`, on the day's
first pregame tick, then a look once a day for what changed (free; about 1,000 small calls, ~10 s). ESPN refuses date ranges
(400), so it's one call per league per day. A league or day that fails keeps the rows it has: a failed read must never look
like cancelled games.
"""

from __future__ import annotations

import concurrent.futures as cf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from betlab import live_legs as L

DAYS = 70
WORKERS = 6
ET = ZoneInfo("America/New_York")
SPORTS = {"nfl": "nfl", "ncaaf": "ncaaf", "nba": "nba", "ncaab": "ncaab", "nhl": "nhl", "ufc": "ufc"}
SOCCER = dict.fromkeys(L.SOCCER, "soccer")


def league_paths() -> dict[str, str]:
    return {**{k: L.PATHS[k] for k in SPORTS}, **{k: f"soccer/{v}" for k, v in L.SOCCER.items()}}


def parse_board(league: str, board: dict) -> list[dict]:
    """Rows from one ESPN scoreboard. A UFC event is one row, its card."""
    sport = SPORTS.get(league) or SOCCER[league]
    out = []
    for e in board.get("events") or []:
        c = (e.get("competitions") or [{}])[0]
        start = e.get("date") or c.get("date")
        if not e.get("id") or not start:
            continue
        sides = {x.get("homeAway"): ((x.get("team") or {}).get("displayName") or "") for x in c.get("competitors") or []}
        home, away = (sides.get("home"), sides.get("away")) if league != "ufc" else (None, None)
        matchup = f"{away} @ {home}" if home and away else (e.get("name") or e.get("shortName") or "")
        if matchup:
            out.append({"id": f"{league}:{e['id']}", "league": league, "sport": sport, "start": start, "home": home, "away": away,
                        "matchup": matchup})
    return out


def fetch_all(now: datetime, days: int = DAYS, get=None) -> tuple[list[dict], set[tuple[str, str]]]:
    """(rows, the (league, ET day) pairs that failed)."""
    session = requests.Session()
    get = get or (lambda url: session.get(url, timeout=15).json())
    dates = [(now + timedelta(days=n)).strftime("%Y%m%d") for n in range(days)]

    def one(job):
        league, path, day = job
        extra = L.EXTRA.get(league, "")
        try:
            return league, day, parse_board(league, get(f"{L.BASE}/{path}/scoreboard?dates={day}{extra}"))
        except Exception:  # noqa: BLE001 - one day's board: it keeps the rows it has
            return league, day, None

    rows: dict[str, dict] = {}
    failed = set()
    with cf.ThreadPoolExecutor(WORKERS) as pool:
        for league, day, got in pool.map(one, [(lg, p, d) for lg, p in league_paths().items() for d in dates]):
            if got is None:
                failed.add((league, day))
            else:
                rows.update({r["id"]: r for r in got})
    return list(rows.values()), failed


def link(rows: list[dict], games: list[dict]) -> None:
    """A row's game page, when `games` holds it: same sport, within a day, both teams named (the NHL's are codes there)."""
    from betlab.novig_sync import _full

    for r in rows:
        if not r["home"] or not r["away"]:
            continue
        start = datetime.fromisoformat(r["start"].replace("Z", "+00:00"))
        for g in games:
            if g["league"] != r["sport"] or not g.get("commence_time") or abs((g["commence_time"] - start).total_seconds()) > 86400:
                continue
            sides = [{"name": _full(n, "nhl") if r["sport"] == "nhl" else n, "abbr": n} for n in (g.get("home"), g.get("away")) if n]
            if len(sides) == 2 and L.team_match(r["home"], sides[0]) and L.team_match(r["away"], sides[1]):
                r["game_id"] = g["game_id"]
                break


def changes(old: dict[str, datetime], rows: list[dict], failed: set, now: datetime) -> tuple[int, int, list[str]]:
    """(new, moved, the ids gone from days that were read): a row in a failed day or the past stays."""
    seen = {r["id"] for r in rows}
    new = sum(r["id"] not in old for r in rows)
    moved = sum(1 for r in rows if r["id"] in old
                and old[r["id"]] != datetime.fromisoformat(r["start"].replace("Z", "+00:00")))
    gone = [i for i, start in old.items() if i not in seen and start > now
            and (i.split(":")[0], start.astimezone(ET).strftime("%Y%m%d")) not in failed]
    return new, moved, gone


def run(db_url: str | None = None, now: datetime | None = None) -> str:
    """Once a day. The line carries the counts; a failure says "failed" (the watchdog reads both)."""
    import psycopg

    from betlab import config, publish

    now = now or datetime.now(ET)
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    if not db_url:
        return "calendar: no app database (SUPABASE_DB_URL): skipped"
    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15) as conn:
        last = conn.execute("select max(updated_at) from schedule_games").fetchone()[0]
        if last and last.astimezone(ET).date() == now.astimezone(ET).date():
            return "calendar: already read today"
        rows, failed = fetch_all(now)
        old = dict(conn.execute("select id, start from schedule_games").fetchall())
        games = [dict(zip(("game_id", "league", "home", "away", "commence_time"), g)) for g in conn.execute(
            "select game_id, league, home, away, commence_time from games where commence_time > now() - interval '1 day'").fetchall()]
        link(rows, games)
        new, moved, gone = changes(old, rows, failed, now)
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany("insert into schedule_games (id, league, sport, start, home, away, matchup, game_id, updated_at) "
                            "values (%s, %s, %s, %s, %s, %s, %s, %s, now()) on conflict (id) do update set start = excluded.start, "
                            "home = excluded.home, away = excluded.away, matchup = excluded.matchup, game_id = excluded.game_id, "
                            "updated_at = now()",
                            [(r["id"], r["league"], r["sport"], r["start"], r["home"], r["away"], r["matchup"], r.get("game_id")) for r in rows])
            if gone:
                cur.execute("delete from schedule_games where id = any(%s)", [gone])
            cur.execute("delete from schedule_games where start < now() - interval '2 days'")
        publish.pulse(conn)                    # open apps show the new schedule at once (live updates)
    note = f"; {len(failed)} league-days failed, kept" if failed else ""
    return f"calendar: {len(rows)} games read, {new} new, {moved} moved, {len(gone)} gone{note}"
