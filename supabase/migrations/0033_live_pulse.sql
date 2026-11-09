-- Live updates (Nov 4; ideas #30, #77): open apps hear that something changed and read it at once, instead of waiting for
-- the next 5-minute reload. `app_pulse` holds no data, only "this changed at": the row 'card' (every publish: the card,
-- tickets, grades, live CLV) and one 'u:<user>' per account (their bets, promos, ladders, challenges, a friend's bets,
-- friend requests). The apps subscribe through Supabase Realtime, which applies the policy below to each change.
create table if not exists app_pulse (
  key text primary key,
  user_id uuid references auth.users on delete cascade,      -- null: everyone's (the card)
  at timestamptz not null default now()
);
alter table app_pulse enable row level security;
create policy shared_or_mine on app_pulse for select to authenticated using (user_id is null or user_id = auth.uid());
grant select on app_pulse to authenticated;
insert into app_pulse (key) values ('card') on conflict do nothing;

-- a pulse is only a nudge: if it ever fails, the bet it's for still saves
create or replace function pulse_user(who uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  insert into app_pulse (key, user_id, at) values ('u:' || who, who, now())
  on conflict (key) do update set at = excluded.at;
exception when others then
  raise warning 'pulse_user: %', sqlerrm;
end $$;

-- a row with a user_id changed: its owner's apps
create or replace function pulse_owner() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  perform pulse_user(case when tg_op = 'DELETE' then old.user_id else new.user_id end);
  return null;
end $$;

-- a bet changed: its owner's apps and their accepted friends' feeds
create or replace function pulse_bet() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  who uuid := case when tg_op = 'DELETE' then old.user_id else new.user_id end;
begin
  perform pulse_user(who);
  perform pulse_user(case when f.requester = who then f.addressee else f.requester end)
    from friendships f where f.status = 'accepted' and who in (f.requester, f.addressee);
  return null;
end $$;

create or replace function pulse_friendship() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'DELETE' then
    perform pulse_user(old.requester); perform pulse_user(old.addressee);
  else
    perform pulse_user(new.requester); perform pulse_user(new.addressee);
  end if;
  return null;
end $$;

revoke execute on function pulse_user(uuid), pulse_owner(), pulse_bet(), pulse_friendship() from public, anon, authenticated;

create trigger pulse after insert or update or delete on bets for each row execute function pulse_bet();
create trigger pulse after insert or update or delete on promos for each row execute function pulse_owner();
create trigger pulse after insert or update or delete on ladders for each row execute function pulse_owner();
create trigger pulse after insert or update or delete on challenges for each row execute function pulse_owner();
create trigger pulse after insert or update or delete on friendships for each row execute function pulse_friendship();

do $$ begin                                                  -- Supabase has this publication; the tests' Postgres doesn't
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table app_pulse;
  end if;
end $$;
