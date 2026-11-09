import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const sent = [];
const answer = { book: "FanDuel", price: 1100, boost_pct: null, stake_dollars: 5, bonus: true, placed_at: "2026-10-24T15:05:00",
  legs: [{ label: "Ohio Bobcats ML", matchup: "Eastern Michigan Eagles @ Ohio Bobcats", sport: "ncaaf", soccer_league: null }] };
class Fake { constructor() { this.messages = { create: async (p) => { sent.push(p); return { stop_reason: "end_turn", content: [{ type: "text", text: JSON.stringify({ bets: [answer] }) }] }; } }; } }
const R = loader({ "server-only": {}, "@anthropic-ai/sdk": { default: Fake, __esModule: true } })(new URL("../lib/slip-read.ts", import.meta.url));

test("screenshots are read by Haiku 5.5 together, with a strict schema of bets", async () => {
  const read = await R.readSlips([{ data: "AAAA", mediaType: "image/jpeg" }, { data: "BBBB", mediaType: "image/png" }]);
  assert.deepEqual(read, [answer]);
  const p = sent[0];
  assert.equal(p.model, "claude-haiku-5-5");
  assert.equal(p.fallbacks, undefined);          // Haiku has no server-side fallback
  assert.equal(p.output_config.format.type, "json_schema");
  assert.deepEqual(p.output_config.format.schema.required, ["bets"]);
  assert.deepEqual(p.output_config.format.schema.properties.bets.items.required, ["book", "price", "boost_pct", "stake_dollars", "bonus", "protect", "reset", "placed_at", "legs"]);
  const imgs = p.messages[0].content.filter((c) => c.type === "image");
  assert.deepEqual(imgs.map((c) => [c.source.data, c.source.media_type]), [["AAAA", "image/jpeg"], ["BBBB", "image/png"]]);
  assert.match(p.messages[0].content.at(-1).text, /never count a leg twice/);
});
