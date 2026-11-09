import json
from datetime import datetime
from zoneinfo import ZoneInfo

from betlab import backup as B

ET = ZoneInfo("America/New_York")
ROWS = {"bets": [{"bet_id": "b1", "stake": 1.0, "label": "Café"}, {"bet_id": "b2", "stake": 2.0, "label": None}], "promos": []}


def test_a_copy_reads_back_whole_one_row_a_line(tmp_path):
    path = tmp_path / "backups" / "app_db.json"
    assert B.write(ROWS, "2026-11-04", path) == "backup: 2 rows in 2 tables"
    text = path.read_text(encoding="utf-8")
    assert json.loads(text) == {"day": "2026-11-04", "tables": ROWS}
    assert sum('"bet_id"' in line for line in text.splitlines()) == 2 and "Café" in text
    assert not path.with_suffix(".tmp").exists()


def test_a_copy_much_smaller_than_the_last_is_refused_and_the_last_kept(tmp_path):
    path = tmp_path / "app_db.json"
    B.write(ROWS, "2026-11-04", path)
    line = B.write({"bets": [], "promos": []}, "2026-11-05", path)
    assert "failed" in line and "kept the last copy" in line
    assert json.loads(path.read_text(encoding="utf-8"))["day"] == "2026-11-04"
    assert B.write({"bets": ROWS["bets"][:1], "promos": []}, "2026-11-05", path).startswith("backup: 1 rows")     # half is fine


def test_once_a_day_by_the_eastern_date(tmp_path):
    path = tmp_path / "app_db.json"
    B.write(ROWS, "2026-11-04", path)
    assert "already taken" in B.run(db_url="unused", now=datetime(2026, 11, 4, 23, 45, tzinfo=ET), path=path)


def test_tokens_never_go_in_the_repo():
    assert not {"push_subscriptions", "live_activity_tokens", "alerts_held", "job_requests"} & set(B.TABLES)
    assert "bets" in B.TABLES and "bet_history" in B.TABLES
