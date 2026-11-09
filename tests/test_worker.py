"""The Railway worker (src/betlab/worker.py): the same jobs as the workflows, on Eastern time, one at a time."""

import re
import threading
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from betlab import worker
from betlab.worker import ET, JOBS, Worker


@pytest.fixture(autouse=True)
def no_failure_alerts(monkeypatch):
    """A failed step alerts the owner (worker.failed): never a real alert from a test."""
    sent = []
    monkeypatch.setattr(worker, "_step_alert", lambda job, lines: sent.append((job, lines)) or "alerts: (test)")
    return sent

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def workflow_commands(name: str) -> list[str]:
    """The betlab commands a workflow runs, in order (the page-taps imports end with the page)."""
    text = (WF / f"{name}.yml").read_text(encoding="utf-8")
    cmds = []
    for line in text.splitlines():
        line = line.split("#")[0]
        for m in re.finditer(r"(?:^|run:|\s)(betlab\s+[a-z-]+(?:\s+--?[\w-]+(?:\s+(?!\|\|)[\w./]+)?)*)", line):
            cmd = re.sub(r"\s+", " ", m.group(1)).strip().removeprefix("betlab ")
            if not cmd.startswith(("import-taken", "import-fun", "import-page-taps")):
                cmds.append(cmd)
        if "scripts/nba_window.py" in line:
            cmds.append("scripts/nba_window.py 15 75")
    return cmds


def job_commands(job: str) -> list[str]:
    return [s.name for s in JOBS[job] if s.name not in worker.WORKER_ONLY]


# The new schedule (Oct 4) changed only the daily run's props steps: no props pull that feeds
# picks in the morning (data only for the lag study), and no NHL props until each game's window.
DAILY_DROPPED = ["pull-props --once-daily", "pull-props --prime-time", "pull-props --league nhl --once-daily"]


def test_jobs_match_the_workflows_step_for_step():
    for job in ("evening", "reprice", "nba"):
        assert job_commands(job) == workflow_commands(job), job
    daily = [c for c in workflow_commands("daily") if c not in DAILY_DROPPED]
    daily.insert(daily.index("pull --auto") + 1, "pull-props --morning-data")
    assert job_commands("daily") == daily


def test_soft_steps_match_the_workflows():
    """A workflow step with `|| echo` may fail; the same step is soft in the worker."""
    for job in ("daily", "evening", "reprice"):
        text = (WF / f"{job}.yml").read_text(encoding="utf-8")
        soft = {re.sub(r"\s+", " ", m.group(1)).strip() for m in re.finditer(r"betlab ([^|\n]+?)\s*\|\|\s*echo", text)}
        soft = {s for s in soft if not s.startswith("import-")}     # the page-taps import (only while the page lives)
        if job == "daily":
            soft = (soft - set(DAILY_DROPPED)) | {"pull-props --morning-data"}
        assert {s.name for s in JOBS[job] if s.soft and s.name not in worker.WORKER_ONLY} == soft, job


def next_fire(job_id: str, after: datetime) -> datetime:
    sched = worker.build_scheduler(Worker(runner=None))
    job = next(j for j in sched.get_jobs() if j.id == job_id)
    return job.trigger.get_next_fire_time(None, after)


def test_daily_stays_at_955_eastern_across_the_clock_change():
    """Clocks fall back at 2 AM on Sunday Nov 1, 2026: the run stays at 9:55 local, an hour later in UTC."""
    t = next_fire("daily-0", datetime(2026, 10, 30, 12, 0, tzinfo=ET))      # Sat Oct 31: daylight time
    assert (t.day, t.hour, t.minute, t.utcoffset().total_seconds() / 3600) == (31, 9, 55, -4)
    t = next_fire("daily-0", datetime(2026, 10, 31, 12, 0, tzinfo=ET))      # Sun Nov 1: standard time
    assert (t.day, t.hour, t.minute, t.utcoffset().total_seconds() / 3600) == (1, 9, 55, -5)


def test_the_schedule_is_the_morning_run_plus_pregame_checks():
    """Mike's rule (Oct 4): no midday reprices or fixed evening runs; every 15 minutes a free pre-game check."""
    assert {job for job, _, _ in worker.SCHEDULE} == {"daily", "pregame", "overnight"}
    sched = worker.build_scheduler(Worker(runner=None))
    fires = []
    for job in sched.get_jobs():
        if job.id.startswith("pregame"):
            nxt = job.trigger.get_next_fire_time(None, datetime(2026, 10, 10, 0, 0, tzinfo=ET))   # a Saturday
            while nxt and nxt.day == 10:
                fires.append(nxt)
                nxt = job.trigger.get_next_fire_time(nxt, nxt + timedelta(seconds=1))
    fires.sort()
    assert (fires[0].hour, fires[0].minute) == (5, 30) and (fires[-1].hour, fires[-1].minute) == (23, 45)
    assert len(fires) == 2 + 18 * 4                                         # 5:30, 5:45, then 6:00-23:45


def test_pregame_reprices_only_after_a_pull():
    calls = []
    Worker(runner=fake({}, calls=calls)).run_job("pregame")
    assert calls == ["pregame", "novig-sync", "lock-due", "alert", "health", "backup", "calendar", "ladders", "alert --held", "leg-news", "resets", "challenges", "pickem"]   # alert, ladders, resets and challenges every tick (free)
    calls = []
    Worker(runner=fake({"pregame": {"pulled": "true"}}, calls=calls)).run_job("pregame")
    assert calls == ["pregame", "novig-sync", "lock-due", "nhl", "card", "preview", "fun", "export-page", "publish", "alert", "health", "backup", "calendar", "ladders", "alert --held", "leg-news", "resets", "challenges", "pickem", "ufc"]


def test_pregame_locks_a_fun_slice_without_a_pull():
    """Oct 10: a slice locks 15 minutes before it starts; with no odds pulled that tick, the fun build,
    publish and alert still run so the locked ticket and its notification arrive on time."""
    calls = []
    Worker(runner=fake({"lock-due": {"lock_due": "true"}}, calls=calls)).run_job("pregame")
    assert calls == ["pregame", "novig-sync", "lock-due", "fun", "export-page", "publish", "alert", "health", "backup", "calendar", "ladders", "alert --held", "leg-news", "resets", "challenges", "pickem"]


def fake(outputs_by_step: dict, codes: dict | None = None, calls: list | None = None):
    def run(step, outputs, cwd=None):
        if calls is not None:
            calls.append(step.name)
        outputs.update(outputs_by_step.get(step.name, {}))
        return (codes or {}).get(step.name, 0), ""
    return run


def test_evening_only_reprices_when_a_kickoff_is_near():
    calls = []
    Worker(runner=fake({}, calls=calls)).run_job("evening")
    assert calls == ["pull --prime-time"]
    calls = []
    Worker(runner=fake({"pull --prime-time": {"pulled": "true"}}, calls=calls)).run_job("evening")
    assert calls == [s.name for s in JOBS["evening"]]       # alert included


def test_reprice_runs_on_new_odds_or_a_fresh_nhl_view():
    calls = []
    Worker(runner=fake({"nhl": {"built": "true"}}, calls=calls)).run_job("reprice")
    assert "card" in calls and "export-page" in calls


def test_a_hard_failure_ends_the_job_and_a_soft_one_does_not():
    calls = []
    res = Worker(runner=fake({}, codes={"preview": 1}, calls=calls)).run_job("daily")
    assert res.ok and calls[-6:] == ["publish", "alert", "dfs --grade", "wind-watch", "watchdog", "rotation"]   # preview is soft
    calls = []
    res = Worker(runner=fake({}, codes={"grade": 2}, calls=calls)).run_job("daily")
    assert not res.ok and calls[-1] == "grade"                     # grade is not


def test_one_job_at_a_time():
    started = threading.Event()

    def slow(step, outputs, cwd=None):
        started.set()
        time.sleep(0.3)
        return 0, ""
    w = Worker(runner=slow)
    t = threading.Thread(target=w.run_job, args=["sync_personal"])
    t.start()
    started.wait(2)
    assert w.run_job("sync_personal", wait=0.05) is None          # refused while the first runs
    t.join()


def test_shadow_mode_runs_nothing():
    calls = []
    Worker(runner=fake({}, calls=calls), shadow=True).run_job("daily")
    assert calls == []


def test_app_requests_allow_list_cooldown_and_shadow():
    w = Worker(runner=fake({}))
    assert w.handle_request("daily")[0] == "refused"              # not requestable
    assert w.handle_request("sync_personal")[0] == "done"
    assert w.handle_request("reprice")[0] == "done"
    status, note = w.handle_request("reprice")
    assert status == "refused" and "minutes ago" in note           # cooldown
    assert Worker(runner=fake({}), shadow=True).handle_request("sync_personal")[0] == "refused"


def test_step_outputs_come_from_the_github_output_file(tmp_path):
    script = tmp_path / "say.py"
    script.write_text("import os\nopen(os.environ['GITHUB_OUTPUT'], 'a').write('soon=true\\n')\nprint('hi')\n")
    out = {}
    code, log = worker.run_step(worker.S(str(script), script=True), out)
    assert code == 0 and out == {"soon": "true"} and "hi" in log


def test_a_hung_step_stops_at_its_own_limit_and_logs_where_it_hung(tmp_path):
    script = tmp_path / "hang.py"
    script.write_text("import time\nprint('no slice to lock', flush=True)\ntime.sleep(60)\n")
    t0 = time.monotonic()
    code, log = worker.run_step(worker.S(str(script), script=True, timeout=2), {})
    assert code == 124 and time.monotonic() - t0 < 20
    assert "timed out after 2s" in log and "no slice to lock" in log
    if os.name == "posix":                                  # SIGABRT for faulthandler: Linux (the worker), not Windows
        assert "hang.py" in log and "line 3" in log        # faulthandler's stack: the sleep on line 3


def test_lock_due_has_a_short_limit():
    step = next(s for s in worker.JOBS["pregame"] if s.args == ("lock-due",))
    assert step.timeout and step.timeout <= 300


def test_startup_lists_the_next_runs():
    sched = worker.build_scheduler(Worker(runner=None))
    nxt = worker.upcoming(sched, n=4, now=datetime(2026, 10, 1, 12, 0, tzinfo=ET))
    assert [(t.hour, t.minute, j.split("-")[0]) for t, j in nxt] == [
        (12, 0, "pregame"), (3, 0, "overnight"), (5, 30, "pregame"), (9, 55, "daily")]   # each entry once, its next fire


def test_overnight_grades_at_3_am_without_waking_the_phone():
    """Mike (Oct 21): grade overnight. 3 AM Eastern on both sides of the Nov 1 clock change; the problem alert
    is left to the 9:55 daily, which grades again."""
    for after, offset in ((datetime(2026, 10, 30, 12, 0, tzinfo=ET), -4), (datetime(2026, 11, 1, 12, 0, tzinfo=ET), -5)):
        t = next_fire("overnight-3", after)
        assert (t.hour, t.minute, t.utcoffset().total_seconds() / 3600) == (3, 0, offset)
    steps = [s.name for s in JOBS["overnight"]]
    assert steps.index("refresh") < steps.index("grade --no-alert") < steps.index("export-page") < steps.index("publish")
    assert "grade" in [s.name for s in JOBS["daily"]]


def test_each_step_records_the_credits_it_spent(tmp_path):
    log = tmp_path / "odds_api_usage_paid.csv"
    log.write_text("ts,endpoint,sport,markets,cost,remaining,used\n2026-10-08T13:00:00+00:00,/sports,,,0,500,0\n")
    finished = []

    class Rec:
        def start(self, job, step):
            return step

        def finish(self, rid, code, tail, credits=None):
            finished.append((rid, credits))

    def run(step, outputs, cwd=None):
        if step.name == "pull --auto":
            with log.open("a") as f:
                f.write("2026-10-08T14:00:00+00:00,/sports/x/odds,x,h2h,30,470,30\n")
        return 0, ""
    w = Worker(runner=run, runs=Rec())
    w.data_dir = tmp_path
    w.run_job("daily")
    spent = dict(finished)
    assert spent["pull --auto"] == 30 and spent["card"] == 0


def test_a_1230_cet_kickoff_gets_its_pull_and_lock_before_6_30_eastern():
    """Nov 8 (Lazio-Napoli, 11:30Z = 6:30 AM ET in winter): soccer's pull window is 15-55 minutes out and a slice locks
    at the first tick within 25 minutes of kickoff. The first tick was 6:30, so it had neither."""
    sched = worker.build_scheduler(Worker(runner=None))
    day = datetime(2026, 11, 8, 0, 0, tzinfo=ET)
    fires = set()
    for job in sched.get_jobs():
        if job.id.startswith("pregame"):
            nxt = job.trigger.get_next_fire_time(None, day)
            while nxt and nxt.hour < 7:
                fires.add((nxt.hour, nxt.minute))
                nxt = job.trigger.get_next_fire_time(nxt, nxt + timedelta(seconds=1))
    kickoff = 6 * 60 + 30
    pulls = [h * 60 + m for h, m in fires if 15 <= kickoff - (h * 60 + m) <= 55]
    locks = [h * 60 + m for h, m in fires if 0 < kickoff - (h * 60 + m) <= 25]
    assert pulls and locks and min(locks) >= max(pulls) - 30
    assert (5, 30) in fires and (6, 0) in fires and (6, 15) in fires


def test_a_failed_step_alerts_the_owner_once_and_the_3_am_job_stays_quiet(no_failure_alerts):
    """Nov 9: the daily refresh (Nov 6) and the overnight grade (Nov 9) failed with exit 1 and nobody heard."""
    res = Worker(runner=fake({}, codes={"refresh": 1, "preview": 124, "grade": WARN_CODE})).run_job("daily")
    assert res.ok
    assert no_failure_alerts == [("daily", ["refresh failed (exit 1)"]), ("daily", ["preview failed (exit 124)"])]
    no_failure_alerts.clear()
    Worker(runner=fake({}, codes={"grade --no-alert": 1})).run_job("overnight")
    assert no_failure_alerts == []                    # left to the 9:55 watchdog (watchdog.overnight_failures)


def test_a_failure_alert_that_raises_never_stops_the_job():
    def boom(job, lines):
        raise RuntimeError("no database")
    calls = []
    res = Worker(runner=fake({}, codes={"refresh": 1}, calls=calls), problem=boom).run_job("daily")
    assert res.ok and calls[-1] == "rotation"


def test_a_failed_export_does_not_stop_the_free_pregame_steps():
    """export-page was the one hard step in pregame: when it failed, health, ladders, held alerts, leg news, resets,
    challenges and the pick'em stopped on every tick."""
    calls = []
    res = Worker(runner=fake({"pregame": {"pulled": "true"}}, codes={"export-page": 1}, calls=calls)).run_job("pregame")
    assert res.ok and calls[calls.index("export-page"):][:3] == ["export-page", "publish", "alert"]
    assert {"health", "ladders", "alert --held", "leg-news", "resets", "challenges", "pickem"} <= set(calls)


def test_the_alert_runs_on_every_pregame_tick():
    """A lock whose tick died before its alert (Nov 4: a deploy killed publish) is still announced on the next tick,
    though nothing is pulled: alerts.run is deduped by alerts_sent, so running it every tick is safe."""
    step = next(s for s in JOBS["pregame"] if s.args == ("alert",))
    assert step.when is None and step.soft and step.timeout


WARN_CODE = worker.WARN
