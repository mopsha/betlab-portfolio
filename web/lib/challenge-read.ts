import "server-only";
// Novig challenges (Oct 28): Claude reads a screenshot of Novig's Points > Challenges into the challenges' own words,
// one line each, with structured output. The worker parses the words (src/betlab/challenges.py `parse`), so the model
// only copies text and never interprets a rule. Haiku, as for slips: a short, exact transcription.
import Anthropic from "@anthropic-ai/sdk";

const MODEL = "claude-haiku-5-5";

const SCHEMA = {
  type: "object", additionalProperties: false, required: ["challenges"],
  properties: {
    challenges: {
      type: "array",
      items: {
        type: "object", additionalProperties: false, required: ["text", "points", "done"],
        properties: {
          text: { type: "string", description: "The challenge exactly as written, e.g. \"Place a parlay on Pro BB (M) (Min. 3 legs, 4.00x, $5)\"" },
          points: { anyOf: [{ type: "integer" }, { type: "null" }], description: "Points it earns, when shown (e.g. 50)" },
          done: { type: "boolean", description: "True when the screenshot shows it completed (a check mark)" },
        },
      },
    },
  },
};

const PROMPT = `These are screenshots of the Novig app's Points > Challenges screen. List every challenge exactly as written (for example "Place a straight trade on CFB (Min. $5)"), one entry each, in order. Leave out referrals and anything that isn't a challenge to place a bet. Points: the points per challenge when the screen says (e.g. "Earn 50 Points per challenge"), else null.`;

export type ChallengeImage = { data: string; mediaType: "image/jpeg" | "image/png" | "image/webp" };
export type ChallengeRead = { text: string; points: number | null; done: boolean };

export async function readChallenges(images: ChallengeImage[]): Promise<ChallengeRead[]> {
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
  const out = ((JSON.parse(text) as { challenges?: ChallengeRead[] }).challenges ?? []).filter((c) => c.text?.trim());
  if (!out.length) throw new Error("No challenges found on those screenshots.");
  return out;
}
