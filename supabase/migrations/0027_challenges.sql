-- Novig challenges (Mike, Oct 28: "i can submit it in the morning and it alerts me when a pick is ripe"). Novig's
-- Points > Challenges ("The Daily Drop": three a day, 50 points each, 100 more for all three) aren't in Novig's API, so
-- each morning a screenshot goes in through More > Novig challenges: the web's /api/challenges reads it (Claude) and
-- writes one row per challenge; the worker's `challenges` step (src/betlab/challenges.py, every pre-game tick) finds
-- the best Novig bet for each and, once it's ripe (its game's news is in and the price clears the bar), saves it on the
-- row and alerts the owner. Claude never places bets: he does, then taps "I placed it".
--   day      the Eastern date the challenge is for (it expires at midnight)
--   text     the challenge as Novig writes it: "Place a parlay on Pro BB (M) (Min. 3 legs, 4.00x, $5)"
--   rules    parsed: {kind: straight|parlay, sport, market, min_legs, min_dec, min_stake}
--   status   open (waiting), ready (a pick is saved and alerted), done (placed), skipped
--   pick     the bet: {label, legs[], price, dec, p, ev, link, matchup, commence_time, stake}
--   best     the best bet so far while it isn't ripe yet (shown as "watching"); refreshed every tick
--   notice   why it waits ("no Novig market for this yet")
create table if not exists challenges (
  challenge_id  uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid() references auth.users (id) on delete cascade,
  day           date not null,
  text          text not null,
  rules         jsonb not null default '{}'::jsonb,
  points        integer,
  status        text not null default 'open' check (status in ('open', 'ready', 'done', 'skipped')),
  pick          jsonb,
  best          jsonb,
  picked_at     timestamptz,
  notice        text,
  created_at    timestamptz not null default now(),
  unique (user_id, day, text)
);
alter table challenges enable row level security;
create policy own_rows on challenges for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
grant select, insert, update, delete on challenges to authenticated;

-- a new challenge is solved at once: the app queues 'challenges' (worker.REQUESTABLE) instead of waiting for the next tick
alter table job_requests drop constraint job_requests_job_check;
alter table job_requests add constraint job_requests_job_check
  check (job in ('refresh_free', 'reprice', 'sync_personal', 'test_alert', 'grade', 'novig_sync', 'challenges'));
