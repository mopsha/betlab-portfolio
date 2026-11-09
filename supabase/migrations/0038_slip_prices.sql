-- A slip's fair price (Nov 4, idea #20): a bet added from a screenshot, priced from its game's pack when it was read. Apart from
-- bets.fair_price and custom_parlays on purpose: fun_ledger.quote_model learns from those, and the promo finder ranks by it, so
-- writing there would change a model with no backtest (and read errors would teach it). Nothing trains on this table.
create table if not exists slip_prices (
  bet_id uuid primary key references bets (bet_id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  p numeric not null check (p > 0 and p <= 1),
  priced_at timestamptz not null default now()
);
alter table slip_prices enable row level security;
create policy mine on slip_prices for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
grant select, insert, delete on slip_prices to authenticated;
