import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const S = loader()(new URL("../lib/social.ts", import.meta.url));

const ME = "me", G = "sam-id", C = "cal-id";
const profiles = [{ user_id: ME, name: "Mike", handle: "mike" }, { user_id: G, name: "Sam", handle: "sam" },
                  { user_id: C, name: "Cal", handle: "cal" }];
const bet = (o) => ({ bet_id: "b1", user_id: G, kind: "custom", pick_id: null, sgp_id: "custom-fd-snap-1", mode: "real", price: 450,
  stake: 0.8, book: "DraftKings", label: null, matchup: "x", legs: ["A ML", "B 3+ receptions"], games: [{ matchup: "x", legs: ["A ML"] }],
  fair_price: 400, p_fair: 0.2, odds_event_id: null, placed_at: "2026-10-27T15:00:00Z", bonus: true, boost: 30, protect: true, reset: true, cashout: null,
  ladder_id: "l1", ticket_status: null, pick_status: null, game_start: "2026-10-27T17:00:00Z", ...o });

test("handles: cleaned, checked, and suggested from an email", () => {
  assert.equal(S.cleanHandle(" @Mike_B "), "mike_b");
  assert.equal(S.cleanHandle("ab"), null);
  assert.equal(S.cleanHandle("has space"), null);
  assert.equal(S.suggestHandle("owner@example.com"), "owner");
  assert.equal(S.suggestHandle("al@x.com"), "al_bets");
});

test("the circle: friends, requests to answer and requests waiting on someone else", () => {
  const list = [
    { requester: G, addressee: ME, status: "accepted" },
    { requester: C, addressee: ME, status: "pending" },
    { requester: ME, addressee: "dana-id", status: "pending" },
  ];
  const c = S.circle(ME, list, profiles);
  assert.deepEqual(c.friends.map((p) => p.handle), ["sam"]);
  assert.deepEqual(c.incoming.map((r) => r.otherId), [C]);
  assert.deepEqual(c.outgoing.map((r) => [r.otherId, r.other]), [["dana-id", null]]);
});

test("Tail is open until the game starts, never once settled; a bet with no game closes after 6 hours", () => {
  const now = new Date("2026-10-27T16:00:00Z");
  assert.equal(S.canTail(bet({}), now), true);
  assert.equal(S.canTail(bet({ game_start: "2026-10-27T15:30:00Z" }), now), false);
  assert.equal(S.canTail(bet({ ticket_status: "lost" }), now), false);
  assert.equal(S.canTail(bet({ live_settled: "lost" }), now), false);
  assert.equal(S.canTail(bet({ game_start: null }), now), true);                                     // entered an hour ago
  assert.equal(S.canTail(bet({ game_start: null, placed_at: "2026-10-27T08:00:00Z" }), now), false);
});

test("a tail copies the bet, not the friend's slip: your price, book and unit; never their bonus, boost or ladder", () => {
  const r = S.tailRow(bet({}), { price: 425, book: "FanDuel", real: true });
  assert.deepEqual([r.kind, r.sgp_id, r.pick_id, r.price, r.book, r.stake, r.mode], ["custom", "custom-fd-snap-1", null, 425, "FanDuel", 1, "real"]);
  assert.deepEqual(r.legs, ["A ML", "B 3+ receptions"]);
  assert.deepEqual(r.games, [{ matchup: "x", legs: ["A ML"] }]);
  for (const k of ["bonus", "boost", "protect", "reset", "cashout", "ladder_id", "user_id", "bet_id", "boost_cap", "promo_id", "lock_id", "promo_ev"]) assert.equal(k in r, false, k);
  const pick = S.tailRow(bet({ kind: "pick", pick_id: "p9", sgp_id: null }), { price: -110, book: "DraftKings", real: false });
  assert.deepEqual([pick.pick_id, pick.sgp_id, pick.mode, pick.stake], ["p9", null, "paper", null]);
  assert.equal(S.betKey(pick), "p:p9");
});

test("the feed: friends' bets only, newest first, each with who placed it", () => {
  const f = S.feed([bet({ bet_id: "old", placed_at: "2026-10-25T10:00:00Z" }), bet({ bet_id: "new" }), bet({ bet_id: "x", user_id: C })],
                   profiles.filter((p) => p.user_id === G));
  assert.deepEqual(f.map((x) => [x.bet.bet_id, x.who.name]), [["new", "Sam"], ["old", "Sam"]]);
});

const RX = JSON.parse(readFileSync(new URL("../../tests/fixtures/reactions.json", import.meta.url), "utf8"));

test("reactions: tally, a tap, and who (tests/fixtures/reactions.json, Nov 6)", () => {
  for (const c of RX.tally) assert.deepEqual(S.tally(c.reactions, RX.me), c.want, c.case);
  for (const c of RX.next) assert.equal(S.nextReaction(c.current, c.tapped), c.want);
  for (const c of RX.who) assert.equal(S.whoText(c.names), c.want);
  assert.deepEqual(S.REACTIONS.map((r) => r.key), ["fire", "money", "sweat", "skull", "pray", "goat"]);   // migration 0042's check
});

test("a friend's profile shows, and the tracker follows, their counted open bets and 15 most recent settled ones (Nov 9)", () => {
  const settled = Array.from({ length: 20 }, (_, i) => bet({ bet_id: `s${i}`, ticket_status: "won", placed_at: `2026-10-${String(i + 1).padStart(2, "0")}T15:00:00Z` }));
  const open = [bet({ bet_id: "o2", game_start: "2026-11-10T01:00:00Z" }), bet({ bet_id: "o1", game_start: "2026-11-09T18:00:00Z" })];
  const paper = bet({ bet_id: "p1", mode: "paper" });
  const got = S.profileBets([...settled, ...open, paper]);
  assert.deepEqual(got.open.map((b) => b.bet_id), ["o1", "o2"]);
  assert.equal(got.recent.length, S.PROFILE_RECENT);
  assert.equal(got.recent[0].bet_id, "s19");
  assert.ok(!got.counted.some((b) => b.bet_id === "p1"));          // real bets only once they have any
});
