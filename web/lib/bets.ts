// My bets: results at your own price, and the record by market. Pure (no I/O).
import type { MyBet } from "./data";
import { marketName, num, sportName, toDec } from "./format";
import { etDay } from "./time";
import { bookOf } from "./books";

export const SETTLED = ["won", "lost", "push", "void", "cashout"];

/** A cashed-out bet (Oct 22) is settled at what the book paid back, whatever its legs or game do later. */
export const statusOf = (b: MyBet): string =>
  num(b.cashout) !== null ? "cashout" : String(b.pick_status ?? b.ticket_status ?? "open").toLowerCase();
/** How a bet counts in the win-loss record (Mike, Oct 26: "pushes should count as losses and cash-outs should be added
 *  to the record as it settles"): won; lost (a push too); void (kept apart); null while its outcome is open. A cash-out
 *  counts as its bet settles once its games are graded; its P/L stays what the book paid back (profit). */
export function recordOutcome(b: MyBet): "won" | "lost" | "void" | null {
  const s = String(b.pick_status ?? b.ticket_status ?? "open").toLowerCase();
  return s === "won" ? "won" : s === "lost" || s === "push" ? "lost" : s === "void" ? "void" : null;
}
/** A status as the app says it. */
export const statusName = (s: string) => (s === "cashout" ? "cashed out" : s);
export const isSettled = (b: MyBet) => SETTLED.includes(statusOf(b));
/** A bet's stake in units (Oct 12: the app counts units only, never dollars or a bankroll); 1 when none is set. */
export const stakeOf = (b: Pick<MyBet, "stake">) => num(b.stake) ?? 1;
/** A bonus bet (Oct 19: new-customer promos): the stake is the book's credit, not cash. A win pays only the profit,
 *  a loss costs nothing, a void returns the credit. It never counts as cash at risk or staked. */
export const isBonus = (b: Pick<MyBet, "bonus">) => b.bonus === true;
export const startOf = (b: MyBet) => b.pick_commence_time ?? b.ticket_commence_time ?? b.game_start ?? null;

/** A game ref's kickoff where the ref carries it ("nba|CHI|WSH|2026-10-24T23:10:00+00:00", soccer the same), else null. */
export function refTime(ref: string | null | undefined): string | null {
  const m = String(ref ?? "").match(/\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?/);
  return m ? m[0] : null;
}

/** The games table's id for a ref without a time: NFL "2026_07_PIT_NO" -> "nfl:2026_07_PIT_NO"; college and NHL refs
 *  are the id ("ncaaf:401856731"). UFC refs name ESPN's fight, not the table's row: null. */
export function refGameId(ref: string | null | undefined): string | null {
  const r = String(ref ?? "");
  if (/^\d{4}_\d{2}_/.test(r)) return `nfl:${r}`;
  return /^(ncaaf|ncaab|nhl|nfl):[^:]+$/.test(r) ? r : null;
}

/** A bet entered by hand or from a slip has no start of its own (Oct 25, Mike: "sort my bets in time order at all
 *  times"): its first game's kickoff, from its refs and the games table's starts ({game_id: start}). */
export function gameStart(b: Pick<MyBet, "games">, starts: Record<string, string>): string | null {
  const times = (b.games ?? []).map((g) => refTime(g.game_ref) ?? starts[refGameId(g.game_ref) ?? ""] ?? null)
    .filter((t): t is string => !!t).map((t) => new Date(t).toISOString());
  return times.length ? times.sort()[0] : null;
}
/** The day a bet belongs to: its game's start, else when it was marked. */
export const dayOf = (b: MyBet) => etDay(startOf(b) ?? b.placed_at);

/** A profit boost (Oct 22, `bets.boost` in percent) multiplies a win's profit; the price stays the book's own. */
export const boostFactor = (b: Pick<MyBet, "boost">) => 1 + Math.max(num(b.boost) ?? 0, 0) / 100;

/** A win's profit with its boost: the book's own profit plus the boost's share of it, never more than the boost's cap
 *  (`boost_cap`, units: the book's "max extra winnings", Oct 30; a capped boost had counted uncapped). A loss is
 *  unchanged. Shared with iPhone BetMath.boosted and fun_ledger.marked_profit (tests/fixtures/promo_profit.json). */
export function boosted(b: Pick<MyBet, "boost" | "boost_cap">, base: number): number {
  if (!(base > 0)) return base;
  const extra = base * (boostFactor(b) - 1), cap = num(b.boost_cap);
  return base + (cap !== null && cap >= 0 ? Math.min(extra, cap) : extra);
}

/** A parlay leg that came off the slip (void or push) takes the price down by its fair chance, as FanDuel
 *  settles it (fun_ledger._finish puts that chance on the leg as `p`). 1 when nothing came off. */
export const voidFactor = (b: MyBet): number =>
  (b.leg_results ?? []).reduce((f, l: any) => (l.result === "void" || l.result === "push") && num(l.p) !== null ? f * num(l.p)! : f, 1);

/** Novig (Oct 28) counts a void leg at its fair value instead of dropping it: the pot (stake / price) times the legs'
 *  values, never under 0.001 of it, so it can pay back less than the stake, and a slip with every leg void still pays
 *  that share (fun_ledger._finish). Null when this rule doesn't apply. */
function novigVoidProfit(b: MyBet, st: number, price: number | null): number | null {
  const f = voidFactor(b);
  if (bookOf(b.book) !== "Novig" || f >= 1 || price === null) return null;
  const p = st * (toDec(price) * Math.max(Math.round(f * 1000) / 1000, 0.001) - 1);
  return boosted(b, p);
}

/** FanDuel's Bet Protect+ (Oct 26, `bets.protect`): 3% of the stake on top, in cash even on a bonus bet, refunded when
 *  the bet is void. */
export const PROTECT_FEE = 0.03;
export const protectFee = (b: Pick<MyBet, "protect" | "stake">) => (b.protect === true ? PROTECT_FEE * stakeOf(b) : 0);

/** Profit in units at the price you took (not the model's logged price), less a Bet Protect+ fee. Null until settled. */
export function profit(b: MyBet): number | null {
  const p = profitBeforeFee(b), s = statusOf(b);
  return p === null ? null : s === "void" ? p : p - protectFee(b);
}

function profitBeforeFee(b: MyBet): number | null {
  const s = statusOf(b);
  const price = num(b.price);
  const st = stakeOf(b);
  if (s === "cashout") return num(b.cashout)! - (isBonus(b) ? 0 : st);   // a bonus bet's stake was never yours
  const novig = s === "won" || s === "void" ? novigVoidProfit(b, st, price) : null;
  if (novig !== null) return novig;
  if (s === "won") {
    if (price !== null) return boosted(b, st * (Math.max(toDec(price) * voidFactor(b), 1) - 1));
    const perUnit = num(b.profit_flat ?? b.profit_1u);
    return perUnit === null ? null : st * perUnit;
  }
  if (s === "lost") return isBonus(b) ? 0 : -st;
  if (s === "push" || s === "void") return 0;
  return null;
}

export type BonusLine = { bets: number; settled: number; won: number; face: number; converted: number; rate: number | null };

/** Bonus bets settled so far: face value used (units), what it turned into, and the conversion rate (cash per unit
 *  of bonus; a fair-priced +400 converts about 80%, a -110 favorite about 45%). Voids return the credit: not used. */
export function bonusSummary(bets: MyBet[]): BonusLine {
  const all = bets.filter(isBonus);
  const done = all.filter((b) => isSettled(b) && statusOf(b) !== "void");
  const face = done.reduce((s, b) => s + stakeOf(b), 0);
  const converted = done.reduce((s, b) => s + (profit(b) ?? 0), 0);
  return { bets: all.length, settled: done.length, won: done.filter((b) => statusOf(b) === "won").length,
           face, converted, rate: face ? converted / face : null };
}

export type BoostLine = { bets: number; settled: number; won: number; units: number; fromBoost: number; staked: number };

/** Boosted cash bets settled so far: their P/L, and the part of it the boosts added (each win's profit beyond what the
 *  book's own price paid, within its cap). Cash-outs count at what they paid back. A boosted bonus bet counts once, as
 *  a bonus (bonusSummary; Oct 30: it was in both). */
export function boostSummary(bets: MyBet[]): BoostLine {
  const all = bets.filter((b) => (num(b.boost) ?? 0) > 0 && !isBonus(b));
  const done = all.filter((b) => isSettled(b) && statusOf(b) !== "void");
  const won = done.filter((b) => statusOf(b) === "won");
  const units = done.reduce((s, b) => s + (profit(b) ?? 0), 0);
  const fromBoost = won.reduce((s, b) => s + (profit(b) ?? 0) - (profit({ ...b, boost: null }) ?? 0), 0);
  return { bets: all.length, settled: done.length, won: won.length, units, fromBoost,
           staked: done.filter((b) => !isBonus(b)).reduce((s, b) => s + stakeOf(b), 0) };
}

export type PromoLedger = { placed: number; settled: number; units: number; expected: number; withEv: number };

/** Bets placed from the promo finder (Oct 30: `promo_ev`, the token's expected dollars at placement): what they turned
 *  into against what the finder expected, in units at the account's unit size. Settled, non-void ones only. */
export function promoLedger(bets: MyBet[], unitDollars: number): PromoLedger {
  const placed = bets.filter((b) => num(b.promo_ev) !== null);
  const done = placed.filter((b) => isSettled(b) && statusOf(b) !== "void");
  return { placed: placed.length, settled: done.length, units: done.reduce((s, b) => s + (profit(b) ?? 0), 0),
           expected: done.reduce((s, b) => s + num(b.promo_ev)! / unitDollars, 0), withEv: done.length };
}

/** CLV at the user's price, retaining the shared close's push adjustment.
 * Older integer football lines may lack closing push probability: don't invent it.
 * A parlay has no sharp closing probability and therefore no CLV. */
export function personalClv(b: MyBet): number | null {
  if (b.kind === "parlay" || b.kind === "custom") return null;
  const isProp = b.pick_kind === "prop" || b.market?.startsWith("player_");
  const originalClv = num(isProp ? b.clv_raw : b.clv);
  if (originalClv === null) return null;
  const price = num(b.price), logged = num(b.logged_price);
  if (price === null) return originalClv;  // no personal price: use the logged pick's close
  if (logged === null) return null;       // old view/fixture cannot establish the original price
  if (price === logged) return originalClv;
  const push = num(b.close_push);
  if (push === null || push < 0 || push > 1) return null;
  if (Math.abs(price) < 100 || Math.abs(logged) < 100) return null;
  // CLV = P(win) * decimal_price + P(push) - 1. Recover P(win) from
  // the original CLV, not from the vigged close_price or corrected prop close.
  const win = (originalClv + 1 - push) / toDec(logged);
  if (win < 0 || win > 1 - push) return null;
  return originalClv + win * (toDec(price) - toDec(logged));
}

const KIND: Record<string, string> = { sgp: "Same-game parlays", sgp_plus: "SGP+ tickets", td: "Anytime TD tickets", over: "Overs" };

/** The row a bet counts under in the record: sport and market for single bets, the ticket type for parlays. */
export function groupOf(b: MyBet): string {
  if (b.kind === "custom") return "Your own parlays";
  if (b.kind === "parlay") return KIND[b.ticket_kind ?? ""] ?? (b.sgp_id?.startsWith("plus-") ? KIND.sgp_plus
    : b.sgp_id?.startsWith("td-") ? KIND.td : KIND.sgp);
  return `${sportName(b.league)} · ${marketName(b.market) || "Bet"}`;
}

export type Line = { group: string; bets: number; won: number; lost: number; push: number; staked: number; units: number;
  clvN: number; clvSum: number; beat: number };

/** The book a bet was placed at (FanDuel, DraftKings, or Novig: its bets also arrive from the Novig sync, Oct 23);
 *  bets from before Oct 12 are FanDuel's. */
export const bookOfBet = (b: Pick<MyBet, "book">) => bookOf(b.book);

/** Settled bets grouped by `groupBy` (the market by default; bookOfBet for the record by book), with a total. */
export function record(bets: MyBet[], groupBy: (b: MyBet) => string = groupOf): { lines: Line[]; total: Line } {
  const by = new Map<string, Line>();
  const blank = (group: string): Line => ({ group, bets: 0, won: 0, lost: 0, push: 0, staked: 0, units: 0, clvN: 0, clvSum: 0, beat: 0 });
  const total = blank("All bets");
  for (const b of bets.filter(isSettled)) {
    const g = groupBy(b);
    if (!by.has(g)) by.set(g, blank(g));
    const s = statusOf(b), r = recordOutcome(b);
    const clv = personalClv(b);
    for (const l of [by.get(g)!, total]) {
      l.bets++;
      if (r === "won") l.won++; else if (r === "lost") l.lost++; else if (r === "void") l.push++;   // push: voids only (Oct 26)
      if (s !== "void" && !isBonus(b)) l.staked += stakeOf(b);    // ROI is on cash: a bonus stake was never yours
      l.units += profit(b) ?? 0;
      if (clv !== null) { l.clvN++; l.clvSum += clv; if (clv > 0) l.beat++; }
    }
  }
  return { lines: [...by.values()].sort((a, b) => b.bets - a.bets || a.group.localeCompare(b.group)), total };
}

/** Which bets are "your record" (Mike, Oct 14: "on October 18th my record is clear"). Once real money starts for
 *  the account (realMode: Oct 18 00:00 ET or user_settings.real_from), only real bets count, from 0-0 even before
 *  the first one is marked; before that, every bet counts (paper). Paper bets are never deleted: they show apart. */
export function recordBets<T extends Pick<MyBet, "mode">>(bets: T[], realMode: boolean): { useReal: boolean; counted: T[]; paper: T[] } {
  const real = bets.filter((b) => b.mode === "real");
  const useReal = realMode || real.length > 0;
  return { useReal, counted: useReal ? real : bets, paper: bets.filter((b) => b.mode !== "real") };
}

/** Units put on parlays this month (the fun bucket, in units a month); bonus bets cost no cash. */
export function bucketUsed(bets: Pick<MyBet, "kind" | "mode" | "stake" | "placed_at" | "bonus">[], now = new Date()): number {
  const month = etDay(now).slice(0, 7);
  return bets.filter((b) => (b.kind === "parlay" || b.kind === "custom") && !isBonus(b) && etDay(b.placed_at).startsWith(month))
    .reduce((s, b) => s + stakeOf(b), 0);
}

/** Units at risk on real bets for games on an Eastern day (the 5-unit daily cap); a bonus bet risks no cash. */
export function atRiskOn(bets: MyBet[], day: string): number {
  return bets.filter((b) => b.mode === "real" && !isBonus(b) && !isSettled(b) && dayOf(b) === day).reduce((s, b) => s + stakeOf(b), 0);
}
