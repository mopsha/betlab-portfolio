import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const C = loader()(new URL("../lib/calendar.ts", import.meta.url));
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/calendar.json", import.meta.url), "utf8"));

test("the month grid runs Sunday to Saturday around the month (shared fixture)", () => {
  for (const g of FIX.grids) {
    const days = C.monthGrid(g.month);
    assert.equal(days[0], g.first, g.month);
    assert.equal(days.at(-1), g.last, g.month);
    assert.equal(days.length, g.weeks * 7, g.month);
  }
});

test("months shift across years", () => {
  for (const [from, n, to] of FIX.shift) assert.equal(C.shiftMonth(from, n), to);
});
