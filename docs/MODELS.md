# Models

How BetLab turns data into probabilities, prices and picks, and what the
backtests say. Code references are to `src/betlab/`.

## Pricing, in one picture

For every FanDuel offer (one side of one market):

1. **`p_model`:** our probability, conditional on no push.
2. **`p_market`:** the sharp market's no-vig probability *at FanDuel's exact line*.
   The reference is Pinnacle, else LowVig, else BetOnline, else the median of other
   books (`settings.yaml` `odds_api.sharp_books`; `market.reference_books`).
3. **`p_final`:** a blend in log-odds space,
   `logit(p_final) = w·logit(p_model) + (1−w)·logit(p_market)`, where `w` is fit on
   history per market type (`edge.blend_prob`, `edge.fit_blend_weight`).
4. **EV** at FanDuel's price, with pushes returning the stake (`odds_math.expected_value`).
5. **A tier:** pick, lean, check-the-news, or nothing (`picks.classify`).

A model that adds nothing earns `w ≈ 0`, and then picks come only from FanDuel prices
that differ from the sharp market. That is the case for football game lines today.

## Football game model

Shared by NFL and college football: `models/football.py`, `models/ratings.py`,
`models/margins.py`, and the evaluator `cards/football.py`.

### 1. Ratings (`models/ratings.py`)

Weighted ridge regression, refit before every week using only earlier games. Each game
gives two rows, one per offense:

    value = mu + home_edge·side + off[team] + def[opponent]

- `side` is +½ for home, −½ for away, and 0 for neutral sites.
- `def` is what a defense *allows*.
- Weights halve every `half_life_days`, the lookback is 800 days, and the ridge
  penalty pulls thin samples toward average.
- The value is points scored. An EPA-per-play version is fit too, but only for notes:
  EPA is 95% correlated with points ratings and got a negative weight when combined
  with them.

### 2. Combiner

- **Margin:** `margin = c0 + c1·pts_margin + c2·rest_diff`, where `rest_diff` is the
  home team's rest days minus the away team's, clipped to ±7.
- **Total:** `total = d0 + d1·pts_total`.

Both are fit by least squares on walk-forward predictions (`fit_params`).

### 3. Key-number distributions (`models/margins.py`, `KeyNumberDist`)

Football margins cluster on 3 and 7, so a normal curve misprices −2.5 vs −3.5. We
reweight each integer by how much more often it occurs than a smoothed curve predicts.
Fitted from NFL history:

| Margin | Weight |
|---|---|
| 3 | 2.4× |
| 7 | 1.76× |
| 10 | 1.56× |
| 0 (a tie) | 0.05× |

Two fixes matter here:
- **Median centering.** The reweighted curve is shifted so its median sits at our
  prediction. Without that, the spike at 3 drags the midpoint and the model
  systematically liked underdogs: "positive EV" picks won only ~46%.
- **A continuous CDF.** Each integer's probability is spread over its unit interval,
  so the median moves smoothly. A discrete median jumps at integers (3.1 and 3.9
  priced identically).

`over_push_under(center, sd, line)` gives P(over), P(push) and P(under) for any line.

### 4. Reading the market at FanDuel's line (`center_for`)

When the sharp book hangs −3 and FanDuel hangs −3.5, we don't compare them directly:
1. Solve for the distribution center at which the sharp book's no-vig price is fair at
   its own line.
2. Price FanDuel's line off that same distribution.

This uses the market-centered spreads `market_margin_sd` and `market_total_sd`.
Across several reference books we take the median center.

### 5. Blend and early weeks

- **Blend weights:** `w_spread`, `w_total` and `w_ml` are fit by minimizing log loss
  of outcomes against the closing no-vig price. The fit uses only weeks after
  `early_weeks`.
- **Early weeks:** through that week, ratings lack current-season data, so live pricing
  uses `w = 0`, meaning pure market. That's the NFL through week 2 and college through
  week 4.

### 6. Fitted settings (saved in `data/models/<league>_params.json`)

| Setting | NFL | College | Meaning |
|---|---|---|---|
| `half_life_days` | 150 | 150 | Rating memory (tuned) |
| `ridge_pts` | 3 | 1 | Shrinkage; college has bigger talent gaps |
| `margin_coef` | [0.12, 0.96, 0.18] | [−0.62, 1.11, −0.58] | c0, points margin, rest |
| `total_coef` | [14.36, 0.68] | [16.54, 0.70] | d0, points total |
| `margin_sd` / `total_sd` | 13.5 / 13.5 | 17.5 / 16.5 | Outcome spread around *our* number |
| `market_margin_sd` / `market_total_sd` | 13.0 / 13.5 | 15.5 / 16.0 | Outcome spread around the *market's* number |
| `w_spread` / `w_total` / `w_ml` | 0.01 / 0.03 / 0.00 | 0.00 / 0.04 / 0.00 (0.22 until 2026-10-09) | Weight on our model in the blend |
| `early_weeks` | 2 | 4 | Market-only through this week |

To refit, delete the JSON: the next `card` or `grade` run refits from all completed
games (`football.production_params`).

### 7. Backtests (`backtest.py`, `betlab backtest nfl`)

These are walk-forward: settings are fit on a training block, then judged on later
seasons the fit never saw. Lower log loss is better.

**NFL, tested on 2019–2025** (trained on 2009–2018):

| Market | Market log loss | Model | Blend |
|---|---|---|---|
| Spreads | **0.6922** | 0.7114 | 0.6926 |
| Totals | **0.6929** | 0.7088 | 0.6931 |
| Moneyline | **0.6080** | 0.6382 | 0.6094 |

- **Spread picks at closing prices:** EV ≥ 0 went 235-209 (52.9%). Higher thresholds
  are noise around break-even.
- **Moneyline "value" picks:** these lost about 23% ROI, concentrated in longshots.
  That's why the −250..+250 guard exists.
- **Blend weights refit on 2019–2025 alone:** 0.0 for all three markets.

**College, tested on 2022–2025** (trained on 2016–2021):

- **Spreads and totals:** CFBD lines have no prices, so we assume −110, which makes
  the market's log loss exactly ln 2 = 0.6931.
- **Spread accuracy:** our raw model's spread log loss was 0.82, badly overconfident.
  Late-season margin RMSE is 15.97 for the model vs 15.17 for the market. Early-season
  (weeks 0–3) RMSE is 21.8, because of roster turnover the ratings can't see.
- **Moneyline:** the blend (w 0.15 then) scored 0.5288 vs the market's 0.5296.
  Picks at EV ≥ 3% went 145-176 for +33.5u, about one standard error and at consensus
  prices, not FanDuel's. So it's not evidence of an edge yet.
- **Production refit** (later weeks only): `w_ml` = 0.22.
- **Set to 0 on 2026-10-09** (weak-spot review #1): live, the 15 college ML bets that were +EV only
  because of the model closed -2.0% CLV on average (SE 0.8), 33% beat the close. College moneylines
  are market-only now; the model's view stays on the Games tab.
- **History rebuilt 2026-09-25** with moneylines averaged as probabilities (the old
  file averaged American prices, so books straddling even money gave nonsense like
  "−5"). The quick fix had been dropping those rows.
  - About 50 near-pick'em games are usable again; most other changes were rounding
    (−1425 became −1421).
  - The refit left every weight unchanged (spreads 0, totals 0.04, moneyline 0.22).
  - Out of sample (fit 2016–21, tested 2022–25, 2,759 games) the moneyline blend beats
    the market by 0.0016 log loss per game (SE 0.0012; positive in 90% of bootstraps).
    It was positive in 2022, 2024 and 2025, negative in 2023. A thin edge, not a proven
    one.
  - Moneylines start in 2021 in CFBD, so the 2016–21 fit leans on one season.
- **When the model disagrees with the moneyline market** (2022–25):
  - Under 12 points: the blend helps a little.
  - 12–20 points (19% of games): the model's side won exactly what the market said
    (35.2% vs 35.2%; the model said 50.8%).
  - 20+ points (16%): its side won 5–7 points more than the market said (36.7% vs
    31.3%; 32.5% vs 25.2%), but far less than the model said (55–62%).
  - So "check the news" flags start at 20 points (`picks.check_news_min_gap`). Picks
    and leans still stop at 12.

**Takeaway:** for football game lines the closing market is better than our ratings.
The model's role is small (college moneylines after week 4), and most picks come from
FanDuel lagging the sharp books. Closing line value on live paper picks is the test.

## Pick rules (`picks.py`, thresholds in `config/settings.yaml`)

- **Pick:**
  - EV of at least 3% (game lines) or 5% (props).
  - Our model and the market within 12 percentage points.
  - Moneylines only between −250 and +250.
- **Lean:** EV of at least 1% and within the 12-point gap. Shown for learning, never
  bet.
- **Check the news:** the gap is 20 points or more (`check_news_min_gap`; 12–20-point
  gaps carried no information in the college backtest) *and* the model has earned weight
  (`w_model` ≥ 0.10) *and* it's the side our model likes. It's shown as a question,
  never bet. A disagreement from a model with ~0 weight isn't news, so it's hidden.
- **Props (paper):** priced by `cards/props_nfl.py` from the over-corrected market,
  with 0 weight on our model, from a props snapshot at most 3 hours old. Graded by
  `grading.grade_props` (zero-stat games count as zero; no snap voids the bet).
- **One pick per correlated group per game:** spreads and moneylines share a "side"
  group, totals are their own group, and props group per player. The best EV wins and
  the rest become leans.

## Explanations (`explain.py`)

Every pick, lean and parlay leg carries football context next to the math:
- **Props:**
  - the player's snap share and targets or carries over his last 3 games, with his
    stat lines;
  - how his usage is trending, and teammates who are out and the share they leave;
  - how this defense has treated his position against the league average (with its rank);
  - game script from the spread and implied points, and what it does to passing and
    rushing;
  - the market's over-lean.
- **Game lines:** what our ratings expect each team to score, rest, and the weight the
  ratings carry.
- **Honesty rule:** it only uses data we have, and when our model has no weight it
  says the pick comes from the price, not from the story.

## Staking (`staking.py`)

- **Paper:** every pick is logged at a flat 1 unit. We also record what two other
  plans would have bet:
  - **tiers:** 1u at 3% EV, 1.5u at 6%, 2u at 9%.
  - **quarter-Kelly:** a quarter of the Kelly fraction, capped at 2u, with 1u = 1% of
    bankroll.
- **Exposure caps** (`apply_exposure_caps`: 2u per game, 5u per day) exist and are
  tested, but are **not yet applied**. They are for the real-money phase.

## Grading and CLV (`grading.py`)

- **Settling:** a side needs `side_margin + point > 0` to win and `= 0` to push. Totals
  compare the total with the line; NFL moneylines push on a tie.
- **Profit** is flat units at the price taken.
- **CLV:**
  1. Take the no-vig closing probability of *our* bet at *our* line: center the market
     distribution on the closing line and closing prices, then price our line.
  2. CLV is the EV of our price under that probability (`odds_math.clv`). Positive
     means we beat the close.
- **Closing lines come from:** nflverse schedules for the NFL; CFBD consensus closing
  lines for college, at −110 because CFBD has no prices.

## NFL player props v0.1 (`models/props_nfl.py`): superseded by v0.2 below

Volume × share × efficiency, simulated:

1. **Team volume:** exponentially weighted targets, carries and pass attempts (half-life
   6 games), adjusted for game script. That's −0.35 targets per point of expected lead
   (trailing teams throw more), +0.30 carries per point of expected lead, and +0.25
   plays per point of total above 44.
2. **Player share:** the player's weighted share of that volume (half-life 4 games),
   shrunk toward position priors (`PRIOR`).
3. **Efficiency:** catch rate, yards per target, yards per carry and yards per attempt
   (half-life 12 games), shrunk toward position norms. QBs also get a shrunk share of
   team pass attempts.
4. **Simulation:** 4,000 draws.
   - Team volume is Normal with SD 6. Shares are Beta, with concentration 40 for
     targets and 20 for carries.
   - Receptions are Binomial, and yards per catch are Gamma with shape 1.3.
   - Rushing yards are Normal with SD 5.8 per carry.
   - Passing yards are Normal with SD 7.4 per attempt.
   - In 5% of draws the player exits early, keeping 10–70% of his volume.
5. **Pricing:** P(over) for any line is read straight off the draws (`prob_over`).

**Calibration** (walk-forward, 2022–2025, about 23,000 player-games): receiving yards and
receptions are close to calibrated (e.g. 25% → 26% and 75% → 78% over rates). After
adding early exits, QB attempt share and wider carry shares, the tails are close to
even, but projections run 7–8% low. Part of that is the sample: nflverse player stats
omit players who played and recorded nothing, which inflates the "actuals."

**Next step (to-do):** evaluate with snap counts so zero-stat games are included, then
tune. After that come FanDuel prop lines via the event-odds endpoint and a market check
against other books.

**What the model doesn't know yet:** opponent and matchup (defense vs. position, pace),
snap share, and how usage shifts when a teammate sits (the game simulator below
handles Out/Doubtful players; `props_nfl.simulate` doesn't). These come with the
backtest work, and the model gets weight in prices only if it then beats real prop
lines (rule 3).

## NFL player props v0.2 (`models/roles_nfl.py`): roles, matchups, absences

The model behind the Fun tab's "our read" and the parlay simulator since 2026-09-24.
It builds the inputs for the joint game simulator (`game_sim_nfl.simulate_teams`):

1. **Role from snap share.** Snap share from the last few games (half-life 2 games;
   games for a previous team count 0.3), times per-snap rates: targets per team target
   while on the field, and carries per team carry (half-life 8 games, lightly shrunk
   toward the position). A backup on 10% of snaps gets a backup's share.
2. **The team adds up.** The shares of the players who play are scaled to 96% of the
   team's targets and carries; 4% goes to an "other" bucket.
3. **Absences.** Regulars ruled out (injury report) are removed, and the shares above
   hand their volume to the players who play.
4. **Matchup.** The opponent's last 16 games: yards per target and catch rate allowed
   to WRs, TEs and RBs, and yards per carry allowed, each relative to the league and
   shrunk toward average, multiply the player's efficiency.
5. **Team volume** from the team's recent games and game script, leaving out games
   where it threw under 60% of its usual passes (starters rested, QB hurt).
6. **Zero-stat games count.** Snap counts (PFR ids mapped to gsis ids) add the games
   where a player played and recorded nothing; nflverse's player stats omit them.

**Backtest** (`betlab backtest props`, `backtest_props.py`): every 2023-2025
regular-season game, walk-forward, both teams simulated together from the players
who took a snap. It scores prop-worthy players (by their last 4 games) against what
happened, zeros included. The table shows CRPS, the error over the whole distribution
(lower is better), and log loss at a naive line (the player's last-6 median + 0.5):

| Stat | n | CRPS v0.1 → v0.2 | Log loss v0.1 → v0.2 | Bias v0.1 → v0.2 |
|---|---|---|---|---|
| Receptions | 8,033 | 1.204 → 1.144 | 0.672 → 0.643 | −0.57 → −0.14 |
| Receiving yds | 8,033 | 16.15 → 15.54 | 0.680 → 0.657 | −6.4 → −1.6 |
| Rushing yds | 3,026 | 17.24 → 16.30 | 0.682 → 0.635 | −6.3 → −1.3 |
| Passing yds | 1,539 | 48.44 → 46.21 | 0.705 → 0.678 | −2.0 → −0.3 |
| Anytime TD | 10,912 | 0.221 → 0.217 | 0.530 → 0.517 | −0.05 → −0.02 |

Alt-rung calibration (predicted minus actual) improved from −4 to −10 points to −1 to
−5. The lowest rungs are still a little light: 3+ receptions −4.7, 30+ receiving yards
−4.0, 200+ passing yards −4.0.

**Against real prop lines** (`betlab backfill props`, `backtest_props.market_eval`):
6,455 FanDuel main lines from 2025 weeks 3–18, each snapshot about an hour before
kickoff. The market is Pinnacle's no-vig price where it has the player (89%), else
BetOnline or a consensus. The model is v0.2 from the same pregame simulation.

| Stat | n | Market log loss | Model alone | Best blend (model weight) | Overs priced / overs hit |
|---|---|---|---|---|---|
| Receptions | 2,384 | 0.6792 | 0.7035 | 0.6768 (0.22) | 48.9% / 44.5% |
| Receiving yds | 2,402 | 0.6932 | 0.7147 | 0.6922 (0.17) | 50.5% / 46.3% |
| Rushing yds | 1,210 | 0.6909 | 0.7367 | 0.6905 (0.08) | 50.2% / 48.7% |
| Passing yds | 459 | 0.6918 | 0.7752 | 0.6918 (0.00) | 50.4% / 51.9% |

What it means:
- **The model alone loses to the market** on every stat.
- **The market leans toward overs.** Correcting receptions (−0.18 in log-odds) and
  receiving yards (−0.17) beat the raw market out of sample (fit on weeks 3–10,
  tested on 11–18). Receptions went 0.6765 → 0.6725 and receiving yards
  0.6946 → 0.6901. Both corrections are in `settings.yaml` `props.market_shift`;
  rushing and passing shifts weren't clearly non-zero, so they're left out.
- **The model adds little once the market is corrected** (weight 0.07 for receptions,
  0 elsewhere, out of sample). Its earlier blend weight mostly came from running low,
  which lined up with the under lean. **Its weight in prices stays 0.**
- **FanDuel vs. the market an hour before kickoff:**
  - Betting where FanDuel beat the *uncorrected* market by 5%+ EV lost 21.6 units on
    105 bets (mostly overs).
  - Betting every FanDuel over lost 11.6%; every under broke even (+0.1%).
  - With the correction, 5%+ EV bets in weeks 11–18 went +7.9 units on 480 bets, which
    is noise.
  - **No proven edge at the close;** any lag edge would show in morning prices, which
    closing-line value on live paper picks will measure.

**ML v1 (Oct 10, Mike: "are we doing ML for NFL player props"; `models/props_nfl_ml.py`,
`betlab backtest nfl-props-ml`):** Poisson-loss trees per stat on every 2016-24 player-game
(role and volume, efficiency, team volume, the opponent's yards allowed by position, spread and
total, who's missing), P(over) from each stat's residual shape by position. Scored on the same
6,455 FanDuel lines from 2025:

| Stat | Market | Corrected | v0.2 | ML | ML weight (fit wk 3-10) | Corrected → blend, wk 11-18 |
|---|---|---|---|---|---|---|
| Receptions | 0.6792 | 0.6751 | 0.7037 | 0.6944 | 0.13 | 0.6725 → 0.6722 |
| Receiving yds | 0.6933 | 0.6898 | 0.7147 | 0.7122 | 0.00 | 0.6896 → 0.6896 |
| Rushing yds | 0.6909 | 0.6909 | 0.7387 | 0.7552 | 0.04 | 0.6865 → 0.6861 |
| Passing yds | 0.6918 | 0.6918 | 0.7679 | 0.7625 | 0.00 | 0.6911 → 0.6911 |

- ML beats v0.2 on receptions, receiving and passing yards, loses on rushing; **neither beats the
  market**, and ML's out-of-sample blend gain is a rounding error (0.0003 on receptions). Its weight
  in prices stays 0.
- The only betting result that looked like money (receiving-yards unders, +28.9 units on 183 bets in
  weeks 11-18) had ML weight 0: it's the over-lean correction alone, already in the card.
- What's left for ML is what the closing market might still miss: morning prices (the props lag
  study) and the market layer on logged lines (mid-November), where the market price is an input
  rather than the thing to beat.
- **2024 repeats it** (Oct 20, the 2024 backfill's 6,265 FanDuel lines; trained on 2016-23): market 0.6901, v0.2 0.7284,
  ML 0.7312; the blend fit on weeks 3-10 scores 0.6891 against the market's 0.6889 in weeks 11-18 (worse on receptions
  and passing yards, better only on rushing, 0.6920 vs 0.6942). Two seasons, no edge: weight stays 0.

**Where the over lean lives** (checked Sep 26, same 6,455 lines, `m2025` rerun): Mike
asked for over picks, since every straight was an under. The lean isn't in one corner
that star overs could escape. Receptions and receiving yards come up short at every line
size (receiving yds: −0.16, −0.15, −0.25, −0.14, −0.11 in log-odds from under 25 yds to
70+; receptions −0.08 to −0.31 by line). Rushing (−0.06, SE 0.06) and passing (+0.06,
SE 0.09) show none.

On Sep 26's 385 FanDuel lines, overs averaged −6.5% EV against Pinnacle's plain no-vig
price and unders −6.1%, and only 2 lines of either side cleared +5%. So FanDuel wasn't
lagging at all. The 19 under picks came from the over-lean correction alone, and no
over had value either way. Overs to cheer for live in the fun bucket instead
(`sgp_plus.py`: the Fun tab's slates), with their cost shown.

**Morning-line CLV: does FanDuel lag in the morning?** (Sep 28, `props_lag.py`,
`betlab backtest lag`)
- **Setup.** From the committed props snapshots, each FanDuel main line in the last
  snapshot 3+ hours before kickoff is priced against the sharp no-vig price at its
  exact point, first in the morning and then at the close (the last snapshot within
  2 hours of kickoff).
  - Pinnacle quoted FanDuel's number on 97% of lines. Other points are skipped rather
    than translated.
  - CLV is on the plain sharp close.
- **Sep 27 (14 games, 780 sides):**
  - The average side was −6.1% against the sharp price, morning and close alike.
  - **The 19 sides that were +EV against Pinnacle in the morning beat the close by
    +2.8% (SE 1.7%). 68% beat it; at 2%+ morning EV, 6 of 6 did (+5.4%).**
  - The signature is a lag. Pinnacle barely moved (+0.5 points toward those sides),
    and FanDuel moved +2.0 points toward Pinnacle.
  - It's one Sunday: suggestive, not proven.
- **The over-lean correction picks the losers.** Unders the card would take (corrected
  EV 5%+) were −1.1% against the plain morning price and lost −1.3% to the close
  (21% beat it). Sunday's card did the same: 24% beat the close.
  - The correction may still be right about results, since overs hit less than
    priced in 2025. But it can't show up as CLV, and the go-live checklist judges
    props on raw CLV. That's for the weekly review.
- **More data:** every Sunday adds about 14 games. A 2025 morning backfill would give
  about 240 games in one go: about 40 paid credits a game, paired with the saved
  hour-before snapshots.

> **Rushing yards, Oct 26, 2026: the market's over lean is real, but no shift in picks.** Overs hit below Pinnacle's
> no-vig chance in all three seasons (2024 -3.5 pts, SE 1.5; 2025 -1.4, SE 1.3; 2026 -7.0, SE 2.3 through week 7).
> Leave-one-season-out (shift fit on two seasons, `over_shift`'s log-odds form, b = -0.10 to -0.18): the corrected
> chance matches the hit rate (46.8% vs 47.2%, plain 50.3%) and held-out log loss improves in 2 of 3 seasons, pooled
> -1.2e-3 (SE 1.3e-3, not significant). As picks it loses: under today's rules (overs 5%+ EV, unders 10%+) the shift
> drops 50 rushing overs that hit 56% (+7.4% ROI, SE 13.4%) and adds 42 unders that hit 47.6% (-10.0%); with unders
> at 5% it adds 399 unders hitting 51.9% (-1.4%, SE 4.7%). The lean is about the size of FanDuel's -112 vig, and
> the overs it would block win on FanDuel's lag. Kept as a note; it would be worth a look only at a no-vig price.

> **Market leans in every sport, Oct 26, 2026 (closing prices, season by season; nothing bettable).** How often each
> kind of side won against the close's no-vig chance, and what it paid at the closing price:
> - **The de-vig method matters, and ours (power) is right.** With a plain proportional de-vig, favorites look
>   underpriced and long shots overpriced (college hoops 5/5 seasons, z ~6; soccer 60-80% favorites 7/7). Power
>   removes it in the NFL and college hoops (college hoops' best log loss: 0.5304 vs 0.5321). Soccer: Shin's log loss
>   is a hair better (0.57302 vs 0.57305), and `soccer.no_vig` (proportional) still grades the soccer closes.
> - **College football moneyline dogs at 20-40% (power):** won 33.0% vs 29.8% priced, 6/6 seasons (2021-26, 2,025),
>   +2.2% ROI at the consensus close (SE 3.1%, by week); home dogs +8%, away -2% (picked after looking). A watch item:
>   college moneylines are market-only (Oct 9), and our picks price them against Pinnacle, not this consensus.
>   Tracked from Oct 27 against Pinnacle's own close (`cfb_dogs.py`, `data/ledger/cfb_dogs.csv`; Mike, Oct 26).
> - **College hoops dogs of 14+ against the spread:** 52.6% (4,329), but 57.1% in 2022 and 51-53% since: under
>   the 52.4% that -110 needs.
> - **No lean:** NFL totals, spreads, favorites, moneylines (2012-25, every bucket within ~1.5 pts, signs flip by
>   season); college totals and spreads (2014-26); college hoops totals; soccer home/draw/away and over 2.5 (2019-25,
>   all within 1 pt); NHL totals. NHL moneylines: only 2025-26 is a real two-way price (ESPN's Unibet years are not,
>   as `backtest_nhl` already notes).

## NFL game flow (`models/game_nfl.py`) and Game Previews (`cards/preview_nfl.py`)

Built 2026-09-24 because Mike wanted the reasoning to start from how a game goes
(team vs. team, offense vs. defense) rather than from prices. `betlab preview` writes
a preview of every NFL game in the next week to the page's Games tab.

1. **Team-game stats from play-by-play** (`team_games`, nflverse pbp, current season
   and the two before): plays, seconds a play, neutral-situation pass rate, pass rate
   over expected, dropbacks and rushes, EPA and success rate per dropback and per
   rush, pressure rate (sacks + QB hits per dropback), explosive-play rate, red-zone
   TD rate, turnovers, points.
2. **Opponent-adjusted unit ratings** (`fit_ratings`): each stat = league + home edge
   + offense[team] + defense[opponent], weighted ridge regression (half-life 120
   days, ridge 4), games strictly before the date. Pass stats are weighted by
   dropbacks and run stats by rushes. `ranks()` ranks every unit 1–32.
3. **Projection** (`project`): plays, pass rate (the neutral rate moved by the game
   script: −0.0025 per point of expected margin, fit on 2023–24), dropbacks, rushes,
   EPA and points. With `market_margin_home` the script follows the market's spread.
4. **Words** (`matchups`, `script_text`): the unit-vs-unit edges in league standard
   deviations, biggest first, and a few sentences on score, pace and run/pass.
5. **Who starts at QB** (`qb_games`, `qb_ratings`, `qb_adjust`, added 2026-09-25). A
   team's pass rating reflects whichever QBs took its recent dropbacks. Each QB gets
   his own rating: EPA per dropback minus what the league, home field and the
   defense explain, weighted by dropbacks and a 730-day half-life, shrunk toward a
   backup's level (−0.15, worth 300 dropbacks). When a different QB starts, the pass
   offense moves by 0.8 × (his rating − the QB mix behind the team's rating). The
   expected starter is the top of the latest ESPN depth chart (nflverse) who isn't Out
   or Doubtful on the injury report.
6. **Weather** (`weather_effects`, `sources/weather.py`, added 2026-09-25). Outdoor
   games get Open-Meteo's kickoff forecast; domes and retractable roofs get none.
   The effects were fit on 2012–25 team-games as residuals from walk-forward ratings.
7. **Who else is missing** (`injuries_nfl.py`, added 2026-09-25). Regulars are found
   from a team's earlier games this season:
   - offensive-line starters (80%+ of snaps in 2 of the last 3 games)
   - the top target (20%+ target share over the last 4)
   - the lead back
   - the top pass rusher (sacks + half QB hits)
   - front-seven and secondary starters

   Live, a regular is missing if he's Out or Doubtful on the injury report, or off the
   active roster (reserve/IR, cut, traded; those drop off the report). The effects
   below move the team's unit (and the opponent's, for defenders), flow into the
   script read and the parlay reads, and get one sentence under "Who's hurt".

8. **The Notebook** (`cards/notebook_nfl.py`, Nov 6; Mike, after @conchpicks' TikTok notebooks). The preview's facts
   told one way at the top of the game page: the story (the market's score, who should throw more or less than usual),
   what changed (the QB read and injury sentences above), each defense's recent pattern in counts (a position group
   20%+ over the league's per-game yards in at least two of its last three games), and the bet, which the apps take
   from the game's own best pick or lean. Words only, no price: the scheme angles behind his notes didn't beat the
   market (DECISIONS 2026-11-06).

`betlab backtest game` reproduces all three checks:

| QB term: pass EPA error (dropback-weighted) | Team-games | Ratings only | With QB | Change |
|---|---|---|---|---|
| All games, 2016–22 (not used for tuning) | 3,646 | 0.0792 | 0.0777 | −2.0% |
| After a QB change, 2016–22 | 441 | 0.0889 | 0.0812 | **−8.7%** |
| All games, 2023–25 (tuned here) | 1,632 | 0.0847 | 0.0829 | −2.1% |
| After a QB change, 2023–25 | 225 | 0.1027 | 0.0916 | −10.7% |

Every setting in the tuning grid (prior −0.05 to −0.15, 150–600 dropbacks, half-life
1–2 years, 50–100% of the gap) beat the ratings alone after QB changes; the chosen
one sits mid-grid.

| Weather (7,284 team-games; 592 with 15+ mph wind) | Pass EPA per dropback | Neutral pass rate | Explosive-play rate |
|---|---|---|---|
| Wind, per 10 mph above 10 (capped at 25) | **−0.059** (SE 0.014) | **−1.3 pts** (0.6) | **−0.9 pts** (0.2) |
| Rain or snow at kickoff | **−0.041** (0.014) | **−2.0 pts** (0.6) | n.s. |
| 32°F or colder | n.s. (−0.017, 0.016) | **−1.7 pts** (0.5) | n.s. |

Bold effects are in `game_nfl.WEATHER`; the rest are left out. Rain counts in
proportion to its forecast chance. The run game showed no weather effect.

**Missing regulars (3,988 team-games, 2016–25; weeks 4+ so every window stays in-season;
beyond the ratings and the QB adjustment).** Each is per missing player:

| Missing | Pass EPA / dropback | Rush EPA / carry | Pressure rate | Kept? |
|---|---|---|---|---|
| Offensive-line starter (own) | **−0.023** (SE 0.008; −0.019 / −0.027 by half) | −0.008 (0.006) | +0.3 pts (0.2) | pass EPA |
| Top target (own) | **−0.043** (0.017; −0.073 / −0.020) | 0.000 | n.s. | pass EPA |
| Lead back (own) | n.s. | −0.029 (0.014; −0.055 / −0.005) | n.s. | **no**: fit on 2016–20, it made 2021–25 worse |
| Top pass rusher (opponent's) | +0.033 (0.017) | n.s. | **−1.6 pts** (0.4; −1.5 / −1.7) | pressure |
| Defensive-back starter (opponent's) | **+0.029** (0.008; +0.020 / +0.035) | +0.011 (0.006) | **−0.45 pts** (0.18) | pass EPA, pressure |
| Front-seven starter (opponent's) | +0.017 (0.012) | n.s. | n.s. | no |

The rule is 2+ standard errors with the same sign in 2016–20 and 2021–25. Out of sample
(fit 2016–20, scored on 2021–25), the kept effects cut the error in games with an
absence by 1.1% (pass EPA) and 2.6% (pressure), and the pressure miss nearly vanished.

- Absences first counted with windows that crossed seasons looked bigger. A player who
  left in the offseason counted as "missing" for weeks, so every window now stays
  inside a season.
- Live counts (injury report plus weekly roster) match "didn't play" in 85–98% of 2025
  team-games. They catch nearly all missing top targets and pass rushers, and about
  three-quarters of missing linemen: Questionable linemen who sit on game day show up
  only at inactives.

**Walk-forward results (816 games, 2023–2025):**

| Target | Engine | Market (closing line) or naive |
|---|---|---|
| Margin, mean absolute error | 10.4 | **9.7** (market) |
| Total, mean absolute error | 10.4 | **10.1** (market) |
| Team dropbacks (2025) | **6.38** | 6.69 (team's recent average) |

So **the score comes from the market** and the engine explains *how* it happens: its
volume forecast beats a team's recent average by about 5%.

**Script lean on props** (`props_market.script_lean`, `betlab backtest script`):
on every 2025 FanDuel main line (backfill, T−60 min), the market's no-vig P(over)
(over-lean corrected) was compared with what happened, adding each offense's pass
matchup edge (SDs) and projected dropbacks vs. its last 8 games
(`game_nfl.script_features`). First fit, team ratings only:

| Stat | Lines | Matchup (log-odds per SD) | Volume (per log ratio) |
|---|---|---|---|
| Receptions | 2,384 | +0.063 | +0.90 |
| Receiving yds | 2,402 | +0.079 | +0.71 |
| Passing yds | 459 | +0.099 | +2.40 |
| Rushing yds | 1,210 | +0.005 | −0.12 |
| **Pass game, together** | 5,245 | **+0.073** (game bootstrap SE 0.028; positive in 99.5%) | **+0.94** (SE 0.47; 97.5%) |

- Held in both halves of the season (matchup +0.092 weeks 1–10, +0.056 weeks 11–22).
- Where the pass matchup edge was 1+ SD, the side it favored hit 53.6% against the
  market's 49.8% (2,412 lines).
- **Refit with who started at QB and the recorded weather in the matchup** (what the
  Games tab uses since 2026-09-25): matchup +0.068 (SE 0.024), volume +0.96 (SE
  0.46), steadier across the season (+0.063 / +0.075 by half). Where the edge was
  1+ SD, the favored side hit **54.6%** against the market's 50.2% (2,581 lines).
- Rushing props showed nothing, so they aren't leaned.
- **Use:** the Games tab's "Lines that fit the script" (FanDuel main pass-game props
  whose chance moves 1+ point). **Not in picks or prices:** it's one season, and it
  needs an out-of-sample season (2024 lines, to-do) before it can touch the card.
- **Not confirmed, off (Oct 28):** 2024 lines didn't agree (pass-game edge -0.007, Oct 19), and neither did 2026's
  (2,338 graded lines through Oct 26: log loss 0.6931 vs the market's 0.6914; favored sides 51.1% vs 51.6%). The
  Games tab no longer shows the lines (`preview.script_lean.show: false`); `prop_lines.csv` still tracks the read.

## NBA team and player models (`models/team_nba.py`, `models/player_nba.py`)

Built 2026-09-25, ML-first plan in `docs/NBA_PLAN.md`. The team model uses ridge ratings
for offensive rating and pace, home court, and back-to-backs. The player model is minutes
(recent minutes, starts, teammates ruled out) times per-minute rates, adjusted for the
opponent and pace, with a negative binomial distribution and per-stat calibration settings.
v2 adds usage shifts when teammates sit, blowout minutes, combos (PRA, P+R, P+A, R+A)
and an optional starting-lineup feature, the biggest single gain. Backtest results
(`betlab backtest nba`) are in `docs/NBA_PLAN.md`. They beat naive baselines on every
measure. The player model has no historical lines, so its market test starts on opening night.

**The team model against 2025-26 closing lines** (Sep 28, `betlab backtest nba`; lines
bought with `betlab backfill nba-lines`, 4,620 paid credits, docs/DECISIONS.md):
- **Data.** Spreads and totals from one snapshot 15 minutes before each night's evening
  slate, plus one before the West Coast games. 1,129 regular-season games are matched,
  and the median line is 1.0 hour before tip. The market is the median of Pinnacle,
  LowVig and BetOnline.
- **Walk-forward result: the market wins.**
  - Margin: model misses by 11.45 points, the closing line by 10.86. Blend weight −0.13
    (SE 0.10).
  - Total: model 15.09, closing line 14.60. Blend weight −0.07 (SE 0.12).
  - Lines within an hour of tip and lines 1-6 hours before give the same answer, and so
    do November-December and January-April.
- **Betting FanDuel where the model disagrees.**
  - Spreads at 2+ points: 48.1% (−8% ROI).
  - Spreads at 6+: 53.1% on 143 bets (+1.5%), which is noise.
  - Totals lose 5-7% at every gap.
- **So the NBA card stays market-only, and the team model's weight stays 0.** It's the
  same finding as the NFL and college. The card (`cards/nba.py`, from Oct 20) prices FanDuel's
  moneyline, spread and total against Pinnacle; a sharp number up to 1.5 points from FanDuel's
  is moved to it but capped at lean (Oct 4; near tip FanDuel almost never lags: 3 sides at
  3% EV in 1,045 games; docs/DECISIONS.md). The lines are now a training set for the ML
  layer, which learns corrections to the market rather than predicting from scratch
  (`docs/ROADMAP.md`).

**Can anything known before tip predict the NBA close's miss?** (Sep 28, first ML test;
the script is in the session notes, not the repo)
- **Setup:**
  - The target is the 2025-26 closing line's miss: actual minus the sharp consensus, for
    margin and total, 1,129 games.
  - Features: rest and rest difference, games in the last 7 days, 3-in-4 nights, road-trip
    length, time-zone change, altitude, each team's last 5 and 10 results against the close
    (margin and total), our team model's gap to the line, and the line itself.
  - Walk-forward by month (fit on earlier months), 845 games scored. Models: a ridge
    regression and shallow boosted trees.
- **Result: nothing.**
  - Both models made the close worse. Margin: −6.6% error explained (SE 1.6%) ridge,
    −10.4% trees. Total: −4.7% and −5.6%.
  - Betting FanDuel where they flagged 2+ points won 46-49% (−7% to −11% ROI).
  - Every feature's correlation with the margin miss is within about 1.7 SE of zero (18
    features).
  - NBA closing lines already price schedule, fatigue, travel and momentum.
- **So the NBA ML layer trains on the logged prop lines** (the softer market), as the plan
  said. Earlier-day lines were not tested: there's no opener history.

**NBA fun tickets: a copula of real-game correlations** (Sep 28, `models/game_sim_nba.py`,
`cards/fun_nba.py`). Mike's rule for the NBA is the NFL's: one SGP+ ticket per window and
straight overs to root for (in national-TV games only).
- **Each player's lines come from the market.** A negative binomial per stat, its mean
  set so the market's no-vig price at FanDuel's line is reproduced, with player model
  v3's dispersion.
- **How they move together** is a Gaussian copula. Its correlations are measured by role
  on within-player ranks, from 2024-25 regulars (30+ games, 20+ minutes). 2025-26 matched
  every entry within about 0.02:
  - The same player: points with threes 0.60, rebounds 0.27, assists 0.17.
  - With the game total: points 0.15, assists 0.11, rebounds −0.04.
  - With his team's margin: points 0.11.
  - A teammate's assists with a scorer's points: 0.07. Teammates' points: −0.01, since
    shared pace and competing for shots cancel out.
  - Opponents: about 0.
- **The game's lines:** total and home margin are normal around the market's, with SD 18.4
  and 13.9 against the 2025-26 closing lines we bought, and uncorrelated (0.02).
- **Checked on 2025-26:** how much more often both legs hit than independent legs
  would, copula / real.

  | Pair | 70% legs | 25% legs (SE) |
  |---|---|---|
  | Points + rebounds, same player | 1.069 / 1.077 | 1.46 / 1.36 (0.03) |
  | Points + threes, same player | 1.170 / 1.168 | 2.16 / 2.29 (0.03) |
  | Points + game total over | 1.039 / 1.033 | 1.26 / 1.28 (0.02) |
  | Points + his team wins big | 1.027 / 1.034 | 1.18 / 1.07 (0.02) |
  | Assists + teammate's points | 1.017 / 1.016 | 1.11 / 1.14 (0.01) |

  Likely legs are right. Some long-shot pairs are overstated; stars sit in blowouts, as
  in the NFL. So tickets keep Mike's 55-80% legs.
- **The legs:** FanDuel's main lines and, since Sep 28, its alt ladders ("25+ points"; the
  NBA pull adds four alternate markets, about +4 credits a game, Mike's choice). Alt rungs
  are capped by other books' same rung, as in the NFL.
- **Pair rule:** across different NBA players, real 70%-leg pairs reach only about
  1.02-1.07, so the NFL's rule of "one pair hitting 1.10× together" is 1.03 here
  (`fun.nba.min_pair_lift`).
- **The replay:** Mar 4, 2026's 7 PM window, run with synthetic props and the real closing
  lines, gave a 3-game ticket at fair +1785 and national-TV overs from Thunder @ Knicks.

## College football: efficiency read and the early-week edge (`models/game_ncaaf.py`)

Built 2026-09-25 (Mike: "add analysis to NCAAF"). CFBD's per-game advanced stats
(`cfbd.advanced`, 2014 on: EPA, success rate, explosiveness, pass/run splits, line
yards, stuff rate, plays) feed the NFL engine's weighted ridge (half-life 150 days,
ridge 3), FBS ranks, projections and unit matchups for the College view of the Games tab.

**Does it know anything the market doesn't?** (`betlab backtest cfb`; 6,699 FBS-vs-FBS
games with lines, week 3+, 2016–25, walk-forward):

- **Against the closing line: no.** Every net rating (EPA, success, explosiveness, pass,
  run, points, luck) and unit clash was within noise or break-even out of sample. Line
  play came closest: stuff rate +0.67 pts per SD (t 3.5) and line yards +0.53 (t 2.8),
  but strong reads won 52.2–52.4% out of sample, right at break-even.
- **Against the opening line: yes, so far.** On 2021–25 games with CFBD openers, a
  regression of (result − opening line) on the ratings and the opening line, fit on earlier
  seasons and scored on the next (2022–25):

| Read (strength) | Games | Won vs opener | Won vs close | Line moved our way | 2022 / 23 / 24 / 25 |
|---|---|---|---|---|---|
| Total, 1+ SD | 850 | **54.7%** | 54.9% | +0.39 pts | 51.7 / 58.1 / 57.1 / 54.8% |
| Total, 1.5+ SD | 369 | 53.8% | 53.2% | +0.44 pts | |
| Spread, 1+ SD | 954 | 53.2% | 53.3% | +0.16 pts | 55.4 / 54.0 / 50.2 / 52.4% |
| Spread, 1.5+ SD | 422 | **55.7%** | 56.1% | +0.14 pts | 54.4 / 55.0 / 56.6 / 60.0% |

  The ratings also predict where lines move: when the success-rate read was strong, the
  line moved its way from open to close 62% of the time. The market catches up during the
  week, so the read matters early.
- **Drivers** (shown with each read): spreads lean mostly on line play and success rate;
  totals on both offenses' efficiency against these defenses and on the total itself
  (extreme totals drift back toward the middle).
- **Use:** the College view shows strong reads (1+ SD) at FanDuel's line. Every FBS game's
  read is tracked from first sight to the last pre-kickoff look (`cfb_reads.py`,
  `data/ledger/cfb_reads.csv`: result at the first line, and the line's move toward it).
  College odds are now also pulled on Tuesdays (`cli.EARLY_WINDOW`, about 3 credits)
  and before each Saturday kickoff window. **Not in picks or prices** until 2026 agrees.
- **2026, weeks 4-8 (final look Oct 26, 545 graded reads):** strong spread reads (1+ SD): 83, 53.0% won, the line
  moved +0.47 pts their way (SE 0.15; toward 41%, against 17%). Strong totals: 77, 42.9% won, +0.40 pts (SE 0.17).
  Weak reads: no move (spreads -0.01, totals +0.04). So 2026 agrees the read anticipates the move, by about half a
  point (roughly 1.5% of win chance in college), well short of the -110 vig, and strong totals lost more than they
  won. It stays a tracked note, not a pick or a price.
- Fitted settings: `data/models/ncaaf_early.json` (refit by `betlab backtest cfb`).
  FCS mismatches are excluded (the read was tested on FBS-vs-FBS only).

## Matchup research, 2026-09-25 (what beats the market, and what doesn't)

> **Oct 19, 2026: not confirmed on 2024 lines.** ypt +0.025 (SE 0.050), deep -0.027 (SE 0.043), the combined read's
> strong side 49.0% vs the market's 50.1% (578 lines); the script lean's pass-game edge -0.007 (SE 0.025). See
> DECISIONS (2026-10-19) and `scripts/props_2024_checks.py`.

Mike asked for matchup analysis for games, lines and props. Every idea was tested for
what it adds **beyond the market** (and, for props, beyond the script lean), walk-forward.
Exploration scripts, not in the repo; port them before relying on any result.

**Props (2025 FanDuel main lines, logistic on the corrected market + script lean,
game-bootstrap SEs, per SD of the feature):**

| Matchup | Lines | Effect | t | Halves (wk 1–10 / 11+) | Verdict |
|---|---|---|---|---|---|
| Man/zone fit: receiver's yards per route vs man and zone × defense's in-season man rate | 2,400 | −0.053 | −1.4 | −0.015 / −0.094 | No edge, even with true coverage |
| Same for targets per route (receptions) | 2,382 | +0.020 | 0.5 | +0.047 / −0.015 | No |
| Target funnel: defense's target share allowed to the position group | 4,786 | +0.037 | 1.0 | −0.050 / +0.112 | No |
| **Yards per target allowed to the position group** (receiving yds) | 2,402 | +0.070 | 1.8 | +0.071 / +0.066 | Promising |
| **Deep-ball fit**: deep-target share × deep yards per attempt allowed (receiving yds) | 2,401 | +0.084 | 2.0 | +0.109 / +0.065 | Promising |
| QB yards pressured vs clean × defense's pressure rate | 458 / 4,786 | ≈0 | 0.1 / 0.2 | flips | No |

**Live since 2026-09-25 as "Matchup notes (unconfirmed)" on the Games tab**
(`models/matchups_nfl.py`, settings `preview.matchup_read`): a note appears when the
combined read moves the over's log-odds by 0.093 or more (1 SD). Every FanDuel main line
is tracked with its features and result (`tracking.py`, `data/ledger/prop_lines.csv`),
and the tab shows each read's running record against the market.

The two promising ones overlap (correlation 0.47; together +0.043 and +0.065, each
SE 0.043). Their combined read's strong side hit 55.7% vs the market's 50.1% on 644
lines, but that is in-sample, and seven matchups were tried, so a t of about 2 could be
luck. **Not in prices or picks.** They need a second season (2024 lines, or 2026 grading).

**Scheme angles, Nov 6** (`scripts/scheme_angles.py`, DECISIONS 2026-11-06): blitz rate, two-high shell rate, box
count and the offense's 2+ TE rate, walk-forward, against FanDuel's 2024 and 2025 lines (t per season): blitz -> RB
receptions -0.3 / -0.7; two-high -> RB receptions +1.8 / 0.0; two-high -> WR receiving yards -1.1 / -2.5; box -> RB
rushing yards -1.8 / -1.0; 2+ TE -> TE receptions +1.5 / -2.5. None passed (expected sign, |t| >= 2 both seasons).

**Coverage data:** man/zone is published free only after the season (nflverse
participation; 2025's file came out Feb 2026). Weekly proxies don't recover it: weeks
1–2 blitz rate, rushers, NGS cushion and separation correlated 0.03–0.32 with a
defense's man rate the rest of 2025, and adding them to last season's rate (r ≈ 0.5)
made the estimate worse. Moot anyway, given the man/zone result above.

**Game lines (3,382 games 2012–25, week 3+, vs nflverse closing lines):** unit
interactions (pass offense × pass defense, pressure allowed × pass rush, explosive ×
explosive allowed, run × run defense, red zone, pace) and the engine's own edge all
had |t| < 1.6, flipped between 2012–18 and 2019–25, and their favored side won
49–52% (−110 needs 52.4%). **The market prices team matchups fully**; the engine's job
is explaining how a game goes, not picking sides.

## Fun same-game parlays (`models/game_sim_nfl.py`, `props_market.py`, `sgp.py`): preview

Built 2026-09-24 for the $10/month fun bucket. `betlab pull-props` pulls FanDuel's and
the other books' props, `betlab fun` builds the parlays, and the page's Fun tab shows
them. **The rule: the market sets each player's line and tails; our simulator supplies
how players move together.**

1. **Joint game simulation** (`game_sim_nfl.simulate_game`, 20,000 draws). One draw is
   one version of the whole game:
   - Each team's points are drawn around the market's implied team total (SD 9.5).
     The same shock moves that offense's efficiency (±10% per SD), so a good day is
     good for everyone on that side.
   - Team targets and carries come from `props_nfl.team_volume`, shifted by half of
     the drawn margin surprise (a team that falls behind throws more).
   - One Dirichlet draw per team splits targets (another splits carries) among its
     players plus an "other" bucket, so teammates compete for the same volume.
   - The QB's passing yards are the sum of his receivers' yards.
   - Team TDs ~ Poisson(0.105 × points), split pass/rush by the team's history, then
     given to players by opportunities in that draw × their own shrunk TD rate.
   - Out/Doubtful players (the official injury report) are removed, and their share
     goes to teammates in proportion to each teammate's share.
2. **Anchoring** (`props_market.anchor`):
   - Fair main lines come from no-vig two-way prices: Pinnacle if it has the player,
     else the median of the other books. Other books' lines are moved to FanDuel's
     line with the simulator's shape.
   - Calibrate: receptions lines set team pass volume and target shares, and rushing
     lines set carry shares.
   - Yards are rescaled so P(over FanDuel's line) matches exactly. A rescale keeps each
     draw's rank, so correlations survive.
   - Tails: each player's yards are bent around the main line (X → line·(X/line)^γ)
     to match the books' alt ladders. γ is fitted per book and the median is used.
     BetOnline's ladders are skipped; they ran far fatter than every other book's.
   - Rake (iterative proportional fitting) so every main line and Pinnacle TD price
     matches exactly. On Falcons @ Packers this kept about 14,600 of 20,000 draws'
     worth of information.
3. **Search** (`sgp.search`):
   - FanDuel legs only, for anchored players and stats.
   - Where other books quote the same alt rung, their no-vig chance is a *ceiling*
     on the leg and scales down every parlay containing it, never up.
   - Legs that beat FanDuel's price by more than 8 points (4 for model-only rungs)
     are dropped as more likely our mistake.
   - 4–5 legs, each 55–80% likely on its own (about −122 to −400). Unders only as
     near-locks (75–92%), at most one per slip (Mike's rule). One leg per player:
     books price same-player legs as nearly one bet and cut the payout hard.
   - Plus one long shot per game: 2–4 legs, legs down to about 12%, fair odds +1,500
     to +6,000 (`fun.longshot`), tagged "Long shot" on the page. Mike asked for
     likely legs after the first slips each leaned on a +400 to +640 rung, and
     near-certain legs only add FanDuel's margin.
   - At least one pair that hits together at least 1.1× as often as independent legs,
     and fair odds of +150 to +1,000.
   - Ranked by the product of leg values (chance × FanDuel payout), using **our game
     read** where there is one (below). FanDuel prices correlation itself, so
     correlation alone isn't an edge.
   - **Our game read** (Mike, Sep 25: "our game reads should factor into the parlays"):
     - Each pass-game leg (receptions, receiving yds, passing yds) gets the Games tab's
       script lean (`props_market.script_lean`) applied to its fair chance. The lean
       uses the offense's pass matchup (with who starts at QB and the weather) and its
       projected dropbacks, read from `exports/previews.json`. The daily and evening
       runs now build previews before parlays.
     - Alt rungs get the same log-odds move; the lean was fit on main lines only.
     - A leg the read raises by a point or more is tagged "fits the game" with the
       read's one-line story.
     - Slips show "with our read" odds next to the fair odds: the joint times each
       leg's read/fair ratio.
     - The worth-it verdict stays on the fair (market) odds. The lean held on 2025 prop
       lines (54.6% vs 50.2%) but isn't confirmed on a second season.
4. **The real test is FanDuel's quoted price.** Mike types it into the slip; the bet
   is worth it only above our fair odds. Typed prices are saved (`fun_quotes`).

**First outside check (Sep 24, 5 slips of 2–3 legs):** FanDuel's quoted SGP prices
were +757, +1068, +1426, +1363 and +1334, against our fair +810, +1065, +1333, +1328
and +1379. That's within about ±7%, while the plain product of FanDuel's legs was
+1125 to +2532. FanDuel prices the correlation about the way our simulator does, which
is encouraging for the simulator but means correlation itself is no edge.

The page also shows **our read vs. the market**: the raw simulation's chance for each
main line next to the market's. It has no weight. Today it runs low on most overs
(the known 7–8% under-projection), which is exactly why it has none.

### SGP+ tickets and overs to root for (Sep 26, `sgp_plus.py`)

Mike's request: one parlay per slate across its games, and straight overs to cheer for.
- **Slates** are kickoff windows on one Eastern day: early (before 3 PM), late (3–7
  PM), night.
- **The ticket:** one mini same-game parlay from each of 2–4 games in the window.
  - Each mini has 2–3 legs with a correlated pair, from the same simulator and leg rules
    as the slips (legs 55–80% likely), overs and TDs only.
  - Games are independent, so the ticket's fair chance is the product of the minis'.
  - The most games that fit the band (+500 to +4000 fair) win, ranked by leg value with
    our game read.
  - Sep 27's 1 PM window: Allen, Maye, Mahomes and Darnold passing overs, each with a
    receiver, fair +2260 (+1646 with our reads), legs multiplying to +1651 at FanDuel.
- **Overs to root for:** each window's straight overs and anytime TDs (30–80% likely),
  best value first, one per player.
  - Against our fair price (which carries the over-lean correction) most cost 5–10
    cents a dollar.
  - Some turn positive with our game read (Mark Andrews 50+ yds +164: −7.5%, with our
    read +11.6%).
- **Grading:** the fun ledger grades a ticket's legs from their own games
  (`leg_games`) and waits for every game. A straight over is a one-leg slip, tracked at
  FanDuel's price.
- Only FanDuel's quoted SGP+ price can show an edge: FanDuel prices each game's
  correlation itself.
- **Mike's first quotes (Sep 26):** FanDuel paid +1107 on the 1 PM ticket (fair +2260,
  EV −49%) and +570 on the late one (fair +1147, −46%). His 23 single-game quotes ran −2%
  to −25% (median about −14%): FanDuel's cut on each game's piece multiplies across an
  SGP+ ticket. Mike wants any size anyway (he watches RedZone).
- **Game lines as legs (Sep 26, Mike's request):** FanDuel's moneyline, spread and total
  for the game (`sgp.game_line_legs`), joint with the player legs through each simulated
  game's points, priced at the sharp no-vig price at FanDuel's number (else the
  simulation, which is centred on the market's spread and total). At most one side leg
  (moneyline or spread) per slip. Favorites' moneylines (−125 to −400) carry far less
  FanDuel margin than alt yardage rungs, so they now appear in most slips ("Win it with
  them"); spreads and totals sit near 50%, under the 55% leg floor. The 1 PM ticket's legs
  went from multiplying to +1651 against a fair +2260 to +2682 against +2675.
- **Where slips show:** each window's SGP+ ticket and overs on the Fun tab, prime-time
  (7 PM ET or later) games' single-game slips there too, every other game's slips on the
  Games tab. Other sports (Mike, Sep 26): college one lines-only ticket per day (New York
  bans college props), NBA like the NFL (one per night plus national-TV singles), soccer
  one per day across all leagues; never across sports.

### Anytime TD ticket per window (Sep 26, `sgp_plus.td_ticket`)

Mike: "choose one person from each game for every slate", then "why choose the lowest
odds one every time, get some analysis in there". One anytime scorer from every game in
the NFL kickoff window: since Oct 25 each game's likeliest scorer by Pinnacle's no-vig chance (Mike: "switch the
TD tickets to the likeliest scorers"), because our TD read (below) never beat Pinnacle on 581 graded reads and now
carries no weight (MODEL_CHANGELOG); from Sep 26 to Oct 24 they were picked by value with that read. The legs are from
different games, so FanDuel pays the plain product of the leg prices: the EV shows
without a quote, by Pinnacle and with our read, next to the likeliest-scorer version.

**FanDuel's TD margin grows with the odds** (Sep 26, 128 anytime TD prices against
Pinnacle's no-vig): it pays back $0.95 per $1 of fair value on 50%+ scorers, $0.92 at
40-50%, $0.89 at 30-40%, $0.84 at 20-30% and $0.76 under 20%. That's why picking the
likeliest scorer was cheapest: the analysis has to beat that margin, not just the market.

**Our TD read** (`models/td_nfl.py`, `betlab backtest td`): logistic regression on
2022-25 player-games (RB, WR, TE, QB), each feature from the player's earlier games: his
share of his team's run/pass opportunities (last 6 games), of its opportunities inside
the 20 and inside the 10, how often he scored (last 8), his position, and the market's
expected points for his team. Trained on 2023-24, tested on 2025 (5,797 player-games,
game bootstrap):

| Model | Test log loss | Gain | SE |
|---|---|---|---|
| Usage + team points | 0.4267 | | |
| + red-zone and inside-10 share | 0.4247 | +0.0020 | 0.0006 |
| + recent TD rate | 0.4251 | +0.0016 | 0.0009 |
| + both (the read) | 0.4243 | +0.0024 | 0.0009 |

Calibrated by eighths except the top one (predicted 45%, scored 42%). Refit on 2023-25
for live use (`data/models/td_params.json`).

**Against Pinnacle, 2026 (first pass Oct 20, 563 graded reads, 59 games):** the model alone loses (log loss 0.561 vs
0.553, SE 0.0065); the half-weight read ties the market (+0.0004, SE 0.003). Where they disagree most the market is
right both ways (model 8+ pts higher: scored 16.2%, Pinnacle 16.1%, model 28.1%; 3+ pts lower: 38.1%, 38.9%, 30.2%).
Final check after Oct 25; whether to drop to the likeliest scorers is Mike's call (his Sep 26 request).

- **Not tested against the TD market:** the 2025 backfill has no anytime TD prices. So
  the read counts at half weight next to Pinnacle's chance (log-odds), and every read is
  tracked this season (`td_reads.py`, `data/ledger/td_reads.csv`): does it beat
  Pinnacle's log loss, and do the players it likes score more than Pinnacle said?
- **Sep 27 tickets:** the 1 PM read ticket (9 games; Hampton, Denzel Boston, Chase Brown,
  LaPorta, Woody Marks, Chris Rodriguez Jr., Rashee Rice, Skattebo, Croskey-Merritt)
  pays +537,005 at FanDuel: EV -67% by Pinnacle, -34% with our read; the likeliest-scorer
  version pays +17,418, -43%. The late ticket (Michael Wilson, Bucky Irving, Henry,
  Brock Bowers): +4,044, -40% by Pinnacle, -5% with our read (likeliest: +571, -22%).
- Our game simulator's own TD chances run 7-12 points under the market on the top
  scorers, so they aren't used for the read.

**Mike's quotes (Sep 26, 66 slips and 4 SGP+ tickets):** slips with only player legs
median EV -23%, slips with a moneyline or total leg -19%, SGP+ tickets -34% to -49%.
Several 3-leg long shots mixing a game total with big yardage rungs priced above our
fair odds (+20% to +46%): either FanDuel underprices those links or our simulator
overstates them. The total and moneyline links are untested; to-do c-sgp-lines-check.

### College football SGP+ ticket, lines only (Sep 26, `cards/fun_ncaaf.py`)

Mike's rule: one college ticket per day; since Oct 10, one per kickoff slice (noon, afternoon, night), locked 15 minutes before the slice's first kickoff (`sgp_plus.keep_tickets`; every sport's tickets lock the same way). New York bans college player props, so the legs
are each game's FanDuel spread, total and moneyline, never a New York school or a game
played in New York (an unconfirmed venue is skipped).

**How college lines move together** (FBS vs FBS, 2014-25, 9,247 games with lines): the
favorite covering and the over are nearly independent for small spreads, but not for big
ones.

| Spread | Games | Both hit vs independent (lift) | 2014-19 / 2020-25 |
|---|---|---|---|
| up to 14.5 | 6,493 | 0.99-1.02 | about 1.0 in both |
| 14.5-21.5 | 1,284 | 1.12 | 1.11 / 1.14 |
| 21.5+ | 1,192 | 1.19 | 1.18 / 1.21 |

- **The model:** each game is drawn from past games with a similar spread (within 4
  points): the favorite's margin and the total relative to the market, the total's
  spread rescaled to this game's total (SD 14.6 at a 45 total, 18.7 at 65+).
- **Held out** (drawn from 2014-21, tested on 3,071 games of 2022-25): against
  independent legs, the four cover/over outcomes' log loss improves by +0.031 per game
  (SE 0.009) at 21.5+, +0.0085 (SE 0.004) at 14.5-21.5, and nothing below (correctly).
  At 21.5+, cover-and-over hit 33.6% against 24.7% independent.
- **The ticket:** each game offers single legs (40-80% likely, no unders) or a side with
  the total when they move together (lift 1.05+); the day's ticket takes the best-value
  pieces from 3-4 games, fair odds +400 to +5000. Legs are priced at the sharp no-vig
  price at FanDuel's number. Sep 26's: Kentucky over, Central Arkansas +47.5, Marshall
  -24.5 with the over (fair +225 together, +292 if independent), Western Kentucky -40.5
  with the over; fair +3490.

### Soccer SGP+ ticket (Sep 28, `cards/fun_soccer.py`)

Mike's rule: one soccer ticket per day, leagues mixed, never with other sports. Since Oct 10, one per kickoff slice, locked 15 minutes before the slice starts like every sport's; since Oct 13, ten slices, one per Eastern kickoff cluster (before 8:45, 9 AM, 10 AM, 11 AM, noon, 12:45, 3 PM, MLS 7:30, 8:30 PM, late), each spanning about 30 minutes so every lineup is in at the lock (docs/DECISIONS.md); FanDuel's goals and btts lines are pulled for the ticket's matches only for the betslip links.
- **No ratings:** ours lost to the market in every league. For each match, the two
  teams' expected goals are fit so a Dixon-Coles score grid (rho −0.05) reproduces
  Pinnacle's no-vig result and its over/under ladder at 1.5, 2.5 and 3.5.
- **Legs:** team to win, over 1.5/2.5/3.5 goals, both teams to score, all read off
  that one grid. That's how they move together within a match.
- **No FanDuel price for goals legs:** FanDuel only sends its 3-way result to the odds
  feed (checked on the Sep 25 EPL pull: no totals from FanDuel or DraftKings). So those
  legs show no FanDuel price, and the verdict comes from the SGP+ quote Mike types.
  Soccer pulls now include totals (+1 credit a league pull) to anchor the goals legs.
- **The ticket:**
  - Minis are a winner with goals first, then correlated goals pairs, then single
    legs, each 45-85% likely.
  - 3-5 matches, fair odds +400 to +3000.
  - A match whose prices don't fit one grid within 3 points is skipped.
- **Checked on 5,279 big-five matches (2023-25, Pinnacle's close):**
  - How often pairs hit together, over independent legs, grid vs real (SE):
    - Favorite wins + over 1.5: 1.045 vs 1.061 (0.016).
    - Favorite wins + over 2.5: 1.183 vs 1.211 (0.023).
    - Both score + over 2.5: 1.474 vs 1.547 (0.026).
    - Favorite wins + both score: 0.865 vs 0.922 (0.022).
    - 55%+ favorites, win + over 2.5: 1.159 vs 1.172.
  - The grid understates how often both teams score (51.9% vs 54.8%), so tickets with
    that leg get slightly long fair odds. That errs toward "not worth it".
- **Grading:** tickets grade from football-data.co.uk's final scores (`fun_ledger`,
  game_ref "league|home|away|kickoff").
- **Shot overs (Oct 10, Mike):** a starter's FanDuel "2+ shots" or "1+ shots on target" rung
  (`shot_rungs`, from the props tracker) can be a match's piece of the ticket, and up to 6 per slice
  show as overs to root for.
  - **Fair chance:** the market's (BetRivers' ladder fit, else FanDuel's own with its margin off).
    The shots model has no weight, so a rung qualifies only when the model's chance is at least the
    fair one: never a fake over.
  - **Bands:** ticket legs 45-85% likely, overs to root for 35-80%. Ranked by how far the model sits
    above the fair chance.
  - **No same-match correlation:** a shot leg is its match's only leg on the ticket (one piece per
    match), so it never sits next to a team leg it moves with.
  - **Timing:** a player is priced once his lineup is out (props pulled 15-55 minutes before
    kickoff), so shot legs come from the slice's earlier matches before the lock.
  - **Grading:** shot legs settle from ESPN's box score (`fun_ledger._espn_shots`), void when the
    player didn't play. As for every soccer leg, a void makes the whole ticket void, where FanDuel
    would drop the leg and keep the rest.

### The parlay backtest (Sep 25, `betlab backtest sgp`)

This checks how legs move together, walk-forward, with inputs from earlier games only.
"Together" is the rank correlation of where each result fell in its own simulated
distribution. "Lift" is how much more often two 70% legs both hit than independent legs
would.

**Pairs, 2023–25 (816 games, simulator v0):**

| Pair | Simulated | Real (SE) | Lift sim / real |
|---|---|---|---|
| QB passing yds + his top target's yds | 0.45 | 0.48 (0.02) | 1.12 / 1.10 |
| QB passing yds + his No. 2 target's yds | 0.36 | 0.38 (0.02) | 1.09 / 1.08 |
| Top two targets' yds, same team | −0.02 | 0.04 (0.03) | 1.00 / 1.00 |
| Both QBs' passing yds (shootout) | 0.04 | 0.05 (0.04) | 1.01 / 1.02 |
| QB passing yds + his RB's rushing yds | 0.03 | **−0.09** (0.02) | 1.01 / 0.98 |
| Both teams' RB rushing yds | −0.05 | −0.11 (0.04) | 0.99 / 0.99 |
| Top target scores + his QB's passing yds | 0.03 | **0.15** (0.02) | 1.00 / 1.02 |

Four-leg slips of 70% legs: shootout (both QBs and both top targets) hit 1.26× as
often as independent legs in the simulator and 1.27× in real games; one team's QB,
top two targets and RB 1.20× vs 1.14×; a spread-out slip 1.00× vs 1.01×.

**Against real 2025 lines** (84,178 pairs of FanDuel main lines, the market's no-vig
chance for each leg), the simulator's joint beats "independent legs" on log loss:
- QB with his own receiver: by 0.024 per pair (SE 0.003). Both went over 28.9% of
  the time; the simulator said 27.4% and independence 22.9%.
- Every other kind of pair is close to independent in both.

This is the part of parlay pricing that matters, and it holds up.

**What was wrong, and v1** (fit on 2021–24 team-games; 2025 was the check):
- **The pass/run trade-off.** Given the pregame line, a team's targets and carries
  correlate −0.36; even after how the score went, −0.32 (2025: −0.32). The simulator
  drew them independently. A team that gets ahead also runs twice as much as it
  assumed: +0.29 carries per point of margin surprise vs +0.15. v1 adds both.
- **Efficiency and scoring.** Yards per target rise 13% per SD of a team's points
  surprise (2025: 14%), yards per carry 5%. v0 used 10% for both.
- **Touchdowns to unlisted players.** v0 gave about 4% of each team's TDs to an
  "other" bucket, but everyone who plays is simulated, so they never scored. Prop-worthy
  players' anytime-TD chances ran 2–5 points low. In v1 the bucket keeps its yards and
  scores no TDs.
- Team scoring surprises are nearly independent (correlation 0.035 over 2,895 games)
  with SD 9.2, so the simulator's independent points (SD 9.5) stay.

**v1 on 2025:**
- The pass/run pairs moved toward reality:
  - QB + his RB: +0.03 → −0.02 (real −0.06)
  - both RBs: −0.05 → −0.10 (real −0.17)
  - RB + the other QB: +0.03 → 0.00 (real −0.02)
  - shootout: 0.04 → 0.06 (real 0.06)
- Slips' lifts stay within noise.
- The joint's gain on real lines went from 0.0011 to 0.0012 per pair.
- Single-player accuracy is unchanged (CRPS within ±0.5% on every stat).
- TD log loss improved: 0.5215 → 0.5203.

**Still open:**
- **A top target's TD with his QB's yards** (fixed Sep 25, night): real 0.15,
  simulated 0.05 in v1. Weighting TDs by yards didn't help.
  - **The cause:** in real games (2021–24) passing-yards surprise correlates 0.42 with
    passing TDs and 0.02 with rushing TDs. The simulator had 0.10 and 0.09, because it
    split TDs by a fixed pass share and ignored how the passing game went.
  - **The fix:** each draw now scales its TD count (0.20 log per SD of passing yards,
    mean kept) and tilts the pass share (0.45 log-odds per SD). That matches both
    numbers (0.42, 0.03).
  - **On 2025:** top target scores + QB yards 0.05 → 0.18 (real 0.15, SE 0.04); RB
    scores + QB yards stays right (0.050 vs 0.051); TD log loss 0.5203 → 0.5201.
- **Top two targets:** simulated slightly too negative (−0.02 vs +0.04).

**Game lines as legs (tested Sep 28, simulator v1, 2023–25, 1,632 team-games per pair).**
The moneyline, spread and total legs added on Sep 26 move with player legs through the
simulated points. The GAME role's "total" is the game's points. Its "margin" is the
team's points minus the opponent's, which is what moneyline and spread legs hit on.
"Tail lift" is how much more often both legs land in their top 25% than independent legs
would, the shape of the long-shot slips. The question: did those slips look generous at
FanDuel (20–46% above our fair odds) because we overstate how totals and big yardage
lines go together?

| Pair | Together sim / real (SE) | Lift sim / real | Tail lift sim / real (SE) |
|---|---|---|---|
| Game total + a QB's passing yds | 0.24 / **0.34** (0.02) | 1.06 / 1.08 | 1.50 / 1.66 (0.08) |
| Game total + a top target's yds | 0.11 / **0.19** (0.03) | 1.02 / 1.04 | 1.25 / 1.42 (0.08) |
| Game total + an RB's rushing yds | 0.06 / 0.07 (0.02) | 1.01 / 1.03 | 1.12 / 1.10 (0.07) |
| Game total + a top target scores | 0.16 / 0.18 (0.02) | 1.03 / 1.03 | 1.41 / 1.35 (0.08) |
| Game total + an RB scores | 0.17 / 0.22 (0.02) | 1.03 / 1.04 | 1.37 / 1.44 (0.07) |
| Team wins big + its QB's passing yds | 0.06 / **0.15** (0.02) | 1.01 / 1.07 | **1.16 / 0.99** (0.08) |
| Team wins big + its top target's yds | 0.02 / 0.11 (0.02) | 1.00 / 1.02 | 1.08 / 1.09 (0.08) |
| Team wins big + its RB's rushing yds | 0.30 / 0.28 (0.02) | 1.08 / 1.06 | 1.59 / 1.49 (0.08) |
| Team wins big + its RB scores | 0.17 / 0.23 (0.02) | 1.03 / 1.03 | 1.36 / 1.62 (0.08) |
| Team wins big + the other QB's passing yds | −0.06 / −0.15 (0.02) | 0.99 / 0.98 | 0.84 / 0.80 (0.07) |

- **Totals with yardage: we understate the link.** For a QB, real games tie his yards to
  the game total more than the simulator does (0.34 vs 0.24, 5 SE), and for a top
  target too (0.19 vs 0.11, 3 SE). The tails are short by about 2 SE. Our fair odds on
  "over + big yards" slips are therefore a bit *too long*, not too short. Those slips
  weren't a simulator artifact: if anything, FanDuel's generosity there is real.
  Where the missing link comes from is unexplained (a candidate: high-scoring games
  have more plays for both offenses, which the simulator doesn't tie to the points).
- **Side legs:** the RB links are right. Winning with QB yards is understated in the
  middle but **overstated in the tail**. When a team wins big, its QB rarely also has a
  top-25% day (real tail lift 0.99; the simulator says 1.16): the offense runs out the
  clock. A moneyline or spread leg plus a big QB yardage rung is priced a little too
  generously by us.
- **The fix, same day (`surprise_total_targets`, `surprise_total_carries`).**
  - In real games, a game that goes over its total gives each offense +0.084 more
    targets per point (2021–24, SE 0.011; 2025 agreed at +0.070). Carries add +0.018.
    It's the passing game, not pace.
  - The simulator now adds both.
  - Held out on 2025:
    - Game total + QB yds: 0.24 → 0.33 (real 0.34).
    - Game total + top target yds: 0.11 → 0.16 (real 0.23).
    - Both QBs: 0.06 → 0.11 (real 0.06, SE 0.06).
    - Average error over every pair: 0.053 → 0.046.
    - Real-line gain unchanged. CRPS within 0.2%.
- **Big win + big QB day, same evening (`margin_bend`).**
  - The cause wasn't starters sitting. In 28+ point wins the starter still throws 94%
    of the passes, and backups mostly hand off.
  - The cause is a bend. Real passing yards follow the straight-line links in the
    middle, but they peak when a team trails by about a touchdown (+6%), drop about 6%
    in wins by 7+ and about 11% in blowout losses.
  - Fit on 2021–24 as what the linear model leaves over; 2025 matched both ends.
  - In the simulator, on 2025: tail lift 1.15 → 1.05 (real 0.93), and passing-yards
    CRPS improved slightly.
  - Left over: moderate wins with good QB days stay too weakly linked (0.05 against
    0.13 real), inside the noise of the pair test.

## Soccer: ratings vs the market (`models/soccer.py`, `betlab backtest soccer`)

Mike, 2026-09-25: soccer should be ML-first, with "so many games" and steadier teams
season to season. The free history made that testable before any pick:
football-data.co.uk has every big-five and MLS match with Pinnacle's odds early in the
week and at the close (through 2024–25), then Betfair Exchange's close.

**Ratings v0** (`models/soccer.py`):
- A time-weighted Poisson model (Dixon–Coles): attack and defense per team, home
  advantage, a 240-day half-life and ridge toward a prior (promoted teams start 0.2
  weaker in attack and defense).
- Optionally half the goals target is shots on target × league conversion (a crude xG).
- It gives 1X2, over/under 2.5 and goal-difference chances.

**Walk-forward test, 2018-19 to 2025-26** (17,600 matches; ratings refit weekly from
earlier matches):

| League | Model minus the close (1X2 log loss) | vs Pinnacle earlier in the week | Walk-forward blend gain |
|---|---|---|---|
| Premier League | +0.015 | +0.012 | ≈ 0 (w → 0) |
| La Liga | +0.020 | +0.018 | ≈ 0 |
| Serie A | +0.023 | +0.021 | ≈ 0 |
| Bundesliga | +0.021 | +0.021 | ≈ 0 |
| Ligue 1 | +0.021 | +0.020 | ≈ 0 |
| MLS | +0.020 | (no early odds) | ≈ 0 |

- The model loses to the market everywhere, even to the early-week line, and the blend
  weight fit on earlier seasons goes to zero. Over/under 2.5 loses too (0.005–0.014).
- Shots on target help a little (Premier League +0.0167 → +0.0154) but nowhere near
  enough.
- **It doesn't predict line moves either.** For 5,884 matches where it disagreed with the
  early line by 5+ points, the line moved its way 48.7% of the time (slope of move on
  disagreement 0.000, SE 0.004). College's early edge doesn't exist here: by early week
  the market has priced team strength.

**So soccer goes market-first, like the NFL:**
- **Picks** from FanDuel prices that lag Pinnacle and Betfair.
- **Props:** shots, shots on target, scorers.
- **Every line logged** from the first pull, with features.
- **The ML layer** looks for information the market prices late (confirmed lineups and
  rotation after midweek European games, fixture congestion) and is tested on the
  history first. Team-strength ratings stay as a feature with no weight.

**The live soccer card** (`cards/soccer.py`, from 2026-09-25; paper):
- **What's priced:** in the odds feed FanDuel posts only the 3-way result for these
  leagues, so that's the market. Pulls ask for `h2h` only, about 1 credit per league
  pull.
- **The fair price:** each outcome (home, draw, away) against the sharp book's no-vig
  3-way chances. That's Pinnacle, else LowVig/BetOnline, else the other books, with
  vig removed by Shin's method.
- **Picks:** the normal game-line rules (EV 3%+, one per match, −250..+250), model
  weight 0.
- **Grading and CLV:** from football-data.co.uk: the score, and the sharp close
  (Pinnacle, else Betfair Exchange, else the books' average). No near-kickoff pulls
  needed.
- **Matching books' names to the files:** each name resolves to its single best club
  in the league's file, then the fixture must be those two clubs within a day.
  "Leeds United" is Leeds, never Man United.
- **Every line is logged** to `data/ledger/soccer_lines.csv` (first and latest FanDuel
  price, the sharp chance, result, sharp close). That answers whether FanDuel lags the
  sharp market in soccer at all.
- **First look** (Premier League, two weeks out): FanDuel's 3-way margin is about 7%
  and its prices sat close to Pinnacle's, with no line at +3% EV. Picks will be rare
  unless FanDuel lags nearer kickoff.

## Soccer props: shots and shots on target (`models/props_soccer.py`, `betlab backtest soccer-props`)

Built 2026-10-10 (Mike: "we can win money on shots / shots on goal"; ML-first, "maybe a separate
model for each league").

**Live, first look (Oct 20, 110 matches):** on the same rungs the model beats FanDuel's margin-free chance (shots log
loss 0.427 vs 0.459, SE 0.006; on target 0.403 vs 0.427) and BetRivers. FanDuel's overs (it offers no unders) run far
above their hit rate (0.5 shots: priced 67.6%, hit 57.9%, model 58.5%), so the model mostly says "don't". Its FanDuel
overs at positive EV: shots -20% ROI (142), on target +41% (119, 36 matches): noise so far. No weight.

- **The feed** (probe, Oct 10, all six leagues): FanDuel posts shots (0.5-5.5) and shots on
  target (0.5-3.5) as over-only ladders, anytime scorer and assists; BetRivers posts shot ladders
  too; Pinnacle a two-way scorer price for some players; DraftKings cards. Pulled once per match
  after lineups (~5 credits).
- **Reading over-only ladders:** each book's ladder is one negative binomial plus a margin
  (`ladder_fit`; residuals under 0.01). FanDuel's margin is ~16%, BetRivers' 6-10%. Both books add
  up to the same 25-30 shots a match but split them differently between players.
- **History:** ESPN's free player boxes (`sources/espn_soccer.py`), 2019-20 to now, six leagues:
  16,400 matches, 675,000 player rows. Minutes come from the substitution minutes; player shots
  add up to the team box.
- **Features:** shots and shots on target per 90 (EWMA, 5 and 20 appearances), minutes per start,
  share of team shots, position; team and opponent shot form; the market's expected goals for
  each team (the close's 1X2 and over/under 2.5 fit to a score grid; MLS from the 1X2 alone);
  home, rest, league.
- **Model:** Poisson-loss trees per target, negative binomial for P(over).
- **Walk-forward test** (starters with 3+ earlier appearances, test seasons 2024-25 and 2025-26;
  log loss at the line, lower is better):

| League | Shots 0.5: per 90 x min | Trees, one per league | **Trees, pooled** | Shots on target 0.5: per 90 x min | **Trees, pooled** |
|---|---|---|---|---|---|
| Premier League | 0.5478 | 0.5324 | **0.5299** | 0.4902 | **0.4669** |
| La Liga | 0.5602 | 0.5426 | **0.5399** | 0.4684 | **0.4392** |
| Serie A | 0.5656 | 0.5458 | **0.5433** | 0.4906 | **0.4571** |
| Bundesliga | 0.5692 | 0.5476 | **0.5452** | 0.5025 | **0.4694** |
| Ligue 1 | 0.5609 | 0.5398 | **0.5354** | 0.5004 | **0.4620** |
| MLS | 0.5399 | 0.5162 | **0.5153** | 0.4839 | **0.4496** |

  - **One pooled model (league as a feature) beats one model per league in every league, every
    line and both targets** (36 of 36 rows): more players beat specialization. Live uses the
    pooled model.
  - The trees beat both baselines everywhere (the recent average by 0.07, per 90 x minutes by
    0.02-0.04).
  - The market's expected goals help a little in the big five (shots 0.5: 0.001-0.0014), nothing
    in MLS, where only the 1X2 is known.
- **Goals, assists, and goal or assist (Oct 10, Mike):** three more targets on the same trees (goals,
  assists, and goal involvements = goals + assists, so "to score or assist" is one count and the
  overlap is exact). Pooled again beats per-league everywhere; log loss at 0.5 (2024-26), best
  baseline vs pooled trees: score or assist 0.41 vs 0.39 (EPL), 0.43 vs 0.39 (Bundesliga); goals
  0.29 vs 0.27; assists 0.27 vs 0.24. FanDuel's "to score or assist" isn't in The Odds API's market
  list, but `player_to_score_or_assist` works (FanDuel and Fanatics, Yes only, with betslip links):
  pulled with the other props, logged and graded with the model's chance, and shown on the game page
  as a tappable FanDuel price next to our fair odds. First look (Palace v Forest): the model sat well
  under FanDuel on every attacker (Strand Larsen +252 fair vs FanDuel +120), like the shots ladders.
- **Anytime-scorer picks (Oct 10, `cards/props_soccer.scorer_offers`):** Pinnacle posts a two-way
  scorer price for a few players a match, the only sharp one in the feed. FanDuel's Yes price
  against Pinnacle's no-vig chance goes through the normal prop rules (5% EV for a pick, model
  weight 0); graded from ESPN's box score (void if he didn't play), CLV against Pinnacle's last
  pre-kickoff price. First look (Oct 10): most FanDuel scorer prices sat 9-20% below Pinnacle's
  fair; Lamine Yamal at -125 was +4.1% (a lean).
- **ESPN's counts vs the books' source:** total shots agree with football-data.co.uk's (Opta-style)
  within 1% (correlation 0.97-0.98, 2024-25, three leagues); shots on target run about 7% low
  (4.58 vs 4.83 a team). The live model scales its shots-on-target means by 1.07, and shots-on-target
  grading from ESPN is approximate (a borderline over may show lost when FanDuel paid it): compare
  with FanDuel's settlement on real bets.
- **First live look (Oct 10, MLS):** the model expects fewer shots from attackers than FanDuel's
  margin-free ladder (Daniel Ríos 1.6 vs 2.3): FanDuel's shot overs look expensive beyond the
  margin. Graded rungs will say who's right.
- **Against the market:** not tested yet (no free prop history). Every FanDuel rung is logged from
  Oct 10 (`tracking_soccer_props.py`) with both books' fair chances and the model's (`p_model`,
  live model `data/models/soccer_props.joblib`, the pooled trees on every season; the daily `refresh`
  adds new matches to the history); weight 0 until it beats them on graded rungs.

## Soccer analysis (game pages, `cards/analysis_soccer.py`)

Built 2026-10-10. Every soccer match in the next 36 hours gets, from the `preview` step
(`exports/soccer_analysis.json`, merged into the app's soccer games by export-page):
- **Goals expected:** the sharp 1X2 and goals line fit to a score grid.
- **Shots and shots on target projected** per team: the shots model's means for the starters,
  divided by the starters' share of a team's shots (history).
- **Shot form:** shots for and allowed over the last 10 league matches, ranked in the league this
  season; rest days.
- **Lineups:** with the lineup out (about an hour before kickoff), changes from the last XI and the
  regulars (4+ starts in the last 5) not starting; before that each team's last XI stands in,
  labeled "expected".
- **Likeliest shooters:** the top 3 starters per team by expected shots, with FanDuel's 2+ shots
  rung, FanDuel's no-margin chance and the model's.
- **Moneyline read** (Oct 15, Mike: "soccer analysis for money lines"; every tracked match in the
  36 hours, cups included): the sharp no-vig 3-way now and at our first look (a 2+ point move gets a
  sentence), the better of FanDuel and DraftKings per side with its EV (a pick needs 3%+), European
  cup matches within 4 days either side (from the line tracker; ESPN's history here has no cup
  matches, so rest days alone miss them), and the lineup's 1X2: the starters' expected goals on the
  Dixon-Coles grid. On the 27 graded goal reads so far that 1X2 is far worse than the market's
  (log loss 1.092 vs 0.898, gap 0.19, SE 0.13), so it has no weight; the page shows its live record.
  Our team ratings are left out: they lost to the market in every league and didn't predict moves.
Reads, not prices: the model has no weight until the graded rungs say so.

## College basketball: efficiency ratings and the opener (`models/ncaab.py`, `betlab backtest ncaab`)

Built 2026-09-25 ahead of the November start, from CollegeBasketballData (same key as
CFBD): 5 seasons (2021-22 to 2025-26), about 6,300 games a season, closing lines on
about 5,600, openers on 7,500 games in 2024-25 (part of the season) and 2025-26 (Bovada,
DraftKings). The first download lost each date window's boundary day (the API reads an
end date as midnight UTC, about 2% of games); fixed and re-downloaded on Sep 26.

**Ratings** (KenPom-style):
- Points per 100 possessions = league + home edge + offense[team] − defense[opponent],
  weighted ridge. Pace is fit the same way.
- Settings were tuned on 2023-24 only: a 180-day half-life, last season at 70% weight,
  a light ridge.
- On Mar 1, 2025 the top six were Duke, Houston, Auburn, Gonzaga, Florida and
  Tennessee.

**Against the close** (2024-25 and 2025-26, held out): the model misses the margin by
9.12 / 9.33 points vs the market's 8.76 / 9.01, and the best blend weight is about 0.
The close is better, as in every other sport.

**Against the opener, it predicts the move.** Where the model disagrees with the
opening spread, the line moves toward the model's side before the close:

| Disagreement | Games (2024-25 + 2025-26) | Move toward the model | SE | Implied CLV | By season |
|---|---|---|---|---|---|
| 2+ pts | 533 + 2,466 | +0.29 pts | 0.03 | +1.1% | +0.28 / +0.29 |
| 3+ pts | 218 + 1,450 | +0.38 pts | 0.05 | +1.4% | +0.37 / +0.38 |
| 5+ pts | 16 + 620 | +0.56 pts | 0.11 | +2.0% | (16 games) / +0.57 |
| 7+ pts | 297 total | +0.89 pts | 0.20 | +3.2% | mostly 2025-26 |

- The move is many SEs from zero and grows with the disagreement. The two seasons agree
  where both have data (2+ and 3+ points).
- The 5+ and 7+ rows rest on 2025-26 alone, because 2024-25 has openers for only part of
  the season. The first write-up claimed both seasons agreed at 5+; that was a
  16-game sample.
- The model's side covered the opener 53.8% at 5+ points (634 games; break-even at −110
  is 52.4%) and 51.9% at 3+.
- Totals move toward the model too, but less (+0.2 to +0.35 pts, about +0.5% to +0.8%
  CLV), probably not enough to beat the vig.
- Slices checked (a small multiple-testing risk):
  - Early season (Nov–Dec, 2025-26 only) was the strongest: 55.5% at 5+ points.
  - Low-major and power-conference games were similar.
- This is the college football early-read finding's shape, at far more volume. It
  makes college basketball the most promising market we have tested for real CLV.

**Roster change** (added Sep 26; `roster_value`, `roster_shift`). In November the
ratings are mostly last season's team, but about half of a team's minutes leave each
year (71% in 2025-26, the portal era). Each team's roster is valued at its players'
previous-season PORPAG (points over a replacement player per game, from CBBD's player
stats; transfers count for their new team), minus what the team had. Since Oct 20 freshmen count too:
each recruit's expected first-season value by 247 rating (`FRESHMAN_BANDS`; Duke's 2026-27 class +6.0); held out,
November error 9.887 -> 9.891 (2024-25) and 9.926 -> 9.889 (2025-26), reads vs the opener +0.48 -> +0.56 pts.

The model's miss tracked that change closely, and the market's didn't:

| Phase | Games | Model's miss per point of roster change | Market's miss |
|---|---|---|---|
| November | 4,660 | +0.47 (SE 0.03) | +0.03 |
| December | 3,898 | +0.34 | +0.07 |
| Jan–Feb | 10,738 | +0.15 | +0.01 |
| Mar–Apr | 2,715 | +0.07 | −0.01 |

- The four seasons agree in Nov–Dec: +0.42, +0.48, +0.38, +0.41. Value lost and value
  gained count about equally (−0.43 and +0.39).
- The market already prices rosters; our ratings didn't. In November, 513 of 626 reads
  at 3+ points pointed against the team's roster change, and those lines barely moved
  toward us (+0.10 pts). The 113 that agreed with it moved +1.0.
- **The fix:** home margin + 0.65 × e^(−days since Nov 1 / 60) × (home change − away
  change). Fit on 2022-23 and 2023-24 margin error (each season alone: 0.6–0.7, 60 days).
- **Held out (2024-25 / 2025-26):** November margin error 10.15 / 10.32 → 9.90 / 9.94
  (the close: 9.39 / 9.75). The whole-season blend weight vs the close stays about 0.1:
  still no edge against the close.
- **Against the opener, the reads get much better** (the table above was without it):

| Disagreement | Games | Move toward the model | SE | By season (2024-25 / 2025-26) | Covered the opener |
|---|---|---|---|---|---|
| 3+ pts | 1,419 | +0.53 pts (was +0.38) | 0.06 | +0.47 / +0.54 | 53.8% (was 51.9%) |
| 5+ pts | 424 | +0.96 pts (was +0.56) | 0.15 | (12 games) / +0.99 | 58.0% (was 53.8%), SE 2.4% |
| 7+ pts | 167 | +1.86 pts (was +0.89) | 0.34 | 2025-26 only | |

- In the first 60 days (2025-26): 3+ reads moved +0.51 (was +0.30), 5+ moved +0.93
  (was +0.48). After day 60 the shift is small and the numbers barely change.
- **Caveats:** the backtest used CBBD's end-of-season rosters. Live uses ESPN's
  preseason rosters, which include players who won't play and miss mid-year arrivals,
  so expect a smaller effect; live CLV decides. Freshmen count 0, so teams built on top
  recruits (Duke, Kentucky) are under-credited in November. ESPN's preseason pages lag:
  on Sep 26, 72% of the 239 teams listed still showed last season's players. A roster
  returning more than 85% of its minutes counts as not updated, and that team gets no
  shift (real rosters top 85% about 2% of the time).

**Plan for November** (to-do c-ncaab):
- Pull college basketball odds early, when openers post.
- Log a "read" for every game where the model (with the roster shift) disagrees with
  FanDuel's line by 3+ points (the gap and the shift are kept), plus paper picks under
  the normal rules. About 1,250 reads a season at 3+ (60 a week).
- Measure CLV against the close. The go-live checklist decides the rest.
- New York rules apply: no games with New York colleges, no college games in New York
  (Madison Square Garden and Barclays events included), and no college props.

## NHL: shots, goalies and the line (`models/nhl.py`, `betlab backtest nhl`)

Built 2026-09-30 on free data only (Mike: NHL now, without spending odds credits):
the NHL's stats API for every team-game and goalie-game since 2018-19, and ESPN for
DraftKings' lines (`docs/DATA_SOURCES.md`).

- **Model:** ridge ratings for shots on goal and non-empty-net goals (recency half-life
  150 days), each team's finishing, and each goalie's save % shrunk toward the league by
  800 shots. Expected goals blend the goals view and the shots view 50/50, against the
  goalies who start. A score grid adds 60-minute ties (weight 1.40), overtime and
  empty-net goals (0.54 per game when the lead is one, 0.66 when it's two; measured on
  2022-24). Books count the shootout winner as a goal, and so does the grid.
- **Tuning:** 2022-24 moneyline log loss, 42 settings. The winner (0.6567) beat the
  worst (0.6624). Short memories (45 days) were worst; 150-250 days were best.
- **Held out, 2024-26 (2,624 games):** log loss 0.6744 against 0.6896 for the home
  team's base rate. Tie rate 22.2% vs 22.8% real. Goals 6.04 vs 6.09 real.
- **Against DraftKings, 2025-26 (936 games with ESPN's open and close; 2024-25 has
  none, and ESPN's 2022-24 numbers aren't real two-way prices):**

| Moneyline log loss | |
|---|---|
| Our model | 0.6819 |
| DraftKings' open | 0.6822 |
| DraftKings' close | 0.6812 |

  - The model is as good as the opener and slightly worse than the close. A blend
    helped the close by 0.0011 on the season's second half (weight picked on the first
    half: 0.15), SE 0.0008: not significant. **Model weight: 0.**
  - **The line moves toward the model:** correlation 0.24 between the model's gap to
    the open and the open-to-close move (0.37 and 0.12 by half season); the close
    moved 17% of the gap. At 5+ points of gap the line moved our way 62% of the time.
  - **But the move is smaller than DraftKings' vig:** taking the model's side at the
    open lost to the close by 2.0% at 5+ points (1.6% at 7+), and beat it only 36%
    (41%) of the time. The results were +3.8% (+8.2%) on 295 (143) bets, which is
    noise at this size. 84% of big-gap reads are underdogs: the ratings are less
    extreme than the market, as in every other sport.
  - **Totals:** the model loses to DraftKings' close (0.6929 vs 0.6889) and leaned under
    (average over chance 46% vs 49% real and 50% market). Not used for reads.
  - **Totals fix, same night (Mike: "go do all 3"):** the guess was that the grid's scores
    are too tightly spread. A shared scoring factor per game (both teams' rates times a
    Gamma draw, `disp`) made 2022-24 totals *worse* at every size tried (log likelihood of
    the final total 2.2509 at 0 vs 2.2598 at 0.03 and 2.3088 at 0.12), so NHL scoring isn't
    more spread out than Poisson plus ties, overtime and empty nets. It's off (`disp: 0`).
    What helped a little: every rate times 1.015 (`goal_scale`, fit on 2022-24; 6.25 goals
    vs 6.22 real). On 2025-26: totals 0.6918 (from 0.6929) vs DraftKings 0.6889; average
    over chance 47.7% vs 49.1% real (n 932, SE about 1.6, so the lean is now within
    noise). Totals still get no weight.
- **The card (market-only, `cards/nhl.py`, from Oct 1):** FanDuel's moneyline, puck line and
  total against the sharp book's no-vig price at the same number (Odds API
  `icehockey_nhl`, about 3 credits a pull; daily plus the two midday re-prices). Picks
  follow the normal game-line rules. Graded by `grading.grade_nhl`: NHL final scores, and
  CLV against our last pull before the start (the 4:17 PM ET re-price on most nights, so
  it's an early "close"). The first live pull (Sep 30, 11 games with FanDuel prices)
  had no pick or lean.
- **Fun (`cards/fun_nhl.py`; the Fun tab is split by market, each window collapsible):** one SGP+ ticket per night (a team to win, favorite -1.5,
  underdog +1.5, over 5.5 / 6.5; no unders) from our grid fit to the sharp moneyline and
  total, weighted toward winners and goals, band +300 to +1500; plus shots-on-goal overs
  to root for (FanDuel vs the other books' no-vig at the same number; `pull-props
  --league nhl`, about 1 credit a game, once a day). Legs settle from NHL scores and
  skater shots (`fun_ledger._grade_nhl`; a player who doesn't play voids the leg).
- **Use:** the Games tab's NHL view (`cards/preview_nhl.py`) shows the model next to
  FanDuel's prices and Pinnacle's no-vig chance (from Oct 1; DraftKings via ESPN only when
  the day's FanDuel pull isn't in), with tonight's goalies. Reads compare the model with
  Pinnacle; the tracker's `book` column says which line each game's first look used. Reads at 5+ points are tracked in
  `data/ledger/nhl_lines.csv` with the close's CLV, never priced or picked.
  What would change that: 2026-27's reads beating the close live.
- **Open:** whether live goalie confirmations add anything (the backtest used the actual
  starters), and a later pull near puck drop for a truer close.

## NHL game analysis and props ML (`cards/analysis_nhl.py`, `models/props_nhl.py`)

Built 2026-09-30 night (Mike: "NHL analysis like NFL style, then NHL props and relate our
analysis"; "the season just started, it's the perfect time to start an ML model").

**Live, first look (Oct 20, 3,017 graded FanDuel lines):** on the 1,717 lines with a two-sided market price, the ML
model is worse than the market (log loss 0.649 vs 0.640; shots 0.700 vs 0.685). The read's tagged lines are mixed
against the market's chance on the same lines (1-1.5 SE each way). No market layer yet; month-one review Nov 1.

- **Game analysis** (Games tab, NHL view): a short game script; "where it's decided" (each
  team's shot volume vs the other's suppression, each power play vs the other's kill with
  expected chances and goals, the goalie gap), all in standard deviations; special-teams
  ranks (`models/nhl.special_ratings`: power play, kill, penalties drawn and taken, shrunk
  by 80 chances / 20 games, half-life 150 days); ESPN's injury list with each player's ice
  time and shot share. These are reads, not prices.
- **Props model (ML from day one):** gradient-boosted trees with a Poisson loss, one per
  stat (shots, points, goals, assists), on every skater-game 2020-26 (about 300,000):
  ice time by situation, shot and scoring rates, shot share, who's in tonight's lineup
  (`share_present`), and the game analysis (team and opponent projected shots, team
  goals, the opposing goalie, back-to-backs). A negative binomial around the mean gives
  P(over) (shots size 21; points, goals, assists Poisson). Saves: the opponent's projected
  shots times the goalie's save %, times 0.955 (that product ran 4.5% high on 2025-26),
  size 29.
- **Walk-forward test** (`betlab backtest nhl-props`, skaters with 5+ games and 10+ minutes;
  log loss at the line, lower is better):

| Shots over 2.5 | 2024-25 | 2025-26 |
|---|---|---|
| Recent average | 0.4766 | 0.4701 |
| Hand-built (recent x team shots) | 0.4783 | 0.4729 |
| Trees, player features only | 0.4752 | 0.4676 |
| **Trees with the game analysis** | **0.4733** | **0.4652** |

  - The trees beat the recent average on every stat and both seasons (points over 0.5:
    0.5996 vs 0.6151 in 2025-26).
  - **The game analysis helps shots** (both seasons, every line: 1.5 / 2.5 / 3.5) and
    goals and assists a little; points not at all.
  - A hand-built team-shots scaling made things *worse*: the trees learn the effect the
    right size.
- **Not yet tested against the market:** there are no free historical prop lines. Every
  FanDuel line is logged from Oct 1 (`data/ledger/nhl_prop_lines.csv`, with every feature),
  priced against the other books' no-vig chance at FanDuel's number (a book at another
  number is moved along the stat's negative binomial). Model weight 0; picks only from
  FanDuel vs that consensus. Lines that fit the game read (team projected 1+ SD above or
  below the league in shots or goals) are tagged, to measure whether the read helps against
  the market. The market layer (what the market misses) trains on these rows once there are
  enough, as in the NFL props ML plan.
- **The joint model** (`models/joint_nhl.py`, 2026-09-30: Mike, "let's make the joint NHL
  model"): one simulated game draws the final score from the market-fit grid, then each team's
  shots given the score (+2.3% per goal scored above expectation, -4.8% for the winner: score
  effects; noise SD 0.21, the two teams' noise correlated -0.14; fit 2022-24), each player's shots
  as a beta-binomial share of his team's (intra-class correlation 0.0032), and each goalie's
  saves as shots faced minus goals allowed. On 2025-26 (`backtest_joint_nhl.py`, lift = joint
  over independent):

| Pair | Observed | Joint model |
|---|---|---|
| Goalie over saves + his team wins | 1.11 (SE 0.04) | 1.15 |
| Goalie over saves + over 6.5 | 0.93 | 0.95 |
| Shooter 3+ + over 6.5 | 1.05 | 1.04 |
| Shooter 3+ + his team wins | 0.99 | 1.00 |
| Two teammates 3+ | 1.02 | 1.06 |

  The first fit (without the winner's -4.8%) had shooter + win at 1.01 against 0.93-0.99
  observed. The builder's NHL legs (game lines, shots, saves) all come from this simulation;
  fair chances stay the market's (the simulation only says how legs move together).
- **Anytime goal scorer (Oct 10, Mike):** FanDuel posts it (Yes only; no assists, points or blocked
  shots in the feed); Pinnacle posts a two-way Yes / No for most skaters (21 of 34 in the probe).
  Pulled with the other props (+1 credit a game); priced against Pinnacle's no-vig chance (normal
  prop rules, model weight 0), the model's goals chance tracked next to each line; picks graded from
  the box score with CLV against Pinnacle's last pre-game price.
- **Feed:** FanDuel sends shots on goal and saves for NHL props, not points. FanDuel offers no
  alternate NHL totals at all (Mike checked the app, Sep 30), so NHL tickets and the builder use
  only its one total. It also sends no NHL alternate lines (alternate puck lines and totals: DraftKings and Pinnacle do, Sep 30), so
  those legs show our fair price. Other books
  (DraftKings, BetOnline, Bovada, Pinnacle) post fewer lines and often only on game day.

## UFC (`cards/ufc.py`, `cards/fun_ufc.py`, `sources/espn_ufc.py`): market-only

No fight model (docs/DECISIONS.md, 2026-10-23): moneyline and total rounds at each of Mike's books against the sharp
no-vig price, model weight 0. A draw or no contest voids the moneyline; total rounds settle on the seconds fought
(Over 2.5 needs more than 12:30). The fun ticket is a plain cross-fight parlay of fighters' FanDuel moneylines (fights
are independent, so the fair chance is the product). Props: none in the feed; on the 63 fights with ESPN prices the
method market's margin is ~20% and the market looked calibrated. **The fight model** (`models/ufc.py`, Oct 23; `betlab backtest ufc`): each fighter's
state before a fight from their earlier UFC fights since 2021 only: Elo (K=32, a finish 1.25x), experience, significant
strikes landed and absorbed per minute, accuracy, takedowns for and against, knockdowns, control share, submission
attempts, win, finish and stopped rates, layoff; rates shrunk toward the average fighter by 15 minutes of average output,
so a debut is an average fighter. Who wins: logistic regression on the differences, fit on both orders of every fight.
Distance: logistic regression on the pair's combined finishing, the gap between them, five rounds and the class's rate.

| Walk-forward, 2023-26 | Log loss |
|---|---|
| Who wins (2,179 fights): model / Elo / coin | 0.663 / 0.676 / 0.693 |
| Goes the distance (2,173): model / base rate | 0.666 / 0.692 |
| Who wins, the 63 fights with DraftKings' prices: market / model / half and half | 0.642 / 0.721 / 0.666 |
| Distance, the 62 with prices: market / model | 0.633 / 0.671 |

No weight: the market beats it clearly, debuts most of all (no UFC history since 2021). The data starts in 2021, so
veterans' earlier fights are missing too. Next: the per-card tracker of its reads against DraftKings' prices, and an
Odds API backfill of moneylines and totals (November) to test it on hundreds of priced fights.

## Planned models
- **NBA and college basketball:** opponent-adjusted efficiency and pace, player
  availability, rest and travel. Props from minutes × per-minute rates.
