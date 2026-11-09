-- 0007: each account's own real-money start (Mike, 2026-10-10: his girlfriend's account). Null means the
-- default, the go-live date (2026-10-18, web/lib/real.ts REAL_START); a date makes "Mark as mine" record
-- real bets from then. Set in More > Settings.
alter table user_settings add column if not exists real_from timestamptz;
