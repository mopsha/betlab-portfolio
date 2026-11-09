import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { loader } from "./load-ts.mjs";

const { score, flips, sideLabel, weekOf } = loader()(new URL("../lib/pickem.ts", import.meta.url));
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/pickem.json", import.meta.url), "utf8"));

test("CFB pick'em: the score, the flips worth an alert and the side labels match the shared fixture (Nov 7)", () => {
  assert.deepEqual(score(FIX.rows), FIX.score);
  const { toFlip, unpicked } = flips(FIX.rows);
  assert.deepEqual(toFlip.map((r) => sideLabel(r, r.ours)), FIX.flips);
  assert.deepEqual(unpicked.map((r) => r.n), FIX.unpicked);
  for (const [key, label] of Object.entries(FIX.labels)) {
    const [n, side] = key.split(":");
    assert.equal(sideLabel(FIX.rows.find((r) => r.n === Number(n)), side), label);
  }
});

test("the entry's week is the coming Saturday (today, on a Saturday)", () => {
  assert.equal(weekOf("2026-11-07"), "2026-11-07");
  assert.equal(weekOf("2026-11-08"), "2026-11-14");
  assert.equal(weekOf("2026-11-11"), "2026-11-14");
});
