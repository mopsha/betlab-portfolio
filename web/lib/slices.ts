// Kickoff slices (Oct 30): the worker's sgp_plus.SLICES and slice_of, for the promo finder's "a slice" scope (Mike:
// "I can't choose bet for a slice"). The same slices the fun tickets lock by; one fixture for the three ports,
// tests/fixtures/slices.json (iPhone Slices in PromoFinder.swift). Prime-time matches (fun.<sport>.primetime) stay in
// their hour's slice here: the finder only groups games.

const ET = "America/New_York";
const LATE_NIGHT_HOUR = 4;          // a 12:30 AM kickoff belongs to the night before

/** sport: [name, ends before this ET hour, what its title calls it] (sgp_plus.SLICES). */
export const SLICES: Record<string, [string, number, string][]> = {
  nfl: [["morning", 12, "morning"], ["early", 15, "early"], ["late", 19, "late"], ["night", 24, "night"]],
  ncaaf: [["noon", 15, "noon"], ["afternoon", 19, "afternoon"], ["night", 24, "night"]],
  soccer: [["early", 8.75, "early"], ["nine", 9.75, "9 AM"], ["ten", 11, "10 AM"], ["eleven", 12, "11 AM"],
    ["noon", 12.67, "noon"], ["lunch", 14.25, "12:45"], ["three", 17, "3 PM"], ["five", 18.75, "5:30 PM"],
    ["mls", 20.25, "7:30 PM"], ["evening", 21.25, "8:30 PM"], ["night", 24, "late"]],
  nhl: [["afternoon", 17, "afternoon"], ["dusk", 18.75, "5 PM"], ["evening", 21, "evening"], ["late", 24, "late"]],
  ncaab: [["morning", 12, "morning"], ["afternoon", 17, "afternoon"], ["evening", 21, "evening"], ["late", 24, "late"]],
  nba: [["afternoon", 17, "afternoon"], ["dusk", 18.75, "5 PM"], ["early", 21, "early"], ["late", 24, "late"]],
  ufc: [["morning", 11.5, "morning"], ["midday", 13.5, "midday"], ["afternoon", 17, "afternoon"],
    ["evening", 19.5, "evening"], ["prelims", 21.5, "prelims"], ["main", 24, "main card"]],
};
export const SPORT = { nfl: "NFL", ncaaf: "College football", soccer: "Soccer", nhl: "NHL", ncaab: "College basketball", nba: "NBA", ufc: "UFC" } as Record<string, string>;

/** [ET day, slice name] for a kickoff (sgp_plus.slice_of); null for a sport with no slices. */
export function sliceOf(sport: string, commence: string): [string, string] | null {
  const table = SLICES[sport];
  if (!table) return null;
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: ET, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(commence)).map((x) => [x.type, x.value]));
  const day = `${p.year}-${p.month}-${p.day}`;
  if (Number(p.hour) < LATE_NIGHT_HOUR)
    return [new Date(Date.parse(`${day}T12:00:00Z`) - 86_400_000).toISOString().slice(0, 10), table[table.length - 1][0]];
  const h = Number(p.hour) + Number(p.minute) / 60;
  return [day, (table.find(([, end]) => h < end) ?? table[table.length - 1])[0]];
}

/** A slice's word in its title: the table's, but the "dusk" slice says its first start, "5:10 PM" (sgp_plus.slice_names). */
export function sliceWord(sport: string, name: string, first: string | number): string {
  if (name === "dusk") {
    const p = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: ET, hour: "numeric", minute: "2-digit", hour12: true })
      .formatToParts(new Date(first)).map((x) => [x.type, x.value]));
    return `${p.hour}${p.minute === "00" ? "" : `:${p.minute}`} ${String(p.dayPeriod).toUpperCase()}`;
  }
  return SLICES[sport]?.find(([n]) => n === name)?.[2] ?? name;
}

export type Slice = { key: string; sport: string; day: string; name: string; title: string; first: string; events: string[] };

/** The games grouped into slices, soonest first: "NFL early · Sun" with its games. */
export function slicesOf(games: { event_id: string; sport: string; commence_time: string }[]): Slice[] {
  const by = new Map<string, Slice>();
  for (const g of [...games].sort((a, b) => a.commence_time.localeCompare(b.commence_time))) {
    const s = sliceOf(g.sport, g.commence_time);
    if (!s) continue;
    const key = `${s[0]}-${g.sport}-${s[1]}`;
    const cur = by.get(key);
    if (cur) { cur.events.push(g.event_id); continue; }
    const word = sliceWord(g.sport, s[1], g.commence_time);
    const dow = new Date(`${s[0]}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
    by.set(key, { key, sport: g.sport, day: s[0], name: s[1], title: `${SPORT[g.sport] ?? g.sport} ${word} · ${dow}`,
                  first: g.commence_time, events: [g.event_id] });
  }
  return [...by.values()].sort((a, b) => a.first.localeCompare(b.first));
}
