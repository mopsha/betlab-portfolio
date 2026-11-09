"""Three checks each pregame tick (free, ideas #72, #73, #79): did a slice lock, is the worker on the pushed code, will the disk last?

- **Missed lock** (`missed_locks`): a slice with a ticket reached its kickoff unlocked, or locked after it. On Oct 25 El
  Clasico's slice locked at the first tick after kickoff with no lock alert; on Nov 1 the early soccer slice locked 15
  seconds late. Replayed on 508 versions of the fun cards from Oct 20: those two, and a batch of day-old slices from one
  commit on Oct 22 that `RECENT` now leaves out.
- **Deploy check** (`undeployed`): a push under `src/` that the running build doesn't have, `GRACE` minutes after the
  push. Railway has skipped or lost such a push (Oct 20, Oct 28, Oct 30) and paused every build (Oct 21), and only the deploy
  list showed it. Only `src/`: pushes elsewhere are skipped by design.

- **Disk growth** (`disk_watch`): one reading a day of the worker's volume (`data/disk_usage.csv`); when the last two weeks'
  growth would fill it within `DISK_DAYS`, say so. The volume filled up on Oct 17-18 and every tick failed for a day;
  `worker.check_disk` only acts at under 300 MB free, which at that point is too late to grow it calmly.

Each goes to the owner's phone through `alerts.problem`, once a day for the same findings. `betlab health --no-alert`
prints them only.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path

import pandas as pd

GRACE = pd.Timedelta(minutes=15)      # a good deploy took 3-5 minutes on Nov 4, and the check runs every 15
RECENT = pd.Timedelta(hours=12)       # an older slice is history, not news
DISK_DAYS = 30                        # warn this long before the volume would fill: Mike grows it in the dashboard
DISK_WINDOW, DISK_MIN_DAYS = 14, 7    # growth over the last two weeks, once there's a week to read


def missed_locks(slates: list[dict], now: pd.Timestamp) -> list[str]:
    """One line per slice with a ticket that's past its kickoff without a lock before it."""
    from betlab import sgp_plus

    lines = []
    for s in slates:
        if not sgp_plus._sliced(s, sgp_plus.LOCK_SPORTS) or not any(s.get(k) for k in sgp_plus.TICKETS):
            continue
        kickoff = pd.Timestamp(s["kickoff"])
        if not kickoff <= now <= kickoff + RECENT:
            continue
        locked = pd.Timestamp(s["locked_at"]) if s.get("locked_at") else None
        if locked is None:
            lines.append(f"slice {s['slate']} never locked (kickoff {kickoff:%H:%M} UTC)")
        elif locked > kickoff:
            lines.append(f"slice {s['slate']} locked late ({(locked - kickoff).total_seconds() / 60:.0f} min after kickoff)")
    return lines


def undeployed(repo: Path, build: str, now: pd.Timestamp, branch: str = "origin/main") -> list[str]:
    """One line when `branch` has a push under src/ the running build lacks, GRACE after its newest such push."""
    from betlab import gitsync

    code, log = gitsync.git(repo, "log", "--format=%h %ct", f"{build}..{branch}", "--", "src/")
    if code:                # a build this clone doesn't know: nothing can be said from here
        print(f"deploy check: build {build[:8]} not compared ({log.strip()[:120]})")
        return []
    rows = [ln.split() for ln in log.splitlines() if ln.strip()]
    if not rows or now - pd.Timestamp(int(rows[0][1]), unit="s", tz="UTC") < GRACE:
        return []
    minutes = (now - pd.Timestamp(int(rows[0][1]), unit="s", tz="UTC")).total_seconds() / 60
    return [f"push {rows[0][0]} isn't on the worker ({minutes:.0f} min after the push; running {build[:8]})"]


def disk_forecast(rows: list[dict], free: float) -> float | None:
    """Days until the volume fills at the growth of the last DISK_WINDOW readings; None with too few, or none growing."""
    recent = rows[-DISK_WINDOW:]
    if len(recent) < DISK_MIN_DAYS:
        return None
    days = (pd.Timestamp(recent[-1]["day"]) - pd.Timestamp(recent[0]["day"])).days
    grown = float(recent[-1]["used_mb"]) - float(recent[0]["used_mb"])
    return free / (grown / days) if days and grown > 0 else None


def disk_watch(path: Path, usage, day: str) -> tuple[str | None, list[str]]:
    """Today's reading, once a day: (a line for the log, findings). `usage` is shutil.disk_usage's result."""
    rows = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    if rows and rows[-1]["day"] == day:
        return None, []
    used, free = usage.used / 2**20, usage.free / 2**20
    rows.append({"day": day, "used_mb": f"{used:.0f}", "free_mb": f"{free:.0f}"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["day", "used_mb", "free_mb"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    left = disk_forecast(rows, free)
    note = f"disk {used:.0f} MB used, {free:.0f} MB free" + (f", about {left:.0f} days left" if left is not None else "")
    return note, [f"worker volume fills in about {left:.0f} days ({free:.0f} MB free)"] if left is not None and left < DISK_DAYS else []


def _slates() -> list[dict]:
    from betlab import config

    out = []
    for name in ("fun.json", "fun_nba.json"):
        path = config.EXPORTS_DIR / name
        try:
            out += json.loads(path.read_text(encoding="utf-8")).get("slates", []) if path.exists() else []
        except ValueError as exc:   # the next `fun` rewrites it (cli.cmd_lock_due)
            print(f"{name} unreadable, skipped ({exc})")
    return out


def run(alert: bool = True, now: pd.Timestamp | None = None) -> list[str]:
    """Prints what it found and alerts the owner; returns the lines printed."""
    from betlab import alerts

    now = now or pd.Timestamp.now(tz="UTC")
    locks = missed_locks(_slates(), now)
    build, repo = os.environ.get("RAILWAY_GIT_COMMIT_SHA", ""), os.environ.get("BETLAB_REPO_DIR", "")
    deploy = undeployed(Path(repo), build, now) if build and repo else []
    from betlab import config

    note, disk = disk_watch(config.DATA_DIR / "disk_usage.csv", shutil.disk_usage(config.DATA_DIR), f"{now.tz_convert('America/New_York'):%Y-%m-%d}")
    out = [f"health: {ln}" for ln in locks + deploy + disk + ([note] if note else [])]
    if alert:
        out += [alerts.problem(kind, lines) for kind, lines in (("lock", locks), ("deploy", deploy), ("disk", disk)) if lines]
    out = out if locks or deploy or disk else out + ["health: locks and deploy fine" if build and repo else "health: locks fine (no build to compare)"]
    for ln in out:
        print(ln)
    return out
