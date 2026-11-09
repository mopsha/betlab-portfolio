# src/betlab/: the package

Everything BetLab computes. The CLI (`cli.py`) is the entry point for every
workflow step. Subpackages have their own READMEs.

## Module map

| Module | Purpose | Key names |
|---|---|---|
| `cli.py` | The `betlab` command: pull, pull-props, card, fun, preview, refresh, grade, export-page, import-taken, backtest, credits | `main`, `EVALUATORS`, `ready`, `prime_time_events` |
| `config.py` | Paths (`ROOT`, `DATA_DIR`, `EXPORTS_DIR`), cached settings loaders, secret lookup | `settings()`, `ny_restrictions()`, `secret(name)` |
| `odds_math.py` | Pure odds math: conversions, vig/hold, devig (multiplicative, power, Shin), EV, Kelly, bonus-bet value, parlays, CLV | `devig`, `expected_value`, `kelly_fraction`, `clv` |
| `edge.py` | Blending model and market probabilities in log-odds space; fitting the blend weight | `blend_prob`, `fit_blend_weight`, `log_loss` |
| `market.py` | Reading one book's two-way prices out of an odds snapshot; choosing the reference books | `two_way`, `reference_books` |
| `picks.py` | Turning priced offers into picks, leans and check-the-news flags; stakes; why-notes | `classify`, `stake`, `why_note` |
| `staking.py` | Confidence tiers, quarter-Kelly units, exposure caps (caps not yet applied) | `tier_units`, `kelly_units`, `apply_exposure_caps` |
| `ledger.py` | The pick ledger (`data/ledger/picks.csv`): load, save, append without duplicates | `add_picks`, `pick_id`, `COLUMNS` |
| `alerts.py` | Pick alerts: new picks (logged in the last 6 h, not started, not yet announced) pushed to every subscribed device; `--test` confirms a newly subscribed one. Run by the worker after each card | `pending`, `messages`, `run`, `test` |
| `apns.py` | The native iPhone app's alerts through Apple's push service (APNs): `alerts.py` sends `apns:` devices here (keys APNS_KEY_P8, APNS_KEY_ID, APNS_TEAM_ID in Railway) |
| `leg_alerts.py` | Leg push alerts (Oct 24): every minute in the worker, each open real bet's legs judged live from ESPN; the bettor's devices get one push per event (a leg hit, one leg left, a leg lost, the bet won; singles won/lost), each once (`alerts_sent` keys `leg:`/`bet:`), a bet's first look silent; off per user with `user_settings.notify` {"legs": false} | `run`, `check`, `events`, `message` |
| `reactions.py` | Reaction alerts (Nov 6, migration 0042): every minute with the leg alerts, a friend's reaction to your bet goes to your devices once (`alerts_sent` keys `react:<bet>:<user>:<reaction>`), held through quiet hours, off with `notify.reactions` | `run`, `pending`, `message` |
| `live_activity.py` | Live Activities (Oct 27): in the same minute, from the same judging, a real bet's iPhone lock-screen / Dynamic Island activity is started (push-to-start once a game is on, at most 3 live per account), updated (on a change, or every 20 minutes; a leg settling at high priority) and ended (won, lost, every game over, or no longer open), over APNs' `liveactivity` push type. Tokens in `live_activity_tokens`, its own record in `live_activity_state` (migration 0025). The content's keys are the app's `ios/Shared/BetActivity.swift`: **change both together** | `plan` (pure), `tick`, `content` |
| `live_legs.py` | The web tracker's leg judging (web/lib/live.ts) ported for the worker: ESPN boards and box scores, leg labels, verdicts; `tests/fixtures/live_legs.json` is run by both test suites so the two stay in step | `parse_leg`, `judge`, `live_bet` |
| `pregame.py` | The new schedule's pre-game pulls (`betlab pregame`, every 15 min on the worker): each game's lines and props once, inside its sport's window after the news, merged into the latest snapshot so other games keep their earlier prices; a pulled game whose news changes before the start is re-pulled (at most twice); one closing look in the last tick before the start (1-15 minutes out) at any game whose open prop picks or leans no pull has followed since they were logged (Oct 13), keeping its other markets | `run`, `due`, `merge_latest`, `windows`, `load_state`, `open_rows`, `with_other_markets` |
| `news.py` | Free news fingerprints per game for the pre-game re-pulls: ESPN's live injury reports (NFL, NBA, NHL), NHL starting goalies, NBA lineups; a source that fails is left out, so outages never look like news | `sources`, `fingerprint`, `changed`, `team_key` |
| `gitsync.py` | The worker's repo clone on the Railway volume: clone once, take main's commits before a job, commit `data/` and `exports/` and push to main after it (GITHUB_TOKEN as a per-command header, never stored or logged) | `ensure_clone`, `update`, `publish` |
| `fun_ledger.py` | The fun ledger (`data/ledger/fun.csv`): syncs the page's quoted and marked parlays, SGP+ tickets (NFL and college) and straight overs, parses leg labels, grades leg by leg (each from its own game; NFL from nflverse, or ESPN's final box score before nflverse posts, `with_espn`; college from CFBD's final scores; a parlay across sports grades each leg by its own sport's grader, `leg_sport`), writes `exports/fun_results.json` | `sync`, `grade`, `summary`, `parse_leg` |
| `golive.py` | The go-live checklist per market (picks with CLV vs the 50 / +1% / 55% bars, leans beside them, research reads; CLV only from real closes: `real_closes` blanks NHL/soccer prop CLV taken from the bet's own pull, Oct 13); writes `exports/golive.json` | `build`, `status`, `market_key`, `real_closes`, `write` |
| `tracking.py` | The prop-line tracker: every FanDuel main line with market, features, reads and result (`data/ledger/prop_lines.csv`) | `record`, `grade`, `summary`, `load` |
| `injuries_nfl.py` | Non-QB absences for the game-flow engine: regulars from earlier games (line, top target, lead back, top pass rusher, defensive starters), who's missing (backtest: didn't play; live: injury report plus weekly roster), the fitted effects and a sentence | `absences`, `live`, `find_regulars`, `adjustments`, `sentence`, `EFFECTS` |
| `ncaab_reads.py` | College basketball reads: games where our margin and FanDuel's spread differ by 3+ points, first sighting kept, graded for CLV (points the close moved toward the read) and result (`data/ledger/ncaab_reads.csv`) | `record`, `grade`, `summary`, `load` |
| `tracking_soccer.py` | Every FanDuel soccer 3-way line (first and latest price, the sharp chance, result, the sharp close from football-data.co.uk): does FanDuel lag in soccer, and the ML layer's training set (`data/ledger/soccer_lines.csv`) | `record`, `grade`, `summary`, `load` |
| `links.py` | Betslip links for "Open in FanDuel" / "Open in DraftKings": matches picks to their own book's outcomes, and every parlay leg to FanDuel's and DraftKings' (DraftKings' nearest rung where it lacks ours; each slip's DraftKings side) in the latest snapshots. A number in both the main market and the alternate ladder links the ladder's rung (Oct 30: a main market keeps its id when its line moves); a leg only in a main market with a number keeps its link, marked `link_main` (`dk_link_main`), and the apps say to check the number | `book_rows`, `Matcher`, `attach_card`, `attach_fun`, `attach_dk` |
| `tracking_nhl_props.py` | Every NHL prop line at both books (`book`) with consensus, model, features, read tag and result (`data/ledger/nhl_prop_lines.csv`); the NHL props ML training set | `record`, `grade`, `summary`, `load` |
| `backtest_joint_nhl.py` | The joint NHL model's pairs (shooter, goalie, win, total) against 2025-26 outcomes | `run` |
| `backtest_props_nhl.py` | NHL props model walk-forward vs baselines, with and without the game analysis; trains and saves the live model | `prepare`, `evaluate`, `train_final` |
| `tracking_nhl.py` | The NHL tracker: every game's DraftKings line (first and last look), goalies, model, result, close and read CLV (`data/ledger/nhl_lines.csv`) | `record`, `grade`, `summary`, `load` |
| `tracking_ufc.py` | The UFC tracker (Oct 23): every fight's DraftKings prices from ESPN (moneyline, method, total rounds, distance) at the first and last look, the sharp moneyline, our model's read, and the result (`data/ledger/ufc_lines.csv`) | `record`, `grade`, `summary`, `load` |
| `tracking_nba.py` | The NBA prop-line tracker: every main NBA line at both books (`book`) with market, model, features and result (`data/ledger/nba_prop_lines.csv`); the NBA ML layer's training set | `record`, `grade`, `summary`, `load` |
| `grading.py` | Settling finished picks and measuring CLV (game lines from scores, player props from player stats) | `grade_all`, `grade_football`, `grade_props`, `settle` |
| `ny_rules.py` | New York betting restrictions | `allowed`, `is_ny_college` |
| `explain.py` | Football explanations for picks, leans and parlay legs (role, matchup, game script, injuries; ratings for game lines) | `prop_story`, `leg_note`, `game_line_story`, `slip_story` |
| `players.py` | Matching sportsbook player names to nflverse ids within the two teams' rosters | `normalize`, `match` |
| `props_market.py` | No-vig prop prices (main lines, TD, alt ladders) and anchoring the game simulator to them | `anchor`, `fair_main`, `rake`, `fit_tails` |
| `sgp.py` | Fun same-game parlays: FanDuel legs (player props, and the game's moneyline, spread and total), pairwise correlation, beam search, near-duplicate filter | `build_legs`, `game_line_legs`, `search`, `pick`, `to_doc`, `leg_doc` |
| `clv_now.py` | Live CLV on open bets (Oct 28, idea #2): at every publish, each open real bet's CLV at its price against the current sharp chance (a pick's card offer; a leg's builder pack; an app parlay's fair chance moved by each leg; a cross-game slip's legs multiplied; NHL codes count as their full names and "ML" as "to win"), written to `bet_clv` |
| `challenges.py` | Novig challenges (Oct 28): each of today's (`challenges` table) parsed from Novig's words, solved (straights: Novig vs Pinnacle's no-vig, at the worse of the pulled and live price; parlays: different games, most likely first at Novig's own price) and, once ripe (news in, the hour's EV bar), saved and alerted; `betlab challenges`, every pregame tick |
| `novig_parlays.py` | Novig in the game pages' book tables (`attach_tables`: NHL lines and props, NBA player lines, soccer 3-way; its live price where $50+ stands behind it, with EV), and Novig's side of every parlay (Oct 28): each fun leg found on Novig's catalog (`nv_id`, `nv_price` when $50+ stands behind it) and each slip's and SGP+ ticket's exact price, largest stake and one-tap link from Novig's free parlay pricer (`nv`); run by `publish` (`page_products(novig=True)`), off with `odds_api.novig.parlays` |
| `novig_sync.py` | Mike's Novig bets into My bets from his own account (Oct 22; read-only key in `NOVIG_KEY_ID` / `NOVIG_PRIVATE_KEY`, set by Mike): fills grouped per outcome become bets ($5 = 1u), settled positions settle them; NOVIG-V3 request signing checked against Novig's 30 published vectors (`tests/data/novig_signing_vectors.json`). Runs in every pregame tick and at 3 AM; `novig_sync` can be queued | `run`, `bets_from_fills`, `string_to_sign`, `sign` Since Oct 28 each bet is matched to the app's game and written as a slip's is (our wording, the game's matchup, `games` with its grader ref), so My bets tracks it; older ones are rewritten once matched. |
| `books.py` | Mike's books (FanDuel, DraftKings; Novig for game lines, Oct 22): `price_all` runs an evaluator per book (`kind="props"`: the sportsbooks only) and attaches an exchange's bet limits, `select` keeps one offer per bet (higher EV, ties to FanDuel; a Novig price under `novig.min_limit` never wins) with the next book's price attached | `targets`, `name`, `price_all`, `attach_limits`, `select` |
| `td_reads.py` | Every anytime TD read the Fun tab makes (`data/ledger/td_reads.csv`): FanDuel price, Pinnacle's chance, our read and features, graded after the game; summary compares log loss with the market's | `record`, `grade`, `summary`, `load` |
| `nba_reads.py` | The NBA team model's game read (models/team_nba): projections for the morning listing and the game page, logged to `data/ledger/nba_reads.csv` and graded against the close and the result | `project`, `rows`, `record`, `grade`, `summary` |
| `soccer_goal_reads.py` | The soccer lineup goals read: Poisson over 2.5 and BTTS from the analysis's lineup goals vs the market's, logged at confirmed lineups (`data/ledger/soccer_goal_reads.csv`), log loss summary | `read`, `record`, `grade`, `summary` |
| `fun_offers.py` | Every offered NFL slip (`data/ledger/fun_offers.csv`) with its style and weakest pair lift, graded leg by leg (fun_ledger's NFL grader); summary by style and one story or not | `record`, `grade`, `summary`, `settle` |
| `backtest_td.py` | The TD read's backtest (train 2023-24, test 2025) and the live fit saved to `data/models/td_params.json` (`betlab backtest td`) | `training`, `run` |
| `sgp_plus.py` | The Fun tab's slates: per kickoff window, one SGP+ ticket (a mini same-game parlay from each of 2–4 games, fair chance the product) and the straight overs to root for | `build`, `ticket`, `td_ticket`, `td_candidates`, `td_chalk`, `minis`, `rooting_overs`, `slate_of` |
| `backtest.py` | Walk-forward backtests against closing lines | `nfl`, `ncaaf`, `run_football` |
| `backtest_props.py` | Walk-forward backtest of the NFL props models (CRPS, log loss, rung calibration), the test against real prop lines, and the script-lean test | `run`, `report`, `market_eval`, `market_games`, `market_report`, `script_eval` |
| `backtest_sgp.py` | The fun-parlay simulator's joint vs real games: pairs of legs by role, four-leg slips and anytime TDs (2023–25), and pairs of real 2025 FanDuel lines (the simulator's joint vs independent legs) | `run`, `report`, `market_pairs`, `market_report`, `pit_draws` |
| `props_lag.py` | Does FanDuel's morning prop price lag? Each FanDuel main line's morning price against the sharp no-vig price at its exact point, morning and close, from the committed props snapshots (`betlab backtest lag`) | `load`, `pairs`, `report` |
| `backtest_ncaab.py` | College basketball ratings walk-forward: tuning on 2023-24, error vs the close with blend weights from earlier seasons, and the opener tests (cover rate, the line's move toward the model) | `predict`, `tune`, `vs_close`, `vs_open`, `line_moves` |
| `backtest_soccer.py` | Soccer ratings vs Pinnacle's close and its earlier line, walk-forward per league, blend weight from earlier seasons, and whether the model predicts line moves | `run`, `predict`, `evaluate`, `line_moves` |
| `backtest_nhl.py` | NHL model walk-forward (tuned on 2022-24, tested on 2024-26), against DraftKings' 2025-26 opens and closes; saves `data/models/nhl.json` | `prepare`, `games`, `walk`, `tune`, `market_eval`, `report` |
| `backtest_nba.py` | NBA team and player models vs naive baselines, walk-forward; tunes calibration on the training season and saves `data/models/nba_*.json` | `load`, `team_eval`, `player_eval`, `tune` |
| `backtest_cfb.py` | College: the efficiency read vs opening and closing lines, walk-forward; refits the early read | `table`, `evaluate`, `fit_early` |
| `cfb_reads.py` | The college early read's tracker (`data/ledger/cfb_reads.csv`) | `record`, `grade`, `summary` |
| `cfb_dogs.py` | College moneyline dogs at 20-40% against Pinnacle's close (`data/ledger/cfb_dogs.csv`; tracked, never a pick) | `record`, `grade`, `summary` |
| `watchdog.py` | The zero watchdog (Oct 30, after Novig's pricer moved and every publish quietly logged "0 priced" for two days): reads yesterday's `runs` logs (ET) for a step's "N of M" at none of many (Novig parlays, live CLV), a count that was above zero most of the week gone to zero on a normal day (Novig game-page prices, leans, offers, slice locks), and errors a soft step swallowed; one owner alert a day (`alerts.problem("watchdog")`); `betlab watchdog [--day D] [--no-alert]`, last step of the 9:55 daily | `check`, `day_stats`, `run`, `RATIOS`, `USUAL` |
| `calendar_sync.py` | The calendar (Nov 4): ESPN's next 70 days for every league into `schedule_games` on the day's first pregame tick, then a daily look for what changed (free, ~15 s). A failed day keeps its rows. `betlab calendar` |
| `archive.py` | Every saved odds pull boiled down to one row per bet, first and last price before the start, for studies (Nov 4). `betlab archive` writes `data/cache/archive/lines.parquet`, rebuilt in ~15 s |
| `dfs.py` | DraftKings classic lineups from the market's prices; a suggestion, not a pick (Nov 5). Off in the worker: DraftKings answers 403 to Railway. `betlab dfs [--grade]` |
| `wind_watch.py` | Windy NFL games against the close, logged by the 9:55 daily: tracked, never bet (Nov 4). `data/ledger/wind_watch.csv`, `betlab wind-watch` |
| `backup.py` | The app database's daily backup (Nov 4): `TABLES` to `data/backups/app_db.json` on the day's first pregame tick, one row a line, so git holds each day's copy; a copy under half the last is refused. `betlab backup` |
| `health.py` | Every pregame tick (Nov 4, free): a slice with a ticket past kickoff without its lock, and a `src/` push not on the worker 15 minutes later, and the volume filling within 30 days (`data/disk_usage.csv`); one owner alert a day per finding. `betlab health [--no-alert]` |
| `alert_prefs.py` | Each account's alert settings (`user_settings.notify`, Nov 2): the one reader, used by `alerts.py`, `leg_alerts.py`, `leg_news.py` and `reactions.py` |
| `leg_news.py` | News on your legs (`betlab leg-news`, every pre-game tick, free, Nov 2): a player on an open real bet goes out (ESPN's injuries, nba.com's inactives), alerted once with the book's rule |
| `rotation.py` | Key rotation reminders (`betlab rotation`, the 9:55 daily, Nov 2): reads `config/key_rotation.yaml`, adds a to-do and one alert. Names only, never a value |
| `pickem.py` | FanDuel's College Football Pick'em (Nov 7): the week's entry (`pickem` table, from screenshots) matched to the Odds API's games (`match_event`: FanDuel's short names, both must fit one game), each frozen line priced against the sharp market with the college margin model (`price`: the home cover chance at the frozen number), our side (`our_side`, none under New York rules), graded from ESPN's board (`settle`, `final_score`), one alert at 10 AM Saturday for flips and one at 11:45 to submit (`_alert`); `betlab pickem`, every pregame tick | `run`, `match_event`, `price`, `flips`, `score` |
| `ladders.py` | Ladder challenges' worker step (`betlab ladders`, every pre-game tick, free): holds the day's best step (or the chosen game's) and locks it once its game's news is in, alerting the owner; the ladder math ported from web/lib/ladder.ts on `tests/fixtures/ladder.json` | `run`, `decide`, `state`, `suggest` |
| `resets.py` | Bet resets (`betlab resets`, every pre-game tick, free): a lost bet with `bets.reset` puts its stake in the wallet as a bonus bet (`issue_resets()`, migration 0031) |
| `backtest_game.py` | Walk-forward checks of the game-flow engine's QB ratings and weather effects | `load`, `qb_eval`, `qb_report`, `weather_eval` |
| `backfill_props.py` | Historical NFL prop lines an hour before kickoff (paid key, ~40 credits a game) | `run`, `path` |
| `sources/` | Outside data: Odds API, nflverse, CollegeFootballData | see `sources/README.md` |
| `models/` | Ratings, key-number distributions, the football model, the props draft, the joint game simulator | see `models/README.md` |
| `cards/` | Per-league pricing of today's FanDuel offers, and the fun parlays (`fun_nfl.py`) | see `cards/README.md` |
| `reports/` | The card, results summaries and fun parlays written to `exports/` | see `reports/README.md` |

## How a card gets made

```
cli.cmd_card
  └─ for each league in EVALUATORS: latest snapshot (data/odds/...) → cards/<league>.evaluate
        └─ cards/football.evaluate: games table + model settings → offers with p_model, p_market, p_final, ev
  └─ picks.classify → picks.stake → picks.why_note → ledger.pick_id
  └─ reports/card.build/write → exports/card.json, card.md, cards/<date>.json
  └─ ledger.add_picks → data/ledger/picks.csv (new picks only)
```

## CLI reference (`betlab <command>`)

| Command | Flags | What it does |
|---|---|---|
| `credits` | | Prints the Odds API balance (free `/sports` call) |
| `pull` | `LEAGUES...` | Pulls those leagues' odds now (3 credits each) |
| `pull` | `--auto --again HOURS` | Like `--auto`, but pulls again if today's last pull is at least HOURS old (the midday re-price) |
| `pull` | `--auto` | For each league in `EVALUATORS`: pulls only if it has started (`settings.leagues.<lg>.start`), is `ready()`, wasn't pulled today (ET date folder exists), and has games in the next 36 h (free `/events` check) |
| `pull` | `--prime-time` | NFL only: pulls if a game kicks off in 30–110 minutes (`PRIME_TIME_WINDOW`); tells the workflow via `GITHUB_OUTPUT` (`pulled=true`) |
| `pull-props` | `--event ID`, `--prime-time`, `--within HOURS`, `--once-daily` | NFL player props for one game, the prime-time game, or every game in the next 36 h: main lines, alt ladders and anytime TD (about 9 credits a game). Saves a `_props` snapshot |
| `pull-props --league nhl` | `--once-daily`, `--within H` | NHL shots-on-goal lines for games in the next 36 hours (about 1 credit a game), for the Fun tab's shots overs. `daily.yml` runs it once a day |
| `pull-props --league nba` | `--tip-window MIN MAX` (default 15 75), `--event ID` | NBA props for games tipping in the window (about 8 credits a game), the night's game lines, and closing prices for games with open NBA picks. Nothing before the season start in settings. `nba.yml` runs it hourly on game nights |
| `fun` | `--event ID`, `--dry-run` | Builds the fun same-game parlays from the latest `_props` snapshot (`cards/fun_nfl.py`) and the college, soccer, NHL and UFC tickets per kickoff slice (`cards/fun_ncaaf.py`, `fun_soccer.py`, `fun_nhl.py`, `fun_ufc.py`); every slice's tickets lock 15 minutes before it starts (`sgp_plus.keep_tickets`, against the last `exports/fun.json`); writes `exports/fun.json`, `fun.md`, `fun/<date>.json` |
| `lock-due` | | Free: does a fun slice reach its lock time (15 minutes before its first kickoff) now? Sets the `lock_due` output, so the worker's pregame tick rebuilds, publishes and alerts (`sgp_plus.lock_due`) |
| `preview` | | Game Previews for every NFL game in the next 7 days (`cards/preview_nfl.py`): market score, our read, pace, run/pass, unit matchups, QBs, injuries, weather, lines that fit the script and matchup notes (both off, still tracked); records every main prop line in the tracker; writes `exports/previews.json` |
| `card` | `--dry-run`, `--snapshot FILE`, `--asof UTC` | Prices the latest snapshot per league; writes the card and logs picks unless `--dry-run` |
| `refresh` | | Refreshes this season's college history from CFBD (skips without a key) |
| `grade` | | Settles open picks, computes CLV, writes `exports/results.json` |
| `export-page` | | Writes `exports/page_sync/*.json` + `manifest.json` for the page sync |
| `import-taken` | `FILE` | Marks the ledger's `taken` columns from the page's taps (a JSON list) |
| `import-fun` | `--quotes FILE --taken FILE` | Syncs the page's quoted and marked fun parlays into `data/ledger/fun.csv` |
| `import-page-taps` | `--taken F --fun-taken F --quotes F` | Copies the page's marks and typed prices into the owner's rows in the app database (insert-only; the daily run repeats it until the page is retired) |
| `import-page-db` | `DIR` | Copies the page's to-dos and reviews (ArtifactData out_dir files, `DIR/todos/*.json`, `DIR/reviews/*.json`) into the app database for the owner (insert-only; done once on Oct 2) |
| `todo` | `list [-v] [--all]` · `add --owner you\|claude --title T [--detail D] [--due YYYY-MM-DD]` · `done\|reopen --id X` · `set --id X [--title] [--detail] [--due] [--owner]` | The shared to-do list (the app's More > Plan), as the owner (`plan.py`) |
| `review` | `--title T --body-file F [--id X]` | Posts a weekly review to More > Reviews (blank lines split paragraphs, "- " lines are bullets) |
| `backtest` | `nfl` | Prints log loss and pick results (the college backtest runs from Python: `backtest.ncaaf()`) |
| `backfill` | `props --season 2025 --weeks 3-18 [--limit N]` | Saves historical prop lines to `data/odds_history/americanfootball_nfl/props_<season>.parquet`; resumable |
| `backtest` | `props` | The NFL props models v0.1 vs v0.2 over 2023–2025 (about 10 minutes) |
| `backtest` | `script` | Does the game script (pass matchup, projected dropbacks) add to the 2025 prop market? With and without QB and weather; fits, game-bootstrap SEs, season halves (about 4 minutes) |
| `nhl` | | The NHL view from free data (0 credits): ESPN's DraftKings lines and goalies, the model, the tracker; `daily.yml` and `reprice.yml` run it |
| `backtest` | `nhl` | NHL model: tune on 2022-24, test on 2024-26 against DraftKings (about 20 minutes) |
| `backtest` | `nba` | NBA team and player models (fit 2024-25, test 2025-26), saves their settings (under 1 minute) |
| `backtest` | `cfb` | College efficiency read vs opening and closing lines (2016–25), and refits `data/models/ncaaf_early.json` (about 1 minute) |
| `backtest` | `ncaab` | College basketball ratings vs the close and the opener, 2023-24 to 2025-26 (under a minute) |
| `backtest` | `soccer` | Soccer ratings vs Pinnacle's close and earlier line for the big five and MLS (2018-19 to 2025-26), blend weights from earlier seasons, and the line-move test (about 1 minute) |
| `backtest` | `sgp` | The fun-parlay simulator's joint: pairs by role, four-leg slips and anytime TDs over 2023–25, then pairs of real 2025 FanDuel lines, joint vs independent legs (about 7 minutes) |
| `backtest` | `td` | The anytime TD read: usage + team points vs adding red-zone role and recent TD rate (train 2023-24, test 2025, game bootstrap), calibration, then refits `data/models/td_params.json` (about 2 minutes) |
| `backtest` | `game` | QB ratings (pass EPA error with and without, 2016–25) and weather effects (2012–25) in the game-flow engine (about 1 minute) |

## Conventions

- **Units:** American odds are numbers like −110/+150. Probabilities, EV and CLV are
  fractions (0.03 = 3%). Units are fractions of the bankroll per `unit_pct`.
- **Probabilities are "conditional on no push"**; `p_push` travels separately.
  `expected_value(p_win, price, p_push)` handles refunds.
- **Time:** stored in UTC ISO strings. The ET date (`America/New_York`) names daily
  folders and cards.
- **Side effects stay in `cli.py`:** modules return DataFrames/dicts, and only the CLI
  (plus `ledger.save`, `reports.*.write`, `sources/*` saves) writes files.
