-- Live Activities (Mike's #3, Oct 27): a real bet live on the iPhone's lock screen and Dynamic Island, started, updated
-- and ended by the worker over APNs (src/betlab/live_activity.py). Apple hands the app two kinds of token, kept apart
-- from push_subscriptions (every alert goes to those rows; these take only Live Activity pushes):
--   kind 'start':  this iPhone's push-to-start token (one per device; the app replaces its old one)
--   kind 'update': one started activity's update token, for its bet
-- live_activity_state is the worker's own record of what it started and last sent (the service only).

create table if not exists live_activity_tokens (
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  token      text not null check (token ~ '^[0-9a-f]+$' and length(token) between 32 and 400),
  env        text not null check (env in ('sandbox', 'production')),
  kind       text not null check (kind in ('start', 'update')),
  bet_id     text,
  device     text,
  created_at timestamptz not null default now(),
  primary key (user_id, token),
  check ((kind = 'start') = (bet_id is null))
);

create table if not exists live_activity_state (
  bet_id     text primary key,
  user_id    uuid not null references auth.users (id) on delete cascade,
  started_at timestamptz not null default now(),
  sent_at    timestamptz not null default now(),
  ended_at   timestamptz,
  content    jsonb not null
);

alter table live_activity_tokens enable row level security;
alter table live_activity_state  enable row level security;   -- no policies: the service only

create policy own_rows on live_activity_tokens for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select, insert, update, delete on live_activity_tokens to authenticated;
revoke all on live_activity_state from anon, authenticated;
