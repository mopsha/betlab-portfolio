// How the Build screen lays a game out (the reorganization, Nov 5): the main lines as one card, a few props worth a
// look, which book pays a slip best, and which wallet tokens fit it. View helpers only: every price, chance and grade
// still comes from lib/builder.ts, and nothing here changes what a slip is worth.
import { isBanned, type Ban } from "./bans";
import { promoFits, type BuildBook, type PackLeg } from "./builder";
import { MINUS, toDec } from "./format";
import { asPromo, promoSports, teamFits, type PromoRow } from "./promos";

export const BUILD_BOOKS: BuildBook[] = ["FanDuel", "DraftKings", "Novig"];

/** A stat tab's title: the combined stats' short keys in words (the board's own titles leave them as "Pr", "Ra"). */
const COMBOS: Record<string, string> = { pr: "Pts + reb", pa: "Pts + ast", ra: "Reb + ast" };
export const tabTitle = (key: string, title: string) => COMBOS[key] ?? title;

/** A matchup's two sides, away first ("Away @ Home"; a fight's "A vs B"). */
export const sidesOf = (matchup: string): string[] => matchup.split(/\s+@\s+|\s+vs\.?\s+/i).map((s) => s.trim()).filter(Boolean);

/** Which side a team leg is on: 0 away, 1 home, -1 neither (a draw, a total). Packs name a team in full, by its short
 *  name or by its code, so the leg's own label, the side's name and the logos' abbreviations are all tried. */
export function sideOf(l: Pick<PackLeg, "label" | "team">, names: string[], abbrs: (string | null | undefined)[] = []): number {
  const team = (l.team ?? "").toLowerCase(), label = l.label.toLowerCase();
  if (!team) return -1;
  for (let i = 0; i < names.length; i++) {
    const n = names[i].toLowerCase();
    if (n === team || n.includes(team) || label.startsWith(n) || abbrs[i]?.toLowerCase() === team) return i;
  }
  return -1;
}

export type MainCol = "spread" | "total" | "win";
export const MAIN_TITLES: Record<MainCol, string> = { spread: "Spread", total: "Total", win: "To win" };
export type MainLines = { cols: MainCol[]; rows: { name: string; side: number; cells: Partial<Record<MainCol, PackLeg>> }[] };

const SPREADS = ["spread", "puck line"], TOTALS = ["total", "goals"];

/** The game's main lines: each team's spread and price to win, the total's over and under (over on the away row, as the
 *  books lay it out), and the draw on its own row. Of a ladder's rungs the main one is the pair closest to even. */
export function mainLines(legs: PackLeg[], matchup: string, abbrs: (string | null | undefined)[] = []): MainLines | null {
  const names = sidesOf(matchup);
  const game = legs.filter((l) => !l.player);
  const closest = <K>(ls: PackLeg[], key: (l: PackLeg) => K): PackLeg[] => {
    const by = new Map<K, PackLeg[]>();
    for (const l of ls) by.set(key(l), [...(by.get(key(l)) ?? []), l]);
    const gap = (g: PackLeg[]) => (g.length >= 2 ? Math.abs(g[0].p - g[1].p) : 1 + Math.abs(g[0].p - 0.5));
    return [...by.values()].sort((a, b) => gap(a) - gap(b))[0] ?? [];
  };
  const sp = closest(game.filter((l) => SPREADS.includes(l.stat ?? "") && sideOf(l, names, abbrs) >= 0),
    (l) => (sideOf(l, names, abbrs) === 0 ? 1 : -1) * Number(l.point ?? 0));
  const tot = closest(game.filter((l) => TOTALS.includes(l.stat ?? "") && (l.side === "over" || l.side === "under") && l.point != null), (l) => Number(l.point));
  const win = game.filter((l) => l.stat === "moneyline");
  const draw = game.find((l) => l.stat === "draw");
  const rows: MainLines["rows"] = [0, 1].map((i) => ({ name: names[i] ?? "", side: i, cells: {
    spread: sp.find((l) => sideOf(l, names, abbrs) === i),
    total: tot.find((l) => l.side === (i === 0 ? "over" : "under")),
    win: win.find((l) => sideOf(l, names, abbrs) === i),
  } }));
  if (draw) rows.push({ name: "Draw", side: -1, cells: { win: draw } });
  const cols = (["spread", "total", "win"] as const).filter((c) => rows.some((r) => r.cells[c]));
  return cols.length ? { cols, rows: rows.filter((r) => cols.some((c) => r.cells[c])) } : null;
}

/** The small line over a main-line price: the team's own number, or the total with O / U. */
export function mainText(col: MainCol, l: PackLeg): string {
  if (col === "win" || l.point == null) return "";
  if (col === "total") return `${l.side === "under" ? "U" : "O"} ${l.point}`;
  return l.point > 0 ? `+${l.point}` : l.point < 0 ? `${MINUS}${Math.abs(l.point)}` : "PK";
}

/** A prop without its player's name: "Over 24.5 points". */
export function propText(l: PackLeg): string {
  const rest = l.player && l.label.startsWith(l.player) ? l.label.slice(l.player.length).trim() : l.label;
  return (rest || l.label).replace(/^./, (c) => c.toUpperCase());
}

/** A few props for the Popular tab: one per player, the best-priced over or yes (the most of its fair price back)
 *  inside the range a parlay leg usually sits in (50-80%, a little wider when the game has few), best first. Pass the
 *  legs as the chosen book prices them. Banned players are never suggested. */
export function popularProps(legs: PackLeg[], sport: string, bans: Ban[] = [], n = 6): PackLeg[] {
  const fit = legs.filter((l) => l.player && l.side !== "under" && l.side !== "no" && !l.unavailable && Number.isFinite(l.price)
    && !isBanned(bans, l.label, sport, l.player));
  const worth = (l: PackLeg) => l.p * toDec(l.price);
  const pick = (lo: number, hi: number) => {
    const best = new Map<string, PackLeg>();
    for (const l of fit) {
      if (l.p < lo || l.p > hi) continue;
      const cur = best.get(l.player!);
      if (!cur || worth(l) > worth(cur) || (worth(l) === worth(cur) && l.label < cur.label)) best.set(l.player!, l);
    }
    return [...best.values()].sort((a, b) => worth(b) - worth(a) || a.label.localeCompare(b.label)).slice(0, n);
  };
  const tight = pick(0.5, 0.8);
  return tight.length >= 3 ? tight : pick(0.4, 0.9);
}

/** The book that pays most among the prices we know (American odds); null when none is known yet. */
export function bestBook(prices: Partial<Record<BuildBook, number | null | undefined>>): BuildBook | null {
  let best: BuildBook | null = null;
  for (const b of BUILD_BOOKS) {
    const p = prices[b];
    if (p == null || !Number.isFinite(p)) continue;
    if (best == null || toDec(p) > toDec(prices[best]!)) best = b;
  }
  return best;
}

/** Does a wallet token fit this slip: its book, its sports, its teams' games, and (once a price is known) its legs and odds. */
export function tokenFits(p: PromoRow, slip: { book: BuildBook; sport: string; matchups: string[]; legs: number; dec: number | null }): boolean {
  if (p.book && p.book.toLowerCase() !== slip.book.toLowerCase()) return false;
  const sports = promoSports(p);
  if (sports && !sports.includes(slip.sport)) return false;
  if (!slip.matchups.every((m) => teamFits(p.teams, m))) return false;
  if (slip.dec != null) return promoFits(asPromo(p), slip.legs, slip.dec);
  return !(p.min_legs && slip.legs < Number(p.min_legs));
}

/** The slips this browser keeps, one per sport. Before Nov 5 a slip held one typed price for whichever book was
 *  chosen; now each book has its own, and an old single price is dropped (it didn't say whose it was). */
export type StoredSlip = { legs: { event_id: string; label: string }[]; prices: Partial<Record<BuildBook, string>> };
export function readSlips(raw: unknown, live: (eid: string) => boolean): { slips: Record<string, StoredSlip>; sport: string | null } {
  const out: Record<string, StoredSlip> = {};
  const s = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  for (const [k, v] of Object.entries(s)) {
    const x = v as { legs?: unknown; prices?: unknown } | null;
    if (k === "_sport" || !Array.isArray(x?.legs)) continue;
    const prices: StoredSlip["prices"] = {};
    for (const b of BUILD_BOOKS) { const t = (x.prices as Record<string, unknown> | undefined)?.[b]; if (typeof t === "string" && b !== "Novig") prices[b] = t; }
    out[k] = { legs: (x.legs as StoredSlip["legs"]).filter((l) => l && typeof l.label === "string" && live(l.event_id)), prices };
  }
  return { slips: out, sport: typeof s._sport === "string" ? s._sport : null };
}
