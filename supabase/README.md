# supabase/

The app's database (Supabase Postgres), per `docs/APP_PLAN.md`.

| Path | What it is |
|---|---|
| `migrations/0038_slip_prices.sql` | A slip's fair chance when it was read (Nov 4): your own rows. Apart from `bets.fair_price` and `custom_parlays` on purpose: `fun_ledger.quote_model` learns from those, so writing there would change the promo finder's model with no backtest. |
| `migrations/0037_sessions.sql` | Signed-in devices (Nov 4): `my_sessions()` and `end_sessions(session)`, your own sessions from `auth.sessions`, as the owner but limited to the caller; never the session you're on. An ended device is out within the hour, when its access token runs out. |
| `migrations/0036_search.sql` | Search (Nov 4): `search_app(q)`, games from the calendar, fights and players from the leg packs, as the signed-in user; your bets and teams are searched in the apps. |
| `migrations/0045_watching.sql` | Watched games (Nov 7): `user_settings.watching`, the game ids an account will watch. A watched game's own slips (every slice's `sgps`, published as `fun_tickets` kind `sgp` with their slate) join Today when the slice locks, and the lock alert names them (`alerts.watched_slips`). |
| `migrations/0046_bet_games_backfill.sql` | A one-time data fix (Nov 9): Build slips marked before Nov 1 get their games copied from `custom_parlays` onto `bets.games`, so friends' trackers (who can't read another account's `custom_parlays`) see each leg's game. Touches only bets with no games; safe to run again. |
| `migrations/0044_pickem.sql` | FanDuel's College Football Pick'em (Nov 7): `pickem`, one row per game of the week's entry (FanDuel's short names, the frozen home line, your pick, BetLab's side and its chance, the final), and `pickem_weeks` (the partners' best score and what it paid, by hand); your own rows. Adds `pickem` to the job list. Applied Nov 7 through the connector. |
| `migrations/0043_books_off.sql` | Books on and off (Nov 6): `user_settings.books_off` (any of FanDuel, DraftKings, Novig; never all three) and `offers.books` (every book's own read of a card bet from `books.per_book`: line, price, EV, the tier it earns alone, units, link), so each account sees a bet at its best book on (`atBooks`, three ports) or not at all |
| `migrations/0042_reactions.sql` | Reactions (Nov 6): `bet_reactions`, one per friend per bet (fire, money, sweat, skull, pray, goat). Only an accepted friend's shared bet takes one, never your own (`can_react`, the same rule as `friend_bets`); you read your own rows, and everyone's on a bet you can see through `bet_reactions_for` (your bets and friends' bets; a reactor's name only when you're friends, else null). A change pulses the owner, the reactor and the owner's friends. The worker's minute loop alerts the owner (`reactions.py`) |
| `migrations/0035_schedule.sql` | The calendar (Nov 4): `schedule_games`, every game ESPN lists for the next 10 weeks, read once a day (`calendar_sync.py`), and `calendar_days`, its counts per Eastern day and sport. Shared, read-only; kept apart from `games`. |
| `migrations/0034_bet_history.sql` | The bet change log (Nov 4): `bet_history`, a trigger on `bets` keeps every insert, edit and delete with the row before and after and who did it (null: the worker). Owner reads; nobody writes through the API. Starts Nov 4: nothing before it. |
| `migrations/0033_live_pulse.sql` | Live updates (Nov 4): `app_pulse` (no data, only "this changed at": the row `card`, stamped by each publish, and one `u:<user>` per account, stamped by triggers on bets, promos, ladders, challenges and friendships, a bet also stamping accepted friends'). Signed-in users read the shared row and their own; the apps listen through Supabase Realtime. A failed pulse never blocks the write that caused it. |
| `migrations/0029_promos.sql` | Promos (Oct 30): `promos` (the wallet: each bonus bet or boost with its terms and expiry; your own rows; a bet that takes one marks it used, deleting that bet gives it back: `promo_used` trigger), `bets.boost_cap` (a boost's max extra winnings, units), `bets.promo_id` (the token; the foreign key on (promo_id, user_id) keeps it your own), `bets.lock_id` (a lock's two bets), `bets.promo_ev` (the finder's expected dollars), `user_settings.unit_dollars`; `my_bets` and `friend_bets` recreated |
| `migrations/0032_alerts_held.sql` | `alerts_held` (Nov 2): alerts waiting out an account's quiet hours; the worker only. Documents `user_settings.notify`'s new keys |
| `migrations/0031_bet_reset.sql` | `bets.reset` and `promos.from_bet` (Nov 1): a bet reset; `issue_resets()` puts a lost bet's stake in the wallet as a bonus bet (worker, `resets.py`) and takes back an unused one when the grade changes; `my_bets` recreated to carry it |
| `migrations/0030_promo_teams.sql` | `promos.teams` (Oct 31): a token for some games only, the teams it names; the finder searches only games with one of them on a side (`teamFits`) |
| `migrations/0028_bet_clv.sql` | Live CLV on open bets (Oct 28): `bet_clv` (each open bet's current sharp chance and CLV, written by the worker at every publish; your own rows, read-only) |
| `migrations/0027_challenges.sql` | Novig challenges (Oct 28): `challenges` (your own rows: the day, Novig's words, the parsed rules, open/ready/done/skipped, the worker's `pick` and `best`), and `challenges` in `job_requests`' allow-list |
| `migrations/0025_live_activities.sql` | Live Activities (Oct 27): `live_activity_tokens` (an iPhone's push-to-start token, kind 'start', or one activity's update token for its bet, kind 'update'; your own rows only; kept apart from `push_subscriptions` so alerts never go to them) and `live_activity_state` (the worker's record of what it started and last sent; the service only) |
| `migrations/0024_social.sql` | Friends (Oct 27): `profiles` (a name and unique @handle; you see your own and the people you're connected to), `friendships` (a request, pending until the one invited accepts through `accept_friend`; either side ends it; one per pair), `user_settings.share_bets` (on by default), `find_person` (an exact @handle or email only: no browsing) and `friend_bets` (accepted friends' shared bets through `my_bets`, so results match My bets; units, never money). The definer functions are the only way across accounts; the bets table stays fenced |
| `migrations/0023_bet_protect.sql` | `bets.protect`: FanDuel Bet Protect+ on a bet (Oct 26): its 3% fee comes off P/L (not on a void) and a protected slip's did-not-play leg counts as won; `my_bets` recreated to carry it |
| `migrations/0022_ladder_book.sql` | A ladder's one book (`ladders.book`, FanDuel by default, Oct 26): every step is suggested, locked and priced there |
| `migrations/0021_ladder_lock.sql` | A ladder's chosen game (`game_id`), turned-down offers (`skipped`), the step the worker locked (`locked`, `locked_at`) and why it waits on the owner (`notice`), Oct 26 |
| `migrations/0020_ladders.sql` | Ladder challenges (Oct 26): `ladders` (each user's start, target, active or stopped; RLS) and `bets.ladder_id` (a step is one of the user's bets; the foreign key on (ladder_id, user_id) keeps it to their own ladder); `my_bets` recreated to carry it |
| `migrations/0011_apns_devices.sql` | The iPhone app's alerts: a `push_subscriptions` row can be an Apple device (`apns:<sandbox|production>:<token>`, no Web Push keys) |
| `migrations/0005_push_alerts.sql` | Pick alerts: `push_subscriptions` (one row per device, personal, RLS) and `alerts_sent` (which picks were announced; the worker only) |
| `migrations/0004_personal_clv.sql` | Preserves closing push probability and appends original price/push fields to the user-isolated My bets view for personal CLV |
| `migrations/0003_my_bets.sql` | My bets: a user's own parlays are graded in `custom_parlays` (never in the shared `fun_tickets`), and `my_bets` adds the result whichever table graded it, plus league, market, EV and close |
| `migrations/0002_tighten_grants.sql` | Takes back TRUNCATE/REFERENCES/TRIGGER that Supabase grants anon and signed-in users by default (TRUNCATE skips row-level security); anon gets nothing |
| `migrations/0001_init.sql` | Schema v1: shared tables (games, offers, paper_picks, fun_tickets, leg_packs, game_analysis, docs, runs), personal tables (bets, quotes, custom_parlays, user_settings, todos, reviews, job_requests), row-level security and the `my_bets` view |
| `tests/rls.test.mjs` | Database tests on a real Postgres (PGlite, in process): the migration loads, each user sees only their own rows, friends see each other's shared bets only after an accepted request, signed-in users can read but never write shared tables, signed-out visitors see nothing, paper picks can't change or be deleted |
| `tests/serve.mjs` | A throwaway local database with the schema, for trying `betlab publish` and `sync-personal` |
| `tests/auth_stub.sql` | The bits of Supabase the schema relies on (`auth.users`, `auth.uid()`, the `authenticated` and `anon` roles) for plain Postgres |

## How data moves

- **`betlab publish`** (`src/betlab/publish.py`) runs after `export-page` in every cloud job.
  It writes the same products the page shows, in one transaction:
  - Card lines and fun tickets that drop off become `active = false`.
  - Builder packs are replaced.
  - Paper picks only ever take new grading (a trigger refuses changes to time, price, line or
    label).
  - It skips quietly while `SUPABASE_DB_URL` isn't set.
- **`betlab sync-personal`** reads the owner's bets, typed prices and saved parlays
  (`OWNER_USER_ID`). It writes them into `picks.csv`, `leans.csv` and `fun.csv`, the same way
  the page's taps did. `--to-json DIR` writes the lists instead, for a rollback.
- **The CSV ledgers stay the source of truth.** These tables are the app's read model.

**Game ids** are `'{league}:{native id}'`, for example `nfl:2026_04_PIT_CLE`,
`ncaaf:401862791` and `nhl:2026020011`. A card line or ticket finds its game by the odds event
id (linked through the NFL fun games), or else by league, start time within two hours, and both
teams. Otherwise it gets its own game, keyed by the odds event id: `ncaaf:<event id>` for an FCS
opponent with no preview, for example.

## Apply migrations

`betlab db-migrate` applies new files in `migrations/` in order, each in its own transaction, and records
them in `betlab_meta.migrations` (a schema the app's API never exposes). 0001 was run by hand in the
SQL editor on Oct 1 and recorded with `--already 0001_init.sql`; 0002 was applied by `db-migrate`.

## Run the tests

```
cd supabase/tests && npm install && npm test
```

## Try a publish locally

1. Start the local database:
   ```
   cd supabase/tests && node serve.mjs 54329
   ```
2. In another shell, from `betlab/`, point publish at it. The local test server takes any
   password.
   ```
   SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54329/postgres?sslmode=disable betlab publish
   ```

Connections use `prepare_threshold=None` because Supabase's connection pooler (and the local
server) can't keep prepared statements between connections.

## Going live (Mike)

Project settings, chosen Oct 1:
- **Enable Data API:** on.
- **Automatically expose new tables:** off. The migration grants every table explicitly, and
  signed-out visitors get nothing.
- **Enable automatic RLS:** on, as a safety net for future tables.
- **Postgres type:** default Postgres.

1. Create the Supabase project.
2. Run `migrations/0001_init.sql` in its SQL editor.
3. Paste the database connection string (Settings → Database, the pooler URL) into the GitHub
   secret `SUPABASE_DB_URL`.

The next cloud run fills the tables. Claude never handles the keys.
