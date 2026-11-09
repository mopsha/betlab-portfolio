# Mac handoff: everything from the Windows session of Oct 24, 2026

For the Mac session that keeps the iPhone app (`ios/`) in step with the web app. Read this top to bottom, then work the
port list in order. The to-do item is `c-mac-port-oct-24-s-web-changes-to-the-iphone-app-` (`betlab todo list -v`).

## Status, Oct 24 11:50 PM: what's left for the iPhone

**Already on the iPhone (Mac commits today):** the tracker fixes (2.1), the Leg alerts switch (2.2), Stats and
achievements (2.3), Share (2.4), the hub and wall with only live bets and wins (2.5), Ask BetLab over the bearer route
(2.6), the daily cap off My bets, themes, team-color Games cards and game pages, soccer club logos, book icons.

**Left, in this order:**
1. **+ Add a bet from a screenshot** (2.8): PhotosPicker, shrink to a JPEG under ~1600px, POST
   `{"image": "data:image/jpeg;base64,..."}` to `<webURL>/api/slip` with `Authorization: Bearer <access token>` (the proxy
   accepts it there since `292d1ca6`). The answer is `{draft, placed_at}` (or `{error}`; 503 = no key).
   Show the confirm form (book, odds before boost, wager $, unit $ default 5, boost %, bonus, placed time, each leg's
   wording with its matched game and Remove), then insert the bets row yourself: port `betRow` from `web/lib/slip.ts`
   (kind custom, sgp_id `custom-fd-snap-<8 chars>`, units = wager / unit, the label, games with game refs).
   The reader is Claude Haiku 5.5 now (no fallback): a 422 says the slip couldn't be read.
2. **Player cards** on Stats (2.8): `web/lib/players.ts` + ESPN search headshots.
3. **Use a promo** (2.8): the terms form opening Build's promo mode on that game; add the max-odds term.
4. **My bets' top** (2.7) if not done: the P/L alone, large; Grade now and + Add small in the corner.
5. Then **Siri** ("How's my parlay?" through the same chat endpoint), Live Activities and widgets.

**Done on the Mac, Oct 25 (12:15 AM):** 1 (+ Add from a screenshot; the proxy's bearer check now really covers
`/api/slip`), 2 (player cards, then redesigned as trading cards on Mike's ask), 3 (Use a promo in Build's toolbar,
max odds), 4 (the P/L alone, Grade now and + in the corner), and Siri (App Shortcuts over `/api/chat`). Left: Live
Activities and widgets (a widget extension target, an App Group, and the worker pushing Live Activity updates).

**Then, Oct 25 (12:45 AM): the ban list** (Mike's idea, across all three): `user_settings.bans` (migration 0017,
applied), one matcher in `src/betlab/bans.py`, `web/lib/bans.ts` and `ios/BetLab/Bans.swift` on
`tests/fixtures/bans.json`, team names in `teams.json` (one file, three copies; `tests/test_bans.py` checks they match).
Worker `859e9123` (running), web `5390df18`, iPhone build 1160. To-do `c-ban-list-first-use` checks it after the first ban.

## 0. Start

1. `git pull --rebase` (the bot commits to `main` every 15 minutes).
2. Nothing on the backend needs you: the worker and the web app are deployed and running (`0183d2d5` through
   `3943398c`). This is iOS work, plus one optional small web change (section 2.6).
3. Build and test as usual: `xcodebuild ... test`. Run the web tests too after touching any shared fixture
   (`cd web && npm test`) and the Python ones (`.venv/bin/python -m pytest`).
4. **Before pushing any `web/` change, run `cd web && npx tsc --noEmit -p . && npm test`.** Railway's web build runs
   the type check: `fba2eaf9` (a null `commence_time` into the lock helpers) failed it, and the site stayed on the
   4:26 PM build for four hours (fixed in `89ecd103`). Also check `gh run list --repo mopsha/betlab --limit 3` after a push.
5. Don't push a `src/` change in the minutes before a fun slice's lock (it redeploys the worker); iOS-only commits are
   safe any time.

## 1. Already live: nothing to port

| What | Where | Notes for the app |
|---|---|---|
| **Leg push alerts** (Mike's #23) | `src/betlab/leg_alerts.py`, `live_legs.py`, `worker.leg_alerts_tick` (every minute) | Pushes reach APNs devices already (`alerts._send`). One push per event, each once ever: *Leg hit*, *One leg left*, *Leg lost* (then silence), *Winner*; singles only won or lost. Payload `{title, body, url: "/bets", tag}`; `tag` becomes `apns-collapse-id`. A bet's first look is silent. Off per account with `user_settings.notify = {"legs": false}` (section 2.2). |
| NBA absences crash | `src/betlab/nba_reads.py` (`d961b3bc`) | The NBA game pages' who's-out list is back. |
| Bets entered by Claude | `bets` rows, kind `custom` with `games: [{matchup, game_ref, legs}]` | Game refs now: `ncaaf:<espn id>`, `ufc:<event>:<fight>`, `<league>\|Home\|Away\|<kickoff>` for soccer. A boosted bet keeps the book's price with `boost` in percent; `bonus: true` for bonus bets. Nothing to change if the app already reads `games`. |

## 2. Port list (in this order)

### 2.1 Tracker fixes in `ios/BetLab/Live.swift`: do these first (wrong verdicts and wrong alerts)

**a. A leg's team goes to the side its name matches best.** On Oct 24, "LSU Tigers ML" at Auburn Tigers read as
Auburn: both are "Tigers", the nickname rule matched both, and home was checked first. LSU led 10-3 and the leg showed
"Down 7" with Auburn's logo. Web fix: `web/lib/live.ts` `teamMatch` / `sideOf` (commit `c633848f`); Python twin
`src/betlab/live_legs.py` `team_match` / `side_of`.

- Replace `isTeam`'s bool with a graded match, `teamMatch(ours, side) -> Int`:
  `3` the full name, the abbreviation or an alias; `2` the nickname / last name (the last word, not a generic word);
  `1` a shared strong word (4+ letters, not generic) both ways; `0` none. Keep `isTeam = teamMatch > 0`.
- `sideOf(ours, game) -> "home" | "away" | nil`: compare `teamMatch` against home and away; the higher wins; **a tie
  (neither, or both alike) names no side** ("Team not found").
- In `judge` (around line 374) use `sideOf(team, g)` for moneylines and spreads, and for the leg's logo
  (`team = side == "home" ? g.home : g.away`).

**b. Spread text** (around line 394): `"+2.5: covering by -13.5"` read like it was covering (Mike, Oct 24). Now:
`m > 0 ? "Covering by \(m)" : m < 0 ? "Short by \(-m)" : "Right on the number"`, where `m = lead + point`.

**c. Test against the shared fixture.** `tests/fixtures/live_legs.json` is the contract all three trackers must read
alike: `parse` (label -> parsed leg, `null` when unreadable) and `judge` (label + game state + optional box ->
expected `status`, `current`, sometimes `text`). Copy it into the test bundle (or read it by path from the repo) and add
a `LiveTests` case that runs every entry through `parseLeg` and `judge`. The two Tigers cases and the Akron "Short by
0.5" case are the ones this fix must pass. Field names in the fixture's games: `home`/`away` are `[name, abbr,
score]`, `winner` for UFC.

### 2.2 Leg alerts switch in More > Settings (`MoreView.swift`, ~line 145-201)

- A toggle "Leg alerts on my real bets", on by default, under the pick alerts.
- Read `user_settings.notify` (jsonb, default `{}`); on = `notify["legs"] != false`.
- Save by upserting `{"notify": <existing notify with legs set>, "updated_at": now}`, **keeping other keys** in
  `notify`. Web reference: `web/lib/actions.ts` `setLegAlerts`, `web/components/LegAlerts.tsx`.
- Footnote text: "A notification when a leg hits, when one leg is left, when a leg loses, and when a bet wins."

### 2.3 My bets > Stats tab (Mike's #40 personal stats and W29 achievements)

A fifth view in `MyBetsView` between Record and Prices, over the same bets as Record (`recordBets`: real bets once
real money started). Port the pure logic first (new `Stats.swift`, beside `BetMath.swift`), then the view.

- **Logic** (`web/lib/stats.ts`), every grouping fed through the existing record function so units, ROI and CLV
  match the Record tab:
  - `sportOf`: a single's league (all soccer leagues -> "Soccer"); else the sports of its games' refs (more than
    one -> "Multi-sport"); else the ticket's `sport`; else **guess from the text** (`guessSport`: a title word NBA/NHL/
    NFL/college football/college basketball/UFC/soccer, then prop wording: passing/receiving/rushing yds, receptions,
    anytime/first TD -> NFL; shots on goal, saves -> NHL; shots on target, to score or assist -> soccer; rebounds,
    threes, "N+ points", "over X points/assists" -> NBA; then NBA nicknames). Without the guess, 11 of Mike's bets read
    "Other".
  - `typeOf`: Single / Parlay, 2-4 legs / Parlay, 5+ legs (legs = max of `legs.count` and the games' legs).
  - `bandOf` (price): Favorite (-111 or shorter), Near even (-110 to +150), Underdog (+151 to +400),
    Long shot (+401 to +1000), Lottery (+1001 or longer).
  - `moneyOf`: Bonus bets / Boosted cash / Plain cash. `weekdayOf`: the Eastern game day.
  - `timeline` (cumulative units per day with a settled bet), `streaks` (current run, longest winning run; pushes and
    voids neither extend nor break), `extremes` (biggest win, worst loss; a bonus loss is 0 so never the worst).
- **Achievements** (`web/lib/achievements.ts`): 15 badges computed from the settled bets in order, never stored. Each
  has `icon, title, how`, the **bet and Eastern day that earned it**, and progress for locked count badges. Copy the
  list exactly (ids, titles, thresholds): first win; +500; +1000; 5+ legs; 8+ legs; boosted win; bonus win; 3 in a row
  (progress = best run); UFC win; soccer win; wins in 4 sports; wins at 2 books; beat the close 10 times; a finished
  Mon-Sun week up with 5+ settled; up 10 units (progress = best cumulative, floored). Earned first (newest first),
  then locked in list order.
- **View** (`web/components/StatsView.tsx`): pills (P/L, ROI, streak "3W"/"2L", best run, badges N of 15); a units
  line chart (Swift Charts `LineMark` + `AreaMark`, green above zero / red below, dashed zero rule); Biggest win /
  Worst loss cards (title = "N-leg parlay · <matchup>" for parlays, else the label); then record tables: By sport,
  Singles vs parlays, By price, Cash/boosts/bonus bets, By book, By day of the week; then a badge grid (locked ones
  dimmed, icon greyscale, "1 of 3" progress or "Locked").
- **Tests:** port `web/tests/stats.test.mjs` (sport/type/band/money, timeline/streaks/extremes, achievements,
  the guesses) into `MyBetsTests`.

### 2.4 Share on every bet card (Mike's W13)

The web draws the picture at `/api/share/<bet_id>`, but that route signs in by the web's cookie session, which the
app doesn't have. **Render it natively instead**: port the card model and draw it with SwiftUI's `ImageRenderer`,
then hand the image to `ShareLink`.

- **Card model** (`web/lib/share.ts` `card()`): status WON / LOST / **ONE LEG AWAY** (lost, 2+ legs, exactly one
  lost and none open) / CASHED OUT / OPEN; a tone (win green, loss red, open accent); title ("8-leg parlay" or the single's
  label); price with the boosted price when boosted (`+978 -> +1271`: profit times 1 + boost/100); every leg (up to 10,
  then "+N more legs") matched to `leg_results` **in order, so repeated labels like "Over 2.5 goals" each get their own
  result**, with its value ("3-1"); headline = settled units ("+11.28u") or "to win 11.28u"; detail = "1u bonus bet" /
  "2u · 50% boost", or "7 of 8 hit · ..." when one leg away; book and date.
- **Picture:** 1080x1350, dark (#0d0f13), BetLab wordmark and "FanDuel · Oct 24, 2026" top, the status large in its
  tone, title and price, a rounded panel of legs with a colored dot each (won green, lost red, void grey, open dark),
  headline bottom-left large, detail bottom-right. The web route (`web/app/api/share/[id]/route.tsx`) has the exact
  sizes and colors.
- A "Share" button on each bet card (open and settled). Tests: port the card assertions in
  `web/tests/stats.test.mjs` (one leg away, repeated legs in order, boosted price).

### 2.5 Home's game-day hub, and the wall

Web: `web/components/GameDay.tsx`, `web/components/Wall.tsx`, `web/lib/gameday.ts`, shown in `web/app/page.tsx`.

- **Hub** at the top of Home's Today view when there's an open bet or a lock still to come today: a "Game day" header
  with "Open the wall"; one compact card per open bet (name, leg segments, hit/total or Live/Won/Lost, the game in
  progress with logos and score/clock, "+N live" when more, and the next leg it needs with its text), live games
  first; then "Parlays lock in" with countdowns to today's next 4 locks (h:mm:ss, the next one accented) and
  "+N more later today". Use `TimelineView(.periodic(from: .now, by: 1))` for the countdown. **No draft ticket
  prices** in the hub (Home lists a parlay only once it locks, Oct 10). Hide the old one-line "Next lock" when the
  hub shows. Bet names (`betName`): "4-leg parlay +940", or the single's leg "Michigan Wolverines ML +250".
- **Mike, Oct 24 night: "just show alive and wins".** The hub shows only bets still alive and wins; a lost bet leaves
  it (it stays in My bets), and with nothing alive and no lock left the hub doesn't show (`9004668a`). The wall drops a
  bet once it's won or lost and a game with no live bet left (`b5aab204`).
- **Wall** (iPad / landscape, or skip on phone): one tile per game with money on it across all open bets, its score
  strip and every leg on it labeled with its bet's name; live first, then upcoming by start, finished last
  (`wallTiles`).
- Both read the same live data as the My bets tracker (`Live.swift`), so do 2.1 first.

### 2.6 Ask BetLab chat (Mike's W22, rated essential)

Web: `web/lib/chat.ts` (Claude `claude-sonnet-5-5` at low effort, the server-side refusal fallback on, four read-only tools: open bets
with live legs, today's board, one game's details, the record), `web/app/api/chat/route.ts`, `web/components/Chat.tsx`,
More > Ask BetLab. It needs `ANTHROPIC_API_KEY` on the web service (Mike's to-do), and it waits until then.

- The route signs in by cookie, like every web page. For the app, **add bearer-token support to `/api/chat`** (a small
  web change; whichever session gets there first): when the request has `Authorization: Bearer <supabase access
  token>`, build the Supabase server client with that header so the same row-level security applies; keep the
  cookie path for the web. Then the app POSTs `{messages: [{role, content}]}` and shows `{answer}` or `{error}`
  (503 = waiting for its key).
- **App view:** a chat screen under More: suggestion chips when empty ("What's the best bet tonight?", "How are my
  open bets doing?", "How am I doing on real money?", "Build me a 3-leg parlay from today's board"), bubbles,
  a typing indicator, "New chat". Answers are plain text with **bold**, "- " lists and markdown links to
  `/games/<league>/<id>`: open those as the app's game page (`web/lib/chat-format.ts` has the rules; only app paths
  and https links become links). Keep the conversation on the device for the session only.
- **Siri (W11)** comes after: an App Intent "How's my parlay?" that asks this same endpoint.

### 2.7 My bets' top (Mike, Oct 24 night)

- The pills at the top of My bets (record, P/L, CLV, today at risk, fun bucket) are gone: only the **P/L**, large
  (a small "REAL P/L" label over the number, ~52pt, green/red). The record stays on the Record and Stats tabs.
- **Grade now** moves out of the way: a small button in the header's top-right corner; its status goes into the
  accessibility label/tooltip, and only "Grading…" or an error shows. Web: `web/app/bets/page.tsx`,
  `RefreshControl compact`.

### 2.8 Night of Oct 24: player cards, Use a promo, + Add from a screenshot

- **Player cards** (W21) on Stats, above the record tables: `web/lib/players.ts` (pure: player legs matched in order to
  `leg_results`, counts, hit rate, top stat, gold/silver/bronze at 70%/50% on 3+ graded legs) and
  `web/components/PlayerCards.tsx`. Headshots: ESPN's search
  `https://site.web.api.espn.com/apis/common/v3/search?query=<name>&limit=5&type=player` (`items[].headshot.href`,
  league match: nba/nfl/nhl/wnba, soccer by sport); cache a day. Test cases in `web/tests/stats.test.mjs`.
- **Use a promo:** a form (type, %, game, max wager, max extra winnings, min/max odds) that opens Build's promo finder on
  that game. On the iPhone, open Build's promo mode with those values set (`Builder.swift` has the finder); max odds
  is a new term (`promoFits` in `web/lib/builder.ts`).
- **+ Add from a screenshot:** the web route `/api/slip` needs the cookie session, so on the iPhone either add bearer auth
  there (as for chat, 2.6) or call the API from the app the same way. The pure part to port is `web/lib/slip.ts`
  (leg -> game matching, game refs per league, the saved row, Eastern time); the reading prompt and JSON schema are in
  `web/lib/slip-read.ts` (Claude Haiku 5.5, no fallback). Tests: `web/tests/slip.test.mjs`, `slip-read.test.mjs`. iOS can use PhotosPicker and send
  a JPEG under ~1600px.

## 3. Done when

- Tracker fixes pass the shared fixture in `LiveTests` (and `npm test` / pytest still pass if you touched the fixture).
- Settings has the Leg alerts switch, saving `notify.legs` without dropping other keys.
- My bets has Stats with the tables, chart and badges, matching the web on the same account.
- Every bet card shares a picture.
- Home shows the hub on a game day.
- Chat works from the app once the key is in and the bearer route exists.
- Update `ios/README.md`, this file's to-do (`betlab todo done --id c-mac-port-oct-24-s-web-changes-to-the-iphone-app-`),
  and `docs/IDEAS.md` (steps 4-6: "iPhone too").
