-- Supabase grants anon and authenticated TRUNCATE, REFERENCES and TRIGGER on new tables even with
-- "automatically expose new tables" off (found on Mike's project, 2026-10-01). TRUNCATE skips
-- row-level security and the paper-pick triggers, so take them all away, now and for future
-- tables. Signed-out visitors (anon) get nothing at all; signed-in users keep exactly what
-- 0001_init.sql grants.
revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;
revoke truncate, references, trigger on all tables in schema public from authenticated;

alter default privileges in schema public revoke all on tables from anon;
alter default privileges in schema public revoke all on sequences from anon;
alter default privileges in schema public revoke truncate, references, trigger on tables from authenticated;

-- The trigger functions are internal: nobody calls them directly.
revoke execute on function paper_picks_frozen() from public, anon, authenticated;
revoke execute on function paper_picks_no_delete() from public, anon, authenticated;
