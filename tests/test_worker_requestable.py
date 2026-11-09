"""Every job the worker accepts from the app must pass job_requests' check constraint (Oct 9: test_alert was
refused silently because migration 0005 never listed it)."""
import pathlib
import re

from betlab import worker

MIGRATIONS = pathlib.Path(__file__).resolve().parents[1] / "supabase" / "migrations"


def test_requestable_jobs_are_allowed_by_the_database():
    allowed = None
    for f in sorted(MIGRATIONS.glob("*.sql")):        # the last migration to set the check wins
        m = re.search(r"job_requests_job_check\s+check\s*\(job in \(([^)]*)\)\)", f.read_text(encoding="utf-8"))
        if m:
            allowed = set(re.findall(r"'([a-z_]+)'", m.group(1)))
    assert allowed is not None
    assert set(worker.REQUESTABLE) <= allowed
    assert set(worker.REQUESTABLE) <= set(worker.JOBS)
