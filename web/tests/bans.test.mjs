import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { loader } from "./load-ts.mjs";

// The cases src/betlab/bans.py and ios/BetLab/Core/Bans.swift run too: all three must answer them alike.
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/bans.json", import.meta.url), "utf8"));
const B = loader()(new URL("../lib/bans.ts", import.meta.url));

test("the shared ban cases", () => {
  for (const c of FIX.cases) assert.equal(B.isBanned(B.cleanBans(c.bans), c.label, c.league ?? null, c.player ?? null), c.hit, JSON.stringify(c));
});

test("a ticket with a banned leg, in its legs or its games' legs", () => {
  const bans = B.cleanBans([{ kind: "player", name: "Josh Allen" }]);
  assert.equal(B.ticketBanned(bans, { legs: [{ label: "Josh Allen 250+ passing yds", player: "Josh Allen" }] }, "nfl"), true);
  assert.equal(B.ticketBanned(bans, { games: [{ legs: [{ label: "KC ML" }, { label: "Josh Allen anytime TD" }] }] }, "nfl"), true);
  assert.equal(B.ticketBanned(bans, { label: "James Cook 60+ rushing yds" }, "nfl"), false);
  assert.equal(B.ticketBanned([], { label: "Josh Allen 250+ passing yds" }, "nfl"), false);
});
