import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const S = loader()(new URL("../lib/slip.ts", import.meta.url));

const games = [
  { game_id: "ncaaf:401856731", league: "ncaaf", home: "South Carolina Gamecocks", away: "Tennessee Volunteers", matchup: "Tennessee Volunteers @ South Carolina Gamecocks", commence_time: "2026-10-24T19:30:00+00:00" },
  { game_id: "nfl:2026_07_CLE_TEN", league: "nfl", home: "Tennessee Titans", away: "Cleveland Browns", matchup: "Cleveland Browns @ Tennessee Titans", commence_time: "2026-10-25T17:00:00+00:00" },
  { game_id: "nba:abc", league: "nba", home: "Chicago Bulls", away: "Washington Wizards", matchup: "Washington Wizards @ Chicago Bulls", commence_time: "2026-10-24T23:10:00+00:00" },
  { game_id: "soccer:def", league: "soccer", home: "Napoli", away: "AS Roma", matchup: "Napoli vs AS Roma", commence_time: "2026-10-24T16:00:00+00:00" },
  { game_id: "ufc:ghi", league: "ufc", home: null, away: null, matchup: "Merab Dvalishvili vs Petr Yán", commence_time: "2026-10-24T18:00:00+00:00" },
];
const read = {
  book: "FanDuel", price: 978, boost_pct: 30, stake_dollars: 5, bonus: false, placed_at: "2026-10-24T13:06:00",
  legs: [
    { label: "Tennessee Volunteers ML", matchup: "Tennessee @ South Carolina", sport: "ncaaf", soccer_league: null },
    { label: "Josh Giddey 7+ assists", matchup: "Wizards @ Bulls", sport: "nba", soccer_league: null },
    { label: "Over 2.5 goals", matchup: "Napoli vs Roma", sport: "soccer", soccer_league: "serie_a" },
    { label: "Petr Yan ML", matchup: "Petr Yan vs Merab Dvalishvili", sport: "ufc", soccer_league: null },
    { label: "Cleveland Browns +3.5", matchup: "Browns @ Titans", sport: "nfl", soccer_league: null },
    { label: "Some team ML", matchup: "Nobody @ Nowhere", sport: "nfl", soccer_league: null },
  ],
};

test("each leg matches the app's game and gets the ref its grader reads", () => {
  const d = S.draft(read, games, new Date("2026-10-24T17:10:00Z"));
  assert.deepEqual(d.legs.map((l) => l.game_ref), [
    "ncaaf:401856731", "nba|CHI|WSH|2026-10-24T23:10:00+00:00", "serie_a|Napoli|AS Roma|2026-10-24T16:00:00+00:00", null, "2026_07_CLE_TEN", null]);
  assert.deepEqual(d.legs.map((l) => l.matched), [true, true, true, true, true, false]);
  assert.equal(d.legs[0].matchup, "Tennessee Volunteers @ South Carolina Gamecocks");   // the app's full names
  assert.equal(d.legs[5].matchup, "Nobody @ Nowhere");
});

test("NFL and NHL rows hold team codes: a slip's full names still match", () => {
  const coded = [{ game_id: "nfl:2026_07_PIT_NO", league: "nfl", home: "NO", away: "PIT", matchup: "Pittsburgh Steelers @ New Orleans Saints", commence_time: "2026-10-25T13:30:00+00:00" },
                 { game_id: "nhl:2026020180", league: "nhl", home: "CHI", away: "FLA", matchup: "FLA @ CHI", commence_time: "2026-10-25T19:00:00+00:00" }];
  const d = S.draft({ ...read, placed_at: "2026-10-25T09:03:00", legs: [
    { label: "DK Metcalf anytime TD", matchup: "Pittsburgh Steelers @ New Orleans Saints", sport: "nfl", soccer_league: null },
    { label: "Florida Panthers ML", matchup: "Florida Panthers @ Chicago Blackhawks", sport: "nhl", soccer_league: null }] }, coded);
  assert.deepEqual(d.legs.map((l) => l.game_ref), ["2026_07_PIT_NO", "nhl:2026020180"]);
});

test("a college or NHL game with the Odds API's hex id gets no ref: the worker finds the grader's own (Nov 9)", () => {
  const hex = [{ game_id: "ncaaf:0842fcd69fdf5061f6751f876ead09f2", league: "ncaaf", home: "Georgia Bulldogs", away: "Florida Gators",
                 matchup: "Florida Gators @ Georgia Bulldogs", commence_time: "2026-11-07T20:30:00+00:00" },
               { game_id: "ncaab:4aac00e6cc06b8905659f911419540d2", league: "ncaab", home: "Duke Blue Devils", away: "Army Black Knights",
                 matchup: "Army Black Knights @ Duke Blue Devils", commence_time: "2026-11-07T23:00:00+00:00" }];
  const d = S.draft({ ...read, placed_at: "2026-11-07T12:00:00", legs: [
    { label: "Georgia Bulldogs ML", matchup: "Florida @ Georgia", sport: "ncaaf", soccer_league: null },
    { label: "Duke Blue Devils -20.5", matchup: "Army @ Duke", sport: "ncaab", soccer_league: null }] }, hex);
  assert.deepEqual(d.legs.map((l) => [l.matched, l.game_ref, l.matchup]),
    [[true, null, "Florida Gators @ Georgia Bulldogs"], [true, null, "Army Black Knights @ Duke Blue Devils"]]);
});

test("a UFC leg matches its fight on last names (no sides in the games table) and takes the fight's ESPN ref", () => {
  const refs = { "ufc:ghi": "ufc:600061267:401911634" };
  const d = S.draft(read, games, new Date("2026-10-24T17:10:00Z"), refs);
  assert.equal(d.legs[3].game_ref, "ufc:600061267:401911634");
  assert.equal(d.legs[3].matchup, "Merab Dvalishvili vs Petr Yán");
  const other = S.draft({ ...read, legs: [{ label: "Over 1.5 rounds", matchup: "Yan vs Volkov", sport: "ufc", soccer_league: null }] },
                        games, new Date("2026-10-24T17:10:00Z"), refs);
  assert.equal(other.legs[0].matched, false);                 // one fighter in common is another fight
});

test("the saved row: units from the unit size, the usual label, legs grouped by game", () => {
  const d = S.draft({ ...read, legs: read.legs.slice(0, 3) }, games);
  const row = S.betRow(d, 5, "2026-10-24T17:06:00.000Z", "abcd1234");
  assert.equal(row.stake, 1);
  assert.equal(row.sgp_id, "custom-fd-snap-abcd1234");
  assert.equal(row.label, "$5 cash, 30% profit boost (+978 -> +1271)");
  assert.equal(row.matchup, "Parlay Sat, Oct 24 · 3 legs");
  assert.deepEqual(row.games.map((g) => [g.game_ref, g.legs]), [["ncaaf:401856731", ["Tennessee Volunteers ML"]],
    ["nba|CHI|WSH|2026-10-24T23:10:00+00:00", ["Josh Giddey 7+ assists"]], ["serie_a|Napoli|AS Roma|2026-10-24T16:00:00+00:00", ["Over 2.5 goals"]]]);
  assert.deepEqual(row.games.map((g) => g.sport), ["ncaaf", "nba", "soccer"]);     // a game with no ref grades by it
  const bonus = S.betRow({ ...d, bonus: true, boost_pct: null, stake_dollars: 10, book: "DraftKings" }, 5, "2026-10-24T17:06:00.000Z", "x");
  assert.equal(bonus.label, "Bonus bet $10");
  assert.equal(bonus.stake, 2);
  assert.equal(bonus.sgp_id, "custom-dk-snap-x");
});

test("a slip's Eastern time becomes the right instant in daylight and standard time", () => {
  assert.equal(S.easternIso("2026-10-24T13:06:00"), "2026-10-24T17:06:00.000Z");   // EDT
  assert.equal(S.easternIso("2026-12-05T20:00:00"), "2026-12-06T01:00:00.000Z");   // EST
  assert.equal(S.easternIso("2026-11-01T03:00:00"), "2026-11-01T08:00:00.000Z");   // clock-change day: after the change
  assert.equal(S.easternIso("2026-11-01T06:30:00"), "2026-11-01T11:30:00.000Z");
  assert.equal(S.easternIso("2027-03-14T03:30:00"), "2027-03-14T07:30:00.000Z");   // spring: after the change
});

// Oct 27: four of Oct 25's slips were read at 2-4.6x their legs' own prices multiplied (impossible for a parlay)
const leg = (label, event_id) => ({ label, matchup: "x", sport: "nfl", game_ref: null, start: null, matched: true, event_id });
const packs = {
  ev1: [{ label: "Justin Jefferson 50+ receiving yds", price: -330, dk_price: -300 },
        { label: "Kyler Murray 175+ passing yds", price: -270, dk_price: -250, dk_moved: true },
        { label: "Darnell Washington over 2.5 receptions", price: 100, dk_price: -105 }],
  ev2: [{ label: "J.J. McCarthy 150+ passing yds", price: -350 }, { label: "Garrett Wilson 3+ receptions", price: -1800 }],
};

test("each leg gets its own book prices from its game's pack, in either way of writing the line", () => {
  const d = S.withPrices({ book: "FanDuel", price: 3038, legs: [
    leg("Justin Jefferson 50+ receiving yards", "ev1"), leg("Kyler Murray 175+ passing yds", "ev1"),
    leg("Darnell Washington 3+ receptions", "ev1"), leg("J.J McCarthy 150+ passing yds", "ev2"),
    leg("Garrett Wilson over 2.5 receptions", "ev2"), leg("Someone 9+ receptions", "ev2"), leg("No game ML", null)] }, packs);
  assert.deepEqual(d.legs.map((l) => l.prices), [
    { FanDuel: -330, DraftKings: -300 }, { FanDuel: -270 }, { FanDuel: 100, DraftKings: -105 }, { FanDuel: -350 },
    { FanDuel: -1800 }, undefined, undefined]);
});

test("a read price far above the legs multiplied is flagged; a fitting one isn't; a leg with no price skips the check", () => {
  const legs = S.withPrices({ legs: [leg("Justin Jefferson 50+ receiving yds", "ev1"), leg("Kyler Murray 175+ passing yds", "ev1"),
                                     leg("Garrett Wilson 3+ receptions", "ev2")] }, packs).legs;
  const bad = S.priceCheck(legs, "FanDuel", 3038);   // the legs multiply to -113 (1.885)
  assert.equal(bad.flag, true);
  assert.equal(bad.legs_price, -113);
  assert.ok(bad.ratio > 15);
  assert.equal(S.priceCheck(legs, "FanDuel", -150).flag, false);  // a same-game price under the product
  assert.equal(S.priceCheck(legs, "FanDuel", 130).flag, false);   // a little over: still fits
  assert.equal(S.priceCheck(legs, "DraftKings", 3038), null);     // Murray's DraftKings number moved: no price there
  assert.equal(S.priceCheck(legs, "Novig", 3038), null);
  assert.equal(S.priceCheck([...legs, leg("Unknown 1+ goals", "ev2")], "FanDuel", 3038), null);
});

test("an odds-on boosted price stays odds-on in the label (Nov 9: -200 with 30% read '+65')", () => {
  const d = S.draft({ ...read, price: -200, boost_pct: 30, legs: [read.legs[0]] }, games, new Date("2026-10-24T17:10:00Z"));
  assert.equal(S.betRow(d, 5, "2026-10-24T17:06:00.000Z", "x").label, "$5 cash, 30% profit boost (-200 -> -154)");
  const even = S.draft({ ...read, price: -110, boost_pct: 50, legs: [read.legs[0]] }, games, new Date("2026-10-24T17:10:00Z"));
  assert.equal(S.betRow(even, 5, "2026-10-24T17:06:00.000Z", "x").label, "$5 cash, 50% profit boost (-110 -> +136)");
});

test("a leg with no game can be put on one of the day's games, with its grader's ref (Nov 9)", () => {
  const placed = "2026-10-24T17:06:00.000Z";
  const choices = S.gameChoices(read, games, placed);
  assert.deepEqual(choices.map((c) => c.sport), ["soccer", "ufc", "ncaaf", "nba", "nfl"]);      // soonest first
  assert.equal(choices.find((c) => c.sport === "soccer").game_ref, "serie_a|Napoli|AS Roma|2026-10-24T16:00:00+00:00");
  const d = S.draft(read, games, new Date("2026-10-24T17:10:00Z"));
  const lost = d.legs[5];
  assert.equal(lost.matched, false);
  const put = S.chooseGame(lost, choices.find((c) => c.sport === "nfl"));
  assert.deepEqual([put.matched, put.matchup, put.game_ref, put.label], [true, "Cleveland Browns @ Tennessee Titans", "2026_07_CLE_TEN", "Some team ML"]);
  // a game long after the slip isn't offered
  assert.equal(S.gameChoices(read, [{ ...games[1], commence_time: "2026-11-04T17:00:00+00:00" }], placed).length, 0);
});
