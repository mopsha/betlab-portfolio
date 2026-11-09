import "server-only";
import { isSettled, refGameId, refTime } from "./bets";
import { myBetsData, ticketBodies, type MyBet } from "./data";
import { addDays, etDay } from "./time";
import { boxscore, espn, findGame, judge, rollup, scoreboard, SOCCER, type BetLive, type Box, type Fetcher, type GameLive, type Group } from "./live";

const ET = "America/New_York";
const ymd = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: ET }).replaceAll("-", "");
const ymdNext = (d: Date, n: number) => addDays(etDay(d), n).replaceAll("-", "");   // by the calendar: a clock-change day isn't 24 hours
const GUESS = ["nfl", "nba", "nhl", "ncaaf", "ncaab", "ufc"];     // a bet that doesn't say its sport

/** A leg's sport (and soccer league) from its game ref: "nhl:2026020162", "2026_07_NE_CHI", "nba|NYK|BOS|tip",
 * "epl|Home|Away|kickoff", "ufc:<event>:<fight>". */
export function refSport(ref: unknown): { sport: string | null; league: string | null } {
  const s = String(ref ?? "");
  if (s.includes("|")) {
    const head = s.split("|")[0];
    return head === "nba" ? { sport: "nba", league: null } : SOCCER[head] ? { sport: "soccer", league: head } : { sport: null, league: null };
  }
  const head = s.split(":")[0];
  if (["nhl", "ncaaf", "ncaab", "ufc", "nba", "nfl"].includes(head) && s.includes(":")) return { sport: head, league: null };
  if (/^\d{4}_\d{2}_/.test(s)) return { sport: "nfl", league: null };
  return { sport: null, league: null };
}

const sportOf = (key: unknown): { sport: string | null; league: string | null } => {
  const k = String(key ?? "").toLowerCase();
  if (SOCCER[k]) return { sport: "soccer", league: k };
  return { sport: k && k !== "mixed" ? k : null, league: null };
};

const labelOf = (l: unknown) => (typeof l === "string" ? l : (l as any)?.label ?? "");

/** A bet's games and the legs on each; each game's start when known (its ref's time, else the games table's by its id,
 *  `game_starts` from data.withStarts). */
export function groups(b: MyBet, tickets: Record<string, Record<string, any>>): Group[] {
  const games = (b as any).games as { matchup: string; game_ref?: string; legs: string[] }[] | null;
  if (Array.isArray(games) && games.length) {
    return games.map((g) => {
      const start = refTime(g.game_ref) ?? b.game_starts?.[refGameId(g.game_ref) ?? ""] ?? null;
      return { ...(refSport(g.game_ref).sport ? refSport(g.game_ref) : sportOf(b.sport ?? b.league)) as any,
        matchup: g.matchup, legs: g.legs, ...(g.game_ref ? { ref: g.game_ref } : {}), ...(start ? { start } : {}) };
    });
  }
  const t = b.sgp_id ? tickets[b.sgp_id] : null;
  if (t?.games?.length) {
    return t.games.map((g: any) => ({ ...(refSport(g.game_ref).sport ? refSport(g.game_ref) : sportOf(t._sport ?? b.sport)) as any,
      matchup: g.matchup, legs: (g.legs ?? []).map(labelOf), start: g.commence_time, ...(g.game_ref ? { ref: g.game_ref } : {}) }));
  }
  const legs = b.legs?.length ? b.legs : b.label ? [b.label] : [];
  const matchup = t?.matchup ?? t?._matchup ?? b.matchup ?? "";
  return [{ ...sportOf(b.league ?? b.sport ?? t?._sport) as any, matchup, legs, start: b.pick_commence_time ?? b.ticket_commence_time }];
}

type DaysBet = Pick<MyBet, "placed_at" | "pick_commence_time" | "ticket_commence_time" | "game_start">;

/** The Eastern days to look for a group's game (live_legs.search_days, iPhone Live.searchDays; tests/fixtures/
 *  live_legs.json "days"): its game's day and the next (late games run past midnight) when the start is known (the
 *  group's, the bet's, the time in its ref, or for a one-game bet its first kickoff); else the day it was placed and the
 *  next, and for an open bet yesterday and today too. Nov 9: an open bet looked only at yesterday and today, so a game
 *  two days back that wasn't graded yet (Mike's Georgia slip), or one tomorrow, had no tracker, here and in Friends. */
export function searchDays(b: Partial<DaysBet>, grp: Pick<Group, "start" | "ref">, open: boolean, now = new Date(), single = true): string[] {
  const start = grp.start ?? b.pick_commence_time ?? b.ticket_commence_time ?? refTime(grp.ref) ?? (single ? b.game_start : null) ?? null;
  const t = start ? new Date(start) : null;
  if (t && !Number.isNaN(t.getTime())) return [ymd(t), ymdNext(t, 1)];
  const placed = b.placed_at ? new Date(b.placed_at) : null;
  const days = placed && !Number.isNaN(placed.getTime()) ? [ymd(placed), ymdNext(placed, 1)] : [];
  if (open || !days.length) days.push(ymdNext(now, -1), ymd(now));
  return [...new Set(days)].sort();
}

/** The days a settled bet's game can be on (searchDays for a settled one-game bet). */
export const daysOf = (b: Partial<DaysBet>, grp: Pick<Group, "start" | "ref">): string[] => searchDays(b, grp, false);

/** Live (or final) state of bets, each game looked for on its own days (searchDays). {bet_id: BetLive}, and whether any
 * game is in progress (the page polls then). Default: the open bets. */
export async function liveBets(get: Fetcher = espn, now = new Date(), bets?: MyBet[]): Promise<{ at: string; bets: Record<string, BetLive>; live: boolean }> {
  const list = bets ?? (await myBetsData()).bets.filter((b) => !isSettled(b));
  const tickets = await ticketBodies(list.filter((b) => b.kind === "parlay" && b.sgp_id).map((b) => b.sgp_id!));
  const boards = new Map<string, Promise<GameLive[]>>();
  const board = (sport: string, league: string | null, days: string[]) => {
    const k = `${sport}|${league ?? ""}|${days.join(",")}`;
    if (!boards.has(k)) boards.set(k, scoreboard(sport, league, days, get));
    return boards.get(k)!;
  };
  const boxes = new Map<string, Promise<Box>>();
  const box = (g: GameLive, league: string | null) => {
    if (!boxes.has(g.key)) boxes.set(g.key, boxscore(g, league, get));
    return boxes.get(g.key)!;
  };
  const out: Record<string, BetLive> = {};
  await Promise.all(list.map(async (b) => {
    const gs: GameLive[] = [];
    const open = !isSettled(b), grps = groups(b, tickets);
    const legs = (await Promise.all(grps.map(async (grp) => {
      let game: GameLive | null = null, league = grp.league ?? null;
      const days = searchDays(b, grp, open, now, grps.length === 1);
      const tries = grp.sport === "soccer" && !league ? Object.keys(SOCCER).map((l) => ["soccer", l] as const)
        : grp.sport ? [[grp.sport, league] as const] : GUESS.map((s) => [s, null] as const);
      for (const [sport, lg] of tries) {
        game = findGame(await board(sport, lg, days), grp.matchup);
        if (game) { league = lg; break; }
      }
      if (game && !gs.some((x) => x.key === game!.key)) gs.push(game);
      const bx = game && game.state !== "pre" ? await box(game, league) : null;
      return grp.legs.map((l) => judge(l, game, bx?.stats ?? null, bx?.heads, bx?.onCourt));
    }))).flat();
    out[b.bet_id] = rollup(legs, gs);
  }));
  const live = Object.values(out).some((x) => x.games.some((g) => g.state === "in"));
  return { at: now.toISOString(), bets: out, live };
}

/** Open bets the live tracker already settles (Mike, Oct 23: lost or won live moves to Settled before the worker
 * grades it): {bet_id: "won" | "lost"}. A loss is certain (-stake, 0 for a bonus bet); a win only when every leg won
 * outright, so its profit is the price. Empty if ESPN is slow (3 s): the page never waits on it. */
export async function liveSettled(bets: MyBet[], get: Fetcher = espn): Promise<Map<string, "won" | "lost">> {
  const open = bets.filter((b) => !isSettled(b));
  const timeout = new Promise<null>((r) => setTimeout(() => r(null), 3000));
  const got = open.length ? await Promise.race([liveBets(get, new Date(), open).catch(() => null), timeout]) : null;
  return new Map(got ? Object.entries(got.bets).filter(([, v]) => v.settle).map(([k, v]) => [k, v.settle!] as const) : []);
}

/** Bets settled from the live tracker: the status says won or lost, flagged as not graded yet. */
export function markLiveSettled(bets: MyBet[], settled: Map<string, "won" | "lost">): MyBet[] {
  return bets.map((b) => {
    const s = settled.get(b.bet_id);
    if (!s || isSettled(b)) return b;
    return { ...b, ...(b.pick_status != null ? { pick_status: s } : { ticket_status: s }), live_settled: s };
  });
}
