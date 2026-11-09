"""The worker's copy of the repo on the Railway volume: clone it once, keep it current, and
commit what each job wrote (data/, exports/) back to main, as the Actions runs did.

The repo is private, so git authenticates with GITHUB_TOKEN (a fine-grained token Mike made:
contents read/write on mopsha/betlab only). The token goes into an HTTP header for each git
command and is never written to .git/config, the remote URL, a log or the runs table; git's
own messages are scrubbed of it too, just in case.

Without a token (local tests, a public mirror) git runs plain, so a local path works as the remote.
"""

from __future__ import annotations

import base64
import os
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REMOTE = "https://github.com/mopsha/betlab.git"
BOT = ["-c", "user.name=betlab-bot", "-c", "user.email=betlab-bot@users.noreply.github.com"]
PATHS = ["data", "exports"]
ET = ZoneInfo("America/New_York")


def _auth() -> list[str]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return []
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic}"]


def _scrub(text: str) -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        text = text.replace(token, "***")
        text = text.replace(base64.b64encode(f"x-access-token:{token}".encode()).decode(), "***")
    return text


def git(repo: Path | None, *args: str, timeout: int = 300) -> tuple[int, str]:
    cmd = ["git", *_auth(), *BOT, *(["-C", str(repo)] if repo else []), *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, _scrub((p.stdout or "") + (p.stderr or ""))
    except subprocess.TimeoutExpired:
        return 124, f"git {args[0]} timed out"


def ensure_clone(repo: Path, remote: str = REMOTE, branch: str = "main") -> tuple[int, str]:
    """Clone the repo onto the volume the first time (it seeds data/ from main); afterwards a no-op."""
    if (repo / ".git").exists():
        return 0, "already cloned"
    repo.parent.mkdir(parents=True, exist_ok=True)
    return git(None, "clone", "-q", "--branch", branch, remote, str(repo), timeout=900)


def compact(repo: Path) -> tuple[int, str]:
    """Free space in the clone (worker.check_disk): drop the temp files a write that hit a full disk leaves in
    .git/objects, then pack loose objects and prune unreachable ones. Only under the worker's job lock."""
    for tmp in (repo / ".git" / "objects").glob("**/tmp_*"):
        tmp.unlink(missing_ok=True)
    git(repo, "reflog", "expire", "--expire=now", "--all")
    return git(repo, "gc", "--prune=now", "--quiet", timeout=900)


def update(repo: Path, branch: str = "main") -> tuple[int, str]:
    """Before a job: save anything a crashed job left behind, then take main's newest commits."""
    _abort_stale_rebase(repo)
    code, log = commit(repo, "leftovers from an interrupted job")
    if code:
        return code, log
    return pull(repo, branch)


def _abort_stale_rebase(repo: Path) -> None:
    if (repo / ".git" / "rebase-merge").exists() or (repo / ".git" / "rebase-apply").exists():
        git(repo, "rebase", "--abort")


def pull(repo: Path, branch: str = "main") -> tuple[int, str]:
    """Take main's newest commits under ours. Since the cutover the worker is the only writer of data/
    and exports/, so a conflict there means another run wrote the same files at the same time (Oct 6:
    GitHub's late fallback daily and a worker job both rewrote ncaaf_games.parquet): the worker's
    newer version wins (-X theirs: in a rebase, "theirs" is the commit being replayed). Rows the
    other run added in other places are kept. A failed pull never leaves a rebase half done."""
    code, log = git(repo, "pull", "--rebase", "--autostash", "-X", "theirs", "-q", "origin", branch)
    if code:
        _abort_stale_rebase(repo)
    return code, log


def commit(repo: Path, message: str) -> tuple[int, str]:
    paths = [p for p in PATHS if (repo / p).exists()]
    if not paths:
        return 0, "nothing to commit"
    code, log = git(repo, "add", "-A", "--", *paths)
    if code:
        return code, log
    if git(repo, "diff", "--cached", "--quiet")[0] == 0:
        return 0, "nothing to commit"
    return git(repo, "commit", "-q", "-m", message)


def publish(repo: Path, job: str, branch: str = "main", tries: int = 3) -> tuple[int, str]:
    """After a job: commit data/ and exports/ ("daily run 2026-10-05_0957") and push, rebasing on
    whatever reached main meanwhile (a code push). A failed push keeps the commit for next time."""
    code, log = commit(repo, f"{job.replace('_', ' ')} {datetime.now(ET):%Y-%m-%d_%H%M}")
    if code:
        return code, log
    for _ in range(tries):
        code, log = pull(repo, branch)
        if code:
            continue                            # pull() left the commit as it was: retry
        code, log = git(repo, "push", "-q", "origin", f"HEAD:{branch}")
        if code == 0:
            return 0, "pushed"
    return code, log
