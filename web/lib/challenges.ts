// Novig challenges (Oct 28; worker src/betlab/challenges.py, table `challenges`, migration 0027).
export type ChallengeBet = {
  label: string; legs: { label: string; game: string; start: string; price: number; p: number }[];
  price: number; dec: number; p: number; ev: number; matchup: string; commence_time: string; stake: number;
  link: string; stake_max?: number | null;
};
export type Challenge = {
  challenge_id: string; day: string; text: string; points: number | null; status: "open" | "ready" | "done" | "skipped";
  pick: ChallengeBet | null; best: ChallengeBet | null; picked_at: string | null; notice: string | null;
  rules: { kind?: string; min_dec?: number | null } | null;
};

/** What a challenge's card says about where it stands. */
export function challengeState(c: Challenge): { tag: string; tone: "good" | "mid" | "faint"; bet: ChallengeBet | null; note: string | null } {
  if (c.status === "done") return { tag: "Placed", tone: "good", bet: c.pick, note: null };
  if (c.status === "skipped") return { tag: "Skipped", tone: "faint", bet: null, note: null };
  if (c.status === "ready" && c.pick) return { tag: "Ready", tone: "good", bet: c.pick, note: null };
  const missed = c.notice?.startsWith("missed: ") ? `${c.notice.slice(8)} started before it was placed; finding another.` : null;
  return { tag: c.best ? "Watching" : "Waiting", tone: "mid", bet: c.best,
           note: missed ?? (c.notice && !c.notice.startsWith("missed") ? c.notice
             : c.best ? "The best so far. You'll get an alert when it's ripe (its game's news is in and the price is right)."
             : "Looking for a Novig price. You'll get an alert when a bet is ripe.") };
}

// ------------------------------------------------------------------ history (Oct 28: "points and how they did")
/** The bet a challenge's pick became: a straight's one Novig outcome is the Novig sync's `novig-<outcome>` bet. */
export const pickOutcome = (c: Pick<Challenge, "pick">): string | null => {
  const m = /novig\.com\/events\/([^/?#]+)/.exec(c.pick?.link ?? "");
  return m && !m[1].includes(",") ? m[1] : null;
};
export type HistBet = { sgp_id: string | null; status: string | null; profit: number | null };
export type HistDay = { day: string; done: number; total: number; points: number; bonus: boolean;
  items: { text: string; status: Challenge["status"]; label: string | null; result: string | null; profit: number | null }[] };
export type History = { days: HistDay[]; month: { key: string; points: number; done: number; total: number; sweeps: number;
  settled: number; won: number; units: number } };

/** Points (each placed challenge's points, 100 more when a day's 3+ are all placed) and how each placed bet did, by day
 *  (newest first) and for the month of `today`. `bets`: the user's bets with their status and profit in units. */
export function challengeHistory(rows: Challenge[], bets: HistBet[], today: string): History {
  const bySgp = new Map(bets.filter((b) => b.sgp_id).map((b) => [b.sgp_id!, b]));
  const byDay = new Map<string, Challenge[]>();
  for (const c of rows) byDay.set(c.day, [...(byDay.get(c.day) ?? []), c]);
  const days: HistDay[] = [...byDay.entries()].sort((a, b) => b[0].localeCompare(a[0])).map(([day, cs]) => {
    const done = cs.filter((c) => c.status === "done").length;
    const bonus = cs.length >= 3 && done === cs.length;
    return { day, done, total: cs.length, bonus,
      points: cs.filter((c) => c.status === "done").reduce((s, c) => s + (c.points ?? 50), 0) + (bonus ? 100 : 0),
      items: cs.map((c) => {
        const o = c.status === "done" ? pickOutcome(c) : null;
        const b = o ? bySgp.get(`novig-${o}`) : undefined;
        const st = b?.status ?? null;
        return { text: c.text, status: c.status, label: c.pick?.label ?? null,
                 result: st && st !== "open" ? st : c.status === "done" ? (b ? "open" : null) : null, profit: b?.profit ?? null };
      }) };
  });
  const key = today.slice(0, 7);
  const inMonth = days.filter((d) => d.day.startsWith(key));
  const placed = inMonth.flatMap((d) => d.items).filter((i) => i.result && i.result !== "open");
  return { days, month: { key, points: inMonth.reduce((s, d) => s + d.points, 0), done: inMonth.reduce((s, d) => s + d.done, 0),
    total: inMonth.reduce((s, d) => s + d.total, 0), sweeps: inMonth.filter((d) => d.bonus).length, settled: placed.length,
    won: placed.filter((i) => i.result === "won").length, units: placed.reduce((s, i) => s + (i.profit ?? 0), 0) } };
}
