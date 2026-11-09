-- Search (Nov 4, idea #52): the shared part, games from the calendar, fights from `games` and players from the builder's leg packs
-- (the players priced for games pulled so far). Your bets and teams are searched in the apps. As the caller, so row-level
-- security applies. `q` is compared with position(), never LIKE, so a % or _ in it is just a character.
create or replace function search_app(q text) returns table (kind text, title text, sport text, at timestamptz, game_id text)
language sql stable set search_path = public as $$
  with needle as (select lower(trim(q)) as n)
  (select 'game', s.matchup, s.sport, s.start, s.game_id from schedule_games s, needle
    where length(n) >= 2 and position(n in lower(s.matchup)) > 0 and s.start > now() - interval '1 day'
    order by s.start limit 25)
  union all
  (select 'game', g.matchup, g.league, g.commence_time, g.game_id from games g, needle
    where length(n) >= 2 and g.league = 'ufc' and position(n in lower(g.matchup)) > 0 and g.commence_time > now() - interval '1 day'
    order by g.commence_time limit 15)
  union all
  (select 'player', x.player, x.sport, x.commence_time, x.game_id from (
      select distinct on (lower(leg->>'player')) leg->>'player' as player, p.sport, p.commence_time, g.game_id
      from leg_packs p cross join needle cross join lateral jsonb_array_elements(p.body->'legs') leg
      left join games g on g.odds_event_id = p.odds_event_id
      where length(n) >= 2 and leg->>'player' not in ('', 'game side') and position(n in lower(leg->>'player')) > 0
      order by lower(leg->>'player'), p.commence_time
    ) x order by x.commence_time limit 15)
$$;
revoke execute on function search_app(text) from public, anon;
grant execute on function search_app(text) to authenticated;
