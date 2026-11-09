from types import SimpleNamespace

import pandas as pd

from betlab import gitsync, health as H

NOW = pd.Timestamp("2026-11-04T20:00:00Z")


def slate(name="2026-11-04-soccer-three", kickoff="2026-11-04T19:45:00Z", locked=None, plus=True):
    return {"slate": name, "kickoff": kickoff, "locked_at": locked, "plus": {"sgp_id": "x"} if plus else None}


def test_a_slice_locked_in_time_or_not_started_is_fine():
    assert H.missed_locks([slate(locked="2026-11-04T19:30:00Z")], NOW) == []
    assert H.missed_locks([slate(kickoff="2026-11-04T20:30:00Z")], NOW) == []


def test_a_slice_past_kickoff_unlocked_or_late_is_found():
    assert "never locked" in H.missed_locks([slate()], NOW)[0]
    assert "locked late (2 min" in H.missed_locks([slate(locked="2026-11-04T19:47:00Z")], NOW)[0]


def test_nothing_to_lock_or_old_news_stays_quiet():
    assert H.missed_locks([slate(plus=False)], NOW) == []                 # no ticket in this slice
    assert H.missed_locks([slate(kickoff="2026-11-03T19:45:00Z")], NOW) == []
    assert H.missed_locks([slate(name="2026-11-04-unsliced")], NOW) == []


def _repo(tmp_path):
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    gitsync.git(None, "init", "-q", "-b", "main", str(repo))

    def commit(path, msg):
        (repo / path).write_text(msg)
        gitsync.git(repo, "add", "-A")
        gitsync.git(repo, "commit", "-q", "-m", msg)
        return gitsync.git(repo, "rev-parse", "HEAD")[1].strip()

    return repo, commit


def test_a_push_the_build_lacks_alarms_after_the_grace(tmp_path):
    repo, commit = _repo(tmp_path)
    build = commit("src/a.py", "one")
    assert H.undeployed(repo, build, pd.Timestamp.now(tz="UTC"), "main") == []
    commit("src/a.py", "two")
    now = pd.Timestamp.now(tz="UTC")
    assert H.undeployed(repo, build, now, "main") == []                                  # still inside the grace
    late = H.undeployed(repo, build, now + pd.Timedelta(minutes=20), "main")
    assert len(late) == 1 and "isn't on the worker" in late[0] and build[:8] in late[0]


def test_only_src_counts_and_an_unknown_build_says_nothing(tmp_path, capsys):
    repo, commit = _repo(tmp_path)
    build = commit("src/a.py", "one")
    commit("data.csv", "the bot's commit")
    later = pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=2)
    assert H.undeployed(repo, build, later, "main") == []
    assert H.undeployed(repo, "0" * 40, later, "main") == [] and "not compared" in capsys.readouterr().out


U = lambda used, free: SimpleNamespace(used=used * 2**20, free=free * 2**20)      # noqa: E731


def _readings(path, days, used=1000, grow=10):
    for d in range(days):
        H.disk_watch(path, U(used + grow * d, 4000 - grow * d), f"2026-11-{d + 1:02d}")


def test_disk_reads_once_a_day_and_says_nothing_with_too_few(tmp_path):
    path = tmp_path / "disk_usage.csv"
    assert H.disk_watch(path, U(1000, 4000), "2026-11-01") == ("disk 1000 MB used, 4000 MB free", [])
    assert H.disk_watch(path, U(1500, 3500), "2026-11-01") == (None, [])
    assert path.read_text().count("\n") == 2


def test_disk_forecast_warns_only_when_the_volume_fills_soon(tmp_path):
    slow, fast, flat = tmp_path / "s.csv", tmp_path / "f.csv", tmp_path / "t.csv"
    _readings(slow, 8)
    assert H.disk_watch(slow, U(1080, 3920), "2026-11-09")[1] == []                # 10 MB a day: over a year left
    _readings(fast, 8, grow=200)
    note, lines = H.disk_watch(fast, U(2600, 2400), "2026-11-09")
    assert "about 12 days left" in note and "fills in about 12 days" in lines[0]
    _readings(flat, 8, grow=0)
    assert H.disk_watch(flat, U(1000, 4000), "2026-11-09") == ("disk 1000 MB used, 4000 MB free", [])


def test_run_alerts_each_kind_once(monkeypatch, capsys):
    from betlab import alerts

    sent = []
    monkeypatch.setattr(alerts, "problem", lambda kind, lines: sent.append(kind) or f"alerts: {kind}")
    monkeypatch.setattr(H, "_slates", lambda: [slate()])
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setattr(H, "disk_watch", lambda *a: (None, []))
    H.run(now=NOW)
    assert sent == ["lock"] and "never locked" in capsys.readouterr().out
    monkeypatch.setattr(H, "_slates", lambda: [])
    assert H.run(now=NOW) == ["health: locks fine (no build to compare)"] and sent == ["lock"]
