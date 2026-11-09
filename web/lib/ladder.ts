// Ladder challenges (Mike, Oct 26): roll the whole stack into one bet at a time, from a start to a target. Pure (no
// I/O). A step is one of the user's bets carrying the ladder's id (migration 0020), so it settles however that bet
// settles. ios/BetLab/Me/Ladder.swift ports this; both answer tests/fixtures/ladder.json alike.
import type { MyBet, Offer } from "./data";
import { isSettled, profit, stakeOf, statusOf, boosted } from "./bets";
import { label as clean, toDec } from "./format";
import { betName } from "./gameday";

export type Ladder = { ladder_id: string; start_units: number; target_units: number; status: "active" | "stopped";
  created_at: string; ended_at?: string | null;
  // migration 0021 (Oct 26): the worker (src/betlab/ladders.py) locks the step once its game's news is in
  game_id?: string | null; skipped?: string[] | null; locked?: LockedStep | null; locked_at?: string | null; notice?: string | null;
  book?: string | null };   // the one book every step is at (0022, Mike Oct 26: "ladder needs to be at one book whole time")
/** The step the worker locked: the offer as it was then, with the stake (the whole stack) and the step number. */
export type LockedStep = { offer_id: string; tier: string; label: string; price: number; book: string | null; matchup: string | null;
  commence_time: string; ev: number | null; game_id: string | null; league?: string | null; stake?: number; step?: number;
  fd_url?: string | null };   // the betslip link at the step's book (Nov 6; locks before then have none: the apps use the live offer's)

/** Where a ladder stands: climbed (the stack reached the target), busted (nothing left), stopped, a step in play,
 *  or waiting for its next step. */
export type LadderPhase = "climbed" | "busted" | "stopped" | "in play" | "next step";
export type LadderState = { phase: LadderPhase; stack: number; steps: MyBet[]; open: MyBet | null; won: number;
  nextStake: number | null; toWin: number | null; progress: number };

const DUST = 1e-6;   // a stack this small is nothing left

/** What a step is called: its legs (a single its leg, a parlay by who is in it), before the slip reader's label, which
 *  is often just its stake ("$10.4 cash", Nov 6); else the label, else the matchup. tests/fixtures/ladder.json step_names. */
export function stepName(b: { legs?: string[] | null; label?: string | null; matchup?: string | null }): string {
  if (b.legs?.length) return betName({ legs: b.legs });
  return clean(b.label ?? "") || String(b.matchup ?? "").split(":")[0];
}

/** The stack a ladder shows: never below nothing (a Bet Protect fee makes a lost step cost a hair more than the stack, and
 *  "ended at −0.06u" read as owing; Nov 6). */
export const shownStack = (u: number) => (u < 0.005 ? 0 : u);

/** The ladder's state from its own bets (oldest first): the stack is the start plus every settled step's profit
 *  (bonus, boost, cash-out and a voided leg all count as My bets counts them); one open step at a time. */
export function ladderState(l: Ladder, bets: MyBet[]): LadderState {
  const steps = bets.filter((b) => b.ladder_id === l.ladder_id).sort((a, b) => a.placed_at.localeCompare(b.placed_at));
  const start = Number(l.start_units), target = Number(l.target_units);
  const stack = start + steps.filter(isSettled).reduce((s, b) => s + (profit(b) ?? 0), 0);
  const open = steps.find((b) => !isSettled(b)) ?? null;
  const won = steps.filter((b) => statusOf(b) === "won").length;
  const phase: LadderPhase = stack >= target - DUST ? "climbed" : stack <= DUST && !open ? "busted"
    : l.status === "stopped" ? "stopped" : open ? "in play" : "next step";
  const toWin = open && open.price != null ? boosted(open, stakeOf(open) * (toDec(Number(open.price)) - 1)) : null;
  // progress on a log scale: each double is the same distance (1u -> 100u is about 6.6 doubles)
  const progress = stack <= 0 ? 0 : Math.min(1, Math.max(0, Math.log(stack / start) / Math.log(target / start)));
  return { phase, stack, steps, open, won, nextStake: phase === "next step" ? stack : null, toWin, progress };
}

/** Prices a step can be: near even money, so a step is likelier won than not and still moves the stack. */
export const STEP_PRICES = { min: -250, max: 150 };
const TIER: Record<string, number> = { pick: 0, lean: 1 };

/** BetLab's suggestion for the next step: its strongest +EV pick (then lean) priced -250 to +150 that starts at least
 *  15 minutes from now, leaving out the ones you turned down (`skipped` offer ids; Mike, Oct 26: "I should be able to
 *  reject options"). Pass offers already cleared of the ban list. Null when nothing fits. */
export function suggestStep<T extends StepOffer>(offers: T[], now = Date.now(), skipped: string[] = [], game: string | null = null,
                                                before: number | null = null, book: string | null = null): T | null {
  return stepOptions(offers, now, before, book).filter((o) => !skipped.includes(o.offer_id) && (!game || o.game_id === game))[0] ?? null;
}

type StepOffer = Pick<Offer, "offer_id" | "game_id" | "tier" | "price" | "ev" | "commence_time"> &
  Partial<Pick<Offer, "book" | "point" | "other_book" | "other_point" | "other_price" | "other_ev">>;

/** An offer as it stands at one book: the offer itself when it's priced there, else the other book's price and EV when
 *  that book posts the same line (same number); null when the book doesn't have it. A ladder stays at one book. */
export function atBook<T extends StepOffer>(o: T, book: string | null): T | null {
  if (!book || (o.book ?? "FanDuel") === book) return o;
  if (o.other_book === book && o.other_price != null && (o.other_point == null || o.other_point === o.point))
    return { ...o, book, price: o.other_price, ev: o.other_ev ?? null };
  return null;
}

/** Every offer that could be a step, best first (picks before leans, then EV). `game` in suggestStep keeps the
 *  suggestion to one game (Mike, Oct 26: "the next pick for this game"). */
export function stepOptions<T extends StepOffer>(offers: T[], now = Date.now(), before: number | null = null, book: string | null = null): T[] {
  return offers.map((o) => atBook(o, book)).filter((o): o is T => o !== null).filter((o) => o.tier in TIER && (o.ev ?? 0) > 0 && o.price >= STEP_PRICES.min && o.price <= STEP_PRICES.max
    && !!o.commence_time && Date.parse(o.commence_time) - now >= 15 * 60_000 && (before === null || Date.parse(o.commence_time) < before))
    .sort((a, b) => TIER[a.tier] - TIER[b.tier] || (b.ev ?? 0) - (a.ev ?? 0));
}

/** How many wins in a row at a price take the stack to the target (the whole stack rolled each time). */
export function stepsToTarget(stack: number, target: number, price: number): number {
  return stack >= target ? 0 : Math.ceil(Math.log(target / stack) / Math.log(toDec(price)));
}

/** When a game's news pull lands, in minutes before its start (config/settings.yaml schedule.pregame; soccer's for
 *  every soccer league): the worker locks a held step then. */
const NEWS: Record<string, [number, number]> = { nfl: [30, 85], ncaaf: [30, 85], nba: [15, 45], ncaab: [15, 45], nhl: [20, 60], ufc: [20, 60] };
export const newsWindow = (league: string | null | undefined): [number, number] => NEWS[league ?? ""] ?? [15, 55];
