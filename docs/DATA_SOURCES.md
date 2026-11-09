# Data sources

The outside services BetLab calls: what each gives us, what it costs, and the
quirks we've hit. File formats of what we store are in `data/README.md` and
`exports/README.md`.

## The Odds API (odds for FanDuel and other books)

- **Code:** `src/betlab/sources/odds_api.py` (`OddsApiClient`, `CreditGuard`, `flatten`,
  `save_snapshot`).
- **Base URL:** `https://api.the-odds-api.com/v4`. The key goes in the `apiKey` query
  parameter, and `ODDS_API_KEY` supplies it.
- **Plan:** two keys since 2026-09-24: the free Starter key (500 credits a month) is
  spent first, then the $30 plan's key (20K a month, renews on the 24th). Other paid
  plans: $59 for 100K, $119 for 5M, $249 for 15M. Historical data is on all paid plans.

**Endpoints and costs:**

| Endpoint | Used by | Cost |
|---|---|---|
| `GET /sports` | `sync_balance()` | free (returns the balance headers) |
| `GET /sports/{sport}/events` | `pull --auto` / `--prime-time` checks | free |
| `GET /sports/{sport}/odds` | every pull (`markets=h2h,spreads,totals`) | markets × regions → **3** |
| `GET /sports/{sport}/events/{id}/odds` | `pull-props` (NFL props, alt ladders, anytime TD) | unique markets returned × regions → about **9** per NFL game |
| `GET /historical/...` | `historical_events` + `historical_event_odds` (`betlab backfill props`; paid key only; 2025 weeks 3–18 done: `data/odds_history/`) | 10× the normal cost; game data from June 2020, props from May 3, 2023 |

**Bookmakers and regions:** asking for up to 10 named books counts as a single region.
We ask for
`fanduel, draftkings, betmgm, williamhill_us, fanatics, betrivers, pinnacle, lowvig,
betonlineag, novig` (`settings.yaml`). That puts Pinnacle, which normally sits in the
EU region, and Novig (the `us_ex` exchanges region) in the same call for no extra cost.
Novig replaced Bovada on Oct 22: an 11th book would double every pull. Every call also asks
for `includeBetLimits` (free): an exchange's price comes with the dollars available at it,
saved in the snapshot's `bet_limit` column. Novig's outcome links end in `{wager}`, the stake
its order slip fills in (`links.book_link` puts in `odds_api.novig.default_wager`, $5).

**Novig's public catalog** (free, no key, `sources/novig.py`, Oct 22): the Odds API carries Novig's US sports but
none of its soccer, so soccer pulls (pregame and the daily) add Novig's 3-way result and goal totals from
`api.novig.com/v3/public/catalog` (`events`, then `markets?event=`; throttled per IP, about one call per match).
A side's buy price is 1 minus the best bid on its other side. Pregame fills pay no fee (only live ones do:
0.06 x P(1 - P) per $1 contract for the taker). Novig also publishes each day's trades and markets as CSV
(`/reporting/trade-data/`), for a later look at whether its prices lag the sharp books. The catalog takes about 10
reads in a burst, then answers 429 with `Retry-After: 1` (Oct 28): `novig._get` spaces reads 0.15 s and waits as told.

**Novig's parlay pricer** (free, no key, `novig_parlays.py`; web `api/novig`, iPhone `Novig.swift`): since Oct 30
`POST api.novig.com/rfq/v2/quote/unauthenticated` with `{"outcomeIds": [...]}` (2-20) answers `{price, expiresAt,
serverNow}`, the price a probability; 400 = legs it won't combine, 404 = no price right now, 429 = over its limit (a
burst of 10, then 1 a second, `Retry-After`). It no longer gives the largest payout. The Oct 28 route
(`/nbx/v1/parlay/request/unauthenticated`, `{"outcomes": [{"id"}]}`, with `maxCashPayout`) was gone by Oct 29 (404
"Cannot POST"). 3 at a time, each answer kept 30 minutes. Docs: docs.novig.com, Affiliates > Parlay Pricing; which legs
combine and how a parlay settles: RFQ > Eligibility, Settlement.

**Balance headers:** `x-requests-remaining`, `x-requests-used` and `x-requests-last`.
`CreditGuard` persists them to `data/odds_api_usage.csv`.

**Quirks:**
- **Coverage:** Pinnacle posts only the current NFL week, so later weeks fall back to
  a consensus of the other books.
- **Props:** player props come from US books. Soccer player props cover the Premier
  League, Ligue 1, Bundesliga, Serie A, La Liga and MLS. The European cups (checked Oct 12, one Champions League
  match): FanDuel posts shots, on target, scorer, assists and score-or-assist; DraftKings the scorer; Pinnacle goals
  and BTTS but no scorer price.
- **Error messages must never show the request URL,** because it contains the key.
  The client raises `OddsApiError` with the path and status only.

## nflverse (NFL schedules, results, closing lines, stats)

- **Code:** `src/betlab/sources/nflverse.py`, via the `nflreadpy` package (free, no
  key, returns polars frames).
- **`load_schedules()`:** every game with scores and nflverse's closing lines. It
  covers 2006 onward in our use.
  - **Sign convention:** `spread_line` is from the home side, **positive when the home
    team is favored**, and `result` is the home margin.
  - **Other columns:** `total_line`, `home_moneyline`/`away_moneyline`,
    `home_spread_odds`/`away_spread_odds`, `over_odds`/`under_odds`,
    `home_rest`/`away_rest`, `location` ("Neutral"), `gameday` and `gametime`
    (Eastern).
- **`load_team_stats(seasons)`:** weekly team stats; EPA per play is computed from
  `passing_epa + rushing_epa` over dropbacks and carries.
- **`load_teams()`:** full names and abbreviations. Relocated teams map to their
  current codes: OAK→LV, SD→LAC, STL→LA, and "Los Angeles Rams"→LA.
- **`load_player_stats()`** (wrapped as `nflverse.load_player_stats`, with TDs) and
  **`load_snap_counts()`:** for the props model. Snap counts use PFR ids, not GSIS ids,
  so joining them needs an id map (to-do).
  nflverse posts a game's stats the morning after; until then the fun ledger grades a finished game
  from ESPN's box score (`fun_ledger.with_espn`, Oct 27).
- **`load_rosters_weekly()`:** each week's roster with `status` (ACT, INA, RES...) and
  gsis/pfr ids; the fun parlays match book names within it.
- **`load_pbp()`** (wrapped as `nflverse.load_pbp`, only `game_nfl.PBP_COLUMNS`):
  play-by-play for the game-flow engine's team-game stats. Three seasons load in about
  8 seconds.
- **`load_depth_charts()`** (wrapped as `nflverse.load_qb_depth`): ESPN depth charts,
  snapshotted about twice a day; the Game Previews take each team's QB order from the
  latest snapshot.
- **Weather history** (`nflverse.load_weather`): the schedule's `roof`, `temp` and
  `wind` plus the play-by-play `weather` text (rain, snow, showers, drizzle, sleet).
- **`load_injuries()`:** the official weekly injury report (`report_status` Out,
  Doubtful, Questionable). The game simulator removes Out/Doubtful players and hands
  their volume to teammates; Questionable players are flagged on the page.
- **Freshness:** lines update through the week, and results arrive the day after
  games.

### CollegeFootballData additions (2026-09-25)

- **`/stats/game/advanced`** (`cfbd.build_advanced`, `refresh_advanced_current`): per
  team-game EPA, success rate, explosiveness, pass/run splits, line yards, stuff rate,
  plays; 2 calls a season, saved to `data/history/ncaaf_advanced.parquet`, refreshed daily
  by `betlab refresh` (2 calls).
- **`/venues`** now also saves name, latitude, longitude and dome (`refresh_reference`),
  for college kickoff weather.
- CFBD's free tier allows 1,000 calls a month; the daily run uses about 8.

## NHL APIs and ESPN (NHL data and free lines)

- **Code:** `src/betlab/sources/nhl.py` (and `espn_odds.py` for college basketball); cached in
  `data/cache/nhl/` (not committed). Free, no key, no odds credits.
- **NHL stats API** (`api.nhle.com/stats/rest/en/...`): `team/summary`, `team/summaryshooting`,
  `team/realtime` and `goalie/summary` with `isGame=true&limit=-1`, one call each per season,
  give every team-game and goalie-game. The team rows carry no abbreviation; the opponent's
  row in the same game does.
- **NHL web API** (`api-web.nhle.com/v1/schedule/<date>`): the week's schedule with game ids
  and start times (redirects: follow them). It lists goalie leaders, not tonight's starter.
- **ESPN** (`site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard`): one book's line
  (DraftKings) for each upcoming game: moneyline, puck line and total with prices, open and
  current; and each team's `probableStartingGoalie` with a status (confirmed, expected,
  probable). The `summary?event=` endpoint keeps the open and close after the game (2025-26
  on; 2024-25 has none; 2022-24 carry Unibet numbers that aren't real two-way prices).
- **The Odds API** (`icehockey_nhl`, from Oct 1): game lines for FanDuel and the sharp books
  (about 3 credits a pull) and `player_shots_on_goal` props per game (about 1 credit).
- **Betslip links:** every Odds API odds request sends `includeLinks=true&includeSids=true` (no extra
  credits); FanDuel's outcomes come back with `addToBetslip?marketId=..&selectionId=..` links, saved
  in each snapshot's `link` column (`links.py`).
- **Skater shots** for grading shots legs: the stats API's `skater/summary` with
  `cayenneExp=gameId=<id>` (`nhl.skater_shots`).
- **College basketball** uses the same scoreboard (`basketball/mens-college-basketball`,
  `groups=50&limit=500`) before `leagues.ncaab.paid_odds_from` (Oct 26 since Oct 15, so the Odds API from the
  Nov 2 opener; was Mar 1): ESPN's team names match
  our map for 262 of 264 teams.

## sportsdataverse (NBA data)

- **Code:** `src/betlab/sources/nba.py`; cached in `data/cache/nba/` (not committed).
- **What:** ESPN schedules, team and player box scores (2002 on), the daily injury report
  and depth charts, plus stats.nba.com mirrors (lineups, matchups, game logs), as parquet
  files on `github.com/sportsdataverse/sportsdataverse-data` releases. Free, no key, and it
  works from the cloud (stats.nba.com itself blocks cloud IPs).
- **Not included:** historical betting lines (ESPN's game files have empty odds for past
  games). See `docs/NBA_PLAN.md`.
- **All-Star games** are labeled regular season in these files; `sources/nba.py` keeps only
  games between the 30 franchises (`NBA_TEAMS`).
- **ESPN's site API** (`site.api.espn.com/apis/site/v2/sports/basketball/nba/...`, free, no
  key) supplies what the daily files can't:
  - tonight's injury report (`injuries`, via `nba.injuries_now`)
  - current rosters (`teams/{id}/roster`, via `nba.rosters_now`)
  - the scoreboard that `scripts/nba_window.py` checks before an NBA run

## Open-Meteo (kickoff weather forecasts)

- **Code:** `src/betlab/sources/weather.py`; venues in `config/stadiums.yaml`.
- **What:** hourly temperature, wind, gusts and chance of rain or snow, 16 days ahead,
  from `https://api.open-meteo.com/v1/forecast`. Free, no key, no account.
- **Use:** only outdoor venues; the preview averages the three hours from kickoff.
- **If it fails:** the preview says the forecast isn't in and applies no weather.

## CollegeFootballData (college games, lines, efficiency)

- **Code:** `src/betlab/sources/cfbd.py`.
- **Base URL:** `https://apinext.collegefootballdata.com` (API v2), with
  `Authorization: Bearer <CFBD_API_KEY>`. The key is free.
- **Endpoints:** `/games`, `/lines` and `/ppa/games` (each for regular and postseason),
  plus `/teams` and `/venues`. Responses are camelCase; `_snake()` normalizes them.
- **Calls:** the daily `refresh` makes 6; a full rebuild from 2014 makes about 80.
- **Lines:** there are several providers per game and we take the median. **CFBD's
  `spread` is negative when the home team is favored,** so we flip it into
  `spread_line`. Moneylines are averaged as probabilities, never as prices.
- **Data quirks:**
  - Impossible moneyline pairs appear (e.g. −75000/−48000) and are dropped by a sanity
    check (implied probabilities summing to 98–120%).
  - Games include Division II/III, so `games()` keeps only games involving an FBS
    team.
  - Bowl weeks are renumbered to 21+ so they don't merge with week 1.
- **Team names:** sportsbooks say "Syracuse Orange" and CFBD says "Syracuse".
  `team_names()` matches "school mascot" first, then the longest school prefix, then
  `SCHOOL_ALIASES` (App State, UMass, LIU, William & Mary).

## football-data.co.uk (soccer results, shots and odds)

- **Code:** `src/betlab/sources/soccer.py`; cached in `data/cache/soccer/` (not
  committed). Free CSVs, no key, cloud-safe.
- **What:** one file per big-five league and season (`mmz4281/2425/E0.csv`), and one file
  per "extra" league across seasons (`new/USA.csv` for MLS).
  - Big five: score, shots and shots on target, and many books' odds. That includes
    Pinnacle's 1X2, over/under 2.5 and Asian handicap odds when collected (a day or
    more before kickoff) and at the close.
  - MLS: score and closing odds only.
- **Pinnacle stopped public odds in 2025:** its closing columns run through 2024–25 and
  about half of 2025–26. After that the sharp reference is Betfair Exchange's close
  (`BFEC*`), then the books' average (`sources/soccer.closing_1x2`).

## CollegeBasketballData (college basketball games, box scores, lines)

- **Code:** `src/betlab/sources/cbbd.py`. Same key as CFBD (`CFBD_API_KEY`); about 25 calls
  a season (date windows: the API returns at most 3,000 rows a call).
- **Saved:** `data/history/ncaab_games.parquet` (games, CBBD's pregame Elo, closing lines
  median across providers, moneylines averaged as probabilities, openers) and
  `data/history/ncaab_team_games.parquet` (possessions, pace, offensive rating, four
  factors per team-game), 2021-22 to 2025-26.
- **Lines:** closing lines every season (ESPN BET, TeamRankings, a consensus); openers
  only from 2024-25 (partial) and 2025-26 (Bovada, DraftKings).
- **Players and rosters** (for the early-season roster shift): `/stats/player/season`
  returns every player in one call (PORPAG, minutes, games; `athleteSourceId` is ESPN's
  id), saved to `data/history/ncaab_players.parquet`. `/teams/roster` gives past
  rosters (1 call a season) but was empty for 2026-27 on Sep 26, so the current season
  comes from ESPN's free roster pages
  (`site.api.espn.com/.../mens-college-basketball/teams/{id}/roster`, one request per
  team, ids from CBBD's `teamSourceId`), saved to `data/history/ncaab_rosters.parquet`.
- **Call budget:** the key is shared with CFBD and has a monthly call limit; 489 were left on
  Sep 26 after the rebuilds. The response header `X-CallLimit-Remaining` shows it.

## Planned sources (not yet in code)

| Source | For | Notes |
|---|---|---|
| Understat | xG for the big five leagues | Scraped JSON |
| American Soccer Analysis | MLS xG | `itscalledsoccer` package |
| ClubElo | Cross-league soccer ratings (Champions League) | Free CSV API |
| cdn.nba.com, ESPN | NBA schedules, box scores, odds in CI | stats.nba.com blocks cloud IPs; use `nba_api` only locally |
| CollegeBasketballData, Barttorvik | College basketball | Same author as CFBD |
