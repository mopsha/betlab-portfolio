import Anthropic from "@anthropic-ai/sdk";
import { chatReady } from "@/lib/chat";
import { readPickem, type PickemImage } from "@/lib/pickem-read";
import { weekOf } from "@/lib/pickem";
import { supabaseServer } from "@/lib/supabase/server";
import { etDay } from "@/lib/time";

export const dynamic = "force-dynamic";
export const maxDuration = 60;
const TYPES = ["image/jpeg", "image/png", "image/webp"] as const;

/** College Football Pick'em (Nov 7): screenshots of FanDuel's Pick'em Questions screen in ({images: [data URL]}, up to
 *  6), one row per game for this week's entry out (the team listed first as away, the second as home: the worker
 *  matches the pair to the week's game and swaps when FanDuel listed them the other way). A game already on the entry
 *  keeps its row but takes the new pick. Queues the worker's `pickem` job so the lines are priced within a minute.
 *  Signed-in only: the web's session or the iPhone app's bearer token, under row-level security. */
export async function POST(req: Request) {
  if (!chatReady()) return Response.json({ error: "Reading screenshots is waiting for its key (ANTHROPIC_API_KEY on the web service)." }, { status: 503 });
  const body = await req.json().catch(() => null);
  const urls: string[] = (Array.isArray(body?.images) ? body.images : []).map(String);
  if (!urls.length || urls.length > 6) return Response.json({ error: "Send 1 to 6 screenshots." }, { status: 400 });
  const images: PickemImage[] = [];
  for (const u of urls) {
    const m = /^data:(image\/(?:jpeg|png|webp));base64,(.+)$/.exec(u);
    if (!m || !TYPES.includes(m[1] as (typeof TYPES)[number])) return Response.json({ error: "Send JPEG, PNG or WebP screenshots." }, { status: 400 });
    if (m[2].length > 7_000_000) return Response.json({ error: "That image is too big: send a screenshot." }, { status: 413 });
    images.push({ data: m[2], mediaType: m[1] as PickemImage["mediaType"] });
  }
  try {
    const read = await readPickem(images);
    const sb = await supabaseServer();
    const week = weekOf(etDay(new Date()));
    const { data: have } = await sb.from("pickem").select("pick_id, away, home, pick").eq("week", week);
    const plain = (s: string) => s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
    const fits = (short: string, full: string) => { const a = plain(short), b = plain(full); return a === b || b.startsWith(`${a} `); };
    let n = (have?.length ?? 0), added = 0, updated = 0;
    for (const g of read) {
      const pick = g.picked === "first" ? "away" : g.picked === "second" ? "home" : null;
      // the same game already on the entry, in either order (matched rows carry the Odds API's full names)
      const old = (have ?? []).find((r) => (fits(g.first, r.away) && fits(g.second, r.home)) || (fits(g.first, r.home) && fits(g.second, r.away)));
      if (old) {
        const swapped = !fits(g.first, old.away);
        const p = pick && swapped ? (pick === "home" ? "away" : "home") : pick;
        if (p !== old.pick) { await sb.from("pickem").update({ pick: p }).eq("pick_id", old.pick_id); updated += 1; }
        continue;
      }
      const row = { week, n: ++n, away: g.first.trim(), home: g.second.trim(), home_line: g.second_line, pick };
      const { error } = await sb.from("pickem").insert(row);
      if (error) return Response.json({ error: "Couldn't save them. Try again." }, { status: 500 });
      added += 1;
    }
    await sb.from("job_requests").insert({ job: "pickem", status: "queued" });          // best effort
    return Response.json({ added, updated, week, games: read });
  } catch (e) {
    if (e instanceof Anthropic.AuthenticationError) return Response.json({ error: "The key was refused: check ANTHROPIC_API_KEY." }, { status: 503 });
    if (e instanceof Anthropic.APIError) return Response.json({ error: `Claude answered with an error (${e.status ?? "?"}): try again.` }, { status: 502 });
    return Response.json({ error: (e as Error).message || "Couldn't read those screenshots." }, { status: 422 });
  }
}
