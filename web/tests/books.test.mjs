import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const B = loader()(new URL("../lib/books.ts", import.meta.url));
const FX = JSON.parse(readFileSync(new URL("../../tests/fixtures/books_off.json", import.meta.url), "utf8"));

function check(offer, off, want, name) {
  const got = B.atBooks(offer, off);
  if (want === null) return assert.equal(got, null, name);
  assert.ok(got, name);
  for (const [k, v] of Object.entries(want)) assert.equal(got[k] ?? null, v, `${name}: ${k}`);
}

test("a card bet at the books an account has on (tests/fixtures/books_off.json, Nov 6)", () => {
  for (const c of FX.cases) check(FX.offer, c.off, c.want, c.case);
  check(FX.lean.offer, FX.lean.off, FX.lean.want, "lean");
  for (const c of FX.old.cases) check(FX.old.offer, c.off, c.want, "old");
  for (const c of FX.on) assert.deepEqual(B.onBooks(c.off), c.want);
});
