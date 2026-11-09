-- Live CLV on open bets (Oct 28, idea #2): at every publish the worker (src/betlab/clv_now.py) writes each open real
-- bet's current sharp chance and CLV at your price; both apps show it on the bet until it's graded, when the graded
-- close takes over. A started game's row keeps its last value (the last look before the close). Your own rows only;
-- the worker writes through the service connection.
create table if not exists bet_clv (
  bet_id      uuid primary key references bets (bet_id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  p_now       numeric not null,
  clv         numeric not null,
  updated_at  timestamptz not null default now()
);
alter table bet_clv enable row level security;
create policy own_rows on bet_clv for select to authenticated using (user_id = (select auth.uid()));
grant select on bet_clv to authenticated;
