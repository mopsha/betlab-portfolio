import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const S = loader()(new URL("../lib/search.ts", import.meta.url));
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/search.json", import.meta.url), "utf8"));

test("search finds your bets (shared fixture)", () => {
  for (const [q, want] of FIX.bet_cases) assert.deepEqual(S.searchBets(FIX.bets, q).map((b) => b.bet_id), want, q);
});

test("search finds teams by name or code (shared fixture)", () => {
  for (const [q, want] of FIX.team_cases) assert.deepEqual(S.searchTeams(FIX.teams, q).map((t) => t.name), want, q);
});
