# src/betlab/cards/: pricing today's FanDuel offers

A "card" module takes an odds snapshot (see `data/odds/README.md`) and returns
one row per FanDuel offer (each side of each market) with our probability, the
market's probability, the blend, and the EV. `cli.cmd_card` then classifies,
stakes and writes the card.

| File | What it is |
|---|---|
| `football.py` | The shared football evaluator. `FootballLeague` holds per-league config: `key`, `load_games`, `team_names`, `params_path`, `first_season`, `base` settings. `evaluate()` prices spreads, totals and moneylines; `load_model()` loads or refits the league's settings; `upcoming()` builds features for the next 8 days' games |
| `nfl.py` | `LEAGUE` for the NFL (nflverse data, `data/models/nfl_params.json`, `GameParams` defaults) plus `evaluate`/`load_model` wrappers |
| `ncaaf.py` | `LEAGUE` for college football (CFBD data, `data/models/ncaaf_params.json`, ridge 1, early weeks 4). NY rules are applied inside `football.evaluate` |

Every fun builder groups games into kickoff slices (`sgp_plus.SLICES`) whose tickets lock 15 minutes before the slice starts (`sgp_plus.keep_tickets`).

`fun_ncaaf.py` builds the college lines-only SGP+ ticket per kickoff slice (noon, afternoon, night) for the Fun tab (spreads, totals, moneylines; big favorites paired with the over from past games' joint outcomes; New York rules; `build`, `draws`, `residuals`, `minis`).

`fun_soccer.py` builds the soccer SGP+ ticket per kickoff slice (morning, midday, evening) across the leagues (team to win, over 1.5/2.5/3.5 goals, both teams to score; each match's legs read off one score grid fit to Pinnacle's result and goals prices; `build`, `targets`, `fit_goals`, `legs`, `minis`). FanDuel's goals prices aren't in the bulk feed, so those legs carry no FanDuel price; the ticket's matches get one event pull (`GOALS_MARKETS`) for their betslip links.

`ncaab.py` prices college basketball (from Nov 2): FanDuel spreads, totals and moneylines against the sharp no-vig price at FanDuel's number (a normal curve moves other books' numbers: SD 11 margin, 16.5 total), model weight 0, New York rules from the schedule's venue state (a game with no confirmed venue is skipped; skips are counted in the card's notes); plus reads where our efficiency margin and FanDuel's spread differ by 3+ points (`price`, `evaluate`, `READ_MIN`).

`soccer.py` prices FanDuel's 3-way match result for the big five and MLS against the sharp book's no-vig 3-way chances (Shin), model weight 0 (`evaluate`, `three_way`, `LEAGUES`). The ratings in `models/soccer.py` lost to the market, so they don't touch it.

`analysis_nhl.py` writes the NHL game analysis: matchups with sizes, the game script, injuries with ice time and shot share.

`props_nhl.py` prices FanDuel's NHL props against the other books' no-vig chance (moved to FanDuel's number along the stat's spread), with the ML model's chance and the read tag (`tonight_features`, `price`, `_consensus`).

`nba.py` is the NBA card (paper, market-only, from Oct 20): FanDuel's moneyline, spread and total against the sharp no-vig chance; a sharp number up to 1.5 points away is moved to FanDuel's (`shift`) and the side is a lean at most (`lean_only`); pushes on whole numbers from 2025-26 (`evaluate`, `fair`, `shift`, `push_chance`).

`nhl.py` is the NHL card (paper, market-only): FanDuel's moneyline, puck line and total against the sharp book's no-vig price at the same number (`evaluate`, `_fair`, `_game_ids`).

`ufc.py` is the UFC card (market-only, Oct 23): moneyline and total rounds at each of Mike's books against the sharp no-vig price, for fights matched to ESPN's UFC card at their segment's start (`evaluate`, `card_fights`, `align`, `_fair`). `fun_ufc.py` builds one plain parlay per card segment from fighters' FanDuel moneylines, plus moneyline packs for the Build tab (`build`).

`analysis_ufc.py` builds the UFC fight pages (Oct 23): segment, weight class and rounds; the tale of the tape and each fighter's last five UFC fights; the weight class's base rates; DraftKings' method, distance and rounds prices as no-vig chances; the books against the sharp moneyline; the fight model's read; same-fight parlay fair prices (`build`, `same_fight`, `finish_timing`, `sharp_total`, `dk_props`).

`fun_nhl.py` builds the NHL Fun slates: one SGP+ ticket per kickoff slice (afternoon, evening, late) from our score grid fit to the sharp moneyline and total (winners, puck lines, overs; no unders), and shots-on-goal overs to root for (`build`, `fit_goals`, `legs`, `minis`, `sog_overs`).

`preview_nhl.py` builds the Games tab's NHL view from free data (`exports/nhl.json`): DraftKings' lines from ESPN, the starting goalies (ESPN's confirmed or probable starter, else our guess), the model's win chance, fair price, total and puck line, team ranks, and a tracked read where the model and DraftKings differ by `nhl.read_min` (`build`, `write`). Never picks.

`props_nba.py` prices NBA player props for the card (paper) and returns the NBA tracker's rows: every FanDuel main line (points, rebounds, assists, threes, combos) against the sharp market's no-vig price at FanDuel's line (moved with the model's negative binomial when the sharp line differs), with player model v3's chance tracked at weight 0 (`price`, `evaluate`). The live data it needs (box scores, injury report, rosters) can be passed in, for tests and replays.

`props_nfl.py` prices NFL player props for the card (paper): every FanDuel main line against the over-corrected market, with `kind` "prop" (weight 0 on our model; `docs/MODELS.md`). It reuses `fun_nfl.prepare_game`.

`preview_ncaaf.py` builds the Games tab's College view (FBS-vs-FBS games in the latest college snapshot): market score, efficiency read, FBS unit ranks, matchups, venue weather, and the early read at FanDuel's line, plus the tracker rows.

`preview_nfl.py` doesn't make card rows either: it builds the Games tab (`betlab preview`), one preview per NFL game in the next week, from `models/game_nfl.py` plus the pass-game script lean on FanDuel's main props.

`fun_nfl.py` is different: it doesn't make card rows. It builds the Fun tab's same-game parlays from the latest `_props` snapshot (`betlab fun`); see `docs/MODELS.md`.

## What `football.evaluate` does, per game

1. Matches the snapshot's team names to the games table (`league.team_names()`) and
   skips games New York rules forbid.
2. **Early weeks:** if the game's week is at or below `early_weeks`, it uses blend
   weight 0 (market only).
3. **Spread:**
   - Takes FanDuel's two-way price.
   - Reads the market center from the reference books (sharpest available, else the
     median of the others) via `KeyNumberDist.center_for`.
   - Gets `p_model` from our margin at FanDuel's line and `p_market` from the market
     distribution at the same line.
   - Blends them, then computes EV with the push probability.
4. **Total:** the same, with the totals distribution.
5. **Moneyline:** `p_market` is the median no-vig probability across the reference
   books, `p_model` comes from our margin, then blend and EV.

## Output columns

`league, event_id, game_ref, commence_time, matchup, market (spreads|totals|h2h),
side, player, label, point, price, book, model_number, kind (game_line|prop),
p_model, p_market, p_final, p_push, ev, market_source, w_model`.

## Adding a league

Add a thin module like `ncaaf.py` and register it in `cli.EVALUATORS` and
`grading.GRADERS`. Full checklist: `docs/OPERATIONS.md` → "Add a league".
