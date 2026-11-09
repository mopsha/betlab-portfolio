-- Friends (Mike, Oct 27: "a social feed where you see your friends' entered bets and their profile"; W16's tail button
-- copies one). Friend requests, accepted by the one invited; friends see each other's bets, never money (the app counts
-- units only, and no dollar figure is stored on a bet); anyone can stop sharing in Settings (share_bets, on by default).
-- Nobody can browse the accounts: a person is found only by their exact @handle or exact email (find_person).

create table if not exists profiles (
  user_id     uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  name        text not null check (char_length(btrim(name)) between 1 and 40),
  handle      text not null unique check (handle ~ '^[a-z0-9_]{3,20}$'),
  created_at  timestamptz not null default now()
);

create table if not exists friendships (
  requester    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  addressee    uuid not null references auth.users (id) on delete cascade,
  status       text not null default 'pending' check (status in ('pending', 'accepted')),
  created_at   timestamptz not null default now(),
  accepted_at  timestamptz,
  primary key (requester, addressee),
  check (requester <> addressee)
);
-- one friendship per pair, whoever asked first
create unique index if not exists friendships_pair on friendships (least(requester, addressee), greatest(requester, addressee));

alter table user_settings add column if not exists share_bets boolean not null default true;

-- Is `other` connected to the signed-in user (a friend, or a request either way)? `accepted` only: friends.
create or replace function connected(other uuid, accepted boolean default false) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from friendships f
                 where ((f.requester = auth.uid() and f.addressee = other) or (f.addressee = auth.uid() and f.requester = other))
                   and (not accepted or f.status = 'accepted'))
$$;

alter table profiles enable row level security;
create policy own_or_connected on profiles for select to authenticated
  using (user_id = (select auth.uid()) or connected(user_id));
create policy own_row on profiles for insert to authenticated with check (user_id = (select auth.uid()));
create policy own_row_update on profiles for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
grant select, insert, update on profiles to authenticated;

alter table friendships enable row level security;
-- both sides see it; only the one asking writes it, as pending; either side ends it (decline, cancel, unfriend).
-- Accepting is accept_friend's alone: there is no update grant, so a request can't accept itself.
create policy either_side on friendships for select to authenticated
  using (requester = (select auth.uid()) or addressee = (select auth.uid()));
create policy ask on friendships for insert to authenticated
  with check (requester = (select auth.uid()) and status = 'pending' and accepted_at is null);
create policy end_it on friendships for delete to authenticated
  using (requester = (select auth.uid()) or addressee = (select auth.uid()));
grant select, insert, delete on friendships to authenticated;

-- A person by their exact @handle or exact email (case aside), never yourself; nothing partial, so no browsing.
create or replace function find_person(q text) returns table (user_id uuid, name text, handle text)
language sql stable security definer set search_path = public as $$
  select p.user_id, p.name, p.handle from profiles p
  left join auth.users u on u.id = p.user_id
  where p.user_id <> auth.uid() and char_length(btrim(q)) >= 3
    and (p.handle = lower(btrim(ltrim(btrim(q), '@'))) or lower(u.email) = lower(btrim(q)))
  limit 1
$$;

-- The one invited accepts a pending request.
create or replace function accept_friend(from_user uuid) returns boolean
language sql volatile security definer set search_path = public as $$
  update friendships set status = 'accepted', accepted_at = now()
  where requester = from_user and addressee = auth.uid() and status = 'pending'
  returning true
$$;

-- Friends' bets, as My bets shows them (the same view, so results, units and grading match), for accepted friends who
-- share; one friend's with `friend`. The view carries no dollars: stakes are units.
create or replace function friend_bets(friend uuid default null) returns setof my_bets
language sql stable security definer set search_path = public as $$
  select b.* from my_bets b
  where b.user_id <> auth.uid() and connected(b.user_id, true)
    and (friend is null or b.user_id = friend)
    and coalesce((select s.share_bets from user_settings s where s.user_id = b.user_id), true)
$$;

revoke execute on function connected(uuid, boolean), find_person(text), accept_friend(uuid), friend_bets(uuid) from public, anon;
grant execute on function connected(uuid, boolean), find_person(text), accept_friend(uuid), friend_bets(uuid) to authenticated;
