-- Reactions (Mike, Nov 6: "add reactions to cards on the friends tab"): a friend reacts to a bet in the Friends feed with
-- one of six, one per person per bet (another one replaces it; the same one again takes it back). The bet's owner sees who
-- reacted on their own card and gets a push (the worker's minute loop, reactions.py). The apps draw each key as its emoji.
-- Only a friend's shared bet takes a reaction, the same bets friend_bets shows them, and never your own.
create table if not exists bet_reactions (
  bet_id      uuid not null references bets (bet_id) on delete cascade,
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  reaction    text not null check (reaction in ('fire', 'money', 'sweat', 'skull', 'pray', 'goat')),
  created_at  timestamptz not null default now(),
  primary key (bet_id, user_id)
);

-- Is this a bet the signed-in user may react to? An accepted friend's bet while they share; not your own.
create or replace function can_react(bet uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from bets b where b.bet_id = bet and b.user_id <> auth.uid() and connected(b.user_id, true)
                   and coalesce((select s.share_bets from user_settings s where s.user_id = b.user_id), true))
$$;

alter table bet_reactions enable row level security;
-- your own reactions; everyone's on a bet you can see comes through bet_reactions_for
create policy own_rows on bet_reactions for select to authenticated using (user_id = (select auth.uid()));
create policy react on bet_reactions for insert to authenticated
  with check (user_id = (select auth.uid()) and can_react(bet_id));
create policy change on bet_reactions for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()) and can_react(bet_id));
create policy take_back on bet_reactions for delete to authenticated using (user_id = (select auth.uid()));
grant select, insert, update, delete on bet_reactions to authenticated;

-- The reactions on these bets that you can see: on your own bets, and on friends' bets you can react to. A reactor's
-- name shows when it's you or someone you're friends with (a friend's other friend is "Someone": no browsing).
create or replace function bet_reactions_for(bets uuid[])
returns table (bet_id uuid, user_id uuid, name text, reaction text, created_at timestamptz)
language sql stable security definer set search_path = public as $$
  select r.bet_id, r.user_id,
         case when r.user_id = auth.uid() or connected(r.user_id, true) then p.name end,
         r.reaction, r.created_at
  from bet_reactions r
  join bets b on b.bet_id = r.bet_id
  left join profiles p on p.user_id = r.user_id
  where r.bet_id = any(bets) and (b.user_id = auth.uid() or can_react(b.bet_id))
  order by r.created_at
$$;

-- a reaction changed: the bet's owner, the one who reacted, and the owner's friends (it shows on their feed)
create or replace function pulse_reaction() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  r bet_reactions := case when tg_op = 'DELETE' then old else new end;
  owner uuid := (select b.user_id from bets b where b.bet_id = r.bet_id);
begin
  perform pulse_user(r.user_id);
  if owner is not null then
    perform pulse_user(owner);
    perform pulse_user(case when f.requester = owner then f.addressee else f.requester end)
      from friendships f where f.status = 'accepted' and owner in (f.requester, f.addressee);
  end if;
  return null;
end $$;
create trigger pulse after insert or update or delete on bet_reactions for each row execute function pulse_reaction();

revoke execute on function can_react(uuid), bet_reactions_for(uuid[]), pulse_reaction() from public, anon;
revoke execute on function pulse_reaction() from authenticated;
grant execute on function can_react(uuid), bet_reactions_for(uuid[]) to authenticated;
