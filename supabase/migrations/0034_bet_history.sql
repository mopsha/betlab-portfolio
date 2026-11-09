-- The bet change log (Nov 4; idea #84): every insert, edit and delete of a bet, with the row before and after and who did
-- it (null: the worker). Before this a changed bet left no trace, so an undo or a wrong stake couldn't be seen afterwards.
-- Append-only: nobody can edit or delete it through the API. A failed log line never blocks the bet.
create table if not exists bet_history (
  id bigserial primary key,
  bet_id uuid not null,
  user_id uuid not null,
  op text not null check (op in ('insert', 'update', 'delete')),
  at timestamptz not null default now(),
  by_user uuid,
  before jsonb,
  after jsonb
);
create index if not exists bet_history_bet on bet_history (bet_id, at);
alter table bet_history enable row level security;
create policy mine on bet_history for select to authenticated using (user_id = (select auth.uid()));
grant select on bet_history to authenticated;

create or replace function log_bet_change() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'UPDATE' and old is not distinct from new then
    return null;
  end if;
  insert into bet_history (bet_id, user_id, op, by_user, before, after)
  values (case when tg_op = 'DELETE' then old.bet_id else new.bet_id end,
          case when tg_op = 'DELETE' then old.user_id else new.user_id end,
          lower(tg_op), auth.uid(),
          case when tg_op = 'INSERT' then null else to_jsonb(old) end,
          case when tg_op = 'DELETE' then null else to_jsonb(new) end);
  return null;
exception when others then
  raise warning 'log_bet_change: %', sqlerrm;
  return null;
end $$;
revoke execute on function log_bet_change() from public, anon, authenticated;

create trigger history after insert or update or delete on bets for each row execute function log_bet_change();
