import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { loader } from "./load-ts.mjs";

const { showsWatched, toggled, watchedLocks } = loader()(new URL("../lib/watch.ts", import.meta.url));
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/watch.json", import.meta.url), "utf8"));

test("Today shows a watched game's own slips at its own lock, never its slice's (Nov 7, shared fixture)", () => {
  const watching = new Set(FIX.watching);
  const now = Date.parse(FIX.now);
  for (const c of FIX.cases) assert.equal(showsWatched(c.ticket, watching, now), c.show, c.name);
  assert.deepEqual(watchedLocks(FIX.locks.tickets, watching, now).map((l) => ({ key: l.slate, title: l.title, at: l.at })), FIX.locks.want);
});

test("watching a game turns on once and off cleanly", () => {
  assert.deepEqual(toggled(["a"], "b", true), ["a", "b"]);
  assert.deepEqual(toggled(["a", "b"], "b", true), ["a", "b"]);
  assert.deepEqual(toggled(["a", "b"], "a", false), ["b"]);
});
