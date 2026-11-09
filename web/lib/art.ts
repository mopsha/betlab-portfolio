// Each of our games' ESPN scoreboard entry (logos, team colors, score and clock) for the Games tab and game pages
// (ported from the iPhone's Live.art, Oct 24: "make game tab sexier too as well as separate game pages"). One board per
// sport and Eastern day through the shared ESPN cache; soccer games are stored as "soccer" without the competition, so
// every league's board, and a club the boards miss comes from the team directories (lib/soccer-clubs.ts).
import type { Game } from "./data";
import { DONE_TTL, PATHS, SOCCER, espn, findGame, scoreboard, type Fetcher, type GameLive } from "./live";
import { find, load } from "./soccer-clubs";

const ymd = (t: string) => new Date(t).toLocaleDateString("en-CA", { timeZone: "America/New_York" }).replaceAll("-", "");
const where = (league: string): [string, string | null][] =>
  league === "soccer" ? Object.keys(SOCCER).map((l) => ["soccer", l]) : SOCCER[league] ? [["soccer", league]] : PATHS[league] ? [[league, null]] : [];

/** {game_id: its ESPN game}. `ttl` for the boards: the Games list only wants logos (long), a game page the live score. */
export async function gameArt(games: Game[], ttl = DONE_TTL, get: Fetcher = espn): Promise<Record<string, GameLive>> {
  const cached: Fetcher = (url, t) => get(url, t ?? ttl);
  const boards = new Map<string, Promise<GameLive[]>>();
  const board = (sport: string, league: string | null, day: string) => {
    const k = `${sport}|${league ?? ""}|${day}`;
    if (!boards.has(k)) boards.set(k, scoreboard(sport, league, [day], cached).catch(() => []));
    return boards.get(k)!;
  };
  const out: Record<string, GameLive> = {};
  await Promise.all(games.filter((g) => g.commence_time).map(async (g) => {
    const day = ymd(g.commence_time!);
    const list = (await Promise.all(where(g.league).map(([s, l]) => board(s, l, day)))).flat();
    const hit = (g.away && g.home ? findGame(list, `${g.away} @ ${g.home}`) : null) ?? findGame(list, g.matchup ?? "");
    if (hit) out[g.game_id] = hit;
  }));
  // soccer games the boards didn't place: their clubs from the directories (logos and colors, our own names, no score)
  const missing = games.filter((g) => !out[g.game_id] && (g.league === "soccer" || SOCCER[g.league]) && g.home && g.away);
  if (missing.length) {
    const clubs = await load(get);
    for (const g of missing) {
      const side = (n: string) => { const c = find(n, clubs); return { name: n, abbr: c?.abbr ?? "", score: null, logo: c?.logo ?? null, color: c?.color ?? null }; };
      out[g.game_id] = { key: g.game_id, sport: "soccer", espnId: "", state: "pre", detail: "", start: g.commence_time ?? "",
                         home: side(g.home!), away: side(g.away!) };
    }
  }
  return out;
}
