-- Let the app queue a test alert (2026-10-09). Turning on pick alerts saves the device and inserts a
-- 'test_alert' job_requests row (web/lib/push-actions.ts), and the worker runs it (worker.REQUESTABLE),
-- but 0005 never added the job to this check, so the insert was refused and no test alert went out.

alter table job_requests drop constraint job_requests_job_check;
alter table job_requests add constraint job_requests_job_check
  check (job in ('refresh_free', 'reprice', 'sync_personal', 'test_alert'));
