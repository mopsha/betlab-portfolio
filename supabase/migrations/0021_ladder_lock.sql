-- Ladder steps locked by the worker (Mike, Oct 26: "If I start a ladder at the beginning of the day I can signify a game
-- or not but it gives me best pick from that day and waits until it has the info it needs, like I don't need a pick on
-- demand"). The worker's `ladders` step (src/betlab/ladders.py, each pre-game tick) holds the day's best step (or the
-- chosen game's) and locks it once that game's news is in, then alerts the owner; the apps show what it holds and the
-- locked step.
--   game_id   the game chosen for the next step (the games table's id); null: any game today
--   skipped   offer ids turned down ("Not this one"), so the worker and both apps leave them out
--   locked    the locked step: the offer as it was at lock time (offer_id, tier, label, price, book, matchup,
--             commence_time, ev, game_id, stake, step); cleared when the step is placed, turned down or starts unplaced
--   notice    why the ladder waits on you ("none:<game_id>": the chosen game has no +EV step after its news;
--             "missed:<label>": the locked step started before it was placed)
alter table ladders add column if not exists game_id text;
alter table ladders add column if not exists skipped jsonb not null default '[]'::jsonb;
alter table ladders add column if not exists locked jsonb;
alter table ladders add column if not exists locked_at timestamptz;
alter table ladders add column if not exists notice text;
