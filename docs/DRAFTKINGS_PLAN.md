# DraftKings: the second book, at full parity by Oct 18

Mike, 2026-10-12: "I chose my second sportsbook: DraftKings. I need DraftKings fully ready to go by my
go-live, it needs to be just as developed as FanDuel is for us." And: "need to consider what happens when
FanDuel markets differ from DK or lines, etc. There's many edge cases to consider."

**Status (Tue Oct 13, 2026, 4:30 PM ET): built (Oct 12), links settled by Mike's iPhone test (Oct 13); paper until Sun Oct 18.**

| What | State |
|---|---|
| Game lines and props at both books, one bet per pick (better EV, ties to FanDuel) | Live on paper |
| A prop at a number the sharp books don't hang: a lean at most, at both books (Mike) | Live |
| Links: each pick and lean opens at its own book | Live; DraftKings' web link opens its app with the bet in the betslip (iPhone test, Oct 13) |
| Parlays: every leg's DraftKings price, its nearest rung where it lacks ours, each slip's DraftKings side and price box, the Build tab's switch | Live; each slip opens at DraftKings in one tap (its own Open in DraftKings button, Oct 13), as does a Build-tab slip at DraftKings |
| DraftKings quotes (`<sgp_id>~dk`) and its own quote model | Ready; Mike types from Tue Oct 13; FanDuel's pattern stands in until ~40 |
| Each bet's book (marking, Edit, `ledger.taken_book`), My bets by book, scorecard by book, Coverage column | Live |
| Settlement: DraftKings' soccer SGP rule; everything else matches FanDuel (table below) | Live |
| Game pages' price tables (NHL, soccer 3-way): FanDuel and DraftKings side by side, each with its EV | Live (Oct 13) |
| Anytime-TD grading counts return, defensive and fumble-recovery TDs (both books) | Live (Oct 13) |
| "I placed this" on a slip goes to the book whose quote was typed (the better one if both) | Live (Oct 13, from the real-mode rehearsal) |
| **Open:** Mike's DraftKings quotes (0 of ~40); one real tap of a 3+ leg same-game slip's Open in DraftKings | To-do list |

How it was built, day by day:
- **Day 1:** game lines at both books (`books.py`; every game-line evaluator takes `book`).
- **Day 2:** props at both books (NFL, NBA, NHL with DraftKings' points, soccer scorers), one bet across spellings,
  moved numbers capped at lean, trackers record the book.
- **Day 3:** links per book (`links.attach_card`), Open in DraftKings (`web/lib/draftkings.ts`, `BookLink`), the
  iPhone test page (More > Settings > Test Open in DraftKings), each bet's book, My bets by book.
- **Day 4:** parlays per book: `links.attach_dk` at export (DraftKings' price and link on every leg; a rung it
  doesn't hang moves to its nearest by chance, within 20% of the number and 10 points of chance: Mike, "DK would
  have either 220 or 230"); each slip's DraftKings side and price box; DraftKings quotes saved as `<sgp_id>~dk`
  (`quotes.book`, migration 0009), their own fun-ledger rows graded from DraftKings' legs;
  `fun_ledger.quote_model(book=...)`; the Build tab's switch (exact legs only; `custom-...~dk`); lock alerts.
- **Day 5:** the house-rules check and DraftKings' soccer rule in grading (`fun_ledger._dk_soccer_void`), the
  scorecard by book (`golive.by_book`), Coverage's DraftKings column, a rehearsal in the preview.
- **Bugs found and fixed on Oct 12:** day 1 published `offers.other_*` with no migration, so every publish failed
  2:02-7:05 PM ET (migration 0008; a test now checks every published column); the card JSON dropped `book`, so the
  app showed every card bet as FanDuel's; anytime-TD parlay legs had no FanDuel link, and the first fix let a TD
  outcome stand in for a missing yardage rung (now 0.5 legs only, and player legs only in their stat's markets).

## What we already know (checked Oct 12, free)

**DraftKings lags the sharp market at least as much as FanDuel.** The morning-price study (`betlab backtest
lag`, 44 NFL games, Sep 27 to Oct 11), the same sides measured for each book against the sharp close:

| Morning EV | FanDuel sides | FanDuel CLV | DraftKings sides | DraftKings CLV |
|---|---|---|---|---|
| 0%+ | 62 | +0.9% (SE 0.6), 68% beat | 80 | +1.2% (SE 0.4), 81% beat |
| 2%+ | 19 | +2.3% (SE 1.0), 84% | 20 | +3.1% (SE 0.8), 85% |
| 3%+ | 5 | +1.5% | 9 | +4.6% (SE 1.3), 89% |

DraftKings' average margin on these lines is also a little smaller (−5.5% vs −6.1% EV on every side). Small
samples, but two lagging books means more qualifying bets, and the lag thesis gets tested twice.

**Coverage in our odds pulls (same pulls, no extra credits: DraftKings is already in `odds_api.bookmakers`):**

| Market | FanDuel | DraftKings |
|---|---|---|
| NFL, college, NHL game lines | all games, links | all games, links |
| NFL props (main, alt ladders, anytime TD) | all | all, more alt rungs |
| NHL props | shots, saves, scorer | shots, saves, scorer, **points** (FanDuel's feed has none) |
| NBA props | from Oct 20 | expected the same; confirm on the first pull |
| Soccer 3-way | all matches | fewer matches when we pull (MLS 2 of 17, La Liga 13 of 24): posts later |
| Soccer props | shots, on target, scorer, assists, score or assist | scorer only (plus cards, which we don't use) |
| Soccer goals and both teams to score | yes | yes |
| College basketball | from the Nov 2 opener (paid, Oct 15) | priced at both books like the other game lines |

**Links:** the feed gives every DraftKings outcome a betslip link (`sportsbook.draftkings.com/?outcomes=<id>`).
Mike's iPhone test (Oct 13, rounds 1-2): from the home-screen app the plain web link opens DraftKings' app (unlike
FanDuel's, which needed its app scheme), and the feed's link lands the bet in the betslip; `dksb://` and
`dksb://sb/addbet/<id>` work too, `dksb://<host>/?outcomes=` only opens the app. One host serves New York.
Round 3 (Oct 13, two winner legs from different games): one `outcomes` parameter with the ids joined by `+` puts
both in one betslip, bare (`I`) or encoded as `%2B` (`J`); `,` and repeated parameters don't. `dkHref` sends `%2B`,
and only when every leg has a DraftKings link.

## The edge cases, and the rule for each

**1. Same bet, different line.** FanDuel −3.5 and DraftKings −3, or a player's receptions at 4.5 vs 5.5.
- Rule: price each book at **its own number** against the sharp no-vig chance **at that exact number** (as
  today: `edge.blend_prob`, props at FanDuel's point). Never translate a price across numbers.
- The two are different bets with different chances. Pick the one with the higher EV, not the better-looking
  price. Where the sharp book hangs only one of the two numbers, the other book's offer uses the moved-number
  rule we already have for the NBA (`cards/nba.py`: a lean, never a pick, until moved-number CLV says otherwise).

**2. Same line, different price.** Best EV wins, which at the same number is simply the better price. A tie
goes to FanDuel (Mike, Oct 12).

**3. One pick per bet, never both books.** The same side of the same game (or the same player and stat) at
both books is one bet: logged once, at the book that qualified first (rule 4 of CLAUDE.md: the ledger keeps
the first qualifying price). Correlated groups (side, total, a player's props) span both books, so one pick
per group per game, whichever book.

**4. A better price appears later at the other book.** The ledger row stays as logged. The app shows "now
better at DraftKings −105" as information (and the alert names the book), but the paper record is never
rewritten. Real bets record the book and price you actually took.

**5. A market only one book posts.** Each book's offers exist only where it posts: FanDuel alone for soccer
shots, on target and assists; DraftKings alone for NHL points (new: the NHL props tracker and model get a
points stat at DraftKings). Nothing is inferred for a book that doesn't post.

**6. Alt ladders and duplicate rungs.** A rung can sit in a book's main market and its alternate ladder at
one price (the FanDuel link problem of Oct 1): the same matcher rules, per book. A rung only one book
offers is that book's alone.

**7. The sharp reference must exclude the book being judged.** Today the consensus fallback excludes
FanDuel (`market.reference_books(..., target_book)`). For DraftKings it must exclude DraftKings, and neither
book may ever be the "sharp" price for the other. Pinnacle, LowVig and BetOnline stay the sharp books.

**8. Player names differ by book** ("Jr.", accents, nicknames). Per-book name matching through the same
`players.match` and `espn_soccer.match_player`, tested on each book's real names before go-live.

**9. Settlement rules can differ.** Before go-live, check each book's house rules for: player props when the
player doesn't play (void vs loss), NHL overtime and shootouts (totals, puck lines, props), soccer 90 minutes
vs extra time, anytime TD (which TDs count), pushes on whole numbers, and void legs inside parlays (FanDuel
drops the leg and reprices; confirm DraftKings). Where a rule differs, the grader settles per book
(`book` column), and the difference goes in this file.

**10. Timing and closing lines.** CLV stays against the sharp close, the same for both books. Our pre-game
pulls already fetch every book at once, so no new pulls. Each book's own move (did it move toward the
sharp price?) is tracked per book, for the lag study.

**11. Parlays are book-specific.** A same-game parlay can only be placed at one book, legs and price.
- Each fun slip and SGP+ ticket is built twice, from each book's legs and prices, where both post the legs.
  A leg one book lacks gets that book's next-best rung or the slip isn't offered there.
- DraftKings prices same-game parlays its own way: its quote model needs **its own typed quotes** (none yet).
  Until about 40 exist, DraftKings uses FanDuel's bands as a stand-in, labeled as such.
- The app shows both books side by side (Mike, Oct 12): each book's legs, prices, likely quote and link.
- DraftKings' multi-game same-game parlay product may combine games differently from FanDuel's SGP+; confirm
  which combinations it allows before building DraftKings tickets across games.

**12. Real money across two books.** Units stay units (Oct 12 decision). The 5-unit daily cap and the parlay
budget count both books together. Each real bet records its book; My bets shows each book and both.

**13. Links and the iPhone app.** Every pick, lean and leg gets the link of the book it's priced at. You test
DraftKings' links on the iPhone the way you tested FanDuel's (a "Test Open in DraftKings" page in Settings,
like FanDuel's), before Oct 18.

**14. Alerts and the app say the book everywhere.** Alerts carry both prices, the better first (Mike, Oct 12):
"NFL pick: Bills +3.5 · DraftKings −105 · FanDuel −110". The Home feed, game pages, My bets and the scorecard
label the book, and a pick shows the other book's price when it posts the bet.

**15. Results by book.** The scorecard and Results tab split by FanDuel, DraftKings and both, so each book's
lag edge is judged on its own record. The record before Oct 12 is FanDuel-only and stays labeled that way.

**16. Things we won't do.** No betting both sides across books (middles and arbitrage get you limited and
aren't the edge we're testing); no boosts or promos (not in the feed); no DraftKings card-market props.

## Build order (as it went; Mon Oct 12, 2026, 8:00 PM ET)

The first table counted from "Mon Oct 13"; Oct 12 was the Monday, so Oct 18 is a **Sunday** (a full NFL slate).
All five build days happened on Oct 12; the week is for watching both books live.

| Day | What | Done when | Status |
|---|---|---|---|
| **Mon Oct 12** | Days 1-5 (above) | Both books priced, linked, quoted and graded; rehearsed in the preview | **Done** |
| **Tue Oct 13** | Mike's iPhone test, done: the web link opens the app with the bet (buttons unchanged), and parlays open as one link (I, J). Also: price tables at both books, TD grading, a real-mode rehearsal at both books. First European cup matchday; first DraftKings paper pick (Kane to score). | DraftKings buttons open the app; first DraftKings quotes in the ledger | **Done** except the quotes |
| **Wed Oct 14 - Fri Oct 16** | Watch both books live (the cups, Thursday night football): DraftKings slips, quotes, grading; DraftKings in the game page's price table; return/defensive TDs in anytime-TD grading. | DraftKings slips graded correctly | Planned |
| **Sat Oct 17** | The weak-spot review across both books; a real-mode rehearsal at both books. | Review posted | Planned |
| **Sun Oct 18** | **Live.** Real money at both books. | First real marks graded Mon Oct 19 | Planned |

Free throughout: no new odds pulls (DraftKings is already in every pull).

## What you do (Mike)

1. ~~DraftKings links on the iPhone~~: done Oct 13 (A, B, E, F, I, J worked). Worth one real tap on a slip's new
   Open in DraftKings button to confirm a 3+ leg same-game parlay lands too.
2. **From Tue Oct 13: type DraftKings' SGP prices** in each slip's DraftKings box, or build at DraftKings on the
   Build tab. About 40 give DraftKings its own quote model; looking up a price doesn't need an account.
3. **Sun Oct 18: open your DraftKings NY account** with a deposit limit, as with FanDuel.

## House rules: where DraftKings settles differently (checked Mon Oct 12, 2026, 8:00 PM ET)

From DraftKings' house rules (the Aug 1, 2024 version filed with the Massachusetts Gaming Commission) and its support
pages, against how BetLab grades (FanDuel's rules):

| Rule | DraftKings | FanDuel | What BetLab does |
|---|---|---|---|
| Pre-game same-game parlay, a leg void or push (football, basketball, hockey) | Leg removed, parlay repriced | Same | Unchanged: the leg comes off at its fair chance |
| **Pre-game soccer SGP, a game leg void or push** | **Whole SGP void** (only a player who didn't take part is removed and repriced) | Leg removed, repriced | `fun_ledger._dk_soccer_void`: a DraftKings soccer slip with a game leg off is void |
| NFL player props, player inactive or no snap | Void | Void | Unchanged |
| Anytime TD | The player with the ball in the end zone (not the passer) | Same | Unchanged; returns and defensive TDs aren't counted by our grader at either book (a follow-up) |
| NHL overtime and shootout | Included; a shootout adds one goal to the winner and the total; player stats exclude the shootout | Same | Unchanged |
| Soccer | Regular time (90 plus stoppage) unless the market says otherwise | Same | Unchanged; knockouts (from February) need a check for extra time |
| Whole-number lines landing exactly | Push, refunded | Same | Unchanged |

Rules change; recheck before February (soccer knockouts) and whenever a DraftKings bet grades unexpectedly.

## Day 2 notes (Oct 12 evening)

- **Rule 1 in practice:** DraftKings' prop number differs from Pinnacle's on 41% of NFL lines (FanDuel 11%), so most
  DraftKings prop value is at moved numbers, which are leans (both books, Mike). The leans are logged; their CLV
  decides whether moved-number props can ever be picks.
- **Rule 8:** players are matched across books by roster id (NFL, NBA), else by normalized name plus
  `config/player_aliases.yaml`; the bet keeps FanDuel's spelling. Soccer scorers match DraftKings' names to Pinnacle's
  (`espn_soccer.match_player`). Oct 11's NFL pull: every name matched at both books.
- **Trackers:** `nhl_prop_lines.csv` and `nba_prop_lines.csv` have a `book` column (one row per book; FanDuel's ids
  unchanged; summaries stay FanDuel's and count DraftKings' lines). NHL points are tracked from DraftKings.
  Kept FanDuel-only on purpose: `prop_lines.csv` (the Games tab's read record, at FanDuel's line) and
  `soccer_prop_lines.csv` (DraftKings posts only the scorer there). The NBA fun tickets and the NHL game page's
  lines stay FanDuel's until days 3-4 (the page adds DraftKings' points where FanDuel has none).

## Mike's decisions (Oct 12)

1. **Ties at the same EV go to FanDuel.**
2. **DraftKings picks on paper from Oct 13:** yes, so a week of DraftKings record exists before real money.
3. **Fun tickets: both books side by side**, each with its own legs, prices, likely quote and link.
4. **Alerts carry both books' prices** ("Bills +3.5: DraftKings −105 · FanDuel −110"), the better one first.
5. **(Oct 12 evening) A prop at a moved number is a lean at both books**, not only DraftKings.
