// Snap a slip (Oct 24): a sportsbook screenshot read into a bet (lib/slip-read.ts), then matched here to the app's own
// games so the bet grades and tracks like any other. Pure, so the tests run it. Game refs follow what the graders read
// (fun_ledger.leg_sport): NFL "2026_07_KC_LV", college/NHL "ncaaf:<id>" / "nhl:<id>", NBA "nba|HOME|AWAY|tip" (ESPN
// abbreviations), soccer "<league>|Home|Away|kickoff", UFC "ufc:<ESPN event>:<fight>" (from the fight's game_analysis
// row: the games table keys UFC by the odds event and has no fighters' sides, so fights match on last names, Oct 25).
import type { Game } from "./data";
import { toAm, toDec } from "./format";
import { etInstant } from "./time";
import { isTeam, parseLeg } from "./live";
import { Pricer, type Pack } from "./builder";
import { fullName, sameTeam } from "./cards";
import TEAMS from "./teams.json";

export const SPORTS = ["nfl", "ncaaf", "nba", "ncaab", "nhl", "soccer", "ufc", "other"] as const;
export const SOCCER_LEAGUES = ["epl", "la_liga", "serie_a", "bundesliga", "ligue_1", "mls", "ucl", "uel", "uecl"] as const;

/** What the reader returns: the slip as it reads, in the app's leg wording. */
export type SlipRead = {
  book: "FanDuel" | "DraftKings" | "Novig" | "Other";
  price: number;                 // the book's own American odds, before any boost
  boost_pct: number | null;      // a profit boost in percent
  stake_dollars: number;
  bonus: boolean;                // a bonus bet (the stake is the book's credit)
  protect?: boolean;             // FanDuel Bet Protect+ on it (Oct 26: a 3% fee; a leg on a player who sits counts as won)
  reset?: boolean;               // a bet reset token on it (Nov 1): if it loses, the stake comes back as a bonus bet
  placed_at: string | null;      // as the slip shows it, Eastern, ISO without a zone ("2026-10-24T13:06:00")
  legs: { label: string; matchup: string; sport: (typeof SPORTS)[number]; soccer_league: (typeof SOCCER_LEAGUES)[number] | null }[];
};

/** A leg's own price at each book, from its game's Build pack (withPrices): what the price check multiplies. */
export type LegPrices = { FanDuel?: number; DraftKings?: number };
export type DraftLeg = { label: string; matchup: string; sport: string; game_ref: string | null; start: string | null; matched: boolean;
                         event_id?: string | null; prices?: LegPrices };
/** What a slip's legs are worth (slipFair): `labels` are the legs it was worked out on, so an edited leg drops it (fairOf). */
export type SlipFair = { p: number | null; labels: string[]; missing: string[] };
export type Draft = Omit<SlipRead, "legs"> & { legs: DraftLeg[]; fair?: SlipFair | null };

// ESPN's NBA abbreviations (sources/nba.NBA_TEAMS), by the end of the team's name
const NBA: [string, string][] = [["Hawks", "ATL"], ["Nets", "BKN"], ["Celtics", "BOS"], ["Hornets", "CHA"], ["Bulls", "CHI"],
  ["Cavaliers", "CLE"], ["Mavericks", "DAL"], ["Nuggets", "DEN"], ["Pistons", "DET"], ["Warriors", "GS"], ["Rockets", "HOU"],
  ["Pacers", "IND"], ["Clippers", "LAC"], ["Lakers", "LAL"], ["Grizzlies", "MEM"], ["Heat", "MIA"], ["Bucks", "MIL"],
  ["Timberwolves", "MIN"], ["Pelicans", "NO"], ["Knicks", "NY"], ["Thunder", "OKC"], ["Magic", "ORL"], ["76ers", "PHI"],
  ["Suns", "PHX"], ["Trail Blazers", "POR"], ["Spurs", "SA"], ["Kings", "SAC"], ["Raptors", "TOR"], ["Jazz", "UTAH"], ["Wizards", "WSH"]];
export const nbaAbbr = (team: string | null) => NBA.find(([n]) => String(team ?? "").endsWith(n))?.[1] ?? null;

const iso = (t: string) => new Date(t).toISOString().replace(".000Z", "+00:00");

// a fighter's last name, accents off (a slip and ESPN can differ on them)
const lastName = (n: string) => n.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim().split(/\s+/).pop() ?? "";

/** A UFC fight's two fighters, from its matchup ("A vs B"): the games table has no sides for fights. */
function fighters(g: Game): [string, string] | null {
  const [a, b] = String(g.matchup ?? "").split(/ vs\.? /);
  return a && b ? [a, b] : null;
}

/** The app's game for a slip leg: same sport, both sides named, the soonest start from 12 hours before the bet on. */
export function matchGame(leg: SlipRead["legs"][number], games: Game[], placedAt: string): Game | null {
  const [x, y] = leg.matchup.split(/ @ | vs\.? | v /);
  if (!x || !y) return null;
  // NFL and NHL rows hold codes ("PIT", "MTL"): a side is its full name and its code, or a slip's "Pittsburgh Steelers"
  // never matched (Oct 25: both of that morning's Steelers-Saints slips saved with no ref)
  const teams = (TEAMS as Record<string, { name: string; abbr: string[] }[]>)[leg.sport] ?? [];
  const side = (n: string | null) => ({ name: teams.find((t) => t.abbr.includes(n ?? ""))?.name ?? n ?? "", abbr: n ?? "", score: null });
  const from = Date.parse(placedAt) - 12 * 3600_000;
  const sameFight = (g: Game) => {
    const f = fighters(g);
    if (!f) return false;
    const want = [lastName(x), lastName(y)].sort(), have = f.map(lastName).sort();
    return want[0] === have[0] && want[1] === have[1];
  };
  const hits = games.filter((g) => g.league === leg.sport && g.commence_time && Date.parse(g.commence_time) >= from
    && (leg.sport === "ufc" ? sameFight(g)
      : (isTeam(x, side(g.away)) && isTeam(y, side(g.home))) || (isTeam(x, side(g.home)) && isTeam(y, side(g.away)))));
  return hits.sort((a, b) => String(a.commence_time).localeCompare(String(b.commence_time)))[0] ?? null;
}

/** The grader's ref for a matched game (null when the sport's ref can't be built). `ufcRefs`: a fight's game id -> its
 * "ufc:<ESPN event>:<fight>" ref (data.ufcRefs, from game_analysis). */
export function gameRef(g: Game, leg: SlipRead["legs"][number], ufcRefs: Record<string, string> = {}): string | null {
  if (!g.commence_time) return null;
  const id = g.game_id.includes(":") ? g.game_id.split(":").slice(1).join(":") : g.game_id;
  switch (g.league) {
    case "nfl": return /^\d{4}_\d{2}_/.test(id) ? id : null;
    // the graders key these by CFBD's, CBBD's and the NHL's numeric ids: a game the paid pull added holds the Odds API's
    // 32-hex id, and a ref built from it never graded (Nov 9: Georgia + Miami, open two days after both finals). No ref
    // then: the matchup goes with the leg and the worker finds the ref (fun_ledger._find_ref)
    case "ncaaf": case "ncaab": case "nhl": return /^\d+$/.test(id) ? `${g.league}:${id}` : null;
    case "nba": { const h = nbaAbbr(g.home), a = nbaAbbr(g.away); return h && a ? `nba|${h}|${a}|${iso(g.commence_time)}` : null; }
    case "soccer": return leg.soccer_league && g.home && g.away ? `${leg.soccer_league}|${g.home}|${g.away}|${iso(g.commence_time)}` : null;
    case "ufc": return ufcRefs[g.game_id] ?? null;
    default: return null;
  }
}

/** The slip as a draft to confirm: each leg matched to the app's game (its full matchup and ref) where one fits. */
export function draft(read: SlipRead, games: Game[], now = new Date(), ufcRefs: Record<string, string> = {}): Draft {
  const placed = read.placed_at ?? now.toISOString();
  return { ...read, legs: read.legs.map((l) => {
    const g = matchGame(l, games, placed);
    const ref = g ? gameRef(g, l, ufcRefs) : null;
    return { label: l.label, matchup: g?.matchup ?? l.matchup, sport: l.sport, game_ref: ref, start: g?.commence_time ?? null, matched: !!g,
             event_id: g?.odds_event_id ?? null };
  }) };
}

// A slip's label as the packs write it: case, "yards" and name periods aside ("J.J. McCarthy" / "J.J McCarthy"; "2.5" stays).
const normLabel = (s: string) => s.toLowerCase().replace(/yards/g, "yds").replace(/\.(?!\d)/g, "").replace(/\s+/g, " ").trim();
/** The ways a pack can write the same leg: "over 2.5 receptions" is "3+ receptions", and back. */
function labelForms(label: string): string[] {
  const n = normLabel(label), out = [n];
  let m = /^(.+) over (\d+)\.5 (.+)$/.exec(n);
  if (m) out.push(`${m[1]} ${Number(m[2]) + 1}+ ${m[3]}`);
  m = /^(.+) (\d+)\+ (.+)$/.exec(n);
  if (m && Number(m[2]) > 0) out.push(`${m[1]} over ${Number(m[2]) - 1}.5 ${m[3]}`);
  return out;
}

/** The pack's leg for a slip's words. A pack can write a team's line in its own way ("NYR to win"; a slip says "New York
 *  Rangers ML"), so a leg that doesn't match as written is read: same kind of bet, same team, same number. */
export function findPackLeg<T extends { label: string }>(label: string, legs: T[], sport: string): T | undefined {
  const forms = labelForms(label);
  const exact = legs.find((p) => forms.includes(normLabel(p.label)));
  if (exact) return exact;
  const want = parseLeg(label);
  if (!want) return undefined;
  return legs.find((p) => {
    const got = parseLeg(p.label);
    if (!got || got.kind !== want.kind) return false;
    if (want.kind === "total" && got.kind === "total") return want.side === got.side && want.point === got.point;
    if (want.kind === "spread" && got.kind === "spread") return want.point === got.point && sameTeam(fullName(sport, want.team), fullName(sport, got.team));
    if (want.kind === "ml" && got.kind === "ml") return sameTeam(fullName(sport, want.team), fullName(sport, got.team));
    return false;
  });
}

/** A slip's fair chance from its games' packs: legs in one game together (their draws), games multiplied. A leg it can't find
 *  (a started game's pack is gone, a market we don't price) means no price at all, and says which: part of a parlay's price
 *  is no price. */
export function slipFair(legs: DraftLeg[], packs: Record<string, Pack>): SlipFair {
  const pr = new Pricer(packs);
  const labels = legs.map((l) => l.label), missing: string[] = [];
  const byGame = new Map<string, string[]>();
  for (const l of legs) {
    const pack = l.event_id ? packs[l.event_id] : undefined;
    const hit = pack ? findPackLeg(l.label, Object.values(pack.legs), l.sport) : undefined;
    if (!hit || !l.event_id) missing.push(l.label);
    else byGame.set(l.event_id, [...(byGame.get(l.event_id) ?? []), hit.label]);
  }
  if (missing.length || !legs.length) return { p: null, labels, missing };
  let p = 1;
  for (const [eid, lbs] of byGame) {
    const j = pr.joint(eid, lbs);
    if (j == null) return { p: null, labels, missing: lbs };
    p *= j;
  }
  return { p, labels, missing: [] };
}

/** The draft's fair price, if its legs are still the ones it was worked out on. */
export function fairOf(d: Pick<Draft, "fair" | "legs">): (SlipFair & { p: number }) | null {
  const f = d.fair;
  if (!f || f.p == null) return null;
  const now = d.legs.map((l) => l.label);
  return now.length === f.labels.length && now.every((x, i) => x === f.labels[i]) ? { ...f, p: f.p } : null;
}

export type SlipValue = { ev: number; fair: number; verdict: "plus" | "even" | "minus" };
const EVEN = 0.01;      // within this of even money is about even: the fair price isn't that exact
/** What a slip is worth per dollar at its price: a boost pays extra on the profit; a bonus bet's stake isn't yours. */
export function slipEv(p: number, price: number, boostPct: number | null | undefined, bonus: boolean | null | undefined): SlipValue {
  const profit = (toDec(price) - 1) * (1 + (boostPct ?? 0) / 100);
  const ev = bonus ? p * profit : p * (profit + 1) - 1;
  return { ev, fair: Math.round(toAm(1 / p)), verdict: ev > EVEN ? "plus" : ev < -EVEN ? "minus" : "even" };
}

type PackLegPrice = { label: string; price?: number | null; dk_price?: number | null; dk_moved?: boolean };
/** Each matched leg's own price at FanDuel and DraftKings from its game's pack (`packs`: odds event id -> the pack's
 * legs), where the pack has that exact leg. A DraftKings leg at a moved number is a different bet: no price. */
export function withPrices(d: Draft, packs: Record<string, PackLegPrice[]>): Draft {
  return { ...d, legs: d.legs.map((l) => {
    const legs = l.event_id ? packs[l.event_id] : undefined;
    if (!legs) return l;
    const hit = findPackLeg(l.label, legs, l.sport);
    if (!hit) return l;
    const prices: LegPrices = {};
    if (hit.price != null) prices.FanDuel = hit.price;
    if (hit.dk_price != null && !hit.dk_moved) prices.DraftKings = hit.dk_price;
    return { ...l, prices };
  }) };
}

/** How far a read price can sit above the legs' own prices multiplied. A parlay pays at most about that product
 * (Oct 25-26: cross-game slips 1.00-1.04x of it, same-game ones 0.6-0.9x); four misread slips came in at 2-4.6x. */
export const PRICE_CHECK_RATIO = 1.5;
export type PriceCheck = { legs_price: number; ratio: number; flag: boolean };
/** The slip's price against its legs' own prices at its book, multiplied; null unless every leg has one there. */
export function priceCheck(legs: DraftLeg[], book: SlipRead["book"], price: number | null): PriceCheck | null {
  if ((book !== "FanDuel" && book !== "DraftKings") || price == null || !legs.length) return null;
  let dec = 1;
  for (const l of legs) {
    const p = l.prices?.[book];
    if (p == null) return null;
    dec *= toDec(p);
  }
  const ratio = toDec(price) / dec;
  return { legs_price: Math.round(toAm(dec)), ratio, flag: ratio > PRICE_CHECK_RATIO };
}

/** The bets row for a confirmed draft (kind custom, like the bets Claude enters by hand): units from the unit size,
 * the label in the usual words, the games with their refs. */
export function betRow(d: Draft, unitDollars: number, placedAtIso: string, id: string) {
  const units = Math.round((d.stake_dollars / unitDollars) * 1000) / 1000;
  // the boosted price: the profit grows, and an odds-on price can stay odds-on (-200 with 30% is -154, not "+65"; Nov 9)
  const boosted = d.boost_pct ? Math.round(toAm(1 + (toDec(d.price) - 1) * (1 + d.boost_pct / 100))) : null;
  const money = d.bonus ? `Bonus bet $${d.stake_dollars}` : `$${d.stake_dollars} cash`;
  const label = d.boost_pct ? `${money}, ${d.boost_pct}% profit boost (${d.price > 0 ? "+" : ""}${d.price} -> ${boosted! > 0 ? "+" : ""}${boosted})` : money;
  // each game keeps its sport: a game with no ref (a college or NHL game on the Odds API's id) still grades by its
  // sport once the worker finds its ref (fun_ledger.game_sport)
  const byGame = new Map<string, { matchup: string; sport: string; game_ref?: string; legs: string[] }>();
  for (const l of d.legs) {
    const k = l.game_ref ?? l.matchup;
    const g = byGame.get(k) ?? { matchup: l.matchup, sport: l.sport, ...(l.game_ref ? { game_ref: l.game_ref } : {}), legs: [] };
    g.legs.push(l.label);
    byGame.set(k, g);
  }
  const day = new Date(placedAtIso).toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric" });
  return {
    kind: "custom" as const, sgp_id: `custom-${d.book === "DraftKings" ? "dk" : d.book === "Novig" ? "nv" : "fd"}-snap-${id}`,
    mode: "real" as const, price: d.price, stake: units, book: d.book === "Other" ? "FanDuel" : d.book, label,
    matchup: d.legs.length === 1 ? d.legs[0].matchup : `Parlay ${day} · ${d.legs.length} legs`,
    legs: d.legs.map((l) => l.label), games: [...byGame.values()], placed_at: placedAtIso, bonus: d.bonus, protect: d.protect === true, reset: d.reset === true,
    boost: d.boost_pct || null,
  };
}

/** "2026-10-24T13:06:00" read off a slip (Eastern wall time) as an instant. */
export function easternIso(local: string | null, now = new Date()): string {
  if (!local) return now.toISOString();
  const at = etInstant(local);
  return Number.isNaN(at.getTime()) ? now.toISOString() : at.toISOString();
}

/** A game a leg the reader couldn't match can be put on (Nov 9): the slip's day's games, with the grader's ref worked out
 *  here, so both apps only copy it onto the leg. */
export type GameChoice = { matchup: string; sport: string; game_ref: string | null; start: string; event_id: string | null };

/** The games around a slip for its unmatched legs to choose from: from 12 hours before it was placed to 36 hours after,
 *  soonest first. A soccer game's ref needs its league, taken from the slip's soccer legs (none: no ref, it tracks by name). */
export function gameChoices(read: SlipRead, games: Game[], placedAt: string, ufcRefs: Record<string, string> = {}): GameChoice[] {
  const at = Date.parse(placedAt), from = at - 12 * 3600_000, to = at + 36 * 3600_000;
  const soccer = read.legs.find((l) => l.sport === "soccer" && l.soccer_league)?.soccer_league ?? null;
  return games.filter((g) => g.matchup && g.commence_time && Date.parse(g.commence_time) >= from && Date.parse(g.commence_time) <= to)
    .sort((a, b) => String(a.commence_time).localeCompare(String(b.commence_time)))
    .slice(0, 200)
    .map((g) => ({ matchup: g.matchup!, sport: g.league, start: g.commence_time!, event_id: g.odds_event_id ?? null,
      game_ref: gameRef(g, { label: "", matchup: g.matchup!, sport: g.league as SlipRead["legs"][number]["sport"],
                             soccer_league: soccer }, ufcRefs) }));
}

/** A leg put on the game the user chose: that game's matchup, sport, start and ref. Its old prices were for no game. */
export function chooseGame(leg: DraftLeg, c: GameChoice): DraftLeg {
  return { ...leg, matchup: c.matchup, sport: c.sport, game_ref: c.game_ref, start: c.start, matched: true, event_id: c.event_id, prices: undefined };
}
