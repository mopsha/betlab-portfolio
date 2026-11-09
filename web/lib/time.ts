import { ET } from "./format";

/** The Eastern date of an instant, "2026-10-01" ("today" means the ET date, as everywhere in BetLab). */
export function etDay(d: Date | string): string {
  return new Date(d).toLocaleDateString("en-CA", { timeZone: ET });
}

/** UTC offset of Eastern time at an instant, in minutes (−240 in EDT, −300 in EST). */
function etOffset(at: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: ET, timeZoneName: "shortOffset" }).formatToParts(at);
  const m = /GMT([+-]\d+)(?::(\d+))?/.exec(parts.find((p) => p.type === "timeZoneName")?.value ?? "");
  return m ? Number(m[1]) * 60 + Math.sign(Number(m[1])) * Number(m[2] ?? 0) : -300;
}

/** The instant an ET date starts. The offset is read at midnight itself, not noon: on a clock-change day (Nov 1, 2026:
 * EDT at midnight, EST by noon) noon's offset put the day's start an hour off. */
export function etStart(day: string): Date {
  const naive = Date.parse(`${day}T00:00:00Z`);
  const guess = naive - etOffset(new Date(`${day}T12:00:00Z`)) * 60_000;
  return new Date(naive - etOffset(new Date(guess)) * 60_000);
}

/** An Eastern wall time, "2026-10-24T13:06:00", as an instant. The offset is read at the instant itself, and nothing
 * here depends on the browser's own zone (the old way misread 6-7 AM on a clock-change day in New York). */
export function etInstant(local: string): Date {
  const naive = Date.parse(`${local}Z`);
  const guess = naive - etOffset(new Date(naive)) * 60_000;
  return new Date(naive - etOffset(new Date(guess)) * 60_000);
}

export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export type DayKey = "today" | "tomorrow" | "week";

/** [from, to) for Home's day switcher. Today starts now-ish: games that started in the last
 * 4 hours stay listed while they're live. */
export function window(day: DayKey, now = new Date()): { from: Date; to: Date } {
  const today = etDay(now);
  if (day === "tomorrow") return { from: etStart(addDays(today, 1)), to: etStart(addDays(today, 2)) };
  const from = new Date(Math.max(etStart(today).getTime(), now.getTime() - 4 * 3600_000));
  return { from, to: etStart(addDays(today, day === "week" ? 7 : 1)) };
}
