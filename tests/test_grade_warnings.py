"""A grader that leaves lines ungraded is flagged (exit 3), alerted to the owner once a day, and never stops
the worker's job; and every ledger saves start times in one shape (Oct 14)."""
import pandas as pd
import pytest

from betlab import alerts, cli, timefmt, tracking_nhl_props, worker
from betlab.worker import Worker

from test_worker import fake


def test_start_times_get_one_shape():
    s = pd.Series(["2026-10-01T02:00Z", "2026-10-10T23:10:00Z", "2026-09-25T23:00:00+00:00",
                   "2026-10-13T20:00:00-04:00", None, "not a time"])
    out = timefmt.utc_text(s).tolist()
    assert out[:4] + out[5:] == ["2026-10-01T02:00:00Z", "2026-10-10T23:10:00Z", "2026-09-25T23:00:00Z",
                                 "2026-10-14T00:00:00Z", "not a time"]
    assert pd.isna(out[4])                     # a blank stays blank (an empty cell in the CSV)


def test_a_ledger_save_writes_the_one_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking_nhl_props, "PATH", tmp_path / "nhl_prop_lines.csv")
    df = pd.DataFrame({c: [None, None] for c in tracking_nhl_props.COLUMNS})
    df["commence_time"] = ["2026-10-01T02:00Z", "2026-10-10T23:10:00Z"]
    tracking_nhl_props.save(df)
    assert pd.read_csv(tmp_path / "nhl_prop_lines.csv", dtype=str)["commence_time"].tolist() == [
        "2026-10-01T02:00:00Z", "2026-10-10T23:10:00Z"]


def test_grade_exits_3_and_alerts_when_a_grader_left_lines(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(cli, "_grade_everything", lambda: print(
        "NHL prop lines graded: 10\nsoccer lines not graded (KeyError: 'Yes')\n"
        "NHL box scores unavailable for 1 game(s): 2026020098 ConnectionError: 429"))
    monkeypatch.setattr(alerts, "problem", lambda kind, lines: sent.append((kind, lines)) or "alerts: sent")
    with pytest.raises(SystemExit) as e:
        cli.cmd_grade(None)
    assert e.value.code == cli.WARN_EXIT == worker.WARN
    assert sent == [("grade", ["soccer lines not graded (KeyError: 'Yes')",
                               "NHL box scores unavailable for 1 game(s): 2026020098 ConnectionError: 429"])]
    assert "grade warnings: 2 line(s)" in capsys.readouterr().out


def test_a_clean_grade_exits_0_without_an_alert(monkeypatch):
    monkeypatch.setattr(cli, "_grade_everything", lambda: print("NHL prop lines graded: 10"))
    monkeypatch.setattr(alerts, "problem", lambda *a: pytest.fail("no alert on a clean grade"))
    cli.cmd_grade(None)


def test_the_overnight_grade_warns_without_an_alert(monkeypatch, capsys):
    """The 3 AM grade records the warning in runs; the 9:55 daily's grade sends the alert if it still stands."""
    import argparse

    monkeypatch.setattr(cli, "_grade_everything", lambda: print("soccer lines not graded (KeyError: 'Yes')"))
    monkeypatch.setattr(alerts, "problem", lambda *a: pytest.fail("no alert at 3 AM"))
    with pytest.raises(SystemExit) as e:
        cli.cmd_grade(argparse.Namespace(no_alert=True))
    assert e.value.code == cli.WARN_EXIT
    assert "left to the morning grade" in capsys.readouterr().out
    calls = []
    res = Worker(runner=fake({}, codes={"grade --no-alert": 3}, calls=calls)).run_job("overnight")
    assert res.ok and calls[-2:] == ["export-page", "publish"]


def test_a_grade_warning_never_stops_the_daily():
    calls = []
    res = Worker(runner=fake({}, codes={"grade": 3}, calls=calls)).run_job("daily")
    assert res.ok and "pull --auto" in calls and calls[-6:] == ["publish", "alert", "dfs --grade", "wind-watch", "watchdog", "rotation"]
    assert ("grade", 3) in res.steps


class ProblemConn:
    def __init__(self, subs):
        self.subs, self.sent = subs, set()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        rows = []
        if sql.startswith("select 1 from alerts_sent"):
            rows = [(1,)] if params[0] in self.sent else []
        elif sql.startswith("select endpoint"):
            rows = [s[1:] for s in self.subs if s[0] == params[0]]
        elif sql.startswith("insert into alerts_sent"):
            self.sent.add(params[0])
        return type("R", (), {"fetchall": lambda _s: rows, "fetchone": lambda _s: rows[0] if rows else None})()


def test_the_problem_alert_goes_to_the_owner_once_a_day(monkeypatch):
    import psycopg

    conn = ProblemConn([("owner", "https://push/mike", "k", "s"), ("other", "https://push/her", "k", "s")])
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: conn)
    got = []
    send = lambda sub, msg, key: got.append((sub["endpoint"], msg["title"], msg["body"])) or 201
    kw = dict(now=pd.Timestamp("2026-10-14T14:00Z"), send=send, db_url="postgres://x", private_key="k", owner="owner")
    lines = ["soccer lines not graded (KeyError: 'Yes')", "NHL box scores unavailable for 1 game(s): 2026020098 x"]
    assert alerts.problem("grade", lines, **kw) == "alerts: grade problem sent to 1 of 1 owner device(s)"
    assert got == [("https://push/mike", "BetLab: grade needs a look",
                    "NHL box scores unavailable for 1 game(s); soccer lines not graded")]
    assert alerts.problem("grade", lines, **kw) == "alerts: grade problem already sent today"
    assert len(got) == 1
