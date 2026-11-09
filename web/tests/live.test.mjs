import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { loader } from "./load-ts.mjs";

const L = loader()(new URL("../lib/live.ts", import.meta.url));
const BETS = loader()(new URL("../lib/bets.ts", import.meta.url));
const LB = loader({ "server-only": {}, "./bets": { isSettled: () => false, refTime: BETS.refTime, refGameId: BETS.refGameId }, "./data": {} })(new URL("../lib/live-bets.ts", import.meta.url));

const side = (name, abbr, score) => ({ name, abbr, score });
const game = (state, home, away, sport = "nfl", extra = {}) => ({ key: `${sport}:1`, sport, espnId: "1", state, detail: "Q3 4:12",
  start: "2026-10-23T20:00:00Z", home, away, ...extra });

test("leg labels from every sport parse", () => {
  assert.deepEqual(L.parseLeg("A.J. Brown 60+ receiving yds"), { kind: "prop", player: "A.J. Brown", stat: "receiving yds", side: "over", need: 60, point: 59.5 });
  assert.equal(L.parseLeg("Joel Embiid over 7.5 rebounds").need, 8);
  assert.equal(L.parseLeg("Derrick White over 7.5 reb + ast").stat, "reb + ast");
  assert.equal(L.parseLeg("Rolando Mandragora 1+ shots on target").stat, "shots on target");
  assert.deepEqual(L.parseLeg("Over 2.5 goals"), { kind: "total", side: "over", point: 2.5 });
  assert.deepEqual(L.parseLeg("Under 47.5 total points"), { kind: "total", side: "under", point: 47.5 });
  assert.deepEqual(L.parseLeg("CBJ to win"), { kind: "ml", team: "CBJ" });
  assert.deepEqual(L.parseLeg("Virginia Tech Hokies -3.5"), { kind: "spread", team: "Virginia Tech Hokies", point: -3.5 });
  assert.equal(L.parseLeg("Both teams to score").kind, "btts");
  assert.equal(L.parseLeg("Drake Maye first TD scorer").first, true);
});

test("teams match by abbreviation, alias, nickname or name, accents aside", () => {
  assert.ok(L.isTeam("NJD", side("New Jersey Devils", "NJ")));
  assert.ok(L.isTeam("Chicago Bears", side("Chicago Bears", "CHI")));
  assert.ok(L.isTeam("Viktoria Plzeň", side("Viktoria Plzen", "PLZ")));
  assert.ok(L.isTeam("Borussia Monchengladbach", side("Borussia Mönchengladbach", "BMG")));
  assert.ok(!L.isTeam("Celta Vigo", side("Celtic", "CEL")));           // same ESPN abbreviation, different clubs
  assert.ok(L.isTeam("Celtic", side("Celtic", "CEL")));
  const games = [game("in", side("Celtic", "CEL", 1), side("Celta Vigo", "CEL", 0), "soccer")];
  assert.equal(L.findGame(games, "Celta Vigo @ Celtic").key, "soccer:1");
  assert.equal(L.findGame(games, "Rangers @ Celtic"), null);
  // Oct 24: "State" is in both pairs; the live Sacramento State game must not take Boise State's leg
  const sac = { ...game("in", side("Ball State Cardinals", "BALL", 0), side("Sacramento State Hornets", "SAC", 3), "ncaaf"), key: "ncaaf:sac" };
  const boise = { ...game("pre", side("Washington State Cougars", "WSU", null), side("Boise State Broncos", "BSU", null), "ncaaf"), key: "ncaaf:bsu" };
  assert.equal(L.findGame([sac, boise], "Boise State Broncos @ Washington State Cougars").key, "ncaaf:bsu");
});

test("players match despite case, suffixes and initials", () => {
  const box = { "demario douglas": { receivingYards: 23 }, "paul reed": { points: 9 }, "aj brown": { receivingYards: 48 } };
  assert.equal(L.findPlayer(box, "Demario Douglas").receivingYards, 23);
  assert.equal(L.findPlayer(box, "Paul Reed Jr").points, 9);
  assert.equal(L.findPlayer(box, "A.J. Brown").receivingYards, 48);
});

test("box scores parse made-attempted and comp/att columns", () => {
  const s = { boxscore: { players: [{ statistics: [
    { keys: ["minutes", "points", "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "rebounds"],
      athletes: [{ athlete: { displayName: "Tyler Herro" }, stats: ["20", "18", "3-7", "4"] }] },
    { keys: ["completions/passingAttempts", "passingYards"], athletes: [{ athlete: { displayName: "Drake Maye" }, stats: ["24/31", "321"] }] }] }] } };
  const box = L.parseBox(s, "nba");
  // both halves of "3-7" (Nov 6): made and attempted
  assert.deepEqual(box["tyler herro"], { minutes: 20, points: 18, threePointFieldGoalsMade: 3, threePointFieldGoalsAttempted: 7, rebounds: 4 });
  assert.equal(box["drake maye"].passingYards, 321);
});

test("props: an over clinches as soon as it's hit, an under busts when passed", () => {
  const live = game("in", side("Chicago Bears", "CHI", 21), side("New England Patriots", "NE", 17));
  const box = { "drake maye": { passingYards: 205 }, "cole kmet": { receptions: 2 } };
  assert.equal(L.judge("Drake Maye 200+ passing yds", live, box).status, "won");
  const under = L.judge("Cole Kmet under 1.5 receptions", live, box);
  assert.equal(under.status, "lost");
  const going = L.judge("Rome Odunze 40+ receiving yds", live, box);       // not in the box yet: 0 so far
  assert.deepEqual([going.status, going.current, going.target, going.text], ["live", 0, 40, "40 to go"]);
  const fin = L.judge("Rome Odunze 40+ receiving yds", { ...live, state: "post" }, { "rome odunze": { receivingYards: 38 } });
  assert.deepEqual([fin.status, fin.text], ["lost", "Missed by 2"]);
});

test("game lines: moneyline, spread, totals, soccer draws and both teams to score", () => {
  const g = game("in", side("Alaves", "ALA", 0), side("Malaga", "MCF", 1), "soccer");
  assert.equal(L.judge("Alavés to win", g, null).status, "losing");
  assert.equal(L.judge("Alavés to win", { ...g, state: "post", home: side("Alaves", "ALA", 1) }, null).status, "lost");   // 1-1: a draw loses a 3-way bet
  assert.equal(L.judge("Over 2.5 goals", g, null).status, "live");
  assert.equal(L.judge("Over 2.5 goals", { ...g, home: side("Alaves", "ALA", 2), away: side("Malaga", "MCF", 1) }, null).status, "won");
  assert.equal(L.judge("Both teams to score", { ...g, state: "post" }, null).status, "lost");
  const nfl = game("post", side("Chicago Bears", "CHI", 30), side("New England Patriots", "NE", 24));
  assert.equal(L.judge("Chicago Bears -3.5", nfl, null).status, "won");
  assert.equal(L.judge("New England Patriots +6", nfl, null).status, "void");          // a push
  assert.equal(L.judge("Under 47.5 total points", nfl, null).status, "lost");
});

test("UFC: live while the fight runs, then its winner", () => {
  const f = game("in", side("Movsar Evloev", "evloev", null), side("Alexander Volkanovski", "volkanovski", null), "ufc", { detail: "R2 3:10" });
  assert.equal(L.judge("Alex Volkanovski ML", f, null).status, "live");
  assert.equal(L.judge("Alex Volkanovski ML", { ...f, state: "post", winner: "away", result: "Decision - Unanimous" }, null).status, "won");
});

test("a parlay rolls up: lost on any lost leg, won when every leg is in", () => {
  const legs = (ss) => ss.map((s) => ({ status: s }));
  const g = [{ state: "in" }];
  assert.equal(L.rollup(legs(["won", "live"]), g).status, "live");
  assert.equal(L.rollup(legs(["won", "lost", "live"]), g).status, "lost");
  assert.deepEqual([L.rollup(legs(["won", "void"]), g).status, L.rollup(legs(["won", "void"]), g).hit], ["won", 1]);
});

test("bets split into their games: saved parlays, tickets and single picks", () => {
  assert.deepEqual(LB.refSport("nhl:2026020162"), { sport: "nhl", league: null });
  assert.deepEqual(LB.refSport("2026_07_NE_CHI"), { sport: "nfl", league: null });
  assert.deepEqual(LB.refSport("epl|Ipswich Town|Nottingham Forest|2026-10-23T19:00:00+00:00"), { sport: "soccer", league: "epl" });
  const custom = { games: [{ matchup: "Minnesota Wild @ Calgary Flames", game_ref: "nhl:1", legs: ["MIN to win"] }] };
  assert.deepEqual(LB.groups(custom, {}), [{ sport: "nhl", league: null, matchup: "Minnesota Wild @ Calgary Flames", legs: ["MIN to win"], ref: "nhl:1" }]);
  const ticket = { kind: "parlay", sgp_id: "t1", legs: ["x"] };
  const g = LB.groups(ticket, { t1: { games: [{ matchup: "Málaga @ Alavés", game_ref: "la_liga|Alavés|Málaga|t", legs: [{ label: "Alavés to win" }], commence_time: "t" }] } });
  assert.deepEqual([g[0].sport, g[0].league, g[0].legs], ["soccer", "la_liga", ["Alavés to win"]]);
  const pick = { kind: "pick", league: "nba", label: "Milwaukee Bucks ML", matchup: "Chicago Bulls @ Milwaukee Bucks", legs: null };
  assert.deepEqual([LB.groups(pick, {})[0].sport, LB.groups(pick, {})[0].legs], ["nba", ["Milwaukee Bucks ML"]]);
});

test("a bet settles from its live state: any lost leg, or every leg won outright", () => {
  const legs = (ss) => ss.map((s) => ({ status: s }));
  const g = [{ state: "in" }];
  assert.equal(L.rollup(legs(["won", "lost", "live"]), g).settle, "lost");
  assert.equal(L.rollup(legs(["won", "won"]), [{ state: "post" }]).settle, "won");
  assert.equal(L.rollup(legs(["won", "void"]), [{ state: "post" }]).settle, undefined);    // a void's reduced price: the grader's
  assert.equal(L.rollup(legs(["won", "live"]), g).settle, undefined);
});

test("live-settled bets read as settled with their profit, flagged not graded", () => {
  const B = loader()(new URL("../lib/bets.ts", import.meta.url));
  const settled = new Map([["a", "lost"], ["b", "won"]]);
  const bets = [{ bet_id: "a", pick_status: "open", stake: 2, price: 150 }, { bet_id: "b", pick_status: null, ticket_status: null, stake: 1, price: 300 },
                { bet_id: "c", ticket_status: "won", stake: 1, price: 100 }];
  const out = LB.markLiveSettled(bets, settled);
  assert.deepEqual([B.statusOf(out[0]), B.profit(out[0]), out[0].live_settled], ["lost", -2, "lost"]);
  assert.deepEqual([B.statusOf(out[1]), B.profit(out[1]), out[1].live_settled], ["won", 3, "won"]);
  assert.equal(out[2].live_settled, undefined);                                            // already graded: untouched
});

test("a settled bet's games are looked up on their own days", () => {
  const b = { placed_at: "2026-10-22T23:05:00Z", pick_commence_time: null, ticket_commence_time: null };
  assert.deepEqual(LB.daysOf(b, { ref: "2026_07_NE_CHI" }), ["20261022", "20261023"]);       // placed Thu 7:05 PM ET
  assert.deepEqual(LB.daysOf(b, { ref: "epl|Ipswich Town|Nottingham Forest|2026-10-23T19:00:00+00:00" }), ["20261023", "20261024"]);
  assert.deepEqual(LB.daysOf(b, { start: "2026-10-25T00:30:00Z" }), ["20261024", "20261025"]);   // 8:30 PM ET Oct 24
  assert.deepEqual(LB.daysOf(b, { start: "2027-03-14T04:30:00Z" }), ["20270313", "20270314"]);   // 11:30 PM ET, the night before the 23-hour day
  assert.deepEqual(LB.daysOf(b, { start: "2026-11-01T04:30:00Z" }), ["20261101", "20261102"]);   // 12:30 AM ET on the 25-hour day
});

// The cases the worker's Python port (src/betlab/live_legs.py, leg push alerts) runs too: both must read them alike.
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/live_legs.json", import.meta.url), "utf8"));

test("shared fixture: labels parse as the worker's port reads them", () => {
  for (const c of FIX.parse) assert.deepEqual(L.parseLeg(c.label), c.expect, c.label);
});

test("shared fixture: legs judge as the worker's port judges them", () => {
  for (const c of FIX.judge) {
    const s = (x) => side(x[0], x[1], x[2]);
    const g = game(c.game.state, s(c.game.home), s(c.game.away), c.game.sport, c.game.winner ? { winner: c.game.winner } : {});
    const got = L.judge(c.label, g, c.box ?? null);
    for (const [k, v] of Object.entries(c.expect)) assert.equal(got[k], v, `${c.label} (${c.game.state}): ${k}`);
  }
});

test("shared fixture: each bet's game is looked for on its own days (Nov 9)", () => {
  for (const c of FIX.days) assert.deepEqual(LB.searchDays(c.bet, c.group, c.open, new Date(c.now), c.single), c.expect, c.why);
});

test("a dead heat never settles live at the full price; a slip's games carry their own starts (Nov 9)", () => {
  const post = [{ state: "post" }];
  assert.equal(L.rollup([{ status: "won" }, { status: "won", deadHeat: true }], post).settle, undefined);
  assert.equal(L.rollup([{ status: "won" }, { status: "won", deadHeat: true }], post).status, "won");
  const slip = { games: [{ matchup: "A @ B", game_ref: "ncaaf:9", legs: ["A ML"] }, { matchup: "C @ D", game_ref: "ncaaf:8", legs: ["C ML"] }],
                 game_starts: { "ncaaf:9": "2026-11-08T00:30:00Z" } };
  assert.deepEqual(LB.groups(slip, {}).map((g) => g.start), ["2026-11-08T00:30:00Z", undefined]);
});

test("football: who has the ball, the red zone and the down; basketball: who's on the floor (Oct 25)", async () => {
  const comp = (state, situation) => ({ events: [{ id: "9", competitions: [{ id: "9", date: "2026-10-25T17:00:00Z", status: { type: { state, shortDetail: "Q2 1:15" } },
    situation, competitors: [{ homeAway: "home", score: "7", team: { id: "1", displayName: "Atlanta Falcons", abbreviation: "ATL" } },
                             { homeAway: "away", score: "3", team: { id: "25", displayName: "San Francisco 49ers", abbreviation: "SF" } }] }] }] });
  const [g] = await L.scoreboard("nfl", null, ["20261025"], async () => comp("in", { possession: "25", isRedZone: true, downDistanceText: "3rd & Goal at ATL 1" }));
  assert.equal(g.ball, "away"); assert.equal(g.redZone, true); assert.equal(g.down, "3rd & Goal at ATL 1");
  const [between] = await L.scoreboard("nfl", null, ["20261025"], async () => comp("in", { possession: null, isRedZone: true }));
  assert.equal(between.ball, null); assert.equal(between.redZone, false);   // ESPN's flag lingers between possessions
  const summary = { boxscore: { players: [{ statistics: [{ athletes: [
    { active: true, athlete: { displayName: "Bam Adebayo" } }, { active: false, athlete: { displayName: "Klay Thompson" } }] }] }] } };
  assert.deepEqual(L.parseOnCourt(summary), ["bam adebayo"]);
  const nba = game("in", side("Miami Heat", "MIA", 50), side("Charlotte Hornets", "CHA", 48), "nba");
  assert.equal(L.judge("Bam Adebayo 10+ rebounds", nba, { "bam adebayo": { rebounds: 6 } }, null, ["bam adebayo"]).onCourt, true);
  assert.equal(L.judge("Klay Thompson 2+ threes", nba, { "klay thompson": { threePointFieldGoalsMade: 1 } }, null, ["bam adebayo"]).onCourt, false);
  assert.equal(L.judge("Bam Adebayo 10+ rebounds", nba, { "bam adebayo": { rebounds: 6 } }, null, null).onCourt, undefined);
});

test("ESPN's cache: a 6-hour copy doesn't answer a live caller, a live copy doesn't answer a 6-hour caller, a failure isn't kept", async () => {
  const [realFetch, realNow] = [globalThis.fetch, Date.now];
  let calls = 0, ok = true, now = 1_000_000;
  globalThis.fetch = async () => { calls++; return { ok, json: async () => ({ calls }) }; };
  Date.now = () => now;
  try {
    await L.espn("https://x/board", L.DONE_TTL); now += 16_000;
    await L.espn("https://x/board");
    assert.equal(calls, 2);                                       // the Games list's copy froze the trackers
    now += 16_000; await L.espn("https://x/board", L.DONE_TTL);
    assert.equal(calls, 3);                                       // a game just over: not its last live box for 6 hours
    now += 10_000; await L.espn("https://x/board", L.DONE_TTL);
    assert.equal(calls, 3);                                       // still good for who asks long
    ok = false; await L.espn("https://x/down", L.DONE_TTL);
    ok = true; await L.espn("https://x/down", L.DONE_TTL);
    assert.equal(calls, 5);
  } finally { globalThis.fetch = realFetch; Date.now = realNow; }
});

test("the shared play-by-play gives the same stats (tests/fixtures/live_legs.json plays, Nov 6)", () => {
  const FX = JSON.parse(readFileSync(new URL("../../tests/fixtures/live_legs.json", import.meta.url), "utf8"));
  for (const c of FX.plays) assert.deepEqual(L.parseBox(c.summary, c.sport), c.expect, c.sport);
});
