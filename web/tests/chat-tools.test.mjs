import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

// lib/chat.ts with the SDK and the data layer stubbed: the tools' answers and the request it sends (no API call).
const sent = [];
class FakeAnthropic {
  constructor() { this.beta = { messages: { toolRunner: async (p) => { sent.push(p); return { stop_reason: "end_turn", content: [{ type: "text", text: "Take Akron +2.5." }] }; } } }; }
}
FakeAnthropic.APIError = class extends Error {};

const bet = (id, extra = {}) => ({ bet_id: id, kind: "custom", mode: "real", price: 940, stake: 1, book: "FanDuel", label: "Bonus bet $5",
  legs: ["TCU Horned Frogs -10.5", "Akron Zips +2.5"], placed_at: "2026-10-24T15:50:00Z", bonus: true, boost: null, pick_status: null, ticket_status: null, ...extra });
const data = {
  myBetsData: async () => ({ bets: [bet("b1"), bet("b2", { ticket_status: "won", profit_1u: 9.4, legs: ["LSU Tigers ML"], price: -265, bonus: false })], settings: { real_from: null } }),
  openBetNames: async () => [{ id: "b1", name: "2-leg parlay +940" }],
  homeData: async () => ({ picks: [{ tier: "pick", label: "Akron Zips +2.5", matchup: "Akron Zips @ Kent State Golden Flashes", commence_time: "2026-10-24T17:00:00Z",
    price: 102, book: "FanDuel", ev: 0.031, p_final: 0.51, league: "ncaaf", game_id: "401866446", why: "x".repeat(900) }], items: [], nextLocks: [], quiet: 3 }),
  allGames: async () => ({ games: [{ game_id: "401866446", league: "ncaaf", matchup: "Akron Zips @ Kent State Golden Flashes", commence_time: "2026-10-24T17:00:00Z" }] }),
  gameData: async () => ({ offers: [], tickets: [], analysis: { read: { gap: 3 } } }),
};
const live = { liveBets: async () => ({ bets: { b1: { status: "live", games: [], legs: [{ label: "TCU Horned Frogs -10.5", status: "losing", text: "Short by 3.5" }] } } }) };
const C = loader({
  "server-only": {}, "@anthropic-ai/sdk": { default: FakeAnthropic, __esModule: true },
  "@anthropic-ai/sdk/helpers/beta/json-schema": { betaTool: (o) => o }, "./data": data, "./live-bets": live,
})(new URL("../lib/chat.ts", import.meta.url));

const tool = (name) => C.TOOLS.find((t) => t.name === name);

test("open bets carry their name and live legs", async () => {
  const out = JSON.parse(await tool("my_open_bets").run({}));
  assert.equal(out.length, 1);
  assert.equal(out[0].name, "2-leg parlay +940");
  assert.deepEqual(out[0].legs, [{ leg: "TCU Horned Frogs -10.5", status: "losing", now: "Short by 3.5" }]);
});

test("the board links each pick to its game page and keeps the why short", async () => {
  const out = JSON.parse(await tool("todays_board").run({}));
  assert.equal(out.picks[0].url, "/games/ncaaf/401866446");
  assert.ok(out.picks[0].why.length <= 401);
});

test("a game is found by any part of its name; none says so", async () => {
  assert.equal(JSON.parse(await tool("game_details").run({ team: "kent state" }))[0].url, "/games/ncaaf/401866446");
  assert.match(await tool("game_details").run({ team: "Knicks" }), /No upcoming game/);
});

test("the record counts settled bets only", async () => {
  const out = JSON.parse(await tool("my_record").run({}));
  assert.equal(out.recent.length, 1);
  assert.equal(out.recent[0].status, "won");
});

test("the request: Sonnet 5.5 with the fallback, the four tools and a round cap", async () => {
  process.env.ANTHROPIC_API_KEY = "test";
  assert.equal(await C.answer([{ role: "user", content: "best bet?" }]), "Take Akron +2.5.");
  const p = sent.at(-1);
  assert.equal(p.model, "claude-sonnet-5-5");
  assert.equal(p.output_config.effort, "low");
  assert.deepEqual(p.betas, ["server-side-fallback-2026-07-01"]);
  assert.equal(p.fallbacks, "default");
  assert.equal(p.tools.length, 4);
  assert.equal(p.max_iterations, 8);
  delete process.env.ANTHROPIC_API_KEY;
});
