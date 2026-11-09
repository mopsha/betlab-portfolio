// My bets > Stats (Mike's #40, Oct 24: "personal stats"): where your bets win and lose, by sport, bet type, price,
// cash vs bonus vs boost, book and weekday, plus units over time, streaks and the best and worst bets. Pure; the
// groupings feed record() (lib/bets.ts), so units, ROI and CLV mean exactly what they do on the Record tab.
import { isBonus, isSettled, profit, record, recordOutcome, dayOf, bookOfBet, type Line } from "./bets";
import type { MyBet } from "./data";
import { num, sportName } from "./format";

const SOCCER = new Set(["epl", "la_liga", "serie_a", "bundesliga", "ligue_1", "mls", "ucl", "uel", "uecl", "soccer"]);
const sportKey = (k?: string | null) => { const s = String(k ?? "").toLowerCase(); return SOCCER.has(s) ? "soccer" : s; };

/** A game ref's sport: "ncaaf:401856731", "epl|Home|Away|kickoff", "ufc:<event>:<fight>", "2026_07_NE_CHI". */
export function refSportKey(ref?: string | null): string | null {
  const s = String(ref ?? "");
  if (s.includes("|")) return sportKey(s.split("|")[0]) || null;
  if (/^\d{4}_\d{2}_/.test(s)) return "nfl";
  const head = s.split(":")[0];
  return s.includes(":") && head ? head : null;
}

// A custom bet entered without game ids (most before Oct 24): its sport from what it says. A title ("NBA late games"),
// then prop wording (college player props are never bet in New York, so yardage props are the NFL's), then NBA nicknames.
const TITLE: [RegExp, string][] = [[/\bNBA\b/, "nba"], [/\bNHL\b/, "nhl"], [/\bNFL\b/, "nfl"], [/college football/i, "ncaaf"],
  [/college basketball/i, "ncaab"], [/\bUFC\b/, "ufc"], [/soccer|SGP\+ .*matches/i, "soccer"]];
const PROP: [RegExp, string][] = [[/passing yds|receiving yds|rushing yds|receptions|anytime TD|first TD/i, "nfl"],
  [/shots on goal|saves\b/i, "nhl"], [/shots on target|to score or assist/i, "soccer"], [/rebounds|threes|\d+\+ points|over [\d.]+ (points|assists)/i, "nba"]];
const NBA = /\b(Celtics|Knicks|Nets|76ers|Raptors|Bulls|Cavaliers|Pistons|Pacers|Bucks|Hawks|Hornets|Heat|Magic|Wizards|Nuggets|Timberwolves|Thunder|Trail Blazers|Jazz|Warriors|Clippers|Lakers|Suns|Kings|Mavericks|Rockets|Grizzlies|Pelicans|Spurs)\b/;
export function guessSport(b: Pick<MyBet, "matchup" | "legs" | "label">): string | null {
  const text = [b.matchup, ...(b.legs ?? [])].join(" | ");
  for (const [re, k] of [...TITLE, ...PROP]) if (re.test(text)) return k;
  return NBA.test(text) ? "nba" : null;
}

/** The sport a bet counts under: a single's league, a ticket's sport, a custom bet's games (else what it says);
 * "Multi-sport" when its legs span more than one. */
export function sportOf(b: MyBet): string {
  if (b.kind === "pick" || b.kind === "lean") return sportName(sportKey(b.league));
  const fromGames = [...new Set((b.games ?? []).map((g) => refSportKey(g.game_ref)).filter(Boolean) as string[])];
  if (fromGames.length > 1) return "Multi-sport";
  const k = fromGames[0] ?? (b.sport && b.sport !== "mixed" ? sportKey(b.sport) : b.sport === "mixed" ? "mixed" : guessSport(b));
  return k === "mixed" ? "Multi-sport" : k ? sportName(k) : "Other";
}

export const legsOf = (b: MyBet) => Math.max(b.legs?.length ?? 0, (b.games ?? []).reduce((s, g) => s + (g.legs?.length ?? 0), 0), 1);
export const typeOf = (b: MyBet) => (legsOf(b) === 1 ? "Single" : legsOf(b) <= 4 ? "Parlay, 2-4 legs" : "Parlay, 5+ legs");

/** Price bands, shortest first. */
export const BANDS = ["Favorite (-111 or shorter)", "Near even (-110 to +150)", "Underdog (+151 to +400)", "Long shot (+401 to +1000)", "Lottery (+1001 or longer)"];
export function bandOf(b: MyBet): string {
  const p = num(b.price);
  if (p === null) return "No price";
  return p <= -111 ? BANDS[0] : p <= 150 ? BANDS[1] : p <= 400 ? BANDS[2] : p <= 1000 ? BANDS[3] : BANDS[4];
}
export const moneyOf = (b: MyBet) => (isBonus(b) ? "Bonus bets" : (num(b.boost) ?? 0) > 0 ? "Boosted cash" : "Plain cash");
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
export const weekdayOf = (b: MyBet) => WEEKDAYS[new Date(`${dayOf(b)}T12:00:00Z`).getUTCDay()];

/** Settled bets in the order they settled (game day, then when placed). */
export const chrono = (bets: MyBet[]) => bets.filter(isSettled)
  .sort((a, b) => dayOf(a).localeCompare(dayOf(b)) || a.placed_at.localeCompare(b.placed_at));

/** Units after each day with a settled bet: [{day, units (cumulative), net (that day)}]. */
export function timeline(bets: MyBet[]): { day: string; units: number; net: number }[] {
  const byDay = new Map<string, number>();
  for (const b of chrono(bets)) byDay.set(dayOf(b), (byDay.get(dayOf(b)) ?? 0) + (profit(b) ?? 0));
  let run = 0;
  return [...byDay.entries()].map(([day, net]) => ({ day, net, units: (run += net) }));
}

/** The current run of wins or losses and the longest winning run, counted as the record counts them (recordOutcome: a
 *  push is a loss, a cash-out counts as its bet settled; voids neither extend nor break one). */
export function streaks(bets: MyBet[]): { current: { kind: "won" | "lost" | null; n: number }; bestWin: number } {
  let kind: "won" | "lost" | null = null, n = 0, best = 0, run = 0;
  for (const b of chrono(bets)) {
    const s = recordOutcome(b);
    if (s !== "won" && s !== "lost") continue;
    n = s === kind ? n + 1 : 1; kind = s;
    run = s === "won" ? run + 1 : 0; best = Math.max(best, run);
  }
  return { current: { kind, n }, bestWin: best };
}

/** The biggest win and the worst loss in units (a bonus loss costs nothing, so it's never the worst). */
export function extremes(bets: MyBet[]): { best: MyBet | null; worst: MyBet | null } {
  const done = chrono(bets).filter((b) => profit(b) !== null);
  const best = done.reduce<MyBet | null>((m, b) => (profit(b)! > 0 && (!m || profit(b)! > profit(m)!) ? b : m), null);
  const worst = done.reduce<MyBet | null>((m, b) => (profit(b)! < 0 && (!m || profit(b)! < profit(m)!) ? b : m), null);
  return { best, worst };
}

export type Stats = {
  total: Line; bySport: Line[]; byType: Line[]; byBand: Line[]; byMoney: Line[]; byBook: Line[]; byWeekday: Line[];
  timeline: ReturnType<typeof timeline>; streaks: ReturnType<typeof streaks>; extremes: ReturnType<typeof extremes>;
};

export function stats(bets: MyBet[]): Stats {
  const order = (keys: string[]) => (lines: Line[]) => [...lines].sort((a, b) => keys.indexOf(a.group) - keys.indexOf(b.group));
  return {
    total: record(bets).total,
    bySport: record(bets, sportOf).lines,
    byType: order(["Single", "Parlay, 2-4 legs", "Parlay, 5+ legs"])(record(bets, typeOf).lines),
    byBand: order([...BANDS, "No price"])(record(bets, bandOf).lines),
    byMoney: order(["Plain cash", "Boosted cash", "Bonus bets"])(record(bets, moneyOf).lines),
    byBook: record(bets, bookOfBet).lines,
    byWeekday: order(WEEKDAYS)(record(bets, weekdayOf).lines),
    timeline: timeline(bets), streaks: streaks(bets), extremes: extremes(bets),
  };
}
