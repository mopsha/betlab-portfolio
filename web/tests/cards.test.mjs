import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const C = loader()(new URL("../lib/cards.ts", import.meta.url));

const bet = (id, legs, leg_results, extra = {}) => ({ bet_id: id, kind: "parlay", placed_at: "2026-10-24T20:00:00Z", price: 300, stake: 1,
  legs: legs.flat(), leg_results, ticket_status: leg_results.some((r) => r.result === "lost") ? "lost" : "won", mode: "real", ...extra });
const r = (leg, result) => ({ leg, result, value: null });

// an SGP+ over two games: the same "Both teams to score" twice, a team's win, and an NHL leg by code
const sgp = bet("b1", [["Both teams to score", "Over 2.5 goals"], ["Chelsea to win", "Both teams to score"]],
  [r("Both teams to score", "won"), r("Over 2.5 goals", "lost"), r("Chelsea to win", "won"), r("Both teams to score", "lost")]);
const nhl = bet("b2", [["OTT to win"]], [r("OTT to win", "won")]);
const groups = {
  b1: [{ sport: "soccer", matchup: "Venezia @ Genoa", legs: ["Both teams to score", "Over 2.5 goals"] },
       { sport: "soccer", matchup: "Chelsea vs Arsenal", legs: ["Chelsea to win", "Both teams to score"] }],
  b2: [{ sport: "nhl", matchup: "NYR @ OTT", legs: ["OTT to win"] }],
};
const grps = (b) => groups[b.bet_id];

test("game legs count for both teams; each leg keeps its own graded result", () => {
  const t = Object.fromEntries(C.teams([sgp, nhl], grps, 1).map((x) => [x.name, x]));
  assert.deepEqual([t.Genoa.won, t.Genoa.lost], [1, 1]);          // BTTS won, over lost
  assert.deepEqual([t.Venezia.won, t.Venezia.lost], [1, 1]);
  assert.deepEqual([t.Chelsea.won, t.Chelsea.lost], [1, 1]);      // its win, then its game's BTTS lost
  assert.deepEqual([t.Arsenal.won, t.Arsenal.lost], [0, 1]);
  assert.equal(t["Ottawa Senators"].won, 1);                       // the code read as the full name
  assert.equal(t.Chelsea.bets, 1);
});

test("a picture's card: a player by name, a team by ESPN's name or code", () => {
  const props = bet("b3", [["Chris Olave 50+ receiving yds"]], [r("Chris Olave 50+ receiving yds", "won")], { kind: "custom" });
  const all = [sgp, nhl, props], g = (b) => groups[b.bet_id] ?? [];
  assert.equal(C.cardOf(all, g, { kind: "player", name: "Chris Olave" }).won, 1);
  assert.equal(C.cardOf(all, g, { kind: "team", name: "Ottawa Senators", abbr: "OTT" }).legs.length, 1);
  assert.equal(C.cardOf(all, g, { kind: "team", name: "Genoa CFC", abbr: "GEN" })?.legs.length ?? 0, 2);
  assert.equal(C.cardOf(all, g, { kind: "team", name: "Boston Bruins", abbr: "BOS" }), null);
});

test("a team's card never takes another team from the same city (Oct 25: the Knicks card had NYCFC, Rangers, Jets)", () => {
  const legs = [["New York Knicks ML", "nba", "Boston Celtics @ New York Knicks"], ["NYR to win", "nhl", "NYR @ OTT"],
                ["NYI to win", "nhl", "NYI @ BOS"], ["New York Jets ML", "nfl", "New York Jets @ Miami Dolphins"],
                ["Both teams to score", "soccer", "New York City FC @ Orlando City SC"]];
  const bets = legs.map(([l], i) => bet(`k${i}`, [[l]], [r(l, "won")]));
  const grps = (b) => { const [l, sport, matchup] = legs[Number(b.bet_id.slice(1))]; return [{ sport, matchup, legs: [l] }]; };
  const knicks = C.cardOf(bets, grps, { kind: "team", name: "New York Knicks", abbr: "NY" });
  assert.deepEqual(knicks.legs.map((l) => l.label), ["New York Knicks ML"]);
  assert.equal(C.cardOf(bets, grps, { kind: "team", name: "New York Rangers", abbr: "NYR" }).legs.length, 1);
  assert.equal(C.sameTeam("Brighton and Hove Albion", "Brighton & Hove Albion"), true);
  assert.equal(C.sameTeam("Bournemouth", "AFC Bournemouth"), true);
  assert.equal(C.sameTeam("New York City FC", "New York Knicks"), false);
});
