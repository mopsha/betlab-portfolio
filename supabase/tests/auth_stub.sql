-- The parts of Supabase the migration relies on, for tests on a plain Postgres (PGlite):
-- the auth schema with users and auth.uid(), and the authenticated / service_role roles.
-- auth.uid() reads the signed-in user from the request's JWT claim, as Supabase does.
create schema if not exists auth;
create table if not exists auth.users (id uuid primary key, email text);   -- email: find_person (0024)
create or replace function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
end $$;
-- signed-in devices (0037): the session in the JWT, and auth.sessions as Supabase has it
create table if not exists auth.sessions (id uuid primary key, user_id uuid not null, created_at timestamptz default now(), updated_at timestamptz,
  refreshed_at timestamp, not_after timestamptz, user_agent text, ip inet);
create or replace function auth.jwt() returns jsonb language sql stable as $$
  select jsonb_build_object('session_id', nullif(current_setting('request.jwt.claim.session_id', true), ''))
$$;
grant execute on function auth.jwt() to authenticated, anon;
grant usage on schema auth to authenticated, anon;
-- No default table privileges: the migration must grant everything it exposes, as on Supabase
-- with "automatically expose new tables" off.
grant execute on function auth.uid() to authenticated, anon;
-- Supabase hands these to anon and authenticated on new tables even with auto-expose off;
-- 0002_tighten_grants.sql must take them back.
alter default privileges in schema public grant truncate, references, trigger on tables to anon, authenticated;
