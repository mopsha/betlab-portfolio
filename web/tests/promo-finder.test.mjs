import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const F = loader()(new URL("../lib/promo-finder.ts", import.meta.url));
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/promo_finder.json", import.meta.url), "utf8"));
const leg = (id, i) => ({ event_id: `g-${id}-${i}`, label: `${id} leg ${i}` });
const pickRows = (rows) => rows.map((k) => ({ ...k, legs: Array.from({ length: k.legs }, (_, i) => leg(k.id, i)), games: k.plain ? k.legs : 1, ev: 0 }));
const lockRows = (rows) => rows.map((l) => ({ ...l, event_id: `g-${l.id}`, promoLeg: `${l.id} leg 0`, hedgeLeg: `${l.id} other` }));
const idOf = (r) => r.legs[0].label.split(" ")[0];
const near = (a, e, m) => assert.ok(Math.abs(a - e) < 1e-9, `${m}: ${a} != ${e}`);

for (const c of FIX.cases) {
  test(`promo finder ranks ${c.promo.kind} ${c.promo.pct ?? ""} ${c.mode} (shared fixture)`, () => {
    // a case may bring its own candidates (a boost that only takes 3-leg parlays)
    const out = F.rank(pickRows(c.picks ?? FIX.picks), lockRows(c.locks ?? FIX.locks), c.promo, c.mode);
    assert.deepEqual(out.map(idOf), c.order);
    for (const [id, v] of Object.entries(c.values ?? {})) near(out.find((r) => idOf(r) === id).value, v, id);
    for (const [id, v] of Object.entries(c.adds ?? {})) near(out.find((r) => idOf(r) === id).boostAdds, v, `${id} adds`);
    for (const [id, t] of Object.entries(c.text ?? {})) assert.equal(out.find((r) => idOf(r) === id).text, t);
  });
}

test("scopes: a slice, picked games, one game, today (capped, started games out, a token's sports)", () => {
  const now = new Date("2026-11-01T15:00:00Z");
  const games = [
    { event_id: "past", sport: "nfl", commence_time: "2026-11-01T14:30:00Z" },
    { event_id: "n1", sport: "nfl", commence_time: "2026-11-01T18:00:00Z" },
    { event_id: "h1", sport: "nhl", commence_time: "2026-11-01T23:00:00Z" },
    { event_id: "t1", sport: "nfl", commence_time: "2026-11-03T01:15:00Z" },
  ];
  const slices = [{ key: "2026-11-01-nfl-early", events: ["n1"] }];
  assert.deepEqual(F.scopeEvents({ kind: "slice", key: "2026-11-01-nfl-early" }, games, slices, null, now), ["n1"]);
  assert.deepEqual(F.scopeEvents({ kind: "games", events: ["h1", "past"] }, games, slices, null, now), ["h1"]);
  assert.deepEqual(F.scopeEvents({ kind: "game", event: "t1" }, games, slices, null, now), ["t1"]);
  assert.deepEqual(F.scopeEvents({ kind: "today" }, games, slices, null, now), ["n1", "h1"]);
  assert.deepEqual(F.scopeEvents({ kind: "today" }, games, slices, ["nhl"], now), ["h1"]);
});

for (const [i, c] of FIX.variety.cases.entries()) {
  test(`promo finder keeps its list varied, case ${i + 1} (shared fixture)`, () => {
    const picks = c.picks.map((k) => ({ ...k, legs: k.labels.map((label) => ({ event_id: "g", label })), games: k.labels.length, ev: 0 }));
    const idOf = (r) => c.picks.find((k) => k.labels.join("+") === r.legs.map((l) => l.label).join("+")).id;
    assert.deepEqual(F.rank(picks, [], c.promo, c.mode, c.top).map(idOf), c.order);
  });
}
