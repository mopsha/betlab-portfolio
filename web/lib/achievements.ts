// Achievements (Mike's W29, Oct 24; "a crap ton" more, Oct 27): badges earned from the bet history, each with the bet
// and day that earned it, and progress toward the ones still locked. Pure: worked out from the bets on every view, never
// stored. Nothing here rewards betting more: no badge counts bets placed or stakes; they're about winning, hitting legs,
// trying markets and books, and beating the close.
import { bookOfBet, dayOf, isBonus, personalClv, profit, startOf, statusOf } from "./bets";
import type { MyBet } from "./data";
import { num } from "./format";
import { chrono, legsOf, sportOf } from "./stats";

export type Group = "Milestones" | "Long shots" | "Parlays" | "Sports" | "Legs" | "Books and promos" | "Sharp" | "Days and runs";
export const GROUPS: Group[] = ["Milestones", "Long shots", "Parlays", "Sports", "Legs", "Books and promos", "Sharp", "Days and runs"];

export type Badge = { id: string; icon: string; title: string; how: string; group: Group; earned: string | null; by: MyBet | null;
  progress?: { have: number; need: number } };

type Hit = { by: MyBet | null; have?: number; need?: number };
type Def = { id: string; icon: string; title: string; how: string; group: Group;
  /** walk the settled bets in order; return the bet that earns it (and progress) */
  test: (bets: MyBet[]) => Hit };

const won = (b: MyBet) => statusOf(b) === "won";
const lost = (b: MyBet) => statusOf(b) === "lost";
const price = (b: MyBet) => num(b.price) ?? 0;
const games = (b: MyBet) => new Set((b.games ?? []).map((g) => g.game_ref ?? g.matchup)).size;

/** The first bet meeting `f`, in settled order. */
const first = (f: (b: MyBet) => boolean) => (bets: MyBet[]): Hit => ({ by: bets.find(f) ?? null });

/** The bet that brings a count to `need` (counting bets meeting `f`), with progress. */
const count = (need: number, f: (b: MyBet) => boolean) => (bets: MyBet[]): Hit => {
  let have = 0;
  for (const b of bets) if (f(b) && ++have === need) return { by: b, have, need };
  return { by: null, have, need };
};

/** The bet that makes the distinct values of `key` (over bets meeting `f`) reach `need`. */
const distinct = (need: number, f: (b: MyBet) => boolean, key: (b: MyBet) => string) => (bets: MyBet[]): Hit => {
  const seen = new Set<string>();
  for (const b of bets) if (f(b)) { seen.add(key(b)); if (seen.size === need) return { by: b, have: need, need }; }
  return { by: null, have: seen.size, need };
};

/** `need` wins in a row (a loss breaks it; voids and cash-outs neither extend nor break it). */
const run = (need: number) => (bets: MyBet[]): Hit => {
  let n = 0, best = 0;
  for (const b of bets) {
    if (won(b)) { n++; best = Math.max(best, n); if (n === need) return { by: b, have: need, need }; }
    else if (lost(b)) n = 0;
  }
  return { by: null, have: best, need };
};

/** Up `need` units overall at some point. */
const up = (need: number) => (bets: MyBet[]): Hit => {
  let total = 0, best = 0;
  for (const b of bets) { total += profit(b) ?? 0; best = Math.max(best, total); if (total >= need) return { by: b, have: need, need }; }
  return { by: null, have: Math.max(0, Math.floor(best)), need };
};

// ---- legs: each leg with its graded result (a single takes the bet's own), as the Share card and player cards read them
type Leg = { label: string; result: "won" | "lost" | "void" | "open"; value: number | null };
export function legsWithResults(b: MyBet): Leg[] {
  const labels = b.legs?.length ? b.legs : b.label ? [b.label] : [];
  const results = b.leg_results ?? [];
  const used = new Set<number>();
  const s = statusOf(b);
  return labels.map((label) => {
    const i = results.findIndex((r, k) => !used.has(k) && r.leg === label);
    if (i >= 0) used.add(i);
    const r = i >= 0 ? results[i] : null;
    const result = r?.result === "won" || r?.result === "lost" ? r.result : r?.result === "void" || r?.result === "push" ? "void"
      : labels.length === 1 && (s === "won" || s === "lost") ? s : "open";
    return { label, result, value: r?.value ?? null };
  });
}
/** The bet that brings the count of won legs matching `re` (and `min`: the line it needed, e.g. 300 for "300+") to `need`. */
const legs = (need: number, re: RegExp, min = 0) => (bets: MyBet[]): Hit => {
  let have = 0;
  for (const b of bets) {
    for (const l of legsWithResults(b)) {
      if (l.result !== "won" || !re.test(l.label)) continue;
      const plus = /(\d+(?:\.\d+)?)\+/.exec(l.label)?.[1], over = /over (\d+(?:\.\d+)?)/i.exec(l.label)?.[1];
      const line = plus ? Number(plus) : over ? Math.ceil(Number(over)) : 0;      // "over 299.5" is 300+
      if (line >= min && ++have === need) return { by: b, have, need };
    }
  }
  return { by: null, have, need };
};
const wonLegs = (need: number) => legs(need, /./);

// ---- days, weeks and months (Eastern game days)
const etHour = (iso: string) => Number(new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", hour: "numeric", hourCycle: "h23" }));
const weekOf = (b: MyBet) => { const d = new Date(`${dayOf(b)}T12:00:00Z`); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); return d.toISOString().slice(0, 10); };
type Span = { n: number; won: number; lost: number; units: number; last: MyBet };
function spans(bets: MyBet[], key: (b: MyBet) => string): [string, Span][] {
  const by = new Map<string, Span>();
  for (const b of bets) {
    const k = key(b), s = by.get(k) ?? { n: 0, won: 0, lost: 0, units: 0, last: b };
    s.n++; s.units += profit(b) ?? 0; s.last = b; if (won(b)) s.won++; if (lost(b)) s.lost++;
    by.set(k, s);
  }
  return [...by.entries()];
}
/** A finished span (a week, a month) that meets `f`; the bet that closed it. `ends`: the span's last day from its key. */
const span = (key: (b: MyBet) => string, ends: (k: string) => string, f: (s: Span) => boolean) => (bets: MyBet[]): Hit => {
  const today = new Date().toISOString().slice(0, 10);
  for (const [k, s] of spans(bets, key)) if (ends(k) < today && f(s)) return { by: s.last };
  return { by: null };
};
const weekEnd = (k: string) => { const d = new Date(`${k}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + 6); return d.toISOString().slice(0, 10); };
const monthEnd = (k: string) => { const [y, m] = k.split("-").map(Number); return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10); };
/** A day (all of a day's bets) that meets `f`. */
const day = (f: (s: Span) => boolean) => (bets: MyBet[]): Hit => {
  for (const [, s] of spans(bets, dayOf)) if (f(s)) return { by: s.last };
  return { by: null };
};
/** Days in a row with a winning bet. */
const winDays = (need: number) => (bets: MyBet[]): Hit => {
  const days = [...new Set(bets.filter(won).map(dayOf))].sort();
  let n = 0, best = 0;
  for (let i = 0; i < days.length; i++) {
    const prev = i ? new Date(`${days[i - 1]}T12:00:00Z`) : null;
    n = prev && (new Date(`${days[i]}T12:00:00Z`).getTime() - prev.getTime()) === 86_400_000 ? n + 1 : 1;
    best = Math.max(best, n);
    if (n === need) return { by: bets.filter(won).find((b) => dayOf(b) === days[i]) ?? null, have: need, need };
  }
  return { by: null, have: best, need };
};

const SPORT = (s: string) => (b: MyBet) => won(b) && sportOf(b) === s;
const realSports = (b: MyBet) => sportOf(b) !== "Multi-sport" && sportOf(b) !== "Other";

export const DEFS: Def[] = [
  // ---- Milestones
  { id: "first-win", group: "Milestones", icon: "🎯", title: "On the board", how: "Win your first bet", test: first(won) },
  { id: "wins-10", group: "Milestones", icon: "🔟", title: "Ten-piece", how: "Win 10 bets", test: count(10, won) },
  { id: "wins-25", group: "Milestones", icon: "🥉", title: "Quarter century", how: "Win 25 bets", test: count(25, won) },
  { id: "wins-50", group: "Milestones", icon: "🥈", title: "Half century", how: "Win 50 bets", test: count(50, won) },
  { id: "wins-100", group: "Milestones", icon: "🥇", title: "Centurion", how: "Win 100 bets", test: count(100, won) },
  { id: "up-ten", group: "Milestones", icon: "🏔️", title: "Double digits", how: "Be up 10 units overall", test: up(10) },
  { id: "up-25", group: "Milestones", icon: "🗻", title: "Quarter stack", how: "Be up 25 units overall", test: up(25) },
  { id: "up-50", group: "Milestones", icon: "🚁", title: "Fifty up", how: "Be up 50 units overall", test: up(50) },
  { id: "up-100", group: "Milestones", icon: "🛰️", title: "Triple digits", how: "Be up 100 units overall", test: up(100) },
  { id: "comeback", group: "Milestones", icon: "🔄", title: "Comeback kid", how: "Get back above zero after being down 5 units", test: (bets) => {
    let total = 0, low = 0;
    for (const b of bets) { total += profit(b) ?? 0; low = Math.min(low, total); if (low <= -5 && total > 0) return { by: b }; }
    return { by: null };
  } },
  { id: "big-win", group: "Milestones", icon: "💰", title: "Big score", how: "Win 10 units or more on one bet", test: first((b) => (profit(b) ?? 0) >= 10) },
  { id: "huge-win", group: "Milestones", icon: "🏦", title: "Bank job", how: "Win 25 units or more on one bet", test: first((b) => (profit(b) ?? 0) >= 25) },

  // ---- Long shots
  { id: "dog-day", group: "Long shots", icon: "🐶", title: "Dog day", how: "Win a bet at +200 or longer", test: first((b) => won(b) && price(b) >= 200) },
  { id: "long-shot", group: "Long shots", icon: "🚀", title: "Long shot", how: "Win a bet at +500 or longer", test: first((b) => won(b) && price(b) >= 500) },
  { id: "four-figures", group: "Long shots", icon: "💎", title: "Four figures", how: "Win a bet at +1000 or longer", test: first((b) => won(b) && price(b) >= 1000) },
  { id: "moonshot", group: "Long shots", icon: "🌙", title: "Moonshot", how: "Win a bet at +2500 or longer", test: first((b) => won(b) && price(b) >= 2500) },
  { id: "lottery", group: "Long shots", icon: "🎰", title: "Lottery ticket", how: "Win a bet at +5000 or longer", test: first((b) => won(b) && price(b) >= 5000) },
  { id: "unicorn", group: "Long shots", icon: "🦄", title: "Unicorn", how: "Win a bet at +10000 or longer", test: first((b) => won(b) && price(b) >= 10000) },
  { id: "dog-pack", group: "Long shots", icon: "🐺", title: "Dog pack", how: "Win 5 bets at +300 or longer", test: count(5, (b) => won(b) && price(b) >= 300) },
  { id: "chalk", group: "Long shots", icon: "🧱", title: "Chalk eater", how: "Win 5 bets at -200 or shorter", test: count(5, (b) => won(b) && price(b) <= -200) },
  { id: "coin-flip", group: "Long shots", icon: "🪙", title: "Coin flip", how: "Win a bet at even money (+100)", test: first((b) => won(b) && price(b) === 100) },
  { id: "lucky-sevens", group: "Long shots", icon: "7️⃣", title: "Lucky sevens", how: "Win a bet priced +777 or +7777", test: first((b) => won(b) && (price(b) === 777 || price(b) === 7777)) },

  // ---- Parlays
  { id: "two-step", group: "Parlays", icon: "✌️", title: "Two-step", how: "Hit a 2-leg parlay", test: first((b) => won(b) && legsOf(b) === 2) },
  { id: "three-peat", group: "Parlays", icon: "🔺", title: "Three-peat", how: "Hit a parlay with 3 or more legs", test: first((b) => won(b) && legsOf(b) >= 3) },
  { id: "five-legs", group: "Parlays", icon: "🖐️", title: "Five alive", how: "Hit a parlay with 5 or more legs", test: first((b) => won(b) && legsOf(b) >= 5) },
  { id: "eight-legs", group: "Parlays", icon: "🎱", title: "Eight ball", how: "Hit a parlay with 8 or more legs", test: first((b) => won(b) && legsOf(b) >= 8) },
  { id: "ten-legs", group: "Parlays", icon: "🐙", title: "Octopus and then some", how: "Hit a parlay with 10 or more legs", test: first((b) => won(b) && legsOf(b) >= 10) },
  { id: "parlays-5", group: "Parlays", icon: "🧩", title: "Puzzle master", how: "Hit 5 parlays", test: count(5, (b) => won(b) && legsOf(b) > 1) },
  { id: "parlays-20", group: "Parlays", icon: "🏗️", title: "Parlay architect", how: "Hit 20 parlays", test: count(20, (b) => won(b) && legsOf(b) > 1) },
  { id: "cross-country", group: "Parlays", icon: "🗺️", title: "Cross-country", how: "Hit a parlay across 3 or more games", test: first((b) => won(b) && games(b) >= 3) },
  { id: "mixtape", group: "Parlays", icon: "📼", title: "Mixtape", how: "Hit a parlay that mixes sports", test: first((b) => won(b) && sportOf(b) === "Multi-sport") },
  { id: "sgp-hero", group: "Parlays", icon: "🎬", title: "Same-game hero", how: "Hit a 4+ leg parlay on one game", test: first((b) => won(b) && legsOf(b) >= 4 && games(b) <= 1) },
  { id: "heartbreak", group: "Parlays", icon: "💔", title: "Heartbreaker", how: "Lose a 4+ leg parlay by one leg (it happens)", test: first((b) => lost(b) && legsOf(b) >= 4
      && legsWithResults(b).filter((l) => l.result === "lost").length === 1 && legsWithResults(b).every((l) => l.result !== "open")) },
  { id: "agony", group: "Parlays", icon: "😩", title: "Agony", how: "Lose 3 parlays by one leg", test: count(3, (b) => lost(b) && legsOf(b) >= 2
      && legsWithResults(b).filter((l) => l.result === "lost").length === 1 && legsWithResults(b).every((l) => l.result !== "open")) },

  // ---- Sports
  { id: "gridiron", group: "Sports", icon: "🏈", title: "Gridiron", how: "Win an NFL bet", test: first(SPORT("NFL")) },
  { id: "campus", group: "Sports", icon: "🎓", title: "Campus", how: "Win a college football bet", test: first(SPORT("College football")) },
  { id: "buckets", group: "Sports", icon: "🏀", title: "Buckets", how: "Win an NBA bet", test: first(SPORT("NBA")) },
  { id: "march", group: "Sports", icon: "🏆", title: "Ready for March", how: "Win a college basketball bet", test: first(SPORT("College basketball")) },
  { id: "biscuit", group: "Sports", icon: "🏒", title: "Biscuit in the basket", how: "Win an NHL bet", test: first(SPORT("NHL")) },
  { id: "golazo", group: "Sports", icon: "⚽", title: "Golazo", how: "Win a soccer bet", test: first(SPORT("Soccer")) },
  { id: "fight-night", group: "Sports", icon: "🥊", title: "Fight night", how: "Win a UFC bet", test: first(SPORT("UFC")) },
  { id: "all-rounder", group: "Sports", icon: "🌎", title: "All-rounder", how: "Win bets in 4 different sports", test: distinct(4, (b) => won(b) && realSports(b), sportOf) },
  { id: "globetrotter", group: "Sports", icon: "✈️", title: "Globetrotter", how: "Win bets in 6 different sports", test: distinct(6, (b) => won(b) && realSports(b), sportOf) },
  { id: "specialist", group: "Sports", icon: "🔬", title: "Specialist", how: "Win 15 bets in one sport", test: (bets) => {
    const by = new Map<string, number>();
    for (const b of bets) if (won(b) && realSports(b)) { const n = (by.get(sportOf(b)) ?? 0) + 1; by.set(sportOf(b), n); if (n === 15) return { by: b, have: 15, need: 15 }; }
    return { by: null, have: Math.max(0, ...by.values()), need: 15 };
  } },

  // ---- Legs
  { id: "legs-25", group: "Legs", icon: "🦵", title: "Leg day", how: "Hit 25 legs", test: wonLegs(25) },
  { id: "legs-100", group: "Legs", icon: "🦿", title: "Never skip leg day", how: "Hit 100 legs", test: wonLegs(100) },
  { id: "legs-250", group: "Legs", icon: "🐛", title: "Centipede", how: "Hit 250 legs", test: wonLegs(250) },
  { id: "td", group: "Legs", icon: "🙌", title: "Six points", how: "Hit an anytime TD leg", test: legs(1, /anytime TD/i) },
  { id: "td-10", group: "Legs", icon: "🏟️", title: "End zone regular", how: "Hit 10 anytime TD legs", test: legs(10, /anytime TD/i) },
  { id: "air-raid", group: "Legs", icon: "🛩️", title: "Air raid", how: "Hit a 300+ passing yards leg", test: legs(1, /passing yds/i, 300) },
  { id: "ground", group: "Legs", icon: "🚜", title: "Ground and pound", how: "Hit a 100+ rushing yards leg", test: legs(1, /rushing yds/i, 100) },
  { id: "deep-threat", group: "Legs", icon: "🎣", title: "Deep threat", how: "Hit a 100+ receiving yards leg", test: legs(1, /receiving yds/i, 100) },
  { id: "splash", group: "Legs", icon: "💦", title: "Splash", how: "Hit a 4+ threes leg", test: legs(1, /threes/i, 4) },
  { id: "thirty-piece", group: "Legs", icon: "💯", title: "Thirty-piece", how: "Hit a 30+ points leg", test: legs(1, /\bpoints\b/i, 30) },
  { id: "double-double", group: "Legs", icon: "✖️", title: "Double-double", how: "Hit a double-double leg", test: legs(1, /double.double/i) },
  { id: "goal", group: "Legs", icon: "🥅", title: "Goal!", how: "Hit a goalscorer leg", test: legs(1, /goals?\b|goalscorer|to score/i) },
  { id: "shots", group: "Legs", icon: "🏹", title: "Trigger happy", how: "Hit 10 shots legs (soccer or hockey)", test: legs(10, /\bshots\b/i) },

  // ---- Books and promos
  { id: "line-shopper", group: "Books and promos", icon: "🛒", title: "Line shopper", how: "Win at 2 different books", test: distinct(2, won, bookOfBet) },
  { id: "three-books", group: "Books and promos", icon: "🏬", title: "Mall rat", how: "Win at FanDuel, DraftKings and Novig", test: distinct(3, won, bookOfBet) },
  { id: "exchange", group: "Books and promos", icon: "🔁", title: "Exchange trader", how: "Win a bet at Novig", test: first((b) => won(b) && bookOfBet(b) === "Novig") },
  { id: "free-money", group: "Books and promos", icon: "🎁", title: "Free money", how: "Cash a bonus bet", test: first((b) => won(b) && isBonus(b)) },
  { id: "bonus-5", group: "Books and promos", icon: "🎀", title: "Bonus baron", how: "Cash 5 bonus bets", test: count(5, (b) => won(b) && isBonus(b)) },
  { id: "bonus-big", group: "Books and promos", icon: "🎉", title: "House money", how: "Turn a bonus bet into 10 units or more", test: first((b) => isBonus(b) && (profit(b) ?? 0) >= 10) },
  { id: "boosted", group: "Books and promos", icon: "⚡", title: "Boosted", how: "Win a profit-boosted bet", test: first((b) => won(b) && (num(b.boost) ?? 0) > 0) },
  { id: "boost-5", group: "Books and promos", icon: "🔋", title: "Supercharged", how: "Win 5 profit-boosted bets", test: count(5, (b) => won(b) && (num(b.boost) ?? 0) > 0) },
  { id: "protected", group: "Books and promos", icon: "🛡️", title: "Insured", how: "Win a Bet Protect+ bet", test: first((b) => won(b) && b.protect === true) },
  { id: "cash-out", group: "Books and promos", icon: "💸", title: "Take the money", how: "Cash out a bet for a profit", test: first((b) => num(b.cashout) !== null && (profit(b) ?? 0) > 0) },
  { id: "ladder", group: "Books and promos", icon: "🪜", title: "First rung", how: "Win a ladder step", test: first((b) => won(b) && !!b.ladder_id) },
  { id: "ladder-3", group: "Books and promos", icon: "🧗", title: "Climber", how: "Win 3 ladder steps", test: count(3, (b) => won(b) && !!b.ladder_id) },

  // ---- Sharp
  { id: "first-clv", group: "Sharp", icon: "📐", title: "Ahead of the market", how: "Beat the closing line once", test: first((b) => (personalClv(b) ?? 0) > 0) },
  { id: "sharp", group: "Sharp", icon: "🔪", title: "Sharp", how: "Beat the closing line on 10 bets", test: count(10, (b) => (personalClv(b) ?? 0) > 0) },
  { id: "closer", group: "Sharp", icon: "🗝️", title: "Closer", how: "Beat the closing line on 25 bets", test: count(25, (b) => (personalClv(b) ?? 0) > 0) },
  { id: "wiseguy", group: "Sharp", icon: "🕶️", title: "Wiseguy", how: "Beat the closing line on 50 bets", test: count(50, (b) => (personalClv(b) ?? 0) > 0) },
  { id: "steam", group: "Sharp", icon: "♨️", title: "Steam chaser", how: "Beat the close by 5% or more on one bet", test: first((b) => (personalClv(b) ?? 0) >= 0.05) },
  { id: "sharp-week", group: "Sharp", icon: "🧠", title: "Sharp week", how: "Beat the close on 5 bets in one Monday-to-Sunday week", test: (bets) => {
    const by = new Map<string, number>();
    for (const b of bets) if ((personalClv(b) ?? 0) > 0) { const n = (by.get(weekOf(b)) ?? 0) + 1; by.set(weekOf(b), n); if (n === 5) return { by: b }; }
    return { by: null };
  } },

  // ---- Days and runs
  { id: "hat-trick", group: "Days and runs", icon: "🎩", title: "Hat trick", how: "Win 3 bets in a row", test: run(3) },
  { id: "on-fire", group: "Days and runs", icon: "🔥", title: "On fire", how: "Win 5 bets in a row", test: run(5) },
  { id: "unstoppable", group: "Days and runs", icon: "🌋", title: "Unstoppable", how: "Win 10 bets in a row", test: run(10) },
  { id: "bounce-back", group: "Days and runs", icon: "🪃", title: "Bounce back", how: "Win right after losing 3 in a row", test: (bets) => {
    let losses = 0;
    for (const b of bets) { if (lost(b)) losses++; else if (won(b)) { if (losses >= 3) return { by: b }; losses = 0; } }
    return { by: null };
  } },
  { id: "perfect-day", group: "Days and runs", icon: "✨", title: "Perfect day", how: "Win every bet on a day with 3 or more", test: day((s) => s.n >= 3 && s.won === s.n) },
  { id: "big-day", group: "Days and runs", icon: "☀️", title: "Big day", how: "Finish a day up 5 units", test: day((s) => s.units >= 5) },
  { id: "monster-day", group: "Days and runs", icon: "👹", title: "Monster day", how: "Finish a day up 10 units", test: day((s) => s.units >= 10) },
  { id: "green-week", group: "Days and runs", icon: "📈", title: "Green week", how: "Finish a Monday-to-Sunday week up, with 5+ bets settled", test: span(weekOf, weekEnd, (s) => s.n >= 5 && s.units > 0) },
  { id: "green-month", group: "Days and runs", icon: "🗓️", title: "Green month", how: "Finish a calendar month up, with 10+ bets settled", test: span((b) => dayOf(b).slice(0, 7), monthEnd, (s) => s.n >= 10 && s.units > 0) },
  { id: "win-days-3", group: "Days and runs", icon: "📆", title: "Three-day run", how: "Win a bet 3 days in a row", test: winDays(3) },
  { id: "win-days-7", group: "Days and runs", icon: "🗞️", title: "Daily news", how: "Win a bet 7 days in a row", test: winDays(7) },
  { id: "weekend", group: "Days and runs", icon: "🎊", title: "Weekend warrior", how: "Win on a Saturday and the Sunday after it", test: (bets) => {
    const days = new Set(bets.filter(won).map(dayOf));
    for (const b of bets.filter(won)) {
      const d = new Date(`${dayOf(b)}T12:00:00Z`);
      if (d.getUTCDay() !== 0) continue;
      d.setUTCDate(d.getUTCDate() - 1);
      if (days.has(d.toISOString().slice(0, 10))) return { by: b };
    }
    return { by: null };
  } },
  { id: "early-bird", group: "Days and runs", icon: "🐦", title: "Early bird", how: "Win a bet on a game that starts before noon ET", test: first((b) => won(b) && !!startOf(b) && etHour(startOf(b)!) < 12) },
  { id: "night-owl", group: "Days and runs", icon: "🦉", title: "Night owl", how: "Win a bet on a game that starts at 10 PM ET or later", test: first((b) => won(b) && !!startOf(b) && etHour(startOf(b)!) >= 22) },
];

/** Every badge, earned first (newest first), then the locked ones in list order. */
export function achievements(bets: MyBet[]): Badge[] {
  const done = chrono(bets);
  const all = DEFS.map((d): Badge => {
    const r = d.test(done);
    return { id: d.id, icon: d.icon, title: d.title, how: d.how, group: d.group, earned: r.by ? dayOf(r.by) : null, by: r.by,
             ...(r.need && !r.by ? { progress: { have: r.have ?? 0, need: r.need } } : {}) };
  });
  const got = all.filter((b) => b.earned).sort((a, b) => b.earned!.localeCompare(a.earned!));
  return [...got, ...all.filter((b) => !b.earned)];
}

/** The locked badges closest to done (by progress), for "Next up". */
export function nextUp(badges: Badge[], n = 6): Badge[] {
  return badges.filter((b) => !b.earned && b.progress && b.progress.have > 0)
    .sort((a, b) => b.progress!.have / b.progress!.need - a.progress!.have / a.progress!.need || a.progress!.need - b.progress!.need)
    .slice(0, n);
}
