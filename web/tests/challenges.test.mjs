import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const { challengeState } = loader()(new URL("../lib/challenges.ts", import.meta.url));
const bet = { label: "Tulane Green Wave -10.5", legs: [], price: 111, dec: 2.11, p: 0.49, ev: 0.035 };
const ch = (fields) => ({ challenge_id: "c", day: "2026-10-28", text: "Place a straight trade on CFB (Min. $5)", points: 50,
  status: "open", pick: null, best: null, picked_at: null, notice: null, rules: null, ...fields });

test("a challenge says where it stands: waiting, watching, ready, placed (Oct 28)", () => {
  assert.equal(challengeState(ch({})).tag, "Waiting");
  const w = challengeState(ch({ best: bet }));
  assert.equal(w.tag, "Watching"); assert.equal(w.bet, bet); assert.match(w.note, /alert when it's ripe/);
  assert.equal(challengeState(ch({ status: "ready", pick: bet })).tag, "Ready");
  assert.equal(challengeState(ch({ status: "done", pick: bet })).tag, "Placed");
  assert.equal(challengeState(ch({ status: "skipped", pick: bet })).bet, null);
  assert.match(challengeState(ch({ notice: "missed: Tulane Green Wave -10.5" })).note, /started before it was placed/);
  assert.equal(challengeState(ch({ notice: "BetLab doesn't price this sport on Novig yet" })).note, "BetLab doesn't price this sport on Novig yet");
});

const { challengeHistory, pickOutcome } = loader()(new URL("../lib/challenges.ts", import.meta.url));

test("challenge history: points by day with the 3-for-3 bonus, and how each placed bet did (Oct 28)", () => {
  const pick = (id) => ({ label: `bet ${id}`, link: `https://novig.com/events/${id}/oddsapi/5` });
  const rows = [
    ch({ challenge_id: "a", day: "2026-10-27", status: "done", pick: pick("o1") }),
    ch({ challenge_id: "b", day: "2026-10-27", status: "done", pick: pick("o2") }),
    ch({ challenge_id: "c", day: "2026-10-27", status: "done", pick: { label: "parlay", link: "https://novig.com/events/x,y/oddsapi/5" } }),
    ch({ challenge_id: "d", day: "2026-10-28", status: "done", pick: pick("o3") }),
    ch({ challenge_id: "e", day: "2026-10-28", status: "skipped" }),
    ch({ challenge_id: "f", day: "2026-09-30", status: "done", pick: pick("o9") }),
  ];
  const bets = [{ sgp_id: "novig-o1", status: "won", profit: 1.1 }, { sgp_id: "novig-o2", status: "lost", profit: -1 },
                { sgp_id: "novig-o3", status: "open", profit: null }];
  const h = challengeHistory(rows, bets, "2026-10-28");
  assert.deepEqual(h.days.map((d) => [d.day, d.done, d.total, d.points, d.bonus]),
    [["2026-10-28", 1, 2, 50, false], ["2026-10-27", 3, 3, 250, true], ["2026-09-30", 1, 1, 50, false]]);
  assert.deepEqual(h.days[1].items.map((i) => i.result), ["won", "lost", null]);     // a parlay isn't synced: no result
  assert.equal(h.days[0].items[0].result, "open");
  const { units, ...month } = h.month;
  assert.deepEqual(month, { key: "2026-10", points: 300, done: 4, total: 5, sweeps: 1, settled: 2, won: 1 });
  assert.ok(Math.abs(units - 0.1) < 1e-9);
  assert.equal(pickOutcome({ pick: pick("o1") }), "o1");
  assert.equal(pickOutcome({ pick: null }), null);
});
