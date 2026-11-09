-- A bet reset (Mike, Nov 1: FanDuel's BET RESET TOKEN: "if i lose I get my wager back as bonus bets").
--   bets.reset        the bet carries one. It changes no profit: a loss still costs the stake, in cash.
--   promos.from_bet   the bet a bonus bet came back from: one token per bet, gone with the bet
--   issue_resets()    the worker's every tick (resets.py, `betlab resets`): a lost real bet with a reset puts its stake,
--                     in dollars, in the wallet as a bonus bet. A grade that changes, or a reset turned off, takes back
--                     a token not yet used (a grade that came early is not final: CLAUDE.md, Oct 30).
alter table bets add column if not exists reset boolean not null default false;
alter table promos add column if not exists from_bet uuid unique references bets (bet_id) on delete cascade;

-- my_bets selects b.*, fixed when the view is made: recreated (as in 0023) to carry the new columns. friend_bets
-- returns its rows, so it goes and comes back with it (as 0024 made it).
drop function if exists friend_bets(uuid);
drop view my_bets;
create view my_bets with (security_invoker = true) as
select b.*,
       pp.status as pick_status,
       pp.profit_flat,
       pp.clv,
       pp.clv_raw,
       pp.commence_time as pick_commence_time,
       coalesce(ft.status, cp.status) as ticket_status,
       coalesce(ft.profit_1u, cp.profit_1u) as profit_1u,
       ft.commence_time as ticket_commence_time,
       cp.grade,
       pp.league,
       pp.market,
       pp.kind as pick_kind,
       pp.ev,
       pp.close_price,
       pp.current_rule,
       coalesce(ft.leg_results, cp.leg_results) as leg_results,
       ft.kind as ticket_kind,
       ft.sport,
       pp.price as logged_price,
       case
         when pp.close_push is not null then pp.close_push
         -- Football grading weights integer-line CLV by its closing push chance.
         -- The old ledger did not retain it. Opening p_push is not a substitute.
         when pp.league in ('nfl', 'ncaaf') and pp.kind is distinct from 'prop'
           and pp.market in ('spreads', 'totals')
           and (pp.point is null or pp.point = trunc(pp.point)) then null
         -- Other existing grading paths measure CLV without a push adjustment.
         else 0::numeric
       end as close_push
from bets b
left join paper_picks pp on pp.pick_id = b.pick_id
  and pp.tier = case b.kind when 'lean' then 'lean' else 'pick' end
left join fun_tickets ft on ft.sgp_id = b.sgp_id
left join custom_parlays cp on cp.sgp_id = b.sgp_id and cp.user_id = b.user_id;

grant select on my_bets to authenticated;

-- Friends' bets, as My bets shows them (0024, unchanged)
create or replace function friend_bets(friend uuid default null) returns setof my_bets
language sql stable security definer set search_path = public as $$
  select b.* from my_bets b
  where b.user_id <> auth.uid() and connected(b.user_id, true)
    and (friend is null or b.user_id = friend)
    and coalesce((select s.share_bets from user_settings s where s.user_id = b.user_id), true)
$$;
revoke execute on function friend_bets(uuid) from public, anon;
grant execute on function friend_bets(uuid) to authenticated;

create or replace function issue_resets() returns integer
language plpgsql security definer set search_path = public as $$
declare
  added integer;
begin
  delete from promos p using my_bets b
  where p.from_bet = b.bet_id and p.status = 'open'
    and not (b.reset and b.mode = 'real' and b.cashout is null and lower(coalesce(b.pick_status, b.ticket_status, '')) = 'lost');
  insert into promos (user_id, kind, book, amount_dollars, note, from_bet)
  select b.user_id, 'bonus', b.book, round(coalesce(b.stake, 1) * coalesce(s.unit_dollars, 5), 2), 'From a bet reset', b.bet_id
  from my_bets b
  left join user_settings s on s.user_id = b.user_id
  where b.reset and b.mode = 'real' and b.cashout is null and lower(coalesce(b.pick_status, b.ticket_status, '')) = 'lost'
  on conflict (from_bet) do nothing;
  get diagnostics added = row_count;
  return added;
end $$;
revoke execute on function issue_resets() from public, anon, authenticated;
