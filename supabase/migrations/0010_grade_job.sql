-- Let a 'grade' job be queued (2026-10-14): grading ran only inside the 9:55 daily, so lines a grader missed
-- (Oct 13-14: NHL prop lines and soccer 3-way lines) waited a whole day after the fix. The worker runs it
-- (worker.REQUESTABLE: grade, export-page, publish; free).

alter table job_requests drop constraint job_requests_job_check;
alter table job_requests add constraint job_requests_job_check
  check (job in ('refresh_free', 'reprice', 'sync_personal', 'test_alert', 'grade'));
