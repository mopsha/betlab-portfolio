import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const G = loader()(new URL("../lib/gameday.ts", import.meta.url));

const NAMES = JSON.parse(readFileSync(new URL("../../tests/fixtures/bet_names.json", import.meta.url), "utf8"));

test("bets get short names: a parlay by who is in it, a single by its leg (tests/fixtures/bet_names.json)", () => {
  for (const c of NAMES.cases) assert.equal(G.betName({ legs: c.legs, label: c.label, price: c.price }, c.n), c.name, JSON.stringify(c.legs));
});

test("countdowns tick to the second and say now once passed", () => {
  const now = Date.parse("2026-10-24T17:00:00Z");
  assert.equal(G.countdown("2026-10-24T18:04:09Z", now), "1h 04m 09s");
  assert.equal(G.countdown("2026-10-24T17:12:30Z", now), "12m 30s");
  assert.equal(G.countdown("2026-10-24T16:59:00Z", now), "now");
});

test("the wall has one tile per game with every bet's legs on it, live games first", () => {
  const g = (key, state, start) => ({ key, sport: "ncaaf", espnId: key, state, detail: "", start, home: { name: "H", abbr: "H", score: 0 }, away: { name: "A", abbr: "A", score: 0 } });
  const leg = (label, gameKey) => ({ label, status: "live", current: null, target: null, unit: "", text: "", gameKey });
  const live = g("ncaaf:1", "in", "2026-10-24T16:00:00Z"), later = g("ncaaf:2", "pre", "2026-10-24T17:00:00Z");
  const bets = {
    b1: { games: [later, live], legs: [leg("Akron +2.5", "ncaaf:2"), leg("TCU -10.5", "ncaaf:1")], status: "live", hit: 0, total: 2 },
    b2: { games: [live], legs: [leg("TCU ML", "ncaaf:1")], status: "live", hit: 0, total: 1 },
  };
  const tiles = G.wallTiles(bets, { b1: "2-leg parlay +260", b2: "TCU ML -400" });
  assert.deepEqual(tiles.map((t) => t.game.key), ["ncaaf:1", "ncaaf:2"]);
  assert.deepEqual(tiles[0].legs.map((l) => [l.label, l.bet]), [["TCU -10.5", "2-leg parlay +260"], ["TCU ML", "TCU ML -400"]]);
});

test("a bet that's over leaves the wall, and a game with no live bet left goes with it", () => {
  const g = (key, state) => ({ key, sport: "nba", espnId: key, state, detail: "", start: "2026-10-24T23:00:00Z", home: { name: "H", abbr: "H", score: 0 }, away: { name: "A", abbr: "A", score: 0 } });
  const leg = (label, gameKey, status = "live") => ({ label, status, current: null, target: null, unit: "", text: "", gameKey });
  const a = g("nba:1", "in"), b = g("nba:2", "post");
  const bets = {
    dead: { games: [a, b], legs: [leg("X", "nba:2", "lost"), leg("Y", "nba:1")], status: "lost", hit: 0, total: 2 },
    won: { games: [b], legs: [leg("Z", "nba:2", "won")], status: "won", hit: 1, total: 1 },
    alive: { games: [a], legs: [leg("W", "nba:1")], status: "live", hit: 0, total: 1 },
  };
  const tiles = G.wallTiles(bets, { dead: "d", won: "w", alive: "a" });
  assert.deepEqual(tiles.map((x) => x.game.key), ["nba:1"]);
  assert.deepEqual(tiles[0].legs.map((l) => l.bet), ["a"]);
});

test("a game day is any open bet or a lock still to come", () => {
  assert.equal(G.isGameDay(0, 0), false);
  assert.equal(G.isGameDay(2, 0), true);
  assert.equal(G.isGameDay(0, 3), true);
});

test("the wall: biggest tile first, and a tile's legs keep their order whatever order the bets come back in", () => {
  const g = (key, state, start) => ({ key, sport: "nfl", espnId: key, state, detail: "", start, home: { name: "H", abbr: "H", score: 0 }, away: { name: "A", abbr: "A", score: 0 } });
  const leg = (label, gameKey) => ({ label, status: "live", current: null, target: null, unit: "", text: "", gameKey });
  const small = g("nfl:1", "in", "2026-10-25T17:00:00Z"), big = g("nfl:2", "pre", "2026-10-25T20:25:00Z");
  const b1 = { games: [small, big], legs: [leg("A1", "nfl:1"), leg("B1", "nfl:2"), leg("B2", "nfl:2")], status: "live", hit: 0, total: 3 };
  const b2 = { games: [big], legs: [leg("B3", "nfl:2")], status: "live", hit: 0, total: 1 };
  const names = { b1: "one", b2: "two" };
  const view = (bets) => G.wallTiles(bets, names).map((t) => `${t.game.key}:${t.legs.map((l) => l.label).join(",")}`);
  assert.deepEqual(view({ b1, b2 }), ["nfl:2:B1,B2,B3", "nfl:1:A1"]);   // 3 legs before 1, though that game is live
  assert.deepEqual(view({ b2, b1 }), view({ b1, b2 }));                  // the live check answered in another order
});
