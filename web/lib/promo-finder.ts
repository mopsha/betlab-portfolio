// The promo finder (Oct 30; Mike: the old finder's "how it decides what bet is best" needed a rework). It takes the
// bets builder.promoCandidates weighs (singles priced off a sharp book, same-game slips at a cautious quote, plain
// parlays at their exact price) and the two-book locks (findLocks), and ranks them one way for every token:
//   - one number, the token's expected dollars: a bonus bet's S·p·(d−1) (its stake is the book's), a boost's whole
//     cash bet S·(p·(d−1+extra) − (1−p)) with the boost's extra capped, a lock's sure S·locked;
//   - and the chance it hits, so every result reads "turns your $10 bonus bet into $6.20 on average · hits 31%";
//   - three modes (Mike: "let me switch"): Max value ranks by expected dollars down to an 8% chance; Balanced (the
//     default) the same among the token's likelier bets; Safe its likeliest, locks first. Safe also prices same-game
//     slips one more quote-model miss down. Balanced and Safe follow what the token can reach (Nov 6, Mike: boosts "never
//     have safe or balanced options"): a boost's value falls as the chance rises, and a 3-leg +100 boost has no 45% bet,
//     so fixed floors left both empty. Of the bets worth something, Balanced takes those at least as likely as the median
//     one (never asking more than 25%), Safe those in the likeliest quarter (never asking more than 45%), each worth at
//     least 60% of the best in its own band. Judgment calls, not backtested: docs/DECISIONS.md (2026-10-30, 2026-11-06).
// Pure; iPhone PromoFinder.swift is the same, and tests/fixtures/promo_finder.json holds both to it.
import type { LockPick, Promo, PromoPick, SlipLeg } from "./builder";
import { toDec } from "./format";

export type Mode = "max" | "balanced" | "safe";
export const MODES: { key: Mode; label: string; floor: number; blurb: string }[] = [
  { key: "max", label: "Max value", floor: 0.08, blurb: "The most the token is worth on average, long shots included." },
  { key: "balanced", label: "Balanced", floor: 0.25, blurb: "The most it's worth among its likelier bets (1 in 4 or better when it has them)." },
  { key: "safe", label: "Safe", floor: 0.45, blurb: "The likeliest bets this token allows that are still worth having." },
];
export const SAFE_SHARE = 0.6;
export const DEFAULT_DOLLARS = 10;

export type Kind = "single" | "parlay" | "sgp" | "lock";
export type Result = {
  kind: Kind; legs: SlipLeg[]; p: number; games: number;
  dec: number;          // the likely price (exact for a single, a plain parlay or a lock)
  at: number;           // the price it's ranked at (a same-game slip's cautious quote)
  value: number;        // the token's expected dollars
  boostAdds: number;    // a boost: the part of `value` the boost adds
  lock?: LockPick;
  text: string;         // what it does, in words
};

/** The token's dollars: its amount, else $10 (the finder then says "per $10"). */
export const tokenDollars = (promo: Promo) => (promo.kind !== "none" && promo.stake && promo.stake > 0 ? promo.stake : DEFAULT_DOLLARS);

function extraOf(dec: number, promo: Promo, S: number): number {
  if (promo.kind !== "boost") return 0;
  const extra = (dec - 1) * promo.pct / 100;
  return promo.maxExtra != null && promo.maxExtra > 0 ? Math.min(extra, promo.maxExtra / S) : extra;
}

/** The token's expected dollars on a bet with chance `p` at decimal `dec`, for a token of S dollars. */
export function tokenValue(p: number, dec: number, promo: Promo, S: number): number {
  if (promo.kind === "bonus") return S * p * (dec - 1);
  return S * (p * (dec - 1 + extraOf(dec, promo, S)) - (1 - p));
}

/** A boost's share of that: S·p·extra. */
export const boostAdds = (p: number, dec: number, promo: Promo, S: number) => S * p * extraOf(dec, promo, S);

const money = (x: number) => `${x < 0 ? "−" : ""}$${Math.abs(x).toFixed(2)}`;
const pctText = (p: number) => `${Math.round(p * 100)}%`;
const ORDER: Record<Kind, number> = { single: 0, parlay: 1, lock: 2, sgp: 3 };    // ties: what's surest about its price first

/** What a result does, in words. */
export function explain(r: Omit<Result, "text">, promo: Promo, S: number, perDefault: boolean): string {
  const tok = perDefault ? "each $10 of it" : `your ${money(S).replace(".00", "")} ${promo.kind === "bonus" ? "bonus bet" : "boosted bet"}`;
  // a lock's sure thing is the pair, not either bet (Oct 30: "100% to hit" on a +250 read as the +250 being sure)
  if (r.kind === "lock") return `Two bets: the promo on the first side, ${money(S * (r.lock?.hedge ?? 0))} cash on the other. Whichever side wins, you're up ${money(r.value)}`;
  if (promo.kind === "bonus") return `Turns ${tok} into ${money(r.value)} on average · hits ${pctText(r.p)}`;
  return `Expected ${money(r.value)} on ${tok} · the boost adds ${money(r.boostAdds)} · hits ${pctText(r.p)}`;
}

/** The q-th quantile of xs (linear between ranks, as numpy's default); the iPhone's PromoFinder.quantile is the same. */
export function quantile(xs: number[], q: number): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b), pos = (s.length - 1) * q, lo = Math.floor(pos);
  return lo + 1 < s.length ? s[lo] + (s[lo + 1] - s[lo]) * (pos - lo) : s[lo];
}

/** The chance a mode asks for on this token: Max value's fixed 8%; Balanced and Safe their floor, or lower when the
 *  token's bets worth something don't reach it (their median, their top quarter). */
export function floorFor(mode: Mode, worth: number[]): number {
  const fixed = MODES.find((m) => m.key === mode)!.floor;
  if (mode === "max" || !worth.length) return fixed;
  return Math.min(fixed, quantile(worth, mode === "balanced" ? 0.5 : 0.75));
}

/** The ranked list for a token: at most `top`, each bet once. */
export function rank(picks: PromoPick[], locks: LockPick[], promo: Promo, mode: Mode, top = 10): Result[] {
  if (promo.kind === "none") return [];
  const S = tokenDollars(promo), perDefault = !(promo.stake && promo.stake > 0);
  const all: Omit<Result, "text">[] = [];
  for (const k of picks) {
    const kind: Kind = k.legs.length === 1 ? "single" : k.plain ? "parlay" : "sgp";
    // Safe: a same-game slip one more quote-model miss down (low/dec is one miss, never below the legs' product cap)
    const at = mode === "safe" && kind === "sgp" ? k.low * (k.low / k.dec) : k.low;
    all.push({ kind, legs: k.legs, p: k.p, games: k.games, dec: k.dec, at, value: tokenValue(k.p, at, promo, S),
               boostAdds: boostAdds(k.p, at, promo, S) });
  }
  for (const l of locks) {
    const d = toDec(l.promoPrice);
    all.push({ kind: "lock", legs: [{ event_id: l.event_id, label: l.promoLeg }], p: 1, games: 1, dec: d, at: d,
               value: S * l.locked, boostAdds: 0, lock: l });
  }
  // Balanced and Safe ask only what this token's bets worth something can reach
  const floor = floorFor(mode, all.filter((r) => r.value > 1e-9).map((r) => r.p));
  const tie = (a: Omit<Result, "text">, b: Omit<Result, "text">) => ORDER[a.kind] - ORDER[b.kind];
  let list = all.filter((r) => r.p >= floor - 1e-12);
  if (mode !== "max") list = list.filter((r) => r.value > 1e-9);
  if (mode === "safe") {
    const best = Math.max(0, ...list.map((r) => r.value));
    list = list.filter((r) => r.value >= SAFE_SHARE * best - 1e-9)
      .sort((a, b) => (b.kind === "lock" ? 1 : 0) - (a.kind === "lock" ? 1 : 0) || b.p - a.p || b.value - a.value || tie(a, b));
  } else {
    list.sort((a, b) => b.value - a.value || tie(a, b));
  }
  const seen = new Set<string>(), uses = new Map<string, number>(), out: Result[] = [], skipped: typeof list = [];
  let unders = 0;
  const legKey = (l: SlipLeg) => `${l.event_id}:${l.label}`;
  const take = (r: (typeof list)[number]) => {
    for (const l of r.legs) uses.set(legKey(l), (uses.get(legKey(l)) ?? 0) + 1);
    if (allUnder(r.legs)) unders++;
    out.push({ ...r, text: explain(r, promo, S, perDefault) });
  };
  for (const r of list) {
    if (out.length >= top) break;
    const key = r.kind + "|" + r.legs.map(legKey).sort().join("+");
    if (seen.has(key)) continue;
    seen.add(key);
    // a varied list (Nov 8, Mike: "shouldn't give all unders"): a leg in two results at most, all-under bets half the list
    if (r.legs.some((l) => (uses.get(legKey(l)) ?? 0) >= MAX_LEG_USES) || (allUnder(r.legs) && unders >= Math.floor(top / 2))) {
      skipped.push(r);
      continue;
    }
    take(r);
  }
  for (const r of skipped) { if (out.length >= top) break; take(r); }   // too few others: the best of the rest, in order
  return out;
}

/** A leg shows in at most this many results, and bets whose legs are all unders fill at most half the list (Nov 8): the
 *  ranking alone gave tonight's NBA 9 all-under results of 10 and one under in 5 of them. Books shade overs, so unders
 *  price a little better against the sharp line on average (0.949 vs 0.937 of fair on Nov 8), and every near-tie went
 *  their way. */
export const MAX_LEG_USES = 2;
export const allUnder = (legs: SlipLeg[]) => legs.length > 0 && legs.every((l) => /\bunder\b/i.test(l.label));

export type Scope = { kind: "slice"; key: string } | { kind: "games"; events: string[] } | { kind: "game"; event: string } | { kind: "today" };
export const TODAY_CAP = 30;       // "anything today" searches the next 30 games, across sports

/** The games a scope searches, soonest first; a token's sports narrow it. */
export function scopeEvents(scope: Scope, games: { event_id: string; sport: string; commence_time: string }[],
                            slices: { key: string; events: string[] }[], sports: string[] | null = null, now = new Date()): string[] {
  const ok = games.filter((g) => Date.parse(g.commence_time) > now.getTime() && (!sports?.length || sports.includes(g.sport)))
    .sort((a, b) => a.commence_time.localeCompare(b.commence_time));
  const has = new Set(ok.map((g) => g.event_id));
  if (scope.kind === "game") return has.has(scope.event) ? [scope.event] : [];
  if (scope.kind === "games") return scope.events.filter((e) => has.has(e));
  if (scope.kind === "slice") return (slices.find((s) => s.key === scope.key)?.events ?? []).filter((e) => has.has(e));
  const day = (t: string) => new Date(t).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  const today = day(now.toISOString());
  const first = ok.filter((g) => day(g.commence_time) === today);
  return (first.length ? first : ok.filter((g) => day(g.commence_time) === day(ok[0]?.commence_time ?? now.toISOString())))
    .slice(0, TODAY_CAP).map((g) => g.event_id);
}
