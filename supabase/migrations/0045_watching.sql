-- Watched games (2026-11-07): the games an account will watch, by games.game_id. Every slice now carries each of its
-- games' own same-game slips (fun_tickets kind 'sgp' with its slate); Today shows a watched game's slips next to the
-- slice's tickets once the slice locks, and the lock alert names them (alerts.watched_slips). It replaces two fixed
-- rules: the Knicks' own slips (fun.nba.own_slips_teams) and a lone game's slips (an NFL prime-time game, a lone NBA
-- game). Per account, written by the apps' Watch button on a game page.
alter table user_settings add column if not exists watching text[] not null default '{}';
