import Anthropic from "@anthropic-ai/sdk";
import { chatReady } from "@/lib/chat";
import { gamesAround, packParts, ufcRefs } from "@/lib/data";
import { mergePack } from "@/lib/builder";
import { draft, easternIso, gameChoices, slipFair, withPrices } from "@/lib/slip";
import { readSlips, type SlipImage } from "@/lib/slip-read";

export const dynamic = "force-dynamic";
export const maxDuration = 90;
const TYPES = ["image/jpeg", "image/png", "image/webp"] as const;

const MAX_IMAGES = 6;

/** Snap slips: screenshots in ({images: [data URL]}, or one {image}), a draft bet out for each bet they show (one slip
 * across several screens is one bet), each leg matched to the app's game. Nothing is saved here; My bets > Add saves
 * what you confirm. Signed-in only (proxy.ts). `draft` and `placed_at` repeat the first for iPhone builds before Oct 25. */
export async function POST(req: Request) {
  if (!chatReady()) return Response.json({ error: "Reading slips is waiting for its key (ANTHROPIC_API_KEY on the web service)." }, { status: 503 });
  const body = await req.json().catch(() => null);
  const urls: string[] = (Array.isArray(body?.images) ? body.images : body?.image ? [body.image] : []).map(String);
  if (!urls.length) return Response.json({ error: "Send a JPEG, PNG or WebP screenshot." }, { status: 400 });
  if (urls.length > MAX_IMAGES) return Response.json({ error: `Up to ${MAX_IMAGES} screenshots at a time.` }, { status: 400 });
  const images: SlipImage[] = [];
  for (const u of urls) {
    const m = /^data:(image\/(?:jpeg|png|webp));base64,(.+)$/.exec(u);
    if (!m || !TYPES.includes(m[1] as (typeof TYPES)[number])) return Response.json({ error: "Send JPEG, PNG or WebP screenshots." }, { status: 400 });
    if (m[2].length > 7_000_000) return Response.json({ error: "That image is too big: try a screenshot instead of a photo." }, { status: 413 });
    images.push({ data: m[2], mediaType: m[1] as SlipImage["mediaType"] });
  }
  try {
    const reads = await readSlips(images);
    const drafts = [];
    for (const read of reads) {
      const placed = easternIso(read.placed_at);
      const games = await gamesAround(new Date(placed));
      const fights = () => ufcRefs(games.filter((g) => g.league === "ufc").map((g) => g.game_id));
      const refs = read.legs.some((l) => l.sport === "ufc") ? await fights() : {};
      const d = draft(read, games, new Date(), refs);
      // a leg with no game gets the day's games to pick from (Nov 9: "Green Bay Packers (opponent not shown)" never
      // tracked); a fight among them needs its ref too
      const unmatched = d.legs.some((l) => !l.matched);
      const choices = !unmatched ? []
        : gameChoices(read, games, placed, read.legs.some((l) => l.sport === "ufc") ? refs : await fights().catch(() => ({})));
      // each leg's own price from its game's Build pack, for the price check on the draft (upcoming games only: a
      // started game's pack is gone, and that slip just goes unchecked)
      const ids = [...new Set(d.legs.flatMap((l) => (l.event_id ? [l.event_id] : [])))];
      const parts = Object.fromEntries(await Promise.all(ids.map(async (id) => [id, await packParts(id).catch(() => [])] as const)));
      const packs = Object.fromEntries(ids.map((id) => [id, parts[id].flatMap((b) => b.legs ?? [])]));
      // what the slip is worth, from the same packs (Nov 4): a screenshot of a betslip answers "is this +EV?" before you place it
      const merged = Object.fromEntries(ids.flatMap((id) => { const pk = mergePack(parts[id]); return pk ? [[id, pk] as const] : []; }));
      const priced = withPrices(d, packs);
      drafts.push({ draft: { ...priced, fair: slipFair(priced.legs, merged), ...(choices.length ? { choices } : {}) }, placed_at: placed });
    }
    return Response.json({ drafts, ...drafts[0] });
  } catch (e) {
    if (e instanceof Anthropic.AuthenticationError) return Response.json({ error: "The key was refused: check ANTHROPIC_API_KEY." }, { status: 503 });
    if (e instanceof Anthropic.RateLimitError) return Response.json({ error: "Too many at once: try again in a minute." }, { status: 429 });
    if (e instanceof Anthropic.APIError) return Response.json({ error: `Claude answered with an error (${e.status ?? "?"}): try again.` }, { status: 502 });
    return Response.json({ error: (e as Error).message || "Couldn't read that slip." }, { status: 422 });
  }
}
