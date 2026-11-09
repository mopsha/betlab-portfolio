-- BetLab app database, v1 (docs/APP_PLAN.md, 2026-10-01).
--
-- Shared tables hold market and model data. Signed-in users can read them; only the worker
-- writes them, with the service key (which bypasses row-level security).
-- Personal tables carry user_id on every row, and row-level security limits every read and
-- write to the signed-in user's own rows (Mike, 2026-10-01: "my data doesn't touch another
-- user's data"). The CSV ledgers stay the source of truth for now; these tables are the
-- app's read model, refreshed by `betlab publish`.


-- ============================================================== shared: market and model data

-- One row per game in any league. game_id = '{league}:{native id}', e.g. 'nfl:2026_04_PIT_CLE',
-- 'ncaaf:401858237', 'nhl:2025020123', 'soccer:<odds event id>'. odds_event_id is separate and
-- nullable: previews and the NHL view exist before odds do.
create table games (
  game_id        text primary key,
  league         text not null,
  season         int,
  week           int,
  odds_event_id  text unique,
  home           text,
  away           text,
  matchup        text,
  commence_time  timestamptz,
  state          text,                 -- scheduled | live | final
  home_score     int,
  away_score     int,
  updated_at     timestamptz not null default now()
);
create index games_time on games (commence_time);

-- Today's card: every priced FanDuel line that is a pick, a lean or a check-the-news flag.
-- offer_id is ledger.pick_id(); rows the latest publish didn't see turn active = false.
create table offers (
  offer_id       text primary key,
  tier           text not null check (tier in ('pick', 'lean', 'check')),
  league         text not null,
  game_id        text,
  odds_event_id  text,
  commence_time  timestamptz,
  matchup        text,
  market         text,
  kind           text,                 -- game | prop
  side           text,
  player         text,
  label          text not null,
  point          numeric,
  price          numeric not null,
  book           text,
  p_model        numeric,
  p_market       numeric,
  p_final        numeric,
  p_push         numeric,
  ev             numeric,
  units_flat     numeric,
  units_tier     numeric,
  units_kelly    numeric,
  market_source  text,
  why            text,
  context        text,
  fd_url         text,
  active         boolean not null default true,
  published_at   timestamptz not null default now()
);
create index offers_live on offers (active, commence_time);

-- The shared paper record (picks.csv and leans.csv): it grades the model, so it belongs to no
-- one. A pick is logged once at the first price it qualified at; the trigger below keeps its
-- time, price and line from ever changing (CLAUDE.md rule 4).
-- Keyed by (pick_id, tier): a bet logged as a pick can later be logged again as a lean when it
-- was re-priced below the bar; the two ledgers keep both records.
create table paper_picks (
  pick_id        text not null,
  tier           text not null check (tier in ('pick', 'lean')),
  created_at     timestamptz not null,
  league         text,
  odds_event_id  text,
  game_ref       text,
  commence_time  timestamptz,
  matchup        text,
  market         text,
  side           text,
  player         text,
  label          text,
  point          numeric,
  price          numeric not null,
  book           text,
  kind           text,
  p_model        numeric,
  p_market       numeric,
  p_final        numeric,
  p_push         numeric,
  ev             numeric,
  market_source  text,
  units_flat     numeric,
  units_tier     numeric,
  units_kelly    numeric,
  why            text,
  status         text,
  profit_flat    numeric,
  close_point    numeric,
  close_price    numeric,
  p_close        numeric,
  clv            numeric,
  clv_raw        numeric,
  graded_at      timestamptz,
  current_rule   boolean not null default true,  -- false: logged under a retired rule (DECISIONS 2026-09-30)
  primary key (pick_id, tier)
);
create index paper_picks_time on paper_picks (commence_time);

create function paper_picks_frozen() returns trigger language plpgsql as $$
begin
  if new.created_at is distinct from old.created_at
     or new.price is distinct from old.price
     or new.point is distinct from old.point
     or new.label is distinct from old.label then
    raise exception 'paper pick % is history: its time, price, line and label never change', old.pick_id;
  end if;
  return new;
end $$;
create trigger paper_picks_frozen before update on paper_picks
  for each row execute function paper_picks_frozen();
create function paper_picks_no_delete() returns trigger language plpgsql as $$
begin
  raise exception 'paper pick % is history: it is never deleted', old.pick_id;
end $$;
create trigger paper_picks_no_delete before delete on paper_picks
  for each row execute function paper_picks_no_delete();

-- Generated fun tickets: same-game parlays, SGP+ and TD tickets, overs to root for. The whole
-- ticket is body; the columns are what lists and grading need.
create table fun_tickets (
  sgp_id         text primary key,
  kind           text not null,        -- sgp | sgp_plus | td | over
  sport          text not null,
  game_id        text,
  odds_event_id  text,
  slate          text,
  matchup        text,
  commence_time  timestamptz,
  fair_price     numeric,
  p_fair         numeric,
  naive_price    numeric,
  price          numeric,              -- FanDuel's own price, when known (overs, TD tickets)
  body           jsonb not null,
  status         text,
  leg_results    jsonb,
  profit_1u      numeric,
  graded_at      timestamptz,
  active         boolean not null default true,
  published_at   timestamptz not null default now()
);
create index fun_tickets_live on fun_tickets (active, commence_time);

-- The builder's simulated-draw packs, one per game (split in parts when big).
create table leg_packs (
  pack_key       text primary key,
  odds_event_id  text,
  sport          text,
  commence_time  timestamptz,
  body           jsonb not null,
  published_at   timestamptz not null default now()
);

-- Each game's analysis as built: kind = nfl_preview | ncaaf_preview | nhl | nba.
create table game_analysis (
  game_id        text not null,
  kind           text not null,
  body           jsonb not null,
  published_at   timestamptz not null default now(),
  primary key (game_id, kind)
);

-- Whole documents that don't need columns: the scorecard (golive), results, fun results,
-- coverage, meta, card notes, fun slates and track records.
create table docs (
  collection     text not null,
  doc_id         text not null,
  body           jsonb not null,
  published_at   timestamptz not null default now(),
  primary key (collection, doc_id)
);

-- Every scheduled job's steps (replaces the GitHub Actions run list).
create table runs (
  id             bigserial primary key,
  job            text not null,
  step           text not null,
  started_at     timestamptz not null default now(),
  finished_at    timestamptz,
  exit_code      int,
  log_tail       text,
  credits_used   int
);
create index runs_recent on runs (started_at desc);

-- ============================================================== personal: one user's rows only

-- Picks, leans and parlays a user marked (paper) or placed (real). Replaces the page's taken
-- and fun_taken collections.
create table bets (
  bet_id         uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  kind           text not null check (kind in ('pick', 'lean', 'parlay', 'custom')),
  pick_id        text,
  sgp_id         text,
  mode           text not null default 'paper' check (mode in ('paper', 'real')),
  price          numeric,
  stake          numeric,
  book           text not null default 'FanDuel',
  label          text,
  matchup        text,
  fair_price     numeric,
  p_fair         numeric,
  legs           jsonb,
  games          jsonb,
  odds_event_id  text,
  placed_at      timestamptz not null default now(),
  check ((pick_id is null) <> (sgp_id is null)),
  unique (user_id, pick_id),
  unique (user_id, sgp_id)
);

-- FanDuel prices a user typed for a slip (replaces fun_quotes for generated slips).
create table quotes (
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  sgp_id         text not null,
  price          numeric not null,
  fair_price     numeric,
  naive_price    numeric,
  p_fair         numeric,
  n_legs         int,
  legs           jsonb,
  matchup        text,
  odds_event_id  text,
  games          jsonb,
  sport          text,
  quoted_at      timestamptz not null default now(),
  primary key (user_id, sgp_id)
);

-- Parlays a user built and saved, with their grade (the page's custom-… quotes).
create table custom_parlays (
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  sgp_id         text not null,
  price          numeric,
  fair_price     numeric,
  naive_price    numeric,
  p_fair         numeric,
  n_legs         int,
  legs           jsonb not null,
  games          jsonb,
  matchup        text,
  odds_event_id  text,
  sport          text,
  grade          text,
  grade_parts    jsonb,
  quoted_at      timestamptz not null default now(),
  primary key (user_id, sgp_id)
);

create table user_settings (
  user_id            uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  bankroll           numeric not null default 100,
  unit_pct           numeric not null default 0.01,
  fun_bucket_monthly numeric not null default 10,
  book               text not null default 'FanDuel',
  notify             jsonb not null default '{}'::jsonb,
  updated_at         timestamptz not null default now()
);

-- The shared to-do list between a user and Claude (owner = you | claude).
create table todos (
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  id             text not null default gen_random_uuid()::text,
  owner          text not null check (owner in ('you', 'claude')),
  title          text not null,
  detail         text not null default '',
  due            date,
  status         text not null default 'open' check (status in ('open', 'done')),
  done_at        timestamptz,
  ord            bigint not null default 0,
  added_by       text not null default 'app',
  created_at     timestamptz not null default now(),
  primary key (user_id, id)
);

create table reviews (
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  id             text not null,
  title          text not null,
  body           text not null,
  created_at     timestamptz not null default now(),
  primary key (user_id, id)
);

-- On-demand jobs the app asks the worker for; the worker checks an allow-list, the credit
-- guard and a cooldown before running one.
create table job_requests (
  id             bigserial primary key,
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  job            text not null check (job in ('refresh_free', 'reprice', 'sync_personal')),
  status         text not null default 'queued' check (status in ('queued', 'running', 'done', 'refused', 'failed')),
  note           text,
  requested_at   timestamptz not null default now(),
  finished_at    timestamptz
);

-- ============================================================== row-level security

alter table games          enable row level security;
alter table offers         enable row level security;
alter table paper_picks    enable row level security;
alter table fun_tickets    enable row level security;
alter table leg_packs      enable row level security;
alter table game_analysis  enable row level security;
alter table docs           enable row level security;
alter table runs           enable row level security;

create policy read_shared on games         for select to authenticated using (true);
create policy read_shared on offers        for select to authenticated using (true);
create policy read_shared on paper_picks   for select to authenticated using (true);
create policy read_shared on fun_tickets   for select to authenticated using (true);
create policy read_shared on leg_packs     for select to authenticated using (true);
create policy read_shared on game_analysis for select to authenticated using (true);
create policy read_shared on docs          for select to authenticated using (true);
create policy read_shared on runs          for select to authenticated using (true);

alter table bets           enable row level security;
alter table quotes         enable row level security;
alter table custom_parlays enable row level security;
alter table user_settings  enable row level security;
alter table todos          enable row level security;
alter table reviews        enable row level security;
alter table job_requests   enable row level security;

create policy own_rows on bets           for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy own_rows on quotes         for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy own_rows on custom_parlays for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy own_rows on user_settings  for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy own_rows on todos          for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy own_rows on reviews        for select to authenticated
  using (user_id = (select auth.uid()));            -- Claude writes reviews; the app only reads them
create policy own_read on job_requests   for select to authenticated
  using (user_id = (select auth.uid()));
create policy own_insert on job_requests for insert to authenticated
  with check (user_id = (select auth.uid()) and status = 'queued');

-- Each user's own bets with what they were on: the paper pick, a generated ticket or their
-- own saved parlay. security_invoker makes the view obey the caller's row-level security.
create view my_bets with (security_invoker = true) as
select b.*,
       pp.status   as pick_status,
       pp.profit_flat,
       pp.clv,
       pp.clv_raw,
       pp.commence_time as pick_commence_time,
       ft.status   as ticket_status,
       ft.profit_1u,
       ft.commence_time as ticket_commence_time,
       cp.grade
from bets b
left join paper_picks pp on pp.pick_id = b.pick_id and pp.tier = case b.kind when 'lean' then 'lean' else 'pick' end
left join fun_tickets ft on ft.sgp_id = b.sgp_id
left join custom_parlays cp on cp.sgp_id = b.sgp_id and cp.user_id = b.user_id;

-- ============================================================== privileges
-- Tables are not exposed to the app automatically (Supabase's "automatically expose new tables"
-- is off), so every grant is explicit. Signed-out visitors (anon) get nothing. Row-level
-- security above still decides which rows a signed-in user sees.
grant usage on schema public to authenticated;
grant select on games, offers, paper_picks, fun_tickets, leg_packs, game_analysis, docs, runs to authenticated;
grant select, insert, update, delete on bets, quotes, custom_parlays, user_settings, todos to authenticated;
grant select on reviews to authenticated;
grant select, insert on job_requests to authenticated;
grant usage on sequence job_requests_id_seq to authenticated;
grant select on my_bets to authenticated;
