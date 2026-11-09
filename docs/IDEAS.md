# Feature ideas

A menu, not a plan: what BetLab could add next. Brainstormed Oct 23, 2026; tidied Oct 28 (shipped ideas moved into one
table, duplicates merged, one line each). Numbers are kept from the original list so old references still work: plain
numbers (#1-#88) are the "edge and tools" list, **W**-numbers the "woah and cool" list.

Effort: **S** an afternoon, **M** a day or two, **L** a week or more. House rules apply to all of them: no model weight
without backtest evidence, New York's rules, Claude never places a bet or handles a key, units not dollars.

## Shipped

| Idea | What it became | When |
|---|---|---|
| W25, W26, W4 + headshots | Team logos and colors, player headshots, motion, the cash animation | Oct 23-24 |
| #23 | Leg push alerts (a leg hit, one left, one lost, the bet won), Garmin included | Oct 24 |
| W27, W7 | Game-day hub on Home and the multi-game wall | Oct 24 |
| W22, W11 (#63) | Ask BetLab chat, and Siri on the iPhone | Oct 24 |
| W13 (#56), W29 (#45), #40 | Share cards, achievements, personal stats | Oct 24 |
| W21 | Player and team cards | Oct 24-25 |
| #70, W24 | + Add a bet from slip screenshots | Oct 24-25 |
| #67, #8 (part) | Use a promo: the boost and bonus-bet finder, the two-book lock | Oct 22 |
| W17 | Wrapped | Oct 27 |
| W16 (#57) | Friends: a feed of friends' bets, profiles and Tail | Oct 27 |
| W8 (#24), W9 (#55) | Live Activities, the Dynamic Island, home and lock-screen widgets (iPhone) | Oct 27 |
| W3, #62 (part) | A haptic tap when a leg hits, a buzz when a bet cashes (iPhone) | Oct 27 |
| #66 (part) | Bet Protect+ tracked and graded (the evaluator itself isn't built) | Oct 26 |
| #2 | Live CLV on open bets ("CLV now" until the close decides it) | Oct 28 |
| #41 | Missed bets: My bets > Record, the picks you skipped at 1u beside the ones you took | Nov 2 |
| #47 | Alert settings: picks, leans, locks, sports, minimum EV, quiet hours | Nov 2 |
| #49 | News on your legs: a player on an open bet goes out, with the book's rule (NFL, NBA, NHL) | Nov 2 |
| #83 | Key rotation reminders: a to-do and one alert past 180 days | Nov 2 |
| W12 | Custom app icons (iPhone): looks, seasons, every NFL, NBA and NHL team | Nov 2 |
| Not on the list | Ladders, the ban list, Novig as a parlay book, Novig challenges, Novig on the game pages | Oct 25-28 |

## Mike's ratings, still to build

- **Liked:** W12 custom app icons (the color themes exist; the icons don't), W35 desktop ticker ("kinda sick but only
  useful for me").
- **Liked, Nov 4:** #9, #11, #12, #13, #14, #15, #16, #18, #22, #34, #38, W35, #60,
  #78. #54 comes with a condition: every game and time known far
  earlier, pulled once and checked once a day for changes. Mike hasn't set an order yet.
- **No, Nov 4:** #1 steam alerts, #86 why this pick, #6 Novig limit orders, #31 tennis, #21 calibration dashboard.
- **No:** W10 Apple Watch (Mike wears a Garmin; leg alerts already reach it). #64 goes with it.

## Claude's short list (if Mike wants a pick)

1. ~~#1 Steam alerts~~: Mike said no (Nov 4).
2. ~~#86 Why this pick~~: Mike said no (Nov 4).
3. **#73 Deploy check and #72 missed-lock alarm**: shipped Nov 4 (`health.py`).
4. ~~#6 Novig limit orders~~: Mike said no (Nov 4).
5. ~~#31 Tennis~~: Mike said no (Nov 4).

## Backlog

### Finding better prices
- **#1 Steam alerts.** The sharp book moved past a threshold and FanDuel, DraftKings or Novig still hangs the old number:
  an alert with the bet. M; credits.
- **#3 Best time to bet, per market.** When FanDuel catches up to the sharp book, from saved snapshots. M; free.
- **#4 Alt-line scanner.** Alternate-ladder rungs priced out of line with the main line and the sharp ladder. M.
- **#5 Middles and arbitrage** across the three books. S-M; free.
- **#6 Novig limit orders.** Post a better price than Novig's offer; show how often similar orders fill. M.
- **#7 Hold map.** Which markets at which book carry the least margin today. S; free.
- **#8 Promo scoring on arrival.** A boost or bonus token scored the moment it's typed in (the finder exists). S.
- **#9 Novig's catalog instead of paid pulls.** Checked Nov 4: saves nothing (credits are per 10 named books). `docs/DECISIONS.md`.
- **#10 Line-freeze watch.** FanDuel hasn't moved while every other book has. S.

### Models and research
- **#11 NBA injury re-pricing.** Redistribute a scratched starter's minutes and re-price teammates' props. L.
- **#12 NFL wind.** Tested Nov 4: a lead on totals, not proof. Tracked by `wind_watch.py`, never bet. `docs/DECISIONS.md`.
- **#13 Referee tendencies.** Tested Nov 4 (NFL): nothing there. `docs/DECISIONS.md`.
- **#14 UFC history before 2021.** Tested Nov 4: almost no gain. `docs/DECISIONS.md`.
- **#15 UFC odds backfill.** Not needed, Nov 4: free lines already show the model far behind the market. `docs/DECISIONS.md`.
- **#16 Market-move model.** Not built, Nov 4: EV already predicts the move. `docs/DECISIONS.md`.
- **#17 Correlation library.** Not built, Nov 4: every sport already prices same-game legs from its own joint simulation (`leg_packs` bits), so a second library would only duplicate it.
- **#18 Soccer props at DraftKings and Novig.** Checked Nov 2: nothing to build yet (`docs/DECISIONS.md`). Recheck if either feed adds them.
- **#19 Tennis Elo** (with #31). L.
- **#20 Is my parlay +EV?** Shipped Nov 4: a screenshot slip gets a fair price and value when read, even before you place it, and keeps it on My bets (`slip.ts slipFair`, `slip_prices`).
- **#21 Calibration dashboard** for every model and market. M.
- **#22 Closing-line archive.** Shipped Nov 4 (`betlab archive`, `archive.py`).

### Live and in-game
- **W1 Live game view.** A mini field, court or octagon on the bet card from the play-by-play. L.
- **W2 Sweat mode.** Full screen, one bet, a progress ring per leg. M.
- **W5 Rewatch your bet.** A 20-second replay of how it unfolded. M.
- **W6 / #28 Live chance to cash.** The parlay's live chance over time, from ESPN's win probability. M.
- **#25 Cash-out advisor.** FanDuel's offer against the bet's live fair value. S-M.
- **#26 Live hedge calculator** for a parlay with one leg left. S.
- **#27 Sweat board.** Every live leg across bets, closest to hitting first. S.
- **#29 Play-by-play for your players** under each live leg. S.
- **#30 Streamed tracker updates.** Shipped Nov 4 as far as it can go (`LivePulse`): a changed bet reaches the tracker at once; scores stay on the 20-second check because ESPN has no feed.

### New markets
- **#31 Tennis** (ATP/WTA), market-only. M; credits.
- **#32 Golf outrights and matchups.** M; credits.
- **#33 Futures and awards** as a tracked card. M.
- **#34 First-half and first-quarter lines**, after a lag study. M; credits.
- **#35 Boxing**, reusing the UFC build. S-M.
- **#36 Esports or F1**, only if Mike bets them. M.
- ~~**#38 DFS optimizer**~~: built Nov 5, from the market's lines rather than our models, but left off (Mike, Nov 5): DraftKings answers 403 to the worker (`dfs.py`, `docs/DECISIONS.md`).
- Never: college player props (New York rules).

### Your bets and records
- **#39 Import FanDuel and DraftKings bets** from their confirmation emails (Mike sets up the forwarding). M.
- **#42 Notes and tags** on bets, filterable in Stats. S.
- **#43 Tax/CSV export** with an export-only dollars-per-unit. S.
- **#44 Reconcile with the books' statements.** M.
- **#46 Variance view.** Expected vs actual profit, with the band luck explains. S-M.
- **#88 Decision journal.** A one-tap reason when you override the model; the review shows which reasons paid. S.

### Alerts
- **#48 Price watch.** "Tell me if Bears −3 gets to −110." S.
- **#50 Morning digest.** Yesterday's results, today's slate and locks, and (new) yesterday's Novig challenge points. S.
- **#51 Lock reminders** for the slices you usually bet. S.

### App experience
- ~~**W35 Desktop ticker**~~: built Nov 5, website only (`/ticker`).
- **W28 Night mode for the bar.** Extra dark, extra large. S.
- **#52 Search.** Shipped Nov 4 (More › Search): teams, games, fights, players priced so far, your bets; players with no pack and no bet aren't found.
- **#53 Follow teams and players.** A "Mine" filter and alerts. M.
- **#54 Calendar.** Shipped Nov 4 (More › Calendar): every game for 10 weeks from ESPN, read once a day (`calendar_sync.py`), with your bets and locks.
- **#59 Inline explanations.** Tap EV, CLV or no-vig for a one-line meaning. S.
- **#61 Offline and faster loads.** Shipped Nov 4: the iPhone opens Home, Games and My bets on saved data and reads anything saved with no signal (`ResponseCache`); the web keeps each page's last copy (`public/sw.js`). Writes still need a connection.
- **#65 Accessibility pass.** Part shipped Nov 4: faint text at 4.5:1 on all 21 web themes, missing iPhone labels, a skip link, focus rings. Not done: a real VoiceOver run-through, the accent colors, the iPhone's themes.
- ~~**#60 Onboarding**~~: built Nov 5, a new account's first look (`/welcome`).

### Social and fun
- **W14 Watch party room.** Two accounts, one live screen, reactions. M-L.
- **W15 / #58 Pick'em with Sam.** Weekly paper picks, a scoreboard, a monthly trophy. M.
- **W18 Daily voice briefing.** A 60-second audio rundown each morning. M.
- **W19 Game previews as stories.** Tap-through cards per big game. M.
- **W20 Hype video** before a big card. M-L.
- **W23 Voice parlay builder.** Say the legs; the slip builds itself. M.
- **W30 Season pass.** Season-long goals with levels. M.
- **W31 Model leaderboard.** Your picks vs the model vs favorites vs a coin flip. S-M.
- **W32 Parlay as a lineup** of players with live stat lines. S-M.
- **W33 AR stat overlay** on the TV. Very L.
- **W34 Smart lights** that flash on a leg. S-M with a Hue bridge.
- **#66 Bet Protect evaluator.** What it's worth on this slip. S.
- **#68 Round-robins**, priced and graded. S-M.
- **#69 Themed slips.** Shipped Nov 4 in Build: underdogs, favorites, overs, both teams to score (`builder.themedSlip`). On demand, not locked tickets in the ledger.

### Reliability and costs
- **#71 Worker health page.** Last run of each job, failures, credits, the build. S-M.
- **#72 Missed-lock alarm.** Shipped Nov 4 (`health.py`).
- **#73 Deploy check.** Shipped Nov 4 (`health.py`).
- **#74 Credit forecaster.** Projected credits to the reset. S.
- **#75 Odds API fallback** to free sources so the card still publishes. M.
- **#76 Nightly backups.** Shipped Nov 4 (`backup.py`, `data/backups/app_db.json`).
- **#77 Realtime updates.** Shipped Nov 4 (`app_pulse`, `LivePulse`).
- **#78 Backtests in CI.** Shipped Nov 4: weekly, soccer and NFL, closed seasons against `config/backtest_baseline.json` (`scripts/backtest_drift.py`). The NHL's takes 20 minutes and is left out.
- **#79 Volume growth watch.** Shipped Nov 4 (`health.disk_watch`). No routine cache pruning: `worker.check_disk` clears it when low.
- **#80 Cost page.** Monthly spend in one place. S.

### Security
- **#81 Passkeys and Face ID.** Face ID lock shipped Nov 4 (iPhone, Settings, off by default). Passkeys skipped (Mike, Nov 4): experimental in Supabase and tied for good to one web address; look again only after a custom web address.
- **#82 Session list.** Shipped Nov 4 (Settings › Signed-in devices, both apps).
- **#84 Audit log.** Shipped Nov 4 (`bet_history`, migration 0034); no screen for it yet.

### Learning
- **#85 Your own weekly review section.** What you took vs skipped, parlay share, leaks. S.
- **#86 Why this pick.** The math step by step on any pick. S-M.
- **#87 Interactive lessons** with your real bets as examples. M.
