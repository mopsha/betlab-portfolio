// View helpers for the Promos wallet, the promo finder and the Ladder in the overhaul look (Nov 5, docs/OVERHAUL.md).
// Pure, and views only: nothing here decides what a token is worth or what a step is (lib/promos.ts, promo-finder.ts
// and ladder.ts do, held to the shared fixtures); this file only words and draws what they return.
import teams from "./teams.json";
import { fmtAm, ET } from "./format";
import { marketName, promoSports, SPORT_CHOICES, type PromoRow } from "./promos";

const num = (v: unknown) => (v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? null : Number(v));
const dollars = (n: number) => `$${Number.isInteger(n) ? n : n.toFixed(2)}`;

/** A token's value as the big number on its card: "$10", "50%". */
export function tokenValueText(p: Pick<PromoRow, "kind" | "amount_dollars" | "pct">): string {
  if (p.kind === "bonus") { const a = num(p.amount_dollars); return a ? dollars(a) : "$?"; }
  const k = num(p.pct);
  return k ? `${k}%` : "?%";
}
export const kindName = (k: PromoRow["kind"] | undefined) => (k === "boost" ? "Profit boost" : "Bonus bet");

/** When a token ends, as a countdown: `today` (the Eastern day) is the warning case. Null with no end date. */
export function endsOf(p: Pick<PromoRow, "expires_at">, now: Date): { text: string; left: string | null; today: boolean; over: boolean } | null {
  if (!p.expires_at) return null;
  const t = new Date(p.expires_at), ms = t.getTime() - now.getTime();
  const day = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: ET });
  const clock = t.toLocaleTimeString("en-US", { timeZone: ET, hour: "numeric", minute: "2-digit" });
  if (ms <= 0) return { text: `ended ${t.toLocaleDateString("en-US", { timeZone: ET, month: "short", day: "numeric" })}`, left: null, today: false, over: true };
  const today = day(t) === day(now);
  const mins = Math.floor(ms / 60_000), h = Math.floor(mins / 60), m = mins % 60;
  const left = ms < 24 * 3600_000 ? (h ? `${h} h ${m} m left` : `${Math.max(1, m)} m left`) : null;
  if (today) return { text: `ends today ${clock}`, left, today, over: false };
  if (ms < 6 * 86400_000) return { text: `ends ${t.toLocaleDateString("en-US", { timeZone: ET, weekday: "short" })} ${clock}`, left, today, over: false };
  return { text: `ends ${t.toLocaleDateString("en-US", { timeZone: ET, month: "short", day: "numeric" })}`, left: null, today, over: false };
}

export type TokenChip = { key: string; text: string; league?: string; team?: TeamMark };
/** A token's limits as small chips: the most it takes, the boost's cap, legs, odds, its sports and its teams. */
export function tokenChips(p: PromoRow): TokenChip[] {
  const out: TokenChip[] = [];
  const amt = num(p.amount_dollars), cap = num(p.max_extra_dollars), legs = num(p.min_legs), lo = num(p.min_odds), hi = num(p.max_odds);
  if (p.kind === "boost" && amt) out.push({ key: "max", text: `up to ${dollars(amt)}` });
  if (cap) out.push({ key: "cap", text: `max ${dollars(cap)} extra` });
  if (legs && legs > 1) out.push({ key: "legs", text: `${legs}+ legs` });
  if (lo !== null && hi !== null) out.push({ key: "odds", text: `${fmtAm(lo)} to ${fmtAm(hi)}` });
  else if (lo !== null) out.push({ key: "odds", text: `${fmtAm(lo)} or longer` });
  else if (hi !== null) out.push({ key: "odds", text: `${fmtAm(hi)} or shorter` });
  for (const s of promoSports(p) ?? []) out.push({ key: `s-${s}`, text: `${SPORT_CHOICES.find(([k]) => k === s)?.[1] ?? s.toUpperCase()} only`, league: s });
  if (p.market) out.push({ key: "market", text: marketName(p.market) });
  for (const g of p.games ?? []) out.push({ key: `g-${g.event_id}`, text: g.matchup });
  for (const t of p.teams ?? []) out.push({ key: `t-${t}`, text: t, team: teamMark(t) });
  return out;
}

export type TeamMark = { name: string; abbr: string | null; src: string | null };
type TeamRow = { name: string; abbr: string[] };
const LEAGUES = teams as unknown as Record<string, TeamRow[]>;
// ESPN's logo files use its own short codes for a few teams
const ESPN_CODE: Record<string, string> = { "nhl:tbl": "tb", "nhl:lak": "la", "nhl:sjs": "sj", "nba:uta": "utah", "nba:nop": "no" };
const words = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);

/** A team a token names ("Knicks"), as a picture: the NFL, NBA or NHL team whose name holds all its words, when exactly
 *  one does. Anything else keeps its name and shows its letters. */
export function teamMark(name: string): TeamMark {
  const w = words(name);
  const hits: { league: string; t: TeamRow }[] = [];
  if (w.length) for (const [league, list] of Object.entries(LEAGUES)) for (const t of list) {
    const tw = words(t.name);
    if (w.every((x) => tw.includes(x)) || t.abbr.some((a) => a.toLowerCase() === name.trim().toLowerCase())) hits.push({ league, t });
  }
  if (hits.length !== 1) return { name, abbr: null, src: null };
  const { league, t } = hits[0], code = (t.abbr[0] ?? "").toLowerCase();
  return { name: t.name, abbr: t.abbr[0] ?? null, src: code ? `https://a.espncdn.com/i/teamlogos/${league}/500/${ESPN_CODE[`${league}:${code}`] ?? code}.png` : null };
}

/** A matchup's two sides, away first: "Away @ Home" or "A vs B". */
export const sidesOf = (matchup: string | null | undefined): string[] => String(matchup ?? "").split(/\s+@\s+|\s+vs\.?\s+/i).map((s) => s.trim()).filter(Boolean);

/** The ladder's rungs, one per step: those won, the one being climbed, and the even-money wins still to come.
 *  `ahead`: lib/ladder.ts stepsToTarget(stack, target, 100), the current step included. At most `max` drawn. */
export function rungs(won: number, ahead: number, ended: "climbed" | "busted" | "stopped" | null, max = 16): ("won" | "now" | "lost" | "todo")[] {
  const out: ("won" | "now" | "lost" | "todo")[] = Array.from({ length: won }, () => "won" as const);
  if (ended === "climbed") return out.slice(-max);
  if (ended === "busted") out.push("lost");
  else if (ahead > 0) out.push(ended ? "todo" : "now");
  for (let i = 1; i < ahead; i++) out.push("todo");
  return out.length > max ? [...out.slice(0, max - 1), "todo"] : out;
}
