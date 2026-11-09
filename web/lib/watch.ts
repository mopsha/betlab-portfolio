// Watched games (Nov 7, migration 0045): Mike marks the games he'll watch, and their own same-game slips join Today's
// Parlays. It replaces two fixed rules: the Knicks' own slips and a lone prime-time game's. Every slice carries each of
// its games' slips (sgp_plus.own_slips), but they lock by their own game, never the slice (Mike: "locks on a sgp
// shouldn't depend on slices at all"; sgp_plus.lock_slips); the worker alerts a watcher at that lock.
// Same rule on the iPhone (Today/Watch.swift), one fixture: tests/fixtures/watch.json.

export const LOCK_MS = 25 * 60 * 1000;

type SlipLike = { kind: string; game_id?: string | null; commence_time?: string | null; sport?: string | null; matchup?: string | null };

/** Whether Today shows this single-game slip: its game is watched, it hasn't started, and its own lock time (25 minutes
 *  before its start) has come. */
export function showsWatched(t: SlipLike, watching: ReadonlySet<string>, now: number): boolean {
  if (t.kind !== "sgp" || !t.game_id || !watching.has(t.game_id)) return false;
  const at = Date.parse(t.commence_time ?? "");
  return at > now && at - now <= LOCK_MS;
}

/** "Knicks @ Cavaliers": a matchup by its teams' last words. */
export const nicks = (m?: string | null) => String(m ?? "").split(/ @ | vs\.? /).map((s) => s.trim().split(" ").pop()).join(" @ ");

/** The watched games' locks still ahead, one per game: "Knicks @ Cavaliers slips" at its start minus 25 minutes. */
export function watchedLocks(tickets: SlipLike[], watching: ReadonlySet<string>, now: number) {
  const by = new Map<string, { slate: string; title: string; sport: string; at: string }>();
  for (const t of tickets) {
    if (t.kind !== "sgp" || !t.game_id || !watching.has(t.game_id) || by.has(t.game_id)) continue;
    const at = Date.parse(t.commence_time ?? "") - LOCK_MS;
    if (at > now) by.set(t.game_id, { slate: `game:${t.game_id}`, title: `${nicks(t.matchup)} slips`, sport: t.sport ?? "", at: new Date(at).toISOString() });
  }
  return [...by.values()];
}

/** The account's watched games with one game turned on or off. */
export function toggled(watching: readonly string[], gameId: string, on: boolean): string[] {
  const rest = watching.filter((g) => g !== gameId);
  return on ? [...rest, gameId] : rest;
}
