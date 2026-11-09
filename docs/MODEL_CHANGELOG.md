# Model changelog

Every change to model settings or pick rules, newest first, with the evidence.
Saved settings live in `data/models/<league>_params.json`. The reasoning behind
bigger choices is in `DECISIONS.md`.

## 2026-11-07: a two-game NHL slice's ticket floor is +200 (Mike)

- **What changed:** `fun.nhl.band_two_games: [200, 1500]`; a slice whose ticket pool has two games uses it in place of the
  usual +300 floor (`cards/fun_nhl.py`), as soccer's two-match slices have their own (Oct 14).
- **Why:** the Nov 7 afternoon slice (FLA @ WSH, STL @ NSH) locked with no ticket and no alert. At the 11:45 pre-game
  pull FanDuel moved its only FLA @ WSH total from 6.5 to 5.5 (it lists no alternate NHL totals), the "Over 6.5 goals"
  piece went, and the two games' best one-leg pieces reached about +265, under +300. Replayed on that day's three
  snapshots: a ticket in each (WSH to win, STL to win). Fun bucket only; no pick rule changed.

## 2026-11-07: watched games get their own parlays; the Knicks rule and the lone-game rule are gone (Mike)

- Mike: "you should be able to signify games you are going to watch and then it gives you parlays for that game, so we
  don't need a strict knicks rule anymore or a strict prime time nfl rule". Every slice now carries each of its games'
  own same-game slips: the NFL's and NBA's full slips (value, story, long shot); for the other sports ("if a game is
  watched that means i want single game slips for it") slips built from each game's Build pack (`sgp.pack_slips`: the
  joint chance as Build prices it, 2-4 legs, one leg per market, the fun rules on player unders, ranked by how much the
  legs move together; three at +150 to +1000 and a long shot at +1500 to +6000). A lines-only game (college, a UFC
  fight, an NHL game before its props are pulled) gets its best single at FanDuel instead ("just give a pick";
  `sgp.best_single`, its EV said plainly, labeled not a pick when it has no edge). They lock with the slice.
- Today shows a game's slips only when the account watches it (Watch on the game page, `user_settings.watching`,
  migration 0045), next to the slice's tickets once the slice locks; the lock alert names them per account
  (`alerts.watched_slips`). Removed: `fun.nba.own_slips_teams` (Oct 21), a lone NBA game's or NFL prime-time game's
  slips for everyone (Oct 12, 19), and Today's rule hiding a game's slips inside an SGP+ window (Oct 12).
- No pricing changed: the slips are the ones the builders already made. Game pages now list every sport's slips.

## 2026-11-04: NHL shootouts: the winner's goal is counted

- **What changed:** `sources/nhl.load_team_games` credits a shootout's winner one goal in `gf` / `ga`, as books settle
  moneylines, puck lines and totals. `gf_play` / `ga_play` are the goals actually played. The report has always left these
  games tied (278 in 2024-27, 18 of 246 this season), though the code assumed it credited the winner.
- **Effect:** graders read a shootout as a tie: a moneyline as a push on the card or lost on a ticket, totals one goal
  short. The ratings took a goal off each winner (a 0-0 game read -1, clipped to 0); `data/models/nhl.json` keeps its
  fit until the next refit, and the model has no weight. Of 37 ledger rows in this season's shootout games, 5 are game lines
  and 2 of those read wrong. Mike had both corrected by hand in `leans.csv` (Nov 4), result columns only: DET @ EDM Over 6.5
  (`08f6cee6491b`) lost -> won, +0.9009; TBL @ NSH TBL moneyline (`77fe29c6ab15`) push -> lost, -1.0. Net -0.0991u. Neither was
  a bet anyone took. No pick, and no real ticket's result, changes. Earlier seasons have no ledger rows here.

## 2026-11-04: a soccer game with only a 4.5 goals line gets its score grid

- **What changed:** `fun_soccer.targets` fits a match's grid to a sharp over/under 4.5 when no sharp book has a 1.5, 2.5,
  3.5 or whole-number line. Such a game now gets its builder pack and can join a ticket. 4.5 is never a leg, every game
  with a nearer line prices as before, `max_fit_error` stays 0.03, and quarter lines alone still anchor nothing.
- **Evidence:** of 350 finished soccer games since Oct 13, 8 had no usable line at their last pull: 5 with a sharp 4.5
  (Barcelona, Bayern and Real Madrid games among them) and 3 with quarter lines only. No sharp book posts 4.5 beside a
  lower line, so the test used Novig's ladder on 172 games: fit to 4.5, the 3.5 misses by 1.0 points and the 2.5 by 1.3
  (90th percentile 2.0, 2.2), against 0.5 for 3.5 predicting 2.5; fit error at most 2.1. Barcelona-Aston Villa, the one
  skipped game Novig listed: over 3.5 65.1% vs 65.6%, over 2.5 82.2% vs 82.8%. Fit prices, not a pick rule; these games
  price somewhat less exactly than others, and no result data was used.

## 2026-11-03: no lean on a moneyline above +250 (Mike)

- **What changed:** `picks.classify` gives a moneyline priced above +250 no tier, so it isn't shown, logged or alerted as a
  lean. Picks already stopped at +250. A big favorite stays a lean, never a pick; props and spreads are untouched; "check
  the news" flags are untouched. Rows already in `leans.csv` stay and keep grading.
- **Evidence:** graded game-line leans on real closes, Nov 3: +250 to +1000: -3.67% CLV on 58, 38% beat the close; above
  +1000: -41.41% on 4, 25% beat. Against them: -250 to +250: -0.26% on 507, 56% beat; -1000 to -250: +0.15% on 61, 69%
  beat; shorter than -1000: +1.23% on 16, 94% beat. A tightening, not a loosening. The cut was chosen after seeing these
  numbers, on a modest sample, and CLV percentages run large at long prices, so the beat rate is the steadier evidence.

## 2026-10-28: the Games tab's lines that fit the script are off (Mike)

- **What changed:** `preview.script_lean.show: false`, so `preview_nfl._script_lines` returns nothing and the NFL game
  pages lose the "Lines that fit the script" section (both apps hide it when a game has no lines). The game-script
  read itself (`script_read`, pace, run/pass) still shows, and every prop line keeps its `p_script` / `script_side` in
  `prop_lines.csv`, so the read stays tested. It was never used for picks; the fun slips dropped it Oct 19.
- **Evidence:** 2026's graded FanDuel main lines (2,338, Sep 24 to Oct 26): log loss market 0.6914, with the script
  0.6931 (+0.0017, SE 0.0012); the 1,555 sides it favored hit 51.1% against the market's 51.6% (overs 47.9 vs 46.1,
  unders 52.3 vs 53.6). 2024's lines already didn't confirm 2025's fit (Oct 19). The Nov 2 check, run early.

## 2026-10-25: anytime TD read to weight 0; TD tickets pick the likeliest scorers (Mike)

- **What changed:** `models/td_nfl.READ_WEIGHT` 0.5 -> 0.0, and `sgp_plus.td_candidates` ranks each game's anytime
  scorers by Pinnacle's no-vig chance (likeliest first) instead of by value with our read. `td_reads.csv` keeps
  recording the half-weight blend (`TRACK_WEIGHT` 0.5), so the read stays tested and can earn weight back.
- **Evidence:** 581 graded reads over 60 games (through Oct 22): log loss Pinnacle 0.5534, half-weight read 0.5540
  (gain -0.0006, SE 0.0032 by game bootstrap), the model alone 0.5616. The read never beat the market (Oct 20: a tie
  on 563 reads). The Oct 20 rule ("600+ graded reads, if the half-weight read doesn't beat Pinnacle, weight 0") was
  19 reads short; Mike made the call Oct 25 ("let's do it at least locally right now").
- **What it does to tickets:** Oct 25's early-slate ticket picked by the read paid +197,970 (fair +340,005); the
  likeliest scorers' version paid about +6,052 (fair +9,897). The tickets get far shorter.

## 2026-10-23: UFC fight model (new; tracked, no weight)

`models/ufc.py`: who wins (logistic regression on Elo and per-minute fight stats, both orders of every fight) and
whether it goes the distance, from ESPN's UFC results since 2021, walk-forward by year. Out of sample (2,179 fights,
2023-26): log loss 0.663 (Elo 0.676, coin 0.693), 61% of winners; distance 0.666 vs the base rate's 0.692. Against
DraftKings' no-vig prices on the 63 fights ESPN kept: market 0.642, model 0.721, half and half 0.666. Weight 0: it
shows on the fight pages as a labeled read and is logged every card. `betlab backtest ufc` reruns it.

## 2026-10-21: NBA fun slices are afternoon, early and late; a likelier SGP+; Knicks slips (Mike)

- **What changed:** NBA fun slates group by fixed slices (`sgp_plus.SLICES["nba"]`: before 5 PM, before 9 PM, later)
  instead of 30-minute tip windows. Every game of a slice is pulled once its slice's first tip is 15-45 minutes away
  (`pregame.due_by_slice`), so the whole slice is priced by its lock. Each slice gets a second, likelier SGP+ ticket
  (`fun.nba.short`: fair +150 to +500, up to 3 games, from the games the regular ticket left out when 2+ are left;
  `fun_nba.short_ticket`, slate key `plus_short`) next to the regular one (+500 to +4000, unchanged). A Knicks game
  (`fun.nba.own_slips_teams: [NY]`) keeps its own slips next to the slice's tickets; its legs can still sit on them.
- **Why:** on Oct 21 the windows made six slices of 1-3 games, each locked minutes after its last game was priced; a
  game's slips vanished when a second game joined its window, and the only ticket ran +2155. Mike: "early and late
  slices but Knicks get slips", and NBA tickets ran longer than the other markets' ("just want a mix").
- **Cost:** a slice's later games are priced up to ~2 hours before their own tip, before their lineups; a lineup change
  still re-pulls the game (news.py), but after the lock the tickets stay. Credits: each game is still pulled once.
- **Effect:** no change to any leg's chance or price; only which games share a ticket, and one more ticket per slice.

## 2026-10-20: NBA lone-game slips use the NBA's pair lift (a bug fix)

- **What changed:** `cards/fun_nba.game_slips` (Oct 19) passes `fun.nba.min_pair_lift` (1.03) to `sgp.search` for
  its value slips and long shot. It had left it out, so the search ran at its NFL default of 1.10.
- **Evidence:** no new setting. 1.03 is the NBA's measured pair lift, already used for the SGP+ minis (settings.yaml
  `fun.nba`). On opening night's 3 PM game (Celtics @ Pistons) the legs gave 0 four-to-five-leg candidates at 1.10 and
  3,253 at 1.03, so the game showed only a +5772 long shot instead of its value slips.
- **Effect:** later lone-game NBA windows (tonight's 7:00 and 9:30 PM) get value slips. The 3 PM slip was priced once
  and locks as it is.

## 2026-10-20: college basketball freshmen count in the roster shift

- **What changed:** `models/ncaab.roster_value` adds each team's incoming class to its roster value (`val_fresh`):
  each recruit's expected first-season value by rating (`FRESHMAN_BANDS`: 0.995+ 1.95, 0.98+ 0.84, 0.95+ 0.65, 0.90+
  0.40, below 0.24 points of PORPAG x games / 30). Before, freshmen counted 0. The shift's weight (`ROSTER_BETA` 0.65)
  and fade are unchanged. Recruits come from CBBD (`cbbd.recruits`, saved in data/history).
- **Evidence:** the bands are the 2022-23 and 2023-24 recruits' first-season values; a separate weight fit on those
  seasons came out 0.73, close to 0.65. Held out, November margin error on games with a closing line: 2024-25 9.887
  -> 9.891 (+0.003, SE 0.018), 2025-26 9.926 -> 9.889 (-0.036, SE 0.019). Against the opener (2025-26 only), reads at
  3+ points moved +0.56 pts toward us (was +0.48) and covered the opener 57.9% (was 56.3%). Never worse; small.
- **Effect:** biggest 2026-27 classes: Arkansas +7.5, Duke +6.0, Michigan +4.7, Kansas +4.5. The card stays
  market-only (model weight 0); this changes the reads and the game pages.

## 2026-10-20: soccer lineup totals need 9 of 11 starters with history (a guardrail, tracked reads only)

- **What changed:** `cards/analysis_soccer.MIN_KNOWN_STARTERS = 9`: a team's lineup shots, shots on target and goals
  (`goals_model`, which feeds the goals read in `soccer_goal_reads.csv`) are shown only when at least 9 of its starters
  have player history. Otherwise they're blank and no goals read is logged for the match.
- **Evidence:** of 67 graded goals reads, two cup matches had a side from outside the six leagues (Union
  Saint-Gilloise, Pafos) whose one or two known starters added up to 0.00 expected goals, a 0% both-teams-to-score
  read. Both rows stay in the ledger (history). On the rest, the read still loses to the market (BTTS log loss 0.863 vs
  0.677 on 65; over 2.5 0.759 vs 0.624 on 67), so it keeps no weight.

## 2026-10-19 (late night): the over-lean shift is off everywhere (Mike)

- **What changed:** `props.market_shift` is empty (was receptions -0.18, receiving yards -0.17 in log-odds), so
  `props_market.over_shift` changes nothing: not the parlays' anchoring (`fair_main`, the fun slips' leg chances), the
  Games tab previews, or grading's corrected close. Picks had it off since Sep 30 (`shift_in_picks: false`).
- **Evidence:** 2024 lines (240 games): overs hit -1.1 pts vs the plain market overall, receiving yards -0.4 (SE 1.0),
  receptions -1.4 (SE 1.1); 2025 had -4.1 and -4.5, the shift said ~-4. 2026's first 325 lines: 45.8% vs 45.3%.
- **Effect:** receptions and receiving-yards overs in slips are priced at the plain market (about 4 points likelier
  than before); unders less so. The scorecard was already judged on the plain close (`clv_raw`).

## 2026-10-19 (late night): the fun slips no longer use the script read (Mike)

- **What changed:** `fun.script_read: false`: `fun_nfl.apply_reads` gets no game-script read, so no pass-game leg's
  chance moves with it (`p_read`), slips rank on the market's chances alone (`read_value` = `leg_value`), and no story
  says "fits how we read the game".
- **Evidence:** the pass-game script edge was +0.068 log-odds per unit on 2025 (SE 0.024) and -0.007 on 2024 (SE
  0.025); its strong side hit 49.9% against the market's 49.9% on 2,615 2024 lines.
- **Unchanged:** the Games tab's game-script read and its "lines that fit the script" (Mike asked only about the
  slips); the matchup check (to-do c-matchup-check, Nov 2) still covers them.

## 2026-10-19 (late night): the Games tab's matchup notes are off (Mike)

- **What changed:** `preview.matchup_read.show: false`: `preview_nfl._matchup_notes` returns none, so the "Matchup
  notes (unconfirmed)" section disappears (web and iPhone show it only when there are notes). The ypt and deep features
  are still written to `prop_lines.csv` for every FanDuel line, so 2026 keeps measuring them.
- **Evidence:** 2024 lines: ypt +0.025 (SE 0.050), deep -0.027 (SE 0.043), the combined read's strong side 49.0% vs
  the market's 50.1% (578 lines); 2025 was +0.040, +0.064 and 56.0% vs 50.4%.

## 2026-10-19 (night): 2024 prop lines checked; no setting changed

`scripts/props_2024_checks.py` on the 2024 backfill: the over lean (-1.1 pts overall vs 2025's -3.4), the script lean
(pass-game -0.007 vs +0.068) and the receiver matchups (ypt +0.025, deep -0.027; strong side 49.0% vs 50.1%) are not
confirmed. Nothing changes in picks (none of them was in picks); the parlays' over-lean anchoring, the fun slips'
script read and the Games tab's matchup notes are still on, pending Mike's call. Details: DECISIONS (2026-10-19).

## 2026-10-19 (night): prop CLV only against a sharp book at the bet's line (Mike)

- **What changed:** NFL, NBA and NHL prop bets get CLV only from a sharp book (Pinnacle, LowVig, BetOnline) quoting
  both sides at the bet's own line in our last props pull after the bet and before the start
  (`grading.sharp_prop_close`; yes/no scorer markets: Pinnacle's two-way price). The ledger's new `close_source`
  says where it came from: `sharp:<book>`, `soft` (only other books quoted it) or `none` (nobody did); soft and none
  carry no CLV, so the scorecard and reviews leave them out. Graded props are regraded once by the same code
  (`grading.fill_close_source`, from each game's own snapshot days). NHL props used the other books' consensus,
  moved between lines; they now follow the same rule.
- **Why:** soft books often hang a prop at -110/-110, a coin flip by default: 17 NFL prop "closes" from them read
  -4.8% (7% beat) while sharp closes read flat. The NHL consensus close was largely the same books the bets were
  priced from.
- **Effect on the scorecard (real closes, current rule):** NFL props 3h+ 17 closes -0.6% -> 12 at +1.4% (75% beat);
  under 3h 29 at -2.3% -> 16 at -0.1% (69%). NHL props under 3h 65 at +1.7% (88%) -> 53 at +0.4% (70%); 3h+ 9 at
  -3.4%. No pick rule, price or threshold changed: this is how bets are measured.

## 2026-10-19: a lone NBA game gets its own slips, like NFL prime time (Mike)

- **What changed:** an NBA tip window with one game (a ticket needs 2+) shows that game's own same-game slips:
  the NFL's slip rules (fun band +150 to +1000, 4-5 legs each 55-80% likely, `sgp.pick`'s no-repeats, one long shot),
  built in `fun_nba.game_slips` and carried on the slate (`sgps`). They lock with the window (`sgp_plus.LOCKED`),
  alert at the lock ("Locked: NBA 7:00 PM slips"), publish as `sgp` tickets on the game page, get FanDuel and
  DraftKings links, and grade from box scores like any NBA leg (each slip carries its game_ref).
- **Why:** opening night (Oct 20) has three games, each alone in its window, so it would have had no ticket at all.
  Mike: "count them like primetime games in the nfl".
- **Effect:** no change to any price or chance; windows with 2+ games keep the SGP+ ticket only.

## 2026-10-19: fun slips can't repeat the same players at nudged lines

- **What changed:** `sgp.pick` compares legs by player and stat (`Leg.key`), not the exact rung. Two slips may share
  at most 2 player-stats, a player-stat sits in at most 2 slips (was 3 identical labels), a player in at most 3 (was
  4). The long shot may share at most 2 player-stats with any value slip (was: only blocked if every leg was identical).
  Applies to every sport's slips and the SGP+ minis (`sgp_plus.minis`, already max 1 shared).
  NHL tickets build their own pieces (`fun_nhl.minis`): there a leg may fill at most 2 of a game's pieces (FanDuel's
  one total and +-1.5 puck lines leave no nudged rungs, only the same leg reused).
- **Why:** Mike, Oct 19 MNF: "the same 4 props repeated". Four of five Commanders @ 49ers slips were Purdy 225+/200+,
  McCaffrey 30+/25+, Kittle 50+/40+, Daniels 175+/200+: each nudged rung counted as a new leg.
- **Effect:** no change to any leg's price, chance or the EV ranking; only which candidates are shown. A game whose
  slip-sized legs (55-80%) are few now shows fewer slips (MNF Oct 19 dry run: 2 value slips and the long shot, not 4
  and 1) rather than near-copies.

## 2026-10-12 (evening, ~8 PM ET): DraftKings parlays, its quote model and its soccer settlement rule (days 4-5)

- **Parlays at DraftKings:** the slips are still built once (FanDuel's prices, our fair odds); DraftKings gets the
  same selections, priced at its own prices (`links.attach_dk`). A rung DraftKings doesn't hang moves to its nearest
  rung by chance (within 20% of the number and 10 points of chance), labeled; the fair odds stay the original slip's,
  so a moved slip's DraftKings EV is approximate (said on the slip).
- **Quote model per book:** `fun_ledger.quote_model(book=...)`. DraftKings uses FanDuel's model, labeled "FanDuel's
  pattern", until ~40 DraftKings quotes are typed (Mike starts Oct 13). No change to FanDuel's model.
- **Grading:** a DraftKings soccer slip with a game leg void or pushed settles void (its house rules); every other
  case settles as before. Checked rules in docs/DRAFTKINGS_PLAN.md ("House rules").
- **Link matching fix:** a yes/no outcome with no number (anytime TD) matched any leg number when the book had no
  rung there (Oct 12: "Stafford 225+ passing yds" took his anytime-TD price at DraftKings); now only a 0.5 or 0 leg,
  and every player leg matches only its own stat's markets (`links.STAT_MARKETS`).

## 2026-10-12 (evening): the European cups on the card; whole-number goals lines in the score grid

- **Champions League, Europa League and Conference League** (`cards/soccer.CUPS`, Mike: live for Oct 13) join the
  soccer card with the same rules as the leagues: market-only 3-way, goals and both teams to score at both books
  against the sharp no-vig, model weight 0, plus the pre-game player-props pull (tracked; scorer picks only where
  Pinnacle posts a scorer price, which it didn't for the first Champions League match checked). Thresholds unchanged.
  Graded from ESPN's final score with our own last pull before kickoff as the close (`soccer.close_3way`,
  `cup_result`): football-data.co.uk has no cup files.
- **Shots model reads for cup players** use each player's latest domestic league from the ESPN history (its
  `league_code` feature); players without history (clubs outside the six leagues) get no read. Cup games are
  not added to the player history: that would change the domestic model's inputs untested.
- **The soccer score grid now reads whole-number goals lines** (2.0, 3.0) with their push set aside
  (`fun_soccer.targets` / `fit_goals`), not just x.5 lines. Many cup (and league) matches hang a 3.0 or quarter
  main line at Pinnacle; 7 of Oct 13's 9 Champions League matches had no x.5 line, so no ticket could be built.
  Quarter lines are still skipped. This feeds the fun tickets and the market xG for the shots model (no pick weight).
- Oct 12 dry run: 54 cup matches priced at both books (18 per cup), 1 lean (Copenhagen vs Braga draw), no picks;
  the Oct 13 midday soccer slice builds a ticket from 8 Champions League matches.

## 2026-10-12 (evening): props priced at FanDuel and DraftKings; a moved number is a lean (docs/DRAFTKINGS_PLAN.md, day 2)

- **Props at both books.** NFL (`cards/props_nfl.py`: the game is simulated once, each book priced at its own numbers),
  NBA (`cards/props_nba.py`), NHL (`cards/props_nhl.py`) and soccer anytime scorers (`cards/props_soccer.py`) price each
  of `odds_api.target_books`; `books.select` keeps one offer per bet. NHL points enter the card at DraftKings, the only
  one of Mike's books that posts them (FanDuel's feed has none).
- **A moved number is a lean at most, at either book (rule 1; Mike chose both books).** When no reference quote sits at
  the book's exact number and the chance is moved along the simulator's or the stat's shape, the offer gets
  `lean_only`. Before, FanDuel props at moved numbers could be picks. Measured on the last 40 NFL props pulls: 11% of
  FanDuel's lines and 41% of DraftKings' are at a number Pinnacle doesn't hang (1.5+ away: 3% and 12%). Moved-number
  pricing was never tested on its own, and DraftKings' top offers on Oct 11 were all moved (Okonkwo over 3.5 at +131,
  "10% EV" from a translation). A tightening, so no backtest is needed to apply it; lifting it needs moved-number CLV.
- **Neither book counts toward the other's prop consensus** (`props_market.mine`, `props_nhl._consensus`), as for game
  lines on Oct 12. NHL props had counted DraftKings toward FanDuel's consensus: shots keep 3-4 other books (BetMGM,
  BetOnline, Bovada, Pinnacle), saves 2-3. NHL fun tickets use the same consensus.
- **One bet under two spellings is one bet.** `books.select` matches players across books by roster id (NFL, NBA) or
  normalized name plus `config/player_aliases.yaml`, keeping FanDuel's spelling so pick ids from before hold;
  `ledger.add_picks` also refuses a pick whose normalized bet is already logged.
- Replay of Oct 11's 11:45 AM NFL props pull: 8 games, every name matched at both books (FanDuel 113/113, DraftKings
  108/108), 480 bets (244 better at DraftKings), 14 leans (11 DraftKings), no picks.

## 2026-10-12: game lines priced at FanDuel and DraftKings (docs/DRAFTKINGS_PLAN.md, day 1)

- `odds_api.target_books: [fanduel, draftkings]`. Every game-line evaluator (NFL, college football, NHL, NBA, soccer
  3-way, soccer goals and BTTS) prices each book against the same sharp no-vig market; `books.select` keeps one offer
  per bet (league, game, market, side, player: the pick id), the higher EV, ties to FanDuel, with the other book's
  line, price and EV attached. Thresholds, weights and rules unchanged.
- **The consensus fallback now excludes both books** (`market.reference_books`): when no sharp book quotes a market,
  neither FanDuel nor DraftKings counts toward the other's market. Before, FanDuel's fallback consensus included
  DraftKings. Sharp books (Pinnacle, LowVig, BetOnline) are unchanged and quote nearly everything we price.
- On Oct 12's card: 702 bets, 257 better at DraftKings. Props, parlays and links stay FanDuel-only until days 2-4.

## 2026-10-12: new tracked reads and a FanDuel quote model (no weight in picks)

- **FanDuel SGP quote model** (`fun_ledger.quote_model`): log(FanDuel's quoted payout / our fair payout) on
  log fair odds, legs, cross-game and log(FanDuel's leg product / fair), light ridge. Leave-one-out on 127 typed
  quotes: RMSE 0.124 vs 0.181 with fair odds alone (about the old bands). Fit: intercept 0.04, log fair 0.04,
  legs -0.07, cross-game -0.03, leg-product gap 0.31. Used for every slip's "FanDuel likely" quote and the Build
  grade's benchmark (bands remain the fallback under 40 quotes). Fun bucket only.
- **NBA game read** (`nba_reads.py`, models/team_nba): margin and total vs the morning market, logged from Oct 20,
  with regulars out (20+ min) listed and key players out (25+) counted; weight 0.
- **College basketball totals reads** (`ncaab_reads.py`, kind "total", 4+ point gap): tracked beside spreads; weight 0.
- **Soccer lineup goals read** (`soccer_goal_reads.py`): starters' expected goals vs the market's on over 2.5 and
  BTTS, logged at confirmed lineups, judged on log loss; weight 0.
- **Soccer goals and BTTS card** (`cards/soccer_goals.py`): market-only, FanDuel vs Pinnacle no-vig (DECISIONS).

## 2026-10-09: "Win it with them" fun slips paused

- `fun.paused_themes: ["Win it with them"]` (settings.yaml); `sgp.pick` skips those slips, so the next-best
  slips take their places (single-game slips and the SGP+ minis). The parlay builder still allows them.
- Evidence (to-do c-sgp-v1; 127 FanDuel quotes Mike typed, 125 graded): the theme (a team's win or cover
  plus its own players' overs) hit 1 of 34 tickets across 14 games against 5.9 expected. Player yardage
  legs on those tickets hit less when the team won (passing 50% vs 90%, rushing 44% vs 77%, receiving
  0 of 7 vs 4 of 7): winning teams lean on the run and sit on leads, losing teams throw. Clustered by game,
  so weaker than the ticket count suggests. The rest held up: legs 58.2% vs 57.4% fair (177), and the
  simulator's joint beat independent legs (log loss 0.389 vs 0.399).
- Retest before turning it back on: the simulator's team-win and player-yardage link on 2023-25 games.

## 2026-10-09: college moneylines market-only (`w_ml` 0.22 -> 0)

- `data/models/ncaaf_params.json` `w_ml` 0.0: college moneylines are priced on the sharp no-vig
  chance alone, like every other market. `w_total` (0.04) and `w_spread` (0) are unchanged.
- Evidence (weak-spot review #1, More > Reviews): of 17 graded college ML picks and leans under the
  current rules, 15 were +EV only because of the model (the sharp price alone was below break-even).
  Those closed -2.0% CLV on average (SE 0.8, about 2.5 SE below zero) and 33% beat the close, while
  market-only edges across all markets closed +0.85% (68, 66% beat). The backtest edge behind 0.22 was
  thin (+0.0016 log loss per game, SE 0.0012). The model's view still shows on the Games tab.
- Side effect: college ML "check the news" flags stop (they need `w_model` >= 0.10).

## 2026-10-04: NBA game lines on the card

- `cards/nba.py` (league `nba` in `cli.EVALUATORS`, from Oct 20): FanDuel's moneyline, spread and
  total against the sharp book's no-vig chance, model weight 0. Spreads and totals at FanDuel's
  number; a sharp number up to 1.5 points away is moved along a normal curve (sd 13.9 margin,
  18.4 total) and capped at lean (`lean_only`, new in `picks.classify`). Whole-number pushes
  2.8% (spreads) and 1.6% (totals), measured on 2025-26.
- `grading.grade_nba` now settles game lines from ESPN's final scores, with CLV against our last
  pull before tip (`nba_close`, pushes included as on the football card).
- Evidence (2025-26 lines near tip, 1,045 games): FanDuel reached 3% EV against Pinnacle 3 times;
  moving the number didn't beat Pinnacle's own chance (log loss 0.6948 vs 0.6912 spreads,
  0.6926 vs 0.6913 totals; within noise). DECISIONS.md, 2026-10-04.

## 2026-09-30 (later): the joint NHL model

- `models/joint_nhl.JointParams`: c -0.006, b_own 0.0233, b_opp 0.0017, b_win -0.048, sd 0.208,
  rho_teams -0.144, rho_player 0.0032 (fit 2022-24; pairs checked on 2025-26). The NHL builder's
  props now move with the score instead of being drawn independently.

## 2026-09-30 (late night): NHL props ML v1 and the NHL game analysis

- `models/props_nhl.py`, saved model `data/models/nhl_props.joblib` (trained 2020-26) and
  `data/models/nhl_props_meta.json` (dispersion, saves size 29 and bias 0.955).
- `cards/props_nhl.py`: FanDuel props vs the other books' no-vig at FanDuel's number,
  model weight 0; `tracking_nhl_props.py` logs every line with features.
- Odds API paid key: `reset_day: 1` (the API showed 20,000 remaining at midnight UTC Oct 1).

## 2026-09-30 (night): NHL card, totals scale, fun ticket

- `models/nhl.Params.goal_scale: 1.015` (fit on 2022-24 totals; 2025-26 totals log loss
  0.6929 -> 0.6918, still behind DraftKings' 0.6889). New `disp` (a shared scoring factor)
  stays 0: it made 2022-24 totals worse at every size. Tie weight refit to 1.419.
- `cards/nhl.py`: FanDuel vs the sharp book, market-only (model weight 0), league `nhl` in
  settings from 2026-10-01.
- `cards/fun_nhl.py` and `fun.nhl`: one SGP+ ticket per night (band +300 to +1500) and
  shots-on-goal overs.

## 2026-09-30: NHL model v1 and college basketball on free lines

- New `models/nhl.py` with settings in `data/models/nhl.json`: half-life 150 days,
  ridge 8, goalie shrinkage 800 shots, goals/shots blend 0.5, tie weight 1.40,
  empty-net rates 0.54 and 0.66. Tuned on 2022-24, tested on 2024-26 (`MODELS.md`, "NHL").
- **Model weight 0** against DraftKings (2025-26: model 0.6819, close 0.6812). Reads at
  `nhl.read_min: 0.05` are tracked, not priced.
- College basketball reads can run on ESPN's DraftKings lines (`cards/ncaab.py` falls
  back to them when there's no FanDuel price; no offers or picks without FanDuel and a
  sharp book). `leagues.ncaab.paid_odds_from: 2027-03-01`.
- `picks.horizon_hours: 36`: picks only within 36 hours of the start (edges further out
  are leans). Mike's call; no model change.

## 2026-09-28 (night): prop picks drop the over-lean shift

- `props.shift_in_picks: false`. `cards/props_nfl.py` prices FanDuel's props against
  Pinnacle's plain no-vig price (`props_market.fair_main(shift=False)`). The
  `market_shift` settings are unchanged and still anchor the parlays.
- **Evidence:**
  - On 2026's first 325 graded receptions and receiving-yards lines, overs hit 45.8%
    (SE 2.8). The plain market said 45.3%; the shift said about 41%.
  - Log loss for receiving yards: 0.6942 plain vs 0.7039 shifted.
  - Every shifted pick was an under that loses to the plain close by construction
    (−1.4% raw CLV, 24% beat it).
  - Decision and follow-up: `DECISIONS.md`.
- **Effect on Monday Sep 28's lines:** 10 under leans with the shift become 2 small
  over leans without it.

## 2026-09-28 (evening): passing bends with the final margin

- `game_sim_nfl.SimParams.margin_bend` is (0.0122, −0.0203, 0.008, −0.0021) at
  `margin_knots` (−21, −7, 7, 21).
  - It's a linear spline in log passing yards, flat below −21, on top of the linear terms.
  - Each draw's multiplier is normalized, so a team's average yards don't move.
  - Fit on 2021–24 team-games, as what the linear own/opponent model leaves over.
- **The shape:** passing peaks when a team trails by about a touchdown (+6%). It drops
  about 6% in wins by 7+ and about 11% in blowout losses.
- Starters sitting explains little: in 28+ point wins the starter still throws 94% of
  the passes.
- **The straight-line links were already right.** Per SD of points, yards per target
  rise 0.118 with own scoring (the simulator has 0.13), and targets rise 0.073 with
  the opponent's scoring. 2025 agreed with both.
- **Held out on 2025, team level:** the leftover error fell (MSE 0.0930 → 0.0916). Both
  ends match: −9.4% vs −8.6% in 21+ losses, and −4.2% vs −4.3% in 21+ wins.
- **Held out on 2025, pairs:**
  - Big win + big QB day (tail lift): 1.15 → 1.05 (real 0.93).
  - Passing-yards CRPS: 45.79 → 45.74.
  - Real-line gain: unchanged.
  - Average pair error: 0.0455 → 0.0464, within noise. The moderate win + good QB
    day link stays too weak (0.05 against 0.13 real).

## 2026-09-28 (afternoon): a game over its total brings both offenses more targets

- `game_sim_nfl.SimParams`: `surprise_total_targets` is 0.084 and `surprise_total_carries`
  is 0.018, per point of total surprise.
  - Both are fit on 2021–24 team-games alongside the margin terms (SE 0.011 and 0.010).
  - 2025 agreed: +0.070 and +0.016.
  - It's the passing game, not pace: carries barely move.
- **Why:** the Sep 28 game-line test found the simulator tied a QB's yards to the game
  total 0.24 against 0.34 in real games, and a top target's 0.11 against 0.19.
- **Held out on 2025:**
  - Game total + QB yds: 0.240 → 0.329 (real 0.336).
  - Game total + top target yds: 0.113 → 0.160 (real 0.225).
  - Both QBs: 0.056 → 0.106 (real 0.064, SE 0.060).
  - Average error over every pair: 0.053 → 0.046.
  - Joint on real FanDuel lines: gain unchanged (0.0012 per pair).
  - CRPS within 0.2% on every stat. Slips and TD calibration are within noise.
- Still open: a big win plus a big QB day stays overstated (2025 tail lift 1.15
  against 0.90 real). The fix belongs to the QB's blowout exits, not to volume.

## 2026-09-28: the parlay simulation starts the market's QB

- **Starter:** `roles_nfl.team_inputs(starter=)`. When FanDuel lists exactly one QB
  on a team with a passing-yards line, that QB starts. Before, the QB with the most
  recent snaps started.
  - On Sep 27 the old rule picked Shedeur Sanders over Deshaun Watson, and Carson
    Wentz over Kyler Murray, who is new to the Vikings.
  - The real starters got no carries, so the market's rushing and TD prices for
    them couldn't be matched. Anchoring kept 11 and 93 effective draws, and both
    games lost their parlays.
  - With the fix they keep 9,364 and 15,176, and all 15 Sep 27 games anchor exactly.
  - A listed starter with no rushing history gets the position's carry prior.
- **Rosters:** players inactive on the latest nflverse roster now stay in when
  FanDuel lists them. nflverse posts a week's roster only after its games, so a
  player back this week used to go unmatched (Xavier Legette on Sep 27). The
  injury report still removes anyone ruled Out or Doubtful.
- No settings changed. This fixes the simulator's inputs; it isn't a model weight.

## 2026-09-25 (late night): college basketball ratings (research; not on the card yet)

- `models/ncaab.py` (efficiency and pace, weighted ridge; tuned on 2023-24). Held out on
  2024-25 and 2025-26: it loses to the close (blend weight about 0), but predicts
  the move from the opener (+0.29 to +0.89 pts toward the model, rising with
  disagreement; +1% to +3% implied CLV; the seasons agree at 2+ and 3+, while 5+ is
  mostly one season). It prices nothing. Live from Nov 2: reads at 3+ points, judged
  by CLV.
- Sep 26: re-downloaded after fixing lost boundary days (+740 games); numbers above
  are from the complete data.
- Sep 26: **roster shift.** The margin moves by 0.65 × e^(−days/60) × the difference in
  roster value change (previous-season PORPAG of this season's roster minus last
  season's team). Fit on 2022-24; held out, the opener reads improve from +0.38 to +0.53
  pts at 3+ and from +0.56 to +0.96 at 5+, and November margin error drops by about 0.3.
  Rosters from ESPN (preseason) and CBBD (history); stale lists (85%+ of minutes back)
  get no shift. The blend weight vs the close is unchanged (about 0.1): still no picks
  from the model.

## 2026-09-25 (late night): parlay touchdowns follow the passing game

- `game_sim_nfl.SimParams.td_yds_gamma` 0.20 and `pass_share_beta` 0.45: a draw with a
  big passing day gets more TDs, more of them passing. Both are matched to 2021-24
  team-games (passing yards correlate 0.42 with passing TDs, 0.02 with rushing TDs).
- On 2025: top target scores + QB yards 0.05 → 0.18 (real 0.15), RB scores + QB yards
  unchanged and right, TD log loss 0.5203 → 0.5201. The Fun tab's "scorer + yards" legs
  now move together as they do in real games.

## 2026-09-25 (night): college history rebuilt; "check the news" from 20 points

- `data/history/ncaaf_games.parquet` rebuilt from CFBD with moneylines averaged as
  probabilities (about 50 broken near-pick'em pairs fixed; `cfbd.games()` no longer
  needs the old patch). The refit left every blend weight unchanged (0 / 0.04 / 0.22).
  The combiner coefficients moved in the third decimal.
- `picks.check_news_min_gap` 0.20: flags only where the college backtest showed
  information (12–20-point gaps: the model's side won exactly the market's rate). This
  is display only; the 12-point pick and lean guardrail is unchanged.

## 2026-09-25 (night): soccer ratings v0 (weight 0)

- `models/soccer.py` (time-weighted Dixon–Coles Poisson; shots on target optional),
  backtested 2018-19 to 2025-26 on the big five and MLS (`betlab backtest soccer`). It
  loses to the market everywhere and doesn't predict line moves, so it has no weight
  and prices nothing.

## 2026-09-25 (night): missing regulars move the game-flow engine (`injuries_nfl.EFFECTS`)

- Per missing regular, beyond the ratings and the QB adjustment (2016–25, 3,988
  team-games):
  - offensive-line starter: pass EPA −0.023
  - top target: pass EPA −0.043
  - opponent's top pass rusher: pressure −1.6 pts
  - opponent's defensive-back starter: pass EPA +0.029, pressure −0.45 pts
- These held in both halves and out of sample (fit 2016–20, error down on 2021–25).
- Dropped: the lead back (didn't hold out of sample), front-seven starters, and linemen
  on rushing and pressure.
- The changes feed game_nfl.project's adjustments, the script read (Games tab lines and
  the parlay reads), and a sentence under "Who's hurt".

## 2026-09-25 (night): game reads in the fun parlays

- Pass-game legs get the Games tab's script lean (settings `preview.script_lean`, unchanged)
  as a "with our read" chance. Slips are ranked by value with the read, and legs it
  favors are tagged. Fair odds and the worth-it verdict stay on the market. No pick
  thresholds or real-money prices changed (the fun bucket only).

## 2026-09-25 (night): fun-parlay simulator v1 (`betlab backtest sgp`)

- First backtest of how parlay legs move together: 816 games (2023–25) by role, and
  84,178 pairs of real 2025 FanDuel lines. QB–receiver stacks, shootouts and four-leg
  lifts matched real games; the simulator's joint beat independent legs on real lines
  (0.024 per QB–receiver pair, SE 0.003).
- `game_sim_nfl.SimParams`, fit on 2021–24 team-games and checked on 2025:
  - `surprise_targets` −0.158, `surprise_carries` +0.291 per point of margin surprise
    (was half the pregame script coefficients: −0.175, +0.15)
  - `vol_corr` −0.32 (the leftover pass/run trade-off; was 0)
  - `eff_beta` 0.13 for yards per target, `eff_beta_rush` 0.053 for yards per carry
    (both were 0.10)
  - `other_td` 0: unlisted players score no TDs (was 1)

  On 2025: the pass/run pairs moved toward reality, single-player CRPS was unchanged,
  and TD log loss went 0.5215 → 0.5203.
- Tried and dropped: TDs weighted by receiving yards (no gain).

## 2026-09-25 (evening): NBA live pricing, two data fixes

- **All-Star games dropped** from every NBA table (`sources/nba.py`): ESPN labels them
  regular season, and they were dragging stars' features after the break. Refit on the
  same test: v3 with lineup minutes error 4.55 → 4.48 (naive 5.06 → 4.96 on the cleaner
  test set), log losses unchanged to the third decimal (points .6560 → .6561, PRA .6523 →
  .6522). Usage betas: points 0.087 → 0.081, assists 0.186 → 0.174.
- **League-average leak fixed** in the opponent features (`player_nba._team_context`): the
  league mean now uses only earlier games (an expanding mean). The backtest was unchanged
  to four decimals.
- **Live path:** `player_games` takes "pending" rows (tonight's players);
  `models/live_nba.py` builds them. `validate_on` shows the live features match the
  backtest's (every feature exact except the opponent factor, within 0.0001).
- **NBA props priced** (`cards/props_nba.py`): market-only (model weight 0), under the
  existing props thresholds. `data/models/nba_player.json` refit.
- **Prop CLV** (all leagues): the close must be a snapshot taken after the pick was logged.
  Before, a pick made from the last pre-kickoff snapshot would have been "closed" against
  its own price. The two NFL prop picks graded so far were closed on a later snapshot, so
  they're unaffected.

## 2026-09-25 (late afternoon): NBA player model v3

- Kept: players returning from missed games (`returning`, `long_absence` in the minutes
  model): returning players' minutes error 6.55 → 6.13; small gains on every stat.
- Tested and dropped: position-specific defense (worse on every stat), a recent-form rate
  (never chosen by tuning), team road trips and rest differences (no signal).
- `data/models/nba_player.json` now holds v3 settings (`pre_lineup`, `lineup`).

## 2026-09-25 (afternoon): NBA player model v2

- Usage shifts when teammates sit (`usage_beta`), blowout minutes from the expected margin,
  combos (PRA, P+R, P+A, R+A), and an optional starting-lineup feature. Knowing the lineup
  cut minutes error from 4.89 to 4.57 and improved every stat's log loss (points .6649 →
  .6564, PRA .6657 → .6527). `data/models/nba_player.json` now holds `pre_lineup` and
  `lineup` settings.

## 2026-09-25 (day): NBA team and player models v1

- `models/team_nba.py` (ridge offense/defense/pace; back-to-back −2.2 per 100) and
  `models/player_nba.py` (minutes × rates × matchup × pace; negative binomial; per-stat
  calibration). Tested on 2025-26 after fitting on 2024-25: better than naive baselines on
  margin, total, minutes and every stat's distribution. Settings:
  `data/models/nba_team.json`, `data/models/nba_player.json`.
- Also: grading crash fixed (text columns stay text in the ledger); college pulls start Sep 25.

## 2026-09-25 (night): college efficiency engine and early read; fun ledger

- **College** (`models/game_ncaaf.py`, `cards/preview_ncaaf.py`, `backtest_cfb.py`):
  advanced-stat unit ratings; College view on the Games tab; an early-week read that beat
  opening lines out of sample (totals 54.7%, strong spreads 55.7%, 2022–25) but not
  closing lines. Tracked in `data/ledger/cfb_reads.csv`; not priced.
- **Fun ledger** (`fun_ledger.py`, `data/ledger/fun.csv`): every priced or marked
  parlay graded leg by leg.
- **Pre-kickoff pulls** cover college too (Saturday ticks) and Sunday's 1 PM and late NFL
  windows, so picks and props have near-closing prices for CLV.

## 2026-09-25 (later): matchup notes and the prop-line tracker

- **Matchup notes (unconfirmed)** on the Games tab: yards per target allowed to the
  receiver's position group and deep-ball fit (`models/matchups_nfl.py`, settings
  `preview.matchup_read`: 0.043 and 0.065 log-odds per SD, joint fit on 2025 lines).
- **Tracker** (`tracking.py`, `data/ledger/prop_lines.csv`): every FanDuel main line
  with the market, features, reads and result; `betlab grade` fills results.
- **Not in picks or prices.**

## 2026-09-25: QB changes, injuries and weather in the Game Previews

- **QB ratings** (`game_nfl.qb_ratings`, `qb_adjust`; `GameParams.qb_*`): a different
  starter moves the team's pass rating by 0.8 × his gap to the QBs behind it. After a
  QB change the pass EPA error fell 8.7% on 2016–22 (not tuned on) and 10.7% on 2023–25.
- **Weather** (`game_nfl.WEATHER`, `sources/weather.py`): wind above 10 mph, rain or
  snow, and freezing cold move passing efficiency and pass rate by amounts fit on
  7,284 team-games 2012–25; only effects over 2 SEs are used.
- **Script lean refit** with QB and weather in the matchup: matchup 0.073 → 0.068,
  volume 0.94 → 0.96; strong-matchup hit rate 54.6% vs the market's 50.2%.
- **Still Games tab only:** no change to picks, prop prices or fun parlays.

## 2026-09-24 (late night): game-flow engine, Game Previews, script lean (Games tab only)

- **New model:** `models/game_nfl.py` rates every offense and defense unit from
  play-by-play (opponent-adjusted weighted ridge) and projects plays, pass/run mix and
  points. Walk-forward 2023–25 it lost to the market on margin (MAE 10.4 vs 9.7) and
  total (10.4 vs 10.1), so it gets **no weight on the score**. It beat a team's recent
  average on dropbacks (6.38 vs 6.69), so it describes volume.
- **Script lean** (`props_market.script_lean`, settings `preview.script_lean`):
  pass-game props move with the pass matchup (+0.073 log-odds per SD, SE 0.028) and
  projected dropbacks (+0.94 per log ratio, SE 0.47). Fit on 5,245 2025 lines; the
  side a 1+ SD matchup favored hit 53.6% vs the market's 49.8%. Rushing: no effect.
- **Where it's used:** only the Games tab. Picks, prop prices and fun parlays are
  unchanged until another season agrees.

## 2026-09-24 (night): NFL player props on the card (paper)

- **What's new:** `cards/props_nfl.py` prices every FanDuel main line (receptions,
  receiving, rushing and passing yards) from a props snapshot at most 3 hours old.
  - p_market: the over-corrected market.
  - p_model: v0.2's read, shown for learning.
  - Model weight: 0.
  - Pick bar: 5% EV, one pick per player.
- **Paper only:** at the close in 2025 this rule was break-even. The point is to
  measure closing-line value from morning prices.
- **Grading** (`grading.grade_props`): settled from player stats; a snap with no
  stats counts as zero, and no snap voids the bet. CLV is measured against the last
  props snapshot before kickoff at the pick's own line.
- **First picks** (Sep 24, Falcons @ Packers):
  - Olamide Zaccheaus under 10.5 receiving yds −113
  - Austin Hooper under 0.5 receptions +106

## 2026-09-26: anytime TD read (fun tickets only)

- New `models/td_nfl.py`: TD chance from red-zone and inside-10 share, usage, recent TD
  rate, position and team expected points. Held out on 2025 it beat usage + team points
  by +0.0024 log loss (SE 0.0009); red-zone role alone +0.0020 (SE 0.0006).
- Used only in the fun bucket's TD tickets and TD legs, at half weight toward Pinnacle's
  no-vig chance, because it was never tested against a TD market. Tracked all season in
  `data/ledger/td_reads.csv`. No picks use it.
- Fix: `sgp.build_legs` crashed a game's whole fun build when an alt rung had zero
  simulated chance (Panthers @ Browns was missing on Sep 26).

## 2026-09-26: prop unders need 10% EV

- `picks.min_ev.prop_under: 0.10` (Mike's rule): a prop under is a pick only from 10%
  EV; 5-10% unders are leans. Overs keep 5%. Stricter, so no backtest needed; on Sep 26
  it would have kept 2 of the 19 under picks.

## 2026-09-24 (evening): props tested against real 2025 lines; market over-lean corrected

- **Data:** backfilled 240 games of 2025 prop lines (9,603 paid credits).
- **Market over-lean:** Pinnacle's no-vig prices lean toward overs. The fair
  probabilities for receptions (−0.18 log-odds) and receiving yards (−0.17) are now
  shifted toward the under (`props.market_shift`, `props_market.over_shift`). This
  applies to the fun parlays' fair odds and every future straight-prop price.
- **Evidence:**
  - Receptions: 95% interval [−0.25, −0.12]; receiving yards [−0.22, −0.11].
  - Out of sample, the correction beat the raw market by 0.004 in log loss.
- **Model weight stays 0.** Against the corrected market, v0.2 earned 0.07 on
  receptions and 0 elsewhere out of sample.
- **Straight props stay paper-only.** FanDuel-vs-market picks showed no edge an hour
  before kickoff. Details: `MODELS.md`.

## 2026-09-24 (evening): NFL props model v0.2 (roles, matchups, absences)

- **New:** `models/roles_nfl.py`, the walk-forward harness `backtest_props.py`, and
  snap counts in the data. See `MODELS.md` for the method and the full table.
- **Evidence** (2023–2025, about 8,000 receiving, 3,000 rushing and 1,500 QB games):
  - CRPS improved on every stat: receptions −5.0%, receiving yds −3.7%, rushing yds
    −5.5%, passing yds −4.6%.
  - Bias shrank to within 1.6 yards / 0.14 receptions.
- **Kept, each because it lowered the error:**
  - snap-share roles
  - filling the players who play to 96% of volume
  - light shrinkage: snap share 0.1 games, per-snap rates 12
  - matchups (small but consistent)
  - team volume that skips games with under 60% of usual passes (passing bias −3.0 → −0.3)
- **Rejected:**
  - stronger lead-back prior (0.78)
  - faster snap half-life (1.5)
  - lighter rate prior of 6 (rushing got worse)
  - opponent-adjusted volume (worse on every stat)
  - wider share spread (κ 25): tails looked better but CRPS got worse for receiving
- Weight in prices stays 0 until real prop lines are backtested.

## 2026-09-24 (later): fun parlays use likely legs only

- Parlays now have 4–5 legs, each 55–80% likely on its own (`fun.min_leg_p`,
  `max_leg_p`); the band is now +150 to +1,000. Mike's request: the first slips each
  leaned on a +400 to +640 rung "that's basically never going to hit."
- Evidence on correlation pricing: FanDuel's quotes for the first 5 slips were within
  about ±7% of our fair odds (details in `MODELS.md`).

## 2026-09-24: NFL game simulator v0 and fun parlays (preview, fun bucket only)

- New: `models/game_sim_nfl.py` (joint draws of a whole game, TD allocation,
  injury-report redistribution), `props_market.py` (no-vig main lines, calibration,
  yard rescaling, alt-ladder tail fit, raking) and `sgp.py` (parlay search). Details in
  `MODELS.md`.
- Evidence so far (Falcons @ Packers, Sep 24): raking converged to 0.05 pp on 42
  market constraints. Correlations looked plausible (QB–WR1 0.45, WR1–WR2 −0.01).
- Problems found and fixed the same day:
  - Low-usage players' tails were far too fat (Jonnu Smith 30+ yards: model 24% vs
    books ~10%). Fixed with the ladder fit, the other-book ceilings and the
    plausibility gap.
  - BetOnline's alt ladders disagreed with every other book, so they're excluded.
- Not backtested; no weight in any straight pick.

## 2026-09-23: NFL props model v0.1 (draft, not on the card)

- Added: early-exit mixture (`exit_prob` 0.05, keeps 10–70% of volume), QB share of
  team pass attempts, and carry-share concentration 20 (targets stay at 40).
- Evidence (walk-forward 2022–2025): the tails of rushing and passing yards were too
  thin, and passing yards ran 11 yards high. After the change the tails were near even,
  but projections run 7–8% low. That's partly sample bias: player stats omit zero-stat
  games. Pending: a snap-count evaluation.

## 2026-09-23: college football game model v1

- `half_life_days` 150, `ridge_pts` 1, `early_weeks` 4. Blend weights fit on later
  weeks: `w_spread` 0.00, `w_total` 0.04, `w_ml` 0.22. Outcome spreads: `margin_sd`
  17.5, `total_sd` 16.5, `market_margin_sd` 15.5, `market_total_sd` 16.0 (after
  widening the search grids, whose edges the first fit hit).
- Evidence: tuned on 2016–2021 and tested on 2022–2025. Late-season margin RMSE is
  15.97 for the model vs 15.17 for the market. The moneyline blend beat the market's
  log loss slightly (0.5288 vs 0.5296).

## 2026-09-23: pick rules

- Moneyline picks are limited to −250..+250. Evidence: NFL moneyline "value" picks lost
  about 23% ROI in the 2019–2025 test, driven by longshots.
- The model gets zero weight in early weeks (NFL ≤ 2, college ≤ 4), and blend weights
  are fit on later weeks only. Evidence: the first college card flagged Akron +460 at
  "+7.8% EV" off stale ratings.
- "Check the news" needs `w_model` ≥ 0.10. Evidence: the NFL totals model (weight 0.03)
  flagged five overs that were 4–6 points high after Week 1 shootouts.

## 2026-09-23: NFL game model v1

- `half_life_days` 150 and `ridge_pts` 3 (grid search on 2009–2018). The combiner uses
  points margin and rest; EPA was dropped (collinear, negative weight).
- Key-number distribution fit on all history, with a median-centered continuous CDF
  (fixed a bias that produced ~46% "value" picks).
- Blend weights fit on weeks > 2 of 2009–2025: `w_spread` 0.01, `w_total` 0.03,
  `w_ml` 0.00. Outcome spreads 13.5/13.5; market spreads 13.0/13.5.
- Evidence (test 2019–2025): the closing market beats the model on log loss in all
  three markets. See `MODELS.md`.
