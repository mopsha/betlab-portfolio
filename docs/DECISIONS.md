# Decisions

Settled questions and why. Before re-opening one, read its reason. If you change a
decision, add a new dated entry rather than editing an old one.

## 2026-11-09: a real slip with a leg off and no leg price waits for what the book paid

A slip read from a screenshot has no fair chance per leg (`leg_p`). When one of its legs came off (a player sat, a whole
number pushed) and the rest won, the fun ledger voided the whole slip at 0 profit, while FanDuel and DraftKings pay the
shorter parlay. We can't know that price without the leg's, and guessing one would put a made-up number in the record. So
a marked slip in that spot stays open and prints "not graded" (the grade step's warning and the owner's daily alert)
until what the book paid is entered as its cash-out, which then settles it (won, profit from the cash-out, `profit_1u`
left empty). An unmarked slip (learning only) still voids, a lost leg still loses it, and Bet Protect+ is unchanged
(`fun_ledger._finish`). Synced Novig cash bets (`novig-...`) take Novig's own settlement and are never graded here.

## 2026-11-08: the promo finder keeps its list varied (Mike: "use a promo shouldn't give all unders")

On Nov 8's NBA games, Balanced gave 9 all-under bets of 10 at both FanDuel and DraftKings, and Keyonte George under 5.5
assists sat in 5 of them. Nothing was mispriced: against the sharp line, FanDuel's unders paid 0.949 of fair on average and
its overs 0.937 (books shade overs), so every near-tie went to an under and the best one or two legs filled every slip. Now
a leg shows in at most two results and all-under bets fill at most half the list (`promo-finder.MAX_LEG_USES`,
`allUnder`; iPhone `PromoFinder.maxLegUses`), and when too few other bets qualify, the best of the rest still fill it.
The cost is small: the tenth Balanced bonus-bet pick that night went from about $7.60 to $5.70 per $10, the first was
unchanged. A display rule, not a pricing one: no threshold or price moved (fixture `promo_finder.json`, `variety`).

## 2026-11-07: a game's own slips lock by their game, never their slice (Mike: "locks on a sgp shouldn't depend on slices at all")

- **Change:** each game's own slips (a slate's `sgps`, the ones Today shows for watched games) follow the rebuilds until
  25 minutes before that game's start, and the first build from then is final (`sgp_plus.lock_slips`, each slip stamped
  `locked_at`). Only the cross-game SGP+ and TD tickets lock by slice.
- **Alerts:** a watched game's lock alert is its own ("Locked: Knicks @ Cavaliers slips", key `slips:<event id>`,
  `alerts.slip_locks`); a slice's alert names its tickets only.
- **Apps:** Today shows a watched game's slips from its own lock time to its start, and Home lists each watched game's
  lock (web `watch.ts`, iPhone `Watch.swift`, fixture `watch.json`).
- **Pulls:** an NBA game is still pulled with its slice's first tip, so a late game's slips can use that pull unless news
  re-pulls it.

## 2026-11-07: NBA and NHL starts from 5 to 6:30 PM are a slice of their own, "dusk" (Mike: "why would the 8:10 knicks game lock now?")

- **What happened:** the NBA's early slice ran from 5 PM to 8:59 PM. Tonight a 5:10 Pacers tip led it, so the slice was
  pulled at about 4:30 and locked at 4:45 with the 8:10 Knicks game in it, priced three and a half hours early.
- **Change:** a "dusk" slice for 5:00-6:30 PM starts in the NBA and the NHL (`sgp_plus.SLICES`, web `slices.ts`, iPhone
  `Slices.table`, fixture `slices.json`); its title says its first start ("NBA 5:10 PM game"). Moving the 5 PM line instead
  would only have put a 5 PM game on the matinee slice. College basketball keeps its 5 PM line: 6 PM tips are common there.
- **Today's slice:** a slice locked under the old hours whose first start is now in dusk rebuilds and locks again at its
  own lock time, with one more lock alert (`_resliced`, key `lock:<slate>:r`). The Knicks game keeps its 4:30 pull unless
  news re-pulls it.

## 2026-11-07: a two-game NHL slice gets a +200 ticket floor (Mike: "Yes, +200 floor")

The afternoon slice locked empty when FanDuel moved its only total and two games' best pieces reached +265 against the
+300 floor. Like soccer's two-match floor (Oct 14), two games get their own. Mike picked +200 over leaving it.


## 2026-11-07: single-game parlays follow the games you watch, not fixed rules (Mike)

Mike: "instead of forcing multiple parlays for a single game ... you should be able to signify games you are going to
watch and then it gives you parlays for that game, so we don't need a strict knicks rule anymore or a strict prime time
nfl rule". So the builders keep making every game's own slips, every slice carries them, and each account picks the
games: Watch on a game page. A watched game's slips join Today's Parlays when its slice locks, with the lock alert.

What follows from it, on purpose: a game nobody watches shows no single-game parlay on Today, Sunday and Monday night
included (a one-game slice has no SGP+, so it shows nothing unless watched); its slips stay on its game page. Sam and
Mike each watch their own games. Not changed: the soccer prime-time list (El Clásico's own slice and parlay), slices,
locks, prices. Soccer slips' goals legs get FanDuel links only when the match is on a ticket (the goals ladder is pulled
for ticket matches, 2 credits each).


## 2026-11-07: FanDuel's College Football Pick'em is picked by expected correct picks at the frozen lines (Mike: "help me pick")

FanDuel's free pick'em (Rewards Hub): 10 spread picks a week, lines frozen Wednesday morning, locked Saturday noon,
settled on the frozen numbers; the top score shares $500K in bonus bets, beating the partners' score pays a 25% boost.
By Saturday the sharp market has moved off those numbers, so the side of each stale line the market now favors is the
pick: each frozen line is priced like the card's spreads (Pinnacle through the college margin model). Nov 7's first
read: Iowa +2.5 at 61% (the market had Iowa -3), three more flips at 51-53%, expected score 4.9 -> 5.3.

Why expected correct and not a contrarian card: the jackpot needs 10 of 10 among every entrant, and a card built to
differ from the crowd gives up expected picks for a tiny chance at a share; the boost only needs more right than the
partners, which the same picks do. Games with a New York college get no pick from BetLab (the hard rule, though a
free pick isn't a bet). Not built: reading the partners' sheet (the sheet on Nov 7 was a different slate than the
questions), and any model weight (the market alone). `pickem.py`, migration 0044, Me › Extras › CFB Pick'em.


## 2026-11-06: Conch-style scheme angles don't beat the prop market (Mike: "test it and find all that data")

Mike wants the analysis to work like @conchpicks' TikTok notebooks (nine transcripts read, Sep 28-Nov 5): one game's
story, what an injury changes for which player, the opponent's recent pattern in counts, scheme tendencies (blitz,
coverage shells, personnel), then one or two props. Our analysis had pressure rate only. Tested on FanDuel's saved 2024
and 2025 main lines (`scripts/scheme_angles.py`), beyond the market's no-vig chance, walk-forward team rates shrunk to last
season, five hypotheses fixed before looking; the bar was the expected sign and |t| >= 2 in both seasons. None passed:
fewer blitzes -> RB catches t -0.3 / -0.7; two-high -> RB catches +1.8 / 0.0; two-high -> fewer WR receiving yards -1.1 /
-2.5; bigger box -> fewer RB rushing yards -1.8 / -1.0; 2+ TE sets -> TE catches +1.5 / -2.5 (flips). Ten tests, so one
|t| of 2.5 is within chance. Two-high vs WR yards and the box vs rushing yards had the right sign twice and are the ones
to rerun with 2026's participation file (about Feb 2027). No weight, no pick rule. The September man/zone, target-funnel
and pressure tests found nothing either (MODELS.md, "Matchup research").

Data, in season: blitzers and box count are free (FTN charting on nflverse, weekly); coverage and personnel per play are
free only after the season (nflverse participation). In season they cost money (Fantasy Points Data about $200 a year,
PFF Pro $200 a year, FTN's feed far more) or come from free season-to-date tables (Sharp Football's man/zone and shell
rates; SumerSports' personnel pages, whose terms forbid scraping). Buying any of it waits for an angle that passes.

## 2026-11-06: the promo finder's Balanced and Safe follow what the token can reach (Mike)

Mike: profit boosts "never have safe or balanced options or very rarely". The cause was the rule, not a bug. A boost's
expected value per dollar is about (1+boost)(1-vig) - 1 - p·boost, so it falls as the chance rises; half the boost tokens
in the wallet need 3+ legs at +100 or longer, where a 25% bet barely exists; and Safe kept only bets worth 60% of
Balanced's best, which no 45% bet reaches under a 30% boost. Now, of a token's bets worth something, Balanced takes those
at least as likely as the median one and Safe those in the likeliest quarter, never asking more than the old 25% and 45%;
Safe's 60% is of the best in its own band. When a token has plenty of likely bets (most bonus bets) nothing changes: the
five old fixture cases keep their order. A 30% boost on four 3-leg parlays (10-22%) now offers Balanced the 22% and 18%
ones and Safe the 22% one, where both were empty. Still judgment calls, not backtested; no pick threshold, model weight or
guardrail is involved (the finder only ranks how to use a token). Web `promo-finder.ts floorFor`, iPhone
`PromoFinder.floorFor`, `tests/fixtures/promo_finder.json`.

## 2026-11-05: a soccer ticket uses legs the books list

Mike's 12:45 cup parlay opened in FanDuel as one pick: 7 of its 8 legs were Conference League goals legs, which neither FanDuel's nor DraftKings' feed carries (0 of 18 matches that day, with Pinnacle and BetMGM posting them), so they had no link. Conference League matches now join a ticket on their winner only, and their shot legs are out too (`fun_soccer.NO_GOALS_FEED`). No threshold, weight or guardrail moved: this narrows the legs a ticket can use, and tickets stay at fair prices. A slice whose matches can't reach the ticket's band now has no ticket but keeps its Build packs. In both apps a parlay with one linked leg gets no FanDuel link, because it would open as a single bet; the card says to build it by hand.

Mike, the same day: stop combining the Europa League and Conference League on one slip. A slice with both now has two tickets, its usual one and a Conference League one, in the slate's second ticket slot (`plus_short`, the NBA's likelier ticket), so they lock, link, publish and alert together with no new slate id. The title and the lock alert name it.

## 2026-11-05: The DFS optimizer is built on the market, and it isn't a pick (idea #38, Mike)

| Decision | Why |
|---|---|
| Projections are the market's expected stats, not our props models | `scripts/dfs_projection_study.py`, 1,032 NBA player-games over 10 days: typical miss 7.84 points against 8.52 for a player's own average, RMSE 9.95 against 10.83, correlation 0.70 against 0.64, and ahead in both halves of the days. Our models stay at no weight (rule 3) |
| DraftKings classic, NBA and NFL only | DraftKings' salary export is a plain public link. Its JSON API answers 403 Access Denied, and we don't work around a refusal. FanDuel's needs a sign-in. A failing export stops only that league, and the log says so |
| Novig's free catalog prices the NBA | Its props sit there all day for every game on today's slate, so the lineups don't wait for each game's paid pull. No credits spent. Its NFL games list no props yet (Nov 5): NFL lineups read our pulled props, so the first Sunday is the real test |
| Labeled a suggestion, with no record claimed | Past salaries aren't free, so the lineups have no backtest; only the projections do. Contests take about 15% and we don't know ownership, so most points isn't most money. `data/ledger/dfs_*.csv` logs each lock and `betlab dfs --grade` fills in NBA results. NFL grading isn't built |
| Off for now: DraftKings answers 403 to Railway (Nov 5, 9:15 and 9:30 runs) | The same link answers from the Mac, so the block is on the server's address. We don't get around a refusal with proxies or a faked browser, and a server that refused shouldn't be asked every 15 minutes. Mike chose to leave it off (Nov 5) over a CSV he exports himself, a run from his Mac, or a paid salary feed |
| A player with no main line stays on his DraftKings average, marked * | Half a stat line would understate him. Only 27 of 62 active players on the first slate had lines: bench players are the weak part |

## 2026-11-04: Batch 6 studies, what they found (Mike picked them from the ideas list; no model, weight or threshold changed)

| Idea | Result | Decision |
|---|---|---|
| **#13 NFL referees** | `scripts/nfl_wind_refs_study.py`, 1999-2025 vs closing totals: 8% of 38 refs beyond 2 SE (5% by luck); even-season vs odd-season miss correlates -0.14; betting any ref 2+ SE off in the seasons before: 416 bets, 50.0% (SE 2.5%), break-even 52.4% | Nothing there. Closed. NBA refs not tested: no free history |
| **#12 NFL wind** | Same script. Game-day wind 15+ mph: under 57.0% on 674 games, season-block 95% interval 52.3-61.8%, both halves of the years alike, against 48.8% under 10 mph. Forecast at kickoff, 2021-25: under 50.5% (<8 mph, 568), 55.4% (8-12, 240), 57.1% (12-15, 77), 59.6% (15+, 47, +/- 14). Nov-Jan looks stronger, Sep-Oct none: spotted after looking, so not trusted. 2024 went against it (36% of 11) | A lead, not proof, so **no pick or lean**. Tracked forward by `wind_watch.py` (`data/ledger/wind_watch.csv`). The archive's forecasts are the models' near-term runs, not days-ahead ones. Judge at ~50 graded 15+ mph games |
| **#16 Which lines move toward us** | 1,928 graded leans and picks with real closes. Inside 3 hours, props by EV: 0-2% 0.0% CLV, 2-3% +0.4%, 3-5% +1.1%, 5-10% +1.9%. A regression on EV, hours, market, book and price: out-of-sample correlation 0.11 | **Not built:** EV already is the move signal. Worth knowing: EV 10%+ runs the other way (16 props at -1.7%; 3 game lines at -56%): stale prices, small sample, for a Tuesday review. Game lines logged 3h+ out run about -1.3% vs +0.1% inside 3h. The prop rows at -5% logged 12-36h out are nearly all NFL in September, before the news-timed pulls; none in November |
| **#14 UFC history before 2021** | Fights from 2015 on, same 2,204 test fights: 0.6628 -> 0.6605; against DraftKings (89) 0.7068 -> 0.6963, market 0.6267, half and half 0.6456 | Not adopted: more download time for almost nothing |
| **#15 UFC odds backfill (~1,100 credits)** | The free DraftKings lines from ESPN already answer it: model 0.7068 vs market 0.6267 on 89 fights, 0.6766 vs 0.5985 on the tracker's 25; blending is worse than the market alone | **Credits not spent.** The fight model stays at no weight |
| **#9 Novig's catalog instead of paid pulls** | The API charges per 10 named books: we name 10, so dropping Novig (9) costs the same one region | Saves nothing. Not built |
| **#17 Correlation library** | Every sport already prices same-game legs from its own joint simulation (`leg_packs` bits) | Not built |
| **#34 First-half lines** | Probed one game each: FanDuel, DraftKings, Pinnacle and BetOnline post `spreads_h1`, `totals_h1` and (not college) `h2h_h1`; Novig only `h2h_h1`. One college spread was a point off the sharp books | Needs a forward lag study: NBA and NFL for two weeks, about 1,000 credits. Mike skipped it for now (Nov 4); not built |
| **#78 Backtests in CI** | Soccer and NFL run in about a minute, and closed seasons shouldn't move. `backtest nhl` takes 20 minutes and rewrites `data/models/nhl.json` as it goes, which a timing run did on the Mac tonight (restored, never committed) | Weekly job on a throwaway copy; a move emails Mike. Don't run `backtest nhl` on working files unless you mean to refit |
| **#11 NBA injury re-pricing** | Not started: it needs the four weeks of graded props due mid-November | With `c-nba` (Nov 17) |

## 2026-11-04: A 4.5 goals line anchors a soccer game when nothing nearer does
The games the old rule dropped were the marquee ones, because a big total is what pushes the sharp line to 4.5: they had no Build pack, no ticket legs and no live CLV. The fallback only applies when the game would otherwise be dropped, so no other price moves. Quarter lines stay out: only 3 of 350 games, and they need their own half-push math. Numbers in `MODEL_CHANGELOG.md`.

## 2026-11-03: Leans stop at +250 on moneylines, on the long side only (Mike)
Long dogs lost to the close (-3.67% on 58, 38% beat), and they are the prices that look like an edge but aren't: the reason picks stop at +250. The +96u
above +1000 is one East Texas A&M win, which says nothing about the bet. Big favorites beat the close (+0.15% on 61, +1.23% on 16), so the same limit
on that side would have cut leans with no case against them; they made about 3.3u on 77, so keep watching them in the Tuesday reviews. Numbers in `MODEL_CHANGELOG.md`.

## 2026-11-03: A promo can be used for less than its max (Mike)
The finder takes a wager up to the token's max and reprices at it, so a capped boost's value and a lock's hedge are right for that stake. The rest of a
bonus bet stays in the wallet: the token shrinks to the wager and a new open one holds the rest on the same terms, with no link between them, so undoing the
bet gives back every dollar. A boost is used once, so the rest of its max wager is gone. FanDuel lets you use as much of a bonus bet as you want at a time (Mike, Nov 3); DraftKings and Novig aren't confirmed, so check the slip there.

## 2026-11-02: Soccer props at DraftKings and Novig: nothing to add yet (Mike's #18)
Checked the last 12 soccer props pulls and Novig's catalog, no credits spent. DraftKings' feed posts anytime scorer, which the card
already prices, and player cards, with no sharp price to judge them against. It posts no shots, shots on target, assists or score-or-assist.
Novig lists no soccer player props at all (its markets are 3-way, totals, spreads, team totals, BTTS and first-half totals). A prop with no
sharp reference would be a made-up edge, so nothing was added. Recheck if either feed adds them.

## 2026-11-02: Alert settings are per account; quiet hours hold alerts but drop leg alerts (Mike's #47)
Defaults keep what everyone got before. An alert found in quiet hours arrives when they end, unless its game has started: a pick is still
useful at 8 AM. A leg alert isn't, since the bet has moved on, so it's recorded unsent. Leans are off by default and aren't marked sent
until an account asks for them, so `alerts_sent` doesn't grow by 70 rows a day for nobody. Not a pick threshold: `min_ev` only quiets alerts,
and the card, ledger and picks don't change. Ladder, challenge and problem alerts don't read these settings.

## 2026-11-02: Sign-in email goes through Resend, from mopsha.dev (Mike)
Supabase's built-in sender allows 2 emails an hour and its template couldn't carry the 6-digit code the iPhone app needs. Mike
may rename the app, so the sender is `login@example.com`, a subdomain of a domain he already owns: a rename only changes the
sender name and the template text. The API key lives in Supabase's SMTP settings, entered by Mike.

## 2026-11-02: College basketball slices lock early; the NBA's don't (Mike)
A college slice locks at its first tip's pull, the first tick within 45 minutes of the tip, instead of 10-25 minutes before.
Mike: no player props to wait for (New York bans them), and nothing else in the slice is news-driven. Its later games keep their
own pre-game pulls for the card; the ticket has their morning lines, as it did at the usual lock. The NBA keeps its usual
lock: lineups come out too close to tip for an early lock to be worth it. Not a pick threshold or a model change.

## 2026-11-01: A bet reset counts as a real loss, and its bonus bet counts when used (Mike's token)
FanDuel's Bet Reset Token gives a lost wager back as bonus bets. `bets.reset` marks the bet. Profit doesn't change: a loss
costs the stake, as the book's cash balance does, and the worker (`issue_resets()`, every pregame tick) puts the stake in
the wallet as a bonus bet, which adds profit only if it's used and wins, the rule every bonus bet already follows. A grade
that changes takes back a token not yet used. The token has no expiry until Mike types the book's. Bet resets aren't wallet
tokens or in the finder yet.

## 2026-11-01: NHL game tracker's first look is the first price

`tracking_nhl.record` kept the first row it saw for a game even when that row had no line, so `first_ml_home` and
`first_p_mkt` stayed empty and `grade` could set no read: 13 reads through Oct 11, then none in 145 games. The first look now
fills when the first price arrives (`first_seen` is that time). Nothing about a pick or a weight changes: reads are tracked,
never picks, at the same `nhl.read_min`. Graded rows stay as they are, so the read count restarts from today's open games.

## 2026-10-30 (evening): promos reworked: a wallet, a finder with three modes, stakes in dollars (Mike)

Mike: the boosts and bonus bets "need a total rework" (how it picks the best bet, no way to aim a token at a slice or
at games he picks, logging, counting, no record of the tokens he holds). Now:
- **A wallet** (`promos`, migration 0029): each token with its book, terms and expiry, typed or read from a screenshot.
  A bet placed with one marks it used (a trigger); deleting that bet gives it back. Expired is worked out when read.
- **One number for every result:** the token's expected dollars, with its chance to hit: a bonus bet S·p·(d−1), a
  boost's whole cash bet S·(p·(d−1+extra) − (1−p)) with the extra capped, a lock's sure S·locked. The old "keeps N%"
  and "EV N%" labels are gone.
- **Three modes** (Mike: "let me switch"): Max value (expected dollars, hit chance 8%+), Balanced (25%+, the default),
  Safe (the likeliest from 45%+ among bets worth at least 60% of Balanced's best; locks first; same-game slips one more
  quote-model miss down). **These floors are judgment calls, not backtested.** Revisit them once the finder's placed
  bets (`promo_ev` against their results, My bets › Promos) have a few dozen settled.
- **Scope:** a kickoff slice (the fun tickets' slices, `lib/slices.ts`), games he picks, one game, or today across
  sports (the next 30 games).
- **Stakes in dollars:** a promo bet is saved at the token's dollars over the account's unit (`user_settings.unit_dollars`,
  was each device's own), not 1u; a boost's cap is stored (`bets.boost_cap`, units) and applied in all three ports (a
  capped boost had counted uncapped); a boosted bonus bet counts once, as a bonus. Bonus bets still count in units as
  before (Mike's choice): a win adds its profit, a loss costs nothing.
- **Locks are placed as a pair** (`bets.lock_id`), and undo removes both.

## 2026-10-28 (late afternoon): Novig challenge bets are day-of only (Mike)

"From now on novig bets are only for day of events." The first CFB pick was Tulane -10.5 on Thursday, ripe at 2 PM
because a later day's game needed no news; once placed it sat in My bets without its game-day card until Thursday.
Challenges now use only games played that day, so every pick waits for its own news and tracks the same day.

## 2026-10-28 (afternoon): Novig challenges, alerted when ripe (Mike)

Novig's Points program sets three challenges a day (50 points each, 100 more for all three), like "a straight trade on
CFB" or "an NBA parlay, 3+ legs at 4.00x". They aren't in Novig's API: its app reads them with your signed-in session,
and BetLab never handles login tokens. So Mike adds a screenshot each morning ("i can submit it in the morning and it
alerts me when a pick is ripe"), Claude only copies the words, and the worker parses and solves them on every tick. The
bar for "ripe" moves through the day (before 5 PM a clearly good price, until 10 PM a fair one, then the best there is)
so a weak early price waits for news and better games without risking the deadline. Straights count the worse of the
pulled and live Novig price: on the first afternoon a live +122 against the morning's Pinnacle line looked like +15%.
Points aren't units: these are small $5 bets placed for the points, outside the picks, priced to lose as little as
possible.

## 2026-10-28 (afternoon): Novig is a parlay book too (Mike)

Mike asked for same-game parlays and SGP+ at Novig. Unlike FanDuel and DraftKings, Novig publishes a free parlay
pricer, so its side of a slip is its real price, not a likely quote from our model: every slip and SGP+ ticket gets
it at publish (`novig_parlays.py`), the Build tab asks it live, and one link opens the whole slip in Novig's app.
"I placed this" now goes to the best known price of the three (a typed FanDuel or DraftKings quote, or Novig's exact
one when its market maker takes at least $5), ties to FanDuel, then DraftKings. Picks don't change: parlays stay fun
bets. Grading follows Novig's rule: a void leg counts at its fair value instead of coming off, so a slip can pay back
less than its stake. On the first run (Oct 28 afternoon) Novig priced 5 of 7 SGP+ tickets with every leg listed; the
two refused were 6- and 8-leg soccer tickets. Legs Novig can't take (a double chance is the NO side of a win market,
and Novig takes no NO side) leave a slip off Novig with a note.

## 2026-10-28: the script read leaves the Games tab (Mike)

The Oct 19 decision kept the Games tab's "lines that fit the script" on and set a Nov 2 check against 2026's lines:
remove if still below the market. Run early on Oct 28 (weeks through Oct 26 all graded): below the market on log
loss and on hit rate (MODEL_CHANGELOG). With 2024 also against it, only 2025 ever said yes, so Mike chose to remove
it now rather than wait a week. Tracking goes on at no cost (the columns are filled anyway), so if 2026's later weeks
turned it around the evidence would show.

## 2026-10-27 (afternoon): NFL spreads logged early: no rule change

The Oct 27 scorecard's weakest spot was NFL spreads, -2.00% CLV on 31 real closes, all of it from the 17 logged 36+
hours out (-4.02%). Those are leans from the week-ahead lines, logged the Sunday before (95-178 hours out); none is
a pick (the pick window is 36 hours) and early leans already stay off Home. One lean carries most of it: BAL -5.5 at
ATL, logged 176 hours out, closed at BAL +3.5 (a nine-point swing on Baltimore's quarterback news), -47.9% CLV, and
won. Without it the other 16 are -1.3% (median -1.9%), under one standard error at this size; inside 36 hours NFL
spreads are +0.45% on 14. Underdogs did worse than favorites early (9 dogs -3.8%, 7 favorites +1.9% without Baltimore)
but that split is after the fact and tiny. So nothing changes: logging them is the only way to keep measuring the
week-ahead lines, and the Tuesday review keeps watching the 36h+ bucket.

## 2026-10-27 (afternoon): college basketball gets a morning slice

The Nov 1 opener (Villanova and Notre Dame in Rome, 9:30 AM ET) would have opened college basketball's "afternoon"
slice, which locks 15 minutes before its first tip. On Nov 1 the only other game is at night, but 24 days of 2025-26
had an 11 AM tournament tip with noon-4:30 games after it: those games would have gone on a ticket locked before
their own pre-game pulls (15-45 minutes before tip), at their 9:55 AM prices. Tips before noon are now their own
"morning" slice, like the NFL's 9:30 AM London games (`sgp_plus.SLICES`). The 9:30 tip itself is pulled at the 8:45,
9:00 or 9:15 tick (the worker runs from 6:30 AM) and was already covered.

## 2026-10-27: NFL bets grade from ESPN's box score when nflverse hasn't posted (Mike)

Monday night's six bets were still open at 9 AM: the 3 AM grade ran before nflverse posted the game's player stats,
and the 9:55 daily would have been the first to see them. Mike asked for an ESPN fallback so Monday and Thursday
night games grade at 3 AM. `fun_ledger.with_espn` adds a finished game's ESPN box score (`espn_nfl_box`, by
nflverse's `espn` id, only once ESPN calls it final) shaped like nflverse's stats, with the final score. Checked on
Monday's game: all 24 legs on six slips graded the same from ESPN as from nflverse. ESPN has no snap counts, so a
player missing from its box stays open for nflverse rather than void (a void would win a Bet Protect+ parlay), and a
first-TD leg still waits for nflverse's play-by-play. The picks ledger's NFL props (`grading.py`) still grade from
nflverse only.

## 2026-10-26 (night): Bet Protect+ is tracked; the record counts a push as a loss (Mike)

Reconciling BetLab with Mike's FanDuel balance  from a screen recording of his settled
bets found a $96 gap: Oct 19's +911 bonus parlay was "INJURY COVERED, WON ON FANDUEL" ($91.15) while BetLab had voided
it (a leg on a player who sat, with no fair chance saved to reprice), plus some FanDuel Faceoff winnings
(not bets) and about $12 of Bet Protect+ fees. Mike asked for Bet Protect+ to be tracked: `bets.protect` (migration
0023, Edit and the slip reader set it); the fee (3% of the stake, in cash even on a bonus bet) comes off P/L on every
settled bet but a void (FanDuel refunds it); a protected slip's did-not-play leg counts as won in the graders. The
Oct 19 row was corrected in data/ledger/fun.csv to FanDuel's result (result columns only). The same evening he set the
record rules: a push counts as a loss, a cash-out counts as its bet settles (P/L stays what was paid back), and the
record's third number is voids only. A ladder also keeps one book the whole way (migration 0022).

## 2026-10-26 (afternoon): a ladder's step is locked by the worker once its game's news is in (Mike)

Mike, after the on-demand version: "If I start a ladder at the beginning of the day I can signify a game or not but
it gives me best pick from that day and waits until it has the info it needs, like I don't need a pick on demand."
He chose: with no game chosen, BetLab holds the day's best step from the morning and locks it once that game's news is
in if it is still +EV, else moves to the next best and waits again; with a game chosen and no +EV step there after its
news, it tells him and waits for him to decide (no automatic fall-back). The worker's `ladders` step
(src/betlab/ladders.py) runs on every pre-game tick, free: "news is in" is the game's post-news pull in the day's
pregame state, the same signal fun slices lock on. A lock alerts the owner's devices; he places the step himself and
taps I placed it. Turned-down offers and the chosen game move onto the ladder (migration 0021), so the web, the iPhone
and the worker see the same ones (they were per device that morning). A locked step that starts unplaced is cleared
with a notice and the next one can lock.

## 2026-10-26: ladder challenges, outside the 5u-a-day rule (Mike)

Mike asked for a "ladder" and chose the ladder challenge: start with some units and roll the whole stack into one
bet at a time until a target (his first: 1u -> 100u, about seven even-money wins in a row, roughly 1 in 128 at a coin
flip). He chose real money with the 5u-a-day cap waived for ladder steps (the late steps of 1u -> 100u stake 30-60u),
BetLab suggesting each step and him confirming it, and the start and target set per ladder. The suggestion is the
card's strongest +EV pick, then lean, priced -250 to +150, at least 15 minutes out, off the ban list: a step should be
likelier won than not and still move the stack, and a +EV bet is the only kind that makes a long ladder less unlikely.
Claude never places a step (CLAUDE.md rule 5): the app records what Mike placed. A step is one of his bets carrying the
ladder's id (migration 0020), so it settles however that bet settles (web/lib/ladder.ts, ios/BetLab/Me/Ladder.swift,
tests/fixtures/ladder.json). The 5u-a-day rule stays for every other bet.

## 2026-10-25: El Clásico is a prime-time match (Mike)

Mike: "El Classico is later today treat it as a primetime game". Like the NFL's night games, a listed match
(`fun.soccer.primetime`, matched either way round, so every Clásico) is a slice of its own: built and locked just
before its own kickoff with its own lineups in, named in the app ("El Clásico · 4 PM"), never on another slice's
ticket. A one-match slice had no ticket (an SGP+ needs 2 matches), so it gets its own parlay: 2-3 of its legs (a
winner, both teams to score, a goals line) priced together on its score grid, fair +150 to +1500
(`fun_soccer.prime_minis`). No shot legs: shots move with goals in a way the grid doesn't price. The cost: a match
left alone in its usual slice (Oct 25: Udinese-Milan at 3:45) gets no ticket that day, only its shot overs.

## 2026-10-25: TD tickets take the likeliest scorers; our TD read carries no weight (Mike)

On Oct 20 Mike asked to switch the TD tickets to the likeliest scorers if our anytime TD read still didn't beat
Pinnacle after Sunday Oct 25. On Oct 25 it hadn't (581 graded reads: log loss 0.5540 vs Pinnacle's 0.5534, the model
alone 0.5616), and Mike said "let's do it at least locally right now". The read was the reason the ticket chose
red-zone role players at long odds; without an edge that only made the tickets longer (+197,970 vs about +6,052 on
the Oct 25 early slate). Lowering a model's weight needs no backtest under hard rule 3; raising it back would: the
tracker keeps scoring the half-weight read against Pinnacle, and it returns only if it beats the market by 2+ SE.

## 2026-10-23: UFC is a market, market-only, from UFC 333 (Mike)

Mike asked for UFC "fully fleshed out" for UFC 333 (Sat Oct 24) and for any ML or analysis that finds an edge on its
props. There is no fight model and nothing to test one against: ESPN's fight center keeps the sportsbook's prices
(DraftKings: moneyline, method of victory, total rounds, goes the distance) only for the last ~5 events (63 fights);
the 3,276 fights since 2021 before them have results but no prices. So UFC is market-only (hard rule 3), like the
NHL: moneyline and total rounds at FanDuel, DraftKings and Novig against the sharp no-vig price.

The props question, on those 63 fights (Oct 23): the method market carries a ~20% margin across its six outcomes
(moneyline 4.3%, total rounds 6.2%, distance 6.7%), so a method model would need to beat the market by about 3 points
of chance on every outcome. Favorites won 67% against the market's 68%. Only 27% went the distance against the
market's 42%, but 47% of all 3,339 fights since 2021 went to a decision, so that is a run of finishes, not a mispricing.
No edge, and too little to look for one. Props aren't in the Odds API at any book (and FanDuel shows only moneylines),
so the card has none. To test later: save ESPN's DraftKings prices for every card from UFC 333 on (free), and
backfill the Odds API's historical moneylines and totals in November (~1,100 credits a year of cards at 10x).

Two feed facts shaped the build: the Odds API's MMA feed mixes promotions, and it gives most fights the card's first
start (all of UFC 333 at 10 AM, though the main card starts at 2 PM). So only fights matched to ESPN's UFC card are
pulled and priced, at their segment's start, and each segment is pulled about 45 minutes before it. A whole segment
shares one pull, so a bet logged from it would be closed against its own prices: open UFC bets get one closing look
at moneyline and totals in the last tick before their segment.

## 2026-10-23: UFC fight pages, model, same-fight parlays, tracker and card changes (Mike)

Mike asked for all five follow-ups in order. Choices made: fight pages build from the free event list, so a card shows
before its paid pulls; the fight model is tracked with no weight (DraftKings beat it on every priced fight we have,
MODEL_CHANGELOG); same-fight parlays are priced on the pages, not ticketed, because FanDuel's same-game price isn't in
any feed (Mike types the quote, as for the NFL); their fair chance uses the sharp moneyline, DraftKings' method split
with its margin removed, and finish timing set to agree with the sharp total. The history backfill for the model
waits for November's credits: October had 5,326 left for 8 days at ~450 a day (Oct 23). A first `betlab ufc` run
downloads every UFC result since 2021 (~2 minutes), so the pregame tick runs it after its locks and alerts.

## 2026-10-22: Mike's Novig bets sync from his account

Mike asked for his Novig bets to be entered and settled automatically. Novig's API reads an account's fills and
positions with a signed key; Mike creates the key and puts it in Railway himself (hard rule 1), and a
`management::read` key is preferred (it can't trade or move money). `novig_sync.py` turns fills into bets and settles
them from Novig's own results, so any Novig market settles, not just the ones our graders read. Novig's documented
parlay endpoint is the market maker's side, so whether app parlays show up is checked against his account first.

## 2026-10-22: Novig's soccer comes from its free public catalog

The Odds API sends no Novig soccer, and Mike's first Novig bets (Oct 22, 3 PM Europa League) were priced by hand from
its website. Novig's public catalog has every league we price, free and unsigned, with each side's best bid and size.
Soccer pulls add its 3-way result and totals (`sources/novig.py`), matched to the pulled matches by both team names and
the start. Read-only: BetLab never places orders. The rest of the card's rules apply unchanged ($50 bet-limit rule,
same thresholds). Mike asked to "automate it": the worker already pulls, prices and alerts on picks; placing the bet
stays his (hard rule 5).

## 2026-10-22: Novig is a third book for game lines

Mike asked to use BetLab on Novig, the CFTC-regulated sports exchange (nationwide from Aug 4, 2026; New York is in,
though the state is fighting prediction markets in court). The Odds API carries it (`us_ex`, key `novig`) with a link
and a bet limit per price. Novig replaced Bovada in the pulls rather than becoming an 11th book (which doubles every
pull's cost): Bovada was only one of the soft books in props consensus prices. Novig is priced like FanDuel and
DraftKings against the same sharp market, for game lines only (`odds_api.prop_books`: props and parlays stay at the
sportsbooks until its props are checked), and the card picks the best book per bet. No threshold changed: an offer
still needs the same EV, and the same New York rules apply. A Novig price with under $50 behind it (or no limit
found) never wins the best-book choice. On Oct 22's NHL slate Novig had the best price on 61 of 76 sides (no vig),
so most offers will show at Novig; its CLV is graded like any book's and shows apart on the scorecard.

## 2026-10-21: NBA fun slices are early and late, with a likelier ticket and Knicks slips

Mike didn't like Oct 21's NBA structure: 30-minute tip windows made six slices, the 7 PM one grew from one game to
three in its last half hour (its game's slips appeared, then vanished), and its only ticket was 7 legs at +2155. He
chose early and late slices (afternoon for matinees) over keeping the windows with each game's slips, and over per-game
slips only, knowing the later games of a slice are priced before their lineups. Knicks games keep their own slips. On
odds he wanted a mix, not everything shorter: the regular ticket stays (+500 to +4000) and a likelier one (+150 to
+500) joins it. Details and the trade-offs: MODEL_CHANGELOG (Oct 21).

## 2026-10-21: grading runs at 3 AM

Mike asked to move grading overnight: the worker doesn't need his PC, so last night's games can be graded while he
sleeps instead of waiting for the 9:55 daily. A new worker job, `overnight` at 3:00 AM ET, runs sync-personal,
refresh, `grade --no-alert`, export-page and publish (free: box scores, our own closes). 3 AM rather than 2: West
Coast NBA and NHL games finish around 1 AM ET, and the 2 AM hour is skipped or repeated when the clocks change. The
9:55 daily still grades first thing, as a catch-up (football-data's soccer files and late box scores often land after
3 AM) and as the one that sends a problem alert, so the phone stays quiet at night; the 3 AM run still records a
warning in `runs` (exit 3).

## 2026-10-20: freshmen join the college basketball roster shift

The roster shift counted freshmen as 0, so in November teams built on top recruits (Duke, Kentucky) read weaker than
they were. CBBD has free recruiting ratings. Test: bands fit on 2022-23/2023-24, then held out on 2024-25 and 2025-26
(MODEL_CHANGELOG). One season is flat and one improves by about 2 SE; against the opener the reads move further our way
and cover more. The weight wasn't re-tuned (0.65, the fit said 0.73), so the change adds no free parameter besides
the band values. It's in because it fixes a known bias at no cost in either test season. The card stays market-only
(weight 0), so picks don't change.

## 2026-10-20: the cups' 3-way bets get a closing look

The cups close from our own lines pulls (`close_3way`), and since Oct 15 only a pull after the bet counts. Two of the
five cup 3-way bets so far were logged in their game's last lines pull (Viking-Bayern draw Oct 13, Nijmegen lean
Oct 15, both 45 minutes before kickoff), so they had no close. The Oct 15 note said to add a closing look if it
recurred, and it did. `pregame._closing` now covers an open cup h2h bet logged after its game's last lines pull: one
`event_odds` call for h2h only (about 1 credit) in the last tick before kickoff, merged into the game-line snapshot
that `close_3way` reads. Domestic leagues don't need it: their close comes from football-data.co.uk. The cups' first
real closes: Copenhagen-Braga draw +2.6% CLV (lost); Lugano +24.5% (won; Pinnacle moved from +162 to +118).

## 2026-10-19 (night): 2024 lines don't confirm the over lean, the script lean or the receiver matchups

The 2024 backfill (Mike, Oct 19: October's leftover credits; 240 games, 9,594 credits) and `scripts/props_2024_checks.py`
ran each 2025 finding on both seasons the same way (2025 reproduced its documented numbers):

| finding | 2025 | 2024 |
|---|---|---|
| over lean, receptions (overs hit minus plain market) | -4.5 pts (SE 1.0) | -1.4 (SE 1.1) |
| over lean, receiving yards | -4.1 (SE 1.0) | -0.4 (SE 1.0) |
| over lean, all four stats | -3.4 (SE 0.6) | -1.1 (SE 0.6) |
| script lean, pass-game matchup (log-odds per unit) | +0.068 (SE 0.024) | -0.007 (SE 0.025) |
| script lean, strong side vs market | 54.6% vs 50.2% (2,581) | 49.9% vs 49.9% (2,615) |
| yards per target allowed (per SD) | +0.040 (SE 0.045) | +0.025 (SE 0.050) |
| deep-ball fit (per SD) | +0.064 (SE 0.046) | -0.027 (SE 0.043) |
| combined matchup read, strong side vs market | 56.0% vs 50.4% (659) | 49.0% vs 50.1% (578) |

Decision: none reaches picks (none ever did). The over-lean correction stays off in picks; the about 4-point shift it
applies to receptions and receiving yards is not supported by 2024 (or by 2026's first 325 lines: overs 45.8% vs
the plain market's 45.3%). The script lean and the two matchups were 2025 noise. No settings changed tonight: where
they still act (the over-lean shift in the parlays' anchoring, the script read in fun slips, the Games tab's matchup
notes) was Mike's call: the same night he chose to remove all three (MODEL_CHANGELOG, three entries).
This replaces "Confirm the matchups by tracking 2026, not by spending credits on 2024" (Sep 25): the credits would
have expired unused.

## 2026-10-19 (night): only a sharp close counts for props; NHL props' edge is smaller than it looked

Mike asked for prop CLV to be graded only against a sharp book at the bet's line. Done (MODEL_CHANGELOG). It removes
a flaw in both directions: NFL props' late "weak spot" was soft-book closes (-110/-110 coin flips), and NHL props'
"strength" (+1.7%, 88% beat) leaned on a consensus close drawn from the same books the bets were priced from.
Against a sharp book at the bet's line, NHL props logged under 3 hours out are +0.4% (53 closes, 70% beat): still
positive, no longer a clear edge. Nothing about the bets changes; the scorecard is now stricter and fewer bets have a
close (sharp books don't hang every rung). Revisit NHL props' standing after ~100 sharp closes.

## 2026-10-19: soccer has no FanDuel lag to bet; the 3-way card stays market-only

The lag study (scripts/soccer_lag_study.py, free) on 250 matches, Sep 25 - Oct 19 (big five, MLS, the three cups):
- Early FanDuel-Pinnacle gaps close from both sides: FanDuel closed 51% of each gap, Pinnacle 46%. A lagging FanDuel
  would close nearly all of it while Pinnacle held.
- The direct test: 31 early FanDuel prices (3h+ before kickoff) at +EV against Pinnacle averaged -3.7% CLV against
  Pinnacle's own close (beat 29%, SE 2.5%); at +2% EV, 17 prices at -2.0%; at +4%, 9 at +0.4% (SE 7.4%).
- Clean tracker lines (390, Oct 12-13 bug window and goals/BTTS rows removed): FanDuel's first prices at +EV (7)
  got about 0 CLV against the Betfair close.
- FanDuel's 3-way hold is 6.9% (median) against Pinnacle's 3.8%.
Decision: no lag-based soccer picks; the 3-way card keeps its existing rules (no change to any threshold). Unlike the
NFL props lag (CLAUDE.md "Core finding"), soccer's early FanDuel prices are just the more expensive market. Revisit
only if a later run shows early +EV prices beating the close on 50+ prices.

## 2026-10-19: fewer fun slips beat near-copies (Mike)

Mike saw MNF's slips as "the same 4 props repeated": the picker treated Purdy 225+ and Purdy 200+ as different legs.
Options: keep 5 slips per game by letting near-copies through, or show fewer, genuinely different slips. Chosen: fewer.
Slips are for fun and for learning how FanDuel prices correlation; a near-copy teaches nothing new and invites
stacking the same outcome. See MODEL_CHANGELOG (2026-10-19).

## 2026-10-14: 2-match soccer slices get a ticket, with a +300 floor (Mike)

The Oct 14 split of cup days into 12:45 and 3 PM slices left the Champions League's early slot with 2 matches, and soccer
tickets needed 3 (`min_games`) and +400 fair: the slice got nothing, so nothing to lock or alert. Mike: minimum 2. Two
matches' best legs reach about +340, so 2-match slices use their own floor (`band_two_games: [300, 3000]`); 3+ match
slices keep +400 and their tickets didn't change. Fun tickets only: no pick rule or model weight moved.

## 2026-10-14: early game-line leans are hidden from Home by default (Mike; replaces "label, don't hide" of Oct 13)

The weak-spot review on real closes (Oct 14, More > Reviews): bets logged 36+ hours before the start closed at
-1.8% CLV with 48% beating the close (61 real closes), against +1.6% and 87% under 3 hours (55). Game-line leans
make up that early bucket (college moneyline, NFL spreads and totals). Mike chose to hide them from Home by default:
`homeData` drops a game-line lean whose start is 36+ hours away (`isEarlyLean`, the same rule as the label), Home
says how many are hidden, and `?early=1` shows them (tagged "Early"). Nothing else changes: they're still logged
and graded on paper, every game page still lists them with "Early · unproven", and no pick rule moved. Revisit if
early leans start beating the close.

## 2026-10-13: soccer gets one slice per kickoff cluster, each short enough for every lineup (Mike)

Mike: split European cup days into 12:45 and 3 PM; "make more slices, since there's so many games"; "maximize having
max info available per slice on the weekends while also having enough games per slice". The three soccer slices
(morning, midday to 5 PM, evening) put the 12:45 and 3 PM cup matches on one ticket, which locked at 12:30 before the
3 PM lineups. A slice locks at the worker tick 10-25 minutes before its first kickoff, and a match's lineups-in pull
is the first tick within 55 minutes of it, so every lineup is in at the lock only when a slice's kickoffs span about
30 minutes. Soccer kicks off in clusters (ET): before 8:45, 9-9:30, 10-10:15, 11:15-11:30, 12-12:30, 12:45, 2:30-3,
MLS 7-7:30, 8:30, 9:30 PM on. Weekend matches a day (Oct 10-18): ~2, ~6, 1-5, 1-5, 2-4, cups, 3-7, 1-7, ~3, 2-4. Each
cluster is its own slice (`sgp_plus.SLICES["soccer"]`, ends on the quarter hour): merging any two neighbors stretches
the span past an hour and costs the later matches' lineups, so information wins over size; a one-match slice gets
single-game slips. Slices are fixed by clock time, not built from each day's kickoffs: a grouping from the day's
games would shift as matches start and leave the feed, possibly after a slice locked.

## 2026-10-13: every open prop bet gets one closing look; a close must come after the bet was logged

A prop's CLV close is the last props pull before the start. Under the new schedule each game is pulled once, after
its news, and the card logs bets from that pull, so nothing later existed. NFL and NBA closes already required a
pull after the bet (`prop_close`), so those bets had no CLV (7 of Monday night's 11 prop leans). NHL props, soccer
props and soccer goals used the last pull even when it was the one the bet came from, so their "CLV" was just the
bet's own EV: 32 of the 52 graded NHL prop leans (+2.2%, 94% "beat"). On the 20 with a real later close, NHL props
were +0.8%, 75% beat: positive, but not the best market that reviews #1-#3 called it.

Now (`pregame._closing`, Mike asked for it before real money): in the last tick before a start (1-15 minutes out;
first built at 30, moved the same day after the NBA dry run closed games only 15 minutes after their pull), a game with
an open prop pick or lean (soccer goals and BTTS included) that no props pull has followed since it was logged gets
one look at just those markets, about 1 credit a market. Its other markets stay in the snapshot. The NHL and soccer
closes now need a pull after the bet was logged, like NFL and NBA. Already graded rows are unchanged (the ledger is
history). The scorecard and the record use only real closes (Mike, same day): `golive.real_closes` blanks
the CLV of NHL and soccer prop and goals rows with no props pull of their market after `created_at`; the rows
still count as logged and keep their results (32 NHL prop leans and 1 pick on Oct 13).

## 2026-10-13: early game-line leans are labeled "Early · unproven", not hidden (Mike chose)

Weekly review #3 split the week's graded leans by when they were logged: under 3 hours before the start, 40 leans
closed +2.3% (90% beat the close); 36+ hours out, 29 closed -4.2% (median -0.5%, 45%), with big news risk (two
Ravens leans logged a week out closed ~47% against us when Baltimore flipped to an underdog). Picks already need to
be inside 36 hours; leans didn't. Options: hide them or label them. Mike: label, don't hide. A game-line lean shown
more than 36 hours before its start (`web/lib/early.ts`, the pick window `picks.horizon_hours`) carries an "Early ·
unproven" tag and a line under Why. Props aren't labeled: they held up early. Nothing changes in pricing, the
ledger or grading; this is display only. Revisit if early leans start beating the close.

## 2026-10-12: a parlay leg DraftKings doesn't hang moves to its nearest rung (Mike, evening)

Plan rule 11 left it open: a leg one book lacks gets that book's next-best rung, or the slip isn't offered there.
Mike: "DK would have either 220 or 230" (FanDuel's 225+). DraftKings' ladders step at different numbers (x9.5 for
passing yards), so without moving, most of its slips would drop. The rung chosen is the one closest in chance to our
fair chance for the original leg, within 20% of the number and 10 points of chance, so a substitute is never a very
different bet; the slip says which legs moved, and its fair odds stay the original's (approximate for DraftKings).
The Build tab doesn't move legs: its simulated chances belong to the exact leg, so a leg DraftKings lacks is
unavailable there.

## 2026-10-12: the European cups go on the card (Mike, for Oct 13)

Replaces "Champions League: not on the card yet" (Sep 25, grading had no source). Mike wants the Champions League,
Europa League and Conference League bet from Oct 13, player props included. Clubs outside the big five don't
matter to the card: it's market-only, and Pinnacle posts every cup match (all 18 per cup this week; one Conference
League match missing), as do FanDuel and DraftKings. Grading uses ESPN's score (free; all three cups) and our own
last pull before kickoff as the close. Player props cost the most: ~30-36 credits a match in the pre-game pull,
roughly 1,600-2,000 in a full cup week (Mike chose props anyway); goals and BTTS alone would be ~6. Watch: the
Conference League's sharp price is thinner (smaller clubs, Pinnacle's lower limits), so its CLV needs checking
before trusting its picks; knockout ties from February can go to extra time, which ESPN's score includes and the
books' 90-minute markets don't.

## 2026-10-12: a prop at a moved number is a lean at either book (Mike chose, evening)

DraftKings hangs a different prop number from Pinnacle's on 41% of NFL lines (FanDuel 11%), so plan rule 1 ("a moved
number is a lean, never a pick, until moved-number CLV says otherwise") decides most of DraftKings' prop offers. Asked
whether it covers FanDuel too, Mike chose both books: one rule for both, and moving a sharp price to another number
was never tested on its own. It costs FanDuel about 11% of its prop lines' chance to become picks. Reopen with the
CLV of moved-number prop leans (logged in leans.csv like any lean).

## 2026-10-12: DraftKings is the second book, at parity by Oct 18 (Mike chose)

Mike chose DraftKings and wants it as developed as FanDuel by go-live. The plan is docs/DRAFTKINGS_PLAN.md
(16 edge cases where the books differ, each with a rule; build Oct 13-17). His answers: ties at the same EV go to
FanDuel; DraftKings picks start on paper Oct 13; fun tickets show both books side by side; alerts carry both
books' prices. Evidence it's worth it: on the same 44 NFL games, DraftKings' morning prop prices lagged the sharp
close at least as much as FanDuel's (2%+ morning EV: 20 sides, +3.1% CLV vs FanDuel's 19 at +2.3%).

## 2026-10-12: college basketball's lines-only ticket (to-do c-sgp-ncaab; Mike asked)

One lines-only SGP+ ticket per tip slice (afternoon, evening, late), the college football rules: moneylines,
spreads and totals only (New York bans college props), never a New York school (Army counts: West Point) or
a game in New York, nor a game whose venue we can't confirm. Unlike football, the favorite covering and the
over are about independent under a 15-point spread (lift 0.92-0.99 in both halves of 2022-26, 27,364 games)
and move together only for 20+ point favorites (1.08, 1.10), so side + total pairs appear only there; the
draws from similar past games reproduce it (0.98 at -3.5, 1.14 at -22.5). Until Mar 1 the legs are
DraftKings' prices from ESPN's free feed and their fair chance is DraftKings' own no-vig (no sharp book
there), so the ticket says to type FanDuel's quote. Graded from CBBD's final scores.

## 2026-10-12: soccer goals and both teams to score, market-only (Mike chose, ~700 credits a month)

Soccer had no picks on game lines because the bulk feed lacks FanDuel's goals and BTTS. Each match's pre-game
pull after lineups now also takes the event endpoint's goals ladder and BTTS (2 more credits a match), and
`cards/soccer_goals.py` prices FanDuel's over/under at 1.5, 2.5 and 3.5 goals and BTTS Yes/No against
Pinnacle's no-vig at the same number (Pinnacle quoted both on all 19 matches checked). Model weight 0; the
normal game-line rules (3% EV for a pick), plus the -250..+250 price range, one goals pick per match. Graded
from the final score (football-data, else ESPN), CLV against the last props pull before kickoff. On Oct 10-11's
pulls FanDuel sat 1-3% under Pinnacle on every side, so expect few leans; the record will say whether FanDuel
ever lags here. Card links now match only the pick's own market (links.CARD_MARKETS).

## 2026-10-12: a slice locks early once its news is in (Mike asked)

Mike: "if all games within a slice have injury reports/starting 11's/etc out then you can lock the slice so I
can get picks earlier". A fun slice (NFL, college, soccer, NHL) now locks at the first pre-game tick where every
game in it not yet started has had its pre-game pull, which `schedule.pregame` already times after each sport's
news (NFL inactives 85 minutes out, soccer lineups 55); NHL slices also need both starting goalies confirmed on
ESPN's scoreboard (`pregame.settled_slates`). Otherwise the usual lock (10-25 minutes before the first kickoff)
applies. NBA tip-time slates are unchanged: lineups land only 15-45 minutes before tip, so there is little to
gain. Mike rejected a frozen early lock: if a game's news changes after the slice locked early (a news.py
re-pull), the slice rebuilds on the new news and locks again, with an "Updated on new news" alert, until its
usual lock time; from then the lock is final (`pregame.reopened_slates`, `keep_tickets(reopen=)`). Typical gain:
NFL 1 PM slices lock about 11:45 instead of 12:45, the 4 PM slice about 3:00 instead of 3:45. Home says "Next
lock ... by" the usual time, and a lone game's slips show from its lock.

## 2026-10-12: the app counts units only, no bankroll (Mike chose)

Mike: "to make the app simpler forget about tracking a person's total bankroll just worry about units, no
need to care how big they are". Settings drops the bankroll and unit size; a real bet's `bets.stake` is
units (1u by default, editable), the daily cap is 5u and the parlay budget is units a month
(`user_settings.fun_bucket_monthly`, 10). The database's `bankroll` and `unit_pct` columns stay with their
defaults but nothing reads them. No real bet existed yet, so nothing was converted. The Python ledgers
already multiply profit by the stake, so their real profit is now in units too. The model's staking
(`config/settings.yaml` bankroll, quarter-Kelly in units at 1% a unit) is unchanged.

## 2026-10-12: "one story" slips beside the value slips (Mike asked; Fun tab only, no model weight)

Mike, Oct 11 (Sunday night): a slip should tell one game story, with no two legs pulling against each
other (his example: Huntley 250+ passing with the Falcons' moneyline). Kept the value-ranked slips and
added up to 2 "one story" slips per NFL game (`fun.story_per_game`): every pair of legs hits together
at least 0.97x as often as unrelated in the anchored simulation (`sgp.one_story`, 0.97 for sim noise),
picked after the value slips so they never repeat one. Their text names the game the slip needs (who
wins, points, who throws) from the simulated games where every leg hits (`sgp.script`).

What the check found: on Oct 11 every value slip already passed the test (8 early games and SNF), so
story slips rarely add anything new. The Falcons ML slips we offered Sunday (4, with Huntley 125-150+
and Ravens receivers) were NOT opposed in the simulation: Falcons ML x Huntley 150+ lift 1.00, x Flowers
50+ 0.99 (a trailing team throws more). Only Falcons ML x Derrick Henry anytime TD pulled apart (0.88),
so the test would have removed 1 of the 4. Whether Mike's rule matters is now measured: every offered
slip (value, story, long shot) is logged once at its first offer to `data/ledger/fun_offers.csv` and
graded leg by leg; `betlab grade` prints hits vs expected and 1u profit at the naive price by style and
by one story or not. Revisit after ~4 Sundays. Mike's call whether to treat a team's moneyline with the
other team's QB yards as a conflict anyway (a rule, not the simulation).

## 2026-10-09: pause the "Win it with them" fun slips (parlay check; Mike chose)

The first parlay check found that theme 1 for 34 (5.9 expected) and its player overs moving against
the team's win. Claude proposed pausing it; Mike: "yes pause it". Shootouts and QB + receiver stacks
stay. Also from the check, for context on real money: FanDuel's SGP quotes pay a median 0.73x our fair
odds (average EV -14% single-game, -34% SGP+, -35% TD tickets), so parlays are the fun bucket's cost.

## 2026-10-09: college moneylines go market-only (weak-spot review #1; Mike chose)

The review found model-driven college ML edges closing 2.0% against us on 15 bets while FanDuel-lag
edges closed in our favor. Claude proposed `w_ml` 0; Mike: "yes make the change, I don't particularly
care about regularly betting on cfb". Re-open only with new evidence that the model's moneyline beats the
close (a backtest at FanDuel's prices, or a season of live model-vs-close tracking).

## 2026-10-04: the new schedule (to-do c-schedule-replan; Mike chose)

Mike: "Every gameline (moneylines, spread, totals) can be pulled in the morning, props and
adjustments to gamelines should only be pulled after injury reports/starters come out for the game."

| Topic | Decision | Why |
|---|---|---|
| Morning (daily run) | Every league's game lines, as now | Lines don't need the news; the morning is when FanDuel lags most |
| Props and line updates | Only in a per-game window after that sport's news: NFL 30–110 min before kickoff (inactives at T-90), college the same, NBA 15–75 min (injury report and lineups), NHL 30–90 min (confirmed goalies), soccer 15–55 min (lineups at T-60). Every slot of the day, not only the evening ones | Mike's rule. It also fills today's gaps: college noon and late kickoffs, NHL (no pull after 4:17 PM, so its CLV used a stale close and no confirmed goalies), NBA weekend matinees |
| Midday reprices (1:17, 4:17 PM) | Dropped once the per-game windows run | They re-pull lines without any news, which the rule rules out; the per-game pulls replace them as the close |
| Morning NFL props | Kept as **data only** (Mike: "Data only"): never picks, leans or fun slips | The props lag test (`c-props-clv`: +2.8% CLV on morning sides the first Sunday) needs morning prices |
| Free news checks | Every ~15 min inside the windows (goalies, NBA injuries and lineups, NFL inactives); a paid re-pull only when something changes | 0 credits; catches late scratches and goalie swaps |
| Where it runs | The Railway worker, after the cutover (Mike: "Worker first") | The repo is private: Actions minutes run ~1,400 a month of the free 2,000 before NBA nights, so frequent checks can't live on GitHub |
| Pick alerts | Phone push from the home-screen app (Mike chose it) when a new pick (not a lean) is logged | He wants to know the moment a pick is found |
| Credits | Roughly flat: the per-game windows add ~900 a month (NHL ~450, soccer ~400, college ~50); dropping the two reprices saves ~1,000–1,500 | October so far: ~580 of 20,000 |

## 2026-10-04: NBA game lines on the card (to-do c-nba-game-lines)

| Topic | Decision | Why |
|---|---|---|
| Pricing | Market-only, like the NHL: FanDuel against Pinnacle's no-vig (`cards/nba.py`) | The market beat our team model on 2025-26 closes (margin weight −0.13 ± 0.10) |
| Different numbers | Priced, moved along a normal curve, but **a lean at most** | Pinnacle and FanDuel shared the number on only 66% of spreads and 39% of totals near tip, so skipping (the NHL rule) would hide most totals. But on 2025-26 the moved chance didn't beat Pinnacle's own (log loss 0.6948 vs 0.6912 on 335 spreads, 0.6926 vs 0.6913 on 631 totals; noise either way). Model honesty: no picks from an untested adjustment; the leans' CLV tests it |
| Pushes | 2.8% spreads, 1.6% totals on whole numbers | How often 2025-26 games landed exactly on a whole-number closing line (498 and 502 lines). A normal curve said 2.9% and 2.2%; the measured rates are used |
| What to expect | Mostly leans, rarely a pick | Near tip, FanDuel's spreads and totals reached 3% EV against Pinnacle 3 times in 1,045 games (all lost; too few to judge). Morning prices may lag more and aren't in the backfill: the live card measures them. Moneylines weren't bought, so they're untested too |
| Credits | About 3 a day for the morning pull from Oct 20 (~90 a month) | The nightly NBA run already pulls game lines near tip; that pull is the close |

## 2026-10-01: the app's host, database and sign-in (Mike chose)

| Topic | Decision | Why |
|---|---|---|
| Budget | Yes: about $5-15 a month for the server, on top of the $30 Odds API | Mike treats the app as a learning project; at a $100 bankroll and $1 units betting won't pay for it |
| Host | Railway | Always on (the scheduler polls goalies, lineups and closes every few minutes); deploys on every push to GitHub; Mike adds the keys in its dashboard, so Claude never handles them. If heavy jobs push the bill past ~$15, move to a Hetzner VPS (~$5 flat, 4 GB) |
| Database | Supabase, free tier | Everything BetLab stores is 28 MB and grows ~2 MB a week, well under the free 500 MB. Postgres, sign-in and file storage in one; Mike knows it from WTW; plain Postgres, so no lock-in |
| Domain | None for now | Railway's free address works and the iPhone app needs none; Cloudflare at cost (~$10/yr) whenever wanted |
| Who signs in | Just Mike, by email link, no public sign-up | Private betting data; his girlfriend bets on DraftKings and the app is built around FanDuel |
| Apple developer account | Later, when the iPhone app starts | The iPhone app is last in the order; a free Apple ID covers 7-day installs; a home-screen web app can get iOS notifications in the meantime |
| Multiple users (planned, not built) | Design for it now: every personal table carries `user_id`, row-level security is on from day one, shared market data has no owner. No invites or second accounts yet | Mike: "in the future we need to separate it by accounts, so my data doesn't touch another user's data". Retrofitting ownership onto a live database means migrating every row and auditing every query; adding a column and a policy at the start costs almost nothing |

## 2026-09-28: grading Mike's own parlays (the Fun tab's builder)

| Topic | Decision | Why |
|---|---|---|
| What the grade measures | Not EV alone (Mike: parlays are always −EV, and EV runs lowest on the short ones). The main signal is FanDuel's payout as a share of fair, against what it usually pays on parlays of the same size. Then: leg prices, legs that fight each other, hit chance and leg count | Mike's 101 quotes: FanDuel paid 78-79% of fair up to +700, but 96% at +700-1500 and 107% at +1500 and up. One benchmark would have graded every long shot A+ |
| Small parlays encouraged (Mike: "good small parlays need to be more encouraged") | 25%+ to hit: +1 notch. Under 10%: −1. Under 4%: −2, and capped at B−. 6+ legs: −1. A typical-priced parlay of its size is a B | The fun bucket is for likely parlays with something to cheer for, not lottery tickets FanDuel is happy to sell |
| Tracking | Saved parlays go to `fun_quotes` as `custom-…` with their grade. They're graded after the games like every slip, with a record by grade (`fun_ledger.custom_summary`) | Tests whether higher grades actually hit more often than their fair odds say |

## 2026-09-28: NBA fun tickets pull alt lines (Mike chose it)

| Topic | Decision | Why |
|---|---|---|
| Legs for NBA tickets | Pull FanDuel's alt ladders (points, rebounds, assists, threes), about +4 credits a game (~900 a month) | Main lines sit near 50%, so Mike's 55-80% leg rule found almost nothing on main lines alone. The alternative was main lines at 45-80% |
| Pair rule | `fun.nba.min_pair_lift` 1.03 (the NFL's is 1.10) | Across different NBA players real 70%-leg pairs reach only 1.02-1.07; same-player stacks run higher but one leg per player rules them out |

## 2026-09-28: prop picks on the plain sharp price (weekly review #1; Mike chose it)

| Topic | Decision | Why |
|---|---|---|
| The over-lean shift in prop picks | **Off** (`props.shift_in_picks: false`). Picks use Pinnacle's plain no-vig price. The shift stays in the parlays' anchoring and as a sentence in each prop's story | Every corrected pick was an under with no edge against the plain price, so it lost to the close by construction: −1.4% raw CLV, 24% beat it (180 leans: −5.8%, 4%). On 2026's first 325 receptions and receiving-yards lines, overs hit 45.8% (SE 2.8) against the plain market's 45.3%, while the shift said about 41%. It was never confirmed on 2024. Morning sides +EV on the plain price beat the close (+2.8%, 19 sides) |
| Bring it back? | Only if 2026's graded lines (`prop_lines.csv`) or a 2024 backfill show the lean again, with a MODEL_CHANGELOG entry | Rule 3: settings follow evidence |
| Only current-rule picks count (2026-09-30, Mike: "just keep current rule", then "I want only stuff under current rules") | Props rows priced on the corrected market (`market_source` "... corrected for the over lean") stay in `picks.csv` (rule 4) but are left out of the go-live checklist, the Results tab's record and the page's pick list (`golive.current_rule`); `retired_excluded` counts them | All 212 graded props were logged Sep 24–28 under the retired rule: 209 unders, −5.3% raw CLV, 7% beat the close, with no difference by hours before kickoff. They also hit 47.4% against a corrected 55.5% (209 decided). They grade a rule we no longer use, not the live one |
| Picks only within 36 hours of kickoff (2026-09-30, Mike chose it) | `picks.horizon_hours: 36`: a qualifying edge further out shows and logs as a lean. Picks logged earlier than 36 hours before the start stay in `picks.csv` but leave the record, the checklist and the page (`golive.current_rule`) | A price from a week out isn't the one he'd bet on game day, and early lines move the most. It matches the 36-hour window of the odds pulls and the soccer card. It removed Penn State −6.5 and LAC–SEA Under 43.5 (still to play) and one settled pick, which leaves 2 picks (0–2) |
| The go-live checklist is a scorecard, not a gate (2026-09-30, Mike: "realistically I am going to be making bets anyways... let's just train till Oct 18 and over time identify and correct weak spots") | Same bars and code (`golive.py`); the page calls markets strong, weak spot or building instead of ready for real money | At about 2 picks a week no market would pass for months, and Mike decides what he bets (rule 5). The work shifts to finding and fixing weak spots with the graded record, while the thresholds still move only on evidence (rule 3) |
| The NHL runs now on free data (2026-09-30, Mike: "can we do nhl now without spending odds api tokens?") | NHL stats API plus ESPN's DraftKings lines and probable goalies; the Games tab's NHL view and a tracker; no Odds API pulls | The season opened Sep 29. Free sources covered everything but FanDuel's and a sharp book's prices. The model tied DraftKings' opener and lost slightly to its close, so reads are tracked, never picks |
| FanDuel's NHL prices from the Odds API (2026-09-30, Mike: "go do all 3") | League `nhl` in the auto pulls from Oct 1 (about 3 credits a pull, up to 3 pulls on game days), shots-on-goal props once a day (about 1 credit a game) | The free lines can't show FanDuel lagging the sharp books, which is where every other sport's picks come from. Roughly 300-500 credits a month out of the 20,000 plan |
| The NHL ticket's band is +300 to +1500 and favors winners and goals | `fun.nhl.band`, `fun_nhl.CHEER` | Mike's best-value band and his "something to cheer for" rule; without the weighting the first ticket was mostly underdog +1.5 legs |
| Hockey runs on FanDuel (2026-09-30, Mike: "how do we transition hockey to FanDuel") | The NHL view's line, market chance and reads use FanDuel's prices and Pinnacle's no-vig chance from the daily pull; ESPN/DraftKings stays as the fallback and for goalies | FanDuel is where Mike bets, and Pinnacle is a sharper "market" than DraftKings for judging reads |
| Build your own follows the Fun tab's market (2026-09-30, Mike: "different for each market and include everything for that market") | Every game in the market with every leg we price: NFL and NBA from their simulations; college from its similar-games draws; NHL and soccer from their score grids (all moneylines, puck lines or double chance, totals both ways; NHL shots and saves drawn independently of the score, labeled). Switching markets clears the slip (SGP+ never mixes sports) | One builder for every market, priced the same way the tickets are; legs FanDuel's feed lacks show our fair price, labeled |
| "Open in FanDuel" buttons (2026-09-30, Mike: "some apps have an export to FanDuel button") | Every odds pull asks for the books' betslip links (`includeLinks`, free); `links.py` matches each pick and leg to its FanDuel outcome by game, price, number, player and side when the page bundle is built; the page opens one bet or combines a parlay's legs into one betslip link | Claude never places bets: the link only fills FanDuel's betslip for Mike to review. A leg with no exact FanDuel match gets no link (never a wrong one); the button says how many legs to add by hand. The multi-leg link format is the one betslip-sharing apps use; Mike's first tap is its first live test |
| BetLab moves to its own server, web app and mobile app (2026-09-30, Mike: "create a mobile app and change the claude page to a real web page... hosting all functions, db's... running and checking things live... instead of using my claude usage") | Planned for the week of Oct 1 (ROADMAP, "BetLab as a real app") | Live checks without GitHub cron delays or Claude routines; a real product Mike can use on his phone |
| NFL fantasy next season (2026-09-30, Mike) | Planned for August 2027 (ROADMAP, "NFL fantasy") | The props models already give every player's stat distribution |
| NHL props are ML from the start (2026-09-30, Mike: "the season just started, it's the perfect time to start an ML model") | Trees on 2020-26 player history now; every FanDuel line and feature logged from day one for the market layer | The trees beat a recent average and a hand-built model on every stat; the market test needs this season's lines, so logging starts now |
| NHL props pulls: shots, points and saves, morning and after 3 PM ET | About 3 credits a game per pull (FanDuel posts shots and saves only) | The afternoon pull gives props a closing price for CLV; the paid key reset to 20,000 on Oct 1 |
| Soccer analysis stays on the list (Mike: "will eventually happen idc, there's so much data") | Planned, aimed at props first | Ratings lost to the close in all six leagues, but props and lineups are untested |
| College basketball's full paid card from the Nov 2 opener (2026-10-15, Mike: "move the FULL college basketball stuff to last week of October") | `leagues.ncaab.paid_odds_from: 2026-10-26` and a pre-game pull 15-45 minutes before tips (`schedule.pregame.ncaab`, like the NBA) | Replaces the Mar 1 plan below. Game lines only (NY bans college props), market-only, model weight 0; the 9:55 pull plus one batched pull per tick with tips due: about 3 credits each, ~2,000 a month at November's slate. Fits the 20,000 plan with the NBA |
| College basketball runs on free lines until Mar 1 (2026-09-30, Mike: "I'd only really bet on college basketball for March Madness") | `leagues.ncaab.paid_odds_from: 2027-03-01`: ESPN's DraftKings lines feed the reads; no FanDuel card until then | Saves roughly 3 credits a day for four months while the reads still build a record before March |

## 2026-09-28: historical odds spending plan (Mike: "I like your plan")

The paid key had 10,328 credits until the Oct 24 renewal, and live pulls need about 2,000
of them. It resets to 20,000 a month after that. Costs: a historical snapshot is 10 credits
per market. Game lines are one call per league per day; props are one call per game.

| Order | What | Credits | Why |
|---|---|---|---|
| 1. Now | **NBA 2025-26 game lines near tip** (h2h, spreads, totals), for the team model vs the close | ~5,000 | The NBA is ML-first and opens Oct 20. It's the one test we can't get another way (ESPN's past odds are empty) |
| 2. Free, from Oct 9 | **Soccer:** does FanDuel lag? Answered by the live lines already logged in `soccer_lines.csv` and graded on football-data.co.uk's free close | 0 | European leagues resume Oct 9-10. A 2024-25 FanDuel backfill (~6,800; big five ~6,000) only if live lines look promising |
| 3. Free, then after Oct 24 | **NFL props morning-line CLV** (`betlab backtest lag`): live Sundays until the renewal, then 2025 weeks 10-18 morning snapshots if it still looks promising | 0, then ~4,800 | The first Sunday was suggestive (19 sides, +2.8% CLV, SE 1.7%) but small |

Not bought: NBA props history (49,000-98,000 credits for a season; 150 sampled games ~6,000),
morning + close NBA lines (~10,000), and the full 2025 NFL props morning season (~9,600).

## 2026-09-25: college basketball (Mike: "keep training")

| Topic | Decision | Why |
|---|---|---|
| Data | CollegeBasketballData, the CFBD key, 5 seasons saved to data/history | Free; box scores, closing lines, and openers for two seasons |
| Model | Opponent-adjusted efficiency and pace, tuned on 2023-24 only | Standard, testable, same shape as the college football ratings |
| Use | The opener, not the close | It loses to the close, but the line moves toward it after the open: +0.38 pts at 3+ disagreement (both seasons agree), +0.56 at 5+ (mostly one season). About +1.4% to +2% CLV |
| Live | November: early pulls, reads at 3+ points with the gap kept, plus the card's market-only picks; reads judged by live CLV by size | 3+ is where both test seasons agree; the bigger-gap edge needs live confirmation |
| Roster shift (Sep 26) | Add the early-season roster shift to the ratings behind the reads; keep model weight 0 for picks | The model's November miss tracked roster change (+0.47 per point, four seasons agree) while the market's didn't. Held out, reads improved (+0.38 → +0.53 pts at 3+) and the close still wins, so it sharpens reads, not picks |
| Roster source | ESPN preseason rosters (free, every 3 days Oct–Dec), CBBD player stats (1 call a season) | CBBD's 2026-27 rosters were empty on Sep 26; ESPN's ids are the ones CBBD's player stats carry. Lists that haven't changed since last season are ignored |
| Unknown venue (Sep 26) | Skip any game the schedule can't place in a state; count New York and unknown-venue skips in the card's notes | 2025-26 had 20+ New York games between two out-of-state teams (MSG events, the Big East tournament, NCAA games in Buffalo). An unmatched game had defaulted to "not in New York"; the rule must fail closed |

## 2026-09-25: go-live checklist readings (no change to the bar)

| Topic | Decision | Why |
|---|---|---|
| "Sure it's real" | P(true average CLV > 0) from a skeptical prior (SD 2 points), per-pick spread at least 5 points | A plain t-test called two lucky prop picks 99% sure; this reads them 83%. For scale, 50 picks at +1% read about 91% |
| Pace | Picks with CLV by Oct 17 at the last two weeks' rate | Shows which markets can reach a decision in time |
| The bar | Unchanged (50 picks, +1%, 55% beat close) | Changing it is Mike's call at the Tuesday review, with these numbers in hand |

## 2026-09-25: college moneylines before Week 5 (to-dos c-cfb-history, c-cfb-flags)

| Topic | Decision | Why |
|---|---|---|
| History | Rebuilt with probability-averaged moneylines | The price-median history broke about 50 near-pick'em games |
| Moneyline weight | Keep 0.22 (the refit agrees) | Out of sample +0.0016 log loss per game (SE 0.0012, 3 of 4 seasons). Thin, but it's paper until the checklist and CLV judge it |
| "Check the news" | Flag from 20 points, not 12 | At 12–20 points the model's side won exactly the market's rate: flags there were noise, about a fifth of the slate |
| Pick guardrail | Unchanged at 12 points | Loosening it would let the model tilt picks where it has shown no information |

## 2026-09-25: soccer goes market-first (Mike: "soccer can prob use ML")

| Topic | Decision | Why |
|---|---|---|
| Team ratings | Built and backtested, weight 0 | They lose to the close and to the early-week line in all six leagues (0.015–0.023 log loss) and don't predict line moves (48.7% toward the model) |
| Where picks come from | FanDuel vs the sharp price (Pinnacle, else Betfair Exchange), like NFL props | That's where the NFL's edge shows up; the ratings add nothing |
| ML layer | Needs information the market prices late: lineups/rotation, congestion, props | Team strength is fully priced by early week |
| History for testing | football-data.co.uk (free) | Nine seasons of closes per league; no credits needed |
| Live market | FanDuel's 3-way result only; pulls ask for `h2h` only (1 credit) | FanDuel posts nothing else for these leagues in the feed |
| Grading and CLV | football-data.co.uk's score and sharp close (Pinnacle, else Betfair Exchange) | Free, and a real sharp close, with no near-kickoff pulls needed for the many kickoff times |
| Champions League | Not on the card yet | football-data.co.uk has no UCL files to grade from |

## 2026-09-25: non-QB injuries (Mike: "factor in injuries to the game sense", due Sep 26)

| Topic | Decision | Why |
|---|---|---|
| Which absences move numbers | Offensive-line starters, the top target, the opponent's top pass rusher and defensive backs | Each is 2+ SEs from zero, has the same sign in both halves, and cut error out of sample |
| Lead back | Listed, but doesn't move numbers | Its 2016–20 effect vanished in 2021–25 (committee backfields) |
| "Missing" live | Out/Doubtful on the report, or off the active roster (reserve, cut, traded) | IR players drop off the injury report; with the roster, live counts match "didn't play" 85–98% of the time |
| Early season | Live counts from 2 games of snaps | nflverse snap counts lag a week; "80%+ of snaps in both games" still finds starters |
| Script lean | Injuries now feed the pass edge it reads | The lean's inputs are pass EPA changes, and injuries are measured in the same units. The lean itself was fit with QB and weather only; noted, not refit |

## 2026-09-25: fun-parlay backtest and game reads (Mike: "start the parlay backtest"; "our game reads should factor into the parlays")

| Topic | Decision | Why |
|---|---|---|
| Simulator v1 | Adopt the volume, efficiency and TD settings fit on 2021–24 | They held on 2025 (fits and co-movement), with no loss in single-player accuracy |
| Test season | Fit on 2021–24; judge on 2025 only | So the improvement isn't measured on the data that chose it |
| TD–yards link | Leave open; no guessed fix | TDs-by-yards didn't help; about 1 point of lift on a 70% pair |
| Game reads in parlays | Next: the Games tab's script lean (tested on 2025 lines) marks and ranks legs that fit the game, and slips show a "with our read" price next to the market-fair one | Mike reads the game first. Fair odds stay market-based: the lean is confirmed on one season only |

## 2026-09-25: the NBA pipeline (Mike: "start the NBA pipeline")

| Topic | Decision | Why |
|---|---|---|
| When props are priced | Hourly "BetLab tick: NBA" routine, 22:20–02:20 UTC. Each run prices games tipping 15–75 min later, so each game lands in one run | Lineups and late injury news land in the last hour. Five runs a night keep the routine count and credits down (about 8 credits a game, once). A free ESPN scoreboard check makes empty runs cost seconds |
| Pricing | Market-only (model weight 0); the model is tracked, not trusted | Rule 3: no market evidence yet. The ML layer learns from the tracker |
| Lineups | `pre_lineup` settings until a live lineup source is tested | The lineup is the biggest lever in the backtest, but no free live source is wired yet |
| Rosters and injuries | ESPN's live site API (current rosters; live injury report) | Box-score rosters miss offseason moves on opening night; the daily injury file is a day behind |
| "Sits" rule | "Out"; "Day-To-Day" with a fresh ruled-out note; or a return 3+ days away | ESPN often leaves game-day scratches as day-to-day. A heuristic, to check against October box scores |
| NBA CLV | Closing pull only for games with open picks that haven't tipped at the next run; otherwise no CLV | A pick's own snapshot is not its close. Picks without a close don't count toward go-live |
| All-Star games | Dropped from all NBA data | They're labeled regular season and distorted stars' recent form |

## 2026-09-23: intake (Mike's answers)

| Topic | Decision | Why |
|---|---|---|
| Leagues | NFL, NCAAF, NBA, NCAAB, WNBA, EPL, UCL, La Liga, Serie A, Bundesliga, Ligue 1, MLS | Mike wants them all covered; he picks which bets to actually play |
| Bet types | Straight bets; parlays/SGPs only in a separate "fun bucket" | Parlay house edge compounds (≈17% for a 4-leg of −110s) |
| Approach | Hybrid: our model plus a no-vig check against sharper books | The most realistic path to an edge; a model alone rarely beats efficient lines |
| Books | FanDuel plus 1–2 others, chosen from our own best-price data | Line shopping is the easiest edge |
| Bankroll | $100 at go-live (1u = $1); $500+ only once the model proves itself | Money he can lose without harm |
| Oct 18 | Real money only in markets that pass the go-live checklist | Small samples can't prove an edge by win rate |
| State | New York, where FanDuel is live | Brings the NY college restrictions |
| Odds data | Free tier now; pay once the model earns it | Mike's call |
| Where to look | Private claude.ai page; Excel dropped (CSV download instead) | His PC is rarely on, so OneDrive files wouldn't update |
| Learning | Why-notes, Betting 101 + calculators, weekly reviews | Mike wants to learn the math |
| Working style | Claude builds, Mike reviews; 30+ min a day, mostly at a computer | His call |
| Cloud | Private GitHub repo + GitHub Actions | His PC is rarely on during the day |
| Page sync | A Claude cloud routine (not a Google Drive bridge) | Mike's choice, after a feasibility test proved a routine can write the page database |

## 2026-09-23: New York rules and legal facts

- **College:** NY bans all college player props, bets on games involving NY colleges,
  and college games played in NY. Enforced in `ny_rules.py`, erring toward skipping
  legal games.
- **Pro player props:** they remain legal in NY, but regulators have been reviewing
  a ban since Feb 2026. Bill A9636, which would have allowed only final-outcome bets,
  failed. So game models must stand on their own.
- **FanDuel minimum stake:** sources disagree ($0.10 vs $5). Mike checks on Oct 18,
  because $5 would break $1 units.

## 2026-09-23: build and modeling

| Decision | Why |
|---|---|
| Python 3.13 venv (not uv) | uv wasn't installed and 3.13 was; it avoids 3.14 wheel gaps. CI matches |
| nflverse via `nflreadpy`; CFBD API v2 | Free, complete, current |
| Points ratings only in the NFL/college combiner; EPA kept for notes | EPA is 95% collinear and got a negative weight |
| Key-number distribution centered by median, continuous CDF | Plain reweighting biased picks toward underdogs (~46% "value" picks); a discrete median jumped |
| Blend against the market's no-vig *price* in logit space | Comparing lines alone ignores juice information and picked the wrong side |
| Blend weights fit on history; NFL ≈ 0, college moneyline 0.22 | The closing market beat our ratings out of sample |
| No moneyline picks beyond −250/+250 | Longshot "edges" lost about 23% ROI in the backtest |
| Early weeks at zero model weight (NFL ≤ 2, college ≤ 4) | Stale ratings produced fake edges (e.g. Akron +460) |
| "Check the news" only when the model's weight is 10% or more | Disagreements from a zero-weight model aren't news |
| College: ridge 1, half-life 150 days | Tuned on 2016–2021 |
| College moneylines averaged as probabilities; impossible pairs dropped | The median of −110 and +100 isn't a price; garbage data exists |
| Props: early-exit mixture, QB attempt share, carry concentration 20 | The calibration backtest showed thin tails and a passing bias |
| Page taps go through branch `claude/page-sync` | Routines can't push to `main` (the bot's commits there aren't Mike's) |
| The workflows start the routine via its API trigger; the routine has no schedule | The page updates minutes after each run; no redundant daily runs |
| `fire_page_sync.sh` fails the workflow on rejection | GitHub emails Mike, so a broken sync can't go unnoticed |
| Evening check Thu/Sun/Mon at ~6:52 PM ET (Mike's request) | Catches prime-time line moves after inactives, about 40 credits a month |
| Shared To-do tab on the page (Mike's request) | One place for what each of us owes next |
| Claude never handles API keys, even with permission | A fixed safety rule; Mike adds keys himself |

## 2026-09-24

- Documentation pass: `CLAUDE.md`, a README in every folder, and `docs/*`, so any new
  session can navigate without prior context (Mike's request).
- CI runs tests only for `main` and pull requests. The routine's daily
  `claude/page-sync` pushes don't need a test run.
- Odds snapshots are filed by **Eastern** date and time (they were UTC). A pull
  between 8 PM and midnight ET would otherwise land in tomorrow's folder, and the next
  morning's `pull --auto` would wrongly skip. Found while documenting `data/odds/`.
- New sport folders under `data/odds/` write their own README, so the "every folder
  documents itself" rule holds as leagues are added.

## 2026-09-24: NFL props and fun parlays (Mike's answers)

| Decision | Why |
|---|---|
| **Fun SGPs:** the page shows our fair odds and Mike types FanDuel's quoted SGP price to see EV | No odds feed carries FanDuel's SGP prices; the app builds them on the fly |
| **SGP goal:** best value inside a payout band (+250 to +1,500) | Mike's choice over longshots; most SGPs are still negative EV, this picks the least bad |
| **SGP bet types:** main lines, alt yardage ladders, anytime TD | Mike's choice |
| **Straight props** go through the go-live checklist like everything else; SGPs stay in the fun bucket | Keeps the real record honest |
| **Data:** Mike bought the $30 plan on Sep 24 (a second, paid key). The free key stays active: spend it first each month, then switch to the paid key. Decide by about Oct 20 whether to keep paying | Mike's call. The paid key also allows a backfill of 2025 prop lines to backtest props before real money |
| **SGP builder live today** as a labeled preview (Falcons @ Packers), then hardened in Phase 1 | Mike asked for it today |

## 2026-09-24: fun-parlay modeling (Claude)

| Decision | Why |
|---|---|
| The market sets each player's line (Pinnacle, else a consensus) and tails (the books' alt ladders); our simulator supplies the correlations | Same lesson as game lines: closing markets beat our ratings, and the props model has no backtest against real prices yet (rule 3) |
| Our model's own read is shown next to the market's on the Fun tab, with no weight | Mike asked for real player analysis; showing it teaches without betting on an unproven model |
| Official injury report: Out/Doubtful players are removed and their volume shifts to teammates; Questionable players are flagged | Jayden Reed (Out) held a 14% target share in our history on day one |
| BetOnline's alt ladders are excluded | They ran far fatter than every other book's (Jonnu Smith 28+ yds 31% vs DraftKings' 25+ 20%) |
| Other books' price for the same alt rung is a ceiling on a leg (and scales parlays down, never up); legs that beat FanDuel by more than 8 points (4 for model-only rungs) are dropped | Our tails were too fat for low-usage players; big disagreements are more likely our error |
| Parlays are ranked by leg value (fair chance × FanDuel payout), not by correlation | FanDuel prices correlation itself; only its quoted price can show an edge |
| **Slips are 4–5 likely legs (each 55–80%), fair odds +150 to +1,000** (Mike's request, same day) | Long-shot rungs made every slip hinge on one leg that rarely hits; near-certain legs add only margin |
| **Props model v0.2: roles from snap share, matchups, injury absences** (Mike: "it needs to do real analysis") | The first live game showed team shares summing to ~130% and roles lagging; the 2023–2025 backtest improved every stat (`MODEL_CHANGELOG.md`) |
| Model variants are accepted only if they lower the walk-forward CRPS; rejected ones are logged | Rule 3, applied to the props model's own settings |
| **Props model weight stays 0** after the 2025 market test | Alone it loses to the market; against the over-corrected market it adds ~nothing out of sample (rule 3) |
| **Correct the props market's over-lean** for receptions and receiving yards (not rushing/passing) | 2025: overs priced ~49–50% hit 44.5–46.3%; the correction beat the raw market out of sample; only clearly non-zero shifts kept |
| **Straight props stay paper-only; no FanDuel-vs-Pinnacle prop picks with real money yet** | At T−60 that rule lost 21.6u on 105 bets (uncorrected) and was break-even corrected; morning-price CLV must show an edge first |
| **Straight props go on the card now, as paper** (Mike: "why can't we do #1 for tonight too") | Picks are logged at prices available when logged (never backdated); the evening snapshot is their close, so CLV starts piling up |
| **Prop unders need 10%+ EV to be picks** (Sep 26, Mike: include unders only if "reallllly good EV let's say 10+") | Stricter only. Every prop edge on Sep 26 was an under from the over-lean correction; unders at 5-10% are leans now. Picks already logged stay in the ledger (rule 4) |
| **No over picks; overs to cheer for go in the fun bucket** (Sep 26; Mike: "EVERY straight is an under, that's boring") | Overs had no value against either price (385 lines: overs −6.5% EV vs plain Pinnacle, none at +5%), and the 2025 over lean holds at every line size, so there's no honest over pick to add. The Fun tab's slates list the best-value overs (cost shown) and one SGP+ ticket per kickoff window |
| **Game lines as parlay legs** (Sep 26, Mike's request; `sgp.game_line_legs`) | Moneyline, spread and total legs priced at the sharp no-vig price, joint with player legs through the simulated points; graded from the final score. One side leg per slip |
| **No parlays when the simulation can't match the market** (Sep 27; `fun_nfl.anchor_problem`) | Anchoring reweights 20,000 simulated games to hit every market price; for Panthers @ Browns it kept 33 effective draws and still missed a price by 21.6 points, and Vikings @ Buccaneers kept 110. Slips from so few draws are noise, so a game under 1,000 effective draws or missing a price by 2+ points gets no slips, only a note. Its anytime TD scorers stay on the window's TD ticket at Pinnacle's no-vig chance (`fun_nfl.market_td_legs`): they never needed the draws, and Mike's rule is one scorer from every game (both skipped games fell off the Sep 27 tickets) |
| **No primetime adjustment** (Sep 27, Mike asked whether primetime games play out differently; `scripts/primetime_study.py`) | Against closing lines, 2006-25: primetime games land 0.8 points lower on the total than day games (-1.0 with dome, wind, cold and late-season controls, 95% CI -2.0 to +0.2), and sides and pace (126 plays either way) don't differ. The famous primetime unders were real only in stretches: 59% in 2019-23 (+36 units at -110), 50% in 2024-25, 47% in 2013-18; all 20 years, 52.0% (-7.6 units). The market already sets primetime totals about a point higher. One open signal: 2025 prop overs fell 4.6 points short of Pinnacle in day games but 2.0 in primetime (+2.6, CI -1.2 to +6.6, 52 games); rechecked with 2026 data (to-do `c-prime-props`) before any change |
| **Page documents stay under 256 KiB** (Sep 26) | The Fun document reached 253-264 KB of compact JSON (the database's limit is 256 KiB) and the page sync writes every document in one all-or-nothing batch, so one oversized document would stop the whole sync. The export now writes each game's fun block as its own `fun_games` document (app/fun keeps an index) and chunks a month of the ledger; it warns above 250 KB |
| **Anytime TD ticket per NFL window** (Sep 26, Mike's request; `sgp_plus.td_ticket`) | One scorer per game; a cross-game parlay pays the product of its legs, so FanDuel's price and EV show without a quote (a boost can be typed in). Fun bucket only |
| **TD picks by our TD read, at half weight** (Sep 26, Mike: "get some analysis in there") | The likeliest scorer is cheapest (FanDuel's TD margin is 5% on favorites, 24% on long shots), so a read has to beat that. Red-zone role and recent scoring beat usage + team points on 2025 (+0.0024 log loss) but were never tested against a TD market: half weight toward Pinnacle, every read tracked (`td_reads.csv`), and the likeliest-scorer ticket's EV shown beside it |
| **College lines-only SGP+ ticket per day** (Sep 26; `cards/fun_ncaaf.py`) | Mike's rule. Legs from past games with a similar spread: big favorites cover with the over (lift 1.12-1.19 at 15+ points, both halves of 2014-25; held out 2022-25 it beat independence by 0.031 log loss at 21.5+). Up to 4 games so side + total pairs fit the band; no unders; NY schools, NY venues and unconfirmed venues skipped |
| **A second account (Mike's girlfriend), Google sign-in** (Oct 10, Mike) | Bets, typed prices, saved parlays, settings and alert devices were per-account from the start (row-level security). Added: each account's own real-money start (`user_settings.real_from`, migration 0007; empty = Oct 18; hers from day one, she's 21+), Plan and Reviews shown to the owner only (`web/lib/owner.ts`), and every account's typed prices and marked parlays joining the fun ledger as quotes (Mike: combine them) so they're graded and counted while the ledger's stakes stay the owner's; every account's saved parlays graded. Sign-in: Continue with Google (Supabase OAuth; sign-ups stay off, the same email links to the invited account); Apple waits for a paid Apple developer account (`NEXT_PUBLIC_BETLAB_APPLE=1` shows it) |
| **The NFL's 9:30 AM international game stands alone** (Oct 10, Mike) | It's its own slice ("NFL morning game", kickoffs before noon ET), flagged prime time like night games: it never joins the 1 PM early-games SGP+ ticket, and as a single game it gets single-game slips (no SGP+ or TD ticket) |
| **Fun tickets per kickoff slice, locked 15 minutes before it starts, with a notification** (Oct 10, Mike) | The day-long college and soccer tickets were rebuilt from the games not yet started on every pre-game tick, so a new parlay replaced them at each kickoff (two different Oct 9 college tickets got quoted). Now every sport has slices (`sgp_plus.SLICES`, Eastern time: NFL early / late / night at 3 and 7 PM; college noon / afternoon / night at 3 and 7 PM; soccer morning / midday / evening at 11 AM and 5 PM; NHL afternoon / evening / late at 5 and 9 PM; kickoffs before 4 AM count as the night before). A slice's SGP+ and TD tickets follow every rebuild (the latest lines and news) until 15 minutes before its first kickoff; the first build at or after that is final (`keep_tickets`, `locked_at`), shown until 4 hours after its last kickoff. The pregame tick runs a free `lock-due` check so the lock happens on time even with no pull, and `betlab alert` pushes each newly locked ticket once (`lock:<slate>` in `alerts_sent`). Lock 12 hours out was tried for an hour the same day: Mike wanted the most news in the ticket. In practice the lock is the first 15-minute worker tick within 25 minutes of the first kickoff (`LOCK_MINUTES`): exactly 15 minutes before :00 and :30 kickoffs, never under 10, so a 7:07 PM slice doesn't lock at 7:00. The NBA (same day, revised that evening, Mike: "per tip time isn't a great split"): slices are 30-minute tip windows from the night's earliest unassigned tip (7:00 + 7:30, then 8:00 + 8:30 ...; `fun_nba.tip_anchor`, "NBA 7:00–7:30 PM tips"). On the 2025-26 schedule that put 81% of games on a ticket (per tip time 59%); wider windows and fixed evening blocks lost 13-37% of games, because a slice locks ~25 minutes before its first tip while each game is priced 15-45 minutes before its own. A rehearsal of four 2025-26 nights through the live code locked every slice 15 minutes before its first tip with every window game priced. A news re-pull merges into its window's slate (`fun_nba.merge`) |
| **SGP+ rules by sport** (Sep 26, Mike's answers) | NFL: any size ("I watch RedZone"), per kickoff window, plus prime-time singles. College: one lines-only ticket per day (NY bans college props; never NY schools or NY venues). NBA: like the NFL (per night plus national-TV singles). Soccer: one ticket per day across all leagues. Never across sports |
| **Page reorganized** (Sep 26, Mike's request) | Today shows one day at a time with sport and bet-type filters (past days from the ledger with results); each game's fun slips live on the Games tab; the Fun tab keeps the SGP+ tickets, overs and prime-time singles; Results leads with a plain-English summary and per-market cards. The results summary uses raw CLV for props, like the checklist |
| **SGP+ ticket per slate** (Sep 26, Mike's request; `sgp_plus.py`) | One mini same-game parlay (2–3 legs, overs only) from each of 2–4 games in a kickoff window, fair odds +500 to +4000, fair chance the product across games; only FanDuel's quoted price can show an edge. Fun bucket only |
| **Props are judged on raw CLV** (Sep 26; `clv_raw`, `golive.checked_clv`) | The over-lean correction applied to the close gave every under ~4 points of CLV before the line moved: the first two graded props read +4.3% and +9.5% corrected, −3.6% and +0.2% raw. The checklist would have passed props on the correction alone. Corrected CLV is still shown; the over lean itself is checked by calibration (do the unders hit at the corrected rate?) at the Oct 17 review |
| Props are pulled once a day (next 36 h) and again 30–110 minutes before kickoff | The first gives the prices we pick at, the second the close we measure CLV against |
| **Fun slips: unders only as near-locks (75%+), at most one per slip** (Mike: "no fun betting on all unders") | Fun money is for fun; the price check still shows the cost (overs are FanDuel's worst-priced side) |
| **One long shot per game** in the Fun tab (+1500 to +6000 fair, 2–4 legs, legs down to ~12%), tagged on the page (Mike's request) | Fun bucket only; same guardrails as the other slips |
| **One leg per player in every slip** (Mike: "remember the player-stack thing") | FanDuel quoted a Penix + London catches + London yards slip at +104 against +230 for its legs, about 20% under our fair; books treat same-player legs as nearly one bet |
| **Game Previews lead with how the game goes** (Mike: "we are depending almost too much on the math… not figuring out how the game will go") | A Games tab per NFL game: market score, our read, pace and run/pass, unit matchups ranked 1–32, and lines that fit the script. Mike picks the lines that make sense with the game |
| **The score comes from the market; the engine explains the how** | Walk-forward, the play-by-play engine lost to closing lines on margin and total but beat a team's recent average on dropbacks |
| **The script lean shows on the Games tab only, not in picks** | It beat the 2025 prop market (53.6% vs 49.8% where the matchup was strong; SE-checked by game bootstrap) but on one season; rule 3 needs out-of-sample evidence before it touches prices |
| **Game previews account for who plays and where** (Mike: "factor in injuries… and weather") | QB changes are the biggest single swing and tested well out of sample; weather effects are fit on 14 seasons. Other injuries are listed with each player's snap share, not modeled yet |
| **The expected starter comes from the ESPN depth chart, skipping QBs ruled Out or Doubtful** | The depth chart reflected the Giants' switch to Winston before the week's injury report existed |
| **Retractable roofs get no weather effect** | They're usually closed in bad weather; the preview says so rather than guessing |
| **Before Friday's game statuses, the preview lists missed and limited practice** | On Thursday nearly every Sunday team's report has no game status yet |
| **No man/zone coverage data** | Coverage matchups added nothing to 2025 prop lines even with true in-season rates, and free weekly proxies can't estimate it |
| **No game-line bets from unit matchups** | 14 seasons of interactions showed no edge vs closing lines |
| **Two receiving-yards matchups (yards per target allowed by position, deep-ball fit) wait for a second season** | t ≈ 2 among seven tries; 2024 lines or 2026 grading must agree first |
| **Confirm the matchups by tracking 2026, not by spending credits on 2024** (Mike chose option 1) | Free; about 4–6 weeks for a useful sample; 2024 would have used ~9,600 of ~10,400 paid credits before the Oct 24 renewal |
| **Log every main prop line with its features and result, not just the leans** | An honest record for each read, and the training set for the planned props ML model (Mike: "eventually a machine learning model") |
| **College analysis focuses on the early week** | The efficiency read beat opening lines 2022–25 but not closing lines; college odds are pulled on Tuesdays so the read sees near-opening numbers |
| **College reads only for FBS-vs-FBS games** | That's what was tested; FCS mismatches produced the strongest, least trustworthy reads |
| **College reads are tracked, not priced** | One backtest window (2022–25) and several tries; 2026's tracked record has to agree (rule 3) |
| **Grade fun slips from their leg labels** | Custom slips and replaced builds still grade; the day's archive keeps only the last build |
| **Log and grade leans too** (`data/ledger/leans.csv`) | Only 3 paper picks by Sep 25; leans test the same FanDuel-vs-sharp signal with more samples. The go-live bar still counts picks only |
| **Midday re-prices on game days** (1:17 and 4:17 PM ET) | One snapshot a day only catches lags that exist at 10:17 AM; each extra look costs about 3 credits a league and never re-logs a pick |
| **Price NBA props after starting lineups** (about 30 minutes before tip) | In the 2025-26 backtest the lineup was the biggest single gain (minutes error −7%, every stat better); morning prices use the `pre_lineup` settings |
| FanDuel prices Mike types are saved (`fun_quotes`) | His first five quotes matched our fair odds within ±7%; more of them will show whether our correlations hold |
| The evening check also pulls prime-time props and rebuilds the parlays after inactives; daily props pulls wait for the two-key switch | Keeps the free key from draining before the paid key is wired |
