-- A Build slip marked before Nov 1 was saved without its games (each leg's game, for the live tracker): only its saved
-- slip in custom_parlays has them. The owner's apps fill them in from there, but a friend can't read another account's
-- custom_parlays (own rows only), so in Friends such a slip tracked as one made-up "Your SGP+: A @ B, C @ D" game and
-- its legs matched nothing (Nov 9 review). Copy the slip's games onto the bet once, so every reader (my_bets,
-- friend_bets, the worker) has them. Only bets with no games of their own are touched; bet_history logs each change.
-- Safe to run again: a bet that has its games is left alone.
update bets b
set games = cp.games
from custom_parlays cp
where cp.user_id = b.user_id and cp.sgp_id = b.sgp_id and b.kind = 'custom'
  and (b.games is null or b.games = '[]'::jsonb)
  and jsonb_typeof(cp.games) = 'array' and jsonb_array_length(cp.games) > 0;
