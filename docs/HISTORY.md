# BetLab history

Dated status notes and retired systems, moved out of `CLAUDE.md` on Oct 25, 2026 when the work became one Mac
session. Nothing here describes how things run today: `CLAUDE.md` does. Decisions and their reasons stay in
`DECISIONS.md`; model changes in `MODEL_CHANGELOG.md`. Add a dated line here only when an orientation note in
`CLAUDE.md` goes stale.

## Status notes, Sep 23 to Oct 25 (as `CLAUDE.md` had them)

BetLab is Mike's (GitHub `mopsha`) personal sports-betting system for **FanDuel in
New York**. It prices FanDuel lines with our models plus the sharp market's no-vig
prices, logs paper picks to a git-committed ledger, grades them with closing line
value (CLV), and publishes everything to a private claude.ai page.

- **Books:** FanDuel and, from Oct 12, **DraftKings** (Mike's second book): game lines, props and parlays are priced at both (Oct 12) and
  each bet goes to the better one (ties to FanDuel); every parlay shows both books
  (`docs/DRAFTKINGS_PLAN.md`). From Oct 22, **Novig** (the CFTC sports exchange) is a third book for game lines only:
  it replaced Bovada in the pulls (same cost), each price carries its bet limit, and one with under $50 behind it
  never wins (`books.py`, DECISIONS Oct 22). With no vig it has the best price on most sides. Its soccer comes from
  Novig's free public catalog (`sources/novig.py`; the Odds API has none); pregame fills pay no fee. Mike's own Novig bets
  enter and settle themselves from his account (`novig_sync.py`, a key Mike set in Railway; every pregame tick and 3 AM).
- **Oct 20 morning:** Mike's to-dos cleared (keeps the $30 Odds API plan); Claude's list consolidated 28 -> 21; fixes:
  cup 3-way closing look, soccer lineup totals need 9 of 11 known starters, ESPN soccer cache gzipped and bad files
  refetched, football-data cached 2 h (the weekend's soccer had gone ungraded; re-graded 10 AM). Tuesday review posted.
- **Oct 21-22 (Thu 11:30 AM ET):** Railway disclosed a breach of stored environment variables (Oct 21; builds paused
  for every plan, Hobby last to return). Mike deleted the worker's old GitHub token and made a new fine-grained one, not
  yet in Railway, so the worker's `git pull`/`push` failed (exit 1) while jobs, publish and alerts ran. **Oct 22, 5:18 PM:**
  Hobby builds returned (5:09 PM); Mike set the new GITHUB_TOKEN and redeployed: the worker runs `bdd1ff56` (3 AM grade,
  NBA early/late slices, mixed-sport grading, Novig, cash-outs), git sync works again and the 39 waiting commits reached
  `main`; the web app is on `bdd1ff56` too. Mike rotated the other Railway keys Oct 23 (below). No misuse found in Supabase,
  Odds API or GitHub logs (Oct 21 evening). Mike's girlfriend uses a second, iCloud account in the iPhone app.
- **Oct 23 (Fri, to 2 PM ET):** Railway keys rotated and verified (database password, Odds API keys, APNs, VAPID; Novig swapped
  to a read-only key, management key revoked; CFBD left as is, Mike's call); the two web-push subscriptions were deleted
  (Mike and Sam use only the iPhone app; Sam's iCloud account has no alert device yet). Novig sync fixed (a
  management key's reads are per-wallet maps): it now reads Mike's cash singles; trade-credit bets and app parlays aren't
  in Novig's API. UFC built end to end for UFC 333 (below; DECISIONS Oct 23). The Mac session is porting Novig, cash-outs,
  boosts and Home's no-leans, then UFC (to-dos). **Start Oct 24 with UFC 333's live check** (`c-ufc-333-sat-oct-24-...`:
  pulls 9:00/11:00/1:00, locks 9:45/11:45/1:45) and the NBA night of Oct 23 (`c-overnight-grade-...`).
- **Start Oct 25 with:** UFC 333's grading and closes (`c-ufc-333-...`), the first real Ask BetLab and + Add uses
  (`c-ask-betlab-...`; chat on Sonnet 5.5, slips on Haiku 5.5, key in Railway since Oct 24 night), NFL Sunday's slices,
  and the Mac's what's-left list (docs/archive/MAC_HANDOFF_2026-10-24.md, top). Leg alerts delivered all evening Oct 24 (runs, job 'live').
- **Oct 24:** leg push alerts live (Mike's #23, `leg_alerts.py`): the worker checks open real bets every minute and pushes a leg
  hit, one leg left, a leg lost or a win to the bettor's devices (reaches the Garmin); off in Settings (web; iOS is the Mac's).
  Game day on the web: Home's hub (open bets live, lock countdowns) and `/wall` (every game you have money on). The tracker
  read "LSU Tigers" at Auburn Tigers as Auburn (shared nickname): sides now go to the better name match (web and worker).
  Ask BetLab (W22): a chat page (More > Ask BetLab) on Claude with read-only tools over your bets, the board and games
  (`web/lib/chat.ts`); it waits for ANTHROPIC_API_KEY on the web service (Mike's to add). My bets > Stats (personal stats and 15 achievements) and a Share button on every bet card (a 1080x1350
  picture, `app/api/share/[id]`). Night: player cards on Stats, Use a promo (`/promo` -> Build's finder on a boost's terms),
  and + Add a bet from a slip screenshot (`/bets/add`, Claude reads it; waits for ANTHROPIC_API_KEY). The iPhone's look came to the web: 21 themes, Games
  cards and game pages in team colors with logos (`lib/art.ts`, every soccer club via `lib/soccer-clubs.ts`), My bets
  cards with team-color scoreboards in the tracker, the book's icon as its button. NBA absences crash fixed (d961b3bc).
- **Oct 23 (afternoon to night):** My bets got a live tracker from ESPN (scores, clocks, every leg live, props as progress
  bars; parlays by game), live settling (a lost leg, or every leg won, moves the bet to Settled before grading),
  folded trackers on Settled, team logos and colors, player headshots, motion and a cash animation (web; the Mac ported
  the tracker and settling, the look-and-feel is its to-do). `docs/IDEAS.md` holds Mike's rated feature list and build
  order (next: leg push alerts). Evening fix: Novig's -99900 placeholder prop prices crashed all NBA props pricing (no NBA
  card or parlays Oct 23 until 7:00 PM; the 4 PM slate was lost); `props_market._two_way` now skips them (dda6b95d).
- **Oct 22 (afternoon to midnight):** Build tab reworked (sportsbook layout) with a bonus/boost finder: singles at their
  exact price, cautious same-game ranking, exact plain parlays, token terms, the two-book lock. Novig is a third book
  (game lines; its soccer from Novig's free public catalog, `sources/novig.py`). My bets: cash-outs (`bets.cashout`),
  boosts (`bets.boost`, the price stays the book's), custom bets get their saved parlay (`publish.MISSING_CUSTOMS`),
  mixed-sport parlays grade leg by leg. Home shows no leans. The iPhone app caught up on Oct 23 (Mac): Novig as a book
  (Open in Novig, "$X available", Novig bets on their own row), cash-outs, boosts, promo singles, Home's no-leans, then UFC (the label and the fight pages) and My bets' live tracker with live settling (settled trackers folded); Oct 24: its logos, headshots, motion and cash animation; then the Oct 24 port (Mac): tracker fixes (teamMatch/sideOf, "Short by", best-named game for all three trackers), Leg alerts switch, My bets Stats and Share, Home's game-day hub and wall, Ask BetLab (via `/api/chat`'s new bearer path). Mike's Novig bets sync from his account
  (`novig_sync.py`, his management key in Railway): the first run failed loading the key (fixed 4e061382), then read
  "0 fills" until Oct 23 11:00 AM (the management key's per-wallet map, fixed dc97ed16): it now reads Mike's two cash
  singles and matches them to his hand entries. Trade-credit bets and app parlays aren't in the API (entered by hand).
  `scripts/novig_read_key.py` makes the read-only key for Mike's swap (to-do). Novig "trade credit"
  wins pay the full return in cash. Lesson from Mike's first Novig bets: soccer edges priced before lineups closed
  5-7% against him; price soccer after the lineups.
- **Where things stand (Tue Oct 20, 2026, 9:30 AM ET):** paper trading ended Sunday Oct 18 (go-live); Mike's real bets
  (Oct 18-19, 10 so far, mostly parlays and bonus bets) are in My bets: about +30u (+2.9u cash, ~+27u from $50 of bonus bets). The worker's volume filled Sat Oct 17 12:00 PM to Sun 12:17 PM (now 5 GB, with a full-disk guard): every
  Saturday slice from 2:30 PM on never locked, and Sunday's 1 PM NFL slice locked late (12:31). Oct 19: NBA opening-night
  prep (each game pulled once 40-45 min before tip on Oct 20-21), and NBA grading reads ESPN until sportsdataverse
  publishes the 2027 files (still 404). Also Oct 19: Mike's first real bets recorded (1-5, +3.32u); bonus bets
  (`bets.bonus`, migration 0012: a loss counts 0); fun slips compare legs by player-stat (no nudged-line repeats); a
  lone NBA game gets its own slips like NFL prime time; soccer has no FanDuel lag (DECISIONS); NFL prop "weak spot" is
  soft-book closes: prop CLV now only from a sharp book at the bet's line (NHL props' edge shrank to
  +0.4%); 2024 prop lines backfilled (9,594 credits) and the over lean, the fun slips' script read and the
  matchup notes turned off (2024 didn't confirm them). Earlier (Oct 13-15): DraftKings links settled, closing looks at open prop bets,
  a scorecard on real closes only, `betlab grade` exits 3 on ungraded lines, cup 3-way closes after the bet, soccer
  Moneyline reads, college basketball's full paid card from the Nov 2 opener.
  Left: the NBA's Oct 20 opening (live check, then Oct 21 grading through the ESPN fallback), Thursday's first NFL slips
  without repeats or the removed reads, Mike's DraftKings quotes and a 3+ leg DraftKings parlay tap, the second account's first marks, what filled the worker volume (by Oct 25), the
  college basketball dry run (by Oct 30).
- **Phase:** paper trading until **2026-10-18**. After that Mike
  bets with real money as he chooses. The app counts units only (Oct 12): no bankroll and
  no unit size in dollars; a real bet is 1u unless edited, 5u a day at most. The go-live checklist is no longer a gate (Mike,
  2026-09-30): it scores each market as a strength or a weak spot, and the job is to
  keep finding and fixing weak spots.
- **UFC (Oct 23):** live from UFC 333 (Sat Oct 24, 10 AM / noon / 2 PM ET), market-only: moneyline and total rounds
  at FanDuel, DraftKings and Novig vs the sharp book, one parlay per card segment (`cards/ufc.py`, `fun_ufc.py`,
  `sources/espn_ufc.py`; DECISIONS Oct 23). Props: none in the feed and no edge found on ESPN's 63 priced fights.
  Also Oct 23: fight pages (`cards/analysis_ufc.py`, `betlab ufc`), a fight model (`models/ufc.py`, tracked, no
  weight: DraftKings beat it 0.642 vs 0.721), same-fight parlay fair prices, the tracker (`tracking_ufc.py`,
  `data/ledger/ufc_lines.csv`), card-change re-pulls (`news._ufc_card`) and voids for cancelled fights.
- **Leagues:** NFL and college football are live. The NHL is live since Sep 30: the Games tab
  view on free data (DraftKings via ESPN, tracked reads), and from Oct 1 a market-only FanDuel
  card plus a nightly SGP+ ticket (`MODELS.md`, "NHL"). Soccer (big five and MLS) is live
  on paper since Sep 25: a market-only 3-way card (our ratings lost to the market); the European cups
  (Champions, Europa, Conference League) join it from Oct 13, props included, graded from ESPN and our own close.
  The NBA (Oct 20, ML-first, `docs/NBA_PLAN.md`; props and a market-only game-lines card), college basketball (Nov 2, the full
  paid FanDuel card from the opener since Oct 15) and WNBA
  (May 2027) are planned; see `docs/ROADMAP.md`.
- **Core finding so far:** closing lines beat our NFL and college ratings models in
  backtests, so picks come mainly from FanDuel prices that lag the sharp books
  (Pinnacle, LowVig). Details: `docs/MODELS.md`.
- **Mike's working style:** Claude builds; Mike reviews and learns the betting math.
  He spends 30+ minutes a day, mostly at a computer, but his PC is rarely on during
  the day, which is why everything scheduled runs in the cloud.

## How it ran before the worker (to Oct 6), and the cutover

0. **On-time starts:** GitHub's cron ran up to 4 hours late, so scheduled Claude routines
   (the "BetLab tick" routines) push an empty commit to `claude/tick`, and `tick.yml`
   starts the named run on `main` within seconds (tested 2026-09-25: under 30 seconds).
   Pre-kickoff checks (`evening.yml`) run Saturday afternoon/evening for college, Sunday
   before the 1 PM and late NFL games, and Thu/Sun/Mon evenings; each fires at both DST
   hours and skips for free when no kickoff is 30–110 minutes away.

1. **10:17 AM ET daily** (GitHub Actions `daily.yml`, plus Sunday 11:47):
   - import the picks Mike marked on the page
   - refresh college data, then grade finished picks
   - pull odds, only for leagues with games in the next 36 hours, once a day
   - price the card and log new paper picks
   - export the page bundle and commit to `main`
   - start the page-sync routine
2. **Thursday, Sunday and Monday about 6:52 PM ET** (`evening.yml`): re-price after NFL
   inactives if a game kicks off in 30–110 minutes, then commit and start the page sync.
3. **Page-sync routine** ("BetLab page sync", a Claude cloud session, no schedule of its
   own):
   - upload `exports/page_sync/*` into the page's database
   - save Mike's "Mark as mine" taps to branch `claude/page-sync`
4. **NBA nights from Oct 20** (`nba.yml`, hourly tick 22:20–02:20 UTC): props for games
   tipping in 15–75 minutes are pulled, priced on the card (paper, market-only) and logged
   to the NBA tracker; the daily run grades them from box scores.
5. **The page** shows the card, results, reviews, lessons and the to-do list.
6. **Since the worker cutover (2026-10-06; docs/DECISIONS.md "the new schedule"):** the Railway worker
   replaces 1–5: the tick and page-sync routines are disabled and the workflows are manual only (rollback). It runs `overnight` at 3 AM ET (grade last night's games, publish;
   problem alerts wait for the daily), `daily` at 9:55 AM ET (grades again, then game lines for every league;
   NFL morning props as data only) and `pregame` every 15 minutes from 6:30 AM to 11:45 PM: each
   game is pulled once, after its sport's news (`schedule.pregame` windows), merged into the latest
   snapshot, then the card, `publish` and pick alerts (`betlab alert`). Each tick also runs a free
   `lock-due` check: fun tickets lock 15 minutes before their kickoff slice starts (`sgp_plus.keep_tickets`), or
   earlier once every game in the slice has had its post-news pull (`pregame.settled_slates`, Oct 12),
   and the lock is rebuilt, published and pushed as a notification even when nothing was pulled. Until the start, free news
   checks (`news.py`: ESPN injuries, NHL goalies, NBA lineups) re-pull a game when its news changes
   (at most twice). In the last tick before a start (1-15 minutes out), a game with an open prop pick or lean logged
   after its last props pull gets one closing look at just those markets (`pregame._closing`), and the feed moving a
   start later by up to 30 minutes keeps the first time seen (`stick_starts`). No midday reprices. The old
   claude.ai page is retired at the cutover. Results commit to `main` as betlab-bot (`gitsync.py`).

## Retired systems' pitfalls

- **Workflow YAML:** a one-line `run:` containing `": "` (a colon and a space) is invalid
  YAML and kills the whole workflow; use a `run: |` block. `tests/test_workflows.py` checks.
- **Routines** can only push `claude/`-prefixed branches, never `main`. Creating a
  routine attaches ALL connectors by default: clear them with
  `clear_mcp_connections: true`.
- **ArtifactData** writes to existing documents need `if_version`.
- **Page documents max out at 256 KiB** of compact JSON. The Fun document hit it on
  Sep 26 and the card (177 leans) on Sep 27; `cmd_export_page` splits Fun per game
  (`fun_games`), the card's leans into `card_leans` chunks and ledger months into chunks,
  and warns above 250 KB. An oversized document is refused by the page sync, so anything
  that can grow with the slate needs splitting.
- **Page form inputs:** in the page's JS, `form.title` is the form's tooltip, not an
  input: read inputs by id.
- **GitHub cron** runs in UTC and has started 2–4 hours late on this repo (Sep 24:
  the 10:17 AM daily began at 2:25 PM ET; both evening checks began after kickoff).
  Time-sensitive runs start from the tick routines instead (see "How it runs"); the
  daily cron stays only as a fallback.

## The Windows PC setup (sessions to Oct 24)

- **One Mac session from Oct 25** (Mike: all work for both apps through one session): web, worker and iPhone change
  together in a session on the Mac (`~/dev/betlab`, venv `.venv/bin/python`, Xcode for `ios/`). Port a
  change to the other app in the same session rather than leaving it as a to-do. The Mac's `.env` has no
  `SUPABASE_DB_URL`, so `betlab todo` and `dump_web_fixture.py` don't run there: read and write `todos` through the
  Supabase connector. The Windows notes below are for the old PC sessions.
- **OS and shells:** Windows 11. PowerShell and Git Bash both work.
- **Python:** the system default is 3.14, but the project venv uses **3.13**
  (`py -3.13 -m venv .venv`); CI uses 3.13 too.
- **Encoding:** polars prints box-drawing characters, so on Windows set
  `PYTHONIOENCODING=utf-8` when printing polars/nflverse frames.
- **Paths:** the repo lives in OneDrive (`Documents/Claude Code/betlab`); GitHub is the
  source of truth.
- **Line endings:** `.gitattributes` normalizes to LF, so git's CRLF warnings are harmless.
- **Scratch files:** exploration scripts go in the session scratchpad, not the repo.

## Key IDs and links, as of Oct 25 (the claude.ai page and the routines are retired)

- **The new app (Oct 1):** web https://betlab.example.app (Railway project `betlab`;
  service and project IDs in `docs/APP_PLAN.md`, Status). Supabase project <supabase-project-ref>. Mike's user id
  00000000-0000-4000-8000-000000000001 (`OWNER_USER_ID`).

- **Page:** https://claude.ai/artifact/6QKwcwXB9a5c3imy692S39 (private to Mike)
- **Repo:** https://github.com/mopsha/betlab (private)
- **Tick routines** (all disabled since the worker cutover, Oct 6; kept for rollback. Push `claude/tick`; Bash only, no connectors):
  daily `trig_01AkZ3v8Xo5RczgfeWDctJi2` (14:17 UTC), Sunday 1 PM games
  `trig_013Fabjc5XtExBzbts9nXcfS` (15:47, 16:47 UTC Sun), Sunday late games
  `trig_01GBqshVPvyLQZTN6rn75YAz` (18:40, 19:40 UTC Sun), Saturday college
  `trig_01EKi5UAhQ2GQBSzcE6PCgDu` (18:07, 19:07, 22:07, 23:07 UTC Sat), reprice
  `trig_01QLky589mYNW5vKFitRr1YE` (17:17 and 20:17 UTC daily), evening
  `trig_018sx3HTag5CddCvdwcMdNC4` (22:52 and 23:52 UTC Thu/Sun/Mon), NBA
  `trig_01RVyt6McaJ7wVsfo2MBrKHH` (20 past the hour, 22:20–02:20 UTC; **created disabled; leave it off:
  the worker prices NBA nights since the Oct 6 cutover**). One-time Saturday run
  check `trig_019AEG7FE9Zq5TP3yuCYTPKN` (2026-09-26 15:30 UTC) writes `todos/c-saturday-check`.
  One-time college basketball week-1 check `trig_01JJtA5n78LWAYatYSYB6Stw` (2026-11-09 16:30 UTC)
  writes `todos/c-ncaab-week1` (reads' CLV by gap, unmatched names, New York skips, credits).
  NBA preseason lineup watch (one-time ticks "tick: lineup-watch" → `nba-reach.yml` watch mode):
  `trig_01Dpb6RbjGKXWKUkpJWneLAo` (2026-10-05 21:00 UTC), `trig_01RKyHEu1SWCusBruhPzhk48`
  (2026-10-06 21:00 UTC); the check `trig_01DHCLN7F8qerDwAa9dMQk6Y` (2026-10-07 14:00 UTC) writes
  `todos/c-lineup-watch`.
- **Page-sync routine:** `trig_01AsDvmu7oHR6WcVyBvNSJLH`
  (https://claude.ai/code/routines/trig_01AsDvmu7oHR6WcVyBvNSJLH), cloud environment
  "Default" `env_01FGmerjeYKGpf7nyYxhYo6o`
- **Repo secrets:** `ODDS_API_KEY`, `CFBD_API_KEY`, `ROUTINE_TOKEN`. Local `.env` holds
  the first two.
