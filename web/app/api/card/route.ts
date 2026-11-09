import { cardOf, type CardKind } from "@/lib/cards";
import { myBetsData, ticketBodies } from "@/lib/data";
import { sportName } from "@/lib/format";
import { look } from "@/lib/headshots";
import { groups } from "@/lib/live-bets";

export const dynamic = "force-dynamic";

/** One card for a picture tapped anywhere (Oct 25): ?kind=player|team&name=...[&abbr=OTT][&sport=nhl]. Your record
 * with that player or team from all your bets, and its face (lib/headshots.ts `look`). Signed-in only (proxy.ts). */
export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  const kind = q.get("kind") as CardKind, name = (q.get("name") ?? "").trim();
  if ((kind !== "player" && kind !== "team") || !name) return Response.json({ error: "Which player or team?" }, { status: 400 });
  try {
    const { bets } = await myBetsData();
    const tickets = await ticketBodies(bets.filter((b) => b.kind === "parlay" && b.sgp_id).map((b) => b.sgp_id!));
    const card = cardOf(bets, (b) => groups(b, tickets), { kind, name, abbr: q.get("abbr") });
    const sport = card?.sport ?? (q.get("sport") ? sportName(q.get("sport")) : "");
    return Response.json({ card, look: await look(kind, kind === "team" ? name : card?.name ?? name, sport) },
                         { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return Response.json({ error: String((e as Error).message ?? e) }, { status: 500 });
  }
}
