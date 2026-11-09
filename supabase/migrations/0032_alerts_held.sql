-- Alert settings (Nov 2, Mike's #47): an alert found during an account's quiet hours waits here until they end.
-- The worker writes and reads it (alerts.py); an alert whose game has started by then is dropped (expires_at).
-- user_settings.notify gains: picks, leans, locks, news (bools), min_ev (percent), sports ({"nfl": false}: off),
-- quiet ({"from": "23:00", "to": "08:00"}, Eastern). All optional: alert_prefs.py has the defaults.
create table alerts_held (
  id         bigint generated always as identity primary key,
  user_id    uuid not null references auth.users (id) on delete cascade,
  msg        jsonb not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);
alter table alerts_held enable row level security;   -- no policies: the service only
revoke all on alerts_held from anon, authenticated;
