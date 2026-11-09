import "server-only";
// College Football Pick'em (Nov 7): Claude reads screenshots of FanDuel's Pick'em Questions screen (two teams a
// question, each with its frozen spread, the picked one highlighted) into rows. Haiku, as for slips and challenges: a
// transcription, in screen order; the worker matches the pair to the week's game and swaps home and away if needed.
import Anthropic from "@anthropic-ai/sdk";

const MODEL = "claude-haiku-5-5";

const SCHEMA = {
  type: "object", additionalProperties: false, required: ["games"],
  properties: {
    games: {
      type: "array",
      items: {
        type: "object", additionalProperties: false, required: ["first", "second", "second_line", "picked"],
        properties: {
          first: { type: "string", description: "The team listed first in the question, without its rank, e.g. \"Iowa\"" },
          second: { type: "string", description: "The team listed second, without its rank, e.g. \"Northwestern\"" },
          second_line: { type: "number", description: "The second team's spread as shown, e.g. -2.5 for \"Northwestern -2.5\", 5.5 for \"Miami +5.5\"" },
          picked: { type: "string", enum: ["first", "second", "none"], description: "Which team is selected (highlighted, filled radio), or none" },
        },
      },
    },
  },
};

const PROMPT = `These are screenshots of FanDuel's College Football Pick'em "Questions" screen. Each question "Which team will cover the spread?" shows two teams, each with its spread (e.g. "#19 Iowa +2.5" and "Northwestern -2.5"), and the selected team is highlighted in blue with a filled radio button. List every question in screen order, once each (the same question may appear in two screenshots: list it once). Drop the ranks ("#19"). second_line is the second team's spread with its sign.`;

export type PickemImage = { data: string; mediaType: "image/jpeg" | "image/png" | "image/webp" };
export type PickemRead = { first: string; second: string; second_line: number; picked: "first" | "second" | "none" };

export async function readPickem(images: PickemImage[]): Promise<PickemRead[]> {
  const client = new Anthropic();
  const message = await client.messages.create({
    model: MODEL,
    max_tokens: 4000,
    output_config: { effort: "low", format: { type: "json_schema", schema: SCHEMA } },
    messages: [{ role: "user", content: [
      ...images.map((im) => ({ type: "image" as const, source: { type: "base64" as const, media_type: im.mediaType, data: im.data } })),
      { type: "text", text: PROMPT },
    ] }],
  });
  if (message.stop_reason === "refusal") throw new Error("Those screenshots couldn't be read.");
  const text = message.content.flatMap((b) => (b.type === "text" ? [b.text] : [])).join("");
  const out = ((JSON.parse(text) as { games?: PickemRead[] }).games ?? []).filter((g) => g.first?.trim() && g.second?.trim());
  if (!out.length) throw new Error("No pick'em questions found on those screenshots.");
  const seen = new Set<string>();
  return out.filter((g) => { const k = `${g.first.trim()}|${g.second.trim()}`.toLowerCase(); if (seen.has(k)) return false; seen.add(k); return true; });
}
