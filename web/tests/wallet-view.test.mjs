import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const V = loader()(new URL("../lib/wallet-view.ts", import.meta.url));
const now = new Date("2026-11-05T03:00:00Z");   // 10 PM Eastern, Nov 4

test("when a token ends: today is the warning case, with the time left", () => {
  const e = V.endsOf({ expires_at: "2026-11-05T04:59:00Z" }, now);
  assert.deepEqual([e.text, e.left, e.today, e.over], ["ends today 11:59 PM", "1 h 59 m left", true, false]);
  const sat = V.endsOf({ expires_at: "2026-11-08T04:59:00Z" }, now);
  assert.deepEqual([sat.text, sat.left, sat.today], ["ends Sat 11:59 PM", null, false]);
  assert.equal(V.endsOf({ expires_at: "2026-11-02T04:59:00Z" }, now).over, true);
  assert.equal(V.endsOf({ expires_at: null }, now), null);
});

test("a token's value and its limits as chips", () => {
  assert.equal(V.tokenValueText({ kind: "bonus", amount_dollars: 10, pct: null }), "$10");
  assert.equal(V.tokenValueText({ kind: "boost", amount_dollars: 25, pct: 50 }), "50%");
  const chips = V.tokenChips({ kind: "boost", amount_dollars: 25, pct: 50, max_extra_dollars: 50, min_legs: 3, min_odds: -200, max_odds: null,
    sports: ["nba"], teams: ["Knicks"], note: null });
  assert.deepEqual(chips.map((c) => c.text), ["up to $25", "max $50 extra", "3+ legs", "−200 or longer", "NBA only", "Knicks"]);
  assert.equal(chips.at(-1).team.name, "New York Knicks");
});

test("a team by name: one match or none", () => {
  assert.match(V.teamMark("Knicks").src, /teamlogos\/nba\/500\/nyk?\.png$/);
  assert.equal(V.teamMark("New York").src, null);        // several teams: no guess
  assert.equal(V.teamMark("Stade Rennais").src, null);
});

test("the ladder's rungs: won, the one being climbed, then what's left", () => {
  assert.deepEqual(V.rungs(3, 3, null), ["won", "won", "won", "now", "todo", "todo"]);
  assert.deepEqual(V.rungs(1, 6, "busted"), ["won", "lost", "todo", "todo", "todo", "todo", "todo"]);
  assert.deepEqual(V.rungs(2, 0, "climbed"), ["won", "won"]);
  assert.equal(V.rungs(0, 40, null).length, 16);
});
