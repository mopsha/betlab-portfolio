import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const { boardTabs, shortLeg } = loader()(new URL("../lib/builder.ts", import.meta.url));
const B = loader()(new URL("../lib/builder.ts", import.meta.url));
const leg = (label, x) => ({ label, price: -110, p: 0.5, p_pack: 0.5, player: "", ...x });

test("game lines: away, draw, home in one row; totals pair over with under by number", () => {
  const legs = [
    leg("Juventus to win", { stat: "moneyline", side: "yes", team: "Juventus" }),
    leg("Draw", { stat: "draw", side: "yes" }),
    leg("Rennes to win", { stat: "moneyline", side: "yes", team: "Rennes" }),
    leg("Under 2.5 goals", { stat: "goals", side: "under", point: 2.5 }),
    leg("Over 1.5 goals", { stat: "goals", side: "over", point: 1.5 }),
    leg("Over 2.5 goals", { stat: "goals", side: "over", point: 2.5 }),
  ];
  const [t] = boardTabs(legs, "Rennes @ Juventus");
  assert.equal(t.title, "Game lines");
  assert.deepEqual(t.sections.map((s) => s.title), ["Result", "Total goals"]);
  // soccer reads home team first (Nov 5): Juventus (home), Draw, Rennes
  assert.deepEqual(t.sections[0].rows[0].legs.map((l) => l.label), ["Juventus to win", "Draw", "Rennes to win"]);
  assert.deepEqual(t.sections[1].rows.map((r) => r.legs.map(shortLeg)), [["Over 1.5"], ["Over 2.5", "Under 2.5"]]);
});

test("a spread rung pairs the away side with the home side's opposite number", () => {
  const legs = [
    leg("CBJ -1.5", { stat: "puck line", side: "yes", team: "CBJ", point: -1.5 }),
    leg("CBJ +1.5", { stat: "puck line", side: "yes", team: "CBJ", point: 1.5 }),
    leg("BUF -1.5", { stat: "puck line", side: "yes", team: "BUF", point: -1.5 }),
    leg("BUF +1.5", { stat: "puck line", side: "yes", team: "BUF", point: 1.5 }),
  ];
  const rows = boardTabs(legs, "BUF @ CBJ")[0].sections[0].rows.map((r) => r.legs.map((l) => l.label));
  assert.deepEqual(rows, [["BUF -1.5", "CBJ +1.5"], ["BUF +1.5", "CBJ -1.5"]]);
});

test("player props: a tab per stat, a section per player, buttons say only the side", () => {
  const p = (label, player, stat, side, point) => leg(label, { player, stat, side, point, team: "PIT" });
  const legs = [
    p("DK Metcalf over 3.5 receptions", "DK Metcalf", "receptions", "over", 3.5),
    p("DK Metcalf under 3.5 receptions", "DK Metcalf", "receptions", "under", 3.5),
    p("Jaylen Warren anytime TD", "Jaylen Warren", "tds", "yes", 0.5),
  ];
  const tabs = boardTabs(legs, "Pittsburgh Steelers @ Cleveland Browns");
  assert.deepEqual(tabs.map((t) => t.title), ["Receptions", "Touchdowns"]);
  assert.equal(tabs[0].sections[0].title, "DK Metcalf");
  assert.deepEqual(tabs[0].sections[0].rows[0].legs.map(shortLeg), ["Over 3.5", "Under 3.5"]);
  assert.equal(shortLeg(tabs[1].sections[0].rows[0].legs[0]), "Anytime TD");
});

const { promoEv, promoFits, findPromo, Pricer } = loader()(new URL("../lib/builder.ts", import.meta.url));

test("promo value: a bonus bet keeps only the profit; a boost multiplies it", () => {
  assert.equal(promoEv(0.25, 4, { kind: "bonus" }), 0.75);
  assert.equal(promoEv(0.25, 4, { kind: "none" }), 0);
  assert.ok(Math.abs(promoEv(0.25, 4, { kind: "boost", pct: 50 }) - 0.375) < 1e-12);
  // a $10 stake at +900 with a 100% boost would add $90; a $25 cap on extra winnings keeps $25 of it
  assert.ok(Math.abs(promoEv(0.1, 10, { kind: "boost", pct: 100, stake: 10, maxExtra: 25 }) - 0.25) < 1e-12);
  assert.ok(Math.abs(promoEv(0.1, 10, { kind: "boost", pct: 100 }) - 0.9) < 1e-12);
});

test("a token's terms: fewest legs and shortest odds", () => {
  assert.equal(promoFits({ kind: "boost", pct: 50, minLegs: 3 }, 2, 5), false);
  assert.equal(promoFits({ kind: "boost", pct: 50, minLegs: 3 }, 3, 5), true);
  assert.equal(promoFits({ kind: "bonus", minOdds: 300 }, 2, 3.5), false);
  assert.equal(promoFits({ kind: "bonus", minOdds: 300 }, 2, 4), true);
});

test("same-game slips rank at a cautious quote; plain parlays of sharp-priced legs at their exact price", () => {
  const bits = (on) => Buffer.from(Uint8Array.from({ length: 100 }, (_, i) => (on(i) ? 255 : 0))).toString("base64");
  const leg = (label, team, p, price, on, source) => [label, { label, team, stat: "moneyline", side: "yes", p, p_pack: p, price, bits: bits(on), source }];
  const game = (id, legs) => ({ event_id: id, matchup: id, commence_time: "", sport: "nba", draws: 800, legs: Object.fromEntries(legs) });
  const pr = new Pricer({
    g1: game("g1", [leg("A ML", "A", 0.5, 110, (i) => i % 2 === 0, "pinnacle (market)")]),
    g2: game("g2", [leg("C ML", "C", 0.5, 105, (i) => i < 50, "pinnacle (market)")]),
    g3: game("g3", [leg("E ML", "E", 0.5, 120, (i) => i % 2 === 1, "fanatics, williamhill_us")]),
  });
  const all = findPromo(pr, ["g1", "g2", "g3"], { kind: "bonus" });
  assert.equal(all.filter((f) => f.legs.length === 1).length, 2);   // each sharp-priced leg alone (Oct 22), never E
  const out = all.filter((f) => f.legs.length > 1);
  assert.equal(out.length, 1);                                       // only the two sharp-priced legs make a plain parlay
  assert.ok(out[0].plain && out[0].dec === out[0].low);
  assert.ok(Math.abs(out[0].dec - 2.1 * 2.05) < 1e-9);
  assert.ok(Math.abs(out[0].ev - 0.25 * (2.1 * 2.05 - 1)) < 1e-9);
  assert.equal(findPromo(pr, ["g1", "g2", "g3"], { kind: "bonus", minLegs: 3 }).length, 0);   // no 3-leg slip here
  const sgp = new Pricer({ g: game("g", [leg("A ML", "A", 0.5, 110, (i) => i % 2 === 0),
    ["Over 210.5", { label: "Over 210.5", stat: "total", side: "over", point: 210.5, p: 0.5, p_pack: 0.5, price: -110, bits: bits((i) => i < 50) }]]) });
  const s = findPromo(sgp, ["g"], { kind: "bonus" })[0];
  assert.ok(!s.plain && s.low < s.dec && Math.abs(s.low / s.dec - Math.exp(-0.12)) < 1e-9);
});

test("the finder skips two legs of one market and ranks by the promo's value", () => {
  const bits = (on) => Buffer.from(Uint8Array.from({ length: 100 }, (_, i) => (on(i) ? 255 : 0))).toString("base64");
  const L = (label, stat, p, price, on, x = {}) => [label, { label, stat, side: "over", point: 1, p, p_pack: p, price, bits: bits(on), ...x }];
  const legs = Object.fromEntries([
    L("Over 1.5 goals", "goals", 0.8, -300, (i) => i < 80),
    L("Over 2.5 goals", "goals", 0.5, 100, (i) => i < 50),
    L("A to win", "moneyline", 0.5, 110, (i) => i % 2 === 0, { side: "yes" }),
  ]);
  const pr = new Pricer({ g: { event_id: "g", matchup: "A @ B", commence_time: "", sport: "soccer", draws: 800, legs } });
  const out = findPromo(pr, ["g"], { kind: "bonus" });
  assert.ok(out.length >= 1);
  assert.ok(out.every((f) => !(f.legs.some((l) => l.label === "Over 1.5 goals") && f.legs.some((l) => l.label === "Over 2.5 goals"))));
  assert.deepEqual(out.map((f) => f.ev), [...out.map((f) => f.ev)].sort((a, b) => b - a));
});

test("a one-game token with a leg minimum gets slips of that many legs (Oct 26)", () => {
  // Mike: "if a boost has a leg minimum and it's for one game it never gives any options". The best-priced legs are
  // long shots; three of them ran past the +1500 fair cap and 4+ leg slips were never built.
  const bits = (on) => Buffer.from(Uint8Array.from({ length: 100 }, (_, i) => (on(i) ? 255 : 0))).toString("base64");
  const L = (player, p, price, on) => [`${player} over 0.5 yds`, { label: `${player} over 0.5 yds`, player, stat: "yds", side: "over",
    point: 0.5, p, p_pack: p, price, bits: bits(on), source: "pinnacle" }];
  const legs = Object.fromEntries([
    L("Long One", 0.1, 950, (i) => i < 10), L("Long Two", 0.1, 950, (i) => i >= 90), L("Long Three", 0.1, 950, (i) => i % 10 === 3),
    L("Likely A", 0.6, -140, (i) => i < 60), L("Likely B", 0.6, -140, (i) => i >= 40), L("Likely C", 0.8, -380, (i) => i % 5 !== 0),
    L("Likely D", 0.5, 105, (i) => i % 2 === 0),
  ]);
  const pr = new Pricer({ g: { event_id: "g", matchup: "A @ B", commence_time: "", sport: "nfl", draws: 800, legs } });
  for (const n of [3, 4]) {
    const out = findPromo(pr, ["g"], { kind: "boost", pct: 50, minLegs: n });
    assert.ok(out.length > 0, `${n}+ legs: some options`);
    assert.ok(out.every((f) => f.legs.length >= n && f.legs.length <= n + 1 && 1 / f.p <= 16), `${n}+ legs, under the cap`);
  }
});

const { lockValue, findLocks, opposite } = loader()(new URL("../lib/builder.ts", import.meta.url));

test("the two-book lock: both outcomes pay the same", () => {
  // a $10 bonus on +400 hedged at -450: $32.73 on the other side, $7.27 either way
  const v = lockValue(5, 1 + 100 / 450, { kind: "bonus" });
  assert.ok(Math.abs(v.hedge * 10 - 32.727) < 0.01 && Math.abs(v.locked * 10 - 7.273) < 0.01);
  assert.ok(Math.abs((4 - v.hedge) - v.hedge * (100 / 450)) < 1e-12);         // a wins = b wins
  // a 100% boost on a $10 cash stake at +150, hedged at -160: equal either way, and the cap shrinks it
  const dB = 1 + 100 / 160, b = lockValue(2.5, dB, { kind: "boost", pct: 100 });
  assert.ok(Math.abs((3 - b.hedge) - (b.hedge * (dB - 1) - 1)) < 1e-12 && b.locked > 0);
  assert.ok(lockValue(2.5, dB, { kind: "boost", pct: 100, stake: 10, maxExtra: 5 }).locked < b.locked);
  assert.equal(lockValue(2, 2, { kind: "none" }), null);
});

test("locks pair each side with its opposite at the other book and skip mismatched rungs", () => {
  const L = (label, x) => [label, { label, p: 0.5, p_pack: 0.5, bits: "", ...x }];
  const pk = { event_id: "g", matchup: "ANA @ NJD", commence_time: "", sport: "nhl", draws: 8, legs: Object.fromEntries([
    L("ANA to win", { stat: "moneyline", team: "ANA", side: "yes", p: 0.35, price: 164, dk_price: 175, not: "NJD to win" }),
    L("NJD to win", { stat: "moneyline", team: "NJD", side: "yes", p: 0.65, price: -200, dk_price: -190 }),
    L("Over 6.5 goals", { stat: "goals", side: "over", point: 6.5, price: -110, dk_price: -105 }),
    L("Under 6.5 goals", { stat: "goals", side: "under", point: 6.5, price: -110, dk_price: -115 }),
    // FanDuel's price here is a stand-in and DraftKings' rung doesn't match: never a lock
    L("NJD +1.5", { stat: "puck line", team: "NJD", side: "yes", point: 1.5, p: 0.8, price: -410, dk_price: -148, source: "fair price (FanDuel's isn't in the feed)" }),
    L("ANA -1.5", { stat: "puck line", team: "ANA", side: "yes", point: -1.5, p: 0.2, price: 410, dk_price: 124, not: "NJD +1.5" }),
  ]) };
  assert.equal(opposite(pk, pk.legs["NJD to win"]).label, "ANA to win");
  assert.equal(opposite(pk, pk.legs["Over 6.5 goals"]).label, "Under 6.5 goals");
  const fd = new Pricer({ g: pk }, "FanDuel"), dk = new Pricer({ g: pk }, "DraftKings");
  const out = findLocks(fd, dk, ["g"], { kind: "bonus" });
  assert.equal(out[0].promoLeg, "ANA to win");                               // the longest real price locks the most
  assert.equal(out[0].hedgeLeg, "NJD to win");
  assert.ok(Math.abs(out[0].locked - 1.64 * (1 - 1 / (1 + 100 / 190))) < 1e-9);
  assert.ok(out.every((k) => !k.promoLeg.includes("1.5") && !k.hedgeLeg.includes("1.5")));
  assert.equal(findLocks(fd, dk, ["g"], { kind: "boost", pct: 50, minLegs: 3 }).length, 0);  // a 3-leg token can't lock a single
});

test("a single priced off a sharp book is a promo pick at its exact price (Oct 22: the Kmet boost)", () => {
  const bits = (on) => Buffer.from(Uint8Array.from({ length: 100 }, (_, i) => (on(i) ? 255 : 0))).toString("base64");
  const legs = Object.fromEntries([["Cole Kmet over 1.5 receptions", { label: "Cole Kmet over 1.5 receptions", player: "Cole Kmet", stat: "receptions",
    side: "over", point: 1.5, p: 0.332, p_pack: 0.33, price: 178, bits: bits((i) => i < 33), source: "pinnacle" }]]);
  const pr = new Pricer({ g: { event_id: "g", matchup: "NE @ CHI", commence_time: "", sport: "nfl", draws: 800, legs } });
  const [k] = findPromo(pr, ["g"], { kind: "boost", pct: 100 });
  assert.ok(k && k.legs.length === 1 && k.plain && Math.abs(k.dec - 2.78) < 1e-9);
  assert.ok(Math.abs(k.ev - (0.332 * (2.78 + 1.78) - 1)) < 1e-9);          // +51%
  assert.equal(findPromo(pr, ["g"], { kind: "boost", pct: 100, minLegs: 2 }).length, 0);
});

test("a promo travels in a link and back, and its max odds keep long slips out", () => {
  const promo = { kind: "boost", pct: 50, stake: 25, minOdds: -200, maxOdds: 200000 };
  const href = B.promoHref(promo, "ev1");
  assert.equal(href, "/build?promo=boost&pct=50&game=ev1&stake=25&min=-200&max=200000");
  const sp = Object.fromEntries(new URL(href, "https://x").searchParams);
  assert.deepEqual(B.promoFromParams(sp), { promo: { kind: "boost", pct: 50, stake: 25, maxExtra: undefined, minLegs: undefined, minOdds: -200, maxOdds: 200000 }, game: "ev1" });
  assert.equal(B.promoFromParams({}), null);
  const capped = { kind: "boost", pct: 50, maxOdds: 300 };
  assert.equal(B.promoFits(capped, 1, 3.5), true);     // +250
  assert.equal(B.promoFits(capped, 1, 5), false);      // +400 is over +300
  assert.equal(B.promoFits({ kind: "boost", pct: 50, minOdds: -200 }, 1, 1.4), false);   // -250 is shorter than -200
});

test("at Novig a leg is there when Novig lists it, at its own price or its fair one, and the slip has Novig ids (Oct 28)", () => {
  const game = { event_id: "g", matchup: "A @ B", commence_time: "", sport: "nba", draws: 800, legs: {
    "A ML": { label: "A ML", p: 0.5, p_pack: 0.5, price: 110, nv_id: "id-a", nv_price: 102 },
    "X over 9.5 points": { label: "X over 9.5 points", p: 0.6, p_pack: 0.6, price: -140, nv_id: "id-x" },
    "Y over 4.5 rebounds": { label: "Y over 4.5 rebounds", p: 0.55, p_pack: 0.55, price: -120 } } };
  const pr = new Pricer({ g: game }, "Novig");
  assert.equal(pr.leg("g", "A ML").price, 102);
  assert.equal(pr.leg("g", "X over 9.5 points").price, -150);            // fair: no vig on an exchange
  assert.equal(pr.leg("g", "Y over 4.5 rebounds").unavailable, true);
  assert.deepEqual(pr.novigIds([{ event_id: "g", label: "A ML" }, { event_id: "g", label: "X over 9.5 points" }]), ["id-a", "id-x"]);
  assert.equal(pr.novigIds([{ event_id: "g", label: "A ML" }, { event_id: "g", label: "Y over 4.5 rebounds" }]), null);
  assert.ok(B.buildId([{ event_id: "g", label: "A ML" }], "Novig").endsWith("~nv"));
});

test("a Build slip's id carries its game day: the same legs another day are another slip (Nov 9)", () => {
  const legs = [{ event_id: "g", label: "Miles McBride over 1.5 threes" }];
  const pack = (t) => ({ g: { event_id: "g", matchup: "Knicks @ Heat", commence_time: t, sport: "nba", draws: 0, legs: {} } });
  const oct30 = new B.Pricer(pack("2026-10-30T23:30:00Z")), nov9 = new B.Pricer(pack("2026-11-10T00:30:00Z"));
  const legacy = B.buildId(legs);
  assert.equal(B.slipDay(nov9, legs), "2026-11-09");                     // 7:30 PM Eastern
  // nothing open under the old id: each game day gets its own id, steady within the day
  const a = B.slipId(oct30, legs, () => false), b = B.slipId(nov9, legs, () => false);
  assert.notEqual(a, b);
  assert.notEqual(b, legacy);
  assert.equal(b, B.slipId(nov9, legs, () => false));
  assert.equal(b, B.buildId(legs, "FanDuel", "2026-11-09"));
  // a slip placed under the old id and still open keeps it
  assert.equal(B.slipId(nov9, legs, (id) => id === legacy), legacy);
  assert.ok(B.slipId(new B.Pricer(pack("2026-11-10T00:30:00Z"), "DraftKings"), legs, () => false).endsWith("~dk"));
  // the iPhone's Build.id(day:) gives the same (BuildTests)
  assert.equal(B.buildId([{ event_id: "e", label: "Brunson Over 25.5 pts" }], "FanDuel", "2026-11-09"), "custom-276a704");
});
