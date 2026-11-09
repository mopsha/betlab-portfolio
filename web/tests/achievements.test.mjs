import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const A = loader()(new URL("../lib/achievements.ts", import.meta.url));

let n = 0;
const bet = (o) => ({ bet_id: `b${++n}`, kind: "custom", mode: "real", price: 100, stake: 1, book: "FanDuel", label: null, matchup: "x",
  legs: ["A ML"], games: null, placed_at: `2026-10-${String(1 + (n % 27)).padStart(2, "0")}T18:00:00Z`, bonus: false, boost: null, cashout: null,
  pick_status: null, ticket_status: "won", league: null, sport: null, leg_results: null, clv: null, clv_raw: null, ...o });
const on = (day, o = {}) => bet({ placed_at: `${day}T18:00:00Z`, ...o });
const got = (bets) => new Set(A.achievements(bets).filter((b) => b.earned).map((b) => b.id));

test("there are lots of badges, every id and icon its own, each in a group", () => {
  assert.ok(A.DEFS.length >= 80);
  assert.equal(new Set(A.DEFS.map((d) => d.id)).size, A.DEFS.length);
  assert.equal(new Set(A.DEFS.map((d) => d.icon)).size, A.DEFS.length);
  assert.ok(A.DEFS.every((d) => A.GROUPS.includes(d.group)));
});

test("runs: 5 in a row is On fire; a loss resets it, a void doesn't", () => {
  const five = [on("2026-10-01"), on("2026-10-02"), on("2026-10-03", { ticket_status: "void" }), on("2026-10-04"), on("2026-10-05"), on("2026-10-06")];
  assert.ok(got(five).has("on-fire"));
  const broken = [on("2026-10-01"), on("2026-10-02"), on("2026-10-03", { ticket_status: "lost" }), on("2026-10-04"), on("2026-10-05")];
  assert.ok(!got(broken).has("on-fire"));
  assert.deepEqual(A.achievements(broken).find((b) => b.id === "on-fire").progress, { have: 2, need: 5 });
});

test("a comeback: back above zero after being down 5 units", () => {
  const lose = Array.from({ length: 5 }, (_, i) => on(`2026-10-0${i + 1}`, { ticket_status: "lost" }));
  assert.ok(got([...lose, on("2026-10-08", { price: 600 })]).has("comeback"));
  assert.ok(!got([...lose, on("2026-10-08", { price: 400 })]).has("comeback"));      // back to -1u: not yet
});

test("legs count by their line: a 300+ passing leg earns Air raid, 250+ doesn't", () => {
  const p = (label) => on("2026-10-12", { legs: [label, "B ML"], leg_results: [{ leg: label, result: "won", value: 310 }, { leg: "B ML", result: "lost" }], ticket_status: "lost" });
  assert.ok(got([p("Jared Goff 300+ passing yds")]).has("air-raid"));
  assert.ok(!got([p("Jared Goff 250+ passing yds")]).has("air-raid"));
  assert.ok(got([p("Jared Goff over 299.5 passing yds")]).has("air-raid"));
  assert.ok(got([on("2026-10-12", { label: "Josh Allen anytime TD", legs: null })]).has("td"));   // a single takes the bet's result
});

test("the heartbreaker: a 4+ leg parlay lost by exactly one graded leg", () => {
  const legs = ["A", "B", "C", "D"];
  const res = (lost) => legs.map((l, i) => ({ leg: l, result: lost.includes(i) ? "lost" : "won" }));
  assert.ok(got([on("2026-10-12", { legs, leg_results: res([2]), ticket_status: "lost" })]).has("heartbreak"));
  assert.ok(!got([on("2026-10-12", { legs, leg_results: res([1, 2]), ticket_status: "lost" })]).has("heartbreak"));
});

test("days: a perfect day needs 3+ bets all won; a big day is +5u", () => {
  assert.ok(got([on("2026-10-12"), on("2026-10-12"), on("2026-10-12")]).has("perfect-day"));
  assert.ok(!got([on("2026-10-12"), on("2026-10-12"), on("2026-10-12", { ticket_status: "lost" })]).has("perfect-day"));
  assert.ok(got([on("2026-10-12", { price: 300 }), on("2026-10-12", { price: 250 })]).has("big-day"));
});

test("Next up: the locked badges closest to done", () => {
  const bets = Array.from({ length: 9 }, (_, i) => on(`2026-10-${String(i + 1).padStart(2, "0")}`, { ticket_status: i % 2 ? "lost" : "won" }));
  const next = A.nextUp(A.achievements(bets), 3);
  assert.equal(next.length, 3);
  assert.ok(next.every((b) => !b.earned && b.progress.have > 0));
  assert.equal(next[0].id, "line-shopper");          // 1 of 2: halfway like Ten-piece's 5 of 10, and fewer to go
  assert.equal(next[1].id, "wins-10");
});
