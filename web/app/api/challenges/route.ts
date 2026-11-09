import Anthropic from "@anthropic-ai/sdk";
import { chatReady } from "@/lib/chat";
import { readChallenges, type ChallengeImage } from "@/lib/challenge-read";
import { supabaseServer } from "@/lib/supabase/server";
import { etDay } from "@/lib/time";

export const dynamic = "force-dynamic";
export const maxDuration = 60;
const TYPES = ["image/jpeg", "image/png", "image/webp"] as const;

/** Novig challenges (Oct 28): screenshots of Novig's Points > Challenges in ({images: [data URL]}), one row per
 *  challenge for today out (the worker solves them, saves each one's bet once it's ripe and alerts you). Queues the
 *  worker's `challenges` job so they're solved within a minute. Signed-in only: the web's session or the iPhone app's
 *  bearer token, under row-level security. */
export async function POST(req: Request) {
  if (!chatReady()) return Response.json({ error: "Reading screenshots is waiting for its key (ANTHROPIC_API_KEY on the web service)." }, { status: 503 });
  const body = await req.json().catch(() => null);
  const urls: string[] = (Array.isArray(body?.images) ? body.images : []).map(String);
  if (!urls.length || urls.length > 4) return Response.json({ error: "Send 1 to 4 screenshots." }, { status: 400 });
  const images: ChallengeImage[] = [];
  for (const u of urls) {
    const m = /^data:(image\/(?:jpeg|png|webp));base64,(.+)$/.exec(u);
    if (!m || !TYPES.includes(m[1] as (typeof TYPES)[number])) return Response.json({ error: "Send JPEG, PNG or WebP screenshots." }, { status: 400 });
    if (m[2].length > 7_000_000) return Response.json({ error: "That image is too big: send a screenshot." }, { status: 413 });
    images.push({ data: m[2], mediaType: m[1] as ChallengeImage["mediaType"] });
  }
  try {
    const read = await readChallenges(images);
    const sb = await supabaseServer();
    const day = etDay(new Date());
    const rows = read.map((c) => ({ day, text: c.text.trim(), points: c.points, ...(c.done ? { status: "done" } : {}) }));
    const { error } = await sb.from("challenges").upsert(rows, { onConflict: "user_id,day,text", ignoreDuplicates: true });
    if (error) return Response.json({ error: "Couldn't save them. Try again." }, { status: 500 });
    await sb.from("job_requests").insert({ job: "challenges", status: "queued" });          // best effort
    return Response.json({ added: rows.length, challenges: read });
  } catch (e) {
    if (e instanceof Anthropic.AuthenticationError) return Response.json({ error: "The key was refused: check ANTHROPIC_API_KEY." }, { status: 503 });
    if (e instanceof Anthropic.APIError) return Response.json({ error: `Claude answered with an error (${e.status ?? "?"}): try again.` }, { status: 502 });
    return Response.json({ error: (e as Error).message || "Couldn't read those screenshots." }, { status: 422 });
  }
}
