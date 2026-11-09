import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const B = loader()(new URL("../lib/builder.ts", import.meta.url));
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/themes.json", import.meta.url), "utf8"));

test("themed slips (shared fixture)", () => {
  const pr = new B.Pricer(FIX.packs);
  for (const c of FIX.cases) {
    const s = B.themedSlip(pr, Object.keys(FIX.packs), c.theme);
    if (c.legs === null) { assert.equal(s, null, c.theme); continue; }
    assert.deepEqual(s.legs.map((l) => l.label), c.legs, c.theme);
    assert.ok(Math.abs(s.p - c.p) < 1e-6, `${c.theme} ${s.p}`);
    assert.ok(s.dec > 1);
  }
});

test("a banned player or team stays off a themed slip", () => {
  const pr = new B.Pricer(FIX.packs);
  const s = B.themedSlip(pr, Object.keys(FIX.packs), "overs", 3, [{ kind: "player", name: "Joe", league: null }]);
  assert.ok(!s.legs.some((l) => l.label.startsWith("Joe")));
});
