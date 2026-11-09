import { showsWatched, watchedLocks } from "./watch";
import "server-only";
import { readFile } from "node:fs/promises";
import { OWNER_USER_ID } from "./owner";
import type { Friendship, Profile, Reaction } from "./social";
import path from "node:path";
import { fixtureMode } from "./mode";
import { supabaseServer } from "./supabase/server";
import { bucketUsed, gameStart, isSettled, profit, recordBets, refGameId, refTime, startOf, statusOf } from "./bets";
import { isReal } from "./real";
import { upcomingLocks, type LockSlate } from "./locks";
import { headshot } from "./headshots";
import { searchBets, searchTeams, type SearchTeam } from "./search";
import type { DeviceSession } from "./devices";
import TEAMS from "./teams.json";
import { addDays, etDay, etStart, window, type DayKey } from "./time";
import type { QuoteModel } from "./builder";
import { cleanBans, isBanned, ticketBanned, type Ban } from "./bans";
import type { Ladder } from "./ladder";
import { atBooks, onBooks, type BookRead } from "./books";

// ------------------------------------------------------------------------------------- types

export type Game = {
  game_id: string; league: string; odds_event_id: string | null; home: string | null; away: string | null;
  matchup: string | null; commence_time: string | null; state: string | null;
  home_score: number | null; away_score: number | null;
};
export type Offer = {
  offer_id: string; tier: "pick" | "lean" | "check"; league: string; game_id: string | null; commence_time: string | null;
  matchup: string | null; market: string | null; kind: string | null; side: string | null; player: string | null;
  label: string; point: number | null; price: number; book: string | null; p_model: number | null; p_market: number | null;
  p_final: number | null; ev: number | null; units_flat: number | null; units_tier: number | null; units_kelly: number | null;
  market_source: string | null; why: string | null; context: string | null; fd_url: string | null;
  other_book?: string | null; other_point?: number | null; other_price?: number | null; other_ev?: number | null;
  bet_limit?: number | null;   // Novig: the dollars available at this price (Oct 22)
  books?: BookRead[] | null;   // every book's own read (books.per_book, Nov 6): shown at an account's books (atBooks)
  link_main?: boolean | null;
};
export type Leg = { label: string; price?: number; p_fair?: number; fair_price?: number; p_read?: number; read?: string;
  source?: string; questionable?: string | null; note?: string; link?: string; p_model_raw?: number;
  link_main?: boolean;   // its link is the main market's, whose line can move (links.Matcher.main_links, Oct 30)
  // DraftKings' side (Oct 12, links.attach_dk): its price and link; a rung it doesn't hang moves to its nearest one
  dk_price?: number; dk_link?: string; dk_point?: number; dk_label?: string; dk_moved?: boolean; dk_link_main?: boolean;
  // Novig's side (Oct 28, novig_parlays.attach): its outcome id, and its price when $50+ stands behind it
  nv_id?: string; nv_price?: number };
/** A slip's DraftKings side: legs it posts, its legs' product and likely quote (FanDuel's pattern until ~40 DK quotes). */
export type DkSide = { legs: number; of: number; moved?: number; naive_price?: number | null; likely_price?: number | null; stand_in?: boolean };
/** A slip's Novig side (Oct 28): legs Novig lists and, when it lists them all, its exact price from Novig's parlay pricer,
 *  the largest stake its market maker takes and the whole slip as one link; `refused` when no market maker priced it. */
export type NvSide = { legs: number; of: number; price?: number; p?: number; payout_max?: number | null; stake_max?: number | null;
  link?: string; priced_at?: string; refused?: boolean };
export type Ticket = {
  sgp_id: string; kind: "sgp" | "sgp_plus" | "td" | "over"; sport: string; game_id: string | null; slate: string | null;
  matchup: string | null; commence_time: string | null; fair_price: number | null; p_fair: number | null;
  naive_price: number | null; price: number | null; status: string | null;
  body: { theme?: string; story?: string; why?: string; legs?: Leg[]; games?: { matchup: string; commence_time: string; legs: Leg[]; fair_price?: number; event_id?: string }[];
    lift?: number; longshot?: boolean; style?: string; cup?: string; likely_price?: number; dk?: DkSide; nv?: NvSide; fits_read?: number; read_price?: number; label?: string; ev?: number; ev_read?: number;
    read?: string; note?: string; link?: string; link_main?: boolean; n_games?: number; n_legs?: number; event_id?: string; sport?: string };
};
export type Slate = { slate: string; sport: string; kickoff: string; n_games: number; label: string;
  title?: string; locked_at?: string | null;
  side_note?: { title: string; text: string } | null; lines_only?: boolean; ticket_ids: string[] };
export type Bet = {
  bet_id: string; kind: "pick" | "lean" | "parlay" | "custom"; pick_id: string | null; sgp_id: string | null;
  mode: "paper" | "real"; price: number | null; stake: number | null; label: string | null; matchup: string | null;
  book?: string | null;   // where it was (or will be) placed: FanDuel or DraftKings (Oct 12)
  bonus?: boolean;        // a bonus bet: the stake is the book's credit, not cash (migration 0012, Oct 19)
  cashout?: number | null; // cashed out early: what the book paid back, in units (migration 0014, Oct 22)
  boost?: number | null;   // a profit boost in percent: price is the book's own, a win's profit x (1 + boost/100) (0015)
  ladder_id?: string | null; // a ladder challenge's step (0020, Oct 26: lib/ladder.ts)
  protect?: boolean;         // FanDuel Bet Protect+ (0023, Oct 26): a 3% fee, and a leg on a player who sits counts as won
  reset?: boolean;           // a bet reset (0031, Nov 1): if it loses, the stake comes back as a bonus bet in the wallet
  boost_cap?: number | null; // the most extra winnings the boost adds, in units (0029, Oct 30: a capped boost counted uncapped)
  promo_id?: string | null;  // the wallet token this bet used (0029: lib/promos.ts)
  lock_id?: string | null;   // a two-book lock's two bets share it (0029)
  promo_ev?: number | null;  // the token's expected dollars when placed, the finder's number (0029)
  user_id?: string;          // whose bet: a friend's in the feed (0024, Oct 27); your own otherwise
  placed_at: string; pick_status?: string | null; ticket_status?: string | null;
};
/** A bet with what it was on (the my_bets view): the paper pick's or ticket's grading and market. */
export type MyBet = Bet & {
  fair_price: number | null; p_fair: number | null; legs: string[] | null; odds_event_id: string | null;
  profit_flat: number | null; clv: number | null; clv_raw: number | null; pick_commence_time: string | null;
  profit_1u: number | null; ticket_commence_time: string | null; grade: string | null; league: string | null;
  market: string | null; pick_kind: string | null; ev: number | null; close_price: number | null;
  logged_price?: number | null; close_push?: number | null; // migration 0004; older fixtures may omit these
  leg_results: { leg: string; result: string; value?: number | null }[] | null; ticket_kind: string | null; sport: string | null;
  live_settled?: "won" | "lost";   // settled from the live tracker before the worker grades it (lib/live-bets.ts)
  slip_p?: number | null;           // a slip's fair chance when it was read (slip_prices, Nov 4)
  clv_now?: number | null;          // live CLV on an open bet (bet_clv, Oct 28): your price against the sharp chance now
  clv_at?: string | null;
  games?: { matchup: string; game_ref?: string; legs: string[] }[] | null;   // a custom bet's games (each with its legs)
  game_start?: string | null;     // a custom bet's first kickoff, from its games (myBetsData, Oct 25): its time order
  game_starts?: Record<string, string>;   // its games' kickoffs by the games table's id (withStarts): the tracker's days
};
export type QuoteRow = { sgp_id: string; price: number; fair_price: number | null; naive_price: number | null; p_fair: number | null;
  n_legs: number | null; legs: string[] | null; matchup: string | null; sport: string | null; quoted_at: string;
  games?: { matchup: string; game_ref?: string | null; legs: string[] }[] | null };
export type CustomParlay = QuoteRow & { grade: string | null; status: string | null; profit_1u: number | null };
export type Quote = { sgp_id: string; price: number; quoted_at: string };
export type Analysis = Record<string, any>;     // the per-game bodies built by the Python side (jsonb)

// ------------------------------------------------------------------------------------ source

type Fixture = Record<string, any[]> & { dumped_at?: string };
let fixtureCache: { at: number; data: Fixture } | null = null;

async function fixture(): Promise<Fixture> {
  if (fixtureCache && Date.now() - fixtureCache.at < 5_000) return fixtureCache.data;
  // turbopackIgnore: a dev-only read; without it the production bundle would trace the whole project
  const file = path.resolve(/* turbopackIgnore: true */ process.cwd(), process.env.BETLAB_FIXTURE || "fixtures/today.json");
  const data = JSON.parse(await readFile(file, "utf8")) as Fixture;
  fixtureCache = { at: Date.now(), data };
  return data;
}

/** The promos wallet (More > Promos, Oct 30; migration 0029): every token the account has added. */
export async function promosData(): Promise<import("./promos").PromoRow[]> {
  if (fixtureMode()) return [...((await fixture()).promos ?? []), ...fixtureWrites.promos] as import("./promos").PromoRow[];
  const sb = await supabaseServer();
  const { data } = await sb.from("promos").select("*").order("created_at", { ascending: false });
  return (data ?? []) as import("./promos").PromoRow[];
}

/** The next week of games from the schedule, for a promo's games (Nov 5: the odds packs only know a game about an hour out). */
export async function promoSchedule(): Promise<import("./promos").PromoGame[]> {
  const now = new Date();
  const list = await rows<ScheduleRow>("schedule_games", { from: ["start", now.toISOString()], to: ["start", new Date(now.getTime() + 8 * 864e5).toISOString()] });
  return list.sort((a, b) => a.start.localeCompare(b.start)).map((g) => ({ event_id: g.id, matchup: g.matchup, commence_time: g.start, sport: g.sport }));
}

/** Today's DFS slates (Me > Extras > DFS lineups, Nov 5). */
export async function dfsData(): Promise<import("./dfs").DfsSlate[]> {
  return rows<import("./dfs").DfsSlate>("dfs_slates");
}

/** This week's College Football Pick'em entry (Me > Extras > Pick'em, Nov 7), in screen order; the fixture's `pickem` locally. */
export async function pickemData(week: string): Promise<import("./pickem").PickemRow[]> {
  if (fixtureMode()) return ((await fixture()).pickem ?? []).filter((r) => r.week === week) as import("./pickem").PickemRow[];
  const sb = await supabaseServer();
  const { data } = await sb.from("pickem").select("*").eq("week", week).order("n");
  return (data ?? []) as import("./pickem").PickemRow[];
}

/** Past pick'em weeks (the last 20 weeks' rows and outcomes), newest first. */
export async function pickemHistoryData(week: string): Promise<{ rows: import("./pickem").PickemRow[]; weeks: import("./pickem").PickemWeek[] }> {
  if (fixtureMode()) return { rows: ((await fixture()).pickem ?? []).filter((r) => r.week !== week) as import("./pickem").PickemRow[], weeks: [] };
  const sb = await supabaseServer();
  const [{ data: rows }, { data: weeks }] = await Promise.all([
    sb.from("pickem").select("*").lt("week", week).order("week", { ascending: false }).order("n").limit(200),
    sb.from("pickem_weeks").select("*").order("week", { ascending: false }).limit(20),
  ]);
  return { rows: (rows ?? []) as import("./pickem").PickemRow[], weeks: (weeks ?? []) as import("./pickem").PickemWeek[] };
}

/** Today's Novig challenges (More > Novig challenges, Oct 28), oldest first; the fixture's `challenges` locally. */
export async function challengesData(day: string): Promise<import("./challenges").Challenge[]> {
  if (fixtureMode()) return ((await fixture()).challenges ?? []).filter((c) => c.day === day) as import("./challenges").Challenge[];
  const sb = await supabaseServer();
  const { data } = await sb.from("challenges").select("*").eq("day", day).order("created_at");
  return (data ?? []) as import("./challenges").Challenge[];
}

/** The last 6 weeks of Novig challenges and the Novig sync's bets they became (status, profit in units): History. */
export async function challengeHistoryData(today: string) {
  const { challengeHistory } = await import("./challenges");
  const since = addDays(today, -42);
  if (fixtureMode()) return challengeHistory(((await fixture()).challenges ?? []) as import("./challenges").Challenge[], [], today);
  const sb = await supabaseServer();
  const [{ data: rows }, { data: bets }] = await Promise.all([
    sb.from("challenges").select("*").gte("day", since).order("created_at"),
    sb.from("my_bets").select("*").like("sgp_id", "novig-%").gte("placed_at", etStart(since).toISOString()),
  ]);
  return challengeHistory((rows ?? []) as import("./challenges").Challenge[],
    ((bets ?? []) as MyBet[]).map((b) => ({ sgp_id: b.sgp_id, status: statusOf(b), profit: profit(b) })), today);
}

/** Fixture mode keeps bets and quotes in memory for the dev server's life (never written anywhere). */
export const fixtureWrites = { bets: [] as Bet[], quotes: [] as Quote[], customs: [] as Record<string, unknown>[],
  todos: [] as Todo[], settings: null as Settings | null, ladders: [] as Ladder[],
  profiles: [] as Profile[], friendships: [] as Friendship[], socialSeeded: false,
  promos: [] as import("./promos").PromoRow[], reactions: [] as Reaction[] };

type Filter = { eq?: [string, unknown][]; inList?: [string, unknown[]]; from?: [string, string]; to?: [string, string]; active?: boolean };

async function rows<T>(table: string, f: Filter = {}): Promise<T[]> {
  if (fixtureMode()) {
    // A preview fixture may carry sample personal rows (my_bets, quotes, custom_parlays); marks made
    // in the preview add to them in memory.
    const fx = await fixture();
    const all = table === "bets" || table === "my_bets" ? [...(fx.my_bets ?? []), ...fixtureWrites.bets]
      : table === "quotes" ? [...(fx.quotes_rows ?? []), ...fixtureWrites.quotes]
      : table === "todos" ? [...(fx.todos ?? []).filter((r: any) => !fixtureWrites.todos.some((c) => c.id === r.id)), ...fixtureWrites.todos]
      : table === "user_settings" ? (fixtureWrites.settings ? [fixtureWrites.settings] : fx.user_settings ?? [])
      : table === "custom_parlays" ? [...(fx.custom_parlays ?? []).filter((r: any) => !fixtureWrites.customs.some((c) => c.sgp_id === r.sgp_id)),
                                     ...fixtureWrites.customs] : fx[table] ?? [];
    const hit = (all as any[]).filter((r) =>
      (f.eq ?? []).every(([k, v]) => r[k] === v)
      && (!f.inList || f.inList[1].includes(r[f.inList[0]]))
      && (!f.from || (r[f.from[0]] && Date.parse(r[f.from[0]]) >= Date.parse(f.from[1])))
      && (!f.to || (r[f.to[0]] && Date.parse(r[f.to[0]]) < Date.parse(f.to[1])))
      && (f.active === undefined || r.active === f.active)) as T[];
    return (table === "offers" ? await forMyBooks(hit) : hit) as T[];
  }
  const sb = await supabaseServer();
  let q = sb.from(table).select("*");
  for (const [k, v] of f.eq ?? []) q = q.eq(k, v as never);
  if (f.inList) q = q.in(f.inList[0], f.inList[1] as never[]);
  if (f.from) q = q.gte(f.from[0], f.from[1]);
  if (f.to) q = q.lt(f.to[0], f.to[1]);
  if (f.active !== undefined) q = q.eq("active", f.active);
  const { data, error } = await q.limit(5000);
  if (error) throw new Error(`${table}: ${error.message}`);
  return (table === "offers" ? await forMyBooks(data ?? []) : data ?? []) as T[];
}

/** The signed-in account's books off (user_settings.books_off, 0043; none when unknown). */
export async function booksOff(): Promise<string[]> {
  try {
    return (await settingsData()).books_off ?? [];
  } catch { return []; }
}

/** Every offer at the account's books (lib/books.ts atBooks): moved to a book that's on, or gone (Nov 6). */
async function forMyBooks(list: unknown[]): Promise<unknown[]> {
  const off = await booksOff();
  if (onBooks(off).length === 3) return list;
  return (list as Offer[]).map((o) => atBooks(o, off)).filter((o): o is Offer => o !== null);
}

async function doc<T>(collection: string, id: string): Promise<T | null> {
  const r = await rows<{ body: T }>("docs", { eq: [["collection", collection], ["doc_id", id]] });
  return r[0]?.body ?? null;
}

// ------------------------------------------------------------------------------------- pages

export type FeedGame = Game & { offers: Offer[]; tickets: Ticket[] };
export type FeedItem = { kind: "game"; at: string; game: FeedGame } | { kind: "ticket"; at: string; ticket: Ticket; slate: Slate | null };

const TIER = { pick: 0, lean: 1, check: 2 } as const;

/** The offers and tickets with no bet on a banned player or team (lib/bans.ts). */
export function unbanned(offers: Offer[], tickets: Ticket[], bans: Ban[]) {
  if (!bans.length) return { offers, tickets };
  return { offers: offers.filter((o) => !isBanned(bans, o.label, o.league, o.player)),
           tickets: tickets.filter((t) => !ticketBanned(bans, t.body, t.sport)) };
}
const byEv = (a: Offer, b: Offer) => TIER[a.tier] - TIER[b.tier] || (b.ev ?? 0) - (a.ev ?? 0);

/** Home: what's worth doing in a day window, across sports, by start time. */
export async function homeData(day: DayKey, sport: string | null) {
  const { from, to } = window(day);
  const range = { from: ["commence_time", from.toISOString()] as [string, string], to: ["commence_time", to.toISOString()] as [string, string] };
  const [games, allOffers, allTickets, slatesDoc, bets, cardMeta, settings] = await Promise.all([
    rows<Game>("games", range),
    rows<Offer>("offers", { ...range, active: true }),
    rows<Ticket>("fun_tickets", { ...range, active: true }),
    doc<{ slates: Slate[] }>("fun", "slates"),
    rows<Bet>("my_bets"),
    doc<{ generated_at?: string; notes?: string[] }>("card", "meta"),
    settingsData(),
  ]);
  // the ban list (Oct 25): no bet on a banned player or team; the games themselves stay
  const { offers, tickets } = unbanned(allOffers, allTickets, settings.bans ?? []);
  const want = (league: string) => !sport || league === sport;
  // Home shows only what can still be bet (Mike, 2026-10-10): anything that has started drops off, and a
  // parlay shows only once it's locked (sgp_plus.keep_tickets: about 15 minutes before its slice) until
  // its first kickoff. A single-game slip has no slice lock: it shows in the same last LOCK_MS before its game.
  const now = Date.now();
  const future = (iso?: string | null) => !!iso && Date.parse(iso) > now;
  const LOCK_MS = 25 * 60 * 1000;
  const slates = new Map((slatesDoc?.slates ?? []).map((s) => [s.slate, s]));
  // A game's own single-game slips show for the games you watch (Mike, Nov 7: no Knicks rule, no lone prime-time rule),
  // in Parlays next to the slices' tickets once the slice locks (lib/watch.ts). Until then a window with an SGP+
  // ticket hid its games' slips (Oct 12) and a lone game showed its own.
  const watching = new Set(settings.watching ?? []);
  const showTicket = (t: Ticket) => future(t.commence_time) && !!(t.slate && slates.get(t.slate)?.locked_at);
  const byGame = new Map<string, FeedGame>();
  for (const g of games.filter((g) => want(g.league) && future(g.commence_time))) byGame.set(g.game_id, { ...g, offers: [], tickets: [] });
  for (const o of offers) {
    if (!(o.game_id && byGame.has(o.game_id) && future(o.commence_time))) continue;
    if (o.tier === "lean") continue;     // Home shows no leans (Mike, Oct 22): they stay on each game's page and Games
    if (o.tier === "pick") continue;     // picks have their own list above the games (Mike, Oct 28: not twice)
    byGame.get(o.game_id)!.offers.push(o);
  }
  // a game row carries its overs to root for in the last LOCK_MS (the game page lists them); slips go to Parlays
  for (const t of tickets) if (t.kind === "over" && t.game_id && byGame.has(t.game_id) && future(t.commence_time)
    && Date.parse(t.commence_time ?? "") - now <= LOCK_MS) byGame.get(t.game_id)!.tickets.push(t);
  for (const g of byGame.values()) g.offers.sort(byEv);

  // Home lists picks and parlays. Leans (Oct 22), "check the news" flags and overs to root for stay on the
  // game page (Mike, 2026-10-01: no overs on the main page).
  const acts = (g: FeedGame) => g.offers.some((o) => o.tier !== "check") || g.tickets.some((t) => t.kind !== "over");
  const items: FeedItem[] = [
    ...[...byGame.values()].filter(acts).map((g) => ({ kind: "game" as const, at: g.commence_time ?? "", game: g })),
    ...tickets.filter((t) => want(t.sport) && ((!t.game_id && (t.kind === "sgp_plus" || t.kind === "td") && showTicket(t))
      || showsWatched(t, watching, now)))
      .map((t) => ({ kind: "ticket" as const, at: t.commence_time ?? "", ticket: t, slate: (t.slate && slates.get(t.slate)) || null })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  const picks = offers.filter((o) => o.tier === "pick" && want(o.league) && future(o.commence_time)).sort(byEv);
  const withPick = new Set(picks.map((o) => o.game_id));
  const quiet = [...byGame.values()].filter((g) => !acts(g) && !withPick.has(g.game_id)).length;
  const sports = [...new Set(games.map((g) => g.league))].sort();
  const open = bets.filter((b) => !["won", "lost", "push", "void"].includes(String(b.pick_status ?? b.ticket_status ?? "open")));
  const bucket = { used: bucketUsed(recordBets(bets, isReal(new Date(), settings.real_from)).counted), cap: settings.fun_bucket_monthly };
  // a watched game's own slips lock by their game, never the slice (Nov 7): one lock each
  const nextLocks = upcomingLocks(slatesDoc?.slates ?? [], now, games, watchedLocks(tickets, watching, now)).filter((l) => want(l.sport));
  return { items, picks, quiet, sports, open: open.length, bucket, pricedAt: cardMeta?.generated_at ?? null, nextLocks,
           fixture: fixtureMode() };
}

export async function gameData(gameId: string) {
  const [games, allOffers, allTickets, analysis, bets, quotes, settings] = await Promise.all([
    rows<Game>("games", { eq: [["game_id", gameId]] }),
    rows<Offer>("offers", { eq: [["game_id", gameId]], active: true }),
    rows<Ticket>("fun_tickets", { eq: [["game_id", gameId]], active: true }),
    rows<{ kind: string; body: Analysis }>("game_analysis", { eq: [["game_id", gameId]] }),
    rows<Bet>("bets"),
    rows<Quote>("quotes"),
    settingsData(),
  ]);
  if (!games[0]) return null;
  const { offers, tickets } = unbanned(allOffers, allTickets, settings.bans ?? []);
  return {
    game: games[0], offers: offers.sort(byEv), tickets,
    analysis: Object.fromEntries(analysis.map((a) => [a.kind, a.body])) as Record<string, Analysis>,
    mine: Object.fromEntries(bets.map((b) => [b.pick_id ?? b.sgp_id, b])) as Record<string, Bet>,
    quotes: Object.fromEntries(quotes.map((q) => [q.sgp_id, q.price])) as Record<string, number>,
  };
}

/** Games: every game not yet started, to a week out, with how many things there are to act on in each. A game leaves
 *  the list at its start (Mike, Oct 13), as on Home; its page still opens from My bets. */
export async function allGames(sport: string | null) {
  const { from, to } = window("week");
  const range = { from: ["commence_time", from.toISOString()] as [string, string], to: ["commence_time", to.toISOString()] as [string, string] };
  const [games, offers, tickets] = await Promise.all([
    rows<Game>("games", range), rows<Offer>("offers", { ...range, active: true }), rows<Ticket>("fun_tickets", { ...range, active: true }),
  ]);
  const counts: Record<string, number> = {};
  for (const x of [...offers.filter((o) => o.tier !== "check"), ...tickets]) if (x.game_id) counts[x.game_id] = (counts[x.game_id] ?? 0) + 1;
  return {
    games: games.filter((g) => (!sport || g.league === sport) && (!g.commence_time || Date.parse(g.commence_time) > Date.now())).sort((a, b) => String(a.commence_time).localeCompare(String(b.commence_time))),
    sports: [...new Set(games.map((g) => g.league))].sort(),
    counts,
  };
}

/** Marked bets keyed by pick or ticket id, for the Mark / Undo buttons. */
export async function myMarks(): Promise<Record<string, Bet>> {
  const bets = await rows<Bet>("bets");
  return Object.fromEntries(bets.map((b) => [b.pick_id ?? b.sgp_id, b]));
}

/** Build's marks: open bets only (Nov 9). The same legs built again for another game must not show an old settled bet
 *  as this slip (whose Undo would delete it). */
export async function openMarks(): Promise<Record<string, Bet>> {
  const bets = await rows<MyBet>("my_bets");
  return Object.fromEntries(bets.filter((b) => !isSettled(b)).map((b) => [b.pick_id ?? b.sgp_id, b]));
}

/** My bets: the signed-in user's bets with their results, the prices they typed and their own parlays. */
export async function myBetsData() {
  const [bets, quotes, customs, settings, clvNow, slipPrices] = await Promise.all([
    rows<MyBet>("my_bets"), rows<QuoteRow>("quotes"), rows<CustomParlay>("custom_parlays"), settingsData(),
    fixtureMode() ? Promise.resolve([]) : rows<{ bet_id: string; clv: number; updated_at: string }>("bet_clv").catch(() => []),
    fixtureMode() ? Promise.resolve([]) : rows<{ bet_id: string; p: number }>("slip_prices").catch(() => []),
  ]);
  // A parlay marked before its FanDuel price was typed takes the price typed later.
  const typed = new Map([...quotes, ...customs].map((q) => [q.sgp_id, q.price]));
  const now = new Map(clvNow.map((c) => [c.bet_id, c]));
  const slipP = new Map(slipPrices.map((s) => [s.bet_id, Number(s.p)]));
  // A Build slip marked before Nov 1 was saved without its games (each leg's game for the live tracker): its saved
  // slip has them.
  const slipGames = new Map(customs.filter((c) => c.games?.length).map((c) => [c.sgp_id, c.games!]));
  const withPrice = bets.map((b) => (b.price == null && b.sgp_id && typed.has(b.sgp_id) ? { ...b, price: typed.get(b.sgp_id)! } : b))
    .map((b) => (!b.games?.length && b.sgp_id && slipGames.has(b.sgp_id)
      ? { ...b, games: slipGames.get(b.sgp_id)!.map((g) => ({ matchup: g.matchup, game_ref: g.game_ref ?? undefined, legs: g.legs })) } : b))
    .map((b) => (slipP.has(b.bet_id) ? { ...b, slip_p: slipP.get(b.bet_id)! } : b))
    .map((b) => (now.has(b.bet_id) ? { ...b, clv_now: Number(now.get(b.bet_id)!.clv), clv_at: now.get(b.bet_id)!.updated_at } : b));
  return { bets: await withStarts(withPrice), quotes, customs, settings, fixture: fixtureMode() };
}

/** A bet with no start of its own (entered by hand or from a slip) sorts, files and closes (Tail) by its first
 *  game's kickoff. */
async function withStarts(bets: MyBet[]): Promise<MyBet[]> {
  const need = bets.filter((b) => !b.pick_commence_time && !b.ticket_commence_time && b.games?.length);
  const ids = [...new Set(need.flatMap((b) => (b.games ?? []).filter((g) => !refTime(g.game_ref)).map((g) => refGameId(g.game_ref))
    .filter((x): x is string => !!x)))];
  const starts = ids.length ? Object.fromEntries((await rows<Game>("games", { inList: ["game_id", ids] }).catch(() => []))
    .filter((g) => g.commence_time).map((g) => [g.game_id, g.commence_time!])) : {};
  // each game's own kickoff too: the live tracker looks for a slip's games on their own days (lib/live-bets searchDays)
  const own = (b: MyBet) => Object.fromEntries((b.games ?? []).map((g) => refGameId(g.game_ref)).filter((x): x is string => !!x && !!starts[x])
    .map((x) => [x, starts[x]]));
  return bets.map((b) => (need.includes(b) ? { ...b, game_start: gameStart(b, starts), game_starts: own(b) } : b));
}

/** Ladders (Oct 26, lib/ladder.ts): the user's ladders, newest first, and what BetLab could suggest as a step: the
 *  card's live picks and leans for the next two days, cleared of the ban list. */
export async function ladderData(bans: Ban[]) {
  const now = new Date();
  const [ladders, offers, games] = await Promise.all([
    // a preview fixture may carry ladders of its own (its `ladders` rows), plus any started in the preview
    fixtureMode() ? fixture().then((fx) => [...((fx.ladders ?? []) as Ladder[]), ...fixtureWrites.ladders]) : rows<Ladder>("ladders"),
    rows<Offer>("offers", { active: true, from: ["commence_time", now.toISOString()],
                            to: ["commence_time", new Date(now.getTime() + 48 * 3600_000).toISOString()] }),
    // every game still to start today (ET), priced or not: the step chooser lists them all (Mike, Oct 26: "why is mnf not there?")
    rows<Game>("games", { from: ["commence_time", now.toISOString()], to: ["commence_time", window("today", now).to.toISOString()] }),
  ]);
  return { ladders: [...ladders].sort((a, b) => b.created_at.localeCompare(a.created_at)),
           offers: unbanned(offers.filter((o) => o.tier !== "check"), [], bans).offers,
           games: [...games].sort((a, b) => String(a.commence_time).localeCompare(String(b.commence_time))),
           dayEnd: window("today", now).to.toISOString() };
}

/** Game day (Home's hub, the wall): the open bets and what to call each on a small card (lib/gameday.ts). */
export async function openBetNames(): Promise<{ id: string; name: string }[]> {
  const { isSettled } = await import("./bets");
  const { betName } = await import("./gameday");
  const { bets } = await myBetsData();
  return bets.filter((b) => !isSettled(b)).map((b) => {
    const n = betName(b);
    return { id: b.bet_id, name: n.startsWith("Bet") ? b.matchup ?? n : n };
  });
}

/** Games from a day before to a week after a moment (snap a slip: the bet's games, started or not). */
export async function gamesAround(at: Date): Promise<Game[]> {
  return rows<Game>("games", { from: ["commence_time", new Date(at.getTime() - 86_400_000).toISOString()],
                               to: ["commence_time", new Date(at.getTime() + 7 * 86_400_000).toISOString()] });
}

/** UFC fights' grader refs ("ufc:<ESPN event>:<fight>") by game id, from their game_analysis rows: the games table
 * keys a fight by its odds event (+ Add's slip matching, lib/slip.ts). */
export async function ufcRefs(gameIds: string[]): Promise<Record<string, string>> {
  if (!gameIds.length) return {};
  const got = await rows<{ game_id: string; body: { game_ref?: string } }>("game_analysis",
    { eq: [["kind", "ufc"]], inList: ["game_id", gameIds] });
  return Object.fromEntries(got.flatMap((r) => (r.body?.game_ref ? [[r.game_id, r.body.game_ref]] : [])));
}

/** Build: games with a leg pack that haven't started (metadata only: the draws load per game), the
 * typical-payout bands from the typed quotes, and the user's own saved parlays. */
export async function buildData() {
  const now = new Date().toISOString();
  let packs: { pack_key: string; odds_event_id: string; sport: string; commence_time: string; matchup: string; part: unknown }[];
  if (fixtureMode()) {
    packs = (await rows<any>("leg_packs", { from: ["commence_time", now] }))
      .map((r) => ({ ...r, matchup: r.body?.matchup, part: r.body?.part }));
  } else {
    const sb = await supabaseServer();
    const { data, error } = await sb.from("leg_packs")
      .select("pack_key, odds_event_id, sport, commence_time, matchup:body->>matchup, part:body->>part")
      .gt("commence_time", now).limit(2000);
    if (error) throw new Error(`leg_packs: ${error.message}`);
    packs = (data ?? []) as typeof packs;
  }
  const games = packs.filter((p) => Number(p.part ?? 1) === 1)
    .map((p) => ({ event_id: String(p.odds_event_id), matchup: p.matchup, commence_time: p.commence_time, sport: p.sport || "nfl" }))
    .sort((a, b) => a.commence_time.localeCompare(b.commence_time));
  const [funResults, customs, settings] = await Promise.all([
    doc<{ typical_ratio?: { bands?: { max_fair: number | null; ratio: number }[]; model?: QuoteModel | null } }>("app", "fun_results"),
    rows<CustomParlay & { games?: unknown; p_fair: number | null }>("custom_parlays"),
    settingsData(),
  ]);
  return { games, bands: funResults?.typical_ratio?.bands ?? null, quoteModel: funResults?.typical_ratio?.model ?? null,
           bans: settings.bans ?? [],
           customs: customs.sort((a, b) => String(b.quoted_at).localeCompare(String(a.quoted_at))), fixture: fixtureMode() };
}

/** One game's leg pack with its simulated draws, all parts (pack_key <event id>, -2, ...). */
export async function packParts(eventId: string): Promise<Record<string, any>[]> {
  const r = await rows<{ body: Record<string, any> }>("leg_packs", { eq: [["odds_event_id", eventId]] });
  return r.map((x) => x.body);
}

// ------------------------------------------------------------------------------------- More

export type Todo = { id: string; owner: "you" | "claude"; title: string; detail: string; due: string | null;
  status: "open" | "done"; done_at: string | null; ord: number; added_by: string; created_at: string };
export type Review = { id: string; title: string; body: string; created_at: string };
/** An account's settings. Units only (Oct 12): the table's old bankroll and unit_pct columns are no longer read. */
export type Settings = { fun_bucket_monthly: number; book: string; real_from?: string | null; share_bets?: boolean;   // share_bets: friends see your bets (0024)
  notify?: { legs?: boolean; picks?: boolean; leans?: boolean; locks?: boolean; news?: boolean; min_ev?: number | null; sports?: Record<string, boolean>; quiet?: { from: string; to: string } | null } | null; bans?: Ban[]; wall_order?: string[];
  unit_dollars?: number | null; books_off?: string[]; watching?: string[] };   // watching: watched games' game ids (0045, Nov 7; lib/watch.ts)   // books_off: books turned off (0043, Nov 6; lib/books.ts)   // dollars per unit, on the account (0029, Oct 30: was each device's own)   // wall_order: the wall's tiles (lib/order.ts)   // bans: the ban list (lib/bans.ts, Oct 25)   // notify.legs false: no leg push alerts (worker leg_alerts.py, Oct 24)
export const DEFAULT_SETTINGS: Settings = { fun_bucket_monthly: 10, book: "FanDuel", real_from: null };

export type Stat = { bets: number; record: string; open: number; units: number; roi: number | null; roi_noise?: number | null;
  clv_bets: number; avg_clv: number | null; beat_close_pct: number | null };
export type Golive = {
  generated_at?: string; review_day?: string; days_left?: number;
  rules: { min_picks: number; min_avg_clv: number; min_beat_close: number };
  markets: { market: string; status: string; progress: number; avg_clv_corrected?: number | null;
    picks: { logged: number; with_clv: number; avg_clv: number | null; beat_close: number | null; sure_positive: number | null };
    leans: { logged: number; with_clv: number; avg_clv: number | null; beat_close: number | null } }[];
  all_markets?: { picks: { with_clv: number; avg_clv: number | null; beat_close: number | null; sure_positive: number | null } };
  /** Each book on its own record (Oct 12; everything before then was FanDuel's). */
  by_book?: { book: string; picks: { logged: number; with_clv: number; avg_clv: number | null; beat_close: number | null };
    leans: { logged: number; with_clv: number; avg_clv: number | null; beat_close: number | null } }[];
  research?: Record<string, Record<string, { n?: number; won?: number; hits?: number; hit_rate?: number }>>;
};
export type PaperPick = { pick_id: string; tier: string; league: string; matchup: string | null; label: string | null; price: number | null;
  commence_time: string | null; status: string | null; profit_flat: number | null; units_flat: number | null; clv: number | null;
  clv_raw: number | null; market: string | null; kind: string | null };

/** My bets > Record > Missed bets (Nov 2): every pick under the current rules. */
export const allPicks = () => rows<PaperPick>("paper_picks", { eq: [["tier", "pick"], ["current_rule", true]] });

/** More > Model: the shared paper record and how each market scores against the close. */
export async function modelData() {
  const [results, golive, meta, picks, marks] = await Promise.all([
    doc<{ overall?: Stat; by_market?: Record<string, Stat> }>("app", "results"),
    doc<Golive>("app", "golive"),
    doc<{ synced_at?: string }>("app", "meta"),
    rows<PaperPick & { current_rule: boolean }>("paper_picks", { eq: [["tier", "pick"], ["current_rule", true]] }),
    myMarks(),
  ]);
  return { results, golive, syncedAt: meta?.synced_at ?? null, picks, marked: new Set(Object.keys(marks)) };
}

export async function coverageDoc() {
  return doc<{ updated?: string; columns: string[]; rows: string[][]; key?: string[]; notes?: string[] }>("app", "coverage");
}

export async function reviewsData() {
  return (await rows<Review>("reviews")).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
}

export async function todosData() {
  return rows<Todo>("todos");
}

export { UNIT_DEFAULT, unitOf } from "./real";   // the unit's dollars (Oct 30): browser-safe, in real.ts

/** A signed-in account that hasn't seen the first-run welcome (Nov 5). A failed read says no: never block the app on it. */
export async function needsWelcome(): Promise<boolean> {
  if (fixtureMode()) return false;
  try {
    const sb = await supabaseServer();
    const { data: { user } } = await sb.auth.getUser();
    if (!user) return false;
    const { data, error } = await sb.from("user_settings").select("onboarded_at").maybeSingle();
    return !error && !data?.onboarded_at;
  } catch { return false; }
}

export async function settingsData(): Promise<Settings> {
  const r = (await rows<Settings>("user_settings"))[0];
  return r ? { fun_bucket_monthly: Number(r.fun_bucket_monthly), book: r.book,
               real_from: r.real_from ?? null, notify: r.notify ?? {}, bans: cleanBans(r.bans),
               wall_order: Array.isArray(r.wall_order) ? r.wall_order.map(String) : [], share_bets: r.share_bets !== false,
               unit_dollars: Number(r.unit_dollars) > 0 ? Number(r.unit_dollars) : null,
               books_off: Array.isArray(r.books_off) ? r.books_off.map(String) : [],
               watching: Array.isArray(r.watching) ? r.watching.map(String) : [] }
    : DEFAULT_SETTINGS;
}

// ------------------------------------------------------------------------------------- Friends

export type SocialData = { me: string; email: string; profile: Profile | null; profiles: Profile[]; friendships: Friendship[] };

async function whoAmI(): Promise<{ id: string; email: string }> {
  if (fixtureMode()) return { id: OWNER_USER_ID, email: "mike@example.com" };
  const { data } = await (await supabaseServer()).auth.getUser();
  return { id: data.user?.id ?? "", email: data.user?.email ?? "" };
}

/** The signed-in user's id (the owner in the local preview). */
export async function myId(): Promise<string> {
  return (await whoAmI()).id;
}

/** Your profile, your friendships (both ways, any status) and the profiles you can see (yours and the people you're
 *  connected to: row-level security, 0024). */
export async function socialData(): Promise<SocialData> {
  const { id: me, email } = await whoAmI();
  if (fixtureMode()) {
    if (!fixtureWrites.socialSeeded) {        // the preview's sample friends, copied once; Friends' buttons edit the copy
      const fx = await fixture();
      fixtureWrites.profiles = [...(fx.profiles ?? [])] as Profile[];
      fixtureWrites.friendships = [...(fx.friendships ?? [])] as Friendship[];
      fixtureWrites.socialSeeded = true;
    }
    const { profiles, friendships } = fixtureWrites;
    return { me, email, profile: profiles.find((p) => p.user_id === me) ?? null, profiles, friendships };
  }
  const [profiles, friendships] = await Promise.all([rows<Profile>("profiles"), rows<Friendship>("friendships")]);
  return { me, email, profile: profiles.find((p) => p.user_id === me) ?? null, profiles, friendships };
}

/** Friends' bets as My bets shows them (friend_bets, 0024): every accepted friend who shares, or just `friend`. */
export async function friendBets(friend?: string): Promise<MyBet[]> {
  if (fixtureMode()) {
    const all = ((await fixture()).friend_bets ?? []) as MyBet[];
    return withStarts(friend ? all.filter((b) => b.user_id === friend) : all);
  }
  const sb = await supabaseServer();
  const { data, error } = await sb.rpc("friend_bets", friend ? { friend } : {});
  if (error) throw new Error(`friend_bets: ${error.message}`);
  return withStarts((data ?? []) as MyBet[]);
}

/** Reactions on these bets you can see (bet_reactions_for, 0042): on your own bets, and friends' bets you can react to. */
export async function reactionsFor(ids: string[]): Promise<Reaction[]> {
  if (!ids.length) return [];
  if (fixtureMode()) {        // the preview's sample rows, with your taps there on top (a take-back is a row with no reaction)
    const me = await myId(), taps = fixtureWrites.reactions;
    const base = ((await fixture()).bet_reactions ?? []) as Reaction[];
    return [...base.filter((r) => !(r.user_id === me && taps.some((t) => t.bet_id === r.bet_id))), ...taps.filter((t) => t.reaction)]
      .filter((r) => ids.includes(r.bet_id));
  }
  const sb = await supabaseServer();
  const { data, error } = await sb.rpc("bet_reactions_for", { bets: ids });
  if (error) throw new Error(`bet_reactions_for: ${error.message}`);
  return (data ?? []) as Reaction[];
}

/** More > Settings > Test Open in FanDuel, round 3 (Oct 6): one live FanDuel bet link to try through the
 *  app's own scheme. The soonest active offer that has a link and hasn't started. */
export async function fdTestOffer(): Promise<{ label: string; matchup: string | null; url: string } | null> {
  const now = new Date().toISOString();
  const offers = await rows<Offer>("offers", { active: true, from: ["commence_time", now] });
  const o = offers.filter((x) => x.fd_url && (x.book ?? "FanDuel") === "FanDuel").sort((a, b) => Date.parse(a.commence_time ?? "") - Date.parse(b.commence_time ?? ""))[0];
  return o ? { label: o.label, matchup: o.matchup ?? null, url: o.fd_url! } : null;
}


/** Up to three upcoming DraftKings bets with links, earliest first, for More > Settings > Test Open in
 *  DraftKings (Oct 12): one to open, and two from different games to try the parlay formats. */
export async function dkTestOffers(): Promise<{ label: string; matchup: string | null; url: string }[]> {
  const now = new Date().toISOString();
  const offers = await rows<Offer>("offers", { active: true, from: ["commence_time", now] });
  const dk = offers.filter((x) => x.fd_url && x.book === "DraftKings" && x.fd_url.includes("draftkings.com"))
    .sort((a, b) => Date.parse(a.commence_time ?? "") - Date.parse(b.commence_time ?? ""));
  const seen = new Set<string>(), out: { label: string; matchup: string | null; url: string }[] = [];
  for (const o of dk) {
    const g = o.matchup ?? o.offer_id;
    if (seen.has(g)) continue;
    seen.add(g);
    out.push({ label: o.label, matchup: o.matchup ?? null, url: o.fd_url! });
    if (out.length === 3) break;
  }
  // Too few DraftKings bets for round 3 (Oct 13: one, ANA ML): borrow fun tickets' winner legs, one per team,
  // so each comes from a different game.
  if (out.length < 3) {
    const tickets = await rows<Ticket>("fun_tickets", { active: true, from: ["commence_time", now] });
    for (const t of tickets.sort((a, b) => Date.parse(a.commence_time ?? "") - Date.parse(b.commence_time ?? ""))) {
      for (const l of (t.body.legs ?? []) as (Leg & { team?: string })[]) {
        if (!l.dk_link?.includes("draftkings.com") || !/ to win$| ML$/.test(l.label)) continue;
        const g = l.team ?? l.label;
        if ([...seen].some((s) => s === g || s.split(" @ ").includes(g))) continue;
        seen.add(g);
        out.push({ label: l.label, matchup: null, url: l.dk_link });
        if (out.length === 3) return out;
      }
    }
  }
  return out;
}

/** Fun tickets' bodies by id (live tracking reads each ticket's games and their legs). */
export async function ticketBodies(ids: string[]): Promise<Record<string, Record<string, any>>> {
  if (!ids.length) return {};
  const r = await rows<{ sgp_id: string; sport: string | null; matchup: string | null; commence_time: string | null; body: Record<string, any> }>(
    "fun_tickets", { inList: ["sgp_id", ids] });
  return Object.fromEntries(r.map((t) => [t.sgp_id, { ...t.body, _sport: t.sport, _matchup: t.matchup, _start: t.commence_time }]));
}

export type ScheduleRow = { id: string; league: string; sport: string; start: string; home: string | null; away: string | null;
  matchup: string; game_id: string | null };

/** The calendar (Nov 4): a month's game counts, and one day's games, your bets and locks. `schedule_games` comes from ESPN
 *  (calendar_sync.py); `sport` narrows it. Days carry "open bets" and "locks" so the month can mark them. */
export async function calendarData(days: string[], day: string, sport: string | null) {
  const [counts, games, { bets }, slatesDoc] = await Promise.all([
    rows<{ day: string; sport: string; games: number }>("calendar_days", { inList: ["day", days] }),
    rows<ScheduleRow>("schedule_games", { from: ["start", etStart(day).toISOString()], to: ["start", etStart(addDays(day, 1)).toISOString()] }),
    myBetsData(),
    doc<{ slates?: LockSlate[] }>("fun", "slates"),
  ]);
  const want = <T extends { sport: string }>(x: T) => !sport || x.sport === sport;
  const count: Record<string, number> = {};
  for (const c of counts.filter(want)) count[c.day] = (count[c.day] ?? 0) + c.games;
  const betDays: Record<string, number> = {};
  for (const b of bets) { const d = etDay(startOf(b) ?? b.placed_at); betDays[d] = (betDays[d] ?? 0) + 1; }
  // the slices with a lock ahead; the NBA's and college basketball's come from the schedule until they're built
  const locks = upcomingLocks(slatesDoc?.slates ?? [], Date.now(), games.map((g) => ({ league: g.sport, commence_time: g.start })))
    .filter((l) => !sport || l.sport === sport);
  return {
    count, betDays,
    sports: [...new Set(counts.map((c) => c.sport))].sort(),
    games: games.filter(want).sort((a, b) => a.start.localeCompare(b.start) || a.matchup.localeCompare(b.matchup)),
    bets: bets.filter((b) => etDay(startOf(b) ?? b.placed_at) === day),
    locks: locks.filter((l) => etDay(l.at) === day),
    allLocks: locks,
  };
}

export type SearchHit = { kind: "game" | "player"; title: string; sport: string; at: string | null; game_id: string | null;
  photo?: string | null };   // a player's headshot, attached here (the box is a client component; headshots are server-only)
export type SearchResults = { teams: (SearchTeam & { sport: string })[]; players: SearchHit[]; games: SearchHit[]; bets: MyBet[] };

/** Search (Nov 4): your bets and the team list here; the shared games, fights and players from search_app (migration 0036).
 *  A preview fixture answers from its own `search_app` rows (matched on the title's words). */
export async function searchData(q: string): Promise<SearchResults> {
  const [found, { bets }] = await Promise.all([searchHits(q), myBetsData()]);
  const players = await Promise.all(found.filter((h) => h.kind === "player").map(async (h, i) =>
    ({ ...h, photo: i < 12 ? (await headshot(h.title, h.sport).catch(() => null))?.url ?? null : null })));
  return { teams: searchTeams(TEAMS as Record<string, SearchTeam[]>, q), players, games: found.filter((h) => h.kind === "game"),
           bets: searchBets(bets, q) };
}

async function searchHits(q: string): Promise<SearchHit[]> {
  if (fixtureMode()) {
    const w = q.toLowerCase().split(/\s+/).filter(Boolean);
    return ((await fixture()).search_app ?? []).filter((h: SearchHit) => w.every((x) => h.title.toLowerCase().includes(x))) as SearchHit[];
  }
  const { data, error } = await (await supabaseServer()).rpc("search_app", { q });
  if (error) throw new Error(`search_app: ${error.message}`);
  return (data ?? []) as SearchHit[];
}

/** Signed-in devices (migration 0037). */
export async function deviceSessions(): Promise<DeviceSession[]> {
  if (fixtureMode()) return [];
  const { data, error } = await (await supabaseServer()).rpc("my_sessions");
  if (error) throw new Error(`my_sessions: ${error.message}`);
  return (data ?? []) as DeviceSession[];
}
