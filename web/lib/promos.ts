// The promos wallet (Mike, Oct 30: "I don't love how our profit boosts and bonus thing works"; migration 0029): each
// bonus bet or profit boost a book gave, with its terms and expiry, kept on the account. Use opens the finder with it,
// and the bet placed with it marks it used (the database's promo_used trigger; deleting that bet gives it back).
// Pure: the iPhone's Promos.swift is the same, and tests/fixtures/promos.json holds both to it.
import { MARKET_CHOICES, type Promo } from "./builder";
import { fmtAm, toDec } from "./format";
import TEAMS from "./teams.json";

export const marketName = (k: string) => MARKET_CHOICES.find(([m]) => m === k)?.[1] ?? k;

export type PromoRow = {
  promo_id: string; kind: "bonus" | "boost"; book: string | null; amount_dollars: number | null; pct: number | null;
  max_extra_dollars: number | null; min_legs: number | null; min_odds: number | null; max_odds: number | null;
  sports: string[] | null; teams?: string[] | null; market?: string | null; games?: PromoGame[] | null; leg_kinds?: string[] | null;
  note: string | null; expires_at: string | null; status: "open" | "used" | "void";
  source?: "typed" | "screenshot"; created_at?: string;
};
/** A game picked for a token from the schedule (Nov 5, migration 0039): ESPN's row, known days before the odds are. */
export type PromoGame = { event_id: string; matchup: string; commence_time: string; sport?: string };
export type PromoState = "open" | "used" | "void" | "expired";

const num = (v: unknown) => (v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? null : Number(v));

/** Open, used, voided by hand, or expired (an open token past its expiry; worked out here, never stored). */
export function promoState(p: PromoRow, now = new Date()): PromoState {
  if (p.status !== "open") return p.status;
  return p.expires_at && Date.parse(p.expires_at) <= now.getTime() ? "expired" : "open";
}

/** The wallet as shown: open tokens soonest-expiring first (no expiry last), then the rest newest first. */
export function wallet(rows: PromoRow[], now = new Date()): { open: PromoRow[]; done: PromoRow[] } {
  const exp = (p: PromoRow) => (p.expires_at ? Date.parse(p.expires_at) : Infinity);
  const open = rows.filter((p) => promoState(p, now) === "open").sort((a, b) => exp(a) - exp(b) || String(a.created_at).localeCompare(String(b.created_at)));
  const done = rows.filter((p) => promoState(p, now) !== "open")
    .sort((a, b) => String(b.expires_at ?? b.created_at).localeCompare(String(a.expires_at ?? a.created_at)));
  return { open, done };
}

/** Open tokens that expire within `hours` (My bets' "expiring soon" and Home's chip). */
export const expiringSoon = (rows: PromoRow[], now = new Date(), hours = 48) =>
  wallet(rows, now).open.filter((p) => p.expires_at && Date.parse(p.expires_at) - now.getTime() <= hours * 3600_000);

/** The sports a token can be used on, in the finder's names; null for any. Its `sports`, else the sports its note
 *  names (Oct 30: Mike's 50% boost said "NBA Only" in the note, and the finder searched every sport). */
export const SPORT_CHOICES: [string, string][] = [["nfl", "NFL"], ["nba", "NBA"], ["nhl", "NHL"], ["ncaaf", "CFB"],
  ["ncaab", "CBB"], ["soccer", "Soccer"], ["ufc", "UFC"]];
const NOTE_SPORTS: [RegExp, string][] = [
  [/\bcbb\b|\bncaab\b|\bcollege basketball\b|\bncaa basketball\b|\bncaam\b/i, "ncaab"],
  [/\bcollege football\b|\bcfb\b|\bncaaf\b/i, "ncaaf"],
  [/\bnba\b/i, "nba"], [/\bnfl\b/i, "nfl"], [/\bnhl\b|\bhockey\b/i, "nhl"],
  [/\bsoccer\b|\bepl\b|\bpremier league\b|\bla liga\b|\bserie a\b|\bbundesliga\b|\bligue 1\b|\bmls\b|\bchampions league\b|\bucl\b/i, "soccer"],
  [/\bufc\b|\bmma\b/i, "ufc"],
];
export function promoSports(p: Pick<PromoRow, "sports" | "note">): string[] | null {
  if (p.sports?.length) return p.sports;
  const found = NOTE_SPORTS.filter(([re]) => re.test(p.note ?? "")).map(([, s]) => s);
  return found.length ? [...new Set(found)] : null;
}

/** A token for some games only (Oct 31, Mike: "boosts for specific games"): the teams it names, each a game's side.
 *  Typed as "Knicks, Celtics" or "Knicks vs Celtics": split on commas and vs/@ into single teams. */
export function splitTeams(text: string | string[] | null | undefined): string[] | null {
  const parts = (Array.isArray(text) ? text : [text ?? ""]).flatMap((t) => t.split(/,|\s+(?:vs\.?|v\.?|@|at)\s+|\s*\/\s*/i))
    .map((t) => t.trim()).filter(Boolean);
  return parts.length ? [...new Set(parts)] : null;
}
const teamWords = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);

/** Is this game ("Away @ Home") one the token is for? Any of its teams whose words are all in one side's name
 *  ("Knicks" in "New York Knicks", "Ohio State" in "Ohio State Buckeyes"); a token with no teams fits every game. */
export function teamFits(teams: string[] | null | undefined, matchup: string): boolean {
  if (!teams?.length) return true;
  const sides = matchup.split(/\s+@\s+|\s+vs\.?\s+/i).map(teamWords);
  return teams.some((t) => { const w = teamWords(t); return w.length > 0 && sides.some((s) => w.every((x) => s.includes(x))); });
}

/** I used it (Oct 31: Mike's $5 Novig bonus went on a bet saved without the token, and the wallet still offered it):
 *  the bets a token may have gone on. Real ones with no token yet, at its book (any when it names none), from the last
 *  `days`; those already marked as this kind (bonus, or boosted) first, then newest; at most 8. */
export type UsedBet = { bet_id: string; mode: string | null; book?: string | null; bonus?: boolean | null; boost?: number | null;
                        promo_id?: string | null; placed_at: string };
export function usedOnChoices<B extends UsedBet>(p: Pick<PromoRow, "kind" | "book">, bets: B[], now = new Date(), days = 7): B[] {
  const since = now.getTime() - days * 86400_000;
  const flagged = (b: UsedBet) => (p.kind === "bonus" ? b.bonus === true : b.boost != null);
  return bets.filter((b) => b.mode === "real" && !b.promo_id && (!p.book || b.book === p.book) && Date.parse(b.placed_at) >= since)
    .sort((a, b) => Number(flagged(b)) - Number(flagged(a)) || b.placed_at.localeCompare(a.placed_at)).slice(0, 8);
}

/** The token as the finder takes it (lib/builder.ts Promo): dollars, the boost's cap, legs and odds. */
export function asPromo(p: PromoRow): Promo {
  const terms = { stake: num(p.amount_dollars) ?? undefined, minLegs: num(p.min_legs) ?? undefined,
    minOdds: num(p.min_odds) ?? undefined, maxOdds: num(p.max_odds) ?? undefined, market: p.market ?? undefined,
    kinds: p.leg_kinds?.length ? p.leg_kinds : undefined };
  return p.kind === "boost"
    ? { kind: "boost", pct: num(p.pct) ?? 0, maxExtra: num(p.max_extra_dollars) ?? undefined, ...terms }
    : { kind: "bonus", ...terms };
}

/** The words of a side, a code read as its team's name: the NHL's packs say "CGY @ SEA" and the schedule "Calgary Flames @ ...". */
function sideWords(side: string): string[] {
  const code = side.trim().toUpperCase();
  const row = Object.values(TEAMS as unknown as Record<string, { name: string; abbr: string[] }[]>).flat().find((t) => t.abbr.includes(code));
  return teamWords(row ? row.name : side);
}
/** The same game, written two ways (ESPN's schedule, the odds feed's pack): within 3 hours, with a side in common; a team doesn't
 *  play twice in 3 hours. One side is enough, since clubs go by different names ("Inter", "Internazionale"). */
export function sameGame(a: { matchup: string; start: string }, b: { matchup: string; start: string }): boolean {
  if (Math.abs(Date.parse(a.start) - Date.parse(b.start)) > 3 * 3600_000) return false;
  const split = (m: string) => m.split(/\s+@\s+|\s+vs\.?\s+/i).map(sideWords).filter((w) => w.length);
  const inside = (x: string[], y: string[]) => x.every((w) => y.includes(w));
  return split(a.matchup).some((x) => split(b.matchup).some((y) => inside(x, y) || inside(y, x)));
}

/** Is this game one the token is for? Its picked games and its teams' games both count; a token with neither fits any game. */
export function tokenFitsGame(p: Pick<PromoRow, "teams" | "games">, eventId: string, matchup: string, start = ""): boolean {
  if (!p.games?.length && !p.teams?.length) return true;
  return !!p.games?.some((g) => g.event_id === eventId || (!!start && sameGame({ matchup: g.matchup, start: g.commence_time }, { matchup, start })))
    || (!!p.teams?.length && teamFits(p.teams, matchup));
}

/** The wager on a token (Nov 3: not always its max): what was typed, at most its max; blank or nonsense is the max. Shared
 *  cases: tests/fixtures/promos.json. */
export function wagerOf(typed: string, max: number | null | undefined): number | undefined {
  const n = Number(typed), m = max != null && max > 0 ? max : undefined;
  return typed.trim() && n > 0 ? (m ? Math.min(n, m) : n) : m;
}

/** What's left of a bonus bet after this wager, in cents; it stays in the wallet as its own token. A boost has none: it's used once. */
export function bonusLeft(face: number | null | undefined, wager: number): number {
  const left = Math.round(((face ?? 0) - wager) * 100) / 100;
  return left >= 0.01 ? left : 0;
}

const dollars = (n: number) => `$${Number.isInteger(n) ? n : n.toFixed(2)}`;

/** "$50 bonus bet", "30% profit boost": what the token is, in the book's words. */
export function promoTitle(p: PromoRow): string {
  const amt = num(p.amount_dollars);
  if (p.kind === "bonus") return `${amt ? `${dollars(amt)} ` : ""}bonus bet`;
  return `${num(p.pct) ?? "?"}% profit boost`;
}

/** Its terms in one line: "up to $25 · max $10 extra · 3+ legs · -200 or longer · NFL". */
export function promoTerms(p: PromoRow): string {
  const parts: string[] = [];
  const amt = num(p.amount_dollars), cap = num(p.max_extra_dollars), legs = num(p.min_legs);
  const lo = num(p.min_odds), hi = num(p.max_odds);
  if (p.kind === "boost" && amt) parts.push(`up to ${dollars(amt)}`);
  if (cap) parts.push(`max ${dollars(cap)} extra`);
  if (legs && legs > 1) parts.push(`${legs}+ legs`);
  if (lo !== null && hi !== null) parts.push(`${fmtAm(lo)} to ${fmtAm(hi)}`);
  else if (lo !== null) parts.push(`${fmtAm(lo)} or longer`);
  else if (hi !== null) parts.push(`${fmtAm(hi)} or shorter`);
  const sp = promoSports(p);
  if (sp?.length) parts.push(sp.map((s) => SPORT_CHOICES.find(([k]) => k === s)?.[1] ?? s.toUpperCase()).join(", "));
  if (p.market) parts.push(marketName(p.market));
  if (p.leg_kinds?.length) parts.push(`${p.leg_kinds.map(legKindName).join(" or ")} only`);
  if (p.games?.length) parts.push(p.games.map((g) => g.matchup).join(", "));
  if (p.teams?.length) parts.push(`${p.teams.join(", ")} games`);
  return parts.join(" · ");
}

/** "expires in 5 h", "expires today 11:59 PM", "expires Sun", "expired Oct 28", or "" with no expiry. */
export function expiresText(p: PromoRow, now = new Date()): string {
  if (!p.expires_at) return "";
  const t = new Date(p.expires_at), ms = t.getTime() - now.getTime();
  const day = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  if (ms <= 0) return `expired ${t.toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" })}`;
  if (ms < 12 * 3600_000) return `expires in ${Math.max(1, Math.round(ms / 3600_000))} h`;
  if (day(t) === day(now)) return `expires today ${t.toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" })}`;
  if (ms < 6 * 86400_000) return `expires ${t.toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "short" })}`;
  return `expires ${t.toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" })}`;
}

/** A sports list as the finder's keys (nfl, nba, nhl, ncaaf, ncaab, soccer, ufc): typed or read as "NFL ", "CFB" or "College
 *  Football" (Nov 9: the reader's free text was saved as is, and a token for "cfb" made the finder search no games). Anything
 *  else is dropped; none left is null (any sport). */
export function cleanSports(list: unknown): string[] | null {
  const keys = SPORT_CHOICES.map(([k]) => k), out: string[] = [];
  for (const raw of Array.isArray(list) ? list : []) {
    const s = String(raw ?? "").trim().toLowerCase();
    const hit = keys.includes(s) ? [s] : NOTE_SPORTS.filter(([re]) => re.test(s)).map(([, k]) => k);
    for (const k of hit) if (!out.includes(k)) out.push(k);
  }
  return out.length ? out : null;
}

/** The kinds of leg a token can be for (Nov 9, Mike: "boosts like td only or first td only"; migration 0047), in the Build
 *  packs' stat names, so the finder tests each candidate leg (builder.marketFits). Every leg of the bet must be one of them.
 *  "first_td" is kept and shown, but no pack prices a first TD, so the finder says it can't build one (`unpricedKinds`). */
export const LEG_CHOICES: [string, string][] = [["tds", "Anytime TD"], ["first_td", "First TD"], ["passing_yards", "Passing yards"],
  ["rushing_yards", "Rushing yards"], ["receiving_yards", "Receiving yards"], ["receptions", "Receptions"], ["points", "Points"],
  ["rebounds", "Rebounds"], ["assists", "Assists"], ["threes", "Threes"], ["pra", "Pts + reb + ast"], ["shots", "Shots"],
  ["saves", "Saves"], ["goals", "Goals"]];
const UNPRICED_KINDS = ["first_td"];
export const legKindName = (k: string) => LEG_CHOICES.find(([x]) => x === k)?.[1] ?? k;
/** A leg-kinds list as LEG_CHOICES keys ("anytime td" and "TD scorer" read as tds); anything else dropped, none left is null. */
export function cleanKinds(list: unknown): string[] | null {
  const out: string[] = [];
  for (const raw of Array.isArray(list) ? list : []) {
    const s = String(raw ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
    const k = LEG_CHOICES.some(([x]) => x === s) ? s : /first_?(td|touchdown)/.test(s) ? "first_td"
      : /(anytime_)?(td|touchdown)(_scorer)?s?$/.test(s) ? "tds" : null;
    if (k && !out.includes(k)) out.push(k);
  }
  return out.length ? out : null;
}
/** The kinds a token allows that no pack prices: all of them means the finder can't build a bet for it. */
export const unpricedKinds = (p: Pick<PromoRow, "leg_kinds">) => (p.leg_kinds ?? []).filter((k) => UNPRICED_KINDS.includes(k));

/** A token read with teams as the game they play (Nov 9, Mike: "it should've assigned it to only Bills vs Vikings, not just
 *  write those teams in"): when two of its teams meet on the schedule before it ends, those games are the token's (the next
 *  meeting of each pair), its sports come from them, and the team names go. One team ("any Ohio State bet") stays a team.
 *  Shared cases: tests/fixtures/promos.json `team_games`. */
export function teamGames<T extends Partial<PromoRow>>(d: T, schedule: PromoGame[], now = new Date()): T {
  const teams = splitTeams(d.teams) ?? [];
  if (teams.length < 2 || d.games?.length) return d;
  const end = d.expires_at ? Date.parse(d.expires_at) : Infinity, from = now.getTime() - 4 * 3600_000;
  const hits = schedule
    .filter((g) => { const t = Date.parse(g.commence_time); return t >= from && t <= end; })
    .filter((g) => !d.sports?.length || !g.sport || d.sports.includes(g.sport))
    .filter((g) => teams.filter((t) => teamFits([t], g.matchup)).length >= 2)
    .sort((a, b) => a.commence_time.localeCompare(b.commence_time));
  const first = new Map<string, PromoGame>();
  for (const g of hits) {
    const pair = teams.filter((t) => teamFits([t], g.matchup)).sort().join("|");
    if (!first.has(pair)) first.set(pair, g);
  }
  if (!first.size) return d;
  const games = [...first.values()];
  const sports = [...new Set([...(d.sports ?? []), ...games.flatMap((g) => (g.sport ? [g.sport] : []))])];
  return { ...d, games, teams: null, sports: sports.length ? sports : null };
}

/** A read boost's expiry (Mike, Nov 9: "a boost's expiry should default to the day before it expires at 11:59pm, unless it's
 *  for a game then it should expire 5 mins after that game time"): a boost for certain games ends 5 minutes after the last one
 *  starts; any other boost at 11:59 PM Eastern the day before the date it shows ("Exp: 12h 31m" landing at midnight is 11:59 PM
 *  tonight). A bonus bet keeps what it shows. Shared cases: tests/fixtures/promos.json `boost_expiry`. */
export function boostExpiry<T extends Partial<PromoRow>>(d: T): T {
  if (d.kind !== "boost") return d;
  const starts = (d.games ?? []).map((g) => Date.parse(g.commence_time)).filter(Number.isFinite);
  if (starts.length) return { ...d, expires_at: etIso(Math.max(...starts) + 5 * 60_000) };
  const shown = etExpiry(d.expires_at);
  if (!shown) return d;
  const day = new Date(Date.parse(`${shown.slice(0, 10)}T12:00:00Z`) - 86400_000).toISOString().slice(0, 10);
  return { ...d, expires_at: etExpiry(`${day}T23:59:00`) };
}

/** Each screenshot's book in a batch (later Nov 9: a batch of FanDuel boosts came back with other books). A screenshot whose
 *  book's name or logo shows keeps it. When the batch's named screenshots agree on one book, the rest (guessed from the look,
 *  or not told) take it; with none named, an untold one takes the batch's most-guessed book, else the account's only book on
 *  (`mine`). Shared cases: tests/fixtures/promos.json `shot_books`. */
export type ShotBook = { book: string | null; from: "name" | "look" | "unknown" };
export function shotBooks(shots: ShotBook[], mine: string[] = []): (string | null)[] {
  const named = [...new Set(shots.filter((s) => s.from === "name" && s.book).map((s) => s.book!))];
  const guessed = shots.filter((s) => s.from === "look" && s.book).map((s) => s.book!);
  const most = guessed.length ? guessed.sort((a, b) => guessed.filter((x) => x === b).length - guessed.filter((x) => x === a).length)[0] : null;
  const only = mine.length === 1 ? mine[0] : null;
  return shots.map((s) => {
    if (s.from === "name" && s.book) return s.book;
    if (named.length === 1) return named[0];
    if (named.length > 1) return s.book ?? only;
    return s.book ?? most ?? only;
  });
}


const ET = "America/New_York";
/** New York's offset from UTC at this instant, in minutes (-240 in summer, -300 in winter). */
function etOffset(ms: number): number {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: ET, hourCycle: "h23", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return Math.round((Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) - Math.floor(ms / 1000) * 1000) / 60000);
}
/** An instant written in Eastern time with its offset: "2026-11-09T23:59:00-05:00". */
export function etIso(ms: number): string {
  const off = etOffset(ms), t = new Date(Math.floor(ms / 1000) * 1000 + off * 60000), a = Math.abs(off);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${t.getUTCFullYear()}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())}T${pad(t.getUTCHours())}:${pad(t.getUTCMinutes())}:${pad(t.getUTCSeconds())}`
    + `${off < 0 ? "-" : "+"}${pad(Math.floor(a / 60))}:${pad(a % 60)}`;
}
/** A token's expiry as both apps take it, in Eastern time with its offset (Nov 9). A time with a zone is that instant; one without
 *  is Eastern wall time (the reader may leave the zone off, and the server runs in UTC, which read it 4-5 hours early); a bare
 *  date is 11:59 PM Eastern that day, as the books mean "Expires 11/01". Null when it isn't a time. */
export function etExpiry(v: unknown): string | null {
  if (v == null || v === "") return null;
  const s = String(v).trim();
  let ms: number;
  if (/T.*(?:z|[+-]\d{2}:?\d{2})$/i.test(s)) ms = Date.parse(s);
  else {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(s.replace(/\.\d+$/, ""));
    if (!m) return null;
    const wall = Date.UTC(+m[1], +m[2] - 1, +m[3], m[4] ? +m[4] : 23, m[5] ? +m[5] : 59, m[6] ? +m[6] : 0);
    ms = wall - etOffset(wall - etOffset(wall) * 60000) * 60000;     // the offset of the instant itself, around a clock change
  }
  return Number.isFinite(ms) ? etIso(ms) : null;
}

const BOOK_NAMES = ["FanDuel", "DraftKings", "Novig"];
/** A typed or read token in the database's shape, every field cleaned but nothing refused (cleanPromo refuses). */
function normPromo(d: Partial<PromoRow>): Omit<PromoRow, "promo_id" | "status"> {
  const kind = d.kind === "boost" ? "boost" : "bonus";
  const pct = num(d.pct), amt = num(d.amount_dollars), cap = num(d.max_extra_dollars), legs = num(d.min_legs);
  const odds = (v: unknown) => { const n = num(v); return n !== null && Math.abs(n) >= 100 ? n : null; };
  const book = d.book?.trim() || null;
  return {
    kind, book: BOOK_NAMES.find((b) => b.toLowerCase() === book?.toLowerCase()) ?? book, amount_dollars: amt !== null && amt > 0 ? amt : null,
    pct: kind === "boost" && pct !== null && pct > 0 ? pct : null,
    max_extra_dollars: kind === "boost" && cap && cap > 0 ? cap : null,
    min_legs: legs && legs >= 1 && legs <= 20 ? Math.round(legs) : null, min_odds: odds(d.min_odds), max_odds: odds(d.max_odds),
    sports: cleanSports(d.sports),
    teams: splitTeams(d.teams),
    market: MARKET_CHOICES.some(([k]) => k === d.market) ? d.market! : null,
    games: d.games?.length ? d.games.map((g) => ({ event_id: g.event_id, matchup: g.matchup, commence_time: g.commence_time, ...(g.sport ? { sport: g.sport } : {}) })) : null,
    leg_kinds: cleanKinds(d.leg_kinds),
    note: d.note?.trim() || null, expires_at: etExpiry(d.expires_at), source: d.source === "screenshot" ? "screenshot" : "typed",
  };
}

/** A typed or read token, checked before it's saved: null and a reason when it can't be one. The iPhone's Promos.clean is the
 *  same (tests/fixtures/promos.json `clean`). */
export function cleanPromo(d: Partial<PromoRow>): { row: Omit<PromoRow, "promo_id" | "status"> | null; error?: string } {
  const kind = d.kind === "boost" ? "boost" : d.kind === "bonus" ? "bonus" : null;
  if (!kind) return { row: null, error: "Pick bonus bet or profit boost." };
  const pct = num(d.pct), amt = num(d.amount_dollars);
  if (kind === "boost" && !(pct && pct > 0 && pct <= 500)) return { row: null, error: "A boost needs its size, 1 to 500%." };
  if (kind === "bonus" && !(amt && amt > 0)) return { row: null, error: "A bonus bet needs its dollar amount." };
  if (amt !== null && amt <= 0) return { row: null, error: "Dollars must be above 0." };
  return { row: normPromo({ ...d, kind }) };
}

/** A token read off a screenshot, as /api/promos sends it to both apps (Nov 9): cleaned as it would be saved, with the id and
 *  status the iPhone's row needs ("" and open) and the expiry in Eastern time with its offset. One cleanPromo would refuse keeps
 *  what could be read and says why (`problem`), to fix before it's kept. */
export type PromoDraft = PromoRow & { problem: string | null };
export function promoDraft(d: Partial<PromoRow>): PromoDraft {
  const read = { ...d, source: "screenshot" as const };
  const { row, error } = cleanPromo(read);
  return { ...(row ?? normPromo(read)), promo_id: "", status: "open", problem: error ?? null };
}

/** Can this token go on a bet now? Null when it can, else why not (Nov 9: placing never checked, so a used token could go on a
 *  second bet). Web placePromo, usedPromo and the slip reader; the iPhone's Promos.usable. */
export function promoUsable(p: Pick<PromoRow, "status" | "expires_at"> | null | undefined, now = new Date()): string | null {
  if (!p) return "That promo is gone.";
  const s = promoState(p as PromoRow, now);
  return s === "open" ? null : s === "used" ? "That promo is already used." : s === "expired" ? "That promo has ended."
    : "That promo is set aside: bring it back first.";
}

/** A slip read from a screenshot (Nov 9): the open wallet tokens it may have used. Only a bonus bet or a boosted slip has one;
 *  the token's kind and book (any when it names none) must match, a boost's size too when both say it, and the slip must sit
 *  inside its terms: the wager at most its dollars, its fewest legs, its odds. An exact dollar match first, then soonest to end.
 *  The draft preselects one only when exactly one fits (`slipToken`). The iPhone's Promos.slipTokens is the same. */
export type SlipForToken = { book: string; bonus: boolean; boost_pct: number | null; stake_dollars: number; price?: number | null; legs?: number | null };
export function slipTokens(s: SlipForToken, rows: PromoRow[], now = new Date()): PromoRow[] {
  const kind = s.bonus ? "bonus" : s.boost_pct ? "boost" : null;
  if (!kind) return [];
  const dec = s.price != null && Math.abs(s.price) >= 100 ? toDec(s.price) : null;
  const fits = (p: PromoRow) => {
    const amt = num(p.amount_dollars), pct = num(p.pct), legs = num(p.min_legs), lo = num(p.min_odds), hi = num(p.max_odds);
    return p.kind === kind && (!p.book || p.book === s.book)
      && (kind !== "boost" || pct === null || Math.abs(pct - (s.boost_pct ?? 0)) < 0.01)
      && (amt === null || s.stake_dollars <= amt + 0.004)
      && (legs === null || s.legs == null || s.legs >= legs)
      && (dec === null || ((lo === null || dec >= toDec(lo) - 1e-9) && (hi === null || dec <= toDec(hi) + 1e-9)));
  };
  const exact = (p: PromoRow) => Math.abs((num(p.amount_dollars) ?? -1) - s.stake_dollars) < 0.005;
  const open = wallet(rows, now).open.filter(fits);
  return [...open.filter(exact), ...open.filter((p) => !exact(p))];
}
/** The token to preselect on a slip: the one that fits, when only one does. */
export function slipToken(s: SlipForToken, rows: PromoRow[], now = new Date()): PromoRow | null {
  const t = slipTokens(s, rows, now);
  return t.length === 1 ? t[0] : null;
}
