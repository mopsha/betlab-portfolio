import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const { isEarlyLean } = loader({ "./data": {} })(new URL("../lib/early.ts", import.meta.url));
const now = Date.parse("2026-10-13T12:00:00Z");
const at = (h) => new Date(now + h * 3600e3).toISOString();

test("a game-line lean more than 36 hours out is early", () => {
  assert.equal(isEarlyLean({ tier: "lean", market: "spreads", commence_time: at(37) }, now), true);
  assert.equal(isEarlyLean({ tier: "lean", market: "h2h", commence_time: at(35) }, now), false);
});

test("picks and props are never labeled early", () => {
  assert.equal(isEarlyLean({ tier: "pick", market: "totals", commence_time: at(48) }, now), false);
  assert.equal(isEarlyLean({ tier: "lean", market: "player_receptions", commence_time: at(48) }, now), false);
  assert.equal(isEarlyLean({ tier: "lean", market: "totals", commence_time: null }, now), false);
});
