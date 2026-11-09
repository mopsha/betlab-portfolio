# scripts/

| File | Used by | What it does |
|---|---|---|
| `nba_window.py` | `nba.yml` | Standard library only: is an NBA game tipping 15–75 minutes from now (ESPN's public scoreboard)? Writes `soon=true/false` to `$GITHUB_OUTPUT`, so empty runs end before anything is installed. If ESPN is down it says yes and lets the Odds API check decide |
| `dfs_projection_study.py` | Claude, on demand | Do the DFS optimizer's market projections beat a player's own average? Yes (Nov 5: 7.84 points against 8.52). Free |
| `nfl_wind_refs_study.py` | Claude, on demand | Do NFL closing totals price the wind, and does the referee matter? (Nov 4; free; findings in `docs/DECISIONS.md`) |
| `backtest_drift.py` | Weekly CI (`backtests.yml`) | Did a closed season's backtest result change? Against `config/backtest_baseline.json`; never run on working files with a backtest that saves settings |
| `primetime_study.py` | Claude, on demand | Do primetime games (7 PM ET+) play out differently? Totals, sides and pace against closing lines 2006-25, and 2025 prop overs against Pinnacle. Findings: `docs/DECISIONS.md` (No primetime adjustment) |
| `scheme_angles.py` | Claude, on demand (free) | Do scheme tendencies add to the prop market? Blitz rate, two-high shells, box count and 2+ TE sets (FTN charting and nflverse participation) against FanDuel's 2024 and 2025 lines, walk-forward, five hypotheses fixed beforehand. Nov 6: none passed (DECISIONS) |
| `soccer_lag_study.py` | Claude, on demand (free) | Does FanDuel lag the sharp market in soccer? How often its 3-way is +EV vs Pinnacle, who closes early gaps, and CLV of every tracked line vs the Betfair close. First look Oct 9; Oct 19: no lag (part 4, early +EV prices vs Pinnacle's close; DECISIONS) |
| `weak_spots.py` | Claude, each Tuesday review and the Oct 17 weak-spot review (free) | Market by market, by book and by when a bet was logged: record, units, CLV on real closes only, share beating the close and sure_positive, under the scorecard's rules (`golive.current_rule`, `golive.real_closes`); markdown to paste into a review, weakest market first. `--since DATE` for one week |
| `props_2024_checks.py` | Claude, Oct 19 (free once `betlab backfill props` saved the lines) | 2025's three NFL prop findings (over lean, script lean, two receiving-yards matchups) on each backfilled season side by side, ~15-30 min a season. Oct 19: none held on 2024, so all three were turned off (DECISIONS) |
| `lineup_watch.py` | `nba-reach.yml` (watch mode) | NBA preseason live test: when do nba.com lineups turn Confirmed, in minutes before tip (polled every 5 min), and does FanDuel post preseason props in the feed (one ~8-credit probe)? Writes `data/lineup_watch/<day>.json`. Archived lineup files can't answer the timing question: their timestamps are the final update, after the game |
| `make_app_icons.py`, `make_app_icons.swift` | Claude, by hand | The iPhone's custom app icons: ESPN's team colors and our looks to `ios/BetLab/app_icons.json`, drawn into the asset catalog |
| `novig_read_key.py` | Mike, once (`railway run --service worker python scripts/novig_read_key.py`) | Makes a `management::read` Novig key (signed by the management key in Railway) for the worker's `novig_sync`: an Ed25519 pair made on the PC, the public half registered with POST /v3/keys, the private half written to `~/novig_betlab_read_key.pem` (never the repo); prints only the new key id. Then Mike swaps NOVIG_KEY_ID / NOVIG_PRIVATE_KEY in Railway and revokes the management key |
| `fire_page_sync.sh` | `daily.yml`, `evening.yml`, `reprice.yml`, `nba.yml`, `sync-page.yml` | Starts the page-sync routine: POST to `https://api.anthropic.com/v1/claude_code/routines/trig_01AsDvmu7oHR6WcVyBvNSJLH/fire` with the `ROUTINE_TOKEN` secret and the `experimental-cc-routine-2026-04-01` beta header |

How `fire_page_sync.sh` responds:
- **No `ROUTINE_TOKEN`:** it prints a note and exits 0.
- **HTTP 2xx:** it prints `page sync started`.
- **Anything else:** it prints the first 300 characters of the response plus how to
  fix it, then exits 1. That fails the workflow and GitHub emails Mike.

It never echoes the token. The fire body is `{}`: the routine ignores fire text by
design.
- `sample_fixture.py`: writes `web/fixtures/today.json` from the repo's own exports and ledgers (the rows `publish` would send), so the website's fixture preview works on a machine with no database URL. Shared market data only; no bets.
