# src/betlab/models/: the math that makes predictions

Pure computation, no I/O except `GameParams.save/load`. The narrative
explanation, with backtest numbers, is in `docs/MODELS.md`.

| File | What it is |
|---|---|
| `ratings.py` | `fit_ratings(games, asof, home_col, away_col, half_life_days, ridge, lookback_days)`: time-weighted ridge offense/defense ratings from games strictly before `asof`. Returns `Ratings(mu, home_edge, off, dfn)`, where `predict(home, away, neutral)` gives each side's expected value. Works for any per-team stat (points, EPA per play) |
| `margins.py` | `KeyNumberDist`: integer-outcome distributions with key-number weights. `fit(values, lo, hi, symmetric)` learns the weights; `pmf(center, sd)` is median-centered with a continuous CDF; `over_push_under(center, sd, line)`; `center_for(line, sd, p_over)` reads a market price back into a center; `log_likelihood` for fitting SDs |
| `football.py` | The football game model shared by the NFL and college. `GameParams` holds every setting (saved as JSON). Functions: `rating_features` (ratings to features), `walk_forward` (week-by-week predictions, no peeking), `apply` (combiner), `fit_distributions`, `spread_probs`/`total_probs`/`ml_prob`, `market_rows` (model vs no-vig market at closing lines; skips early weeks), `fit_params` (combiner + SDs + blend weights), `production_params` (fit on everything, for live use) |
| `props_nfl.py` | Draft NFL props model, **not on the card yet**. `PropParams`; `prepare` (player-games plus team totals and game script); `team_volume`, `player_profile` (shrunk shares and efficiency); `simulate` (4,000 draws per player); `prob_over`. Calibration notes and the open to-do are in `docs/MODELS.md` |

`roles_nfl.py` is props model v0.2: each player's role from snap share, the opponent matchup, absences, and team volume, backtested in `backtest_props.py` (`docs/MODELS.md`). It builds the inputs `game_sim_nfl.simulate_teams` draws from.

`game_nfl.py` is the game-flow engine: team-game stats from play-by-play (`team_games`), opponent-adjusted unit ratings (`fit_ratings`, `ranks`), a projection of plays, pass/run mix and points with the market's game script (`project`), the biggest unit matchups and a short game story (`matchups`, `script_text`), each offense's script features for the prop script lean (`script_features`), QB ratings and the effect of a QB change (`qb_games`, `qb_ratings`, `qb_adjust`), and weather effects (`WEATHER`, `weather_effects`). It gets no weight on the score (the market is better); see `docs/MODELS.md`.

`joint_nhl.py` is the joint NHL game: the final score from the grid, team shots given the score, players' shots as beta-binomial shares, goalies' saves as shots faced minus goals (`simulate`, `JointParams`).

`props_nhl.py` is the NHL props ML model: walk-forward player features (`features`, `game_features`), Poisson-loss gradient-boosted trees per stat (`fit`, `predict`), negative binomial overs (`p_over`, `nb_size`), goalie saves (`saves_mean`).

`nhl.py` is the NHL game model: ridge ratings for shots, goals and 5-on-5 attempts (`fit`), goalie save % shrunk toward the league, expected goals against tonight's starters (`expected_goals`), and a score grid with 60-minute ties, overtime and empty-net goals (`grid`, `project`, `p_over`, `p_cover`, `ranks`). Settings: `data/models/nhl.json` (`betlab backtest nhl`).

`team_nba.py` is the NBA team model: team-games from box scores with possessions and pace (`team_games`), ridge offense/defense/pace ratings (`fit_ratings`, `ranks`), and a game projection with a back-to-back adjustment (`project`).

`td_nfl.py` is the anytime TD read: a logistic model of scoring from red-zone and inside-10 share, usage, recent TD rate, position and team expected points (`player_games`, `rolling`, `design`, `fit`, `Reads`, `blend`, `note`); fun tickets only, at half weight toward Pinnacle.

`ncaab.py` is the college basketball ratings model: opponent-adjusted efficiency and pace by weighted ridge (`fit`), and a game projection of margin and total (`Ratings.project`), plus the early-season roster shift (`roster_value`, `roster_dval`, `roster_shift`, `season_day`: last season's player value of this season's roster, fading over about 60 days). It loses to the close but predicts moves from the opener, much better with the roster shift (docs/MODELS.md).

`soccer.py` is the soccer ratings model: time-weighted Poisson attack/defense with home advantage and a promoted-team prior (`fit`, `Ratings.expected`), and match probabilities with Dixon–Coles's low-score correction (`probs`, `score_matrix`). Backtested with no edge over the market (docs/MODELS.md), so it has no weight.

`live_nba.py` builds tonight's NBA rows for pricing: rosters (ESPN's current ones, or rebuilt from box scores), players ruled out, tonight's team rows, then `player_nba.player_games` on "pending" rows so the features match the backtest's (`tonight`). `validate_on` replays a past night and compares the live features with the backtest's.

`player_nba.py` is the NBA player model: walk-forward features for every player-game (`player_games`: recent minutes, starts, teammates ruled out, per-minute rates, opponent allowances, pace), a minutes regression and per-stat calibration (`fit`, set by `backtest_nba.tune`), expected stats (`predict`) and negative binomial helpers (`p_over`, `crps`).

`game_ncaaf.py` is the college engine: CFBD advanced stats per team-game (`team_games`), ridge unit ratings with FBS ranks (`fit_ratings`, `ranks`), projections and matchups, and the early read (`early_features`, `early_read` with its drivers in words; settings in `data/models/ncaaf_early.json`).

`matchups_nfl.py` has the receiver-vs-defense matchups behind the Games tab's unconfirmed matchup notes: targeted dropbacks (`targets`), walk-forward defense yards per target by position group and deep-ball numbers (`ratings`), one receiver's features against one defense (`features`), and the read on the over (`read`).

`game_sim_nfl.py` draws every player in one game together (shared game script, Dirichlet shares, QB yards = receivers' yards, TDs from drawn points, injury-report redistribution). It powers the fun parlays only; its correlations are not backtested yet (`docs/MODELS.md`).

## Invariants

- Nothing here may use information from on or after the prediction date. `fit_ratings`
  filters `date < asof`, and `walk_forward` fits before each week.
- Probabilities returned for lines are **conditional on no push**, with the push
  probability separate.
- Any settings change goes through a backtest and into `docs/MODEL_CHANGELOG.md`.

`ufc.py` (Oct 23): the UFC fight model from ESPN's results since 2021: each fighter's pre-fight state (Elo, per-minute strike, takedown, knockdown and control rates, finish and stopped rates), who-wins and goes-the-distance logistic regressions, walk-forward by year (`features`, `fit_win`, `fit_distance`, `walk_forward`, `report`, `reads`). Tracked on the fight pages, no weight (docs/MODELS.md).
