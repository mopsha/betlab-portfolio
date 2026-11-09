import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const { matchupText, inOrder } = loader()(new URL("../lib/format.ts", import.meta.url));
const fixture = JSON.parse(readFileSync(new URL("../../tests/fixtures/soccer_matchups.json", import.meta.url), "utf8"));

test("soccer reads home team first, the rest as stored (Nov 5)", () => {
  for (const c of fixture.cases) assert.equal(matchupText(c.text, c.sport), c.out, `${c.text} (${c.sport})`);
  assert.deepEqual(inOrder("soccer", "away", "home"), ["home", "away"]);
  assert.deepEqual(inOrder("nba", "away", "home"), ["away", "home"]);
});
