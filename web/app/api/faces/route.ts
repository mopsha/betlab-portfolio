import { headshot } from "@/lib/headshots";

const HEAD_SPORT: Record<string, string> = { nba: "NBA", nfl: "NFL", nhl: "NHL", wnba: "WNBA", ncaaf: "NCAAF", ncaab: "NCAAB", soccer: "Soccer" };
const MAX = 40;

/** Player photos by name for Build's prop rows (the overhaul, Nov 4): {faces: {name: url | null}}. ESPN's search, cached
 *  a day (lib/headshots.ts); a name it can't place shows its initials. Read-only, and behind sign-in like every route. */
export async function GET(req: Request) {
  const u = new URL(req.url);
  const sport = String(u.searchParams.get("sport") ?? "").toLowerCase();
  const names = [...new Set(String(u.searchParams.get("names") ?? "").split("|").map((n) => n.trim()).filter((n) => n && n.length <= 60))].slice(0, MAX);
  const got = await Promise.all(names.map((n) => headshot(n, HEAD_SPORT[sport] ?? "Soccer").then((h) => h.url).catch(() => null)));
  return Response.json({ faces: Object.fromEntries(names.map((n, i) => [n, got[i]])) }, { headers: { "Cache-Control": "private, max-age=3600" } });
}
