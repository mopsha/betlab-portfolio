import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { loader } from "./load-ts.mjs";

const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/missed.json", import.meta.url), "utf8"));
const M = loader()(new URL("../lib/missed.ts", import.meta.url));
const near = (a, b) => (a === null || b === null ? a === b : Math.abs(a - b) < 1e-9);

for (const c of FIX.cases) test(c.name, () => {
  const r = M.missedBets(c.picks, c.taken, c.since);
  assert.deepEqual(r.picks.map((p) => p.pick_id), c.want.ids);
  assert.deepEqual([r.won, r.lost, r.push, r.tookN], [c.want.won, c.want.lost, c.want.push, c.want.took_n]);
  assert.ok(near(r.units, c.want.units) && near(r.clv, c.want.clv) && near(r.tookUnits, c.want.took_units));
});
