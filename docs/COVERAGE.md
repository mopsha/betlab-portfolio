# Market coverage

What BetLab does in each market, side by side. **Update this table in the same session
whenever a market gains or loses a piece** (CLAUDE.md, "Before you stop"). The page's **Markets** tab
shows this table (`betlab export-page` reads this file), so the next sync updates it.

Last updated: 2026-11-06, 12:10 PM ET (NFL game pages gain the Notebook: story, what changed, the pattern, the bet; words only)

| Market | Status | DraftKings | Picks: game lines | Picks: ML | Picks: props | Analysis: game lines | Analysis: ML | Analysis: props | Fun parlays | Credits/mo | Backfilled seasons | Ongoing ML |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NFL | Live | ✓ lines, props, parlays | ✓ | ✓ | ✓ | ✓ (and the Notebook, Nov 6: words, no price) | ✓ | ✓ (ML v1, no weight; matchup notes off Oct 19, script lines off Oct 28) | ✓ (no repeated players; script read off Oct 19) | ~2,800 | 2012–25 (props 2023–25; lines 2024–25) | ✓ (mid-Nov) |
| College football | Live | ✓ lines, parlays | ✓ | ✓ | ✗ (NY) | ✓ | ✓ | ✗ (NY) | ✓ lines only | ~200 | 2014–25 | Tracking |
| NBA | Oct 20 | ✓ lines, props, parlays (Oct 20) | ✓ | ✓ | ✓ | ✓ team model + who's out, tracked | ✓ team model, tracked | ✓ | ✓ (early and late slices with a regular and a likelier SGP+; a lone or Knicks game gets its own slips, Oct 21) | ~2,400* | 2024–26 (lines 2025–26) | ✓ (mid-Nov) |
| College basketball | Nov 1 | ✓ lines, parlays (card at FanDuel, DraftKings and Novig, Oct 30) | Nov 1 | Nov 1 | ✗ (NY) | ✓ spreads, totals (tracked) | ✗ | ✗ (NY) | ✓ lines only | ~2,000 | 2021–26 | Tracking |
| NHL | Live | ✓ lines, props (points only here), parlays | ✓ | ✓ | ✓ shots, saves, scorer; points (DraftKings) | ✓ | ✓ | ✓ | ✓ + shots | ~800* | 2018–26 (props 2020–26, lines 2025–26) | ✓ (props now) |
| Soccer (top 5 + MLS) | Live | ✓ 3-way, goals, BTTS, scorer, parlays (a pushed game leg voids its SGP) | ✓ goals, both teams to score (market-only, from Oct 12) | ✓ 3-way | Tracking (shots, on target, scorer, assists) | ✓ shots, lineups, goals read (tracked), moneyline read (Oct 15) | Planned | ✓ shots ML (no weight) | ✓ ten kickoff-cluster slices (opens in FanDuel or DraftKings) | ~2,400* | 2018–26 (players 2019–26) | ✓ shots |
| European cups (Champions, Europa, Conference League) | Live (Oct 13) | ✓ as the leagues | ✓ goals, both teams to score (market-only) | ✓ 3-way | Tracking (shots, on target, scorer, assists) | ✓ shots, lineups (players with domestic history) | Planned | ✓ shots ML for players from the six leagues (no weight) | ✓ (with the leagues' slices; cup days 12:45 and 3 PM) | ~500 a cup week (Oct 13: ~9 a match) | ✗ (ESPN scores, our own close) | ✓ shots |
| UFC | Oct 24 (UFC 333) | ✓ moneyline, total rounds | ✓ total rounds (market-only; not at FanDuel) | ✓ (market-only) | ✗ (none in the feed; no edge found, Oct 23) | ✓ fight pages: tale of the tape, last five fights, class base rates, DraftKings' method/distance as chances, same-fight parlay fair prices | ✓ fight model (win, distance; tracked, no weight: loses to DraftKings) | ✓ DraftKings' method, distance, rounds (ESPN; tracked per card) | ✓ one parlay per card segment | ~10 a card (+ re-pulls on card changes) | ESPN results and fight stats 2021–26; prices only the last ~5 events (Odds API backfill in Nov) | Tracking (ufc_lines.csv) |
| MLB | 2027 | Planned | Planned | Planned | Planned | Planned | Planned | Planned | Planned | — | ✗ | Planned |
| WNBA | May 2027 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ |

**Key**
- **Novig** (Oct 22): the sports exchange is a third book for game lines in every league but college basketball (its
  card picks FanDuel or DraftKings itself), priced against the same sharp market with the dollars available shown;
  props stay at FanDuel and DraftKings. Soccer's Novig prices (3-way, totals) come from Novig's free public
  catalog (`sources/novig.py`); the Odds API carries the rest. **Parlays from Oct 28:** every same-game slip and SGP+
  ticket, and the Build tab, gets Novig's exact price from its free parlay pricer (`novig_parlays.py`), in both apps.
  The game pages' book tables (NHL lines and props, NBA player lines, soccer's 3-way) show Novig's live price and EV
  too (`novig_parlays.attach_tables`).
- **Picks:** FanDuel or DraftKings lagging the sharp books (or, for NHL props, the other books' consensus), the
  better book per bet; game lines and props from Oct 12. A prop at a number the sharp books don't hang is a
  lean at most. Paper until Oct 18.
- **CLV:** only real closes count (Oct 13): every open prop bet gets a closing look in the last tick before the start,
  and a close from the bet's own pull is left out of the scorecard.
- **Model weight in picks:** none. College FB moneylines went market-only on Oct 9 (they were the last, at 22%).
- **Analysis:** our own read (Games tab), tracked against the market. It reaches picks only if
  it beats the close.
- **Tracking:** every line is logged, but no machine-learning model is planned yet.
- **Ongoing ML:** a model that keeps learning from logged lines.
- **DraftKings:** Mike's second book from Oct 12 (docs/DRAFTKINGS_PLAN.md): every market is priced at both books and
  each bet goes to the better one; parlays show both books, and DraftKings' parlay quotes teach its own quote model.
- **NY:** New York bans college player props.
- **\*:** estimate. The others are measured from the credit log.

**Books:** every ✓ above is FanDuel. From Oct 12, game lines (NFL, college football, NHL, NBA, soccer 3-way,
goals and BTTS) and props are priced at DraftKings too, each bet at the better book; its links and parlays open
in its app (Oct 13), and the game pages' price tables show both books (docs/DRAFTKINGS_PLAN.md). DraftKings adds NHL points props; its feed has no soccer shots,
on-target or assists props.

**Never ✓ (by design):** college props (New York law).
**Next up:** the NHL
props market layer once lines accumulate, MLB in February.
