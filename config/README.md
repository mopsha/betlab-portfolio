# config/

Loaded by `betlab.config.settings()` and `betlab.config.ny_restrictions()` (cached
per process). Money is in USD, and probabilities/EV are fractions (0.03 = 3%).

## `settings.yaml`

"Live" means the code reads the key today; "not wired yet" means it's declared for
a later phase and changing it has no effect.

| Key | Status | Meaning / used by |
|---|---|---|
| `timezone` | live | ET date for daily folders and card names (`cli.py`) |
| `bankroll.unit_pct` | live | 1 unit = this share of the bankroll; quarter-Kelly units (`picks.stake`) |
| `bankroll.real_start_date`, `real_bankroll` | not wired yet | The page hard-codes the same values (`REAL_START`, `BANKROLL`) in `page/index.html` |
| `bankroll.max_units_per_bet/game/day` | not wired yet | For `staking.apply_exposure_caps` in the real-money phase |
| `bankroll.fun_bucket_monthly` | live | The fun bucket ($10 a month): shown as a meter on the page's Fun tab |
| `props.market_shift` | off (empty) since Oct 19 | Log-odds shift on the market's fair over-probability per stat. Was receptions −0.18, receiving yards −0.17 (2025's over lean); 2024 lines didn't confirm it (`docs/DECISIONS.md`, 2026-10-19) |
| `preview.matchup_read` (`stats`, `ypt`, `deep`, `show_min`, `show`) | tracked only (`show: false` since Oct 19) | Unconfirmed receiver matchups: log-odds per SD of each feature and the SD, and how strong the read must be to show a note; notes off because 2024 lines didn't confirm them |
| `fun.script_read` | off since Oct 19 | Whether the game-script read moves fun slips' pass-game legs and stories (2024 lines didn't confirm it) |
| `preview.script_lean` (`stats`, `matchup`, `volume`) | Games tab only | How the game script moves the market's P(over) on pass-game props (log-odds per SD of pass matchup edge, per log ratio of projected dropbacks). Fit by `betlab backtest script`; not used for picks; `show: false` hides the lines since Oct 28 (still tracked) |
| `fun.band`, `min_legs`, `max_legs`, `min_leg_p`, `max_leg_p`, `under_min_p`, `under_max_p`, `max_unders`, `per_game`, `stake`, `sims` | live | Fun parlays (`betlab fun`): fair-odds band, 4-5 legs each 55-80% likely, unders only as 75-92% near-locks and at most one per slip, one long shot per game (`fun.longshot`: band, legs, shortest leg chance), one leg per player (`one_leg_per_player`), parlays per game, $ per parlay, simulated games |
| `fun.college.band`, `min_games`, `max_games`, `max_legs`, `leg_p`, `allow_unders`, `pair_lift`, `minis_per_game`, `pool_games` | live | The college lines-only SGP+ ticket per kickoff slice (noon, afternoon, night; `cards/fun_ncaaf.py`): fair +400 to +5000, 3-4 games, legs 40-80% likely, no unders, a side and total paired only when they move together (lift 1.05+), from the 12 best-value games |
| `fun.plus.band`, `min_games`, `max_games`, `max_legs`, `mini_legs`, `mini_band`, `max_unders_mini`, `minis_per_game`, `over_p`, `overs_per_game`, `overs_per_slate`, `td_min_p`, `td_per_game` | live | (`td_*`: the window's anytime TD ticket, one scorer per game at least 20% likely, picked by value with our TD read) | The Fun tab's slates (`sgp_plus.py`): one SGP+ ticket per kickoff window (fair +500 to +4000, 2–4 games, up to 10 legs, each game a 2–3 leg mini with no unders), and the straight overs to root for (30–80% likely, 3 per game, 6 per window) |
| `picks.min_ev.game_line` / `.prop` / `.prop_under` | live | Minimum EV for a pick (3% / 5%; prop unders 10%, Mike's rule so the card isn't all unders: below it they are leans) (`picks.classify`) |
| `picks.lean_ev` | live | Minimum EV for a lean (1%); a moneyline above +250 is never one (`picks.classify`) |
| `nhl.read_min` | live | NHL reads: our win chance minus DraftKings' no-vig chance at least this (tracked, never picks) |
| `leagues.ncaab.paid_odds_from` | live | College basketball uses ESPN's free DraftKings lines until this date (reads only), then the Odds API: 2026-10-26, so the full card runs from the Nov 2 opener (Mike, Oct 15; was 2027-03-01) |
| `picks.horizon_hours` | live | Picks only for games starting within this many hours (36); edges further out are leans |
| `picks.max_model_market_gap` | live | Larger model-vs-market gaps can't be picks or leans (12 points) |
| `picks.check_news_min_gap` | live | "Check the news" flags start here (20 points): smaller gaps carried no information in the college backtest |
| `picks.devig_two_way` / `devig_three_way` | not wired yet | Code uses `odds_math.devig`'s default (power). Shin is meant for 3-way soccer |
| `staking.kelly_fraction`, `kelly_cap_units`, `tiers` | live | Alternative staking plans recorded on each pick (`picks.stake`) |
| `schedule.pregame` | from the worker cutover | Minutes before the start (lo, hi) when `betlab pregame` pulls a game's lines and props, once, after its sport's news: NFL/college 30-85, NBA 15-45 (retune after the lineup watch), NHL 20-60, soccer 15-55 (`pregame.py`) |
| `odds_api.base_url`, `bookmakers` | live | `OddsApiClient` |
| `odds_api.keys` | live | The Odds API keys in the order they're spent: the free key (`ODDS_API_KEY`, 500 a month, resets on the 1st, no reserve) and then the paid key (`ODDS_API_KEY_PAID`, 20,000, resets on the 24th, 50-credit reserve for closing lines). Each has its own `CreditGuard` and usage log |
| `odds_api.sharp_books` | live | Reference books for the fair price, in priority order (`market.reference_books`) |
| `odds_api.target_book` | not wired yet | `"fanduel"` is currently hard-coded in `cards/football.py` |
| `leagues.<lg>.sport_key` | live | The Odds API sport key |
| `leagues.<lg>.start` | live | `pull --auto` skips a league before this date |
| `leagues.<lg>.family`, `props` | not wired yet | Descriptive for now |

Only leagues that also appear in `cli.EVALUATORS` (NFL and college football today) are
actually pulled and priced. The others are declared for their planned start dates.

## `player_aliases.yaml`

Sportsbook player name → nflverse full name, for names `players.normalize` can't match (suffixes, initials and accents are already handled). Add a line when `betlab fun` reports an unmatched player, or when a slip's leg stays open after its game is final (Nov 2: FanDuel's "Chigoziem Okonkwo" is nflverse's and ESPN's "Chig Okonkwo"). The live trackers don't need it: they fall back to first initial and last name.

## `stadiums.yaml`

Every NFL venue by nflverse `stadium_id`: name, latitude, longitude and roof (`outdoors`,
`dome`, `retractable`), for the kickoff forecast (`sources/weather.py`). Add a line when
the schedule lists a new venue; the Game Previews show no weather for a venue it can't
find. nflverse calls some open-air international venues "dome"; this table wins.

## `key_rotation.yaml`

When each key last changed, for the 9:55 reminder (`rotation.py`). Names and places only, never a value. Finishing the to-do counts as rotating.

## `ny_restrictions.yaml`

- `college_player_props: false`: New York bans all college player props.
- `college_games_in_ny_state: false`: New York bans bets on college games played there.
- `ny_college_teams`: Division I schools in New York, matched by name *prefix*
  (`ny_rules.is_ny_college`), so both "Syracuse" and "Syracuse Orange" match.

Never loosen these (see `CLAUDE.md`, rule 2).

A league entry may list `markets` (the Odds API market keys to pull; default h2h, spreads, totals). Soccer leagues pull `[h2h]` only: FanDuel posts only the 3-way result for them, and each market costs a credit.

`backtest_baseline.json` (Nov 4): closed-season backtest numbers the weekly drift check compares against (`scripts/backtest_drift.py --update`, after reading why they moved).
