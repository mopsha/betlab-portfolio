// The calendar's month grid (Nov 4). Pure, so the tests run it; dates are plain "YYYY-MM-DD" Eastern days, never instants, so a
// clock change can't move a cell. Port: ios/BetLab/Games/CalendarView.swift, one fixture tests/fixtures/calendar.json.
const asDate = (day: string) => new Date(`${day}T12:00:00Z`);
const str = (d: Date) => d.toISOString().slice(0, 10);

/** Every day of the weeks (Sunday first) that hold a day of this month ("2026-11"). */
export function monthGrid(month: string): string[] {
  const start = asDate(`${month}-01`);
  const first = new Date(start);
  first.setUTCDate(1 - start.getUTCDay());
  const end = asDate(`${shiftMonth(month, 1)}-01`);
  end.setUTCDate(0);                                   // the month's last day
  end.setUTCDate(end.getUTCDate() + (6 - end.getUTCDay()));
  const out: string[] = [];
  for (const d = first; d <= end; d.setUTCDate(d.getUTCDate() + 1)) out.push(str(d));
  return out;
}

export function shiftMonth(month: string, n: number): string {
  const [y, m] = month.split("-").map(Number);
  const i = y * 12 + (m - 1) + n;
  return `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`;
}

export const monthName = (month: string) =>
  asDate(`${month}-15`).toLocaleDateString("en-US", { timeZone: "UTC", month: "long", year: "numeric" });
