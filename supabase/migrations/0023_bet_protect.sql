-- FanDuel's Bet Protect+ on a bet (Mike, Oct 26): it costs 3% of the stake on top, in cash even on a bonus bet ("total
-- charged $10.30" on a $10 bet), and a leg on a player who doesn't play counts as won ("INJURY COVERED, WON ON FANDUEL":
-- Oct 19's +911 bonus parlay paid $91.15 while BetLab had voided it). `protect` true: P/L takes the fee off every settled
-- bet but a void (web lib/bets.ts profit, ios BetMath.profit, fun_ledger.marked_profit), and the graders count a
-- did-not-play leg as won (fun_ledger._finish). my_bets selects b.*, fixed when the view is made: recreated (as in 0020).
alter table bets add column if not exists protect boolean not null default false;

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
