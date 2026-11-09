// The desktop ticker (Nov 5, W35): your open bets as short lines, live ones first, from the same /api/live as the tracker.
// Desktop only (the iPhone has its Live Activity), so it has no port. Units and money stay out: what's happening, not what's at stake.
import type { BetLive, GameLive, LegLive } from "./live";

export type TickerItem = { id: string; live: boolean; score: string; clock: string; hit: number; total: number; next: string; state: "live" | "soon" | "lost" | "won" };

const side = (s: GameLive["home"]) => `${s.abbr ?? s.name ?? ""}${s.score != null ? ` ${s.score}` : ""}`.trim();
const time = (iso: string) => new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", hour: "numeric", minute: "2-digit" });
const OPEN: LegLive["status"][] = ["live", "winning", "tied", "losing", "pending", "unknown"];

/** The game a line shows: one in progress, else the next to start, else the last. */
function gameOf(games: GameLive[]): GameLive | null {
  return games.find((g) => g.state === "in")
    ?? [...games].filter((g) => g.state === "pre").sort((a, b) => a.start.localeCompare(b.start))[0]
    ?? games[games.length - 1] ?? null;
}

export function tickerItems(bets: Record<string, BetLive>): TickerItem[] {
  const out = Object.entries(bets).filter(([, b]) => b.games.length || b.legs.length).map(([id, b]): TickerItem & { at: string } => {
    const g = gameOf(b.games);
    const live = b.games.some((x) => x.state === "in");
    const leg = b.legs.filter((l) => OPEN.includes(l.status)).sort((x, y) => OPEN.indexOf(x.status) - OPEN.indexOf(y.status))[0];
    const state = b.settle ?? (live ? "live" : "soon");
    return { id, live, at: g?.start ?? "", state, hit: b.hit, total: b.total,
      score: g ? `${side(g.away)} · ${side(g.home)}` : "",
      clock: !g ? "" : g.state === "pre" ? time(g.start) : g.detail,
      next: b.settle === "won" ? "All legs hit" : b.settle === "lost" ? (b.legs.find((l) => l.status === "lost")?.label ?? "Lost") : leg ? [leg.label, leg.text].filter(Boolean).join(": ") : "" };
  });
  const rank = (i: TickerItem) => (i.state === "live" ? 0 : i.state === "soon" ? 1 : 2);
  return out.sort((a, b) => rank(a) - rank(b) || a.at.localeCompare(b.at) || a.id.localeCompare(b.id)).map(({ at: _at, ...i }) => i);
}
