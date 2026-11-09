// Build your own parlay (Mike, 2026-09-28), ported from the old page's Fun-tab builder.
// Each game's legs come with a sample of simulated games as bitsets (leg_packs): a parlay's chance
// is the share of draws where every leg hits, scaled by each leg's market-fair chance. The grade
// isn't EV alone (parlays always cost something): it compares FanDuel's price with what its
// parlays this size usually pay, then checks each leg's price, whether the legs help each other,
// and Mike's own rules. Pure: runs in the browser.
import { parseOdds, pct, signed, toAm, toDec } from "./format";
import { isBanned, type Ban } from "./bans";

export type PackLeg = {
  label: string; player?: string; team?: string; stat?: string; side?: string; point?: number;
  price: number; p: number; p_pack: number; source?: string; bits?: string; not?: string; link?: string;
  link_main?: boolean;                                         // the link follows the main line (fanduel.mainLineText)
  dk_price?: number; dk_link?: string; dk_moved?: boolean; dk_link_main?: boolean;   // DraftKings' side (Oct 12, links.attach_dk)
  nv_id?: string; nv_price?: number;                           // Novig's side (Oct 28, novig_parlays.attach)
  unavailable?: boolean;                                       // not at this book at this number
};
/** The book a slip is built for (Oct 12: the Build tab's switch; Novig from Oct 28). */
export type BuildBook = "FanDuel" | "DraftKings" | "Novig";
export type Pack = {
  event_id: string; matchup: string; commence_time: string; game_ref?: string | null; sport: string;
  draws: number; legs: Record<string, PackLeg>;
};
export type PackGame = { event_id: string; matchup: string; commence_time: string; sport: string };
export type Band = { max_fair: number | null; ratio: number };
/** FanDuel's SGP pricing (fun_ledger.quote_model): log(quote / fair payout) from fair odds, legs, cross-game, its leg prices. */
export type QuoteModel = { coef: { intercept: number; log_fair: number; legs: number; cross_game: number; naive_gap: number };
  rmse: number; quotes: number };
/** FanDuel's usual payout share for this slip (quote / fair, decimal odds) from the model. */
export function modelRatio(m: QuoteModel, fairDec: number, naiveDec: number, legs: number, crossGame: boolean): number {
  const c = m.coef;
  return Math.exp(c.intercept + c.log_fair * Math.log(fairDec) + c.legs * legs + c.cross_game * (crossGame ? 1 : 0)
    + c.naive_gap * Math.log(naiveDec / fairDec));
}
export type SlipLeg = { event_id: string; label: string };

export const GRADES = ["A+", "A", "A−", "B+", "B", "B−", "C", "D", "F"] as const;
/** FanDuel's usual payout share by fair price, until Mike's typed quotes replace it (fun_results). */
export const DEFAULT_BANDS: Band[] = [
  { max_fair: 300, ratio: 0.78 }, { max_fair: 700, ratio: 0.79 }, { max_fair: 1500, ratio: 0.95 }, { max_fair: null, ratio: 1.05 },
];

/** A pack split in parts (pack_key <event_id>, -2, ...) merged into one, legs by label. */
export function mergePack(parts: Record<string, any>[]): Pack | null {
  if (!parts.length) return null;
  const first = parts.find((p) => (p.part ?? 1) === 1) ?? parts[0];
  const legs: Record<string, PackLeg> = {};
  for (const p of parts) for (const l of p.legs ?? []) legs[l.label] = l;
  return { event_id: String(first.event_id), matchup: first.matchup, commence_time: first.commence_time,
           game_ref: first.game_ref ?? null, sport: first.sport ?? "nfl", draws: Number(first.draws), legs };
}

const POP = new Uint8Array(256).map((_, i) => { let c = 0, x = i; while (x) { c += x & 1; x >>= 1; } return c; });
const decode = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));

export class Pricer {
  private cache = new Map<string, Uint8Array>();
  /** book: whose prices and links the legs carry. At DraftKings a leg it doesn't post at this exact number is
   *  unavailable (a moved rung is a different bet, and the draws price this one). At Novig a leg is there when Novig
   *  lists it (nv_id); its price is Novig's when $50+ stands behind it, else its fair price (an exchange has no vig, and
   *  the slip's own price comes from Novig's pricer). */
  constructor(private packs: Record<string, Pack>, readonly book: BuildBook = "FanDuel") {}

  pack(eid: string): Pack | undefined { return this.packs[eid]; }
  leg(eid: string, label: string): PackLeg | undefined {
    const l = this.packs[eid]?.legs[label];
    if (!l || this.book === "FanDuel") return l;
    if (this.book === "Novig") return l.nv_id
      ? { ...l, price: l.nv_price ?? Math.round(toAm(1 / l.p)), link: `https://novig.com/events/${l.nv_id}/oddsapi/5`, link_main: false }
      : { ...l, price: NaN, link: undefined, unavailable: true };
    return l.dk_price != null && !l.dk_moved ? { ...l, price: l.dk_price, link: l.dk_link, link_main: l.dk_link_main }
      : { ...l, price: NaN, link: undefined, unavailable: true };
  }

  /** The slip's Novig outcome ids, in order; null when a leg isn't on Novig. */
  novigIds(slip: SlipLeg[]): string[] | null {
    const ids = slip.map((s) => this.packs[s.event_id]?.legs[s.label]?.nv_id);
    return ids.every(Boolean) ? (ids as string[]) : null;
  }

  private bits(eid: string, label: string, depth = 0): Uint8Array | null {
    const key = eid + "|" + label;
    const hit = this.cache.get(key);
    if (hit) return hit;
    const l = this.leg(eid, label);
    if (!l || depth > 2) return null;
    let b: Uint8Array | null;
    if (l.bits) b = decode(l.bits);
    else if (l.not) { const o = this.bits(eid, l.not, depth + 1); b = o ? o.map((x) => ~x & 255) : null; }
    else b = null;
    if (b) this.cache.set(key, b);
    return b;
  }

  /** Joint fair chance of some legs of one game: share of draws where all hit x each leg's shrink. */
  joint(eid: string, labels: string[]): number | null {
    const pk = this.pack(eid);
    if (!pk || !labels.length) return null;
    const bs = labels.map((lb) => this.bits(eid, lb));
    if (bs.some((b) => !b)) return null;
    let n = 0;
    const first = bs[0]!;
    for (let i = 0; i < first.length; i++) { let a = 255; for (const b of bs) a &= b![i]; n += POP[a]; }
    const legs = labels.map((lb) => pk.legs[lb]);
    const shrink = legs.reduce((m, l) => m * (l.p / Math.max(l.p_pack, 1e-6)), 1);
    return Math.min((n / pk.draws) * shrink, Math.min(...legs.map((l) => l.p)));
  }
}

export type Evaluation = {
  games: string[]; legs: (PackLeg & SlipLeg)[]; p: number; indep: number; lift: number; naive: number; fair: number;
  worst: { label: string; v: number }; fights: { a: string; b: string; lift: number }[]; rules: string[];
  typical: number; typed: number | null; provisional: boolean; grade: string; idx: number; why: string; notes: string[];
};

const LINES = ["moneyline", "spread", "total"];

export function evaluate(pr: Pricer, slip: SlipLeg[], priceText: string, bands: Band[] = DEFAULT_BANDS,
                         model: QuoteModel | null = null): Evaluation | null {
  const byGame: Record<string, string[]> = {};
  for (const l of slip) (byGame[l.event_id] ??= []).push(l.label);
  const games = Object.keys(byGame).filter((eid) => pr.pack(eid));
  const legs = slip.map((l) => ({ ...pr.leg(l.event_id, l.label)!, ...l })).filter((l) => l.p != null);
  if (!legs.length || legs.length !== slip.length || legs.some((l) => l.unavailable)) return null;
  let p = 1;
  for (const eid of games) { const j = pr.joint(eid, byGame[eid]); if (j == null) return null; p *= j; }
  const indep = legs.reduce((m, l) => m * l.p, 1);
  const naive = legs.reduce((m, l) => m * toDec(l.price), 1);
  const values = legs.map((l) => ({ label: l.label, v: l.p * toDec(l.price) }));
  const worst = values.reduce((a, b) => (b.v < a.v ? b : a));
  const fights: Evaluation["fights"] = [];
  for (const eid of games) {
    const ls = byGame[eid];
    for (let i = 0; i < ls.length; i++) for (let k = i + 1; k < ls.length; k++) {
      const a = pr.leg(eid, ls[i])!, b = pr.leg(eid, ls[k])!;
      const lift = (pr.joint(eid, [ls[i], ls[k]]) ?? a.p * b.p) / (a.p * b.p);
      if (lift < 0.9) fights.push({ a: ls[i], b: ls[k], lift });
    }
  }
  // Mike's rules (2026-09-24): 55-80% legs, unders only as near-locks, one leg per player.
  const rules: string[] = [];
  const players = legs.filter((l) => l.player).map((l) => l.player!);
  const dup = players.find((x, i) => players.indexOf(x) !== i);
  if (dup) rules.push(`two legs on ${dup} (books price those as nearly one bet)`);
  for (const l of legs) {
    if (l.side === "under" && (l.p < 0.75 || l.p > 0.92)) rules.push(`${l.label}: unders only as near-locks (75–92%)`);
    else if (l.side !== "under" && (l.p < 0.55 || l.p > 0.8) && !LINES.includes(String(l.stat))) rules.push(`${l.label}: ${pct(l.p)} (your legs are 55–80%)`);
  }
  // FanDuel pays full margin on small parlays and near fair on long shots (Mike's quotes), so a
  // parlay is judged against its own size's usual payout share.
  const fair = toAm(1 / p);
  const band = bands.find((b) => b.max_fair == null || fair <= b.max_fair) ?? bands[bands.length - 1];
  // the quote model (Oct 12) knows this slip's legs, games and FanDuel's leg prices; the bands are its fallback
  const typical = model ? modelRatio(model, 1 / p, naive, legs.length, games.length > 1) : Number(band.ratio);
  const typed = parseOdds(priceText);
  let idx: number, why: string, provisional = false;
  if (typed != null) {
    const r = p * toDec(typed), rel = r / typical;
    idx = rel >= 1.25 ? 0 : rel >= 1.15 ? 1 : rel >= 1.08 ? 2 : rel >= 1.03 ? 3 : rel >= 0.98 ? 4 : rel >= 0.93 ? 5 : rel >= 0.88 ? 6 : rel >= 0.8 ? 7 : 8;
    why = `${pr.book} pays ${(r * 100).toFixed(0)}% of fair; ${model ? "a slip like this usually gets" : "parlays this size usually get"} ${(typical * 100).toFixed(0)}%. EV ${signed(r - 1)}.`;
  } else {
    const avg = values.reduce((s, x) => s + x.v, 0) / values.length;
    idx = avg >= 1.0 ? 2 : avg >= 0.96 ? 3 : avg >= 0.93 ? 4 : avg >= 0.9 ? 5 : avg >= 0.86 ? 6 : 7;
    why = pr.book === "Novig" ? "Asking Novig for its price…"
      : `Provisional, from the legs' own prices (${(avg * 100).toFixed(0)}% of fair on average). Type ${pr.book === "DraftKings" ? "DraftKings'" : "FanDuel's"} price for the real grade.`;
    provisional = true;
  }
  // Small, likely parlays are what the fun bucket is for (Mike, 2026-09-28): reward them, and hold
  // long shots down however well FanDuel pays them.
  const notes: string[] = [];
  if (p >= 0.25) { idx -= 1; notes.push(`+1: ${pct(p)} to hit. Small, likely parlays get a boost`); }
  else if (p < 0.04) { idx += 2; notes.push(`−2: ${pct(p, 1)} to hit is a long shot (the grade tops out at B−)`); }
  else if (p < 0.1) { idx += 1; notes.push(`−1: ${pct(p)} to hit is on the long side`); }
  if (legs.length >= 6) { idx += 1; notes.push(`−1: ${legs.length} legs (every leg adds FanDuel's margin)`); }
  if (fights.length) { idx += 1; notes.push(`−1: ${fights[0].a} and ${fights[0].b} work against each other (hit together ${fights[0].lift.toFixed(2)}× as often as chance)`); }
  if (worst.v < 0.85) { idx += 1; notes.push(`−1: ${worst.label} is priced ${((1 - worst.v) * 100).toFixed(0)}% under fair: swap it if you can`); }
  if (p < 0.04) idx = Math.max(idx, GRADES.indexOf("B−"));
  idx = Math.max(0, Math.min(idx, GRADES.length - 1));
  return { games, legs, p, indep, lift: p / indep, naive, fair, worst, fights, rules, typical, typed, provisional,
           grade: GRADES[idx], idx, why, notes };
}

export const gradeClass = (idx: number) => (idx <= 3 ? "good" : idx <= 6 ? "mid" : "bad");

/** A saved parlay's id: a hash of the sorted labels (the old page's, so a slip keeps its id across apps); a DraftKings
 *  build gets "~dk" (Oct 12) and a Novig one "~nv" (Oct 28), so the same legs at each book are tracked apart. `day` (the
 *  slip's first game day, ET; Nov 9) goes into the hash: the same legs built for another game are another slip, not the
 *  old settled bet (the same one-leg single on the next Knicks game showed as placed, and its Undo deleted the old bet).
 *  Without `day`: the id slips had before, still used for a slip placed under it while that bet is open (`slipId`). */
export const buildId = (slip: SlipLeg[], book: BuildBook = "FanDuel", day: string | null = null) =>
  "custom-" + (slip.map((l) => l.label).sort().join("|") + (day ? `@${day}` : "")).split("").reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7).toString(16)
  + (book === "DraftKings" ? "~dk" : book === "Novig" ? "~nv" : "");

/** The slip's first game day in Eastern time ("2026-11-09"); today when no game says. */
export function slipDay(pr: Pricer, slip: SlipLeg[], now = new Date()): string {
  const starts = slip.map((l) => pr.pack(l.event_id)?.commence_time).filter((x): x is string => !!x && !Number.isNaN(Date.parse(x)));
  const first = starts.length ? new Date(Math.min(...starts.map((x) => Date.parse(x)))) : now;
  return first.toLocaleDateString("en-CA", { timeZone: "America/New_York" });
}

/** The id this slip goes under: an open bet's old (day-less) id while that bet is open, so a placed slip keeps its id;
 *  otherwise the id with the slip's game day. `open`: whether an id is one of the account's open bets. */
export function slipId(pr: Pricer, slip: SlipLeg[], open: (id: string) => boolean, now = new Date()): string {
  const legacy = buildId(slip, pr.book);
  return open(legacy) ? legacy : buildId(slip, pr.book, slipDay(pr, slip, now));
}

/** The custom_parlays row (the old page's fun_quotes doc for a custom slip). */
export function customRow(pr: Pricer, slip: SlipLeg[], e: Evaluation, id: string = buildId(slip, pr.book)) {
  const games = e.games.map((eid) => {
    const pk = pr.pack(eid)!;
    return { matchup: pk.matchup, event_id: eid, game_ref: pk.game_ref ?? null, legs: slip.filter((l) => l.event_id === eid).map((l) => l.label) };
  });
  const sports = [...new Set(e.games.map((eid) => pr.pack(eid)!.sport))];
  return {
    sgp_id: id, price: e.typed, fair_price: Math.round(e.fair), naive_price: Math.round(toAm(e.naive)), p_fair: e.p,
    n_legs: e.legs.length, legs: e.legs.map((l) => l.label),
    matchup: games.length > 1 ? `Your SGP+: ${games.map((g) => g.matchup).join(", ")}` : games[0].matchup,
    odds_event_id: games.length === 1 ? games[0].event_id : null, games, sport: sports.length === 1 ? sports[0] : "mixed",
    grade: e.grade,
    grade_parts: { provisional: e.provisional, typical: e.typical, lift: +e.lift.toFixed(3), worst_leg: e.worst.label,
                   worst_value: +e.worst.v.toFixed(3), fights: e.fights.length, rules: e.rules.length },
  };
}
export type CustomRow = ReturnType<typeof customRow>;

/** "Record by grade" for a user's saved parlays (graded ones only). */
export function recordByGrade(rows: { grade: string | null; status: string | null; p_fair: number | null; profit_1u: number | null }[]) {
  const graded = rows.filter((r) => r.status === "won" || r.status === "lost");
  const by = new Map<string, { grade: string; graded: number; won: number; expected: number; units: number }>();
  for (const r of graded) {
    const g = r.grade || "?";
    const x = by.get(g) ?? { grade: g, graded: 0, won: 0, expected: 0, units: 0 };
    x.graded += 1; x.won += r.status === "won" ? 1 : 0; x.expected += Number(r.p_fair) || 0; x.units += Number(r.profit_1u) || 0;
    by.set(g, x);
  }
  const order = (g: string) => { const i = (GRADES as readonly string[]).indexOf(g); return i < 0 ? 99 : i; };
  return [...by.values()].sort((a, b) => order(a.grade) - order(b.grade));
}

// ------------------------------------------------------------------ the leg board (Oct 22)
// Mike asked for the Build tab to look like a sportsbook's SGP screen: a game's legs laid out as
// market tabs (Game lines, then one per player stat), each market a set of rows of price buttons
// (Over | Under, away | draw | home, one spread rung per row).

export type BoardRow = { key: string; legs: PackLeg[] };
export type BoardSection = { title: string; sub?: string; rows: BoardRow[] };
export type BoardTab = { key: string; title: string; count: number; sections: BoardSection[] };

const STAT_TITLES: Record<string, string> = {
  moneyline: "Moneyline", draw: "Moneyline", spread: "Spread", "puck line": "Puck line", total: "Total", goals: "Total goals",
  btts: "Both teams to score", "double chance": "Double chance",
  passing_yards: "Passing yds", rushing_yards: "Rushing yds", receiving_yards: "Receiving yds", receptions: "Receptions",
  tds: "Touchdowns", shots: "Shots", shots_on_target: "Shots on target", points: "Points", rebounds: "Rebounds",
  assists: "Assists", threes: "Threes", pra: "Pts + reb + ast",
};
const GAME_ORDER = ["moneyline", "spread", "puck line", "total", "goals", "btts", "double chance"];
const SIDES = ["over", "yes", "under", "no"];
const statTitle = (s?: string) => STAT_TITLES[s ?? ""] ?? (s ?? "Other").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const cap = (s: string) => s.replace(/^./, (c) => c.toUpperCase());

/** A leg's text on its button: the row says the market, so "Over 38.5", "Yes", "CLE +2.5", "Anytime TD". */
export function shortLeg(l: PackLeg): string {
  const side = l.side ?? "";
  if (l.player) {
    if ((side === "over" || side === "under") && l.point != null) return `${cap(side)} ${l.point}`;
    const rest = l.label.startsWith(l.player) ? l.label.slice(l.player.length).trim() : l.label;
    return cap(rest || l.label);
  }
  if (l.stat === "btts") return side === "no" ? "No" : "Yes";
  if ((side === "over" || side === "under") && l.point != null) return `${cap(side)} ${l.point}`;
  if (l.stat === "moneyline") return l.label.replace(/ (to win|ML)$/, "");
  return l.label;
}

/** A game's legs as the board's tabs. Team order follows the matchup ("Away @ Home"), the draw sits between. */
export function boardTabs(legs: PackLeg[], matchup = ""): BoardTab[] {
  const at = (l: PackLeg) => { const i = l.team ? matchup.indexOf(l.team) : -1; return i < 0 ? 1e4 : i; };
  const away = (l: PackLeg) => at(l) < matchup.indexOf(" @ ") || matchup.indexOf(" @ ") < 0;
  const order = (a: PackLeg, b: PackLeg) => {
    if (a.stat === "draw" || b.stat === "draw") return a.stat === "draw" ? (away(b) ? 1 : -1) : (away(a) ? -1 : 1);
    const s = SIDES.indexOf(a.side ?? "") - SIDES.indexOf(b.side ?? "");
    return s || at(a) - at(b) || a.label.localeCompare(b.label);
  };
  const rows = (ls: PackLeg[], key: (l: PackLeg) => number | string): BoardRow[] => {
    const by = new Map<string, PackLeg[]>();
    for (const l of ls) { const k = String(key(l)); by.set(k, [...(by.get(k) ?? []), l]); }
    return [...by.entries()].map(([k, v]) => ({ key: k, legs: v.sort(order) }))
      .sort((a, b) => (Number(a.key) - Number(b.key)) || a.key.localeCompare(b.key));
  };
  // A spread rung pairs the away side with the home side's opposite number (BUF +1.5 with CBJ -1.5).
  const rung = (l: PackLeg) => (l.stat === "spread" || l.stat === "puck line") ? (away(l) ? 1 : -1) * Number(l.point ?? 0)
    : (l.side === "over" || l.side === "under") && l.point != null ? Number(l.point) : 0;

  const game = legs.filter((l) => !l.player);
  const tabs: BoardTab[] = [];
  if (game.length) {
    const byStat = new Map<string, PackLeg[]>();
    for (const l of game) { const s = l.stat === "draw" ? "moneyline" : l.stat ?? ""; byStat.set(s, [...(byStat.get(s) ?? []), l]); }
    const stats = [...byStat.keys()].sort((a, b) => {
      const i = (s: string) => { const x = GAME_ORDER.indexOf(s); return x < 0 ? 99 : x; };
      return i(a) - i(b) || a.localeCompare(b);
    });
    const soccer = game.some((l) => l.stat === "draw");
    tabs.push({ key: "game", title: "Game lines", count: game.length,
      // soccer reads home team first (Nov 5): a row of team sides (the result, a spread) runs home, draw, away, as the game
      // card above it does; totals keep Over before Under (iPhone Build.boardTabs)
      sections: stats.map((s) => ({ title: s === "moneyline" && soccer ? "Result" : statTitle(s),
        rows: rows(byStat.get(s)!, rung).map((r) => soccer && r.legs.some((l) => l.team) ? { ...r, legs: [...r.legs].reverse() } : r) })) });
  }
  const props = new Map<string, PackLeg[]>();
  for (const l of legs.filter((x) => x.player)) props.set(l.stat ?? "", [...(props.get(l.stat ?? "") ?? []), l]);
  for (const [stat, ls] of [...props.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))) {
    const players = new Map<string, PackLeg[]>();
    for (const l of ls) players.set(l.player!, [...(players.get(l.player!) ?? []), l]);
    tabs.push({ key: stat, title: statTitle(stat), count: ls.length,
      sections: [...players.entries()].sort((a, b) => a[0].localeCompare(b[0]))
        .map(([who, pl]) => ({ title: who, sub: pl[0].team || undefined, rows: rows(pl, rung) })) });
  }
  return tabs;
}

// ------------------------------------------------------------------ promos (Oct 22)
// Mike's bonus bets and profit boosts, on parlays (his choice): a bonus bet's stake isn't returned, so a
// win pays only the profit; a profit boost multiplies the profit. Both grow as the odds lengthen, so a ranking at
// the book's likely quote runs to the longest slip allowed, where that quote is least sure (Oct 22 review: the
// quote model misses by ~12%). So a same-game slip is ranked at a cautious quote (one miss below the likely one), and
// plain parlays (one leg per game) pay exactly their legs' product: built from legs priced off a sharp book
// (Pinnacle, LowVig, BetOnline), they need no guess at all and may run longer.

/** A promo token's terms, as the book states them (all optional): stake in dollars, the cap on a boost's extra
 *  winnings in dollars, the fewest legs, and the shortest total odds (American) the token accepts. */
export type PromoTerms = { stake?: number; maxExtra?: number; minLegs?: number; minOdds?: number; maxOdds?: number; market?: string | null;
                           kinds?: string[] | null };   // the kinds of leg it allows (Nov 9, promos.LEG_CHOICES)
/** The markets a token can be limited to (Nov 5, migration 0039). A soccer draw is part of the moneyline; both teams to score
 *  and double chance fit only a token for any market. Shared cases: tests/fixtures/promos.json. */
export const MARKET_CHOICES = [["moneyline", "Moneyline"], ["spread", "Spread"], ["total", "Total"], ["props", "Player props"]] as const;
export function marketFits(market: string | null | undefined, leg: { stat?: string; player?: string }, kinds?: string[] | null): boolean {
  // a token for certain kinds of leg ("Anytime TD only", Nov 9): a player leg of one of them, in the packs' stat names
  if (kinds?.length && !(leg.player && kinds.includes(leg.stat ?? ""))) return false;
  if (!market) return true;
  if (market === "props") return !!leg.player;
  if (leg.player) return false;
  const s = leg.stat ?? "";
  return market === "moneyline" ? s === "moneyline" || s === "draw"
    : market === "spread" ? s === "spread" || s === "puck line"
    : market === "total" ? s === "total" || s === "goals" : false;
}
export type Promo = { kind: "none" } | ({ kind: "bonus" } & PromoTerms) | ({ kind: "boost"; pct: number } & PromoTerms);

/** Expected value per dollar staked (a bonus bet: per dollar of bonus credit) at decimal odds `dec`. A boost's
 *  extra winnings stop at the token's cap (maxExtra, which needs the stake to compare). */
export function promoEv(p: number, dec: number, promo: Promo): number {
  if (promo.kind === "bonus") return p * (dec - 1);
  if (promo.kind !== "boost") return p * dec - 1;
  let extra = (dec - 1) * promo.pct / 100;
  if (promo.stake && promo.maxExtra != null) extra = Math.min(extra, promo.maxExtra / promo.stake);
  return p * (dec + extra) - 1;
}

/** Whether a slip meets the token's terms: enough legs, and total odds between minOdds and maxOdds (FanDuel's
 *  "-200 Min | +200000 Max", Oct 24). */
export function promoFits(promo: Promo, legs: number, dec: number): boolean {
  if (promo.kind === "none") return true;
  if (promo.minLegs && legs < promo.minLegs) return false;
  if (promo.maxOdds != null && dec > toDec(promo.maxOdds) + 1e-9) return false;
  return promo.minOdds == null || dec >= toDec(promo.minOdds) - 1e-9;
}

/** A promo in a link (the promo helper, Oct 24): /build?promo=boost&pct=50&game=<event>&stake=25&min=-200&max=200000.
 *  Null when the link carries no promo. */
export function promoFromParams(sp: Record<string, string | undefined>): { promo: Promo; game: string | null } | null {
  const kind = sp.promo === "boost" || sp.promo === "bonus" ? sp.promo : null;
  if (!kind) return null;
  const n = (k: string) => { const v = Number(String(sp[k] ?? "").replace(/[^0-9.+-]/g, "")); return sp[k] && Number.isFinite(v) && v !== 0 ? v : undefined; };
  const terms: PromoTerms = { stake: n("stake"), maxExtra: n("cap"), minLegs: n("legs"), minOdds: n("min"), maxOdds: n("max") };
  const pct = n("pct");
  const promo: Promo = kind === "boost" ? { kind, pct: pct && pct > 0 && pct <= 500 ? pct : 50, ...terms } : { kind, ...terms };
  return { promo, game: sp.game || null };
}

/** The link for a promo (the reverse of promoFromParams). */
export function promoHref(promo: Promo, game: string | null): string {
  if (promo.kind === "none") return "/build";
  const q = new URLSearchParams({ promo: promo.kind });
  if (promo.kind === "boost") q.set("pct", String(promo.pct));
  if (game) q.set("game", game);
  const put = (k: string, v?: number) => { if (v != null) q.set(k, String(v)); };
  put("stake", promo.stake); put("cap", promo.maxExtra); put("legs", promo.minLegs); put("min", promo.minOdds); put("max", promo.maxOdds);
  return `/build?${q}`;
}

/** The book's usual payout share for a slip (the quote model, else the bands): its likely quote is that over the fair chance. */
export function typicalRatio(p: number, naive: number, legs: number, crossGame: boolean, bands: Band[] = DEFAULT_BANDS,
                             model: QuoteModel | null = null): number {
  if (model) return modelRatio(model, 1 / p, naive, legs, crossGame);
  const fair = toAm(1 / p);
  return Number((bands.find((b) => b.max_fair == null || fair <= b.max_fair) ?? bands[bands.length - 1]).ratio);
}

/** A leg whose fair chance comes from a sharp book's price, not soft books or a model: NFL, college and NBA packs name
 *  the book ("pinnacle", "betonlineag (market)"); soccer and NHL packs fit every chance to Pinnacle's prices
 *  (fun_soccer.targets, fun_nhl) and their source says where the price came from ("FanDuel price in the feed"). */
export const sharpLeg = (l: Pick<PackLeg, "source">) => /pinnacle|lowvig|betonline|price in the feed/i.test(String(l.source ?? ""));

export type PromoPick = {
  legs: SlipLeg[]; p: number; games: number;
  plain: boolean;     // one leg per game: it pays exactly the legs' product
  dec: number;        // the likely quote (the exact one for a plain parlay)
  low: number;        // the quote it's ranked at: cautious for a same-game slip, exact for a plain parlay
  ev: number;         // the promo's value per dollar at `low`
};

const SGP_MAX_DEC = 16;     // same-game slips to fair +1500: where Mike's typed quotes teach the quote model
const PLAIN_MAX_DEC = 26;   // plain parlays to fair +2500: their price is exact

/** The best bets for a promo: singles priced off a sharp book at their exact price (Oct 22), 2-3 leg same-game slips
 *  from each game's best-priced legs, ranked at a cautious
 *  quote, and 2-4 leg plain parlays across games from legs priced off a sharp book, at their exact price. */
export function findPromo(pr: Pricer, eids: string[], promo: Promo, bands: Band[] = DEFAULT_BANDS,
                          model: QuoteModel | null = null, top = 8, bans: Ban[] = []): PromoPick[] {
  const out = promoCandidates(pr, eids, promo, bands, model, bans);
  // the best 3 singles always show, apart from the parlays: an uncapped boost ranks long parlays of near-fair legs
  // higher, but a single risks far less, a token's winnings cap favors it, and some tokens take singles only
  const byEv = (a: PromoPick, b: PromoPick) => b.ev - a.ev;
  return [...out.filter((f) => f.legs.length === 1).sort(byEv).slice(0, 3),
          ...out.filter((f) => f.legs.length > 1).sort(byEv).slice(0, top)];
}

/** Every bet findPromo weighs, unranked (the promo finder, lib/promo-finder.ts, ranks them its own way). */
export function promoCandidates(pr: Pricer, eids: string[], promo: Promo, bands: Band[] = DEFAULT_BANDS,
                                model: QuoteModel | null = null, bans: Ban[] = []): PromoPick[] {
  type L = PackLeg & { eid: string; v: number };
  const per = eids.filter((e) => pr.pack(e)).map((eid) => Object.values(pr.pack(eid)!.legs)
    .map((l) => ({ ...pr.leg(eid, l.label)!, eid }))
    // a leg the book doesn't post (FanDuel's soccer totals: our fair price stands in) can't be bet, so it can't carry a promo
    .filter((l) => !l.unavailable && l.p >= 0.05 && l.p <= 0.95 && Number.isFinite(l.price)
      && !(pr.book === "FanDuel" && String(l.source ?? "").startsWith("fair price"))
      && marketFits(promo.kind === "none" ? null : promo.market, l, promo.kind === "none" ? null : promo.kinds)                   // a token for one market (Nov 5)
      && !isBanned(bans, l.label, pr.pack(eid)?.sport ?? null, l.player || null))     // the ban list (Oct 25)
    .map((l) => ({ ...l, v: l.p * toDec(l.price) } as L))
    .sort((a, b) => b.v - a.v));
  const out: PromoPick[] = [];
  const cap = Math.max(...bands.map((b) => Number(b.ratio)));
  const miss = Math.exp(-(model?.rmse ?? 0.12));     // one typical miss of the quote model
  const consider = (ls: L[]) => {
    // one leg per player, and one per game market (Over 1.5 with Over 2.5 is one bet twice)
    const keys = ls.map((l) => l.eid + "|" + (l.player || (l.stat === "draw" ? "moneyline" : l.stat)));
    if (new Set(keys).size < keys.length) return;
    const byGame = new Map<string, string[]>();
    for (const l of ls) byGame.set(l.eid, [...(byGame.get(l.eid) ?? []), l.label]);
    // nested legs (A or draw with A to win) are one bet twice; the books refuse them and the quote model overrates them
    for (const a of ls) for (const b of ls) if (a !== b && a.eid === b.eid && a.label < b.label) {
      const j = pr.joint(a.eid, [a.label, b.label]);
      if (j == null || j >= 0.97 * Math.min(a.p, b.p)) return;
    }
    let p = 1;
    for (const [eid, lbs] of byGame) { const j = pr.joint(eid, lbs); if (j == null) return; p *= j; }
    const plain = [...byGame.values()].every((x) => x.length === 1);
    if (p <= 0 || 1 / p > (plain ? PLAIN_MAX_DEC : SGP_MAX_DEC)) return;
    const naive = ls.reduce((m, l) => m * toDec(l.price), 1);
    // a same-game slip: never more than the best payout share Mike's typed quotes have shown (the model extrapolates
    // past it), nor more than the legs' product; ranked one miss below that
    const ratio = plain ? p * naive : Math.min(typicalRatio(p, naive, ls.length, byGame.size > 1, bands, model), cap);
    const dec = plain ? naive : Math.min(ratio / p, naive);
    const low = plain ? naive : Math.min((ratio * miss) / p, naive);
    if (!promoFits(promo, ls.length, low)) return;
    out.push({ legs: ls.map((l) => ({ event_id: l.eid, label: l.label })), p, games: byGame.size, plain, dec, low,
               ev: promoEv(p, low, promo) });
  };
  // same-game slips: 2-3 legs from each game's 14 best-priced legs. A token with a leg minimum of 3 or more (Mike, Oct 26:
  // "if a boost has a leg minimum and it's for one game it never gives any options") gets slips of that many legs and
  // one more (up to 6), from a pool that mixes the best-priced legs with the best-priced likely ones (45%+): the
  // best-priced legs are long shots, and three of them already ran past the +1500 fair cap, so nothing was left.
  const need = Math.max(2, promo.kind === "none" ? 0 : promo.minLegs ?? 0);
  const sizes = need <= 3 ? [2, 3] : [need, Math.min(need + 1, 6)].filter((n, i, a) => a.indexOf(n) === i);
  for (const g of per) {
    const t = need < 3 ? g.slice(0, 14)
      : [...new Map([...g.slice(0, 7), ...g.filter((l) => l.p >= 0.45).slice(0, 7)].map((l) => [l.label, l])).values()];
    const pick = (from: number, chosen: L[], n: number) => {
      if (chosen.length === n) { consider(chosen); return; }
      for (let i = from; i < t.length; i++) pick(i + 1, [...chosen, t[i]], n);
    };
    for (const n of sizes) pick(0, [], n);
  }
  // singles: one leg priced off a sharp book pays exactly its price, so a boost or a bonus keeps all of it (Oct 22: a
  // 100% boost on Cole Kmet over 1.5 receptions, FanDuel +178 against a 33.2% fair chance, was worth +51%)
  for (const g of per) for (const l of g.filter(sharpLeg)) consider([l]);
  // plain parlays: each game's best 3 legs priced off a sharp book, one per game, 2-4 legs, from the 8 games whose best
  // leg is priced best (about 7,500 slips at most)
  const sharp = per.map((g) => g.filter(sharpLeg).slice(0, 3)).filter((g) => g.length)
    .sort((a, b) => b[0].v - a[0].v).slice(0, 8);
  const walk = (from: number, picked: L[]) => {
    if (picked.length >= 2) consider(picked);
    if (picked.length === 4) return;
    for (let gi = from; gi < sharp.length; gi++) for (const l of sharp[gi]) walk(gi + 1, [...picked, l]);
  };
  if (sharp.length > 1) walk(0, []);
  return out;
}

// ------------------------------------------------------------------ the two-book lock (Oct 22)
// A promo on one side at the promo's book, the other side with cash at the other book, sized so both outcomes pay the
// same: the promo's value for sure instead of on average (Mike has FanDuel and DraftKings). A bonus bet S at decimal dA
// hedged at dB locks S(dA-1)(1-1/dB); a boosted cash stake S that would win W (profit plus the capped extra) locks
// W - (W+S)/dB. Singles only: hedging a parlay's every outcome takes more bets than it saves.

/** What both outcomes pay, per promo dollar, and the hedge per promo dollar. Null for no promo. */
export function lockValue(dA: number, dB: number, promo: Promo): { locked: number; hedge: number } | null {
  if (promo.kind === "bonus") { const hedge = (dA - 1) / dB; return { locked: hedge * (dB - 1), hedge }; }
  if (promo.kind !== "boost") return null;
  let extra = (dA - 1) * promo.pct / 100;
  if (promo.stake && promo.maxExtra != null) extra = Math.min(extra, promo.maxExtra / promo.stake);
  const win = dA - 1 + extra;                // the promo bet's profit if it wins
  const hedge = (win + 1) / dB;              // covers the profit and the lost stake
  return { locked: win - hedge, hedge };
}

export type LockPick = {
  event_id: string; promoLeg: string; hedgeLeg: string; promoPrice: number; hedgePrice: number;
  promoLink?: string; hedgeLink?: string; locked: number; hedge: number;
};

/** The other side of a leg in its game: an explicit opposite (the pack's `not`), the opposite side of the same
 *  number (over/under, yes/no; a player's too), the other team's opposite rung, or the other team in a two-way
 *  moneyline (no draw in the pack). */
export function opposite(pk: Pack, a: PackLeg): PackLeg | undefined {
  const legs = Object.values(pk.legs);
  const flip: Record<string, string> = { over: "under", under: "over", yes: "no", no: "yes" };
  return legs.find((b) => b.label !== a.label && (a.not === b.label || b.not === a.label))
    ?? legs.find((b) => b.label !== a.label && b.stat === a.stat && (b.player ?? "") === (a.player ?? "") && b.point === a.point
      && !!a.side && flip[a.side] === b.side && (a.stat !== "moneyline" && a.stat !== "spread" && a.stat !== "puck line"))
    ?? legs.find((b) => b.label !== a.label && (a.stat === "spread" || a.stat === "puck line") && b.stat === a.stat
      && b.team !== a.team && a.point != null && b.point === -a.point)
    ?? (a.stat === "moneyline" && !legs.some((x) => x.stat === "draw")
      ? legs.find((b) => b.label !== a.label && b.stat === "moneyline" && !b.player && b.team !== a.team) : undefined);
}

/** A price the book really posts: not a fair-price stand-in (FanDuel's soccer goals and puck lines) nor a moved rung. */
const posted = (pr: Pricer, eid: string, label: string) => {
  const l = pr.leg(eid, label);
  if (!l || l.unavailable || !Number.isFinite(l.price)) return undefined;
  if (pr.book === "FanDuel" && /^(fair price|no fanduel)/i.test(String(l.source ?? ""))) return undefined;
  return l;
};

/** The best locks for a promo at `pr`'s book, hedged at `hedge`'s book, from these games' two-sided markets. A pair
 *  whose two prices add to under 98% or over 115% (implied) is a mismatched feed rung, not a bet: it's skipped, as is
 *  a price more than 30% off our fair chance. */
export function findLocks(pr: Pricer, hedge: Pricer, eids: string[], promo: Promo, top = 5, bans: Ban[] = []): LockPick[] {
  if (promo.kind === "none" || pr.book === hedge.book || (promo.minLegs ?? 1) > 1) return [];
  const out: LockPick[] = [];
  for (const eid of eids) {
    const pk = pr.pack(eid);
    if (!pk) continue;
    for (const raw of Object.values(pk.legs)) {
      if (!marketFits(promo.market, raw, promo.kinds)) continue;
      const b0 = opposite(pk, raw);
      if (!b0) continue;
      const a = posted(pr, eid, raw.label), b = posted(hedge, eid, b0.label);
      if (!a || !b) continue;
      if (isBanned(bans, a.label, pk.sport, a.player || null) || isBanned(bans, b.label, pk.sport, b.player || null)) continue;   // the ban list
      const dA = toDec(a.price), dB = toDec(b.price);
      const over = 1 / dA + 1 / dB;
      if (over < 0.98 || over > 1.15 || Math.abs(a.p * dA - 1) > 0.3 || Math.abs(b.p * dB - 1) > 0.3) continue;
      if (!promoFits(promo, 1, dA)) continue;
      const v = lockValue(dA, dB, promo)!;
      out.push({ event_id: eid, promoLeg: a.label, hedgeLeg: b.label, promoPrice: a.price, hedgePrice: b.price,
                 promoLink: a.link, hedgeLink: b.link, locked: v.locked, hedge: v.hedge });
    }
  }
  return out.sort((x, y) => y.locked - x.locked).slice(0, top);
}

/** Themed slips (Nov 4, idea #69): one leg per game, the best-priced leg that fits, from the best games. Plain parlays, so the
 *  price is the legs' own, exact. Port: Build.themedSlip; fixture tests/fixtures/themes.json. */
export const SLIP_THEMES = [
  { key: "underdogs", title: "Underdogs", sub: "Moneyline dogs, 25-48% each" },
  { key: "favorites", title: "Favorites", sub: "Moneyline favorites, 60-85% each" },
  { key: "overs", title: "Overs only", sub: "Game and player overs, 45-75% each" },
  { key: "btts", title: "Both teams score", sub: "Soccer: both teams to score" },
] as const;
export type SlipTheme = (typeof SLIP_THEMES)[number]["key"];
export type ThemedSlip = { theme: SlipTheme; legs: SlipLeg[]; p: number; dec: number; ev: number };

const fitsTheme = (l: PackLeg, theme: SlipTheme) =>
  theme === "underdogs" ? l.stat === "moneyline" && l.p >= 0.25 && l.p < 0.48
  : theme === "favorites" ? l.stat === "moneyline" && l.p >= 0.6 && l.p <= 0.85
  : theme === "overs" ? l.side === "over" && l.p >= 0.45 && l.p <= 0.75
  : l.stat === "btts" && l.side === "yes" && l.p >= 0.4;

export function themedSlip(pr: Pricer, eids: string[], theme: SlipTheme, size = 3, bans: Ban[] = []): ThemedSlip | null {
  const best: { eid: string; l: PackLeg; v: number }[] = [];
  for (const eid of eids) {
    const pack = pr.pack(eid);
    if (!pack) continue;
    let top: { eid: string; l: PackLeg; v: number } | null = null;
    for (const raw of Object.values(pack.legs)) {
      const l = pr.leg(eid, raw.label) ?? pack.legs[raw.label] ?? raw;
      if (l.unavailable || !Number.isFinite(l.price) || !fitsTheme(l, theme)) continue;
      if (pr.book === "FanDuel" && String(l.source ?? "").startsWith("fair price")) continue;      // the book doesn't post it
      if (isBanned(bans, l.label, pack.sport, l.player || null) || !(l.bits || l.not)) continue;
      const v = l.p * toDec(l.price);
      if (!top || v > top.v || (v === top.v && l.label < top.l.label)) top = { eid, l, v };
    }
    if (top) best.push(top);
  }
  best.sort((a, b) => b.v - a.v || a.eid.localeCompare(b.eid));
  const picks = best.slice(0, size);
  if (picks.length < 2) return null;
  const p = picks.reduce((m, x) => m * x.l.p, 1), dec = picks.reduce((m, x) => m * toDec(x.l.price), 1);
  return { theme, legs: picks.map((x) => ({ event_id: x.eid, label: x.l.label })), p, dec, ev: p * dec - 1 };
}
