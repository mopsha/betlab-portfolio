import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const S = loader()(new URL("../lib/slices.ts", import.meta.url));
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/slices.json", import.meta.url), "utf8"));

test("kickoff slices match the worker's (shared fixture)", () => {
  for (const [sport, kickoff, day, name] of FIX.cases) assert.deepEqual(S.sliceOf(sport, kickoff), [day, name], `${sport} ${kickoff}`);
});

test("games group into slices, soonest first, titled by sport, slice and day", () => {
  const out = S.slicesOf([
    { event_id: "b", sport: "nfl", commence_time: "2026-11-01T18:00:00Z" },
    { event_id: "a", sport: "nfl", commence_time: "2026-11-01T18:05:00Z" },
    { event_id: "r", sport: "ncaab", commence_time: "2026-11-01T14:30:00Z" },
  ]);
  assert.deepEqual(out.map((s) => [s.title, s.events]), [["College basketball morning · Sun", ["r"]], ["NFL early · Sun", ["b", "a"]]]);
});
