import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const load = loader();
const S = load(new URL("../lib/stats.ts", import.meta.url));
const A = load(new URL("../lib/achievements.ts", import.meta.url));
const C = load(new URL("../lib/share.ts", import.meta.url));

let n = 0;
const bet = (o) => ({ bet_id: `b${++n}`, kind: "custom", mode: "real", price: 100, stake: 1, book: "FanDuel", label: null, matchup: "x",
  legs: ["A ML"], games: null, placed_at: `2026-10-${String(10 + n).padStart(2, "0")}T18:00:00Z`, bonus: false, boost: null, cashout: null,
  pick_status: null, ticket_status: "won", league: null, sport: null, leg_results: null, clv: null, clv_raw: null, ...o });

test("bets fall into sports, types, price bands and money kinds", () => {
  const ufc = bet({ games: [{ matchup: "a vs b", game_ref: "ufc:1:2", legs: ["A ML"] }, { matchup: "c vs d", game_ref: "ufc:1:3", legs: ["C ML"] }], legs: ["A ML", "C ML"] });
  const mixed = bet({ games: [{ matchup: "x", game_ref: "epl|H|A|t", legs: ["H to win"] }, { matchup: "y", game_ref: "ncaaf:9", legs: ["Y ML"] }] });
  assert.equal(S.sportOf(ufc), "UFC");
  assert.equal(S.sportOf(mixed), "Multi-sport");
  assert.equal(S.sportOf(bet({ kind: "pick", league: "serie_a" })), "Soccer");
  assert.equal(S.sportOf(bet({ matchup: "SGP+ Fri Oct 23 · NBA late games", legs: ["x", "y"] })), "NBA");
  assert.equal(S.sportOf(bet({ matchup: "Dallas Cowboys @ Green Bay Packers", legs: ["Dak Prescott 225+ passing yds"] })), "NFL");
  assert.equal(S.sportOf(bet({ matchup: "New York Knicks @ Boston Celtics", legs: ["New York Knicks ML"] })), "NBA");
  assert.equal(S.sportOf(bet({ matchup: "Parlay Fri Oct 23 · college football night", legs: ["Duke Blue Devils +2.5"] })), "College football");
  assert.equal(S.typeOf(ufc), "Parlay, 2-4 legs");
  assert.equal(S.typeOf(bet({ legs: Array(8).fill("x") })), "Parlay, 5+ legs");
  assert.equal(S.bandOf(bet({ price: -130 })), S.BANDS[0]);
  assert.equal(S.bandOf(bet({ price: 1128 })), S.BANDS[4]);
  assert.equal(S.moneyOf(bet({ bonus: true, boost: 30 })), "Bonus bets");
  assert.equal(S.moneyOf(bet({ boost: 50 })), "Boosted cash");
});

test("units over time, streaks and extremes follow the settled order", () => {
  const bets = [bet({ price: 200 }), bet({ ticket_status: "lost" }), bet({}), bet({}), bet({ ticket_status: null })];
  const t = S.timeline(bets);
  assert.deepEqual(t.map((p) => p.units), [2, 1, 2, 3]);
  assert.deepEqual(S.streaks(bets), { current: { kind: "won", n: 2 }, bestWin: 2 });
  const e = S.extremes(bets);
  assert.equal(e.best.price, 200);
  assert.equal(e.worst.ticket_status, "lost");
});

test("achievements: earned ones carry their bet and day, locked ones their progress", () => {
  const bets = [bet({ price: 1100, bonus: true, legs: Array(5).fill("x") }), bet({ ticket_status: "lost" }), bet({ book: "DraftKings" })];
  const by = Object.fromEntries(A.achievements(bets).map((b) => [b.id, b]));
  assert.ok(by["four-figures"].earned && by["five-legs"].earned && by["free-money"].earned && by["line-shopper"].earned);
  assert.equal(by["eight-legs"].earned, null);
  assert.deepEqual(by["hat-trick"].progress, { have: 1, need: 3 });
  assert.equal(A.achievements(bets)[0].earned >= A.achievements(bets)[1].earned, true);   // newest first
});

test("a share card says one leg away, keeps repeated legs in order and shows a boosted price", () => {
  const b = bet({ ticket_status: "lost", price: 1128, bonus: true, legs: ["Over 2.5 goals", "Lazio to win", "Over 2.5 goals"],
    leg_results: [{ leg: "Over 2.5 goals", result: "won", value: "3-1" }, { leg: "Lazio to win", result: "won", value: "2-1" }, { leg: "Over 2.5 goals", result: "lost", value: "1-1" }] });
  const c = C.card(b);
  assert.equal(c.status, "ONE LEG AWAY");
  assert.deepEqual(c.legs.map((l) => [l.result, l.value]), [["won", "3-1"], ["won", "2-1"], ["lost", "1-1"]]);
  assert.equal(c.detail, "2 of 3 hit · 1u bonus bet");
  const boosted = C.card(bet({ ticket_status: null, price: 978, boost: 30, legs: ["A ML", "B ML", "C ML", "D ML"] }));
  assert.equal(boosted.status, "OPEN");
  assert.equal(boosted.price, "+978 → +1271");
  assert.match(boosted.headline, /^to win 12\.71u$/);
});

const P = load(new URL("../lib/players.ts", import.meta.url));

test("player cards count each leg, match results in order, and rank the most-bet first", () => {
  const a = bet({ ticket_status: "lost", legs: ["Josh Giddey 7+ assists", "Tre Jones 9+ points", "Miami Heat ML"],
    leg_results: [{ leg: "Josh Giddey 7+ assists", result: "lost", value: 6 }, { leg: "Tre Jones 9+ points", result: "won", value: 10 }, { leg: "Miami Heat ML", result: "won" }] });
  const b = bet({ ticket_status: null, legs: ["Josh Giddey 7+ assists", "Tre Jones 9+ points"], leg_results: null });
  const c = bet({ kind: "pick", ticket_status: null, pick_status: "won", legs: null, label: "Tre Jones over 8.5 points", price: -110 });
  const list = P.players([a, b, c]);
  assert.deepEqual(list.map((p) => [p.name, p.legs.length, p.won, p.lost, p.open]), [["Tre Jones", 3, 2, 0, 1], ["Josh Giddey", 2, 0, 1, 1]]);
  assert.equal(list[0].hitRate, 1);
  assert.equal(list[0].topStat, "points");
  assert.equal(list[0].bets, 3);
  assert.equal(P.tierOf(list[0]), null);           // 2 graded legs: no tier yet
  assert.equal(P.playerLegs(a).length, 2);         // the moneyline is no player's
});
