import "server-only";
// Whose picture goes beside a bet (the overhaul's pictures rule, Nov 4): a leg's player by ESPN's search (cached a
// day, lib/headshots.ts), its team from the game's ESPN entry (lib/art.ts). Views only: nothing here prices or grades.
import type { ArtOf } from "@/components/ui/Art";
import type { Offer, Ticket } from "./data";
import { headshot } from "./headshots";
import { SOCCER, parseLeg, sideOf, type GameLive } from "./live";

const HEAD_SPORT: Record<string, string> = { nba: "NBA", nfl: "NFL", nhl: "NHL", wnba: "WNBA", ncaaf: "NCAAF", ncaab: "NCAAB", soccer: "Soccer" };
const headSport = (league: string) => HEAD_SPORT[league] ?? (SOCCER[league] ? "Soccer" : league.toUpperCase());

/** A leg's picture: its player's photo, or its team's logo and color from the game. Null for a total or a draw. */
export async function legArt(label: string, league: string, g?: GameLive | null, player?: string | null): Promise<ArtOf | null> {
  const p = parseLeg(label);
  const who = player ?? (p && "player" in p ? p.player : null);
  if (who) {
    const h = await headshot(who, headSport(league)).catch(() => null);
    return { src: h?.url ?? null, name: who, kind: "player" };
  }
  if (p && "team" in p && g) {
    const s = sideOf(p.team, g);
    if (s) return { src: g[s].logo, name: g[s].name, abbr: g[s].abbr, color: g[s].color, kind: "team" };
  }
  return null;
}

/** A game's two teams as pictures (away first). */
export const gamePair = (g?: GameLive | null): ArtOf[] =>
  g ? [g.away, g.home].map((s) => ({ src: s.logo, name: s.name, abbr: s.abbr, color: s.color, kind: "team" as const })) : [];

/** A pick's picture: the player or the side it's on; a total shows both teams (the caller draws the pair). */
export const offerArt = (o: Offer, g?: GameLive | null) => legArt(o.label, o.league, g, o.player);

/** A parlay's pictures, at most `max`: its legs' players and teams, then the teams of its games. `arts` by matchup. */
export async function ticketArt(t: Ticket, byMatchup: Map<string, GameLive>, max = 4): Promise<ArtOf[]> {
  const games = t.body.games ?? (t.body.legs ? [{ matchup: t.matchup ?? "", legs: t.body.legs }] : []);
  const legs = games.flatMap((g) => (g.legs as ({ label: string } | string)[]).map((l) => ({ label: typeof l === "string" ? l : l.label, g: byMatchup.get(g.matchup) })));
  const out: ArtOf[] = [], seen = new Set<string>();
  const add = (a: ArtOf | null) => { if (a && !seen.has(a.name) && out.length < max) { seen.add(a.name); out.push(a); } };
  // teams first (free), then players (one search each, cached a day), so a card always has a picture
  const found = await Promise.all(legs.slice(0, 8).map((l) => legArt(l.label, t.sport, l.g).catch(() => null)));
  for (const a of found) if (a?.kind === "team") add(a);
  for (const a of found) if (a?.kind === "player" && a.src) add(a);
  if (out.length < 2) for (const g of games) for (const a of gamePair(byMatchup.get(g.matchup))) add(a);
  return out;
}
