import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

function load(path, require = () => ({})) {
  const url = new URL(path, import.meta.url);
  const module = { exports: {} };
  const code = ts.transpileModule(readFileSync(url, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInThisContext(`(function(require, module, exports) {\n${code}\n})`, { filename: fileURLToPath(url) })(require, module, module.exports);
  return module.exports;
}
const slices = load("../lib/slices.ts");
const { lockTime, upcomingLocks, scheduledSlices } = load("../lib/locks.ts", () => slices);

test("a slice locks at the first quarter-hour tick within 25 minutes of its first kickoff (Oct 10)", () => {
  assert.equal(lockTime("2026-10-10T22:10:00Z").toISOString(), "2026-10-10T21:45:00.000Z");   // 6:10 PM -> 5:45
  assert.equal(lockTime("2026-10-10T23:30:00Z").toISOString(), "2026-10-10T23:15:00.000Z");   // 7:30 PM -> 7:15
  assert.equal(lockTime("2026-10-10T23:07:00Z").toISOString(), "2026-10-10T22:45:00.000Z");   // 7:07 PM -> 6:45
});

test("the next locks: unlocked slices with a ticket, soonest first", () => {
  const s = (slate, kickoff, extra = {}) => ({ slate, sport: "nhl", kickoff, label: slate, title: slate,
    ticket_ids: ["plus-x"], ...extra });
  const now = Date.parse("2026-10-10T20:52:00Z");
  const out = upcomingLocks([
    s("soccer evening", "2026-10-10T23:30:00Z"), s("nhl evening", "2026-10-10T22:10:00Z"),
    s("nhl late", "2026-10-11T02:10:00Z", { ticket_ids: [] }),                        // no ticket: nothing to lock
    s("noon", "2026-10-10T16:00:00Z"),                                                 // started
    s("afternoon", "2026-10-10T21:30:00Z", { locked_at: "t" }),                       // already locked
  ], now);
  assert.deepEqual(out.map((l) => l.slate), ["nhl evening", "soccer evening"]);
});

test("the NBA's slices come from the schedule until their pull builds them (Oct 24)", () => {
  const now = Date.parse("2026-10-24T21:00:00Z");                                   // 5 PM ET
  const games = [{ league: "nba", commence_time: "2026-10-24T22:10:00Z" }, { league: "nba", commence_time: "2026-10-24T22:40:00Z" },
    { league: "nba", commence_time: "2026-10-24T23:40:00Z" }, { league: "nba", commence_time: "2026-10-25T00:10:00Z" },
    { league: "nba", commence_time: "2026-10-25T01:10:00Z" }, { league: "nba", commence_time: "2026-10-25T02:10:00Z" },
    { league: "nhl", commence_time: "2026-10-24T23:00:00Z" }];
  assert.deepEqual(scheduledSlices(games, now), [
    { slate: "2026-10-24-nba-dusk", sport: "nba", title: "NBA 6:10 PM games", at: "2026-10-24T21:45:00.000Z" }, // 6:10 tip -> 5:45 (Nov 7)
    { slate: "2026-10-24-nba-early", sport: "nba", title: "NBA early games", at: "2026-10-24T23:15:00.000Z" },   // 7:40 -> 7:15
    { slate: "2026-10-24-nba-late", sport: "nba", title: "NBA late games", at: "2026-10-25T00:45:00.000Z" }]);  // 9:10 -> 8:45
  // once the pull builds a slice, the built one stands in for it
  const out = upcomingLocks([{ slate: "2026-10-24-nba-dusk", sport: "nba", kickoff: "2026-10-24T22:10:00Z", label: "x", title: "NBA 6:10 PM games",
    ticket_ids: ["plus-y"] }], now, games);
  assert.deepEqual(out.map((l) => l.slate), ["2026-10-24-nba-dusk", "2026-10-24-nba-early", "2026-10-24-nba-late"]);
});

test("college basketball's slices too, once a slice has the two games a ticket needs (Nov 2)", () => {
  const now = Date.parse("2026-11-02T14:15:00Z");                                   // 9:15 AM ET
  const games = [{ league: "ncaab", commence_time: "2026-11-02T14:00:00Z" },        // started
    { league: "ncaab", commence_time: "2026-11-02T15:00:00Z" },                     // 10 AM, alone in the morning
    { league: "ncaab", commence_time: "2026-11-02T23:00:00Z" }, { league: "ncaab", commence_time: "2026-11-02T23:30:00Z" },
    { league: "ncaab", commence_time: "2026-11-03T02:30:00Z" }];                    // 9:30 PM, alone in the late slice
  assert.deepEqual(scheduledSlices(games, now), [
    { slate: "2026-11-02-ncaab-evening", sport: "ncaab", title: "College basketball evening games", at: "2026-11-02T22:15:00.000Z" }]);   // 6 PM tip: its pull, 5:15
});
