"""The worker's repo on the volume (gitsync.py) against a local bare repo: clone, commit, push, rebase."""

import subprocess
from pathlib import Path

import pytest

from betlab import gitsync
from betlab.worker import JOBS, Worker


def _sh(cwd, *args):
    subprocess.run(["git", *gitsync.BOT, *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def origin(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    bare = tmp_path / "origin.git"
    _sh(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    _sh(tmp_path, "clone", "-q", str(bare), str(seed))
    (seed / "data" / "ledger").mkdir(parents=True)
    (seed / "data" / "ledger" / "picks.csv").write_text("pick_id\n")
    (seed / "src.py").write_text("code\n")
    _sh(seed, "add", "-A")
    _sh(seed, "commit", "-q", "-m", "seed")
    _sh(seed, "push", "-q", "origin", "HEAD:main")
    return bare, seed


def _log(repo):
    return subprocess.run(["git", "-C", str(repo), "log", "--format=%s", "main"], capture_output=True, text=True).stdout


def test_clone_commit_and_push_rebasing_on_a_code_push(origin, tmp_path):
    bare, seed = origin
    repo = tmp_path / "volume" / "repo"
    assert gitsync.ensure_clone(repo, remote=str(bare))[0] == 0
    assert (repo / "data" / "ledger" / "picks.csv").exists()
    assert gitsync.ensure_clone(repo, remote=str(bare)) == (0, "already cloned")
    # meanwhile a code change reaches main
    (seed / "src.py").write_text("code v2\n")
    _sh(seed, "commit", "-q", "-am", "code push")
    _sh(seed, "push", "-q", "origin", "HEAD:main")
    (repo / "data" / "ledger" / "picks.csv").write_text("pick_id\np1\n")
    (repo / "scratch.txt").write_text("not data")           # only data/ and exports/ are committed
    code, log = gitsync.publish(repo, "daily")
    assert (code, log) == (0, "pushed")
    msgs = _log(bare)
    assert msgs.splitlines()[0].startswith("daily ") and "code push" in msgs
    assert gitsync.publish(repo, "daily") == (0, "pushed") and _log(bare) == msgs   # nothing new: no empty commit


def test_update_saves_leftovers_then_pulls(origin, tmp_path):
    bare, seed = origin
    repo = tmp_path / "repo"
    gitsync.ensure_clone(repo, remote=str(bare))
    (repo / "exports").mkdir()
    (repo / "exports" / "card.json").write_text("{}")
    assert gitsync.update(repo)[0] == 0
    assert "leftovers from an interrupted job" in _log(repo)


def test_the_token_never_shows_in_git_output(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret123")
    assert "ghp_secret123" not in gitsync._scrub("fatal: https://x:ghp_secret123@github.com")
    assert any("extraheader" in a for a in gitsync._auth())


def test_worker_refuses_without_a_ledger_and_commits_after_a_job(origin, tmp_path, monkeypatch):
    bare, _ = origin
    repo = tmp_path / "repo"
    gitsync.ensure_clone(repo, remote=str(bare))
    ran = []

    def runner(step, outputs, cwd):
        ran.append(step.name)
        (repo / "data" / "ledger" / "picks.csv").write_text(f"pick_id\n{len(ran)}\n")
        return 0, ""

    empty = Worker(runner=runner, repo=repo, ledger=tmp_path / "nowhere" / "picks.csv")
    res = empty.run_job("sync_personal")
    assert not res.ok and ran == []
    w = Worker(runner=runner, repo=repo, ledger=repo / "data" / "ledger" / "picks.csv")
    res = w.run_job("sync_personal")
    assert res.ok and [s for s, _ in res.steps] == ["git pull", *[s.name for s in JOBS["sync_personal"]], "git push"]
    assert _log(bare).splitlines()[0].startswith("sync personal ")


def test_same_file_written_on_both_sides_keeps_the_workers_version(origin, tmp_path):
    """Oct 6: GitHub's fallback daily and a worker job both rewrote a binary history file; every
    later pull conflicted and update() left the rebase half done."""
    bare, seed = origin
    repo = tmp_path / "repo"
    gitsync.ensure_clone(repo, remote=str(bare))
    hist = Path("data") / "history"
    (seed / hist).mkdir(parents=True)
    (seed / hist / "games.parquet").write_bytes(b"\x00github\x01")
    (seed / "data" / "ledger" / "picks.csv").write_text("pick_id\ngh1\n")
    _sh(seed, "add", "-A")
    _sh(seed, "commit", "-q", "-m", "daily run (GitHub)")
    _sh(seed, "push", "-q", "origin", "HEAD:main")
    (repo / hist).mkdir(parents=True)
    (repo / hist / "games.parquet").write_bytes(b"\x00worker\x02")
    assert gitsync.commit(repo, "refresh free")[0] == 0
    assert gitsync.update(repo)[0] == 0
    assert not (repo / ".git" / "rebase-merge").exists()
    assert (repo / hist / "games.parquet").read_bytes() == b"\x00worker\x02"
    assert "gh1" in (repo / "data" / "ledger" / "picks.csv").read_text()   # the other run's rows stay
    assert gitsync.publish(repo, "reprice") == (0, "pushed")


def test_update_clears_a_rebase_left_half_done(origin, tmp_path):
    bare, seed = origin
    repo = tmp_path / "repo"
    gitsync.ensure_clone(repo, remote=str(bare))
    (seed / "data" / "ledger" / "picks.csv").write_text("pick_id\ngh\n")
    _sh(seed, "commit", "-q", "-am", "github")
    _sh(seed, "push", "-q", "origin", "HEAD:main")
    (repo / "data" / "ledger" / "picks.csv").write_text("pick_id\nworker\n")
    gitsync.commit(repo, "worker")
    gitsync.git(repo, "pull", "--rebase", "-q", "origin", "main")     # the old code's plain pull: stuck
    assert (repo / ".git" / "rebase-merge").exists()
    assert gitsync.update(repo)[0] == 0
    assert not (repo / ".git" / "rebase-merge").exists()
    assert "worker" in (repo / "data" / "ledger" / "picks.csv").read_text()


def test_a_full_disk_compacts_clears_the_cache_and_alerts_before_the_job(origin, tmp_path):
    """Oct 17: the worker's 500 MB volume filled up and every tick failed for a day, cutting off fun.json."""
    bare, _ = origin
    repo = tmp_path / "repo"
    gitsync.ensure_clone(repo, remote=str(bare))
    cache = repo / "data" / "cache"
    (cache / "nhl").mkdir(parents=True)
    (cache / "nhl" / "games_2026.parquet").write_bytes(b"x")
    (repo / ".git" / "objects" / "pack" / "tmp_pack_abc").write_bytes(b"half")
    free = iter([10 * 2**20, 100 * 2**20, 200 * 2**20])     # before, after gc, after the cache
    sent, ran = [], []
    w = Worker(runner=lambda step, o, cwd: (ran.append(step.name), (0, ""))[1], repo=repo,
               ledger=repo / "data" / "ledger" / "picks.csv", cache=cache,
               free=lambda p: next(free), warn=lambda lines: sent.append(lines) or "sent")
    res = w.run_job("sync_personal")
    assert res.ok and ran                                   # 200 MB left: the job runs
    assert not cache.exists() and not (repo / ".git" / "objects" / "pack" / "tmp_pack_abc").exists()
    assert sent and "disk nearly full" in sent[0][0]


def test_a_disk_still_full_after_cleanup_runs_nothing(origin, tmp_path):
    bare, _ = origin
    repo = tmp_path / "repo"
    gitsync.ensure_clone(repo, remote=str(bare))
    ran = []
    w = Worker(runner=lambda step, o, cwd: (ran.append(step.name), (0, ""))[1], repo=repo,
               ledger=repo / "data" / "ledger" / "picks.csv", free=lambda p: 5 * 2**20, warn=lambda lines: "sent")
    res = w.run_job("sync_personal")
    assert not res.ok and ran == [] and res.steps == []


def test_plenty_of_disk_skips_the_check(origin, tmp_path):
    bare, _ = origin
    repo = tmp_path / "repo"
    gitsync.ensure_clone(repo, remote=str(bare))
    w = Worker(runner=lambda step, o, cwd: (0, ""), repo=repo, ledger=repo / "data" / "ledger" / "picks.csv",
               free=lambda p: 4 * 2**30, warn=lambda lines: (_ for _ in ()).throw(AssertionError("no alert")))
    assert w.run_job("sync_personal").ok
