# BetLab web app: new structure and build plan

## Context

Today BetLab lives on one claude.ai page with eight tabs (Today, Games, Fun, To-do, Results,
Review, Markets, Learn). The same game shows up on three tabs (its leans on Today, its analysis
on Games, its parlays on Fun), every sport is organized differently, and the analysis crowds
out the bets. Mike (Oct 1): "there's a better way to organize EVERYTHING... let's start building
the web version and totally replan the structure."

Decisions so far:
- **Structure:** a time-first Home feed and one page per game.
- **Order:** database first.
- **Look:** a fresh, app-like design.
- **Earlier (Oct 1):** Railway plus Supabase free; just Mike for now, with per-user separation
  designed in; super sleek, with analysis in the background (`docs/ROADMAP.md`).

The goal is a web app that answers "what's worth doing now?" in one glance, and puts everything
about a game in one place. The paper record keeps running untouched while the app is built.

## Status (2026-10-04; latest notes Mon Oct 12, 2026, 7:35 PM ET)

- **Oct 12: two accounts and two books.** Mike's girlfriend signs in with Google (the home-screen app's sign-in sheet
  fix: the login screen polls `/auth/status`); DraftKings sits beside FanDuel on every bet (links, book on each bet,
  My bets by book). An unmigrated column stopped every publish 2:02-7:05 PM ET (migration 0008; `test_publish` now
  checks every published column against the migrations).

- **Phase 1, done.** The Supabase database is live (`supabase/`, migrations 0001 and 0002 applied;
  `betlab db-migrate` tracks them). Every cloud run publishes to it (confirmed at 1:28 PM).
- **Phase 2 core, done.** The web app is live at https://betlab.example.app.
  It has Home (no overs to root for, Mike's call), Games, and one page per game, plus Mark,
  Undo and FanDuel prices. Mike signed in from the live site, and it works.
  `/api/health` checks the Supabase wiring.
- **Phase 3 started.** `src/betlab/worker.py` runs on Railway as the `worker` service, in shadow
  mode (`BETLAB_SHADOW=1`), with no data volume and no Odds API keys. It only logs when each job
  would run.
- **Phase 4 started (Oct 1 evening): My bets is live.** Migration 0003 grades a user's own parlays in
  `custom_parlays` (never in the shared `fun_tickets`) and widens `my_bets`. `publish` now also writes
  every graded fun-ledger slip as an inactive ticket, since tickets are graded after they leave the card.
  `betlab import-page-taps` copies the old page's marks and typed prices into the owner's rows. It's
  insert-only, and the daily run repeats it until the page is retired. The owner id is
  `app.owner_user_id` in settings.yaml.
- **Phase 4: Build is live (Oct 2).** `/build` ports the old page's builder: one slip per sport, pricing from
  the leg packs' simulated draws (`web/lib/builder.ts`, checked against a Python recomputation), the grade
  against FanDuel's usual payout share, Save & track into `custom_parlays`, Mark, Open in FanDuel, and the
  record by grade. The daily run now also runs `sync-personal` after the page copy, so the web app's marks
  and saved parlays reach the ledgers and get graded.
- **Phase 4: More is live (Oct 2).** Model, Markets, Reviews, Learn, Plan and Settings under `/more`. The to-do
  list and reviews moved from the page into the database (`betlab import-page-db` copied 86 to-dos and 2 reviews;
  `betlab todo` and `betlab review` write them now); the page's To-do tab points to the app. Settings saves
  bankroll, unit and fun bucket in `user_settings` and the theme in a cookie. Real-money marking and
  the settings integration are built (see below).
- **Real-money marking is built (Oct 2, live on Oct 18).** From Oct 18 ET, Mark becomes "I placed this · 1u" (Mike:
  default 1 unit): a `real` bet at 1 unit in dollars (Settings) and the price shown; Edit fixes the stake or the price
  FanDuel gave. My bets keeps real money and paper apart (record, P/L in dollars, today's risk against the 5u cap), and
  Home and My bets read the fun bucket from Settings. Stakes are dollars everywhere (the ledgers' convention).
- **Oct 2 fix:** `publish.merge_games` folds a game stored under its odds event id into its league id when
  the preview arrives (the unique `odds_event_id` broke that morning's publish).
- **Personal-record correction (Oct 2):** My bets computes CLV at the user's recorded price,
  using raw prop CLV and the closing push chance, and scales missing-price winnings by stake.
  Migration 0004 is applied to Supabase; it must precede deploying the new publisher. Older integer football lines with
  a different personal price lack closing push data and are excluded from personal CLV averages.
  The original paper prices and shared CLV are preserved. Regression checks: `npm test` from `web/`,
  Python grading/publishing tests, and the database's My bets isolation tests.
- **Oct 6: CUTOVER DONE.** Mike pasted the 4 keys and deleted `BETLAB_SHADOW`; the worker cloned the repo
  (19:20 UTC) and its first live pregame pushed as betlab-bot (282c10a). A queued `refresh_free` + `reprice`
  ran every step (CFBD refresh ok; the odds pulls skipped, already done today, so the Odds API keys were
  first used by the next pregame pull), exposed the git-sync conflict bug (fixed 4fc859b), and the
  `preview` step was killed (exit -9, out of memory), then ran past the 25-minute limit: fixed the same
  day (column-projected play-by-play, no nflreadpy RAM cache, weather breaker, math threads capped at 2);
  a queued reprice then passed every step, preview 24 s. Mike moved Railway to Hobby (8 vCPU / 8 GB). The 7 tick/page-sync routines are disabled, daily.yml's fallback cron is
  removed (every workflow is manual, kept for rollback). Claude's tools may not change Railway variables:
  Mike does those.
- **Oct 4: cutover prepared, waiting on Mike's keys (Mike: retire the old page, worker first).**
  - Worker code: `gitsync.py` clones the repo onto the Railway volume `worker-volume` (`/data`;
    `BETLAB_REPO_DIR=/data/repo`, `BETLAB_DATA_DIR`, `BETLAB_EXPORTS_DIR` set) and pushes each job's
    `data/` and `exports/` to **main** as betlab-bot, not a `data-live` branch: the same as the Actions
    runs, so rollback needs no merge. No job runs without the ledger. Git is the backup (no separate
    Storage backup). With `GITHUB_TOKEN` set the clone runs even in shadow mode, to prove it.
  - The old claude.ai page retires at the cutover: no page-taps bridge, no page-sync routine.
  - New schedule on the worker (docs/DECISIONS.md, "the new schedule"): `daily` 9:55 AM and `pregame`
    every 15 minutes, 5:30 AM to 11:45 PM since Nov 9 (was 6:30: winter's 12:30 CET kickoffs are 6:30 ET) (pregame.py, news.py); since Oct 21 also `overnight` at 3 AM (sync-personal, refresh, grade, publish). Pick alerts (`betlab alert`, migration 0005 applied; live Oct 9: VAPID keys on Railway, Mike's iPhone
    subscribed and got the test alert after migration 0006). Real-money marking rehearsed Oct 9 in the preview.
  - **Switch steps, once Mike has pasted GITHUB_TOKEN, ODDS_API_KEY, ODDS_API_KEY_PAID and
    CFBD_API_KEY into the worker's variables:** confirm the shadow clone in the worker log (runs
    table, job `worker`, step `git clone`); remove `schedule:` from daily/evening/reprice/nba.yml
    (keep `workflow_dispatch` for rollback); disable the tick routines (daily, Sunday 1 PM, Sunday
    late, Saturday, reprice, evening) and the page-sync routine, keeping `tick.yml` for one-time
    ticks; delete `BETLAB_SHADOW`; post a "moved to the app" note on the old page; watch the first
    jobs in `runs` and the first betlab-bot commit. Switch between runs, not during an evening check.
  - Railway CLI from Git Bash: `export MSYS_NO_PATHCONV=1` first, or `/data` turns into a Windows path.
- **Next (as of Mon Oct 12, 2026, 8 PM ET; the live list is More > Plan):**
  1. DraftKings links: switch the buttons to whatever Mike's iPhone test opens (More > Settings > Test Open in
     DraftKings, Oct 13), and add DraftKings to the game page's "FanDuel vs. the sharp book" table.
  2. Real money from Sun Oct 18: "I placed this" activates per account (`user_settings.real_from`); check the first
     real marks end to end on Oct 19.
  3. NBA opening night (Oct 20) on the worker: the morning listing, pregame pulls, game pages and fun slates.
  - Done since this list was written: the home-screen install and Refresh (Oct 2), the worker cutover (Oct 6),
    pick and lock alerts (Oct 9-10), a second account with Google sign-in (Oct 10-12), DraftKings (Oct 12).
- **Later (Mike, Oct 1):** rethink the schedule itself. The worker copies today's times exactly
  (`SCHEDULE` in `worker.py`), so the cutover changes nothing.
- **Railway:**
  - project `betlab` (<railway-id>), environment production
    (<railway-id>)
  - service `betlab` = the web app (<railway-id>): root `/web`, deploys
    only on `/web/**` changes
  - service `worker` (<railway-id>): `Dockerfile.worker`, deploys only on
    `src/`, `config/`, `scripts/`, `pyproject.toml` and migrations changes
  - `railway environment edit` silently does nothing; use `railway api` (serviceInstanceUpdate)

## The new structure (information architecture)

There are four main places. Everything else sits under **More**. On a phone this is a bottom
tab bar; on desktop, a top bar.

```
Home      Games      Build      My bets      More (Model · Markets · Reviews · Learn · Plan · Settings)
```

### 1. Home: "what's worth doing now"
- **Day switcher** (Today · Tomorrow · This week) plus sport chips (All · NFL · College football
  · NHL · NBA · Soccer). Sport is only a filter.
- **Picks first**, when any qualify: big rows with the bet, price, EV, Open in FanDuel and Mark.
- **Then a time-sorted feed of games**, one row per game: start time, sport, matchup, line. Under
  that, the game's one or two best actionable items: a lean, the top parlay with its fair price,
  "3 overs". A badge flags anything that needs checking (goalie not confirmed, QB change,
  injuries). Tapping a row opens the game page.
- **Strip at the top:** your open bets (count, today's result) and the fun bucket ($3 of $10).
- **Cross-game tickets** (SGP+ and the anytime-TD ticket) show as one row in the feed at their
  window's first start time ("Sunday early games · SGP+ fair +1240").
- No explanations on Home. Each row has at most one "Why" link, which opens the game page or a
  detail sheet.

### 2. Games: the schedule, and a page per game
- **Games list:** every game by day, with sport chips and a team search. Same row design as Home.
- **Game page** (`/games/[league]/[gameId]`), top to bottom:
  1. Header: teams, start time, line and total, status badges.
  2. **Bets:** picks and leans on this game (compact rows).
  3. **Parlays:** this game's SGPs (compact tickets), its overs to root for, and "Add to builder"
     on any leg.
  4. **Lines and props:** FanDuel vs the sharp price, model vs market tables (top rows, then "All").
  5. Folded analysis: how the game goes · tale of the tape and matchups · who's hurt ·
     weather · special teams (NHL) · data notes. Each has "About these numbers".
- The same component serves every sport. Only the analysis sections differ by league.

### 3. Build: your own parlay
- Today's builder, full screen: pick legs from any upcoming game (game picker plus search), a
  slip with chance, fair odds, how the legs work together, the grade, the FanDuel price box,
  Open in FanDuel, and Save & track.
- **Your saved parlays** with their grades and results, plus the "record by grade" table.

### 4. My bets (personal, per user)
- **Open:** marked or placed picks, leans and parlays, with live status.
- **Settled:** results and CLV.
- **Your record:** units, ROI and CLV by market, plus the fun-bucket month.
- **Prices you typed:** FanDuel quotes.
- After Oct 18 this is where real stakes go. Bankroll and unit size live in Settings.

### More
- **Model:** the strengths and weak-spots scorecard, the paper record (shared: it grades the
  model), the CLV chart, by-market tables, and the research reads (college early read, NFL
  script lean, matchup notes, NHL reads, TD read).
- **Markets:** the coverage table (`docs/COVERAGE.md`).
- **Reviews:** the Tuesday weekly reviews.
- **Learn:** Betting 101 and its calculators (ported as is).
- **Plan:** the shared to-do list (you and Claude).
- **Settings:** bankroll and unit, sign-in, notifications (later), theme.

### Design rules (from `docs/ROADMAP.md`, Oct 1)
- **Focus:** the focus is the bet and one-tap actions. Analysis is one tap away (folded section,
  "Why", detail sheet), never inline by default.
- **Bets:** one stats line per bet, no paragraphs on cards, no grids of stat boxes.
- **Layout:** phone first (bottom tab bar, 44 px tap targets); dense but calm; no empty space
  from uneven columns.
- **Names:** one name per thing everywhere: NFL, College football, NHL, NBA, College basketball,
  Soccer; DraftKings; Moneyline / Spread / Total / Player prop. Titles say when ("Sunday early
  games"), not which sport.
- **Look:** a fresh identity. Calm neutrals with one accent; green and red only for win/loss and
  EV; a mono face for odds; dark mode first-class. The design plan goes into the app's theme
  tokens.

## Architecture

```
Railway worker (Python, volume /data) ──publish──▶ Supabase Postgres ◀── Next.js web app (Railway)
  runs the unchanged betlab jobs on a schedule        shared tables (server-written)     reads/writes directly,
  sync-personal ◀── Mike's bets, quotes, parlays ──── personal tables (user_id + RLS)   RLS on personal rows
  nightly data/ backup to Supabase Storage; commits ledgers to a data-live branch
```

- **The CSV ledgers stay the source of truth for now; Postgres is the app's read model.**
  Grading, CLV, the scorecard and the fun ledger all run on pandas CSVs, so rewriting them all
  at once is too risky. Later, ledgers move to the database one at a time (picks and leans
  first, then fun).
- **No FastAPI in v1.** The web reads Supabase directly, and builder pricing already runs in the
  browser. On-demand actions ("refresh now", "sync my bets") go into a `job_requests` table that
  the worker polls, with an allow-list, the credit guard and a cooldown. There's no public
  server port.
- **One worker process** (`src/betlab/worker.py`): APScheduler on Eastern time, one global lock,
  and the job lists copied step for step from `daily.yml`, `evening.yml`, `reprice.yml` and
  `nba.yml`. Each step runs `betlab ...` as its own process, so one failing step can't stop the
  scheduler. Free sources (ESPN, the NHL API) can refresh every few minutes. `config.py` reads
  `BETLAB_DATA_DIR` and `BETLAB_EXPORTS_DIR` from the environment, and the volume mounts at
  `/data`.
- **The proof of when picks were made is kept two ways.** In Postgres, a trigger makes a paper
  pick's time, price and line unchangeable. In git, the worker commits `data/ledger/*.csv` and
  `exports/` to a `data-live` branch after each job.
- **A `runs` table** (job, step, timing, exit code, end of the log, credits used) replaces the
  GitHub Actions screens. A failed or missing run shows in the app.

## Database schema v1 (`supabase/migrations/0001_init.sql`)

**Game key:** `game_id = '{league}:{native id}'`, for example `nfl:2026_04_PIT_CLE`,
`ncaaf:401858237`, `nhl:<gamePk>`, `soccer:<odds event_id>`. The Odds API `event_id` is a
separate, nullable unique column, because previews exist before odds do.

**Shared tables.** Signed-in users can read; only the worker's service key writes.

| Table | Holds | Comes from |
|---|---|---|
| `games` | league, season, week, teams, start time, state, scores | previews, NHL view, odds pulls |
| `offers` | today's card. `tier` is pick, lean or check; prices, chances, EV, units, why, FanDuel link; `active` | `card.json` and `card_leans` (id = `ledger.pick_id()`) |
| `paper_picks` | the shared paper record (picks and leans), immutable once logged | `picks.csv`, `leans.csv` |
| `fun_tickets` | generated SGPs, SGP+, TD tickets and overs as `jsonb`, plus grading | `fun.json`, `fun_games`, `fun.csv` |
| `leg_packs` | the builder's simulated-draw packs as `jsonb` | `fun_legs` |
| `game_analysis` | (`game_id`, kind) holding `jsonb`: each game's preview or NHL/NBA analysis | `previews*.json`, `nhl.json` |
| `docs` | (collection, id) holding `jsonb`: scorecard, results, fun results, coverage, meta, track records | the rest of `export-page` |
| `runs` | job runs (see above) | worker |

**Personal tables.** Every row carries `user_id`. RLS:
`using (user_id = auth.uid()) with check (user_id = auth.uid())`.
- `bets`: marked or placed picks, leans and parlays (replaces `taken` and `fun_taken`).
- `quotes`: FanDuel prices typed in (replaces `fun_quotes`).
- `custom_parlays`: saved builder parlays with their grade.
- `user_settings`: bankroll, unit, fun bucket, book, notifications.
- `todos` and `reviews`: imported once from the page.
- `job_requests`.
- The `my_bets` view (`security_invoker`) gives each user their own record.

## Build phases (about 8–9 sessions of backend work and 6–8 of web work; done when each phase's checks pass)

**Phase 1: Database and publish (Actions still in charge)**
- Write the Supabase schema, RLS and the immutability trigger.
- Refactor `cmd_export_page` (`src/betlab/cli.py` ~763) into `build_docs()`, which yields every
  document once (keeping the `links.attach_*` calls, `split_fun`, `pack_docs` and
  `golive.current_rule`). Two outputs use it: the existing file writer, so the claude.ai page
  keeps working, and a new `src/betlab/publish.py`, which upserts the tables in one transaction.
- Add `betlab publish` after `export-page` in the four workflows, marked soft so it can't break a
  run. Mike pastes `SUPABASE_DB_URL` into GitHub secrets.
- `betlab sync-personal`: refactor `cmd_import_taken` into `ledger.apply_taken()` and reuse
  `fun_ledger.sync()`. It reads the owner's `bets`, `quotes` and `custom_parlays` with the
  service key (`OWNER_USER_ID`) and writes them into the CSV ledgers. It replaces the
  `claude/page-sync` branch round trip.
- `scripts/import_page_db.py` copies todos and reviews into the database once.

**Phase 2: Web app MVP** (`web/` in the same repo; Next.js App Router, TypeScript; one service on
Railway)
- Design tokens and the app shell: bottom tabs on phone, top bar on desktop, dark and light.
- Sign-in by email link (Supabase Auth). Public sign-up is off.
- **Home:** day switcher, sport chips, picks, the game feed, cross-game tickets, open-bets strip.
- **Game page:** all sections. Ported from today's page JS: `fdHref`/`ny_link` links, the
  compact ticket and row components, the analysis renderers.
- Mark as mine, Undo, and price quotes write to `bets` and `quotes`.

**Phase 3: Worker on Railway (shadow, then primary)**
- `src/betlab/worker.py`, a Dockerfile, the volume seeded once from main, the `runs` table,
  `job_requests` polling, the nightly `data/` backup to Storage (keeping 14 days), and the
  `data-live` commits (Mike pastes a GitHub token limited to this repo into Railway).
- **Shadow (3–4 days):** no Odds API keys. It logs when each job would fire, compared against the
  tick routines.
- **Switch, once Home and marking work on the web:** turn off the GitHub cron and the tick
  routines, copy the latest `data/` to the volume, Mike pastes the Odds API and CFBD keys into
  Railway, and shadow mode ends. The claude.ai page stays up for a week fed from `data-live`;
  compare the `docs` table against the files daily.
- **Rollback:** set `WORKER_ENABLED=0`, restore the workflow crons and re-enable the tick routines
  (the worker pushes to main, so there's nothing to merge), then `sync-personal --to-json` and
  `import-taken`.

**Phase 4: The rest of the web app**
- Build (the builder plus saved parlays), My bets, and More (Model, Markets, Reviews, Learn
  calculators, Plan, Settings).
- A "refresh now" button through `job_requests`.
- Make it installable as a home-screen app (iOS notifications later).

**Phase 5: Retire the old path**
- Remove the page-sync routine, `tick.yml`, the `claude/page-sync` branch and the cron triggers.
- Keep the workflows as manual runs only.
- Update `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md` and `docs/ROADMAP.md`.

The iPhone app (SwiftUI) came after this, on the same database: built Oct 14 on the Mac (`ios/`), every tab the web app
has plus pick alerts through Apple (APNs), installed through TestFlight (`ios/README.md`).

## What Mike does (Claude never touches keys)
1. **Now:** sign up for Railway and Supabase (the `u-railway-supabase` to-do).
2. **Phase 1:** paste the Supabase database URL into GitHub secrets, and confirm the sign-in
   email.
3. **Phase 3:** paste the Supabase, Odds API, CFBD and GitHub keys into Railway's variables.

## Verification

**Tests** (in `tests/`):
- `test_build_docs.py`: a golden test that the refactor writes byte-identical page files.
- `test_publish.py`: publishing twice gives the same row counts, and offers dropped from the
  card become inactive.
- `test_sync_personal.py`: gives the same result as today's `import-taken` and `import-fun`.
- `test_worker_schedule.py`: next run times in Eastern time across the Nov 1 change from daylight
  to standard time, job lists that match the workflow YAML, and the lock blocking overlapping
  runs.
- An RLS test against a local Supabase (`supabase start`): user B sees none of user A's rows and
  can't write shared tables. A trigger test that a paper pick's price can't change.

**Web, using the browser preview** (`.claude/launch.json` gets a `web` dev-server entry):
- Home, a game page per sport and Build at phone (375 px) and desktop widths, in dark and light.
- No console errors and no sideways scrolling.
- Marking a bet shows up in My bets, and `sync-personal` writes it to `picks.csv`.

**Parity:** for a week after the switch, the web and the claude.ai page show the same card,
parlays and scorecard each day, and every scheduled run appears in `runs` with exit code 0.
