// Player cards (Mike's W21, Oct 24): the players you bet on most, each with your record on them. Pure: every player
// prop leg in your bets (parsed as the live tracker reads labels, lib/live.ts), matched in order to the bet's graded
// leg results, so a player twice in one parlay or in two parlays counts each time. Team cards: lib/cards.ts.
import { isSettled, profit, statusOf } from "./bets";
import type { MyBet } from "./data";
import { normName, parseLeg } from "./live";
import { sportOf } from "./stats";

export type PlayerLeg = { label: string; stat: string; result: "won" | "lost" | "void" | "open"; day: string; betId: string;
  game?: string };   // game: a team card's game leg (BTTS, a total) names its matchup
export type Player = {
  key: string; name: string; sport: string; legs: PlayerLeg[]; won: number; lost: number; open: number;
  hitRate: number | null; topStat: string | null; bets: number; units: number;   // units: P/L of the settled bets he was in
};

const STAT_NAME: Record<string, string> = { td: "touchdowns", goal_or_assist: "goal or assist" };

/** A leg's result from its graded result; a single bet's leg takes the bet's own once it's settled. */
export function legResult(r: string | null | undefined, settled: boolean, legs: number, status: string): PlayerLeg["result"] {
  return r === "won" || r === "lost" ? r : r === "void" || r === "push" ? "void"
    : settled && legs === 1 && (status === "won" || status === "lost") ? status : "open";
}

/** Every player leg in a bet, with its graded result (in order: repeated labels each get their own). */
export function playerLegs(b: MyBet): (PlayerLeg & { player: string })[] {
  const labels = b.legs?.length ? b.legs : b.label ? [b.label] : [];
  const results = b.leg_results ?? [];
  const used = new Set<number>();
  const settled = isSettled(b), s = statusOf(b);
  const out: (PlayerLeg & { player: string })[] = [];
  for (const label of labels) {
    const i = results.findIndex((r, k) => !used.has(k) && r.leg === label);
    if (i >= 0) used.add(i);
    const p = parseLeg(label);
    if (!p || !("player" in p)) continue;
    out.push({ player: p.player, label, stat: p.kind === "prop" ? p.stat : STAT_NAME[p.kind] ?? p.kind,
               result: legResult(i >= 0 ? results[i].result : null, settled, labels.length, s), day: b.placed_at.slice(0, 10), betId: b.bet_id });
  }
  return out;
}

/** One leg on a card, with who it's about and the bet it came from. */
export type Entry = { key: string; name: string; sport: string; leg: PlayerLeg; bet: MyBet };

/** Cards from entries, most-bet first (ties: the better hit rate). `min` legs to make the list. A bet's units count
 *  once per card, however many of its legs are on it. Players and teams (lib/cards.ts) both. */
export function tally(entries: Entry[], min = 2): Player[] {
  const by = new Map<string, Player & { betIds: Set<string>; stats: Map<string, number> }>();
  for (const { key, name, sport, leg: l, bet: b } of entries) {
    const p = by.get(key) ?? { key, name, sport, legs: [], won: 0, lost: 0, open: 0, hitRate: null,
                               topStat: null, bets: 0, units: 0, betIds: new Set<string>(), stats: new Map<string, number>() };
    if (p.sport === "Multi-sport" && sport !== "Multi-sport") p.sport = sport;
    p.legs.push(l);
    if (l.result === "won") p.won++; else if (l.result === "lost") p.lost++; else if (l.result === "open") p.open++;
    p.stats.set(l.stat, (p.stats.get(l.stat) ?? 0) + 1);
    if (!p.betIds.has(b.bet_id)) { p.betIds.add(b.bet_id); p.bets++; if (isSettled(b)) p.units += profit(b) ?? 0; }
    by.set(key, p);
  }
  return [...by.values()].filter((p) => p.legs.length >= min).map(({ betIds, stats, ...p }) => ({
    ...p, hitRate: p.won + p.lost ? p.won / (p.won + p.lost) : null,
    topStat: [...stats.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null,
    legs: [...p.legs].sort((a, b) => b.day.localeCompare(a.day)),
  })).sort((a, b) => b.legs.length - a.legs.length || (b.hitRate ?? -1) - (a.hitRate ?? -1) || a.name.localeCompare(b.name));
}

/** Your players, most-bet first (ties: the better hit rate). `min` legs to make the list. */
export function players(bets: MyBet[], min = 2): Player[] {
  return tally(bets.flatMap((b) => playerLegs(b).map((l) =>
    ({ key: normName(l.player), name: l.player, sport: sportOf(b), leg: l, bet: b }))), min);
}

/** A card's tier by hit rate on 3+ graded legs: gold 70%+, silver 50%+, else bronze; none until 3 are graded. */
export function tierOf(p: Player): "gold" | "silver" | "bronze" | null {
  if (p.won + p.lost < 3 || p.hitRate === null) return null;
  return p.hitRate >= 0.7 ? "gold" : p.hitRate >= 0.5 ? "silver" : "bronze";
}
