import "server-only";
// Player headshots for the player cards (Oct 24): bets carry names, not player ids, so ESPN's site search finds the
// player by name, preferring the bet's league. Cached a day by Next's fetch cache; a miss just shows initials.
// `look` (Oct 25): the whole card face, a player's or a team's (logo, colors, jersey, position), like the iPhone's.
import type { CardKind } from "./cards";
import { teamColor } from "./live";

const SEARCH = "https://site.web.api.espn.com/apis/common/v3/search";
const LEAGUE: Record<string, (league: string, sport: string) => boolean> = {
  NBA: (l) => l === "nba", NFL: (l) => l === "nfl", NHL: (l) => l === "nhl", WNBA: (l) => l === "wnba",
  Soccer: (_l, s) => s === "soccer", NCAAF: (l) => l === "college-football", NCAAB: (l) => l === "mens-college-basketball",
};

export type Headshot = { url: string | null; team: string | null };

export async function headshot(name: string, sport: string): Promise<Headshot> {
  try {
    const r = await fetch(`${SEARCH}?query=${encodeURIComponent(name)}&limit=5&type=player`,
      { headers: { "User-Agent": "BetLab" }, next: { revalidate: 86_400 }, signal: AbortSignal.timeout(8_000) });
    if (!r.ok) return { url: null, team: null };
    const items: any[] = (await r.json())?.items ?? [];
    const fits = Object.hasOwn(LEAGUE, sport) ? LEAGUE[sport] : undefined;   // unknown sport: the first hit
    const hit = items.find((it) => fits?.(String(it.league ?? ""), String(it.sport ?? ""))) ?? (fits ? null : items[0]);
    if (!hit) return { url: null, team: null };
    const team = (hit.teamRelationships ?? []).find((t: any) => t?.core?.displayName || t?.displayName);
    return { url: hit.headshot?.href ?? null, team: team?.core?.displayName ?? team?.displayName ?? null };
  } catch {
    return { url: null, team: null };
  }
}

/** A card's face: the photo (a player's headshot, a team's logo), the team, its color and logo, jersey and position. */
export type Look = { photo: string | null; team: string | null; teamShort: string | null; color: string | null;
                     logo: string | null; jersey: string | null; position: string | null };
const NONE: Look = { photo: null, team: null, teamShort: null, color: null, logo: null, jersey: null, position: null };

export async function look(kind: CardKind, name: string, sport: string): Promise<Look> {
  // a team's name as a slip or the odds feed writes it isn't always ESPN's ("Brighton and Hove Albion" / "&")
  for (const q of [...new Set([name, name.replace(/ and /gi, " & "), name.replace(/^(AFC|FC|CF|SC) | (FC|CF|SC|AFC)$/g, "")])]) {
    const got = await lookOnce(kind, q, sport);
    if (got.photo || got.team) return got;
    if (kind === "player") break;
  }
  return NONE;
}

async function lookOnce(kind: CardKind, name: string, sport: string): Promise<Look> {
  try {
    const r = await fetch(`${SEARCH}?query=${encodeURIComponent(name)}&limit=5&type=${kind}`,
      { headers: { "User-Agent": "BetLab" }, next: { revalidate: 86_400 }, signal: AbortSignal.timeout(8_000) });
    if (!r.ok) return NONE;
    const items: any[] = (await r.json())?.items ?? [];
    const fits = Object.hasOwn(LEAGUE, sport) ? LEAGUE[sport] : undefined;
    const hit = items.find((it) => fits?.(String(it.league ?? ""), String(it.sport ?? ""))) ?? (fits ? null : items[0]);
    if (!hit) return NONE;
    if (kind === "team") {
      const logo = hit.logos?.[0]?.href ?? null;
      return { ...NONE, photo: logo, logo, team: hit.displayName ?? name, teamShort: hit.abbreviation ?? null,
               color: teamColor(hit.color, hit.alternateColor) };
    }
    const t = (hit.teamRelationships ?? []).find((x: any) => x?.core?.displayName || x?.displayName);
    const core = t?.core ?? {};
    return { photo: hit.headshot?.href ?? null, team: core.displayName ?? t?.displayName ?? null, teamShort: core.shortDisplayName ?? null,
             color: teamColor(core.color, core.alternateColor), logo: core.logos?.[0]?.href ?? null,
             jersey: hit.jersey ?? null, position: hit.position?.abbreviation ?? null };
  } catch {
    return NONE;
  }
}
