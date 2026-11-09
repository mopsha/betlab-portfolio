-- A token for one market and certain games (Mike, Nov 5: "if it's for a game I should select the market, then select games
-- from a drop down if I need to"). `market`: moneyline, spread, total or props, null for any (web builder.marketFits, iPhone
-- Build.marketFits). `games`: the games picked from the schedule, [{event_id, matchup, commence_time, sport}]; the finder searches only
-- those (and any game of `teams`, which stays for a game not posted yet).
alter table promos add column if not exists market text check (market in ('moneyline', 'spread', 'total', 'props'));
alter table promos add column if not exists games jsonb;
