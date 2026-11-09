import "server-only";
// The promos wallet (Oct 30): Claude reads a screenshot of a book's promos or bonus-bet screen (FanDuel's "Bonus Bets",
// DraftKings' "My Offers", a profit-boost token) into each token's terms, with structured output; the wallet shows them
// to check before they're saved. Haiku, as for slips: a short, exact transcription. Each token goes out cleaned as it
// would be saved (promoDraft, Nov 9): sports as the finder's keys, the expiry in Eastern time with its offset, the id and
// status the iPhone's row decodes. The call has 45 seconds and one retry (the SDK's default was 10 minutes and two retries,
// so a slow read sat on "Reading…" with nothing to do).
// Nov 9 (Mike: "it should've read which book it's in just by look", "I should be able to send a bunch of boosts at once"):
// the book is always answered, from the app's look when no name shows; "Exp: 12h 31m" comes back as minutes; the kinds of
// leg a token is for ("Anytime TD scorer only") as LEG_CHOICES keys; and each screenshot is its own read, several at once.
// Later Nov 9 (Mike: a batch of FanDuel boosts came back with other books; "it should be better"): Sonnet, not Haiku, reads
// them; the book is one answer per screenshot (a screenshot is one app) with what gave it away, and a screenshot that
// can't tell takes the book the batch's others named (route.ts); every read's tokens go to the log for checking. The
// first real batch (10 FanDuel Rewards Hub shots, dark) showed what FanDuel's rewards screens look like: the prompt says so.
import Anthropic from "@anthropic-ai/sdk";
import { LEG_CHOICES, SPORT_CHOICES, etIso, type PromoRow } from "./promos";

export const READ_TIMEOUT_MS = 60_000;
export const MAX_IMAGES = 20;
const AT_ONCE = 6;

const MODEL = "claude-sonnet-5-5";
const N = (description: string) => ({ anyOf: [{ type: "number" }, { type: "null" }], description });

const SCHEMA = {
  type: "object", additionalProperties: false, required: ["book", "book_from", "promos"],
  properties: {
    book: { type: "string", enum: ["FanDuel", "DraftKings", "Novig", "unknown"],
            description: "The sportsbook whose app this screenshot is from: one answer for the whole screenshot" },
    book_from: { type: "string", enum: ["name", "look", "unknown"],
                 description: "name: the book's name or logo shows; look: only the app's colors and layout tell; unknown: neither" },
    promos: {
      type: "array",
      items: {
        type: "object", additionalProperties: false,
        required: ["kind", "amount_dollars", "pct", "max_extra_dollars", "min_legs", "min_odds", "max_odds", "sports", "teams",
                   "market", "leg_kinds", "expires_at", "expires_in_minutes", "note"],
        properties: {
          kind: { type: "string", enum: ["bonus", "boost"], description: "bonus: a bonus bet / free bet / bet credit (the stake isn't returned); boost: a profit boost" },
          amount_dollars: N("A bonus bet's dollar amount; a boost's max wager in dollars"),
          pct: N("A profit boost's size in percent, e.g. 30"),
          max_extra_dollars: N("A boost's cap on extra winnings in dollars"),
          min_legs: N("The fewest legs the token needs, e.g. 3"),
          min_odds: N("The shortest total odds allowed, American, e.g. -200"),
          max_odds: N("The longest total odds allowed, American"),
          sports: { anyOf: [{ type: "array", items: { type: "string", enum: SPORT_CHOICES.map(([k]) => k) } }, { type: "null" }],
                    description: "Sports it's limited to (ncaaf is college football, ncaab college basketball), else null" },
          teams: { anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }], description: "When it's only for certain games, the teams named, one per entry as written (e.g. [\"Knicks\", \"Celtics\"]), else null" },
          market: { anyOf: [{ type: "string", enum: ["moneyline", "spread", "total", "props"] }, { type: "null" }], description: "When it's only for one market: moneyline, spread, total or props (player props), else null" },
          leg_kinds: { anyOf: [{ type: "array", items: { type: "string", enum: LEG_CHOICES.map(([k]) => k) } }, { type: "null" }],
                       description: "When it's only for certain kinds of player bet, those kinds: tds = anytime touchdown scorer, first_td = first touchdown scorer, passing_yards, rushing_yards, receiving_yards, receptions, points, rebounds, assists, threes, pra = points + rebounds + assists, shots, saves, goals (a goalscorer). Else null" },
          expires_at: { anyOf: [{ type: "string" }, { type: "null" }], description: "When it expires, ISO 8601 with offset if the screen gives a date or time (Eastern time unless stated)" },
          expires_in_minutes: N("When the screen gives a countdown instead (\"Exp: 12h 31m\", \"Ends in 2d 4h\"), that countdown in minutes"),
          note: { anyOf: [{ type: "string" }, { type: "null" }], description: "Anything else the terms say, short" },
        },
      },
    },
  },
};

const PROMPT = (today: string) => `This is a screenshot of a sportsbook's promotions, bonus bets or profit boost tokens. Today is ${today} (Eastern). List every bonus bet and profit boost the user holds, one entry each, with its terms exactly as shown. A boost or bonus for one game or team ("Bills vs Vikings", "any Ohio State bet") lists those teams; one for a league ("Any NCAA Basketball Mens Games event") gives that sport. "3+ leg SGP/SGP+" means min_legs 3 (same-game only goes in the note). "No Min | $25 Max Wager" is a $25 amount; "+100 Min | +200000 Max Odds" are min_odds 100 and max_odds 200000. A boost for one kind of bet ("Anytime TD scorer", "First TD scorer only", "player points") gives those leg_kinds. Leave out offers they haven't claimed, deposit matches, and anything that isn't a bonus bet or a profit boost. A date like "Expires 11/01" means 11:59 PM Eastern that day; a countdown goes in expires_in_minutes.
The book (one for the whole screenshot): use its name or logo if it shows anywhere, including the top bar, the token's art or the terms ("FanDuel Sportsbook", "DK"). If not, go by the look. FanDuel: its Rewards Hub ("Sportsbook Rewards Club", a small shield logo, levels with gold shields, "Reward Restrictions", "Your Rewards") is dark navy and black with bright blue (#1493ff) buttons such as "Find bet" or "Go to event", profit boosts and bonus bets as "30% Profit Boost" or "$10.61 Bonus Bet" with "Exp: 11/12/2026" and a gold round icon; elsewhere FanDuel's app is white with the same bright blue. DraftKings: black with green (#53d337) and orange accents, its crown logo, "DK", "My Offers", "Dynasty Rewards", "Crowns". Novig: a prediction-market app with Yes/No style prices. A dark screen alone doesn't mean DraftKings: look for green and the crown. Answer unknown only if nothing tells.`;

export type PromoImage = { data: string; mediaType: "image/jpeg" | "image/png" | "image/webp" };
type Read = Partial<PromoRow> & { expires_in_minutes?: number | null };
/** One screenshot's read: its book (null when it couldn't tell), what told it, and its tokens with that book. */
export type ShotRead = { book: string | null; from: "name" | "look" | "unknown"; promos: Partial<PromoRow>[] };

/** One screenshot's tokens, as read (not yet cleaned): "unknown" book as null, a countdown as its expiry from `now`. */
export async function readOne(client: Anthropic, image: PromoImage, today: string, now: Date): Promise<ShotRead> {
  const message = await client.messages.create({
    model: MODEL,
    max_tokens: 4000,
    output_config: { effort: "low", format: { type: "json_schema", schema: SCHEMA } },
    messages: [{ role: "user", content: [
      { type: "image" as const, source: { type: "base64" as const, media_type: image.mediaType, data: image.data } },
      { type: "text", text: PROMPT(today) },
    ] }],
  });
  if (message.stop_reason === "refusal") throw new Error("That screenshot couldn't be read.");
  if (message.stop_reason === "max_tokens") throw new Error("Too many promos on one screenshot to read: crop it.");
  const text = message.content.flatMap((b) => (b.type === "text" ? [b.text] : [])).join("");
  let read: { book?: string; book_from?: ShotRead["from"]; promos?: Read[] };
  try { read = JSON.parse(text); } catch { throw new Error("The read came back garbled: try again."); }
  const book = read.book && read.book !== "unknown" ? read.book : null;
  const promos = (read.promos ?? []).map(({ expires_in_minutes, ...p }) => ({
    ...p,
    book,
    expires_at: p.expires_at || (expires_in_minutes && expires_in_minutes > 0 ? etIso(now.getTime() + expires_in_minutes * 60_000) : null),
  }));
  return { book, from: book ? read.book_from ?? "look" : "unknown", promos };
}

/** Every screenshot read on its own, AT_ONCE at a time. Each screenshot's tokens, or the error it hit. */
export async function readPromos(images: PromoImage[], today: string, now = new Date()): Promise<(ShotRead | Error)[]> {
  const client = new Anthropic({ timeout: READ_TIMEOUT_MS, maxRetries: 1 });
  const out: (ShotRead | Error)[] = new Array(images.length);
  let next = 0;
  async function worker() {
    while (next < images.length) {
      const i = next++;
      try { out[i] = await readOne(client, images[i], today, now); } catch (e) { out[i] = e as Error; }
    }
  }
  await Promise.all(Array.from({ length: Math.min(AT_ONCE, images.length) }, worker));
  return out;
}
