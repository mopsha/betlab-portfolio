-- Pick alerts (Mike, 2026-10-04: "I need notifications of when a pick is found").
--
-- 1. push_subscriptions: one row per device that tapped "Turn on pick alerts" (Web Push from the
--    home-screen app). Personal: each user sees and removes only their own devices.
-- 2. alerts_sent: which picks were already announced, so a pick is pushed once, ever. Written only
--    by the worker (`betlab alert`); signed-in users can't read or write it.

create table push_subscriptions (
  user_id      uuid not null default auth.uid() references auth.users (id) on delete cascade,
  endpoint     text not null check (endpoint like 'https://%'),
  p256dh       text not null,
  auth         text not null,
  device       text,
  created_at   timestamptz not null default now(),
  last_sent_at timestamptz,
  primary key (user_id, endpoint)
);

create table alerts_sent (
  pick_id    text primary key,
  sent_at    timestamptz not null default now(),
  recipients int not null default 0
);

alter table push_subscriptions enable row level security;
alter table alerts_sent        enable row level security;   -- no policies: the service only

create policy own_rows on push_subscriptions for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

grant select, insert, update, delete on push_subscriptions to authenticated;
revoke all on alerts_sent from anon, authenticated;
