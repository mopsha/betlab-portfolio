# BetLab

A personal sports-betting research system: it prices the lines at retail sportsbooks (FanDuel, DraftKings, the Novig
exchange) against the sharp market's no-vig prices, logs every pick to a git-committed ledger before its game, grades it
by closing line value (CLV), and shows it all in a web app and a native iPhone app on one database.

**Portfolio copy.** This is the code, tests and docs only. The private repo's data (odds snapshots, pick ledgers,
backups) and every key, ID and personal detail are left out, so the pipeline won't run as-is without your own keys and
a fresh database.

## What it does

- **Prices markets, not hunches.** The core finding (backtested, written up in [`docs/MODELS.md`](docs/MODELS.md)):
  closing lines beat our own ratings models, so picks come from retail prices that lag the sharp books (Pinnacle,
  LowVig). Models are tracked and given zero weight until a backtest earns them some.
- **Seven leagues:** NFL, college football, NBA, college basketball, NHL, soccer (top five leagues, MLS, European cups)
  and UFC: game lines, player props and same-game parlays priced from simulated games.
- **Grades itself honestly.** Every pick is graded against a sharp close taken after it was made. When a backtest didn't
  hold up on new data, the feature was turned off ([`docs/DECISIONS.md`](docs/DECISIONS.md)).
- **Runs unattended.** A worker on Railway runs the schedule in Eastern time: grading overnight, morning lines, a
  pre-game tick every 15 minutes (pull after the news, price, publish, push alerts). It also checks itself: a watchdog
  for counts that quietly drop to zero, deploy and disk checks, and per-step failure alerts.
- **Two apps kept in step:** a Next.js web app and a SwiftUI iPhone app (widgets, Live Activities, Siri). Both have
  live bet tracking from ESPN play-by-play, a parlay builder with fair prices, screenshot-to-bet and screenshot-to-promo
  reading with Claude, promo optimization, friends feeds and push alerts.

## Stack

| Part | Built with |
|---|---|
| Pricing, models, grading, worker | Python 3.13: pandas, NumPy, scikit-learn, APScheduler |
| Web app | Next.js 16, React, TypeScript, on Railway |
| iPhone app | SwiftUI, WidgetKit, ActivityKit, App Intents (no third-party SDKs) |
| Database | Supabase (Postgres) with row-level security, 47 migrations, tested on PGlite |
| AI features | Claude API: reading bet slips and promo screenshots, an in-app assistant |
| Data | The Odds API, ESPN, nflverse, NHL and NBA feeds, Novig's public API, Open-Meteo |

About 90k lines across Python, TypeScript and Swift, with 1,020 Python tests, 229 web tests and 201 iPhone tests. Logic
shared by the three ports (live leg judging, ban matching, promo math) runs against one JSON fixture in each, so they
can't drift apart (`tests/fixtures/`).

## Where to read

| Start here | What it shows |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/APP_PLAN.md`](docs/APP_PLAN.md) | How the pieces fit |
| [`docs/MODELS.md`](docs/MODELS.md) · [`docs/MODEL_CHANGELOG.md`](docs/MODEL_CHANGELOG.md) | Every model, its backtest and why it has the weight it has |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Decisions with their reasons and evidence |
| [`CLAUDE.md`](CLAUDE.md) | The working agreement and "pitfalls we already hit": production incidents and what each one changed |
| [`src/betlab/`](src/betlab/README.md) · [`web/`](web/README.md) · [`ios/`](ios/README.md) · [`supabase/`](supabase/README.md) | The code, each folder with its own README |

## How it was built

Built from Sept 2026 over about 2,000 commits, using Claude Code as the engineering partner: I set the direction, made
the betting and product decisions, and reviewed the work, while Claude wrote most of the code under the rules in
[`CLAUDE.md`](CLAUDE.md). Those rules: no model weight without backtest evidence, an append-only pick ledger, tests on
every push, and New York's betting rules built in.

## Running it

1. Copy `.env.example` to `.env` and add your own keys.
2. Python: `python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/python -m pytest`. A few tests
   read data files that aren't in this copy.
3. Web: `cd web && npm install && npm test`. iPhone: see [`ios/README.md`](ios/README.md).

Not betting advice. Picks were suggestions for one person, counted in units.
