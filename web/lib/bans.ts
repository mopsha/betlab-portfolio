// The ban list (Mike, Oct 25): players and teams BetLab never gives bets on. Games and players stay visible; a banned
// player's props and a banned team's side (moneyline, spread, to win) leave Home, the game pages and the promo finder.
// Totals, both-teams-to-score and a draw are on no one. Stored on the account (user_settings.bans) so the phone and the
// worker read the same list. Ported from src/betlab/bans.py (Swift: ios/BetLab/Core/Bans.swift); all three run
// tests/fixtures/bans.json, and teams.json is the same file in all three. **Change them together.**
import TEAMS from "./teams.json";
import { normName, parseLeg, plain } from "./live";

export type Ban = { kind: "player" | "team"; name: string; league?: string | null };

const CLUB = new Set(["fc", "cf", "afc", "sc", "ac"]);
const words = (s: unknown) => plain(s).split(" ").filter((t) => t && !CLUB.has(t));
const same = (a: string[], b: string[]) => a.length === b.length && a.every((t, i) => t === b[i]);

/** The stored list as entries we can match. */
export function cleanBans(raw: unknown): Ban[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((b) => b && typeof b === "object" && (b.kind === "player" || b.kind === "team") && plain(b.name))
    .map((b) => ({ kind: b.kind, name: String(b.name).trim(), league: b.league || null }));
}

/** The NFL/NBA/NHL teams a text names ("NYJ", "Jets", "New York Jets"), as "league:Full Name". */
export function teamKeys(text: unknown, league?: string | null): Set<string> {
  const t = words(text), out = new Set<string>();
  if (!t.length) return out;
  for (const [lg, rows] of Object.entries(TEAMS as Record<string, { name: string; abbr: string[] }[]>)) {
    if (league && lg !== league) continue;
    for (const r of rows) {
      const full = words(r.name);
      if (same(t, full) || (t.length === 1 && r.abbr.some((a) => plain(a) === t[0]))
          || same(full.slice(-t.length), t) || same(full.slice(0, t.length), t)) out.add(`${lg}:${r.name}`);
    }
  }
  return out;
}

export function teamHit(ban: string, ours: string, league?: string | null, banLeague?: string | null): boolean {
  if (banLeague && league && banLeague !== league) return false;
  const b = teamKeys(ban, banLeague || league), o = teamKeys(ours, league || banLeague);
  if (b.size || o.size) return [...b].some((k) => o.has(k));
  const bw = words(ban), ow = words(ours);
  return bw.length > 0 && bw.length <= ow.length && (same(ow.slice(0, bw.length), bw) || same(ow.slice(-bw.length), bw));
}

export function playerHit(ban: string, ours: string): boolean {
  const b = normName(ban).split(" ").filter(Boolean), o = normName(ours).split(" ").filter(Boolean);
  if (!b.length || !o.length) return false;
  if (same(b, o)) return true;
  if (b.length === 1) return o[o.length - 1] === b[0];
  if (b[b.length - 1] !== o[o.length - 1]) return false;
  return (b[0].length === 1 || o[0].length === 1) && b[0][0] === o[0][0];
}

const contains = (label: string, name: string) => ` ${plain(label)} `.includes(` ${plain(name)} `);

/** The ban a leg or bet runs into, else null. `player` is the leg's player when the feed gives one. */
export function banHit(bans: Ban[], label: string, league?: string | null, player?: string | null): Ban | null {
  if (!bans.length) return null;
  const leg = parseLeg(label);
  if (leg?.kind === "total" || leg?.kind === "btts" || leg?.kind === "btts_no" || leg?.kind === "draw" || leg?.kind === "no_draw" || plain(label) === "draw") return null;
  const who = player || (leg && "player" in leg ? leg.player : null);
  for (const b of bans) {
    if (b.kind === "player") {
      if (who && playerHit(b.name, who)) return b;
      if (!who && !leg && contains(label, b.name)) return b;
    } else if (leg && (leg.kind === "ml" || leg.kind === "spread" || leg.kind === "draw_or" || leg.kind === "not_win")) {
      if (teamHit(b.name, leg.team, league, b.league)) return b;
    } else if (!leg && !who && contains(label, b.name)) return b;
  }
  return null;
}

export const isBanned = (bans: Ban[], label: string, league?: string | null, player?: string | null) =>
  banHit(bans, label, league, player) !== null;

type LegLike = string | { label?: string | null; player?: string | null };

/** A parlay with any banned leg: legs are labels or leg objects ({label, player}). */
export const anyLegBanned = (bans: Ban[], legs: LegLike[] | null | undefined, league?: string | null) =>
  bans.length > 0 && (legs ?? []).some((l) => typeof l === "string" ? isBanned(bans, l, league)
    : isBanned(bans, l?.label ?? "", league, l?.player || null));

/** A ticket, slip or over (fun_tickets body) with a banned leg: its legs, else its games' legs, else its label. */
export function ticketBanned(bans: Ban[], body: Record<string, any> | null | undefined, league?: string | null): boolean {
  if (!bans.length || !body) return false;
  const legs: LegLike[] = body.legs?.length ? body.legs : (body.games ?? []).flatMap((g: any) => g.legs ?? []);
  if (legs.length) return anyLegBanned(bans, legs, league);
  return !!body.label && isBanned(bans, body.label, league, body.player || null);
}
