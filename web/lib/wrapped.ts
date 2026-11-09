// BetLab Wrapped (Mike's W17, Oct 27): a month or the season as a tap-through story, like Spotify Wrapped. Your
// bottom line, the biggest hit, the leg that broke your heart, your player, your book, your betting type, your best
// day and the badges you earned. Pure, from the same settled bets as the Record tab (record(), profit(), chrono()), so
// every number matches it; app/wrapped draws the story and app/api/wrapped the picture to share.
import { achievements } from "./achievements";
import { bookOfBet, dayOf, isBonus, personalClv, profit, record, type Line } from "./bets";
import type { MyBet } from "./data";
import { num } from "./format";
import { players, type Player } from "./players";
import { card, type CardLeg } from "./share";
import { chrono, legsOf, sportOf, streaks } from "./stats";

/** "2026-10" (a month, Eastern game days) or "season" (every bet). */
export type Period = string;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** A period's name: "October" (this year's), "October 2025", "Your season". */
export function periodName(p: Period, now = new Date()): string {
  if (p === "season") return "Your season";
  const [y, m] = p.split("-").map(Number);
  return `${MONTHS[m - 1]}${y === now.getUTCFullYear() ? "" : ` ${y}`}`;
}

/** The months with a settled bet, newest first, then "season" when there's more than one month. */
export function periods(bets: MyBet[]): Period[] {
  const months = [...new Set(chrono(bets).map((b) => dayOf(b).slice(0, 7)))].sort().reverse();
  return months.length > 1 ? [...months, "season"] : months;
}

export const inPeriod = (b: MyBet, p: Period) => p === "season" || dayOf(b).startsWith(p);

/** A bet as Wrapped shows it: what it was, its price and day, the units, and its legs with their results. */
export type Shown = { title: string; price: string; day: string; units: number; legs: CardLeg[]; more: number; book: string };
const shown = (b: MyBet): Shown => {
  const c = card(b);
  return { title: c.title, price: c.price, day: dayOf(b), units: profit(b) ?? 0, legs: c.legs, more: c.more, book: c.book };
};

/** Your betting type: the first that fits, in this order (each needs enough bets to mean something). */
export type Persona = { name: string; why: string };
export function persona(bets: MyBet[]): Persona {
  const n = bets.length;
  const share = (f: (b: MyBet) => boolean) => bets.filter(f).length / Math.max(n, 1);
  const clv = bets.map(personalClv).filter((x): x is number => x !== null);
  const prices = bets.map((b) => num(b.price)).filter((x): x is number => x !== null).sort((a, b) => a - b);
  const median = prices.length ? prices[Math.floor(prices.length / 2)] : null;
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  const bySport = record(bets, sportOf).lines.filter((l) => l.group !== "Multi-sport" && l.group !== "Other");
  const top = bySport[0];
  if (clv.length >= 5 && clv.filter((x) => x > 0).length / clv.length >= 0.6)
    return { name: "The Sharp", why: `You beat the closing line on ${clv.filter((x) => x > 0).length} of ${clv.length} bets. That's the real scoreboard.` };
  if (n >= 5 && share((b) => legsOf(b) >= 5) >= 0.5)
    return { name: "The Parlay Architect", why: `${pct(share((b) => legsOf(b) >= 5))} of your bets had 5 or more legs. Go big or go home.` };
  if (n >= 5 && share(isBonus) >= 0.5)
    return { name: "The Bonus Hunter", why: `${pct(share(isBonus))} of your bets were the books' own money.` };
  if (n >= 5 && median !== null && median >= 800)
    return { name: "The Long-Shot Dreamer", why: `Your typical bet paid +${median}. One hit pays for a lot of misses.` };
  if (n >= 5 && top && top.bets / n >= 0.6)
    return { name: `The ${top.group} Loyalist`, why: `${top.bets} of your ${n} bets were ${top.group}.` };
  if (n >= 5 && share((b) => legsOf(b) === 1) >= 0.6)
    return { name: "The Straight Shooter", why: `${pct(share((b) => legsOf(b) === 1))} of your bets were singles.` };
  return { name: "The All-Rounder", why: `${bySport.length} sport${bySport.length === 1 ? "" : "s"}, singles and parlays: a bit of everything.` };
}

/** The parlay that lost by exactly one leg (every other leg won), the longest price first: the leg that broke your heart. */
export function heartbreak(bets: MyBet[]): { bet: Shown; leg: CardLeg; hit: number } | null {
  let best: { b: MyBet; leg: CardLeg; n: number } | null = null;
  for (const b of bets) {
    const c = card(b);
    if (c.status !== "ONE LEG AWAY") continue;
    const leg = c.legs.find((l) => l.result === "lost");     // card() shows the first 10 legs: past that, it's skipped
    if (leg && (!best || (num(b.price) ?? 0) > (num(best.b.price) ?? 0))) best = { b, leg, n: legsOf(b) };
  }
  return best ? { bet: shown(best.b), leg: best.leg, hit: best.n - 1 } : null;
}

export type Wrapped = {
  period: Period; name: string;
  total: Line; roi: number | null; days: number; sports: number; legs: number;
  best: Shown | null; heartbreak: ReturnType<typeof heartbreak>;
  player: Player | null; book: Line | null; books: Line[];
  persona: Persona;
  bestDay: { day: string; units: number; bets: number } | null; busiest: { day: string; bets: number } | null; bestRun: number;
  badges: { icon: string; title: string; how: string; day: string }[];
};

/** Everything a period's story shows, or null when it has no settled bet. */
export function wrapped(all: MyBet[], period: Period, now = new Date()): Wrapped | null {
  const bets = chrono(all).filter((b) => inPeriod(b, period));
  if (!bets.length) return null;
  const total = record(bets).total;
  const byDay = new Map<string, { units: number; bets: number }>();
  for (const b of bets) {
    const d = byDay.get(dayOf(b)) ?? { units: 0, bets: 0 };
    d.units += profit(b) ?? 0; d.bets++;
    byDay.set(dayOf(b), d);
  }
  const days = [...byDay.entries()].map(([day, d]) => ({ day, ...d }));
  const bestDay = days.reduce<(typeof days)[number] | null>((m, d) => (d.units > 0 && (!m || d.units > m.units) ? d : m), null);
  const busiest = days.reduce((m, d) => (d.bets > m.bets ? d : m), days[0]);
  const winner = bets.reduce<MyBet | null>((m, b) => ((profit(b) ?? 0) > 0 && (!m || profit(b)! > profit(m)!) ? b : m), null);
  const books = record(bets, bookOfBet).lines;
  const book = books.length > 1 ? [...books].sort((a, b) => b.units - a.units)[0] : books[0] ?? null;
  // badges count from your whole history (one is earned once), shown when the bet that earned it is in this period
  const badges = achievements(all).filter((x) => x.by && inPeriod(x.by, period))
    .map((x) => ({ icon: x.icon, title: x.title, how: x.how, day: x.earned! }));
  return {
    period, name: periodName(period, now),
    total, roi: total.staked ? total.units / total.staked : null,
    days: byDay.size, sports: new Set(bets.map(sportOf).filter((s) => s !== "Multi-sport" && s !== "Other")).size,
    legs: bets.reduce((s, b) => s + legsOf(b), 0),
    best: winner ? shown(winner) : null, heartbreak: heartbreak(bets),
    player: players(bets, 2)[0] ?? null, book, books,
    persona: persona(bets),
    bestDay, busiest: busiest.bets > 1 ? { day: busiest.day, bets: busiest.bets } : null, bestRun: streaks(bets).bestWin,
    badges,
  };
}
