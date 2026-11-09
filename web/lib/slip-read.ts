import "server-only";
// Snap a slip (Oct 24): Claude reads a sportsbook screenshot into a SlipRead (lib/slip.ts) with structured output, so
// the answer is always the schema's shape. The model writes legs in the app's own wording, which the live tracker,
// the graders and the leg alerts already read. Needs ANTHROPIC_API_KEY on the web service, like the chat.
import Anthropic from "@anthropic-ai/sdk";
import { SOCCER_LEAGUES, SPORTS, type SlipRead } from "./slip";

// Haiku (Mike, Oct 24: "why don't we use sonnet or haiku especially for just reading slips"): a slip is a short,
// well-defined extraction that you confirm before it's saved, so the cheapest model fits ($0.10/$0.50 per M tokens).
// Haiku has no server-side refusal fallback; a decline just says the slip couldn't be read.
const MODEL = "claude-haiku-5-5";

const nullable = (t: object) => ({ anyOf: [t, { type: "null" }] });
const BET = {
  type: "object", additionalProperties: false,
  required: ["book", "price", "boost_pct", "stake_dollars", "bonus", "protect", "reset", "placed_at", "legs"],
  properties: {
    book: { type: "string", enum: ["FanDuel", "DraftKings", "Novig", "Other"] },
    price: { type: "integer", description: "The book's own American odds for the whole bet BEFORE any profit boost (the struck-through number when a boost shows two)" },
    boost_pct: nullable({ type: "number", description: "Profit boost percent, e.g. 30 for a 30% PROFIT BOOST badge" }),
    stake_dollars: { type: "number", description: "Total wager in dollars (a bonus bet's face value), not the TOTAL CHARGED that adds Bet Protect+'s 3%" },
    bonus: { type: "boolean", description: "True when the slip says BONUS BET" },
    protect: { type: "boolean", description: "True when the slip shows BET PROTECT+ or a TOTAL CHARGED that includes 3% Bet Protect+" },
    reset: { type: "boolean", description: "True when the slip shows BET RESET TOKEN or BET RESET: a lost wager comes back as bonus bets. Not a BONUS BET: the stake is still cash" },
    placed_at: nullable({ type: "string", description: "When placed, Eastern time, ISO without zone: 2026-10-24T13:06:00" }),
    legs: {
      type: "array",
      items: {
        type: "object", additionalProperties: false, required: ["label", "matchup", "sport", "soccer_league"],
        properties: {
          label: { type: "string" },
          matchup: { type: "string", description: "Away @ Home with full team names for US sports; Home vs Away for soccer; Fighter vs Fighter" },
          sport: { type: "string", enum: [...SPORTS] },
          soccer_league: nullable({ type: "string", enum: [...SOCCER_LEAGUES] }),
        },
      },
    },
  },
};
// Several screenshots at once (Mike, Oct 25: "submit multiple pics in case it doesn't fit on one screen or multiple
// bets at once"): one answer with every bet they show.
const SCHEMA = { type: "object", additionalProperties: false, required: ["bets"], properties: { bets: { type: "array", items: BET } } };

const PROMPT = `Read these sportsbook bet slip screenshots into the schema: one entry in "bets" per bet. Several screenshots can be one long slip scrolled across screens (put it together as one bet and never count a leg twice where the screens overlap) or several different bets (one entry each). One leg per selection; a Same Game Parlay+ lists every selection inside it as its own leg.

Write each leg's label exactly in these forms (full team names, as ESPN writes them):
- Moneyline: "Kansas State Wildcats ML"; a soccer 3-way winner: "Chelsea to win"; soccer draw: "Draw"
- Spread: "Boise State Broncos -14.5"; a pick'em: "Kansas City Chiefs PK"
- Totals: "Over 52.5 total points" (football, basketball), "Over 2.5 goals" (soccer, hockey), "Over 1.5 rounds" (UFC); one team's own total: "New York Knicks over 110.5 points", "New York Rangers over 2.5 goals"
- A line on part of a game (first half, a quarter, a period, regulation only): keep the part in the label, right after the team or "Over"/"Under": "New York Knicks 1H -3.5", "New York Rangers 1st Period ML", "Over 45.5 1H total points", "New York Rangers 60 Min ML"; never write it as the full game's line
- Both teams to score: "Both teams to score"
- Player props: "Josh Giddey 7+ assists" for an alternate line shown as 7+ (or "To Record 7+"), "Day'Ron Sharpe over 2.5 assists" for an over/under line; stats as: points, rebounds, assists, threes, pts + reb + ast, receiving yds, rushing yds, rush + rec yds (rushing + receiving yards together), passing yds, receptions, shots on target, shots, shots on goal, saves, pts + reb, pts + ast, reb + ast, stl + blk (steals + blocks), turnovers, field goals made, free throws made, offensive rebounds, longest reception, longest rush, rush attempts (carries), pass attempts, completions, interceptions (thrown by a QB), tackles (tackles + assists), sacks, kicking points, blocked shots, hits, fouls (always "yds", never "yards")
- Game leaders: "Ja'Marr Chase most receiving yds", "Jalen Brunson most points"; cards: "Bukayo Saka to be carded"
- First scorers: "Jalen Brunson first basket", "Logan Cooley first goal scorer", "Bhayshul Tuten first TD scorer"; quarter, half and period stats: "Jalen Brunson over 7.5 1st quarter points", "Josh Hart over 4.5 2nd half rebounds", "Logan Cooley over 0.5 1st period points"; also longest completion, power play points
- Touchdowns: "Colston Loveland anytime TD" (also for "Anytime Touchdown Scorer"); two or more: "Josh Jacobs 2+ touchdowns"; by kind: "Bijan Robinson 1+ rushing tds", "Jared Goff 2+ passing tds", "Jared Goff over 1.5 passing tds"; an anytime goalscorer: "Lamine Yamal 1+ goals"; goal or assist: "Player to score or assist"; double-double / triple-double: "Karl-Anthony Towns double-double"
For soccer, also give the competition (soccer_league). If the slip doesn't show a field, use null.`;

export type SlipImage = { data: string; mediaType: "image/jpeg" | "image/png" | "image/webp" };

/** Every bet in the screenshots, in the order they show. */
export async function readSlips(images: SlipImage[]): Promise<SlipRead[]> {
  const client = new Anthropic();
  const message = await client.messages.create({
    model: MODEL,
    max_tokens: 16000,
    output_config: { effort: "medium", format: { type: "json_schema", schema: SCHEMA } },
    messages: [{ role: "user", content: [
      ...images.map((im, i) => [{ type: "text" as const, text: `Screenshot ${i + 1} of ${images.length}:` },
                                { type: "image" as const, source: { type: "base64" as const, media_type: im.mediaType, data: im.data } }]).flat(),
      { type: "text", text: PROMPT },
    ] }],
  });
  if (message.stop_reason === "refusal") throw new Error("The slip couldn't be read.");
  const text = message.content.flatMap((b) => (b.type === "text" ? [b.text] : [])).join("");
  const bets = ((JSON.parse(text) as { bets?: SlipRead[] }).bets ?? []).filter((b) => Array.isArray(b.legs) && b.legs.length);
  if (!bets.length) throw new Error("No selections found on those screenshots.");
  return bets;
}
