-- Let a 'novig_sync' job be queued (2026-10-22): Mike's Novig bets are entered and settled from his account
-- (novig_sync.py, read-only key), every pregame tick and at 3 AM; queueing it checks a new key at once.

alter table job_requests drop constraint job_requests_job_check;
alter table job_requests add constraint job_requests_job_check
  check (job in ('refresh_free', 'reprice', 'sync_personal', 'test_alert', 'grade', 'novig_sync'));
