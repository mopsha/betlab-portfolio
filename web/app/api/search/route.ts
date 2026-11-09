import { searchData } from "@/lib/data";

export const dynamic = "force-dynamic";

/** Search (Nov 4): the signed-in user's bets and teams, and the shared games, fights and players (lib/data.ts searchData). */
export async function GET(req: Request) {
  try {
    const q = (new URL(req.url).searchParams.get("q") ?? "").slice(0, 80);
    return Response.json(await searchData(q), { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return Response.json({ error: String((e as Error).message ?? e) }, { status: 500 });
  }
}
