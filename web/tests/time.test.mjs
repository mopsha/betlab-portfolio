import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const { etStart, etDay, etInstant } = loader()(new URL("../lib/time.ts", import.meta.url));

test("an Eastern day starts at its own midnight, clock changes too (Nov 1, 2026)", () => {
  assert.equal(etStart("2026-10-31").toISOString(), "2026-10-31T04:00:00.000Z");   // EDT
  assert.equal(etStart("2026-11-01").toISOString(), "2026-11-01T04:00:00.000Z");   // EDT at midnight, EST by noon
  assert.equal(etStart("2026-11-02").toISOString(), "2026-11-02T05:00:00.000Z");   // EST
  assert.equal(etStart("2027-03-14").toISOString(), "2027-03-14T05:00:00.000Z");   // EST at midnight, EDT by noon
  assert.equal(etDay("2026-11-01T04:30:00Z"), "2026-11-01");                       // 12:30 AM EDT
});

test("an Eastern wall time is the right instant on clock-change days", () => {
  assert.equal(etInstant("2026-10-24T13:06:00").toISOString(), "2026-10-24T17:06:00.000Z");
  assert.equal(etInstant("2026-11-01T00:30:00").toISOString(), "2026-11-01T04:30:00.000Z");   // EDT
  assert.equal(etInstant("2026-11-01T06:30:00").toISOString(), "2026-11-01T11:30:00.000Z");   // EST
  assert.equal(etInstant("2027-03-14T01:30:00").toISOString(), "2027-03-14T06:30:00.000Z");   // EST
  assert.equal(etInstant("2027-03-14T03:30:00").toISOString(), "2027-03-14T07:30:00.000Z");   // EDT
});
