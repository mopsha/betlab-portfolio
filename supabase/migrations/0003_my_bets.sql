-- My bets (Phase 4, 2026-10-01).
--
-- 1. A user's own saved parlays get graded in their own row, so a custom slip's legs never sit
--    in the shared fun_tickets table (Mike's rule: one user's data never touches another's).
--    The worker fills these from the fun ledger for the owner.
-- 2. my_bets carries what the My bets screen needs: the result and profit whichever table graded
--    it, and the pick's league, market, EV and closing price.

alter table custom_parlays
  add column status      text,
  add column leg_results jsonb,
  add column profit_1u   numeric,
  add column graded_at   timestamptz;

drop view my_bets;
create view my_bets with (security_invoker = true) as
select b.*,
       pp.status   as pick_status,
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
       pp.kind     as pick_kind,
       pp.ev,
       pp.close_price,
       pp.current_rule,
       coalesce(ft.leg_results, cp.leg_results) as leg_results,
       ft.kind     as ticket_kind,
       ft.sport
from bets b
left join paper_picks pp on pp.pick_id = b.pick_id and pp.tier = case b.kind when 'lean' then 'lean' else 'pick' end
left join fun_tickets ft on ft.sgp_id = b.sgp_id
left join custom_parlays cp on cp.sgp_id = b.sgp_id and cp.user_id = b.user_id;

grant select on my_bets to authenticated;
