-- Signed-in devices (Nov 4, idea #82): your own sessions, and ending one. auth.sessions isn't reachable through the API, so two
-- functions stand in, as the owner, each limited to the caller's rows. Ending a session stops its next refresh, so that device
-- is out within the hour at the latest, when its access token runs out: a token already issued can't be recalled.
create or replace function my_sessions() returns table (
  id uuid, created_at timestamptz, last_active timestamptz, user_agent text, ip text, current boolean
)
language sql stable security definer set search_path = '' as $$
  select s.id, s.created_at, coalesce(s.refreshed_at::timestamptz, s.updated_at, s.created_at), s.user_agent, host(s.ip),
         s.id::text = (auth.jwt() ->> 'session_id')
  from auth.sessions s
  where s.user_id = auth.uid() and (s.not_after is null or s.not_after > now())
  order by 3 desc
$$;

-- one session, or (null) every session but this one; never this one by id: Sign out is how you leave. Returns how many ended.
create or replace function end_sessions(session uuid default null) returns integer
language plpgsql security definer set search_path = '' as $$
declare
  me uuid := auth.uid();
  here text := auth.jwt() ->> 'session_id';
  n integer;
begin
  if me is null or here is null then
    raise exception 'sign in first';
  end if;
  delete from auth.sessions s where s.user_id = me and s.id::text <> here and (session is null or s.id = session);
  get diagnostics n = row_count;
  return n;
end $$;

revoke execute on function my_sessions(), end_sessions(uuid) from public, anon;
grant execute on function my_sessions(), end_sessions(uuid) to authenticated;
