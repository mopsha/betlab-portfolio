import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { loader } from "./load-ts.mjs";

// The cases ios/BetLab/Me/Ladder.swift runs too: both apps must answer them alike.
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/ladder.json", import.meta.url), "utf8"));
const L = loader()(new URL("../lib/ladder.ts", import.meta.url));
const near = (a, b, what) => assert.ok(Math.abs(a - b) < 1e-4, `${what}: ${a} != ${b}`);

const bet = (s, i) => ({ bet_id: `b${i}`, ladder_id: "L", kind: "custom", mode: "real", stake: s.stake, price: s.price,
  bonus: s.bonus === true, boost: s.boost ?? null, cashout: s.cashout ?? null, placed_at: `2026-10-2${i}T12:00:00Z`,
  pick_status: null, ticket_status: s.status, leg_results: null });

test("the shared ladder states", () => {
  for (const c of FIX.states) {
    const l = { ladder_id: "L", start_units: c.ladder.start, target_units: c.ladder.target, status: c.ladder.status ?? "active", created_at: "2026-10-20T00:00:00Z" };
    const s = L.ladderState(l, c.steps.map(bet));
    assert.equal(s.phase, c.expect.phase, c.name);
    near(s.stack, c.expect.stack, c.name);
    assert.equal(s.won, c.expect.won, c.name);
    if (c.expect.next_stake === null) assert.equal(s.nextStake, null, c.name); else near(s.nextStake, c.expect.next_stake, c.name);
    if ("to_win" in c.expect) near(s.toWin, c.expect.to_win, c.name);
  }
});

test("a step from another ladder doesn't count", () => {
  const l = { ladder_id: "L", start_units: 1, target_units: 10, status: "active", created_at: "x" };
  const other = { ...bet({ stake: 1, price: 100, status: "won" }, 1), ladder_id: "M" };
  assert.equal(L.ladderState(l, [other]).stack, 1);
});

test("the shared step suggestions", () => {
  for (const c of FIX.suggest) {
    const got = L.suggestStep(c.offers, Date.parse(c.now), c.skipped ?? [], c.game ?? null, c.before ? Date.parse(c.before) : null, c.book ?? null);
    assert.equal(got ? got.offer_id : null, c.expect, c.name);
    if (c.expect_price !== undefined) assert.equal(got.price, c.expect_price, c.name);
  }
});

test("wins in a row to the target", () => {
  for (const c of FIX.steps_to_target) assert.equal(L.stepsToTarget(c.stack, c.target, c.price), c.expect, JSON.stringify(c));
});

test("a step reads as its legs before the slip reader's label, and a ladder never shows less than nothing", () => {
  for (const c of FIX.step_names) assert.equal(L.stepName(c), c.expect, JSON.stringify(c));
  for (const c of FIX.ended_stack) assert.equal(L.shownStack(c.stack), c.expect);
});
