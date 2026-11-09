# web/

**Folders (Nov 4, `docs/OVERHAUL.md`):** `components/` is grouped by feature: `app` (nav, pulse), `ui` (shared pieces), `today`, `live`, `build`, `games`, `promos`, `friends`, `me`. Import components as `@/components/<folder>/<Name>`.

## The overhaul's look (Nov 4, `docs/OVERHAUL.md`)

The tabs are **Today** (`/`), **Live** (`/bets`), **Build**, **Games**, **Me** (`/more`): a floating tab bar to 999px, a side nav from 1000px (`components/app/Nav.tsx`; the top bar is gone). The sections below still describe each feature; where they say "My bets" read Live, "More" read Me, "Home" read Today.

| Path | What it is |
|---|---|
| `app/globals.css`, `look.css`, `kit.css`, `screens.css` | Loaded in that order. `look.css`: the base look (tokens for Device/Dark, borderless cards, the floating tab bar). `kit.css`: the shared pieces. `screens.css`: the rebuilt screens and the desktop layout. New rules go in the last two; a rebuilt screen's old rules leave `globals.css` (the builder's, the wall's and the sub-pages' are still there). Only team colors and white-on-color text are hard-coded; everything else is a token, so all the themes work |
| `components/ui/Art.tsx` | `Art` (a team's logo, a player's photo or a league's logo, with a team-color monogram only as the fallback) and `ArtStack`. League logos: `lib/league-art.ts`. Whose picture goes beside a pick or parlay: `lib/pictures.ts` (server: `lib/art.ts` for teams, `lib/headshots.ts` for players; never holds a page more than 2.5 s) |
| `components/ui/Ring.tsx`, `Kit.tsx`, `Chart.tsx` | `Ring` (a leg's progress around its picture, the number as a badge); `Glow` (a card with team color as a soft light), `LivePill`, `SectionTitle`, `StatCells`, `ScreenHead` / `IconLink` (a main screen's header: round icon buttons, Search last), `SubHead` (a sub-page's header on the one `BackLink`); `Spark` and `AreaChart` |
| `app/page.tsx` | **Today:** the date, the day's units as the hero with what's still in play and a trend line (a calm line when there are no bets today), the live cards (`components/today/LiveCards.tsx`: logos, big score, clock pill, the bet and its legs as rings; they replace the game-day hub), picks (`BetRow`, with the team's logo or player's photo), parlays as cards you swipe (`ParlayShelf`; a tap opens the full `TicketCard` below) with the next lock's countdown beside the heading, then the games feed with logos. Refresh is a header icon; the promo line, open bets, fun bucket and priced time sit under the hero. `homeData`'s rules are unchanged. From 1000px the live cards are a right-hand column |
| `app/bets/page.tsx`, `app/bets/load.ts` | **Live:** Open, Settled and Wall, units in play at the right. Each bet is `components/live/BetCard.tsx`: a glow card (one game: two logos, big score, clock pill; several: a picture stack and each game as a line), name, book · stake · boost, price, "wins N.Nu", then ring legs with their status lines (`LiveBets.tsx`: `BigBoard`, `LiveTop`, `LiveBet`, `Leg`, `legRing`). A parlay across games with more than 4 legs, and every settled bet, folds its legs behind its dots. `/wall` still works. `load.ts` is the one loader Live and the pages below share |
| `app/more/record`, `stats`, `ladder`, `prices` | Record, Stats, Ladder and Prices, out of My bets and under Me (same content and components); `/bets?view=record\|stats\|ladder\|prices` (or `?tab=`) redirects to them |
| `app/more/page.tsx`, `app/more/extras` | **Me:** the account, units won with the record and the close and units over time (week, month, all), tiles (Promos, Ladder, Friends, Record and stats), BetLab's pages (Ask BetLab, Model and markets, Reviews and Plan for the owner, Search, Calendar), Stats, Settings and **Extras** (Learn, Wrapped, Prices, Novig challenges, Markets). `/promo` redirects to `/build/promo`: the wallet with the finder is the one promos home. Settings has one Alerts section; the two book test pages are at its bottom |
| `app/games/[league]/[id]/page.tsx` | **A game's page:** `components/games/GameHero.tsx` (large logos, big score or start time, clock pill, two glows, a chance-to-win bar where the page has one: the NHL's market or model, a UFC fight's price), Your bet (`GameBets.tsx`, your open bets' legs on this game as rings), Bets on this game, then Analysis as folds in one card; two columns from 1000px |
| `app/build/page.tsx`, `app/build/check`, `app/build/promo`, `components/build/BuildModes.tsx` | **Build:** three modes (Build · Check a slip, the slip reader · Use a promo). The builder's game strip, board and slip show logos (`art` prop), prop rows show player photos (`/api/faces`, ESPN's search cached a day), price buttons select with the accent's tint and ring, and the slip is a floating accent bar with a picture stack; the slip pins beside the markets from 1180px |
| Previews | `fixtures/today.json` has no bets. For Live, Today's live cards and Me, make a hand-made `fixtures/sample-bets.json` (git-ignored; invented bets shaped like `MyBet` on today's real games, merged with today.json) and serve it: `node scripts/dev-fixture.mjs <port> fixtures/sample-bets.json real`. The service worker caches styles in a preview: unregister it and clear `caches` when a CSS change doesn't show |

The BetLab web app (Phase 2 of `docs/APP_PLAN.md`): Next.js 16 (App Router, TypeScript) on
Supabase. Next.js 16 renamed middleware to `proxy.ts` and made page `params` promises. Read
`node_modules/next/dist/docs/` before using an API you haven't used in this version.

| Path | What it is |
|---|---|
| `app/page.tsx` | **Home:** a day switcher, sport chips, picks first, then games and cross-game tickets by start time. Only things you can act on: no leans (Oct 22: they stay on each game's page and Games) and no check-the-news flags. On today's view with an open bet or a lock still to come, the **game-day hub** (Oct 24, `components/today/GameDay.tsx`) heads it: your open bets live in compact cards, countdowns to today's next locks, and the way to the wall |
| `app/wall/page.tsx` | **The wall** (Oct 24, Mike's W7): every game you have money on, one tile each with its score and your legs on it, for a laptop or TV (`components/live/Wall.tsx`, `lib/gameday.ts` `wallTiles`); the same `/api/live` poll as My bets. Drag a tile by its ⠿ grip (or arrow keys on it) to arrange them; the order is saved per account (`user_settings.wall_order`, `lib/order.ts`, Oct 25) and tiles you haven't placed follow live-first |
| `app/chat/page.tsx`, `app/api/chat/route.ts` | **Ask BetLab** (Oct 24, Mike's W22): chat with Claude (`claude-sonnet-5-5` at low effort, server-side refusal fallback on) over the signed-in account's data through four read-only tools in `lib/chat.ts`: open bets with live legs, today's board, one game's offers and analysis, the record. Needs `ANTHROPIC_API_KEY` on the web service (until then the page says it's waiting); the conversation stays in the browser session. Linked from More |
| `app/bets/add/page.tsx`, `app/api/slip/route.ts` | **Add a bet from a screenshot** (Oct 24): Claude Haiku (`claude-haiku-5-5`) reads the slip into a strict JSON shape (`lib/slip-read.ts`), `lib/slip.ts` matches each leg to the app's game and builds the grader's game ref (NFL id, `ncaaf:`/`nhl:` id, `nba\|HOME\|AWAY\|tip`, `<league>\|Home\|Away\|kickoff`; UFC legs keep their matchup only), you confirm or fix it, and `addSlipBet` saves a real custom bet. Units from your unit size ($5 default, kept in the browser). Needs ANTHROPIC_API_KEY. "+ Add" in My bets' header. **Price check** (Oct 27): each matched leg gets its own FanDuel/DraftKings price from its game's Build pack (`withPrices`, upcoming games only), and a draft whose odds are over 1.5x the legs' prices multiplied is flagged before saving (`priceCheck`; a parlay can't pay much more than that: four Oct 25 slips were misread at 2-4.6x) |
| `app/promo/page.tsx` | **Use a promo** (Oct 24): a boost or bonus bet's terms as the book lists them (percent, game, max wager, max extra winnings, min and max odds) open Build's promo finder on that game (`promoHref`/`promoFromParams` in `lib/builder.ts`). Only games with a leg pack are listed (NFL after the 9:55 AM pull, NBA 15-45 minutes before tip). Linked from More and Build |
| `app/games/page.tsx` | **Games:** every game for the next week, by day |
| `app/games/[league]/[id]/page.tsx` | **A game's page:** bets, parlays, overs to root for, the top lines, then folded analysis. The game id is `league:id` |
| `components/today/TicketCard.tsx` (`DkSide`), `components/build/Builder.tsx` + `lib/builder.ts` (`Pricer` book) | DraftKings' side of every parlay (Oct 12): each leg's DraftKings price (a rung it lacks shows its nearest), the slip's DraftKings legs and likely quote, and a DraftKings price box (saved as `<sgp_id>~dk`, `quotes.book`); the Build tab's FanDuel / DraftKings switch |
| `lib/early.ts` | Game-line leans more than 36 hours before the start get an "Early · unproven" tag in `BetRow` (Mike, Oct 13; docs/DECISIONS.md) |
| `app/more/challenges`, `components/promos/Challenges.tsx`, `app/api/challenges`, `lib/challenge-read.ts`, `lib/challenges.ts` | More › Novig challenges (Oct 28; History: the month's points, placed, 3-for-3 days and the synced straights' results, then each past day, `challengeHistory`): add the screenshot of Novig's Points › Challenges (Claude Haiku copies each challenge's words; saved for today and the worker's job queued); each card shows Waiting, Watching (the best so far), Ready (alerted) or Placed, with Open in Novig, I placed it and Skip |
| `lib/novig.ts`, `app/api/novig` | Novig (Oct 22; parlays Oct 28): on iPhone/iPad "Open in Novig" uses Novig's app scheme (`novigapp://events/...`; novig.com has no universal links); each slip's Novig side (`TicketCard` `NvSide`: its exact price, nothing to type) and "I placed this" at the best of the three prices (`bestBook`); the Build tab's Novig button asks `api/novig` (Novig's parlay pricer, server side for CORS) and fills in the price; Novig grades a void leg at its fair value (`bets.ts` `novigVoidProfit`) |
| `components/me/AlertSettings.tsx` | Settings > Alert settings (Nov 2): writes `user_settings.notify` through `setNotify`; the worker's `alert_prefs.py` reads it |
| `lib/missed.ts` | My bets > Record > Missed bets (Nov 2; shared fixture `tests/fixtures/missed.json`) |
| `lib/draftkings.ts`, `components/ui/BookLink.tsx`, `app/more/settings/draftkings-test` | Open in DraftKings (Oct 12): a bet's button follows its book (`offers.fd_url` holds the link at the offer's own book); the web link opens DraftKings' app with the bet in the betslip (iPhone test, Oct 13); a parlay is one link with the outcome ids joined by `%2B` (round 3); each slip's DraftKings side has its own button. `lib/books.ts`: the book names; each bet stores its book (`bets.book`), editable in Edit |
| `app/login`, `app/auth/callback`, `app/auth/confirm` | Sign-in: Google (always the account picker), email and password, or a 6-digit email code typed back in (works in the home-screen app); `/auth/confirm` takes the email templates' token-hash links in any browser. Sign-ups are off in Supabase. `/auth/status` + `components/app/SignedInWatch.tsx` move the login screen on once a sign-in finished in the Google sheet over the iPhone home-screen app (Oct 12) |
| `app/friends/page.tsx`, `app/friends/[handle]/page.tsx`, `lib/social.ts`, `components/friends/Friends.tsx`, `components/friends/FriendsUi.tsx`, `components/live/BetCard.tsx` | **Friends** (Oct 27, Mike: "a social feed where you see your friends' entered bets and their profile"; W16's tail button): More › Friends is the feed (accepted friends' bets, newest first, as My bets' own card with the live tracker: `BetCard`, shared with My bets, and `/api/live?friends=all`), requests to accept or decline, Add a friend by exact @handle or email, and your name and @handle. A profile (`/friends/<handle>`) has their record in units, open bets, recent bets, badges and player and team cards. **Tail** copies an open bet into your bets at the odds you got and your book (`tailBet`, `lib/social.tailRow`: the same pick or parlay so it grades the same, 1u, never their bonus, boost or ladder), until its game starts (`canTail`; a bet with no known game for 6 hours). Settings › Friends see my bets (`share_bets`). Friends see units, never money. Database: `supabase/migrations/0024_social.sql` |
| `app/wrapped/page.tsx`, `components/me/WrappedStory.tsx`, `lib/wrapped.ts`, `app/api/wrapped/route.tsx` | **Wrapped** (Oct 27, Mike's W17): a month (`?p=2026-10`, the newest by default) or the season as a story you tap through (right side or → next, left or ← back, hold to pause; it moves on every 8 s, never with reduced motion): the month in numbers, the bottom line, biggest hit, the heartbreaker (the longest parlay lost by one leg, and that leg), your player (with headshot), your best book, your betting type (`persona`: Sharp, Parlay Architect, Bonus Hunter, Long-Shot Dreamer, a sport's Loyalist, Straight Shooter, All-Rounder; first that fits on 5+ bets), best day and longest streak, badges earned that month, and a summary whose Share sends `app/api/wrapped` (1080x1350). Counted like My bets (real money, live-settled bets included), so its P/L always matches. In More, and a link at the top of Stats |
| `app/build/promo/page.tsx`, `components/promos/PromoFinder.tsx` | **Use a promo** (Oct 30 rework; `docs/DECISIONS.md` 2026-10-30): pick a token from the wallet or type one, the book, where to look (a kickoff slice, games you pick, one game, today across sports: `lib/promo-finder.ts` `scopeEvents`, `lib/slices.ts`) and how to rank (Max value, Balanced, Safe: `rank`). Every result reads in expected dollars and chance to hit; a lock is a result type. "I placed it" saves the bet at the token's dollars over your unit, with its bonus or boost, the boost's cap, the token's id and the expected dollars (`placePromo`); a lock saves both bets under one `lock_id`, and Undo removes both (`undoPromo`). Build keeps its slip's promo line and links here |
| `app/more/promos/page.tsx`, `components/promos/PromoWallet.tsx` | **Promos** (Oct 30, migration 0029): the wallet of bonus bets and boosts, soonest to expire first (`lib/promos.ts`); Add, From a screenshot (`/api/promos`, `lib/promo-read.ts`: Claude reads the book's promos screen, you check each before saving), Edit, Won't use, Use (the finder). My bets' Promos section and Home's "Expires today" line read it too |
| `app/bets/page.tsx` | **My bets:** Open (with Undo), Settled by day, Record by market (units at your price, CLV), Prices (your own parlays and the FanDuel prices you typed). Math in `lib/bets.ts`. A cash-out (Oct 22, `bets.cashout`, units paid back, typed in Edit) settles a bet at that amount whatever its legs do. A profit boost (`bets.boost`, percent; set when marked from Build's promo mode or in Edit) keeps the book's own price and multiplies a win's profit; the Profit boosts card shows what boosts earned. **Stats** (Oct 24, Mike's #40 and W29): units over time, streaks, best and worst bets, the record by sport, singles vs parlays, price band, cash/boost/bonus, book and weekday (`lib/stats.ts`, through `record()`), and achievements (`lib/achievements.ts`: 89 badges in eight groups since Oct 27, worked out from the bets, never stored; Stats shows the earned ones, Next up (the six closest) and the rest folded by group). Every bet card has **Share** (W13): `app/api/share/[id]` draws it as a 1080x1350 picture (`lib/share.ts`; a parlay lost by one leg says ONE LEG AWAY) for the phone's share sheet. Stats also shows **player and team cards** (W21; trading cards like the iPhone's since Oct 25, `components/games/PlayerCards.tsx`, `components/games/Cards.tsx`, `lib/players.ts`, `lib/cards.ts`): your most-bet players and teams in swipeable rows with sport chips, each with its legs W-L as a ring, recent results, units and a gold/silver/bronze tier, faces from ESPN's search (`lib/headshots.ts` `look`, cached a day). A team's legs are its moneylines and spreads plus its games' totals and both-teams-to-score legs. A tap on a card, on any live leg's headshot or logo, or on a scoreboard's logo opens the card sheet (every leg, by market or stat) from `/api/card` (`CardProvider` in the layout, `CardTap`). The top of My bets is the P/L alone; Grade now and + Add sit in the header's corner |
| `components/me/Ladder.tsx`, `lib/ladder.ts` | **My bets › Ladder** (Oct 26, Mike): a ladder challenge from a start to a target (his first 1u -> 100u), the whole stack on one bet at a time, outside the 5u-a-day rule. The state (stack, open step, climbed or busted) comes from the user's bets carrying the ladder's id (`ladderState`, through `profit()`); The worker (`src/betlab/ladders.py`) holds the day's best step (`suggestStep`: the strongest +EV pick, then lean, -250 to +150, 15+ minutes out, today only, off the ban list), or the chosen game's ("From": every game left today), and locks it once its game's news is in, alerting you; the view shows what it holds and the locked step, and "I placed it" saves it (`ladderStep`), or one of your open bets becomes the step. "Not this one" and the game choice are saved on the ladder (`changeLadder`, migration 0021); stopping a ladder with no steps deletes it. `ladders` table, migration 0020; one fixture with the iPhone, `tests/fixtures/ladder.json`. **Change both together** |
| `app/build/page.tsx` | **Build** (laid out like a sportsbook SGP screen since Oct 22: a strip of game cards, the game's markets as tabs of price buttons from `lib/builder.ts` `boardTabs`, the FanDuel / DraftKings switch at the top, and the slip as a bottom sheet on phones): your own parlay from any upcoming game of one sport (one slip per sport, kept in the browser until saved), priced from each game's simulated draws (`leg_packs`, loaded per game by the `loadPack` action because NFL packs reach 200 KB), graded, saved to `custom_parlays` (Save & track), then Mark and Open in FanDuel. Below: your parlays and the record by grade. Pricing and grade in `lib/builder.ts`. **Promo mode** (Oct 22): No promo / Bonus bet / Profit boost (25-100% or typed), with the token's terms (stake, a boost's max extra winnings, min legs, min odds; `promoFits`). `findPromo` ranks (this game, or the sport's next 16) singles priced off a sharp book at their exact price (the best 3 always show, under their own heading; Oct 22), 2-3 leg same-game slips at a cautious quote (one quote-model miss, ~12%, below the likely one, capped at the best payout share in Mike's quotes and at the legs' product) and 2-4 leg plain parlays (one leg per game, legs priced off a sharp book: `sharpLeg`) at their exact price, to fair +1500 and +2500; legs the book doesn't post and nested legs skipped. "Use" loads one into the slip, which shows the promo value at the typed price, the exact price of a plain parlay, or the likely one, and flags a slip outside the token's terms. **Lock it in** (Oct 22, below the picks): `findLocks` pairs each side with its opposite (`opposite`: the pack's `not`, over/under at one number, opposite rungs, a two-way moneyline) at the other book, both prices really posted and adding to 98-115% implied; `lockValue` sizes the cash hedge so both outcomes pay the same (bonus S(dA-1)(1-1/dB); boost W-(W+S)/dB), shown in dollars beside the best max-EV pick, with links to both books. Singles only |
| `app/more/` | **More:** Model (scorecard, record, CLV chart, by market, the paper record), Markets (coverage table), Reviews, Learn (lessons and calculators in `components/me/Calculators.tsx`), Plan (the shared to-do list, `components/me/PlanList.tsx`), Settings (bankroll, unit, fun bucket, theme and font cookies from `lib/looks.ts`: Device, Light, Dark, Pink, Gold, Purple, Rose; Classic, Modern, Rounded, Sleek; sign out). Game pages' `‹ Back` (`components/ui/BackLink.tsx`) returns to the page you came from, filters and all |
| `components/` | `BetRow`, `TicketCard` / `OverRow`, `PriceBox` (FanDuel price: a live verdict, saved on blur), `MarkButton`, `FdLink`, `GameRow`, `Analysis` (NFL, college and NHL folds), `Nav` / `TabBar` |
| `lib/data.ts` | Every read: the signed-in user's Supabase client, so row-level security applies, or the local fixture |
| `lib/actions.ts` | Server actions: `markBet`, `undoBet`, `saveQuote`, `saveCustom`, `setTodoDone`, `addTodo`, `saveSettings`, `setTheme`, `setFont`, `signOut` (they write as the user) and `loadPack` (one game's builder pack) |
| `lib/real.ts` | Real money from Oct 18 (or the account's own date): `isReal()`, `fmtU()`. From then Mark records a placed bet (mode `real`, 1 unit, the price shown; Edit changes the units or price, `updateBet`). Units only since Oct 12: a stake is units (the Python ledgers multiply profit by it), no bankroll or dollars; My bets shows real money and paper apart, with today's units at risk against the 5u cap and parlay units against the month's |
| `lib/format.ts` | Odds math and one name per sport, market and book |
| `lib/time.ts` | Eastern-time day windows |
| `proxy.ts` | Refreshes the session cookie and sends signed-out visitors to `/login` |

## Run it

- **Real data, with sign-in** (Mike). `.env.local` holds `NEXT_PUBLIC_SUPABASE_URL` and
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` and is never committed.
  ```
  npm install
  npm run dev
  ```
  Then open http://localhost:3000.
- **Local preview without sign-in** (Claude, and the launch entry `betlab-web-preview` on port 3001):
  1. `python scripts/dump_web_fixture.py` (from `betlab/`) writes `web/fixtures/today.json`, a
     snapshot of the shared tables. It's git-ignored and holds no one's bets.
  2. `npm run dev:fixture` serves the app from that snapshot. Marks live in memory until the
     server stops.

  On the Mac (no `SUPABASE_DB_URL`), `python scripts/sample_fixture.py` builds the same file from the repo's exports
  instead, and the launch entry `web-sample` serves it on port 3011. Sample bets go in the fixture's `my_bets` (made-up
  rows, never Mike's), search answers in `search_app`. The service worker caches nothing on localhost, so a style change
  shows on reload (Nov 6).

  `fixtureMode()` can never be on in a production build.
- **Try real-money marking early:** launch entry `betlab-web-real` (port 3003) serves `fixtures/mine.json` with
  `NEXT_PUBLIC_BETLAB_PREVIEW_REAL=1`, which a production build ignores. Stop the other preview first (one `.next` folder).
- **Preview with the owner's bets** (for My bets): `python scripts/dump_web_fixture.py --mine` writes
  `web/fixtures/mine.json` (git-ignored), and the launch entry `betlab-web-mine` serves it on port 3002.

## Record validation

`npm test` checks personal profit and CLV using the actual pure TypeScript modules;
`npm run typecheck` and `npm run build` check the app. My bets uses your recorded
price for CLV, with raw prop CLV and the closing push adjustment. Migration
`0004_personal_clv.sql` exposes the logged price and closing push chance.
Older integer football lines with a different personal price have no personal
CLV until that closing push chance is available; missing values are excluded
from averages. Winnings without a personal price scale the logged per-unit
profit by your stake.

## Home-screen install and refresh

More includes installation help (Safari's Share > Add to Home Screen on iPhone,
or a native install button when the browser offers one). `app/manifest.ts`,
`public/icon.svg`, and `public/icons/` provide standalone app metadata and icons.
The root `InstallProvider` captures browser install prompts across navigation.
This is an online app: no offline odds cache. The only service worker (`public/sw.js`) shows pick alerts.
Manifest, icon and `sw.js` requests bypass the login redirect; betting data still requires sign-in.

Home's Refresh now queues the existing `reprice` job through the user's Supabase
client and RLS. `lib/refresh.ts` reads the latest worker startup and the user's
latest request, selecting status fields only. `lib/refresh-actions.ts` refuses
to enqueue in shadow mode, unknown mode, or a local preview, reuses pending
requests, and limits requests to one per 30 minutes. The worker also enforces
its global cooldown, lock, allow-list and paid-credit guard. Startup mode does
not prove the worker is currently online; queued requests wait for its poller.

My bets' Grade now (Oct 14) is the same control (`RefreshControl job="grade"`): it queues the
worker's `grade` job (grade, export-page, publish; free) instead of waiting for the 9:55 AM run.
The server action accepts only the jobs in `lib/jobs.ts` `APP_JOBS`; a new one also needs
`worker.REQUESTABLE` and the `job_requests` check (migration), which `tests/test_worker_requestable.py` checks.
`components/app/RefreshControl.tsx` polls pending requests every five seconds while
the tab is visible and reloads the Home data on completion. The priced time
remains the indicator of data freshness. No migration or worker cutover is needed.

`npm test` includes refresh-state and server-action regression checks.

## Pick alerts

Settings > Pick alerts (`components/me/PickAlerts.tsx`) subscribes this device to Web Push with
`NEXT_PUBLIC_VAPID_PUBLIC_KEY` (set on the web service; baked in at build, so it redeploys) and saves
the subscription in `push_subscriptions` through the user's RLS (`lib/push-actions.ts`). Saving also
queues a `test_alert` job, so the worker sends a confirmation to new devices. On iPhone, alerts need
BetLab opened from the home screen (iOS 16.4+). The worker's `betlab alert` sends every new pick
after each card (`src/betlab/alerts.py`); the service worker shows it and opens BetLab on tap.

## Design tokens

The tokens are at the top of `app/globals.css`:
- calm cool neutrals, one cobalt accent, and green and red only for results and EV
- dark mode in all three theme states, and the four color themes
- fonts: Archivo (condensed, for names and scores), Public Sans (text), JetBrains Mono (every
  price)
- phone first, with a bottom tab bar; a top bar from 760px

The rules are Mike's (`docs/ROADMAP.md`): the bet and one-tap actions up front, all analysis
one tap away.

## Live tracker (My bets, Oct 23)

Open bets whose games are on today (or ran past midnight) get a live card in the style of FanDuel's and DraftKings'
open bets: a score strip per game (LIVE dot, clock), a segment per parlay leg, and each leg with a status circle and a
progress bar to its target ("45 / 60 rec yds"). `/api/live` (`lib/live-bets.ts`) reads the signed-in user's open bets,
splits each into games (saved parlays' `games`, fun tickets' bodies, single picks), finds each game on ESPN's free
scoreboard by its teams (or fighters), reads that game's box score, and judges every leg (`lib/live.ts`: an over is won
the moment it's hit, an under lost the moment it's passed; a soccer draw loses a "to win" leg; a pushed line is void).
ESPN is fetched server-side through a 15-second cache (a copy answers only while young enough for both who saved it and who asks, so the Games list's 6-hour boards can't freeze a tracker); the page polls every 20 s while a game is live (or about to
start), every 5 minutes otherwise, and not while the tab is hidden. ESPN doesn't push, so a socket would only move the
same polling to the server (Server-Sent Events would be the upgrade if it's ever worth it). Preview: the
`web-fixture-live` launch config with a gitignored `fixtures/live-test.json` of open bets on today's games.

Since c453bb61: a bet whose live state is settled (any lost leg; or every leg won outright, a voided leg waiting for
the grader's reduced price) moves to Settled at once, labeled "lost live · not graded yet" and counted in the record
(`liveSettled`, `markLiveSettled`); the page re-renders when one settles while you watch. Settled bets (the 40 most
recent) get the same tracker from their own game days (`/api/live?view=settled`; finished games cached 6 hours).

## The look, from the iPhone (Oct 24)

`lib/art.ts` finds each of our games on ESPN's scoreboard for its logos, colors and live score (soccer games search every
league's board, and a club the boards miss comes from ESPN's team directories through `lib/soccer-clubs.ts`, a port of
the iPhone's `SoccerClubs` with its alias table). The Games tab draws each game as a `GameCard` in its teams' colors; a game
page and each game in My bets' tracker open with the wall's `Board` (`components/live/LiveBets.tsx`). The book's link is its
app icon (`BookLink icon`, `public/books/`). Themes: the iPhone's 14 extra (`lib/looks.ts`, `globals.css`), their in-between
shades mixed from page, card and accent.
