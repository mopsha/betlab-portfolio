import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const load = loader();
const M = load(new URL("../lib/me-view.ts", import.meta.url));
const B = load(new URL("../lib/bets.ts", import.meta.url));

let n = 0;
const bet = (day, status, o = {}) => ({ bet_id: `b${++n}`, kind: "custom", mode: "real", price: 100, stake: 1, book: "FanDuel", label: null, matchup: "x",
  legs: ["A ML"], games: null, placed_at: `${day}T18:00:00Z`, bonus: false, boost: null, cashout: null, pick_status: null, ticket_status: status,
  league: null, sport: null, leg_results: null, clv: null, clv_raw: null, ...o });

const today = "2026-11-04";
const bets = [
  bet("2026-10-01", "won"),                 // only in all time
  bet("2026-10-10", "lost"),                // in the month (30 days: from Oct 6)
  bet("2026-10-29", "won", { price: 150 }), // in the week (7 days: from Oct 29)
  bet("2026-11-03", "won"),
  bet("2026-11-04", "lost"),
  bet("2026-11-04", "open"),                // not settled: never counted
];

test("a range is today and the days before it, by the Eastern day", () => {
  assert.equal(M.rangeFrom("week", today), "2026-10-29");
  assert.equal(M.rangeFrom("month", today), "2026-10-06");
  assert.equal(M.rangeFrom("all", today), "");
  assert.equal(M.rangeOf("month"), "month");
  assert.equal(M.rangeOf("year"), "all");
  assert.equal(M.rangeOf(undefined), "all");
  assert.equal(M.rangeLabel("week"), "this week");
});

test("the number, the record, the return and the streak follow the range", () => {
  const all = M.meNumbers(bets, "all", today);
  assert.deepEqual([all.bets, all.won, all.lost, all.streak], [5, 3, 2, "L1"]);
  assert.equal(all.units.toFixed(2), "1.50");
  assert.equal(all.roi.toFixed(2), "0.30");
  assert.equal(all.units, B.record(bets).total.units);         // the same number the record shows
  assert.deepEqual(all.points.map((p) => +p.toFixed(2)), [0, 1, 0, 1.5, 2.5, 1.5]);

  const month = M.meNumbers(bets, "month", today);
  assert.deepEqual([month.won, month.lost, +month.units.toFixed(2)], [2, 2, 0.5]);
  const week = M.meNumbers(bets, "week", today);
  assert.deepEqual([week.won, week.lost, +week.units.toFixed(2)], [2, 1, 1.5]);
  assert.deepEqual(week.points.map((p) => +p.toFixed(2)), [0, 1.5, 2.5, 1.5]);   // the range starts from zero
  assert.equal(week.clv, null);                                // no bet with a close: no number, never 0

  const none = M.meNumbers([], "week", today);
  assert.deepEqual([none.bets, none.units, none.roi, none.streak, none.points], [0, 0, null, null, [0]]);
});

test("the wallet in one line", () => {
  assert.deepEqual(M.walletLine([{ kind: "bonus", amount_dollars: 5 }, { kind: "bonus", amount_dollars: "5" }, { kind: "boost", amount_dollars: 25 }]),
    { dollars: 10, bonuses: 2, boosts: 1 });
  assert.deepEqual(M.walletLine([]), { dollars: 0, bonuses: 0, boosts: 0 });
});

test("the badge row: earned ones, then a couple still locked, the nearest first", () => {
  const b = (id, earned, progress) => ({ id, earned, progress });
  const row = M.badgeRow([b("a", "2026-11-01"), b("b", "2026-10-20"), b("c", null), b("d", null, { have: 4, need: 5 }), b("e", null, { have: 1, need: 5 })]);
  assert.deepEqual(row.map((x) => x.id), ["a", "b", "d", "e"]);
  assert.deepEqual(M.badgeRow([b("c", null), b("d", null), b("e", null)]).map((x) => x.id), ["c", "d"]);
  assert.equal(M.badgeRow(Array.from({ length: 30 }, (_, i) => b(`x${i}`, "2026-11-01")), 10, 2).length, 10);
});
