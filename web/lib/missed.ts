// Missed bets (Mike's #41, Nov 2): the picks you skipped and how they did, at 1 unit each, beside the picks you took on the
// same terms. A pick counts from the account's real-money start. Shared cases: tests/fixtures/missed.json (iPhone: Missed.swift).
export type MissedPick = { pick_id: string; league?: string | null; matchup?: string | null; label?: string | null; price?: number | null;
  commence_time: string | null; status: string | null; profit_flat: number | null; clv: number | null; clv_raw: number | null };

const SETTLED = new Set(["won", "lost", "push"]);
const n = (v: unknown) => { const x = Number(v); return v === null || v === undefined || !Number.isFinite(x) ? null : x; };
const sum = (ps: MissedPick[]) => ps.reduce((t, p) => t + (n(p.profit_flat) ?? 0), 0);

export function missedBets<T extends MissedPick>(picks: T[], taken: Iterable<string>, since: string | Date) {
  const mine = new Set(taken), from = new Date(since).getTime();
  const settled = picks.filter((p) => SETTLED.has(String(p.status)) && p.commence_time && new Date(p.commence_time).getTime() >= from);
  const skipped = settled.filter((p) => !mine.has(p.pick_id))
    .sort((a, b) => String(b.commence_time).localeCompare(String(a.commence_time)));
  const took = settled.filter((p) => mine.has(p.pick_id));
  const clvs = skipped.map((p) => n(p.clv_raw) ?? n(p.clv)).filter((x): x is number => x !== null);
  const count = (s: string) => skipped.filter((p) => p.status === s).length;
  return { picks: skipped, won: count("won"), lost: count("lost"), push: count("push"), units: sum(skipped),
           clv: clvs.length ? clvs.reduce((a, b) => a + b, 0) / clvs.length : null, tookN: took.length, tookUnits: sum(took) };
}
