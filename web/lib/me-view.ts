// What the Me page shows, worked out from pieces the app already has (the Me reorganization, Nov 5): the numbers for
// the chosen range, the wallet in one line, and which badges fit in the row. Pure; nothing here changes what the
// record, the streak or a badge is.
import type { Badge } from "./achievements";
import { nextUp } from "./achievements";
import { dayOf, isSettled, record } from "./bets";
import type { MyBet } from "./data";
import type { PromoRow } from "./promos";
import { streaks, timeline } from "./stats";
import { addDays } from "./time";

export const RANGES = [["week", "Week", "this week"], ["month", "Month", "this month"], ["all", "All", "all time"]] as const;
export type Range = (typeof RANGES)[number][0];

export const rangeOf = (s: string | null | undefined): Range => (RANGES.some(([k]) => k === s) ? (s as Range) : "all");
export const rangeLabel = (r: Range) => RANGES.find(([k]) => k === r)![2];
/** The first Eastern day in the range: today and the 6 (or 29) days before it; "" for all time. */
export const rangeFrom = (r: Range, today: string) => (r === "week" ? addDays(today, -6) : r === "month" ? addDays(today, -29) : "");

export type MeNumbers = { bets: number; units: number; won: number; lost: number; roi: number | null; clv: number | null;
  streak: string | null; points: number[] };

/** Units won, the record, the return on cash staked, the average CLV and the current run, over the settled bets whose
 *  day (dayOf: the game's Eastern day) is in the range; `points` is the units after each of those days, from zero. */
export function meNumbers(bets: MyBet[], range: Range, today: string): MeNumbers {
  const from = rangeFrom(range, today);
  const mine = bets.filter((b) => isSettled(b) && dayOf(b) >= from);
  const { total } = record(mine);
  const run = streaks(mine).current;
  return {
    bets: total.bets, units: total.units, won: total.won, lost: total.lost,
    roi: total.staked ? total.units / total.staked : null,
    clv: total.clvN ? total.clvSum / total.clvN : null,
    streak: run.kind ? `${run.kind === "won" ? "W" : "L"}${run.n}` : null,
    points: [0, ...timeline(mine).map((p) => p.units)],
  };
}

/** The open tokens in one line: bonus dollars waiting and how many boosts. */
export function walletLine(open: Pick<PromoRow, "kind" | "amount_dollars">[]): { dollars: number; bonuses: number; boosts: number } {
  const bonus = open.filter((p) => p.kind === "bonus");
  return { dollars: bonus.reduce((s, p) => s + (Number(p.amount_dollars) || 0), 0), bonuses: bonus.length, boosts: open.length - bonus.length };
}

/** The badges for Me's row: the newest earned first (`achievements` already orders them), then a couple still locked,
 *  the closest to done first. */
export function badgeRow(badges: Badge[], earned = 10, locked = 2): Badge[] {
  const got = badges.filter((b) => b.earned).slice(0, earned);
  const near = nextUp(badges, locked);
  const rest = badges.filter((b) => !b.earned && !near.includes(b));
  return [...got, ...near, ...rest].slice(0, got.length + locked);
}
