-- The DFS optimizer (Nov 5, idea #38; dfs.py): today's DraftKings classic slates and their best lineups, shared by every account
-- as the card is. Written by the worker. Read-only in the apps: a lineup is a suggestion you enter yourself.
create table if not exists dfs_slates (
  slate_id text primary key,               -- "<league>:<DraftKings draft group>"
  league text not null,
  label text,
  lock_at timestamptz not null,
  games int,
  priced int,                              -- players priced by the market; the rest are on their DraftKings average
  players int,
  lineups jsonb not null,                  -- [{salary, proj, players: [{slot, id, name, team, game, salary, proj, basis, status}]}]
  built_at timestamptz not null default now()
);
alter table dfs_slates enable row level security;
create policy read_all on dfs_slates for select to authenticated using (true);
grant select on dfs_slates to authenticated;
