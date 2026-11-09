import Anthropic from "@anthropic-ai/sdk";
import { chatReady } from "@/lib/chat";
import { MAX_IMAGES, readPromos, type PromoImage, type ShotRead } from "@/lib/promo-read";
import { boostExpiry, promoDraft, shotBooks, teamGames, type PromoGame } from "@/lib/promos";
import { supabaseServer } from "@/lib/supabase/server";
import { etDay } from "@/lib/time";

export const dynamic = "force-dynamic";
export const maxDuration = 180;
const TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
const BOOKS = ["FanDuel", "DraftKings", "Novig"];

/** The promos wallet (Oct 30): screenshots of a book's bonus bets or boosts in ({images: [data URL]}), each token's
 *  terms out, to check before saving (nothing is saved here). Signed-in only: the web's session or the iPhone app's
 *  bearer token (proxy.ts BEARER_PATHS). The tokens go out cleaned (lib/promos.ts promoDraft, Nov 9).
 *  Nov 9: up to MAX_IMAGES screenshots, each read on its own, every token kept; each screenshot's book settled across
 *  the batch (shotBooks: one named book wins over guesses from the look; none at all is the account's only book switched on); two teams that meet on the schedule become that game (teamGames); a boost's expiry
 *  follows Mike's rule (boostExpiry). Screenshots that failed are counted (`failed`) when others read. */
export async function POST(req: Request) {
  if (!chatReady()) return Response.json({ error: "Reading screenshots is waiting for its key (ANTHROPIC_API_KEY on the web service)." }, { status: 503 });
  const sb = await supabaseServer();
  const { data: who } = await sb.auth.getUser();
  if (!who?.user) return Response.json({ error: "Sign in first." }, { status: 401 });
  const body = await req.json().catch(() => null);
  const urls: string[] = (Array.isArray(body?.images) ? body.images : []).map(String);
  if (!urls.length || urls.length > MAX_IMAGES) return Response.json({ error: `Send 1 to ${MAX_IMAGES} screenshots.` }, { status: 400 });
  const images: PromoImage[] = [];
  for (const u of urls) {
    const m = /^data:(image\/(?:jpeg|png|webp));base64,(.+)$/.exec(u);
    if (!m || !TYPES.includes(m[1] as (typeof TYPES)[number])) return Response.json({ error: "Send JPEG, PNG or WebP screenshots." }, { status: 400 });
    if (m[2].length > 7_000_000) return Response.json({ error: "That image is too big: send a screenshot." }, { status: 413 });
    images.push({ data: m[2], mediaType: m[1] as PromoImage["mediaType"] });
  }
  const now = new Date();
  const [reads, settings, schedule] = await Promise.all([
    readPromos(images, etDay(now), now),
    sb.from("user_settings").select("books_off").eq("user_id", who.user.id).maybeSingle(),
    sb.from("schedule_games").select("id, matchup, start, sport").gte("start", new Date(now.getTime() - 4 * 3600_000).toISOString())
      .lte("start", new Date(now.getTime() + 15 * 86400_000).toISOString()).limit(5000),
  ]);
  const ok = reads.filter((r): r is ShotRead => !(r instanceof Error));
  const errors = reads.filter((r): r is Error => r instanceof Error);
  if (!ok.length) return failed(errors[0]);
  const off: string[] = settings.data?.books_off ?? [];
  const mine = BOOKS.filter((b) => !off.includes(b));
  const games: PromoGame[] = (schedule.data ?? []).map((g) => ({ event_id: g.id, matchup: g.matchup, commence_time: g.start, sport: g.sport }));
  const books = shotBooks(ok, mine);
  // every token read counts (Nov 9: Mike's 10 screenshots were 10 tokens, two pairs with the same terms; merging overlaps
  // would have dropped two of them)
  const promos = ok.flatMap((r, i) => r.promos.map((p) => ({ ...p, book: books[i] })))
    .map((p) => promoDraft(boostExpiry(teamGames(p, games, now))));
  // what each screenshot read, for checking a bad read afterwards (Nov 9; terms only, no images)
  console.log(JSON.stringify({ promo_read: { user: who.user.id, shots: ok.map((r, i) => ({ book: r.book, from: r.from, settled: books[i], promos: r.promos })),
    failed: errors.map((e) => e.message), out: promos } }));
  if (!promos.length) return Response.json({ error: `No bonus bets or boosts found on ${images.length === 1 ? "that screenshot" : "those screenshots"}.` }, { status: 422 });
  return Response.json({ promos, failed: errors.length, read: images.length });
}

function failed(e: Error | undefined) {
  if (e instanceof Anthropic.AuthenticationError) return Response.json({ error: "The key was refused: check ANTHROPIC_API_KEY." }, { status: 503 });
  if (e instanceof Anthropic.APIConnectionTimeoutError) return Response.json({ error: "Reading took too long: try again in a moment." }, { status: 504 });
  if (e instanceof Anthropic.RateLimitError) return Response.json({ error: "Too many reads at once: try again in a minute." }, { status: 429 });
  if (e instanceof Anthropic.APIConnectionError) return Response.json({ error: "Couldn't reach Claude: try again." }, { status: 502 });
  if (e instanceof Anthropic.APIError) return Response.json({ error: `Claude answered with an error (${e.status ?? "?"}): try again.` }, { status: 502 });
  return Response.json({ error: e?.message || "Couldn't read those screenshots." }, { status: 422 });
}
