# docs/

Topics that span the whole repo. Folder-specific documentation lives in each
folder's own `README.md`. Start with `../CLAUDE.md` if you're new here.

| File | Read it when you need |
|---|---|
| `ARCHITECTURE.md` | **Before Oct 6** (see `APP_PLAN.md` for the worker and apps): how the pieces fit: GitHub Actions, the repo, the page-sync routine, the page. Schedules, data flow, failure handling, security boundaries |
| `COVERAGE.md` | Every market side by side: picks, analysis, props, fun, credits, backfilled seasons, ongoing ML. Updated whenever a market changes |
| `MODELS.md` | How every model works, the math behind pricing and picks, backtest results, what we learned |
| `OPERATIONS.md` | Runbook: local setup, running things by hand, refitting, rebuilding data, debugging failed runs, rotating secrets, adding a league |
| `DATA_SOURCES.md` | The outside services we call (The Odds API, nflverse, CollegeFootballData): what each gives us, costs, limits, quirks |
| `DECISIONS.md` | A dated log of product and design decisions and why they were made. Check it before re-opening a settled question |
| `MODEL_CHANGELOG.md` | Every change to model settings, with the evidence behind it |
| `ROADMAP.md` | Phases and dates. The live task list is the page's To-do tab |
| `IDEAS.md` | Feature ideas (Oct 23 brainstorm): part 2 "woah and cool" (35: live game views, sweat mode, Wrapped, widgets, chat, social), then 88 on prices, models, live, tracking, app and reliability with value, effort and cost. A menu, not a plan |
| `NBA_PLAN.md` | The NBA build: ML-first, data sources, models, evaluation, timeline, Mike's decisions |
| `DRAFTKINGS_PLAN.md` | The second book (Oct 12): DraftKings at parity with FanDuel by Oct 18, the edge cases where the two books differ and the rule for each, day-by-day build, Mike's decisions |
| `OVERHAUL.md` | The reorganization and UI overhaul (from Nov 4): the plan, Mike's picks, what's done |
| `HISTORY.md` | Dated status notes and retired systems moved out of `CLAUDE.md` (Oct 25): the pre-worker pipeline, the routines and their IDs, the Windows setup |
| `archive/` | Finished one-off documents: the Oct 24 Mac handoff (all ported), the page-sync routine's prompt (retired Oct 6) |
