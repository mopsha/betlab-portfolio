-- Live Activities (Oct 27): how many times the worker sent a bet's start. A start an iPhone never confirms (no update
-- token back) is sent again, up to live_activity.MAX_STARTS.
alter table live_activity_state add column if not exists starts int not null default 1;
