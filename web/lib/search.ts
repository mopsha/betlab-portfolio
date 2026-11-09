// Search (Nov 4): what's searched in the app itself, your bets and the team list; games, fights and players come from the database
// (search_app, migration 0036). Pure, so the tests run it. Port: ios/BetLab/Games/SearchView.swift, fixture tests/fixtures/search.json.
import { plain } from "./live";

export type SearchBet = { bet_id: string; placed_at: string; label?: string | null; matchup?: string | null; legs?: unknown };
export type SearchTeam = { name: string; abbr: string[] };

const LEAST = 2;
const words = (q: string) => plain(q).split(" ").filter(Boolean);

/** Your bets with every word somewhere in their label, matchup or legs, newest first. */
export function searchBets<T extends SearchBet>(bets: T[], q: string, max = 20): T[] {
  const w = words(q);
  if (plain(q).length < LEAST) return [];
  const text = (b: T) => plain([b.label, b.matchup, ...(Array.isArray(b.legs) ? b.legs : [])].filter(Boolean).join(" "));
  return bets.filter((b) => { const t = text(b); return w.every((x) => t.includes(x)); })
    .sort((a, b) => b.placed_at.localeCompare(a.placed_at)).slice(0, max);
}

/** Teams by name (every word) or exact code, in the list's own order by sport. */
export function searchTeams(all: Record<string, SearchTeam[]>, q: string, max = 12): (SearchTeam & { sport: string })[] {
  const w = words(q), code = q.trim().toUpperCase();
  if (plain(q).length < LEAST) return [];
  const out: (SearchTeam & { sport: string })[] = [];
  for (const sport of Object.keys(all).sort()) {
    for (const t of all[sport]) {
      const n = plain(t.name);
      if (t.abbr.some((a) => a.toUpperCase() === code) || w.every((x) => n.includes(x))) out.push({ ...t, sport });
    }
  }
  return out.slice(0, max);
}
