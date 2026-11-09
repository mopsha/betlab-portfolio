-- FanDuel's College Football Pick'em (2026-11-07): the week's 10 spread picks at FanDuel's frozen Wednesday lines,
-- one row per game, per account (src/betlab/pickem.py). Read from screenshots by the web's /api/pickem; the worker
-- matches each pair to the week's game, prices the frozen line against the sharp market on every pre-game tick,
-- grades it from ESPN when final, and alerts Saturday morning before the noon lock.
--   week        the lock day (Saturday, ET)
--   n           the question's place on the screen (1-10)
--   away, home  FanDuel's short names as read ("Iowa", "Notre Dame"); the worker swaps them when FanDuel listed home first
--   away_name, home_name  the Odds API's full names once matched; away_logo, home_logo from ESPN's board
--   home_line   the home team's frozen spread (-5.5: home favored); the away side is its negative
--   pick        your side; ours: BetLab's side (null under New York rules, or unpriced); p_home its home cover chance
--   fair_line   the sharp market's home spread when priced; event_id, start: the matched game
--   home_pts, away_pts, result ('home' / 'away' / 'push'): the final, once graded
create table if not exists pickem (
  pick_id    uuid primary key default gen_random_uuid(),
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  week       date not null,
  n          smallint not null default 0,
  away       text not null,
  home       text not null,
  away_name  text,
  home_name  text,
  away_logo  text,
  home_logo  text,
  home_line  numeric not null,
  pick       text check (pick in ('home', 'away')),
  ours       text check (ours in ('home', 'away')),
  p_home     numeric,
  fair_line  numeric,
  priced_at  timestamptz,
  event_id   text,
  start      timestamptz,
  home_pts   integer,
  away_pts   integer,
  result     text check (result in ('home', 'away', 'push')),
  notice     text,
  created_at timestamptz not null default now(),
  unique (user_id, week, away, home)
);
alter table pickem enable row level security;
create policy own_rows on pickem for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
grant select, insert, update, delete on pickem to authenticated;

-- The week's outcome, entered by hand after FanDuel grades it Sunday: the partners' best score and what it paid.
create table if not exists pickem_weeks (
  user_id      uuid not null default auth.uid() references auth.users (id) on delete cascade,
  week         date not null,
  partner_best smallint,
  reward       text,
  primary key (user_id, week)
);
alter table pickem_weeks enable row level security;
create policy own_rows on pickem_weeks for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
grant select, insert, update, delete on pickem_weeks to authenticated;

-- Let a 'pickem' job be queued: a new entry is matched and priced within a minute (worker.REQUESTABLE).
alter table job_requests drop constraint job_requests_job_check;
alter table job_requests add constraint job_requests_job_check
  check (job in ('refresh_free', 'reprice', 'sync_personal', 'test_alert', 'grade', 'novig_sync', 'challenges', 'pickem'));
