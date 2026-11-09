// When each fun slice's parlays lock (Mike, 2026-10-10: "something where on the app it says when the
// next slip will lock"). Pure, so the tests run it. Mirrors the worker (sgp_plus.keep_tickets / lock_due):
// the first 15-minute tick within LOCK_LEAD_MS of the slice's first kickoff, or earlier once the news is in
// for every game of the slice (pregame.settled_slates, Oct 12): Home says "by" this time.
import { SPORT, sliceOf, sliceWord } from "./slices";

export type LockSlate = { slate: string; sport: string; kickoff: string; label: string; title?: string;
  locked_at?: string | null; ticket_ids?: string[] };
export type NextLock = { slate: string; title: string; sport: string; at: string };
/** A scheduled game; a start not yet known (null, as the games table allows) is skipped. */
export type ScheduleGame = { league: string; commence_time: string | null };

const LOCK_LEAD_MS = 25 * 60 * 1000, TICK_MS = 15 * 60 * 1000;
// College basketball locks with its first tip's pull, the first tick within 45 minutes of it (pregame.FIRST_TIP_ONLY).
const LEAD_MS: Record<string, number> = { ncaab: 45 * 60 * 1000 };
export const lockTime = (kickoff: string, sport = "") =>
  new Date(Math.ceil((Date.parse(kickoff) - (LEAD_MS[sport] ?? LOCK_LEAD_MS)) / TICK_MS) * TICK_MS);

/** The slices with a parlay still to lock (not locked, first kickoff ahead), soonest first. `games`: the NBA's and
 * college basketball's slices are built only once their lines are pulled, so until then they come from the schedule
 * (Mike, Oct 24: "i don't see that lock coming up on home"). */
export function upcomingLocks(slates: LockSlate[], now = Date.now(), games: ScheduleGame[] = [], watched: NextLock[] = []): NextLock[] {
  // `watched`: the watched games' own locks (lib/watch.ts watchedLocks: by each game, never its slice, Nov 7)
  const built = slates
    .filter((s) => !s.locked_at && Date.parse(s.kickoff) > now
      && (s.ticket_ids ?? []).some((id) => id.startsWith("plus-") || id.startsWith("td-")))
    .map((s) => ({ slate: s.slate, title: s.title ?? s.label, sport: s.sport, at: lockTime(s.kickoff, s.sport).toISOString() }));
  const known = new Set(slates.map((s) => s.slate));
  return [...built, ...scheduledSlices(games, now).filter((l) => !known.has(l.slate)), ...watched].sort((a, b) => a.at.localeCompare(b.at));
}

// Built only once their lines are pulled: the NBA's by its pull 15-45 minutes before the first tip, college basketball's
// by the 9:55 pull or its pre-game one. A ticket needs two games (cards/fun_ncaab.py, fun_nba.py); since Nov 7 a lone NBA
// game's slips show only when watched, so it no longer counts as a lock to come.
const SCHEDULED: Record<string, number> = { nba: 2, ncaab: 2 };

/** The slices still to be built, from the schedule: one per slice with a game still ahead, locking at the first tip's lock
 * time. Like the worker's (sgp_plus.slice_of, slice_names). */
export function scheduledSlices(games: ScheduleGame[], now = Date.now()): NextLock[] {
  const by = new Map<string, { sport: string; name: string; first: number; n: number }>();
  for (const g of games) {
    const t = g.commence_time ? Date.parse(g.commence_time) : NaN;
    const s = SCHEDULED[g.league] && t > now ? sliceOf(g.league, g.commence_time!) : null;
    if (!s) continue;
    const k = `${s[0]}-${g.league}-${s[1]}`, cur = by.get(k);
    by.set(k, { sport: g.league, name: s[1], first: Math.min(cur?.first ?? t, t), n: (cur?.n ?? 0) + 1 });
  }
  return [...by.entries()].filter(([, s]) => s.n >= SCHEDULED[s.sport]).map(([slate, s]) => ({ slate, sport: s.sport,
    title: `${SPORT[s.sport]} ${sliceWord(s.sport, s.name, s.first)} game${s.n === 1 ? "" : "s"}`,
    at: lockTime(new Date(s.first).toISOString(), s.sport).toISOString() }));
}
