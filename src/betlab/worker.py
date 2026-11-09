"""The Railway worker (docs/APP_PLAN.md, Phase 3): runs BetLab's scheduled jobs itself, replacing
GitHub's cron, the "BetLab tick" Claude routines and the page-sync routine.

    python -m betlab.worker            (BETLAB_SHADOW=1: log when each job would run, run nothing)

- The schedule (Mike, 2026-10-04; docs/DECISIONS.md "the new schedule"): game lines every morning
  (`daily`), and props and line updates only after each game's news (`pregame`, every 15 minutes:
  pregame.py pulls each game once inside its sport's window). The NFL morning props pull is data
  only (`--morning-data`). The midday reprices and the evening and NBA runs are gone; their jobs stay
  for the app's Refresh now (`reprice`) and for a rollback to the workflows.
- `evening`, `reprice` and `nba` still copy their workflows step for step (the parity tests check);
  `daily` follows daily.yml except for the props steps above. Each step runs as its own process, so
  one failure never stops the scheduler. A step reads what an earlier one reported (pulled=true).
- SCHEDULE is in Eastern time, so daylight saving needs no second fire.
- One lock: two jobs never touch data/ at once (the workflows' `concurrency: betlab-data`).
- Every step is recorded in the app database's `runs` table (replaces the Actions run list).
- The app can ask for a job (`job_requests`): an allow-list, a cooldown, never in shadow mode.
- Data lives in a clone of the repo on the Railway volume (BETLAB_REPO_DIR, cloned from main on the
  first start; gitsync.py). Each job starts by taking main's newest commits and ends by committing
  data/ and exports/ and pushing to main as betlab-bot, as the workflows did. No job runs without
  the ledger (data/ledger/picks.csv): an empty volume must never start a new, empty ledger.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from betlab import gitsync

ET = ZoneInfo("America/New_York")
QUIET_JOBS = {"overnight"}   # no phone alert at 3 AM: its failed steps reach the owner through the 9:55 watchdog
WARN = 3   # a step that finished with something to look at (cli.WARN_EXIT): recorded in runs, the job goes on
# The volume filled up on Oct 17 (500 MB): every tick failed for a day, and the files being written were cut off.
DISK_LOW = 300 * 2**20     # less free than this before a job: compact git, then clear the cache, and tell the owner
DISK_STOP = 50 * 2**20     # still less after that: run nothing, since a write that hits a full disk truncates its file


@dataclass(frozen=True)
class Step:
    args: tuple[str, ...]
    soft: bool = False                                  # a failure is logged and the job goes on
    when: Callable[[dict], bool] | None = None          # run only if earlier steps reported this
    script: bool = False                                # a scripts/*.py file, not a betlab command
    timeout: int | None = None                          # seconds; None = STEP_TIMEOUT

    @property
    def name(self) -> str:
        return " ".join(self.args)


def S(*args: str, soft: bool = False, when=None, script: bool = False, timeout: int | None = None) -> Step:
    return Step(tuple(args), soft, when, script, timeout)


pulled = lambda o: o.get("pulled") == "true"
pulled_or_built = lambda o: o.get("pulled") == "true" or o.get("built") == "true"
soon = lambda o: o.get("soon") == "true"
# a fun slice reaches its lock time (15 minutes before it starts): rebuild, publish and alert even with no pull
pulled_or_due = lambda o: o.get("pulled") == "true" or o.get("lock_due") == "true"

# The workflows, step for step, minus the old page's taps imports at the top of daily.yml (they end
# with the page; sync-personal brings the app's marks into the ledgers); publish fills the app's database after every export.
JOBS: dict[str, list[Step]] = {
    "daily": [
        S("sync-personal", soft=True),
        S("refresh", soft=True),                          # history updates: a source down must not cost the morning pull
        S("grade"),                                       # (Nov 6: one 502 here stopped the whole daily, no lines all day)
        S("pull", "--auto"),                              # every league's game lines: the morning look
        S("pull-props", "--morning-data", soft=True),     # NFL props for the lag study only (never picks)
        S("nhl", soft=True),
        S("ufc", soft=True),                              # UFC fight pages (free; Oct 23)
        S("card"),
        S("preview", soft=True),
        S("fun", soft=True),
        S("export-page"),
        S("publish", soft=True),
        S("alert", soft=True),
        S("dfs", "--grade", soft=True, timeout=180),      # free: what yesterday's lineups really scored
        S("wind-watch", soft=True, timeout=120),          # windy NFL games against the close; tracked, never bet (Nov 4)
        S("watchdog", soft=True, timeout=120),            # yesterday's quiet zeros and swallowed errors (Oct 30)
        S("rotation", soft=True, timeout=60),             # keys due for rotation: a to-do and one alert (Nov 2)
    ],
    "evening": [
        S("pull", "--prime-time"),
        S("pull-props", "--prime-time", soft=True, when=pulled),
        S("card", when=pulled),
        S("preview", soft=True, when=pulled),
        S("fun", soft=True, when=pulled),
        S("export-page", when=pulled),
        S("publish", soft=True, when=pulled),
        S("alert", soft=True, when=pulled),
    ],
    "reprice": [
        S("pull", "--auto", "--again", "3"),
        S("pull-props", "--league", "nhl", "--afternoon", soft=True),
        S("nhl", soft=True),
        S("card", when=pulled_or_built),
        S("preview", soft=True, when=pulled_or_built),
        S("export-page", when=pulled_or_built),
        S("publish", soft=True, when=pulled_or_built),
        S("alert", soft=True, when=pulled_or_built),
    ],
    "nba": [
        S("scripts/nba_window.py", "15", "75", script=True),
        S("pull-props", "--league", "nba", when=soon),
        S("card", when=pulled),
        S("export-page", when=pulled),
        S("publish", soft=True, when=pulled),
        S("alert", soft=True, when=pulled),
    ],
    "pregame": [                                         # each game once, after its sport's news
        S("pregame", soft=True),                         # a league that failed is logged; the rest still publish
        S("novig-sync", soft=True, timeout=120),         # Mike's new Novig bets and results (read-only; free)
        # free: does a fun slice lock now? (sgp_plus.lock_due). It takes ~2 s; on Oct 15 it hung after its output
        # until the 25-minute limit and the 12:30 tick was skipped, so a stall now costs this tick only
        S("lock-due", soft=True, timeout=120),
        S("nhl", soft=True, when=pulled),                # NHL view and props offers (free), before the card
        # soft: a failed card must not stop the locks, publish and alerts below (Oct 13: a tracker error failed every
        # card from 5:15 PM, so no slice locked and the app kept the 2:15 card); they go out with the last good card
        S("card", soft=True, when=pulled),
        S("preview", soft=True, when=pulled),
        S("fun", soft=True, when=pulled_or_due),
        # soft (Nov 9): a failed export must not stop health, ladders, held alerts, leg news, resets, challenges and the
        # pick'em below; publish sends the last good export
        S("export-page", soft=True, when=pulled_or_due),
        S("publish", soft=True, when=pulled_or_due),
        # every tick (Nov 9; free, deduped by alerts_sent): a lock whose tick died before its alert (a deploy, a hung
        # publish) is still announced before kickoff, though nothing is pulled after it
        S("alert", soft=True, timeout=180),              # new picks and newly locked tickets and slips
        S("health", soft=True, timeout=120),             # free: a missed lock, a push not deployed, the disk (health.py, Nov 4)
        S("backup", soft=True, timeout=120),             # the day's first tick: the app database into data/ (backup.py, Nov 4)
        S("calendar", soft=True, timeout=180),           # the day's first tick: ESPN's next 10 weeks (calendar_sync.py, Nov 4)
        # free, every tick: a ladder's step locks once its game's news is in (ladders.py, Oct 26), which can happen on a
        # tick that pulled nothing (another league's pull, or the chosen game's earlier one)
        S("ladders", soft=True, timeout=120),
        S("alert", "--held", soft=True, timeout=60),       # free: what an account's quiet hours held (Nov 2)
        S("leg-news", soft=True, timeout=120),            # free: a player on an open bet goes out (Nov 2)
        S("resets", soft=True, timeout=60),      # free: a lost bet's reset goes in the wallet as a bonus bet (Nov 1)
        # Novig challenges (Oct 28): today's best bet for each, alerted once ripe (challenges.py; free: the pulls on disk,
        # Novig's catalog and parlay pricer)
        S("challenges", soft=True, timeout=240),
        S("pickem", soft=True, timeout=120),       # the CFB pick'em entry priced at the frozen lines (Nov 7)
        # `dfs` is off: DraftKings answers 403 to Railway's servers (Nov 5). Run it by hand with `betlab dfs` from elsewhere; DECISIONS.
        # UFC fight pages (free, Oct 23) last: their first run downloads ESPN's results since 2021 (~2-3 min), which
        # must never hold up a lock; they publish with the next tick's export (or the next publish)
        S("ufc", soft=True, when=pulled),
    ],
    # 3 AM (Mike, Oct 21): last night's games graded while he sleeps, after the latest West Coast finishes (~1 AM).
    # refresh is soft so a college data failure doesn't stop the other leagues; the 9:55 daily grades again
    # (soccer's football-data files often land later) and sends any problem alert, so the phone stays quiet at night
    "overnight": [
        S("novig-sync", soft=True),                      # Mike's Novig bets, settled from his account (Oct 22)
        S("sync-personal", soft=True),
        S("refresh", soft=True),
        S("grade", "--no-alert"),
        S("export-page"),
        S("publish", soft=True),
    ],
    "sync_personal": [S("sync-personal")],
    "novig_sync": [S("novig-sync")],              # check a new Novig key at once (Oct 22; migration 0016)
    "challenges": [S("challenges", timeout=240)],  # a new Novig challenge solved at once (Oct 28; migration 0027)
    "pickem": [S("pickem", timeout=120)],          # a new pick'em entry matched and priced at once (Nov 7; migration 0044)
    # grade now instead of at the next daily (free: box scores and our own closes), then show it (Oct 14)
    "grade": [S("grade"), S("export-page"), S("publish", soft=True)],
    "test_alert": [S("alert", "--test")],          # a device just turned pick alerts on (Settings)
    "refresh_free": [S("refresh", soft=True), S("nhl", soft=True), S("ufc", soft=True), S("export-page"), S("publish", soft=True)],
}

# Steps only the worker runs (the workflows never had them): pick alerts need the worker's keys; UFC came after them.
WORKER_ONLY = {"alert", "alert --test", "alert --held", "ufc", "watchdog", "rotation", "leg-news", "health", "backup", "calendar", "wind-watch", "dfs", "dfs --grade"}

# Eastern time: (job, cron fields, first day). The pre-game check runs from 5:30 AM to 11:45 PM (late West Coast tips
# and puck drops); it costs nothing unless a game is in its window. 5:30 (Nov 9): in winter a 12:30 CET match kicks off
# at 6:30 AM ET (Nov 8, Lazio-Napoli) and needs its lineups-in pull 15-55 minutes out (5:45-6:15) and its lock at 6:15;
# the old first tick, 6:30, locked that slice at kickoff with no pull and no lock alert. A noon CET kickoff (6 AM ET)
# gets 5:30 and 5:45.
SCHEDULE: list[tuple[str, dict, str | None]] = [
    ("daily", {"hour": "9", "minute": "55"}, None),
    ("pregame", {"hour": "5", "minute": "30,45"}, None),
    ("pregame", {"hour": "6-23", "minute": "*/15"}, None),
    ("overnight", {"hour": "3", "minute": "0"}, None),   # 3, not 2: the 2 AM hour is skipped or repeated at clock changes
]

# Jobs the app may ask for, and how long after the same job they're refused (minutes).
REQUESTABLE = {"sync_personal": 1, "refresh_free": 10, "reprice": 30, "test_alert": 0, "grade": 30, "novig_sync": 1,
               "challenges": 0, "pickem": 0}


@dataclass
class Result:
    job: str
    steps: list[tuple[str, int | None]] = field(default_factory=list)   # (step, exit code; None = skipped)
    ok: bool = True


class Runs:
    """The `runs` table in the app database; prints only when there is no database."""

    def __init__(self, url: str | None):
        self.url = url

    def _exec(self, sql: str, params: list) -> int | None:
        if not self.url:
            return None
        import psycopg
        try:
            with psycopg.connect(self.url, prepare_threshold=None, connect_timeout=15) as c:
                row = c.execute(sql, params).fetchone()
                return row[0] if row else None
        except Exception as e:  # noqa: BLE001 - logging must never stop a job
            print(f"runs log failed: {type(e).__name__}", flush=True)
            return None

    def start(self, job: str, step: str) -> int | None:
        return self._exec("insert into runs (job, step) values (%s, %s) returning id", [job, step])

    def finish(self, rid: int | None, code: int | None, tail: str, credits: int | None = None) -> None:
        if rid is not None:
            self._exec("update runs set finished_at = now(), exit_code = %s, log_tail = %s, credits_used = %s "
                       "where id = %s returning id", [code, tail[-4000:], credits, rid])


def credits_spent(data_dir: Path | None = None) -> int:
    """Every Odds API credit the usage logs (data/odds_api_usage*.csv, one per key) have recorded.
    A step's difference before and after is what it spent: the runs log's credits_used."""
    import csv

    from betlab import config

    total = 0
    for f in sorted(Path(data_dir or config.DATA_DIR).glob("odds_api_usage*.csv")):
        with f.open(newline="", encoding="utf-8") as fh:
            total += sum(int(float(r["cost"] or 0)) for r in csv.DictReader(fh))
    return total


def _command(step: Step) -> list[str]:
    if step.script:
        return [sys.executable, *step.args]
    exe = shutil.which("betlab")
    return [exe, *step.args] if exe else [sys.executable, "-m", "betlab.cli", *step.args]


STEP_TIMEOUT = 1500   # seconds


def run_step(step: Step, outputs: dict, cwd: str | None = None, timeout: int | None = None) -> tuple[int, str]:
    """Run one step with its own GITHUB_OUTPUT file (the commands report through it, as in Actions). A step past
    its time limit is sent SIGABRT first: faulthandler then writes every thread's stack to the log (where it hung),
    and only then is it killed."""
    timeout = timeout or step.timeout or STEP_TIMEOUT
    with tempfile.TemporaryDirectory() as tmp:
        out_file = os.path.join(tmp, "out")
        open(out_file, "w").close()
        env = os.environ | {"GITHUB_OUTPUT": out_file, "PYTHONIOENCODING": "utf-8", "PYTHONFAULTHANDLER": "1"}
        with subprocess.Popen(_command(step), cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding="utf-8", errors="replace") as p:
            try:
                out, err = p.communicate(timeout=timeout)
                code, log = p.returncode, (out or "") + (err or "")
            except subprocess.TimeoutExpired:
                out, err = _stop(p)
                code, log = 124, f"timed out after {timeout}s\n{out or ''}{err or ''}"
        for line in open(out_file, encoding="utf-8").read().splitlines():
            k, sep, v = line.partition("=")
            if sep:
                outputs[k.strip()] = v.strip()
    return code, log


def _stop(p: subprocess.Popen) -> tuple[str, str]:
    """Abort a hung step so faulthandler dumps its stacks, then kill it if it still won't go."""
    try:
        # Windows has signal.SIGABRT but Popen.send_signal refuses it there (the worker runs on Linux)
        p.send_signal(signal.SIGABRT if os.name == "posix" else signal.SIGTERM)
        return p.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()
        return p.communicate()


class Worker:
    def __init__(self, runner=run_step, runs: Runs | None = None, shadow: bool = False, cwd: str | None = None,
                 repo: Path | None = None, ledger: Path | None = None, cache: Path | None = None,
                 free: Callable[[Path], int] | None = None, warn: Callable[[list[str]], str] | None = None,
                 problem: Callable[[str, list[str]], str] | None = None):
        self.runner, self.runs, self.shadow, self.cwd = runner, runs or Runs(None), shadow, cwd
        self.repo, self.ledger, self.cache = repo, ledger, cache
        self.free = free or (lambda p: shutil.disk_usage(p).free)
        self.warn = warn or _disk_alert
        self.problem = problem or _step_alert
        self.data_dir: Path | None = None               # where the usage logs live (config.DATA_DIR by default)
        self.lock = threading.Lock()
        self.last_run: dict[str, datetime] = {}

    def run_job(self, job: str, wait: float = 1800) -> Result | None:
        """Run a job's steps in order under the one lock. A failed hard step ends the job."""
        if not self.lock.acquire(timeout=wait):
            rid = self.runs.start(job, "skipped: another job held the lock")
            self.runs.finish(rid, None, "")
            return None
        try:
            self.last_run[job] = datetime.now(ET)
            res = Result(job)
            if self.shadow:
                rid = self.runs.start(job, "(shadow) would run")
                self.runs.finish(rid, 0, " -> ".join(s.name for s in JOBS[job]))
                print(f"{datetime.now(ET):%a %H:%M} ET shadow: would run {job}", flush=True)
                return res
            if self.ledger is not None and not self.ledger.exists():
                rid = self.runs.start(job, "refused: no ledger on the volume")
                self.runs.finish(rid, 1, f"{self.ledger} is missing: is the repo cloned? (BETLAB_REPO_DIR)")
                print(f"{job}: refused, {self.ledger} is missing", flush=True)
                res.ok = False
                return res
            if self.repo is not None and not self.check_disk(job):
                res.ok = False
                return res
            if self.repo is not None:
                self._git(job, "git pull", gitsync.update, res)
            outputs: dict = {}
            for step in JOBS[job]:
                if step.when and not step.when(outputs):
                    res.steps.append((step.name, None))
                    continue
                rid = self.runs.start(job, step.name)
                before = self._credits()
                code, log = self.runner(step, outputs, self.cwd)
                if code not in (0, WARN):
                    log = f"{log}\n{self.failed(job, step, code)}"
                after = self._credits()
                self.runs.finish(rid, code, log, None if before is None or after is None else after - before)
                res.steps.append((step.name, code))
                print(f"{datetime.now(ET):%a %H:%M} ET {job}: {step.name} -> {code}", flush=True)
                if code not in (0, WARN) and not step.soft:
                    res.ok = False
                    break
            if self.repo is not None:   # commit what ran, even after a failed step: it's on the volume either way
                self._git(job, "git push", lambda repo: gitsync.publish(repo, job), res)
            return res
        finally:
            self.lock.release()

    def check_disk(self, job: str) -> bool:
        """Before a job: with under DISK_LOW free, compact the clone, then (still low) delete the cache (gitignored,
        every file in it is fetched again for free), record a "disk" step and alert the owner once a day.
        False (run nothing) if even that leaves under DISK_STOP."""
        free = self.free(self.repo)
        if free >= DISK_LOW:
            return True
        rid = self.runs.start(job, "disk")
        notes = [f"{free / 2**20:.0f} MB free"]
        code, log = gitsync.compact(self.repo)
        notes.append(f"git gc -> {code}" + (f": {log.strip()[:200]}" if code else ""))
        if self.free(self.repo) < DISK_LOW and self.cache is not None and self.cache.exists():
            shutil.rmtree(self.cache, ignore_errors=True)
            notes.append(f"deleted {self.cache}")
            if code:                                    # gc had no room the first time
                notes.append(f"git gc again -> {gitsync.compact(self.repo)[0]}")
        free = self.free(self.repo)
        ok = free >= DISK_STOP
        notes.append(f"{free / 2**20:.0f} MB free after cleanup" + ("" if ok else ": job not run"))
        try:
            notes.append(self.warn([f"worker disk nearly full ({free / 2**20:.0f} MB free)"]))
        except Exception as e:  # noqa: BLE001 - an alert must never stop the check
            notes.append(f"alert failed: {type(e).__name__}")
        self.runs.finish(rid, WARN if ok else 1, "\n".join(notes))
        print(f"{datetime.now(ET):%a %H:%M} ET {job}: disk -> {' · '.join(notes)}", flush=True)
        return ok

    def failed(self, job: str, step: Step, code: int | None) -> str:
        """A step that failed, hard or soft, tells the owner (Nov 9: the Nov 6 daily refresh and the Nov 9 overnight
        grade failed with exit 1 and nobody heard): one problem alert per job and step a day (alerts.problem's key
        hashes the line before its parentheses, so another exit code the same day is the same alert). The 3 AM job
        stays quiet: the 9:55 watchdog reports its failures (watchdog.overnight_failures)."""
        if job in QUIET_JOBS:
            return "failure alert: left to the 9:55 watchdog"
        try:
            return self.problem(job, [f"{step.name} failed (exit {code})"])
        except Exception as e:  # noqa: BLE001 - an alert must never stop the job
            return f"failure alert failed: {type(e).__name__}"

    def _credits(self) -> int | None:
        try:
            return credits_spent(self.data_dir)
        except Exception:  # noqa: BLE001 - a credit count must never stop a job
            return None

    def _git(self, job: str, name: str, fn, res: Result) -> None:
        rid = self.runs.start(job, name)
        code, log = fn(self.repo)
        self.runs.finish(rid, code, log)
        res.steps.append((name, code))
        print(f"{datetime.now(ET):%a %H:%M} ET {job}: {name} -> {code}", flush=True)

    def handle_request(self, job: str) -> tuple[str, str]:
        """(status, note) for an app request: allowed, not in shadow mode, past its cooldown."""
        if job not in REQUESTABLE:
            return "refused", "not a job the app can start"
        if self.shadow:
            return "refused", "the worker is in shadow mode"
        last = self.last_run.get(job)
        if last and datetime.now(ET) - last < timedelta(minutes=REQUESTABLE[job]):
            return "refused", f"ran less than {REQUESTABLE[job]} minutes ago"
        res = self.run_job(job, wait=60)
        if res is None:
            return "refused", "another job is running; try again in a few minutes"
        return ("done" if res.ok else "failed"), " · ".join(f"{s}: {c}" for s, c in res.steps if c is not None)


def _disk_alert(lines: list[str]) -> str:
    from betlab import alerts
    return alerts.problem("disk", lines)


def _step_alert(job: str, lines: list[str]) -> str:
    from betlab import alerts
    return alerts.problem(f"the {job} run", lines)


def poll_requests(worker: Worker, url: str | None) -> None:
    """Take the oldest queued job request, run it (or refuse it) and record the outcome."""
    if not url:
        return
    import psycopg
    try:
        with psycopg.connect(url, prepare_threshold=None, connect_timeout=15, autocommit=True) as c:
            row = c.execute("""update job_requests set status = 'running'
                               where id = (select id from job_requests where status = 'queued' order by requested_at limit 1
                                           for update skip locked) returning id, job""").fetchone()
            if not row:
                return
            status, note = worker.handle_request(row[1])
            c.execute("update job_requests set status = %s, note = %s, finished_at = now() where id = %s", [status, note[:500], row[0]])
    except Exception as e:  # noqa: BLE001
        print(f"job request poll failed: {type(e).__name__}", flush=True)


_leg_error: dict = {"text": "", "at": 0.0}


def leg_alerts_tick(worker: Worker) -> None:
    """Leg push alerts (leg_alerts.py) and friends' reactions (reactions.py), every minute: a runs row only when a notification went out, and a failure at
    most once an hour (the same error every minute would bury the log)."""
    from betlab import leg_alerts, reactions
    try:
        line = leg_alerts.run()
        try:                                      # friends' reactions (0042) never stop the leg alerts
            more = reactions.run()
        except Exception as e:  # noqa: BLE001
            more = f"reaction alerts failed ({type(e).__name__}: {e})"[:300]
        line = "\n".join(x for x in (line, more) if x)
        if line:
            rid = worker.runs.start("live", "leg-alerts")
            worker.runs.finish(rid, 0, line)
    except Exception as e:  # noqa: BLE001 - a bad minute must not stop the loop
        text = f"{type(e).__name__}: {e}"[:500]
        if text != _leg_error["text"] or time.time() - _leg_error["at"] > 3600:
            _leg_error.update(text=text, at=time.time())
            rid = worker.runs.start("live", "leg-alerts")
            worker.runs.finish(rid, 1, text)
        print(f"leg alerts failed: {type(e).__name__}", flush=True)


def build_scheduler(worker: Worker):
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BlockingScheduler(timezone=ET)
    for i, (job, fields, start) in enumerate(SCHEDULE):
        sched.add_job(worker.run_job, CronTrigger(timezone=ET, start_date=start, **fields), args=[job],
                      id=f"{job}-{i}", max_instances=1, coalesce=True, misfire_grace_time=900)
    return sched


def upcoming(sched, n: int = 6, now: datetime | None = None) -> list[tuple[datetime, str]]:
    """The next n scheduled fires (before the scheduler starts, jobs have no next_run_time yet)."""
    now = now or datetime.now(ET)
    fires = [(j.trigger.get_next_fire_time(None, now), j.id) for j in sched.get_jobs() if j.id not in ("requests", "legs")]
    return sorted((t, i) for t, i in fires if t)[:n]


def main() -> None:
    from betlab import config

    if os.environ.get("WORKER_ENABLED", "1") == "0":
        print("WORKER_ENABLED=0: the worker is off (rollback switch); sleeping", flush=True)
        while True:
            time.sleep(3600)
    url = config.secret("SUPABASE_DB_URL")
    shadow = os.environ.get("BETLAB_SHADOW", "") == "1"
    repo = Path(os.environ["BETLAB_REPO_DIR"]) if os.environ.get("BETLAB_REPO_DIR") else None
    runs = Runs(url)
    if repo is not None and (not shadow or os.environ.get("GITHUB_TOKEN")):   # in shadow: proves the token and volume
        rid = runs.start("worker", "git clone")
        code, log = gitsync.ensure_clone(repo)
        runs.finish(rid, code, log)
        print(f"repo on the volume: {log or code}", flush=True)
    worker = Worker(runs=runs, shadow=shadow, cwd=str(config.ROOT), repo=None if shadow else repo,
                    ledger=None if shadow else config.DATA_DIR / "ledger" / "picks.csv", cache=config.CACHE_DIR)
    sched = build_scheduler(worker)
    sched.add_job(poll_requests, "interval", seconds=20, args=[worker, url], id="requests", max_instances=1, coalesce=True)
    if not shadow:
        sched.add_job(leg_alerts_tick, "interval", seconds=60, args=[worker], id="legs", max_instances=1, coalesce=True)
    print(f"BetLab worker {'in SHADOW mode (logs only) ' if shadow else ''}started; data in {config.DATA_DIR}", flush=True)
    for when, jid in upcoming(sched):
        print(f"  next: {jid} at {when:%a %b %d %I:%M %p %Z}", flush=True)
    rid = worker.runs.start("worker", "started (shadow)" if shadow else "started")
    # the code this build runs (Railway sets it): on Oct 20 a push of the NBA slip fix was skipped and the worker kept the
    # 10:27 AM build all evening, which only the deploy list showed
    worker.runs.finish(rid, 0, f"build {os.environ.get('RAILWAY_GIT_COMMIT_SHA', 'unknown')[:8]}")
    sched.start()


if __name__ == "__main__":
    main()
