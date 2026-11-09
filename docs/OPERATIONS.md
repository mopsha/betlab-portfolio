# Operations runbook

How to run, change, debug and extend BetLab. Commands assume the repo root
(`betlab/`) on Windows. In Git Bash use `./.venv/Scripts/…` instead of `.venv\Scripts\…`.

## Local setup

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

Keys go in `.env` (copy `.env.example`), and **Mike adds them himself**. Claude never
reads or writes keys. To check whether they are present:

```
.venv\Scripts\python -c "from betlab import config; print({k: bool(config.secret(k)) for k in ('ODDS_API_KEY','CFBD_API_KEY')})"
```

## Everyday commands

| Command | What it does | Cost |
|---|---|---|
| `betlab credits` | Shows the Odds API balance | free |
| `betlab pull --auto` | Pulls odds for each league that has a model, has started, is ready, has games in the next 36 h, and wasn't pulled today | 3 credits per league pulled |
| `betlab pull nfl ncaaf` | Pulls those leagues now, no checks | 3 each |
| `betlab pull --prime-time` | Evening check: NFL only, and only if a kickoff is 30–110 min away | 0 or 3 |
| `betlab card --dry-run` | Prices and prints the card; writes nothing | free |
| `betlab card` | Writes `exports/card*` and logs new picks | free |
| `betlab card --snapshot FILE --asof 2026-09-24T12:00` | Prices a specific snapshot as of a time | free |
| `betlab refresh` | Re-downloads this season's college games, lines and PPA | 6 CFBD calls |
| `betlab grade [--no-alert]` | Settles finished picks, computes CLV, writes `exports/results.json`; exits 3 and alerts the owner when lines are left ungraded (`--no-alert`: the worker's 3 AM run, no alert) | free |
| `betlab export-page` | Builds `exports/page_sync/` for the page sync | free |
| `betlab import-taken FILE` | Merges the page's taps (a JSON list) into the ledger | free |
| `betlab backtest nfl` | Walk-forward backtest, printed | free, about 15 s |

On Windows, set `PYTHONIOENCODING=utf-8` when a command prints polars tables.

## Run the pipeline locally, exactly like the cloud

```
betlab refresh
betlab grade
betlab pull --auto
betlab card
betlab export-page
```

Then commit, push and start the page sync: `gh workflow run sync-page.yml --repo mopsha/betlab`.
Anything you run locally and commit becomes part of the record, just like the bot's runs.

## Refit model settings

- Delete `data/models/nfl_params.json` or `data/models/ncaaf_params.json`. The next
  `card` or `grade` run refits from every completed game and saves new ones (about
  20–35 s).
- Before committing a refit, run the league's backtest and record the change and its
  evidence in `docs/MODEL_CHANGELOG.md`.
- Per-league rating settings (memory, shrinkage, early weeks) live in
  `cards/nfl.py` / `cards/ncaaf.py` (`base=GameParams(...)`). The NFL uses the
  `GameParams` defaults.

## Rebuild the college history (about 80 CFBD calls, about 2 minutes)

```
.venv\Scripts\python -c "from betlab.sources import cfbd; cfbd.refresh_reference(); cfbd.build_history(2014)"
```

Then delete `data/models/ncaaf_params.json` so the model refits on the rebuilt data.
Last rebuilt 2026-09-25 (101 seconds); compare the weights before and after, and log
any change in `docs/MODEL_CHANGELOG.md`.

## The page

- **Source:** `page/index.html`. It's published as the claude.ai artifact
  `6QKwcwXB9a5c3imy692S39`.
- **Publishing a change:** from a Claude session, call the Artifact tool with
  `file_path` = `page/index.html` and `url` = the artifact URL. Omit `capabilities` to
  keep `db` and `downloads`. Load the `artifact-design` and `artifact-capabilities`
  skills before editing. Details: `page/README.md`.
- **Refreshing its data now:** Actions tab → "sync page" → Run workflow, or
  `gh workflow run sync-page.yml --repo mopsha/betlab`.
- **Inspecting or seeding its database** from a Claude session: ArtifactData
  (`get`/`list`/`query`; `set`/`update`/`batch`). Writes to existing documents need
  `if_version` (read first).

## The page-sync routine

- **Where:** https://claude.ai/code/routines/trig_01AsDvmu7oHR6WcVyBvNSJLH. It has no
  schedule; the workflows start it through its API trigger.
- **Runs:** in a Claude session, use RemoteTrigger `list_runs` and then `get_run_log`
  on a session id. Mike can open the routine page on the web.
- **Changing its prompt:** RemoteTrigger `update` with the full `job_config`. Keep
  `docs/archive/ROUTINE_PROMPT.md` identical to what you send.
- **Connectors must stay empty.** Updates and edits can re-attach them; check
  `mcp_connections` and clear with `clear_mcp_connections: true`.
- **Token rotation (Mike does it):**
  1. Routine → Edit → API trigger → Regenerate.
  2. `gh secret set ROUTINE_TOKEN --repo mopsha/betlab`.

## When something breaks

| Symptom | Likely cause | Fix |
|---|---|---|
| GitHub emails "daily failed" | Check `gh run view <id> --log-failed` | Read the failing step; tests usually reproduce it locally |
| "page sync FAILED: HTTP 401/403" | `ROUTINE_TOKEN` revoked or regenerated | Mike regenerates it and re-sets the secret |
| Phone alert "BetLab: watchdog needs a look" | A feature reported zero all day, or a soft step swallowed an error (`watchdog.py`, the 9:55 daily) | `select step, log_tail from runs` for that day and step; the alert names the feature. A step that should be watched logs "N of M" |
| Phone alert "BetLab: disk needs a look" saying the volume fills in about N days | The last two weeks' growth (`health.disk_watch`, `data/disk_usage.csv`) | `railway volume list`; Mike grows `worker-volume` in the dashboard, or clear what grew |
| A bet was lost or changed by mistake | `bet_history` holds every change, with the row before and after (`select * from bet_history where bet_id = ...`); `data/backups/app_db.json` holds the database's daily copy, and git log on it every earlier day | Restore by hand through the Supabase connector: put back only the rows that are wrong, and read them first. Never restore a whole table over newer rows |
| Phone alert "BetLab: lock needs a look" | A slice with a ticket reached kickoff unlocked, or locked after it (`health.py`, every pregame tick) | Read that tick's `lock-due`, `fun` and `publish` rows in `runs`; a tick after kickoff still locks, so check the app has the ticket |
| Phone alert "BetLab: deploy needs a look" | A push under `src/` isn't on the worker 15 minutes later (`health.py`) | `railway deployment list --service worker`, status.railway.com; redeploy if it was skipped |
| Page stamps stale but runs green | The routine ran but did nothing useful | `get_run_log` on the latest run; "green" only means no infrastructure error |
| "ODDS_API_KEY is not set: skipping" in a cloud log | Secret missing | Mike re-adds it with `gh secret set` |
| `CreditBudgetExceeded` | Balance near the 50-credit reserve | Wait for the monthly reset, or Mike upgrades the plan (then raise `monthly_credits` in settings) |
| "NCAAF: pricing failed (...)" on the card | Data or name mismatch | Reproduce with `betlab card --dry-run`; check `cfbd.SCHOOL_ALIASES` for unmatched names |
| A league shows "no games priced" | Snapshot has events our games table doesn't (name mapping) | Compare `snap.home_team` with the mapping (`nflverse.team_abbr_by_name`, `cfbd.team_names`) |
| The app shows nothing new (no card, no fun tickets) but alerts still arrive | The worker's `publish` step fails (`runs`: step publish, exit 1), e.g. a published column with no migration (Oct 12) | Read `runs.log_tail`; add the migration (`supabase/migrations`, apply it), then queue `refresh_free` in `job_requests` to republish |
| A slip opens FanDuel with legs missing | A leg found no FanDuel outcome (`links.Matcher`), e.g. anytime TD legs before Oct 12 | Query the ticket's `body->legs` for legs without `link`; compare with the feed's outcome in the latest props snapshot |
| `git pull --rebase` refuses | Uncommitted local changes | Commit first, then pull |
| `UnicodeEncodeError` printing tables | Windows console encoding | `PYTHONIOENCODING=utf-8` |
| Evening check never pulls | Cron started too late, or no kickoff in the window | `gh run view` its log; widen `PRIME_TIME_WINDOW` in `cli.py` if delays are routine |

## Secrets

| Secret | Where | Used by |
|---|---|---|
| `ODDS_API_KEY` | GitHub secret + `.env` | `pull`, `pull-props`, `credits` (the free key; spent first) |
| `ODDS_API_KEY_PAID` | GitHub secret + `.env` | The $30 plan's key (bought 2026-09-24): used once the free key runs low, and always for historical backfills |
| `CFBD_API_KEY` | GitHub secret + `.env` | `refresh`, CFBD rebuilds |
| `ROUTINE_TOKEN` | GitHub secret only | `scripts/fire_page_sync.sh` |

Mike sets them with `gh secret set NAME --repo mopsha/betlab`, which prompts for the
value. Claude must never handle the values.

## Odds credit budget

- **Allowance:** two keys, spent in order (`settings.yaml` `odds_api.keys`): the free
  key's 500 credits (resets on the 1st), then the paid key's 20,000 (resets on the
  24th). `betlab credits` shows both. Historical calls always use the paid key.
- **How the guard works:**
  - `CreditGuard` reads the true balance from the API's response headers; `betlab
    credits` and every pull refresh it with a free `/sports` call.
  - The balance is persisted in `data/odds_api_usage.csv`.
  - Each key has its own guard and log (`data/odds_api_usage.csv` for free,
    `data/odds_api_usage_paid.csv` for paid) and its own reset day.
  - A call goes to the first key whose guard allows it; a 401 (out of credits)
    moves it to the next key. The paid key keeps a 50-credit reserve for closing lines.
- **Typical costs:**
  - 3 credits per league pull.
  - About 3 per prime-time evening check.
  - Props (`pull-props`: 4 main markets, 4 alt ladders, anytime TD) cost about 9 per
    NFL game. The evening check pulls them for the prime-time game (about 27 a week).
  - The daily run pulls NFL props once a day (games in the next 36 h) and again for
    games 30–110 minutes from kickoff: roughly 400 credits in a week with a full
    Sunday slate. The free key goes first, then the paid key.
  - Soccer (big five and MLS, from Sep 25): match result only, about 1 credit per
    league pull, only for leagues with matches in the next 36 h (daily run and the
    midday re-prices). Grading and CLV come free from football-data.co.uk.
  - College basketball (from Nov 2): about 3 credits per pull for the whole slate (spreads,
    totals, moneylines), once a day plus the midday re-prices. CBBD refresh: about 3 calls a
    day from Oct 28, plus 1 call once a season for last season's player lines. Rosters come
    from ESPN (free, about 365 requests and 2 minutes every 3 days, Oct–Dec).
  - NBA (from Oct 20): props about 12 credits a game (8 main markets and, since Sep 28, 4
    alt ladders for the fun tickets), pulled once 15–75 minutes before tip
    (`pull-props --league nba`), plus about 3 for the night's game lines, plus a few for
    closing prices on open picks. That's roughly 3,000 credits a month.
  - The historical prop backfill costs about 40 paid credits a game; 2025 weeks 3–18
    (240 games) used 9,603 on 2026-09-24.
- **The upgrade trigger** is in `ROADMAP.md`.

## Add a league (checklist)

1. **Data source:** `src/betlab/sources/<name>.py`. It returns a games table with the
   columns the football model expects:
   - identifiers: `game_id`, `season`, `week`, `date`
   - teams and venue: `home_team`, `away_team`, `neutral`
   - results: `home_pts`, `away_pts`, `margin`, `total`
   - lines and prices: `spread_line` (home favored +), `total_line`,
     `home_spread_odds`/`away_spread_odds`/`over_odds`/`under_odds`,
     `home_moneyline`/`away_moneyline`
   - extras: `home_rest`/`away_rest`, `home_epa`/`away_epa`

   A new sport (soccer, basketball) gets its own model module instead.
2. **League wrapper:** `src/betlab/cards/<league>.py` with a `LEAGUE` definition and
   `evaluate`/`load_model` wrappers, modeled on `cards/ncaaf.py`.
3. **Registration:**
   - Add the league to `EVALUATORS` and `ready()` in `cli.py`.
   - Add it to `leagues:` in `settings.yaml` (with its Odds API `sport_key` and start
     date).
   - Add it to `GRADERS` in `grading.py`.
4. **Evidence:** run a backtest (`backtest.py`), then record the settings in
   `docs/MODEL_CHANGELOG.md` and the reasoning in `docs/DECISIONS.md`.
5. **Tests and docs:** add tests, then update `CLAUDE.md`, the folder READMEs and
   `docs/ROADMAP.md`.

## The shared to-do list

It lives only in the page database (`todos` collection), not in git. Each document has
the fields `owner` (`claude`/`you`), `title`, `detail`, `due` (YYYY-MM-DD or null),
`status` (`open`/`done`), `done_at`, `order`, `created_at` and `added_by`
(`claude`/`page`).

In a Claude session:
- **Read it:** ArtifactData `query` with `where status == open`.
- **Tick an item off:** `update` with `{status: "done", done_at: <ISO time>}` and the
  document's `if_version`.
- **Add an item:** `set` under a new id (`c-...` for Claude, `u-...` for Mike).
