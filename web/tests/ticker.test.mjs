import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const T = loader()(new URL("../lib/ticker.ts", import.meta.url));
const game = (state, start, detail = "") => ({ key: "g", sport: "nba", espnId: "1", state, detail, start,
  home: { abbr: "CHI", score: state === "pre" ? null : 92 }, away: { abbr: "NYK", score: state === "pre" ? null : 98 } });
const leg = (label, status, text = "") => ({ label, status, current: null, target: null, unit: "", text, gameKey: "g" });

test("live bets come first, then the next to start, then what's settled", () => {
  const items = T.tickerItems({
    soon: { games: [game("pre", "2026-11-06T00:00:00Z")], legs: [leg("A", "pending")], status: "pending", hit: 0, total: 1 },
    done: { games: [game("post", "2026-11-05T20:00:00Z", "Final")], legs: [leg("B", "lost")], status: "lost", hit: 0, total: 1, settle: "lost" },
    live: { games: [game("in", "2026-11-05T23:00:00Z", "Q4 3:12")], legs: [leg("C", "won"), leg("Brunson 25+ points", "winning", "22 of 25")], status: "live", hit: 1, total: 2 },
  });
  assert.deepEqual(items.map((i) => i.id), ["live", "soon", "done"]);
  assert.equal(items[0].score, "NYK 98 · CHI 92");
  assert.equal(items[0].clock, "Q4 3:12");
  assert.equal(items[0].next, "Brunson 25+ points: 22 of 25");
  assert.equal(items[2].next, "B");
});

test("a bet with nothing to track stays off", () => {
  assert.deepEqual(T.tickerItems({ x: { games: [], legs: [], status: "pending", hit: 0, total: 0 } }), []);
});
