# src/betlab/sources/: outside data

Each module talks to one outside service and returns tidy pandas tables. What
each service offers, its costs and quirks: `docs/DATA_SOURCES.md`.

| File | Service | Key names |
|---|---|---|
| `novig.py` | Novig's public catalog (free, no key; Oct 22) | `add_rows` (a soccer pull's Novig rows: 3-way result and totals, buy price = 1 - the other side's bid, bet limit, order-slip link), `events`, `markets`, `match`; read-only |
| `odds_api.py` | The Odds API | `OddsApiClient` (`sync_balance`, `events`, `odds`, `event_odds`), `CreditGuard` (budget and persisted balance), `estimate_cost`, `flatten` (JSON → one row per book/market/outcome), `save_snapshot`, `SNAPSHOT_COLUMNS`, `GAME_MARKETS` |
| `nflverse.py` | nflverse via `nflreadpy` | `load_games()` (schedules, scores, closing lines, kickoff in ET, `neutral`), `load_team_epa(seasons)`, `games_with_epa(first_season)` (the NFL games table the model uses), `team_abbr_by_name()` (sportsbook name → code), player stats, snap counts (offense and defense), weekly rosters, injuries, `load_pbp`, `load_qb_depth(season)` (QB order on the latest depth chart), `load_weather(seasons)` (past kickoff weather); `load_snap_counts_all` and `load_player_stats_all` (every player incl. linemen and defenders, with sacks and QB hits: for `injuries_nfl`) |
| `cbbd.py` | CollegeBasketballData (same key as CFBD) | `build_history`, `refresh_recent` (last 10 days and the next week, about 3 calls; the daily run from Oct 28), `games`, `schedule` (with venue states), `team_games`, `teams`, `team_names` (the odds feed's names, "Florida St Seminoles", mapped to schools; checked on 326 real names), `players` (player season lines with PORPAG, 1 call a season), `rosters`, `refresh_rosters` (this season's from ESPN's free roster pages, every 3 days Oct–Dec) |
| `soccer.py` | football-data.co.uk (free CSVs) | `load(league, seasons)` (scores, shots on target, Pinnacle early and closing odds, Betfair Exchange and average closes), `closing_1x2`, `no_vig`, `season_code`, `current_season` |
| `nhl.py` | NHL stats API and web API (free); ESPN's site API for DraftKings' lines and the probable goalies | `load_team_games` (goals with the shootout goal removed, shots, 5-on-5 attempts, empty-net goals), `load_goalie_games`, `schedule`, `scoreboard` (today's lines and goalies), `backfill_lines`/`load_lines` (past opens and closes, `data/history/nhl_lines.parquet`), `current_season`; cached in `data/cache/nhl/` |
| `espn_odds.py` | ESPN's site API (free) | `snapshot`: DraftKings' game lines in the Odds API's flat format (bookmaker `draftkings`); college basketball's lines until `paid_odds_from` |
| `nba.py` | sportsdataverse (GitHub releases; free); ESPN's site API for live data | `load_schedules`, `load_team_box`, `load_player_box` (All-Star games dropped), `load_injuries`, `injuries_now` (live report with a `sits` flag), `rosters_now`, `current_season` (seasons named by the year they end; cached in `data/cache/nba/`) |
| `weather.py` | Open-Meteo (free, no key) | `venue(stadium_id, stadium)` from `config/stadiums.yaml`, `forecast(lat, lon, kickoff)`: temperature, wind, gusts, chance of rain or snow over the three hours from kickoff |
| `cfbd.py` | CollegeFootballData v2 | `games()` (the college games table: FBS-involved games, bowl weeks renumbered, rest days, −110 placeholders, sanitized moneylines, venue state), `build_history`, `refresh_current`, `refresh_reference` (teams and venues), `team_names()` (sportsbook name → CFBD school), `SCHOOL_ALIASES` |

## The games-table contract

Both `games_with_epa()` and `cfbd.games()` return these columns, which the
football model and grading rely on:

- **Identifiers:** `game_id`, `season`, `week`, `date` (naive ET date), `kickoff`
  (tz-aware ET).
- **Teams and venue:** `home_team`, `away_team`, `neutral`.
- **Results:** `home_pts`, `away_pts`, `margin` (home minus away; NaN until played),
  `total`.
- **Lines:** `spread_line` (**positive = home favored**), `total_line`.
- **Prices:** `home_spread_odds`, `away_spread_odds`, `over_odds`, `under_odds`,
  `home_moneyline`, `away_moneyline`.
- **Model extras:** `home_rest`, `away_rest`, `home_epa`, `away_epa`.
- **College only:** `venue_state`, `spread_open`, `total_open`, `home_div`,
  `away_div`, `season_type`.

## Rules

- Never print or log a request URL that contains a key.
- Keys come only from `config.secret()`, which reads the environment or `.env`.
- Anything cached to disk goes under `data/` (committed if small, `data/cache/` if not).

`espn_ufc.py`: UFC cards, results and the sportsbook's prices from ESPN's free fight center (Oct 23): `scheduled(day)` (segment starts, rounds), `event`/`fights` (results to the second; DraftKings' moneyline, method, total rounds, distance for recent events only), `history(years)` (cached gzipped), `same_fight`/`find` (last-name matching). Feeds `cards/ufc.py` and `grading.grade_ufc`.
