-- The calendar (Nov 4, idea #54; Mike: "make sure we have all the games and times far earlier ... pull all at once and then
-- just once a day it checks for any changes"). Every game ESPN lists for the next 10 weeks, free; the Odds API's free list
-- only looks 1 day ahead for the NHL, 2 for college basketball and 2-3 weeks for the rest, so `games` can't hold this. Kept
-- apart from `games`, whose ids and rows the card, tickets and bets depend on; `game_id` links a row to its game page.
create table if not exists schedule_games (
  id text primary key,                     -- "<league>:<ESPN event id>"
  league text not null,                    -- epl, nfl, ufc ...
  sport text not null,                     -- as games.league: soccer for every soccer league
  start timestamptz not null,
  home text,
  away text,
  matchup text not null,
  game_id text,
  updated_at timestamptz not null default now()
);
create index if not exists schedule_games_start on schedule_games (start);
create index if not exists schedule_games_search on schedule_games (lower(matchup));
alter table schedule_games enable row level security;
create policy read_all on schedule_games for select to authenticated using (true);
grant select on schedule_games to authenticated;

create or replace view calendar_days with (security_invoker = true) as
  select (start at time zone 'America/New_York')::date::text as day, sport, count(*)::int as games
  from schedule_games group by 1, 2;
grant select on calendar_days to authenticated;
