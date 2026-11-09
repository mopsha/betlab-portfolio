// FanDuel's College Football Pick'em (Nov 7; worker src/betlab/pickem.py, table `pickem`, migration 0044). The lines
// freeze Wednesday morning and the entry locks Saturday at noon ET; the worker prices each frozen line against the sharp
// market and names our side. Same rules in the worker and the iPhone app: tests/fixtures/pickem.json.
export type Side = "home" | "away";
export type PickemRow = {
  pick_id: string; week: string; n: number; away: string; home: string; home_line: number;
  away_name: string | null; home_name: string | null; away_logo: string | null; home_logo: string | null;
  pick: Side | null; ours: Side | null; p_home: number | null; fair_line: number | null; priced_at: string | null;
  event_id: string | null; start: string | null; home_pts: number | null; away_pts: number | null;
  result: Side | "push" | null; notice: string | null;
};
export type PickemWeek = { week: string; partner_best: number | null; reward: string | null };

export const MIN_FLIP = 0.52;

/** The lock day of the entry an instant falls in: the coming Saturday in Eastern time (today, on a Saturday). */
export function weekOf(etDay: string): string {
  const d = new Date(`${etDay}T12:00:00Z`);
  const ahead = (6 - d.getUTCDay() + 7) % 7;
  d.setUTCDate(d.getUTCDate() + ahead);
  return d.toISOString().slice(0, 10);
}

/** The week's tally: how many you got right, how many BetLab's side would have. A push counts for both. */
export function score(rows: PickemRow[]) {
  const done = rows.filter((r) => r.result === "home" || r.result === "away" || r.result === "push");
  return {
    games: rows.length, picked: rows.filter((r) => r.pick).length, graded: done.length,
    yours: done.filter((r) => r.pick && (r.result === r.pick || r.result === "push")).length,
    ours: done.filter((r) => r.ours && (r.result === r.ours || r.result === "push")).length,
  };
}

/** The picks against our side with our side at 52% or better, and the games not picked yet. */
export function flips(rows: PickemRow[]): { toFlip: PickemRow[]; unpicked: PickemRow[] } {
  const toFlip: PickemRow[] = [], unpicked: PickemRow[] = [];
  for (const r of rows) {
    if (!r.pick) unpicked.push(r);
    else if (r.ours && r.p_home != null && r.pick !== r.ours && Math.max(Number(r.p_home), 1 - Number(r.p_home)) >= MIN_FLIP) toFlip.push(r);
  }
  return { toFlip, unpicked };
}

/** "Iowa +2.5": the side's team as FanDuel names it and its frozen line. */
export function sideLabel(r: Pick<PickemRow, "home" | "away" | "home_line">, side: Side): string {
  const team = side === "home" ? r.home : r.away;
  const line = side === "home" ? Number(r.home_line) : -Number(r.home_line);
  return `${team} ${line > 0 ? "+" : ""}${line}`;
}

/** The chance a side covers the frozen line, from the row's home chance. */
export const chance = (r: Pick<PickemRow, "p_home">, side: Side): number | null =>
  r.p_home == null ? null : side === "home" ? Number(r.p_home) : 1 - Number(r.p_home);
