// Game day (Mike's W27 and W7, Oct 24): Home's hub on a day with action (your open bets live, a countdown to each lock,
// the next ticket) and the wall (/wall: every game you have money on, one tile each, your legs on it). Pure, so the
// tests run it; the live states come from /api/live (lib/live-bets.ts).
import type { BetLive, GameLive, LegLive } from "./live";

export type BetName = { id: string; name: string };

/** What to call a bet on a small card: "4-leg parlay +940", or a single's own leg "Michigan Wolverines ML +250". */
export function betName(b: { legs?: string[] | null; label?: string | null; price?: number | null; games?: unknown }, n?: number): string {
  const legs = b.legs?.length ? b.legs : b.label ? [b.label] : [];
  const count = n ?? legs.length;
  const price = b.price == null ? "" : ` ${b.price > 0 ? "+" : ""}${b.price}`;
  if (count <= 1) return (legs[0] ?? "Bet") + price;
  return parlayName(legs, count) + price;
}

// Where a leg's name stops: a number, a side or a market word ("125+", "-9.5", "over", "ML", "anytime", "to win").
const STOP = /^([+\-.]?\d|o\d|u\d)|^(over|under|ml|anytime|to|yes|no|draw|first|last|alt|both|total|btts)$/i;
const SUFFIX = /^(jr\.?|sr\.?|ii|iii|iv)$/i;

/** Who a leg is about: a team by its full name ("Jacksonville Jaguars" in "Jacksonville Jaguars -9.5"), a player by his
 * name without the first name ("Fagnano" in "Joe Fagnano 125+ passing yds"); null for a leg with no name ("Over 47.5"). */
export function legName(leg: string, full = false): string | null {
  const w = leg.trim().split(/\s+/);
  const i = w.findIndex((x) => STOP.test(x));
  const who = i < 0 ? w : w.slice(0, i), rest = i < 0 ? [] : w.slice(i);
  if (!who.length) return null;
  // a team line is the name and then only a moneyline, a spread or "to win"; anything else is a player's prop
  const team = rest.length === 0 || (rest.length === 1 && /^(ml|[+\-]\d+(\.\d+)?|draw)$/i.test(rest[0]))
    || (rest[0]?.toLowerCase() === "to" && rest[1]?.toLowerCase() === "win");
  if (team || who.length < 2 || (who.length === 2 && SUFFIX.test(who[1]))) return who.join(" ");
  return full ? who.join(" ") : who.slice(1).join(" ");
}

/** A parlay by who is in it (overhaul, Nov 6; it read "4-leg parlay"): two names, then "and N more" for the other names
 * and the legs with no name; one name on every leg is "Rashod Bateman, 2 legs"; no name at all, "4-leg parlay". The same
 * rule as the iPhone's Stats.betName, on tests/fixtures/bet_names.json. */
function parlayName(legs: string[], count: number): string {
  if (legs.length !== count) return `${count}-leg parlay`;
  const names: string[] = [];
  let bare = 0;
  for (const l of legs) {
    const n = legName(l);
    if (n === null) bare++;
    else if (!names.includes(n)) names.push(n);
  }
  if (!names.length) return `${count}-leg parlay`;
  if (names.length === 1 && !bare) return `${legName(legs[0], true)}, ${count} legs`;
  const more = names.length - Math.min(2, names.length) + bare;
  const shown = names.slice(0, 2);
  return more ? `${shown.join(", ")} and ${more} more` : shown.join(", ");
}

/** "1h 04m 09s", "12m 30s", "0m 05s" to a time; "now" once it's passed. Units, so it never reads as a clock time
 * (Mike, Oct 24: "1:04" looked like a time). */
export function countdown(at: string, now = Date.now()): string {
  const s = Math.floor((Date.parse(at) - now) / 1000);
  if (!(s > 0)) return "now";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const two = (x: number) => String(x).padStart(2, "0");
  return h ? `${h}h ${two(m)}m ${two(sec)}s` : `${m}m ${two(sec)}s`;
}

export type Tile = { game: GameLive; legs: (LegLive & { bet: string })[] };

/** The wall's tiles: one per game across the bets still alive, each with every leg on it (named by its bet); the
 * biggest first (most legs: Mike, Oct 25, "sorting in size order on wall looks best"), then live games, then upcoming
 * by start, finished last. A bet that's over (won, or lost on a leg) leaves the wall, and a game with no live bet left
 * goes with it (Mike, Oct 24: "if a bet is over that tracker should disappear"). Bets are read in bet-id order, so a
 * tile's legs keep their order from one poll to the next (they followed the order the live check answered in). */
export function wallTiles(bets: Record<string, BetLive>, names: Record<string, string>): Tile[] {
  const tiles = new Map<string, Tile>();
  for (const [id, b] of Object.entries(bets).sort(([x], [y]) => x.localeCompare(y))) {
    if (b.status === "won" || b.status === "lost") continue;
    for (const l of b.legs) {
      const g = l.gameKey ? b.games.find((x) => x.key === l.gameKey) : undefined;
      if (!g) continue;
      if (!tiles.has(g.key)) tiles.set(g.key, { game: g, legs: [] });
      tiles.get(g.key)!.legs.push({ ...l, bet: names[id] ?? "Bet" });
    }
  }
  const rank = (g: GameLive) => (g.state === "in" ? 0 : g.state === "pre" ? 1 : 2);
  return [...tiles.values()].sort((a, b) => b.legs.length - a.legs.length || rank(a.game) - rank(b.game)
    || a.game.start.localeCompare(b.game.start) || a.game.key.localeCompare(b.game.key));
}

/** Is today a game day for the hub? Any open bet, or a lock still to come today. */
export function isGameDay(openBets: number, locksToday: number): boolean {
  return openBets > 0 || locksToday > 0;
}
