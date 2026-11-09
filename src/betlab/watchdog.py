"""The zero watchdog (Oct 30): a feature that quietly reports zero for a day is a fault, not a quiet day.

On Oct 29-30 Novig moved its parlay pricer and every publish logged "novig parlays (fun): 0 priced" for two days: no
error, no exit code, nothing in `runs` to see unless you read it. This reads the worker's `runs` logs for one Eastern
day (yesterday, from the 9:55 daily) and sends the owner one problem alert (`alerts.problem("watchdog")`) for:

- **None of many** (`RATIOS`): a step logs "N of M", and over the day M added up to plenty while N stayed 0 (Novig
  priced none of the slips it lists every leg of; live CLV priced none of the open bets).
- **Gone quiet** (`USUAL`): a count that was above zero on most of the last week's days is zero on a day the worker
  published as usual (Novig's game-page prices, the card's leans, offers published, slice locks).
- **Swallowed errors** (`SWALLOWED`): a step that exited 0 but logged an exception or "failed" / "not priced" (a soft
  step's own try/except, e.g. "NBA absences skipped (TypeError ...)").
- **Stuck open** (`stale_open`, Nov 9): bets (any account's, from `my_bets`) still open `STALE_HOURS` after their last
  game's start: a grader that can't read them stays quiet, so this counts them and names up to 3.

Counts that are honestly zero on quiet days (pick alerts, fun parlays, leg alerts) are not watched. Read-only: it
reads `runs` and alerts; `betlab watchdog --no-alert` prints the findings only.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# (what, step, "N of M" pattern, least M over the day). Every match in a log counts (publish prints one line per doc).
RATIOS = [
    ("Novig parlays priced none", "publish", r"novig parlays \([^)]*\): (\d+) of (\d+) priced", 10),
    ("live CLV priced no open bet", "publish", r"live CLV: (\d+) of (\d+) open bet", 30),
]

# (what, step, pattern, "sum" or "max" over the day): zero on a normal day after being above zero on most of the week.
USUAL = [
    ("Novig game-page prices gone", "publish", r"novig tables: (\d+) rows priced", "sum"),
    ("the card has no leans", "card", r"(\d+) leans", "max"),
    ("no offers published", "publish", r"offers (\d+)", "max"),
    ("no slice locked", "lock-due", r"slices to lock: (\S+)", "count"),
    ("no backup taken", "backup", r"backup: (\d+) rows", "max"),
    ("the calendar read no games", "calendar", r"calendar: (\d+) games read", "max"),
]
WEEK, MOST, NORMAL_PUBLISHES = 7, 5, 8   # the last 7 days; above zero on 5+ of them; 8+ publishes makes a normal day

SWALLOWED = re.compile(r"[^\n]{0,60}(?:\b\w*(?:Error|Exception)\b[:(]|\bTraceback\b|\bfailed\b|\bnot priced\b)[^\n]{0,60}")
# Nov 9: one Open-Meteo blip (its breaker skips forecasts for that run, by design) paged the owner. An outage the code
# already rides out counts only when it hit TRANSIENT_RUNS+ runs that day.
TRANSIENT = re.compile(r"Open-Meteo failed")
TRANSIENT_RUNS = 3


def _values(log: str, pattern: str) -> list[tuple[str, ...]]:
    return [m if isinstance(m, tuple) else (m,) for m in re.findall(pattern, log or "")]


def day_stats(rows: list[tuple[str, str, int | None, str]]) -> dict:
    """One day's runs rows (job, step, exit code, log tail) -> the counts the rules read."""
    out: dict = {"publishes": 0, "ratio": {}, "usual": {}, "swallowed": []}
    for _, step, code, log in rows:
        out["publishes"] += step == "publish"
        for what, s, pat, _ in RATIOS:
            if step == s:
                n, m = out["ratio"].get(what, (0, 0))
                for a, b in _values(log, pat):
                    n, m = n + int(a), m + int(b)
                out["ratio"][what] = (n, m)
        for what, s, pat, how in USUAL:
            if step != s:
                continue
            got = _values(log, pat)
            cur = out["usual"].get(what, 0)
            if how == "count":
                out["usual"][what] = cur + len(got)
            elif got:
                vals = [int(v[0]) for v in got]
                out["usual"][what] = cur + sum(vals) if how == "sum" else max(cur, *vals)
            else:
                out["usual"].setdefault(what, 0)
        if code == 0:
            out["swallowed"] += [(step, m.strip()) for m in SWALLOWED.findall(log or "")]
    return out


def check(days: dict[date, list[tuple[str, str, int | None, str]]], day: date) -> list[str]:
    """The findings for `day`, judged against the WEEK days before it. Each line starts with what's wrong (the alert's
    body), then the numbers in parentheses."""
    today = day_stats(days.get(day, []))
    lines = []
    for what, _, _, least in RATIOS:
        n, m = today["ratio"].get(what, (0, 0))
        if n == 0 and m >= least:
            lines.append(f"{what} (0 of {m} over the day)")
    if today["publishes"] >= NORMAL_PUBLISHES:
        week = [day_stats(days.get(day - timedelta(d), [])) for d in range(1, WEEK + 1)]
        for what, *_ in USUAL:
            above = sum(w["usual"].get(what, 0) > 0 for w in week)
            if today["usual"].get(what, 0) == 0 and above >= MOST:
                lines.append(f"{what} (0 today, above 0 on {above} of the last {WEEK} days; {today['publishes']} publishes)")
    seen = set()
    counts = Counter((step, re.sub(r"\d+", "#", msg)) for step, msg in today["swallowed"])
    for step, msg in today["swallowed"]:
        key = (step, re.sub(r"\d+", "#", msg))
        if TRANSIENT.search(msg) and counts[key] < TRANSIENT_RUNS:
            continue
        if key not in seen:
            seen.add(key)
            lines.append(f"swallowed error in {step} ({msg[:160].replace('(', '[').replace(')', ']')})")
    return lines


CATCH_UP = 3   # days back a missed watchdog run is made up (Nov 9: Nov 6's daily died at a hard step, so Nov 5 went unchecked)


def missed(days: dict[date, list[tuple[str, str, int | None, str]]], day: date) -> list[date]:
    """Days before `day` (up to CATCH_UP) whose watchdog never ran: it runs in the next day's daily."""
    return [d for d in (day - timedelta(k) for k in range(CATCH_UP, 0, -1))
            if not any(job == "daily" and step == "watchdog" for job, step, *_ in days.get(d + timedelta(1), []))]


STALE_HOURS = 36       # a bet still open this long after its last game's start: nothing will settle it on its own


def _ref_time(ref: str) -> datetime | None:
    """The start a ref carries itself ("nba|HOME|AWAY|<tip>", "<league>|home|away|<kickoff>"); None otherwise."""
    parts = str(ref or "").split("|")
    if len(parts) != 4:
        return None
    try:
        t = datetime.fromisoformat(parts[3].replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=ET)


def _when(v) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=ET)
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=ET)


def last_start(bet: dict, starts: dict) -> datetime | None:
    """A bet's last game's start: its pick's or ticket's, each game's own (`commence_time` / `start`), the time in its
    ref, or the app's games table (`starts`, by game id, NFL refs also as "nfl:<id>"); else when it was placed."""
    times = [_when(bet.get("pick_commence_time")), _when(bet.get("ticket_commence_time"))]
    for g in bet.get("games") or []:
        if not isinstance(g, dict):
            continue
        ref = g.get("game_ref") or g.get("gameRef")
        times += [_when(g.get("commence_time")), _when(g.get("start")), _ref_time(ref),
                  _when(starts.get(ref)), _when(starts.get(f"nfl:{ref}"))]
    times = [t for t in times if t]
    return max(times) if times else _when(bet.get("placed_at"))


def stale_open(bets: list[dict], starts: dict, now: datetime) -> list[str]:
    """Nov 9: Clippers lines, DNP props and Georgia + Miami sat open for days and nothing said so. One finding when any
    bet is still open STALE_HOURS after its last game's start: the count and up to 3 of them."""
    stale = []
    for b in bets:
        t = last_start(b, starts)
        if t is not None and now - t > timedelta(hours=STALE_HOURS):
            stale.append((t, b))
    if not stale:
        return []
    stale.sort(key=lambda x: x[0])
    shown = "; ".join(f"{str(b.get('label') or b.get('matchup') or b.get('bet_id'))[:60]} {t.astimezone(ET):%b %-d}"
                      for t, b in stale[:3])
    return [f"{len(stale)} bet(s) still open {STALE_HOURS}+ hours after their last game ({shown.replace('(', '[').replace(')', ']')})"]


def load_open_bets(conn) -> tuple[list[dict], dict]:
    """Every account's open bets (no result, no cash-out) and the app's game starts for their refs."""
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select bet_id, label, matchup, games, placed_at, pick_commence_time, ticket_commence_time from my_bets "
                    "where cashout is null and coalesce(pick_status, ticket_status, 'open') = 'open'")
        bets = cur.fetchall()
        refs = sorted({r for b in bets for g in (b.get("games") or []) if isinstance(g, dict)
                       for r in [g.get("game_ref") or g.get("gameRef")] if r})
        refs += [f"nfl:{r}" for r in refs]
        cur.execute("select game_id, commence_time from games where game_id = any(%s)", [refs])
        starts = {r["game_id"]: r["commence_time"] for r in cur.fetchall()}
    return bets, starts


QUIET_FAILED = 0, 3, None    # done, done with a warning (cli.WARN_EXIT: grade alerts on its own), still running


def overnight_failures(rows: list[tuple[str, str, int | None, str]]) -> list[str]:
    """The 3 AM job's failed steps (Nov 9): the worker alerts every other job's failure at once (worker.failed) but
    keeps the phone quiet at night, so the 9:55 daily reports this morning's. On Nov 9 sync-personal and grade
    failed with exit 1 overnight and nobody heard."""
    out = []
    for job, step, code, log in rows:
        if job == "overnight" and code not in QUIET_FAILED:
            last = next((ln.strip() for ln in reversed((log or "").splitlines()) if ln.strip()), "")
            out.append(f"overnight {step} failed (exit {code}; {last[:120].replace('(', '[').replace(')', ']')})")
    return list(dict.fromkeys(out))


def load(conn, day: date) -> dict[date, list[tuple[str, str, int | None, str]]]:
    """`runs` rows for `day` and the WEEK days before it, by Eastern date."""
    start = datetime.combine(day - timedelta(WEEK), datetime.min.time(), ET)
    end = datetime.combine(day + timedelta(1), datetime.min.time(), ET)
    cur = conn.execute("select started_at, job, step, exit_code, coalesce(log_tail, '') from runs "
                       "where started_at >= %s and started_at < %s", [start, end])
    days: dict = defaultdict(list)
    for at, job, step, code, log in cur.fetchall():
        days[at.astimezone(ET).date()].append((job, step, code, log))
    return days


def run(day: date | None = None, alert: bool = True, db_url: str | None = None) -> tuple[list[str], str]:
    """(findings for `day`, default yesterday ET; the alert's result line)."""
    import psycopg

    from betlab import alerts, config

    today = datetime.now(ET).date()
    day = day or (today - timedelta(1))
    db_url = db_url or config.secret("SUPABASE_DB_URL")
    if not db_url:
        return [], "watchdog: no app database (SUPABASE_DB_URL): skipped"
    with psycopg.connect(db_url, prepare_threshold=None, connect_timeout=15) as conn:
        days = load(conn, day)
        lines = [f"{d:%b %-d}: {line}" for d in missed(days, day) for line in check(load(conn, d), d)]
        lines += check(days, day)
        try:
            lines += stale_open(*load_open_bets(conn), datetime.now(ET))
        except Exception as exc:  # noqa: BLE001 - the runs findings still go out
            lines.append(f"open bets not checked ({type(exc).__name__}: {str(exc)[:120]})")
        start = datetime.combine(today, datetime.min.time(), ET)
        cur = conn.execute("select job, step, exit_code, coalesce(log_tail, '') from runs "
                           "where job = 'overnight' and started_at >= %s", [start])
        lines += overnight_failures(cur.fetchall())
    if not lines:
        return [], f"watchdog: {day}: nothing quietly at zero"
    return lines, alerts.problem("watchdog", lines) if alert else "watchdog: alert not sent (--no-alert)"
