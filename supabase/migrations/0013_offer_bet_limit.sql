-- 0013: an exchange price's bet limit on each offer (Novig, Oct 22): the dollars available at that price, from the
-- Odds API's includeBetLimits. publish._offer sends it in the same commit (the Oct 12 lesson, migration 0008).
alter table offers add column if not exists bet_limit numeric;
