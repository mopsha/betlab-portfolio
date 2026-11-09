# The overhaul (started Nov 4, 2026)

The approved plan for BetLab's reorganization and UI overhaul, and Mike's picks as they come in. Mockups:
https://claude.ai/artifact/6KfxDETA4a5bnC4KWS7jMV (private to Mike).

## Picks so far

- **Nov 4: structure A.** Tabs become Today · Live · Build · Games · Me. Live joins open bets and the wall; Build holds
  the builder, slip check and promo finder; Me replaces More; Search sits in every header.
- **Nov 4: the look.** Mike found the first mockups "clean but monotonous" and a painted-color second try bad; the
  third pass is approved ("looks awesome"). Its rules: cards without outlines on a darker page; big numbers lead (the
  day's units on Today, the score on a live bet); team color as a soft glow behind a score, never a painted band; each
  leg is a ring that fills toward its target; section titles are real headings; a floating tab bar.
- **Nov 4: pictures everywhere (Mike: "logos instead of CHI or NYK, think of a smarter way to do everything like
  that").** Anything that names a team, player, league or book shows its own art, from the sources the apps already
  load (`web/lib/art.ts`, `headshots.ts`, `soccer-clubs.ts`; iPhone `LogoStore`, `Players`): a team's logo beside its
  score and on game cards, a player's photo inside his leg's ring with the current number as a badge, a stack of small
  logos and photos on a parlay, the league's logo in a sport chip. One building block does it in each app (an
  `Art` view taking a team, player or league) with a team-color monogram only as the fallback when no art loads.
- **Still open:** the name (BetLab stays until Mike says otherwise). The desktop pages and the building-block sheet
  are still drawn in the first look.

## Status (Nov 4, late)

**Built, both apps, the night of Nov 4** (TestFlight 1739; the website deployed from `main`):

- **Tabs:** Today, Live, Build, Games, Me. Paths and tab values are unchanged (`/bets`, `/more`; `bets`, `more`).
- **Today:** the day's units as the hero, then one card per game with your bets on it (Mike, Nov 4: "it shouldn't have
  two cards for the same game"; a bet across games has its own card), the pick card, parlays as a sideways row with
  the lock countdown, the games feed with logos.
- **Live:** Open and Settled only (the web adds a Wall tab; the iPhone a wall button). A bet is a glow card: logos,
  big score, clock pill, ring legs with photos.
- **Me:** the units-won hero and chart, tiles (Promos, Ladder, Friends, Record and stats), a BetLab group, Settings
  with one Alerts section, and Extras (Learn, Wrapped, Prices, Novig challenges, Markets). Record, Stats, Ladder and
  Prices are their own screens (iPhone `Me/BetScreens.swift`; web `/more/record|stats|ladder|prices`, old
  `/bets?tab=` links redirect).
- **Game page:** logo hero with glows, a win-chance bar where the data has one (NHL, soccer on the iPhone; NHL, UFC on
  the web), your bet, bets on the game, analysis folds.
- **Build:** modes Build · Check a slip · Use a promo, logo game strip, price buttons, photo prop rows, floating slip bar.
- **Web desktop (from 1000px):** side navigation, Today with live bets in a right column, two-column game page,
  Build's slip pinned from 1180px.
- **Kits:** iPhone `Design/Kit.swift`, `KitLive.swift`, `KitMe.swift`; web `components/ui/` (`Art`, `Ring`, `Kit`,
  `Chart`) with `app/look.css`, `kit.css`, `screens.css`.
- **Previews:** `python scripts/sample_fixture.py` builds the web fixture with no database.

**Added Nov 4, later the same night (Mike: "rework friends, promos and ladder, make Ask BetLab look better"):**

- **Friends:** a feed. Your profile and units on top with Add a friend, requests as cards, friends as a row of avatars
  with today's bet count, each friend's bet drawn as Live draws one with Tail as its button; the friend profile leads
  with units won. iPhone `Friends/FriendsView.swift`, `FriendProfileView.swift`, `Design/KitSocial.swift`; web
  `app/friends`, `components/friends`, `app/social.css`.
- **Ask BetLab:** your messages as bubbles, answers as text under a small mark, games in answers as cards with logos,
  suggestion chips when empty, a floating input, a typing indicator, copy. iPhone `Me/ChatView.swift`,
  `ChatCards.swift`; web `components/me/Chat.tsx`, `components/chat/Answer.tsx` (`/chat?sample=1` shows a made-up
  conversation in fixture mode only).
- **Promos:** each promo is a token card (book, kind, value big, countdown, limits as chips, Use it); the finder is
  three steps (Your token, Where, Rank by) with results built like the pick card and a lock as two linked cards.
  iPhone `Promos/WalletView.swift`, `FinderView.swift`, `Design/KitWallet.swift` (`Promos.swift` and
  `PromoFinder.swift` now hold only the rules); web `components/promos/Token.tsx`, `PromoWallet.tsx`,
  `PromoFinder.tsx`, `lib/wallet-view.ts`, `app/wallet.css`.
- **Ladder:** the stack and target as the hero with a rung track, the current step as the main card, the climb as a
  timeline, past ladders folded. iPhone `Me/LadderView.swift`; web `components/me/Ladder.tsx` (fixture mode shows two
  invented ladders from `components/ladder/sample.ts` when there are none).
- Not seen on screen: a real chat answer; a two-book lock in the finder; a ladder step that is holding or in play on
  the web; the iPhone's finder, add and edit sheets, friend profile and ladder start; themes other than light on the
  iPhone and Device dark and light on the web.

**Build and Me reorganized, Nov 4, last (Mike: "all the right functionality exists, it can just be organized sooooo
much better"; drawn first: the V4 boards on the mockup canvas):**

- **Build is three layers, then content.** Header (a book menu, saved parlays, a search icon), the modes, the sport
  chips and game strip, then one row of market tabs: Popular (main lines and the top props), Lines, one per stat, Ideas
  (the themed slips). The promo lives in the slip. The slip shows the price at each of the three books with the best
  marked. iPhone `Build/BuildView.swift`, `BuildMarkets.swift`, `BuildIdeas.swift`, `BuildSlip.swift`,
  `Design/KitBuild.swift`; web `components/build/` (`Builder`, `BookMenu`, `Markets`, `SlipPanel`, `PromoChoice`),
  `lib/build-view.ts`, `app/build.css`, saved parlays at `/build/saved`.
- **Behaviour that changed with it (both apps):** a typed price is kept per book (an unsaved single price from before is
  dropped once); Novig's exact price is asked for whenever every leg is on Novig, after a short wait; "I placed this"
  saves the parlay and marks it in one step; Popular's props are a new pick (one leg per player near a 65% chance; the
  two apps' rules differ slightly). **The apps differ on one thing:** the iPhone's "I placed this" goes to the best book
  (a wallet promo pins its book); the web's goes to the chosen book and says which book pays more.
- **Me is about you, in one order.** Header and gear; your number with Week / Month / All beside it (they change the
  number: the last 7 and 30 days by game day); four stats in one row (record, return, vs close, streak); Your betting
  (Promos, Ladder, one Record and stats place with a Record / Stats / Prices switch); Badges; Friends; BetLab (Ask
  BetLab, How the model is doing, Reviews and plan); Extras as chips (Learn, Wrapped, Novig challenges, Prices,
  Calendar; Markets is inside the model screen on the iPhone and a chip on the web). Search left Me. iPhone
  `Me/MoreView.swift`, `MeNumbers.swift`, `RecordHub.swift`, `SettingsView.swift`, `MarketsView.swift`,
  `ReviewsView.swift`, `Design/KitProfile.swift`; web `app/more/page.tsx`, `components/me/MeNumbers.tsx`,
  `MeBadges.tsx`, `MeFriends.tsx`, `RecordSwitch.tsx`, `lib/me-view.ts`, `app/me.css`.
- Not seen on screen: typing a price, the promo chooser, Ideas, search and the stat tabs on the iPhone's Build; a sport
  with a main-lines card on the iPhone; a live Novig quote on the web; the Record and stats switch and badges sheet on
  the iPhone; themes other than light on the iPhone and Device dark on the web.

**Closed Nov 6** (both apps unless marked):

- **Themes:** every theme opened on screen: the iPhone's 22 (Live, Me, a game page) and the web's 21 (game page, Me, Live).
  One fault, in every iPhone theme: the game page's chance numbers were cut at the row's edge (fixed). Lemon's yellow accent
  on white cards is low-contrast (left as Mike's theme).
- **Bet names:** a parlay is named by who's in it ("Fagnano, Lawrence and 2 more +940"; one player: "Anthony Black, 2 legs";
  no names: "4-leg parlay"), one rule in three ports (web `betName`, iPhone `Stats.betName`, worker `leg_alerts.parlay_name`)
  on `tests/fixtures/bet_names.json`.
- **iPhone:** Me counts a live-settled bet at once (a quiet tracker never recorded settles before); the game page's "Your
  bet" shows its legs as rings; Today's hero no longer shows through the header when scrolled (`HardTopEdge`).
- **iPhone demo mode:** `-demo <fixture>` reads every table from a web preview fixture, signs in as no one and writes
  nothing (`Core/Demo.swift`). Use it for every simulator check; `-demoActivity YES` with it starts a sample Live Activity.
- **Search:** rows lead with a logo, a photo or a game's two logos; the web's field is the kit's.
- **Web calendar:** its day dots were gray blobs over the next week (class names shared with bet cards and leg dots).
- **Web Today:** "N open bets" counts the tracker's settles, like Live.
- **Live Activity:** a dark card with each team's color as a glow, legs as small rings, the full name. The widgets lead with
  the day's units in the hero size (the widgets themselves not seen on screen).
- **Previews:** the service worker caches nothing on localhost (dev file names aren't hashed), so a style change shows.

**Still open:**

- One tokens file for both apps; splitting `data.ts`, `actions.ts`, the rest of `globals.css` and `BuildView.swift` (pure
  moves, nothing visible).
- `TicketCard` (Today's parlay cards) restyled by the base look only: no ticket was built in the fixture when checked, so it
  wasn't seen. Stats and Model read fine in the new look; the wall's tiles were redone with Live.
- The widgets: logos need the app to share pictures with them (LogoStore does it for the Live Activity only).
- Motion and haptics beyond what existed; the name (BetLab stays unless Mike says otherwise).

## Next session

How to pick it up: work in the main checkout (the `betlab-overhaul` worktree is retired; it has nothing unpushed). Web
preview: `python scripts/sample_fixture.py`, then the `web-sample` preview entry; sample bets go in the fixture's `my_bets`.
iPhone: `xcrun simctl launch booted com.mopsha.betlab -demo <fixture path> [-tab more] [-openGame <game_id>]
[-appearance <theme>]`. Look at a render before showing Mike anything: the one mockup published unseen was the one he
rejected.

## Why

BetLab grew feature by feature for six weeks. It works, but Mike finds things hard to find, screens too busy,
the look inconsistent and a bit plain. The map of both apps confirms it:

- **Navigation:** More grew from 6 planned rows to 14 (ordered differently in each app). My bets holds 6 segments;
  Record alone has 6 sections. Promos live in four places, with two different "Use a promo" pages on the web (one is
  dead code on the iPhone). The wall is reachable only from Home's hub on game days. Search, Calendar, Wrapped each
  have 2-3 entry points; alert settings are split over three sections.
- **Look:** neither app has shared building blocks. Web: one 98 KB `globals.css`, 15 corner radii, ~28 font sizes,
  ~30 card variants, six ways to draw a bet, four ways to draw a game. iPhone: chips rewritten in 8 places,
  `themedCard` used twice, radii 4-28, five screens ignore the chosen theme.
- **Code:** `web/components` (48 files), `web/lib` (55) and `ios/BetLab` (63) are flat; `data.ts`, `actions.ts`,
  `BuildView.swift`, `MoreView.swift` are dumping grounds.

**Mike's answers:** scope is everything (navigation, visuals, code layout, trimming). He opens the app to see today's
picks, follow live bets, and build or check a slip. Refine the current feel rather than start over; references are
FanDuel/DraftKings, Apple Sports and Robinhood; polish is my call. Both apps move together; the website gets a real
desktop layout. Keep all 22 themes, rebuilt on tokens. Rarely used (tuck into Extras, don't delete): Markets, Learn,
My bets › Prices, paper-bet sections, Wrapped, Novig challenges. Nothing's layout is sacred. Open to a rename.
Delivery: mockups first, then phases, each one usable.

His Oct 1 design rules still stand and guide every screen: the bets are the focus; one stats line per bet; analysis
always findable, never inline; dense but calm; units, never money; one name per thing.

## Phase 0: Mockups (nothing in the apps changes)

One private mockup page (an Artifact Mike can open on his phone), drawn with real sample data read from Supabase:

1. **Two tab structures**, side by side:
   - **A (my recommendation): Today · Live · Build · Games · Me.** Live = open bets and the wall as one screen.
     Build = builder, slip check ("Is my parlay +EV?"), promo finder. Me = record, stats, ladder, promos wallet,
     friends, model, settings, Extras. No More tab; Search in every header; Ask BetLab as a button on Today.
   - **B: Home · Games · Build · My bets · More**, regrouped: My bets down to Open / Settled / Record; More in four
     short groups (You, Promos, BetLab, Settings).
2. **Key screens in the refined look**, phone and desktop: Today, Live, a game page, Build with its slip, Me,
   Settings. Two polish levels to choose from (quieter / bolder): bigger headline numbers, team color, charts for
   record and CLV, motion notes.
3. **Desktop layout:** side navigation; Today with live bets in a right column; Build with the slip pinned beside
   the markets; game page in two columns.
4. **The building blocks** on one sheet: card, bet row, game row, chip, pill, button, section header, sheet, fold,
   empty state, in three themes (light, dark, one colored).
5. **Extras group** contents, and 3-4 name and logo ideas beside "keep BetLab".

Mike picks; his picks are written into this plan's later phases and `docs/DECISIONS.md` before any build.

## Phase 1: Foundation (almost no visible change)

**1a. Preview without Mike's account** (needed to check every later phase safely):
- Web: commit a scrubbed sample fixture (`web/fixtures/sample.json`) so `npm run dev:fixture` works on the Mac;
  fix `.claude/launch.json` and the README to match.
- iPhone: a `-demo` launch argument that feeds `SupabaseClient.rows` from a bundled sample (same data), bypassing
  sign-in, never writing. Simulator checks stop touching Mike's real account.

**1b. Code layout, as pure moves (no behavior change, one commit per area):**
- `ios/BetLab/` into folders: `App`, `Design`, `Today`, `Live`, `Build`, `Games`, `Me`, `Promos`, `Friends`,
  `Core` (store, client, models, math). The project uses synchronized folders, so no project-file edits.
  Split `BuildView.swift` (13 views), `MoreView.swift` (More + Markets + Reviews + Settings).
- `web/components/` into the same feature folders plus `ui/`; `web/lib/data.ts` and `actions.ts` split by feature
  behind the same exports; `globals.css` split into `tokens.css`, `themes.css` and one file per area.

**1c. Design tokens and building blocks:**
- One token file, `design/tokens.json` (spacing scale, type scale, 3 radii, elevation, motion timings, the 22
  themes as accent + page + card), read by both apps, with a test in each that the port matches it (the same
  pattern as `tests/fixtures/*.json`). `web/lib/looks.ts` and `ios/BetLab/Theme.swift` become readers of it.
- Web `components/ui/`: Card, Button, Chip, Pill, Tag, SectionHeader, PageHeader (with one history-aware back
  link, from `BackLink`), Sheet (from `Cards.tsx`'s dialog), Fold, EmptyState, StatTable.
- iPhone `Design/`: the same set as SwiftUI views and modifiers, built on `themedCard` / `themedRows`; `TagView`,
  `bareRow`, `StatTable`, `LiveDot`, `CountingText` move in.
- One **BetRow** and one **GameRow** family per app (sizes: compact, card, live) replacing the six and four
  current variants; `BetCardView`/`BetCard`, `GameCardRow`/`GameCard`, `Scoreboard`/`Board` are the bases.

## Phase 2: Navigation (the visible reorganization)

- New tabs per Mike's pick: web `components/Nav.tsx` (`TABS`), iPhone `BetLabApp.swift` (`SignedInView`).
- Me / regrouped More: web `app/more/page.tsx` (`PLACES`), iPhone `MoreView`. Same order in both apps.
- One home each: promos (wallet + finder; delete the old `/promo` page and the unreachable `PromoFormView`),
  alert settings (one section), Search (header icon everywhere), Calendar (inside Games), the wall (inside Live).
- Extras group: Markets, Learn, Prices, Wrapped, Novig challenges, paper record. Screens and the worker's jobs
  stay as they are.
- Old web paths redirect to the new ones; push alerts, widgets, Live Activity taps, Siri and `-tab` / `-openGame`
  arguments keep landing in the right place (check each).

## Phase 3: Screens, one per step, both apps each time

Order follows Mike's three jobs. Each screen is rebuilt from the Phase 1 blocks to its approved mockup:

1. **Today** (web `app/page.tsx`, `lib/data.ts homeData`; iPhone `HomeView`, `Feed`, `GameDay`): picks and locks
   first, one live strip, then the feed; the nine stacked blocks become three.
2. **Live** (`LiveBets.tsx`, `Wall.tsx`, `app/bets`; `LiveViews`, `MyBetsView`, `WallView`): open bets and the wall
   merged; settled behind one tap.
3. **Build** (`Builder.tsx`, `PromoFinder.tsx`, `SlipUpload.tsx`; `BuildView`, `PromoFinder`, `Slip`): builder,
   slip check and promo finder as three modes of one screen; saved parlays one tap away.
4. **Game page** (`Analysis.tsx`; `GameView`, `Analysis`): bets up top, analysis as tidy folds; split the
   per-sport analysis files.
5. **Me** (`StatsView`, `RecordTable`, `Ladder`, `Friends`, `PromoWallet`; iPhone equivalents): a profile header
   with the record and a units chart, then rows into each area.
6. **Settings and the rest** (Model, Reviews, Plan, Calendar, Search, Chat, Friends, login): restyled on the
   blocks; the five iPhone screens that ignore themes fixed here.

Logic files (`live.ts`, `builder.ts`, `promos.ts`, their Swift and Python ports, shared fixtures) are not changed
by the redesign; only views move.

## Phase 4: Desktop website

Side navigation from ~1000 px and the multi-column layouts approved in Phase 0 (Today + live column, Build + pinned
slip, two-column game page, Me as a dashboard). Phone width stays the iPhone's twin.

## Phase 5: Polish, widgets, name

- Motion and haptics from the token timings: number roll-ups, leg-hit and bet-won moments, sheet and tab
  transitions (respecting Reduce Motion); charts for record, CLV and units.
- Widgets and the Live Activity restyled from the same tokens (move the token reader into `ios/Shared/`).
- Rename and new icon, only if Mike picked one in Phase 0 (text and assets; the sign-in sender was set up for this).
- Docs: `CLAUDE.md` (app description, task table paths), `web/README.md`, `ios/README.md`, `docs/APP_PLAN.md`
  (structure and design rules), `docs/DECISIONS.md`, `docs/IDEAS.md`.

## Working rules for every phase

- Before starting: commit the unrelated work now sitting uncommitted in the tree (wind watch, archive) on its own.
- Each step lands in both apps in one session, pulled, tested and pushed; web-only and iOS-only pushes don't
  redeploy the worker, and nothing in `src/` changes except where a phase says so.
- No change to pick rules, models, the ledger, New York rules or any shared logic fixture.
- TestFlight build after each visible phase; Mike reacts on his phone before the next one starts.

## Verification (each phase)

- `cd web && npx tsc --noEmit -p . && npm test && npx next build`; `.venv/bin/python -m pytest`;
  `xcodebuild ... test` (`ios/README.md`).
- Web: the fixture preview (`web-fixture` in `.claude/launch.json`) at phone and desktop widths, light, dark and
  two colored themes; console clean; screenshots sent to Mike.
- iPhone: simulator in `-demo` mode, every changed screen opened (tests alone missed the Nov 4 calendar crash),
  in three themes, screenshots sent to Mike.
- New token tests: both ports equal `design/tokens.json`; a web test that no stylesheet outside `tokens.css` /
  `themes.css` hard-codes a color, radius or font size.
- After Phase 2: tap a real pick alert, lock alert, widget and Live Activity on the TestFlight build to confirm
  each opens the right screen.
