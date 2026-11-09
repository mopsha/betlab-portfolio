-- Promos (Mike, Oct 30: the boosts and bonus bets "need a total rework"). One migration for the counting fixes and the
-- wallet, so my_bets is recreated once:
--   bets.boost_cap   the most extra winnings a boost can add, in units (a book's "max extra winnings $" over the unit
--                    size, saved at placement): a capped boost had counted uncapped (web lib/bets.ts profit,
--                    ios BetMath.profit, fun_ledger.marked_profit)
--   bets.promo_id    the token this bet used (a row of promos, the bettor's own: the foreign key is on the pair)
--   bets.lock_id     the two bets of a two-book lock (the promo side and its cash hedge) share one id
--   bets.promo_ev    the token's expected dollars when it was placed (the finder's number), for "what it turned into
--                    vs what it should have"
--   user_settings.unit_dollars  dollars per unit, on the account (was each device's own: the slip reader's field)
--   promos           the wallet: each bonus bet or boost the books have given, with its terms and expiry; a bet that
--                    takes one marks it used, and deleting that bet gives it back (promo_used trigger). Expired is
--                    expires_at < now(), worked out when read.
alter table bets add column if not exists boost_cap numeric check (boost_cap is null or boost_cap >= 0);
alter table bets add column if not exists promo_id uuid;
alter table bets add column if not exists lock_id uuid;
alter table bets add column if not exists promo_ev numeric;
alter table user_settings add column if not exists unit_dollars numeric check (unit_dollars is null or unit_dollars > 0);

create table if not exists promos (
  promo_id           uuid primary key default gen_random_uuid(),
  user_id            uuid not null default auth.uid() references auth.users (id) on delete cascade,
  kind               text not null check (kind in ('bonus', 'boost')),
  book               text,                       -- FanDuel, DraftKings, Novig; null: any
  amount_dollars     numeric check (amount_dollars is null or amount_dollars > 0),   -- a bonus bet's face; a boost's max stake
  pct                numeric check (pct is null or (pct > 0 and pct <= 500)),        -- a boost's size
  max_extra_dollars  numeric check (max_extra_dollars is null or max_extra_dollars > 0),
  min_legs           integer check (min_legs is null or min_legs between 1 and 20),
  min_odds           numeric,                    -- American
  max_odds           numeric,
  sports             text[],                     -- null: any sport
  note               text,
  expires_at         timestamptz,
  status             text not null default 'open' check (status in ('open', 'used', 'void')),
  source             text not null default 'typed' check (source in ('typed', 'screenshot')),
  created_at         timestamptz not null default now(),
  unique (promo_id, user_id),
  check (kind <> 'boost' or pct is not null)
);
alter table promos enable row level security;
create policy own_rows on promos for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
grant select, insert, update, delete on promos to authenticated;

alter table bets add constraint bets_promo_fk foreign key (promo_id, user_id)
  references promos (promo_id, user_id) on delete set null (promo_id);

-- a bet that takes a token uses it up; moving or deleting that bet gives it back (unless voided by hand)
create or replace function promo_used() returns trigger
language plpgsql security invoker set search_path = public as $$
begin
  if tg_op in ('UPDATE', 'DELETE') and old.promo_id is not null
     and (tg_op = 'DELETE' or new.promo_id is distinct from old.promo_id) then
    update promos set status = 'open'
    where promo_id = old.promo_id and user_id = old.user_id and status = 'used'
      and not exists (select 1 from bets b where b.promo_id = old.promo_id and b.bet_id <> old.bet_id);
  end if;
  if tg_op in ('INSERT', 'UPDATE') and new.promo_id is not null then
    update promos set status = 'used' where promo_id = new.promo_id and user_id = new.user_id and status = 'open';
  end if;
  return null;
end $$;
create trigger promo_used after insert or update of promo_id or delete on bets
  for each row execute function promo_used();

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
