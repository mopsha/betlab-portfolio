# Roadmap

The **live** task list is the app's More > Plan (`betlab todo list`; see `OPERATIONS.md`). This file is the phase
plan behind it. Last updated: Mon Oct 12, 2026, 7:35 PM ET.

| When | Phase | Status |
|---|---|---|
| Sep 23 | Foundations: odds math, Odds API client with credit guard, ledger, NY rules, page with the Learn tab | Done |
| Sep 23 | NFL and college game models with backtests; first cards and a paper pick | Done |
| Sep 23 | Cloud: daily and evening runs, page-sync routine, shared to-do list (replaced by the Railway worker Oct 6) | Done |
| Sep 24 | Documentation everywhere | Done |
| Sep 25 | Soccer ratings backtested on 2018–26 (big five, MLS): no edge vs the market, so soccer goes market-first | Done |
| Sep 25 | College basketball ratings backtested (2021–26): no edge on the close, but they predict the line's move from the opener (+0.38 pts at 3+ disagreement; +0.53 with the Sep 26 roster shift) | Done |
| Sep 25 on | Soccer live on paper: market-only 3-way card (big five and MLS), every line logged | Live |
| Sep 25 on | Every FanDuel main prop line tracked with market, features and result (`data/ledger/prop_lines.csv`): the second test season for the script lean and matchup notes, and the props model's training set | Live |
| Sep 25–Oct 1 | NFL props: snap-count calibration, prop lines, market check; on the card from Week 4 | Done (live on paper) |
| Sep 29–Oct 9 | First graded picks and CLV; weekly reviews (#1 Sep 29, #2 Oct 6) and the first weak-spot review (Oct 9: college moneylines went market-only) | Done; reviews continue each Tuesday |
| Sep 30 on | **NHL** (Mike moved it up): Games tab view on free data, then FanDuel vs the sharp book on the card (Oct 1), an SGP+ ticket per slice, shots overs, props tracked with an ML model (no weight) | Live |
| Oct 1–6 | **BetLab as a real app**: the web app on Railway and Supabase (Home, Games, Build, My bets, More), installable on the iPhone home screen, push alerts, the Railway worker replacing GitHub Actions and the Claude routines (cutover Oct 6). Plan: `docs/APP_PLAN.md`. A native iPhone app (SwiftUI) stays a later option | Done |
| Oct 10 | Soccer props: shots, on target, scorers, assists pulled after lineups and tracked with a shots model (no weight); scorer picks against Pinnacle | Live |
| Oct 10 | A second account (Mike's girlfriend), Google sign-in | Done (sign-in fixed Oct 12) |
| Oct 12 | **DraftKings, the second book** (Mike): all five days built Oct 12 (game lines, props, links, parlays and quotes per book, its settlement rules, results by book); Mike's iPhone link test and DraftKings quotes from Oct 13. Plan: `docs/DRAFTKINGS_PLAN.md` | Built (paper) |
| Oct 13 | **European cups** (Champions, Europa, Conference League) on the soccer card with goals, BTTS and player props, graded from ESPN and our own close (built Oct 12) | Live from Oct 13 |
| Oct 17 | Weak-spot review across every market and both books, before real money (no longer a go-live gate; Mike, Sep 30) | Planned |
| **Sun Oct 18 on** | **Real money** at FanDuel and DraftKings as Mike chooses, counted in units only (1u unless edited, 5u a day at most; no bankroll since Oct 12); "I placed this" activates, and real results feed the weak-spot reviews | Planned |
| Oct 20 | **NBA, ML-first** (Mike, Sep 25): team and player models, props priced after lineups and tracked, a market-only game-lines card, fun tickets per tip time; paper from opening night; the ML layer mid-November. Plan: `docs/NBA_PLAN.md` | Built; opening night Oct 20 |
| Nov 1 | College basketball live on paper with the full paid card from the opener (Mike, Oct 15; was Mar 1; Nov 1 since Oct 26: Villanova @ Notre Dame in Rome): FanDuel and DraftKings vs the sharp book, plus reads where the model disagrees with the line by 3+ points, judged by live CLV | Planned |
| Early Nov | Decide whether to keep the paid odds plan (credits tracked in `runs.credits_used`) | Planned |
| Mid-Nov | **Props ML model v1** (Mike: "eventually a machine learning model"), the NBA ML layer, the soccer ML layer on lineups and rotation; each only with out-of-sample evidence | Planned |
| Feb–Mar 2027 | **MLB build** (Mike, Sep 30): market-first card, every line logged, SGP+ and overs to root for; live on opening day (late March). Plan below | Planned |
| May 2027 | WNBA | Planned |
| Aug 2027 | **NFL fantasy** (Mike, Sep 30): projections and tools for fantasy football from the props models. Plan below | Planned |

## BetLab as a real app (plan, week of Oct 1)

**Replanned Oct 1 (Mike approved): the full plan is `docs/APP_PLAN.md`** (time-first Home,
one page per game, database first, Railway worker). The notes below are the earlier outline.

Mike wants a real product: a redesigned web app and a mobile app, with everything running on
our own server instead of GitHub Actions cron, the Claude page-sync and tick routines (which
use Mike's Claude usage) and the claude.ai page.

- **Backend:** the existing Python package behind a small API (FastAPI), on a cloud host (a
  small VM or a container host: Railway, Render, Fly.io or AWS Lightsail, roughly $5-25 a month).
- **Database:** Postgres (Supabase is a good fit: database, auth and storage in one, and Mike
  already uses it with Expo on WTW) replacing the git-committed CSV ledgers and the page's
  document store. The ledgers' history migrates once; git keeps the code, not the data.
- **Jobs:** a scheduler on the server (APScheduler or cron) runs the pulls, pricing, grading
  and builds on time, more often (goalie confirmations, lineups, closing lines), with no
  GitHub cron delays and no Claude usage. The Odds API budget still sets how often odds are
  pulled; free sources (ESPN, the NHL, nflverse) can refresh every few minutes.
- **Design principle for the web and iPhone apps (Mike, Oct 1): super sleek and streamlined.**
  The focus is the bets themselves: what to bet, the price, the chance, fair odds, and one tap to
  mark it or open it in FanDuel. All the analysis (game reads, matchups, model vs market, injuries,
  the math, backtests, track records) is background systems and explanation: always findable, never
  in the focus.
  - Every screen leads with a short list of actionable items; the reasoning sits one tap away
    (More / Why, a detail sheet on iPhone), never inline by default.
  - One stats line per bet, not a grid of boxes; no paragraphs on cards.
  - Deep analysis gets its own places (a game's detail page, Results, Learn), reached from the
    item it explains, not stacked under it.
  - No empty space from uneven columns; dense but calm, and quick to scan on a phone.
  - Today's page follows this from Oct 1 (compact Fun tickets); the apps start from it.
- **Web app:** a redesign of today's tabs (Today, Games, Fun, Results, Markets, Learn, To-do)
  in React (Next.js), reading the API live, built to the design principle above.
- **Mobile app:** a native iPhone app in Swift (SwiftUI; Mike, Sep 30: iOS only; same design principle), sharing the
  API: the card, the Fun tab's builder with "Open in FanDuel", push notifications (APNs: a pick
  qualifies, a goalie is confirmed, a game starts). Building needs a Mac with Xcode (or a
  cloud Mac); installing on Mike's phone needs an Apple ID (free: 7-day installs; the $99/year
  developer account for TestFlight and push in production).
- **How we'll build the iPhone app (Mike has a Mac, Sep 30):**
  - Claude Code runs on the Mac for the iOS work, so Claude builds with Xcode's tools
    (`xcodebuild`), runs the iPhone simulator and checks screenshots itself. The server and web
    work stay on the Windows PC; both machines share the code through GitHub.
  - From the PC, Mike drives the Mac's Claude session with Remote Control (Mike, Oct 14): the
    session runs on the Mac (repo `~/dev/betlab`) and he follows it from the Claude app on the
    PC; Claude sends simulator screenshots. No Screen Sharing or SSH needed.
  - Mac setup (done Oct 14): Xcode 26.6 (iOS 26.5 SDK and simulator), the Claude desktop app,
    the repo and venv, and Mike's Apple ID in Xcode (a free team). The Mac must be on, awake
    and lid open during iOS sessions.
  - Started Oct 14 (`ios/`): every tab the web app has (Home, Games, Build, My bets, More), no third-party
    packages. Mike's paid developer account is active (Oct 14); installed on his iPhone with pick alerts through Apple (APNs).
  - Installing on his iPhone: free Apple ID (7-day installs from Xcode) to start; the $99/year
    developer account for TestFlight and push notifications.
- **Order:** the database and API first, then the scheduler (retire the routines), then the
  web app, then the iPhone app. Claude keeps building and reviewing; the running system no longer
  needs Claude sessions.
- **Mike's decisions (made Oct 1, `docs/DECISIONS.md`):** Railway (~$5-15 a month), Supabase
  free, no domain yet, just Mike by email link, his own Mac, the Apple developer account later.
- **Separate accounts (planned, not built yet; Mike, Oct 1):** one person's data must never touch
  another's. Built in from the first table:
  - *Shared, no owner:* odds snapshots, games, model outputs, the card's prices, previews, fun
    tickets as generated. Written only by the server.
  - *Personal, `user_id` on every row:* bets marked or placed, typed FanDuel quotes, custom
    parlays, the fun bucket, bankroll and unit settings, to-dos, notification settings.
  - *Enforced by the database, not the app:* Supabase row-level security on every personal
    table (`user_id = auth.uid()`), so a bug in an API route still can't read someone else's
    rows. The server's own jobs use the service key and never act on personal rows without an
    explicit user.
  - *Per-user results:* the paper record and CLV stay shared (they grade the model); "my record"
    is computed from each user's own bets.
  - *Later, when a second person joins:* invite-only accounts, a per-user book (FanDuel or
    DraftKings), and a test that one user's session sees zero rows of another's.

## NFL fantasy (plan, 2027 season)

Mike asked on 2026-09-30. The props models already produce each player's full stat
distribution (receptions, yards, touchdowns, rushing, passing), which is most of a fantasy
projection.
- **Weekly projections:** fantasy points (PPR, half and standard) with ranges from the props
  models, anchored to the betting market where lines exist.
- **Tools:** start/sit, waiver pickups (role and snap-share trends), and FanDuel DFS lineups (DraftKings classic lineups exist since Nov 5, `dfs.py`; FanDuel's salaries need a sign-in)
  (an optimizer over the projections and their correlations from the game simulator: a QB
  with his receivers).
- **Preseason:** draft rankings from season-long projections in August.
- **Test:** projections scored on 2024-26 seasons against real fantasy points before use.

## MLB (plan, for the 2027 season)

Mike asked on 2026-09-30 (the Yankees were in the postseason). Same approach as soccer and
the NBA: the market prices the games, and we look for where FanDuel lags it.

- **Card (market-first):** moneylines, run lines and totals, FanDuel against Pinnacle's
  no-vig price, inside the 36-hour pick window like every other sport. Our own team
  ratings get weight only if they beat closing lines in a backtest; baseball closing
  lines are sharp, so expect market-only at first.
- **What moves a baseball line:** the starting pitchers. Lines are posted against the
  listed starters, so a late scratch changes everything: the card needs the probable
  starters (MLB Stats API, free and cloud-safe) and re-prices when one changes.
- **Props:** pitcher strikeouts, hits, total bases and home runs, every FanDuel line logged
  with features (pitcher K rate and pitch count, opposing lineup, park, weather, umpire),
  like `prop_lines.csv`. Props are the most likely soft spot, as in the NFL, and the
  ML layer trains on those logged lines.
- **Data:** MLB Stats API (schedules, probable starters, lineups, box scores; free),
  Retrosheet and Baseball Savant for history (check which work from GitHub's cloud
  runners, as with nba.com), Open-Meteo for weather (wind at Wrigley, cold in April).
  No free historical odds: buying one season of closing lines (like the NBA's, ~4,600
  credits) is Mike's call after the Oct 24 renewal decision.
- **Credits:** about 15 games a day for 6 months is the biggest volume we'd pull. One
  game-lines pull a day across the slate is ~3 credits; props per game add up fast, so
  pull props only for games starting within the hour (like the NBA tick).
- **Fun:** one SGP+ ticket per night across games, plus overs to root for (home runs,
  strikeouts). No same-player stacks, per Mike's rules.
- **Timeline:** build and backtest in February, test in spring training (mid-March),
  paper for the first two weeks, then scored like every other market.

## NHL (2026-27 season)

Mike asked on 2026-09-30 and then moved it up: it went live the same night on free data
(the model and the backtest are in `MODELS.md`, "NHL"). The plan below is what comes next.

- **Card (market-first):** moneylines, puck lines and totals, FanDuel against Pinnacle's
  no-vig price, inside the 36-hour window. Hockey lines are sharp and low-scoring games
  are noisy, so our team ratings get weight only if a backtest beats the close.
- **What moves a hockey line:** the starting goalie. Starters are confirmed late (often
  the morning skate or an hour before puck drop), so, like NBA lineups, price close to
  the start and re-price when the goalie changes. Back-to-backs usually mean the backup.
- **Props:** shots on goal, points, goalie saves. Every FanDuel line logged with features
  (ice time, power-play role, opponent shots allowed, goalie) for the ML layer, as in
  the NFL and NBA.
- **Data:** the NHL's public stats API (schedules, lineups, box scores, shots; free) for
  history and live games; check it works from GitHub's cloud runners first. No free
  historical odds, so the card is market-only and the logged lines are the training set.
- **Credits:** about 8 games a night. Game lines are cheap; props only for games starting
  within the hour, like the NBA tick. Check against the budget before turning on props.
- **Fun:** one SGP+ ticket per night plus overs to root for (shots, points). New York
  has no hockey-specific rules; college hockey follows the college rules.
- **Timeline:** data and backtest in the first half of November, paper card from about
  Nov 20, props in December, ML layer once there are enough logged lines.

## Props machine-learning model (plan)

The model predicts what the market misses, not the stat itself: target = over/under
hit, with the market's corrected log-odds as a fixed offset, so it can only add to the
market. It learns from `data/ledger/prop_lines.csv` rows (2026 as they grade) plus 2025
(and 2024 if backfilled) rebuilt with the same features.

- **Features:** the script lean's pass matchup and projected dropbacks, the QB and
  weather adjustment, receiver matchups (yards per target allowed, deep-ball fit), role
  (snap and target share, trend), line and price, and the stat. New features join only
  after the matchup lab shows they add something.
- **Model:** regularized logistic regression first (it's what the hand-built leans are);
  gradient-boosted trees (LightGBM) only if they beat it out of sample.
- **Validation:** walk-forward by week, game-grouped, scored by log loss vs the market
  and the favored side's hit rate; calibration by decile. It replaces the hand-built
  leans only if it beats them out of sample, and it reaches prices or picks only with the
  same evidence bar as everything else (rule 3).
- **When:** once about 8 weeks of 2026 lines are graded (≈ 4,000 more rows), mid-November.

## Market scorecard (per market, weekly; the go-live checklist until Sep 30)

Since 2026-09-30 this isn't a gate: Mike bets as he chooses from Oct 18. A market that
clears every bar is a **strength**; one with 50+ picks that misses a bar is a **weak spot**
to investigate and fix; the rest are **building**.


- At least 50 paper picks with measured CLV.
- Average CLV of at least +1%, and beating the close at least 55% of the time.
  Props are judged on raw CLV (against the plain sharp close): their fair price is
  corrected for the market's over lean, and the same correction on the close would hand
  every under about 4 points before the line moved (found Sep 26).
- Backtest calibration within 3 percentage points, where history exists.
- No open data or grading bugs.

The page's Results tab shows each market's progress on the first three every day
(`golive.py`, `app/golive`), with leans (same signal, smaller edges, `data/ledger/leans.csv`)
as supporting evidence. Since 2026-09-25 game days also get midday re-prices
(`reprice.yml`, 1:17 and 4:17 PM ET) so lags that open after the morning run can qualify.

## Upgrade triggers

- **$30/month data plan:** when a market passes on 100+ bets, or when November's volume
  needs it and overall CLV is positive. A one-month history backfill for prop
  backtests is optional.
- **$500 bankroll:** when CLV stays positive over 300+ bets and the staking rules have
  been followed.
