import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const S = loader()(new URL("../lib/slip.ts", import.meta.url));
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/slip_ev.json", import.meta.url), "utf8"));
const ALL = "/w==";      // 8 draws, all hits
const pack = (eid, sport, legs) => ({ event_id: eid, matchup: "x", commence_time: "", sport, draws: 8,
  legs: Object.fromEntries(legs.map(([label, p, bits]) => [label, { label, p, p_pack: p, price: -110, bits: bits ?? ALL }])) });
const leg = (label, event_id, sport = "nhl") => ({ label, event_id, sport, matchup: "x", game_ref: null, start: null, matched: true });

test("a priced slip's value, with a boost or a bonus bet (shared fixture)", () => {
  for (const c of FIX.cases) {
    const v = S.slipEv(c.p, c.price, c.boost, c.bonus);
    assert.ok(Math.abs(v.ev - c.ev) < 1e-9, JSON.stringify(c));
    assert.equal(v.fair, c.fair);
    assert.equal(v.verdict, c.verdict);
  }
});

test("a slip's legs find their pack legs in any wording", () => {
  const legs = [{ label: "NYR to win" }, { label: "NYR -1.5" }, { label: "Over 6.5 goals" }, { label: "Artemi Panarin 3+ shots" }];
  const find = (l) => S.findPackLeg(l, legs, "nhl")?.label;
  assert.equal(find("New York Rangers ML"), "NYR to win");
  assert.equal(find("New York Rangers -1.5"), "NYR -1.5");
  assert.equal(find("New York Rangers +1.5"), undefined);
  assert.equal(find("Over 6.5 total goals"), "Over 6.5 goals");
  assert.equal(find("Under 6.5 goals"), undefined);
  assert.equal(find("Artemi Panarin over 2.5 shots"), "Artemi Panarin 3+ shots");
  assert.equal(find("St. Louis Blues ML"), undefined);
});

test("a slip's fair chance: legs in one game together, games multiplied, or what it couldn't price", () => {
  const packs = { a: pack("a", "nhl", [["NYR to win", 0.6, "/w=="], ["Over 6.5 goals", 0.5, "8A=="]]), b: pack("b", "nhl", [["BUF to win", 0.5]]) };
  const same = S.slipFair([leg("New York Rangers ML", "a"), leg("Over 6.5 goals", "a")], packs);
  assert.ok(same.p > 0 && same.p <= 0.5);
  assert.deepEqual(same.labels, ["New York Rangers ML", "Over 6.5 goals"]);
  const cross = S.slipFair([leg("New York Rangers ML", "a"), leg("Buffalo Sabres ML", "b")], packs);
  assert.ok(Math.abs(cross.p - 0.3) < 1e-9);
  const miss = S.slipFair([leg("New York Rangers ML", "a"), leg("Somebody 3+ shots", "a"), leg("Boston Bruins ML", null)], packs);
  assert.equal(miss.p, null);
  assert.deepEqual(miss.missing, ["Somebody 3+ shots", "Boston Bruins ML"]);
});

test("the fair price only counts for the legs it was worked out on", () => {
  const d = { fair: { p: 0.3, labels: ["A ML", "B ML"], missing: [] }, legs: [leg("A ML", "a"), leg("B ML", "b")] };
  assert.equal(S.fairOf(d)?.p, 0.3);
  assert.equal(S.fairOf({ ...d, legs: [leg("A ML", "a")] }), null);
  assert.equal(S.fairOf({ ...d, legs: [leg("A ML", "a"), leg("C ML", "b")] }), null);
  assert.equal(S.fairOf({ ...d, fair: { p: null, labels: [], missing: ["A ML"] } }), null);
});
