# NBA plan: ML-first, paper from opening night (Oct 20, 2026)

Status (Tue Oct 13, 2026): built and rehearsed; opening night Oct 20 runs on the Railway worker at both books
(FanDuel and DraftKings). Oct 13 dry run on the real schedule: each game pulled once at 45 minutes and given a closing
look 15 minutes before tip; tip windows now come from the night's full schedule (they had regrouped mid-night on
Oct 21's 11 games). The ML layer comes mid-November.

Mike, 2026-09-25: "ML for NBA will be the move cause there's SOOOOO many games." About 1,230
regular-season games and hundreds of player props a night give a model enough rows to learn
from within weeks. The NFL can't offer that.

The evidence rules are the same as everywhere else: the market's price is the baseline, and
a model earns weight only by beating it out of sample (CLAUDE.md rule 3). The NBA starts as
paper and gets its own go-live checklist; it can't pass by Oct 18.

## Data

| What | Source | Cost | Status |
|---|---|---|---|
| Schedules, scores, team and player box scores (2002 on), injuries (daily), depth charts, play-by-play | sportsdataverse's GitHub releases (ESPN), `sources/nba.py` | Free; works from the cloud (stats.nba.com blocks cloud IPs) | Loader built 2026-09-25; All-Star games dropped. The current season's files lag (Oct 19: 2027 box files 404, no scores), so its finished games come from ESPN's scoreboard and game summaries (Oct 19) |
| Tonight's injury report and current rosters | ESPN's public site API (`nba.injuries_now`, `nba.rosters_now`) | Free, no key | Built 2026-09-25 |
| Lineups, matchups, hustle, possessions, game logs | sportsdataverse's stats.nba.com mirrors (`nba_stats_*` releases) | Free | Available; wire in when a feature needs it |
| Live game lines and player props | The Odds API (`basketball_nba`) | Game lines about 3 credits a pull; props about 8 credits a game (points, rebounds, assists, threes and the four combos), about 60–75 a night with the lines | From opening night (`betlab pull-props --league nba`) |
| **Historical betting lines** | **None free.** ESPN's game files have empty odds for past games | The Odds API's historical game lines: about 30 credits a day (3 markets); a full 2025–26 season ≈ 5,000 credits, every third day ≈ 1,700 | **Mike's decision** (see below) |

## Models

1. **Team model (game lines).** Opponent-adjusted ratings from box scores: offensive and
   defensive efficiency, pace, the four factors, home court, rest and back-to-backs, travel,
   and injuries measured as the minutes and value of absent players. It predicts margin and
   total.
2. **Player model (props).** A minutes model (role, starter, rotation changes, injuries around
   him, blowout risk from the spread) times per-minute rates (recency-weighted,
   opponent-adjusted, pace-adjusted). The distributions come from simulation, so points,
   rebounds, assists, threes and combos stay consistent. This is the NFL props design
   (v0.2) adapted to basketball.
3. **ML layer (the "beat the market" part).** The target is over/under (or cover), with the
   market's no-vig log-odds as a fixed offset, so the model learns only what the market
   misses. Features: 1–2's projections vs the line, role changes, rest, injuries, pace
   matchups, line movement. Regularized logistic first; gradient-boosted trees (LightGBM)
   only if they beat it out of sample.

## Results so far (`betlab backtest nba`, fit on 2024-25, tested on all of 2025-26)

| | Model | Naive baseline |
|---|---|---|
| Game margin, mean absolute error (1,224 games) | **11.45** | 13.14 (home court only) |
| Game total, mean absolute error | **15.13** | 15.87 (league average) |
| Player minutes, MAE (20,424 games by regulars) | **4.90** | 5.06 (last-10 average) |
| Points: log loss at a typical line (last-10 median + 0.5) | **0.665** | 0.679 |
| Rebounds | **0.630** | 0.651 |
| Assists | **0.621** | 0.640 |
| Threes | **0.560** | 0.588 |

- The whole-distribution error (CRPS) is 2–3% better than the naive baseline on every stat,
  and bias is under 0.13 on every stat.
- Back-to-backs cost 2.2 points per 100 possessions (fit on 2024-25).
- Teammates ruled out add minutes: about +1.6 for 30 missing teammate minutes.
- v1 was overconfident at the extremes (its 77% points overs hit 66%). Per-stat calibration
  settings chosen on 2024-25 fixed most of it: damped matchup and pace, a blend with the
  last-10 average, and wider distributions for points.
- Closing lines usually miss the NBA margin by about 10 points, so the team model alone
  won't beat the market (it doesn't know about injuries or lineups yet). The ML layer's job
  is to find what the market misses, tested on lines logged from opening night.

### Player model v2 (Sep 25): what moved the needle

Log loss at a typical prop line (lower is better), fit and calibrated on 2024-25, tested on
2025-26 (20,424 games by regulars):

| Variant | Minutes MAE | Points | Rebounds | Assists | Threes | PRA | P+R | P+A | R+A |
|---|---|---|---|---|---|---|---|---|---|
| v1 | 4.90 | .6652 | .6299 | .6208 | .5604 | .6661 | .6628 | .6673 | .6469 |
| v2: usage when teammates sit, blowout minutes | 4.89 | .6649 | .6294 | .6208 | .5603 | .6657 | .6624 | .6669 | .6467 |
| **v2 + tonight's starting lineup** | **4.57** | **.6564** | **.6230** | **.6132** | **.5583** | **.6527** | **.6509** | **.6554** | **.6362** |
| Naive last-10 average | 5.06 | .6787 | .6506 | .6403 | .5875 | .6814 | .6793 | .6815 | .6652 |

- **Usage** is real but small: with 30% of the team's usual scoring out, a player's
  points go up about 3% and assists 5% (on top of the extra minutes).
- **Blowouts:** starters lose about 0.8 minutes per 10 points of expected margin; the bench
  gains a little.
- **The starting lineup is the biggest single lever** (minutes error −7%, every stat and
  combo better). **So NBA props are priced after lineups are announced (about 30 minutes
  before tip)**, like NFL props after inactives. Both settings are saved
  (`data/models/nba_player.json`: `pre_lineup` for earlier prices, `lineup` after).
- Calibration at the extremes improved: its 77% points overs now hit 71% (v1: 66%).

### Player model v3 (Sep 25): candidates tested, one kept

Same test (fit and calibrated on 2024-25, scored on 2025-26):

| Candidate | Result | Verdict |
|---|---|---|
| **Returning from missed games** (games missed right before tonight, capped at 5; a long-absence flag) | Minutes error for returning players 6.55 → 6.13 (−6%); overall 4.89 → 4.87; points .6649 → .6647, rebounds .6294 → .6289, PRA .6657 → .6654 | **Kept** (v3) |
| Position-specific defense (what a defense allows to guards, forwards, centers) | Worse on every stat (points .6649 → .6665, PRA .6657 → .6680) | Dropped: too noisy |
| Recent form (a 4-game-memory rate blended with the 15-game one) | Tuning on 2024-25 chose not to use it; no change | Dropped |
| Team model: road-trip length, rest differences beyond back-to-backs | Margin residuals within noise (±0.4 pts, SE 0.4–1.3) | Nothing to add |

Players coming back lose about 1.2 minutes per game missed; after 5+ games out, part of
that eases. **v3 with tonight's lineup** is the best version: minutes error 4.55, points
.6560, rebounds .6225, assists .6133, threes .5583, PRA .6523 (naive: 5.06, .6787, .6506,
.6403, .5875, .6814). `data/models/nba_player.json` holds v3 `pre_lineup` and `lineup`.

**Data fix, Sep 25 evening: All-Star games dropped.** ESPN labels All-Star games as
regular season (teams "EAST"/"WEST" in 2024, four mini-teams in 2025, "STARS"/"STRIPES"/
"WORLD" in 2026), so they were in every feature. Kevin Durant's last 10 games before
March 2 held three 6–12 minute All-Star mini-games (0, 7 and 5 points). That dragged the
stars' averages for weeks after the break, and the stars get the most props. Only games
between the 30 franchises are kept now (`nba.NBA_TEAMS`). Refit, same test: v3 with lineup
minutes error 4.48 (naive 4.96), points .6561 (naive .6781), rebounds .6232, assists
.6130, threes .5584, PRA .6522 (naive .6803). The naive baseline improved too, so part
of the minutes gain is a cleaner test set. The log losses barely moved because it is
about 25 players × 10 games out of 20,000.

## The live pipeline (built Sep 25; runs from Oct 20)

How a night works, from the "BetLab tick: NBA" routine to the tracker:

1. **When:** the tick routine fires at 20 past the hour, 22:20–02:20 UTC. That covers
   6:20–10:20 PM ET in daylight time and 5:20–9:20 PM ET in standard time. Each run
   prices the games tipping **15–75 minutes** later. Tip-offs are on the hour or half
   hour, so every game lands in exactly one run, close to lineups and after most injury
   news. `nba.yml` first checks ESPN's free scoreboard (no installs, no credits), so a run
   with nothing to do takes seconds.
2. **Pull** (`betlab pull-props --league nba`):
   - those games' props, about 8 credits a game
   - the night's game lines, about 3 credits; their spreads feed the blowout feature, and
     they're the close for the card's game-line picks and leans (`grading.nba_close`). The
     morning daily run also pulls the day's lines (`pull --auto`, ~3 credits) for the card
   - for any game with open NBA prop picks or leans that hasn't tipped yet, just the
     picked markets again. That later price is the pick's close.

   The pull does nothing before `settings.yaml`'s NBA start date (Oct 20).
3. **Tonight's players** (`models/live_nba.py`):
   - Rosters are ESPN's current ones, so offseason and deadline moves count.
   - Players "Out" on ESPN's live injury report sit. So do "Day-To-Day" players whose
     fresh note says they were ruled out, and anyone whose expected return is 3+ days
     away. Everyone else day-to-day plays and is flagged.
   - Tonight's rows go through the backtest's feature code as "pending" rows.
     `validate_on` replays a past night and checks the live features against the
     backtest's: they match (checked on Jan 15 and Mar 2, 2026).
   - Lineups aren't known yet, so the `pre_lineup` settings price everything.
4. **Pricing** (`cards/props_nba.py`, on the card; paper):
   - p_market is the sharp book's no-vig price at FanDuel's line. A quote at another
     line is moved to FanDuel's with the model's negative binomial shape.
   - p_model is v3's chance.
   - The model's weight is 0 (rule 3), so picks come only from FanDuel lagging the
     market, under the normal props thresholds.
5. **Tracker** (`tracking_nba.py`, `data/ledger/nba_prop_lines.csv`): every FanDuel main
   line, with FanDuel's prices, the market, the model and every feature. The next
   morning's `betlab grade` adds the result from box scores. **This is the ML layer's
   training set.**
6. **Grading:** NBA prop picks settle from ESPN box scores; a player who didn't play
   voids. CLV uses only a snapshot taken after the pick. Picks whose game had no later
   pull get no CLV and don't count toward the go-live checklist.

A replay of Mar 2, 2026 (4 games, synthetic odds) priced and tracked 156 lines in about 4
seconds.

**Built Sep 28:**
- **The page's NBA view:** the Games tab's NBA switch, from `app/nba`. It shows every line
  priced tonight with the market's and the model's chances, and the model's running record.
- **NBA fun:** one SGP+ ticket per window, and overs to root for in national-TV games, from
  `app/fun_nba`. ESPN's scoreboard gives national TV for free. See `docs/MODELS.md`.
  Since Oct 21 a night has fixed slices (afternoon, early before 9 PM, late: `sgp_plus.SLICES["nba"]`; 30-minute tip
  windows from Oct 10), each pulled whole 15-45 minutes before its first tip (`pregame.due_by_slice`), with a regular
  and a likelier SGP+ ticket and a Knicks game's own slips; a news re-pull merges into it (`fun_nba.merge`), and its
  tickets lock at the first tick within 25 minutes of its first tip, with a notification (`sgp_plus.keep_tickets`).
- **Alt ladders:** added to the pull for the tickets' 55-80% legs (+4 credits a game).
- **Grading:** NBA tickets grade from ESPN box scores (`fun_ledger._grade_nba`).

**The lineup source (Sep 28):**
- **Where it comes from:** nba.com's "Today's Lineups" file
  (`stats.nba.com/js/data/leaders/00_daily_lineups_YYYYMMDD.json`, `nba.lineups`). It's a
  static file on nba.com's CDN, not the stats API that blocks cloud servers.
- **What it holds:** per game, each team's players, with a position filled in only for
  the five starters, "Confirmed" or "Expected", and "Active" or "Inactive".
- **How pricing uses it** (`props_nba.confirmed_lineups`):
  - A game whose two lineups are Confirmed, with all ten starters matched to ESPN ids, is
    priced with the `lineup` settings.
  - Its Inactive players sit.
  - "Expected" lineups are never used.
  - Other games use `pre_lineup`.
  - The tracker logs `lineup_known` and `starter_now`, and the card notes how many games
    had confirmed lineups.
- **Replaying five 2025-26 nights with the real files:**
  - The lineup was known for 90-100% of lines.
  - Minutes error went 4.33 → 4.17, 4.99 → 5.13, 4.53 → 4.42, 4.45 → 4.19 and 5.77 → 5.77.
  - That's about 0.12 minutes, roughly 3%, against the backtest's 7%. The replays had no
    injury report.

**Still open before opening night:**
- **A live test in preseason (Oct 3–17).** Two lineup questions:
  - *Can GitHub's runners reach nba.com's lineup file?* **Yes** (Sep 29, the `nba reach`
    workflow: HTTP 200 in 0.3 s, 387 players parsed through `nba.lineups`).
  - *How early are lineups Confirmed?* The run prices games 15-75 minutes before tip. If
    confirmation usually comes later, the NBA tick should price closer to tip. Last
    season's archived files can't answer it: every timestamp is the final update, about
    2.5 hours *after* tip (27 sampled days, 408 team-games). So `scripts/lineup_watch.py`
    watches it live on Oct 5 (5 games) and Oct 6 (4 games), started by one-time tick
    routines at 21:00 UTC. It polls every 5 minutes and records when each team's starters
    were first Expected and first Confirmed. About 60 minutes before the first tip it also
    probes one game's preseason props (`basketball_nba_preseason`, about 8 credits): do
    FanDuel props come through the feed at all? Results go to `data/lineup_watch/<day>.json`,
    **Result (Oct 6 only; Oct 5's run never got a runner):** 8 teams, starters Confirmed 8-28 minutes
    before tip (one at 73); 1 of 8 by 30 minutes, 7 of 8 by 15. No book had preseason props. The
    run's push failed, so the numbers were recovered from its log into `data/lineup_watch/20261006.json`.
    Since the worker cutover the NBA window is `schedule.pregame.nba` [15, 45]: the first pull lands
    30-45 minutes out on Expected lineups, and the tick 15 minutes before tip re-pulls when a team's
    starters turn Confirmed (`news.py` fingerprints lineup status). That caught both teams in 3 of the
    4 games, so the window stays. Recheck on opening week's runs log.
    and a one-time check the next morning writes them to the to-do list.
  - Preseason games aren't run through the card or the tracker on purpose: preseason
    lines would pollute the ML layer's training set.
- **Checking the injury "sits" rule against October box scores.** Done Oct 8 on 22 preseason games
  (Oct 3-8; ESPN summaries, each day's injury snapshot): all 61 player-games the rule sat (Out, a
  fresh ruled-out note, or a return 3+ days away) sat. Day-To-Day played only 22 of 55 (preseason
  rest). The rule stays: once a game's lineups are Confirmed, nba.com's Inactives join the sitters
  (`cards/props_nba.py`), so the Day-To-Day guess only shapes the first pull, 30-45 minutes out, and
  the Confirmed re-pull replaces it. Recheck Day-To-Day in opening week's regular-season games.

## Evaluation

- 1–2 are backtested now on 2024–26 box scores (no market needed): minutes error, CRPS, and
  calibration at typical prop lines.
- The ML layer is trained walk-forward by date on **logged lines**: every FanDuel NBA line
  from opening night, with features and results (the NFL prop tracker's design). It's
  scored by log loss vs the market, the favored side's hit rate, and CLV. It needs about 3–4
  weeks of nights (≈ 10,000 prop lines) before v1.
- For game lines, last season's historical lines (if bought) give a before-opening-night
  test; otherwise the first weeks of logged lines do.

## Timeline

| When | What |
|---|---|
| Sep 25 | Data loader (`sources/nba.py`), this plan |
| Sep 25 | Team model (`models/team_nba.py`) and player model (`models/player_nba.py`) v1, backtested (above) |
| Sep 25 | Player model v2: usage shifts, blowout minutes, combos, starting lineup (above) |
| Sep 25 | Player v3 candidates tested (above): returning from absence kept; position defense, recent form and team travel dropped |
| Sep 25 | Live pipeline built early (above): hourly pulls 15–75 minutes before tip, pricing, the NBA prop tracker, grading, `nba.yml`, the tick routine (disabled until Oct 19) |
| Oct 1–12 | NBA in the app (the night's games from the morning pull, a game page with every priced player line), the preseason lineup watch, the worker's pregame window [15, 45] (rehearsed Oct 9) |
| Oct 4 | Game lines on the card (`cards/nba.py`): FanDuel vs Pinnacle, market-only; moved numbers are leans only; graded from ESPN's final scores |
| Oct 12 | DraftKings: props and game lines priced at FanDuel and DraftKings (each at its own number; a moved number is a lean), the tracker records the book; fun tickets show both books (docs/DRAFTKINGS_PLAN.md) |
| ~~Oct 19~~ | ~~Enable "BetLab tick: NBA"~~: not needed since the worker cutover (Oct 6); the worker's pregame job prices NBA games. Leave `trig_01RVyt6McaJ7wVsfo2MBrKHH` disabled |
| Oct 20 | Opening night: logging starts |
| Mid-Nov | ML layer v1 on the logged lines, walk-forward; reaches prices only if it beats the market |

Soccer moves to after the NBA build (late October).

## Decisions for Mike

- **Historical game lines for 2025–26: bought Sep 28** (4,620 credits: spreads and
  totals near tip, 1,129 games; docs/DECISIONS.md, "historical odds spending plan").
  - Result: the market beats the team model (margin blend weight −0.13, SE 0.10;
    `docs/MODELS.md`), so the card stays market-only.
  - The lines are saved in `data/odds_history/basketball_nba/lines_2026.parquet` for
    the ML layer.
- **Keep the $30 Odds API plan past Oct 24?** NBA props every night need it (≈ 2,000–2,200
  credits a month on their own: about 7.5 games a night × 8 credits, plus game lines).
