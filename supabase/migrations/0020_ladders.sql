-- Ladder challenges (Mike, Oct 26): start with some units, roll the whole stack into one bet at a time, and climb to a
-- target (his first: 1u -> 100u). Each step is one of the user's own bets carrying the ladder's id, so it settles
-- however that bet settles; the stack (the start plus every settled step's profit), the open step, and whether the
-- ladder climbed or busted are worked out from those bets (web/lib/ladder.ts, ios/BetLab/Ladder.swift, one fixture:
-- tests/fixtures/ladder.json). Ladder steps are real bets outside the 5u-a-day rule (Mike, Oct 26; DECISIONS).
create table if not exists ladders (
  ladder_id     uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid() references auth.users (id) on delete cascade,
  start_units   numeric not null check (start_units > 0),
  target_units  numeric not null,
  status        text not null default 'active' check (status in ('active', 'stopped')),
  created_at    timestamptz not null default now(),
  ended_at      timestamptz,
  check (target_units > start_units),
  unique (ladder_id, user_id)
);
alter table ladders enable row level security;
create policy own_rows on ladders for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
grant select, insert, update, delete on ladders to authenticated;

-- a step belongs to its owner's ladder: (ladder_id, user_id) must name one of that user's ladders
alter table bets add column if not exists ladder_id uuid;
alter table bets add constraint bets_ladder_fk foreign key (ladder_id, user_id)
  references ladders (ladder_id, user_id) on delete set null (ladder_id);

-- my_bets selects b.*, fixed when the view is made: recreated (as in 0015) to carry ladder_id
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
