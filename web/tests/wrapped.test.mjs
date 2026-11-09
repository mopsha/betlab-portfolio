import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const W = loader()(new URL("../lib/wrapped.ts", import.meta.url));

let n = 0;
const bet = (o) => ({ bet_id: `b${++n}`, kind: "custom", mode: "real", price: 100, stake: 1, book: "FanDuel", label: null, matchup: "x",
  legs: ["A ML"], games: null, placed_at: "2026-10-20T18:00:00Z", bonus: false, boost: null, cashout: null,
  pick_status: null, ticket_status: "won", league: null, sport: null, leg_results: null, clv: null, clv_raw: null, ...o });
const on = (day, o = {}) => bet({ placed_at: `${day}T18:00:00Z`, ...o });

test("months with a settled bet, newest first, and the season once there's more than one", () => {
  assert.deepEqual(W.periods([on("2026-10-19"), on("2026-10-25"), on("2026-11-02"), on("2026-11-03", { ticket_status: null })]),
                   ["2026-11", "2026-10", "season"]);
  assert.deepEqual(W.periods([on("2026-10-19")]), ["2026-10"]);
  assert.equal(W.periodName("2026-10", new Date("2026-10-27T12:00:00Z")), "October");
  assert.equal(W.periodName("2025-12", new Date("2026-10-27T12:00:00Z")), "December 2025");
  assert.equal(W.periodName("season"), "Your season");
});

test("a month's story: its own bets only, the bottom line, biggest hit, best day and book", () => {
  const bets = [
    on("2026-09-28", { price: 900 }),                                        // September: not in October's story
    on("2026-10-19", { price: 389, boost: 30 }),                              // +5.06u
    on("2026-10-19", { ticket_status: "lost" }),
    on("2026-10-25", { price: 150, book: "DraftKings" }),
    on("2026-10-26", { ticket_status: "lost", book: "DraftKings" }),
    on("2026-10-27", { ticket_status: null }),                               // open: not counted
  ];
  const w = W.wrapped(bets, "2026-10", new Date("2026-10-27T12:00:00Z"));
  assert.equal(w.name, "October");
  assert.equal(w.total.bets, 4);
  assert.deepEqual([w.total.won, w.total.lost], [2, 2]);
  assert.ok(Math.abs(w.total.units - (3.89 * 1.3 - 1 + 1.5 - 1)) < 1e-9);
  assert.equal(w.best.price, "+389 → +506");
  assert.equal(w.bestDay.day, "2026-10-19");
  assert.equal(w.busiest.day, "2026-10-19");
  assert.equal(w.book.group, "FanDuel");                                    // +4.06u vs DraftKings +0.50u
  assert.equal(w.days, 3);
  assert.equal(W.wrapped(bets, "2026-08"), null);
  assert.equal(W.wrapped(bets, "season").total.bets, 5);
});

test("the heartbreaker is the longest parlay that lost by one leg, and names that leg", () => {
  const legs = ["A 50+ receiving yds", "B 3+ receptions", "C ML"];
  const res = (lost) => legs.map((l, i) => ({ leg: l, result: i === lost ? "lost" : "won", value: i === lost ? 44 : 1 }));
  const bets = [
    on("2026-10-25", { price: 600, legs, ticket_status: "lost", leg_results: res(0) }),
    on("2026-10-25", { price: 3038, legs, ticket_status: "lost", leg_results: res(2) }),
    on("2026-10-25", { price: 9000, legs, ticket_status: "lost", leg_results: legs.map((l) => ({ leg: l, result: "lost" })) }),   // two+ lost
  ];
  const h = W.heartbreak(bets);
  assert.equal(h.leg.label, "C ML");
  assert.equal(h.bet.price, "+3038");
  assert.equal(h.hit, 2);
  assert.equal(W.heartbreak([on("2026-10-25")]), null);
});

test("the betting type: the first that fits, with enough bets to mean it", () => {
  const many = (o, k = 6) => Array.from({ length: k }, () => on("2026-10-25", o));
  assert.equal(W.persona(many({ kind: "pick", pick_status: "won", ticket_status: null, clv: 0.03, logged_price: 100 })).name, "The Sharp");
  assert.equal(W.persona(many({ legs: Array(6).fill("x") })).name, "The Parlay Architect");
  assert.equal(W.persona(many({ bonus: true })).name, "The Bonus Hunter");
  assert.equal(W.persona(many({ price: 1200 })).name, "The Long-Shot Dreamer");
  assert.equal(W.persona(many({ kind: "pick", league: "nba" })).name, "The NBA Loyalist");
  assert.equal(W.persona(many({}, 2)).name, "The All-Rounder");                   // two bets: too few for a type
});

test("badges show in the month whose bet earned them", () => {
  const bets = [on("2026-09-28"), on("2026-10-20", { price: 1200 })];
  const oct = W.wrapped(bets, "2026-10").badges.map((b) => b.title);
  assert.ok(oct.includes("Four figures"));
  assert.ok(!oct.includes("On the board"));                                    // earned in September
});
