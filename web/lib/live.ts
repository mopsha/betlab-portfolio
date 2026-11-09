// Live tracking for My bets (Mike, Oct 23: "live stuff for my bets screen... live track props too... the easiest
// but most accurate method"). ESPN's free scoreboards and game summaries carry the live score, clock and every
// player's box score in each league we bet, ~15-30 s behind the broadcast, with no ids to match: a bet's game is found
// on today's scoreboard by its teams (or fighters), and each leg is judged from the live numbers. Server-side only
// (app/api/live), cached 15 s, so many bets on one game cost one request.

import { addDays, etDay } from "./time";

export type Side = { name: string; abbr: string; score: number | null; logo?: string | null; color?: string | null };
export type GameLive = {
  key: string; sport: string; espnId: string; state: "pre" | "in" | "post"; detail: string; start: string;
  home: Side; away: Side; neutral?: boolean;
  // football while live (Mike, Oct 25: "signify who has the ball", "a redzone indicator"): ESPN's situation
  ball?: "home" | "away" | null; redZone?: boolean; down?: string | null;
};
export type LegStatus = "pending" | "live" | "winning" | "losing" | "tied" | "won" | "lost" | "void" | "unknown";
export type LegLive = {
  label: string; status: LegStatus; current: number | null; target: number | null; unit: string; text: string;
  gameKey: string | null; img?: string | null;     // a prop's player headshot, a team leg's logo (Oct 23)
  card?: { kind: "player" | "team"; name: string; abbr?: string | null } | null;   // whose card its picture opens (Oct 25)
  onCourt?: boolean | null;     // a basketball player's leg while live: on the floor now (Oct 25); null when unknown
  deadHeat?: boolean;           // a tie for "most X": won at a share, so never settled live at the full price (Nov 9)
};
// onCourt: a live basketball game's five a side on the floor (ESPN's box score marks them `active`), normalized names
export type Box = { stats: Record<string, Record<string, number>>; heads: Record<string, string>; onCourt?: string[] };
const HOOPS = new Set(["nba", "ncaab", "wnba"]);
export type Group = { sport: string; league?: string | null; matchup: string; legs: string[]; start?: string | null; ref?: string | null };

// ---------------------------------------------------------------------------------------------- ESPN

export const PATHS: Record<string, string> = {
  nfl: "football/nfl", ncaaf: "football/college-football", nba: "basketball/nba", ncaab: "basketball/mens-college-basketball",
  nhl: "hockey/nhl", ufc: "mma/ufc", wnba: "basketball/wnba", mlb: "baseball/mlb",
};
export const SOCCER: Record<string, string> = {
  epl: "eng.1", la_liga: "esp.1", serie_a: "ita.1", bundesliga: "ger.1", ligue_1: "fra.1", mls: "usa.1",
  ucl: "uefa.champions", uel: "uefa.europa", uecl: "uefa.europa.conf",
};
const EXTRA: Record<string, string> = { ncaaf: "&groups=80&limit=300", ncaab: "&groups=50&limit=400" };
const BASE = "https://site.api.espn.com/apis/site/v2/sports";
const HEADSHOT = "https://a.espncdn.com/i/headshots";

/** A team color that reads on both the light and dark themes: the primary unless it's near white or near black, then
 * the alternate; none if both are. ESPN gives hex without '#'. */
export function teamColor(primary?: string | null, alternate?: string | null): string | null {
  const lum = (h: string) => {
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  for (const c of [primary, alternate]) {
    if (c && /^[0-9a-f]{6}$/i.test(c) && lum(c) > 0.08 && lum(c) < 0.85) return `#${c}`;
  }
  return null;
}

export type Fetcher = (url: string, ttl?: number) => Promise<any>;

const cache = new Map<string, { at: number; ttl: number; p: Promise<any> }>();
const TTL = 15_000;
export const DONE_TTL = 6 * 3600_000;    // a finished game's board or box score never changes

/** ESPN JSON through a shared cache: 15 s (ESPN itself says max-age=10), or `ttl` for finished games. A copy answers only
 * while it's young enough for both whoever saved it and whoever asks: the Games list saves today's boards for 6 hours (it
 * wants logos), and that copy would freeze the live trackers (Nov 1, 2026). A failed fetch isn't kept. */
export const espn: Fetcher = (url, ttl = TTL) => {
  const hit = cache.get(url);
  if (hit && Date.now() - hit.at < Math.min(hit.ttl, ttl)) return hit.p;
  // 8 s at most: one stalled box score held all of /api/live for undici's 5 minutes (Nov 9 review); a timeout is a miss
  const p: Promise<any> = fetch(url, { headers: { "User-Agent": "BetLab" }, cache: "no-store", signal: AbortSignal.timeout(8_000) })
    .then((r) => (r.ok ? r.json() : null)).catch(() => null)
    .then((v) => { if (v === null && cache.get(url)?.p === p) cache.delete(url); return v; });
  cache.set(url, { at: Date.now(), ttl, p });
  if (cache.size > 800) for (const [k, v] of cache) if (Date.now() - v.at > v.ttl) cache.delete(k);
  return p;
};

const path = (sport: string, league?: string | null) =>
  sport === "soccer" ? `soccer/${SOCCER[league ?? ""] ?? league}` : PATHS[sport];

/** Today's and yesterday's games (Eastern dates: a late game can run past midnight) for a sport. */
export async function scoreboard(sport: string, league: string | null | undefined, days: string[], get: Fetcher = espn): Promise<GameLive[]> {
  const p = path(sport, league);
  if (!p) return [];
  const yday = addDays(etDay(new Date()), -1).replaceAll("-", "");
  const boards = await Promise.all(days.map((d) => get(`${BASE}/${p}/scoreboard?dates=${d}${EXTRA[sport] ?? ""}`,
    d < yday ? DONE_TTL : undefined)));
  const out: GameLive[] = [];
  for (const sb of boards) {
    for (const e of sb?.events ?? []) {
      for (const c of (sport === "ufc" ? e.competitions : [e.competitions?.[0]]) ?? []) {
        if (!c) continue;
        const comp = [...(c.competitors ?? [])];
        const side = (x: any): Side => ({
          name: sport === "ufc" ? x.athlete?.displayName ?? "" : x.team?.displayName ?? "",
          abbr: sport === "ufc" ? lastName(x.athlete?.displayName) : x.team?.abbreviation ?? "",
          score: x.score === undefined || x.score === "" ? null : Number(typeof x.score === "object" ? x.score.value : x.score),
          logo: sport === "ufc" ? ((x.athlete?.id ?? x.id) ? `${HEADSHOT}/mma/players/full/${x.athlete?.id ?? x.id}.png` : null) : x.team?.logo ?? null,
          color: sport === "ufc" ? null : teamColor(x.team?.color, x.team?.alternateColor),
        });
        const home = comp.find((x) => x.homeAway === "home") ?? comp[0], away = comp.find((x) => x.homeAway === "away") ?? comp[1];
        if (!home || !away) continue;
        const st = c.status?.type ?? e.status?.type ?? {};
        const g: GameLive = {
          key: `${sport}:${sport === "ufc" ? c.id : e.id}`, sport, espnId: String(e.id), state: (st.state ?? "pre") as GameLive["state"],
          detail: st.shortDetail ?? st.detail ?? "", start: c.date ?? e.date, home: side(home), away: side(away), neutral: !!c.neutralSite,
        };
        const sit = c.situation;
        if ((sport === "nfl" || sport === "ncaaf") && g.state === "in" && sit) {
          const id = String(sit.possession ?? "");
          g.ball = id && id === String(home.team?.id) ? "home" : id && id === String(away.team?.id) ? "away" : null;
          g.redZone = !!(g.ball && sit.isRedZone);               // ESPN leaves the flag on between possessions
          g.down = g.ball ? sit.downDistanceText ?? sit.shortDownDistanceText ?? null : null;
        }
        if (sport === "ufc") {
          g.home.score = home.winner ? 1 : null; g.away.score = away.winner ? 1 : null;      // a fight has a winner, not a score
          (g as any).winner = home.winner ? "home" : away.winner ? "away" : null;
          (g as any).result = c.status?.result?.displayName ?? null;
        }
        out.push(g);
      }
    }
  }
  return out;
}

/** A game's players: their stats ({normalized name: {stat: value}}) from the summary's box score (soccer: its rosters)
 * and their headshots ({normalized name: url}). */
export async function boxscore(g: GameLive, league: string | null | undefined, get: Fetcher = espn): Promise<Box> {
  const p = path(g.sport, league);
  if (!p || g.sport === "ufc") return { stats: {}, heads: {} };
  const s = await get(`${BASE}/${p}/summary?event=${g.espnId}`, g.state === "post" ? DONE_TTL : undefined);
  if (!s) return { stats: {}, heads: {} };
  return { stats: parseBox(s, g.sport), heads: parseHeads(s, g.sport),
           ...(HOOPS.has(g.sport) && g.state === "in" ? { onCourt: parseOnCourt(s) } : {}) };
}

/** Who's on the floor in a live basketball game: ESPN's box score marks them `active`, five a side (play-by-play
 *  substitutions miss the changes between quarters, so they drift). */
export function parseOnCourt(s: any): string[] {
  const out: string[] = [];
  for (const t of s.boxscore?.players ?? []) for (const grp of t.statistics ?? []) for (const a of grp.athletes ?? []) {
    if (a.active && a.athlete?.displayName) out.push(normName(a.athlete.displayName));
  }
  return [...new Set(out)];
}

/** Players' headshots: the box score's own (NFL, NBA, NHL), else ESPN's headshot address by player id (soccer). */
export function parseHeads(s: any, sport: string): Record<string, string> {
  const out: Record<string, string> = {};
  const put = (a: any) => {
    const name = a?.displayName;
    if (!name) return;
    const href = typeof a.headshot === "object" ? a.headshot?.href : a.headshot;
    const url = href || (sport === "soccer" && a.id ? `${HEADSHOT}/soccer/players/full/${a.id}.png` : null);
    if (url) out[normName(name)] ??= url;
  };
  if (sport === "soccer") for (const t of s.rosters ?? []) for (const pl of t.roster ?? []) put(pl.athlete);
  else for (const t of s.boxscore?.players ?? []) for (const grp of t.statistics ?? []) for (const a of grp.athletes ?? []) put(a.athlete);
  return out;
}

export function parseBox(s: any, sport: string): Record<string, Record<string, number>> {
  const out: Record<string, Record<string, number>> = {};
  const put = (name: string, k: string, v: number) => {
    if (!name || !Number.isFinite(v)) return;
    const key = normName(name);
    (out[key] ??= {})[k] = (out[key][k] ?? 0) + v;
  };
  if (sport === "soccer") {
    for (const team of s.rosters ?? []) {
      for (const pl of team.roster ?? []) {
        for (const st of pl.stats ?? []) put(pl.athlete?.displayName ?? "", st.name, Number(st.value));
      }
    }
    playStats(s, sport, out);
    return out;
  }
  for (const team of s.boxscore?.players ?? []) {
    for (const grp of team.statistics ?? []) {
      const keys: string[] = grp.keys ?? [];
      for (const a of grp.athletes ?? []) {
        const name = a.athlete?.displayName ?? "";
        // football: a QB's "sacks" (taken) and "interceptions" (thrown) aren't a defender's (made); Nov 6
        const rename: Record<string, string> = grp.name === "passing" ? { sacks: "sacksTaken" }
          : grp.name === "interceptions" ? { interceptions: "interceptionsMade" } : {};
        keys.forEach((k, i) => {
          const raw = String(a.stats?.[i] ?? "");
          if (!raw || raw.includes(":")) return;                    // clocks (time on ice) aren't counts
          // "6-10" made-attempted, "24/31" comp/att: both halves (Nov 6: pass attempts and shots attempted were dropped)
          const ks = k.split(/[-/]/), vs = raw.split(/(?<=\d)[-/]/);
          ks.forEach((kk, j) => { if (j < vs.length) put(name, rename[kk] ?? kk, Number(vs[j])); });
        });
      }
    }
  }
  playStats(s, sport, out);
  return out;
}

/** A box's game-wide row: who scored first is decided ("firstBasket", "firstGoal", "firstTd": 1). */
export const GAME = "_game";

/** What only ESPN's play-by-play says (Nov 6), added to the box's rows: NBA quarter stats ("q1:points", "q2:rebounds",
 *  "q3:assists", "q4:threes") and the first basket (the first field goal; free throws don't count); NHL period stats
 *  ("p1:goals", "p1:assists"), power-play goals and points, the first goal; NFL longest completion and the first TD;
 *  soccer's first goal. live_legs.play_stats and Live.playStats are the same. */
export function playStats(s: any, sport: string, out: Record<string, Record<string, number>>): void {
  const add = (name: string, k: string, v = 1) => { if (!name) return; const key = normName(name); (out[key] ??= {})[k] = (out[key][k] ?? 0) + v; };
  const first = (k: string, name: string) => {
    if (!name || out[GAME]?.[k]) return;
    (out[GAME] ??= {})[k] = 1;
    add(name, k);
  };
  if (sport === "nba") {
    const ids: Record<string, string> = {};
    for (const t of s.boxscore?.players ?? []) for (const g of t.statistics ?? []) for (const a of g.athletes ?? []) ids[String(a.athlete?.id)] = a.athlete?.displayName ?? "";
    for (const p of s.plays ?? []) {
      const q = p.period?.number, who: string[] = (p.participants ?? []).map((x: any) => ids[String(x.athlete?.id)] ?? "");
      const typ: string = p.type?.text ?? "";
      if (p.scoringPlay && who.length) {
        const v = Number(p.scoreValue ?? 0);
        add(who[0], `q${q}:points`, v);
        if (v >= 2) {
          first("firstBasket", who[0]);
          if (v === 3) add(who[0], `q${q}:threes`);
          if (who.length > 1) add(who[1], `q${q}:assists`);
        }
      } else if (typ.includes("Rebound") && who.length) add(who[0], `q${q}:rebounds`);
    }
  } else if (sport === "nhl") {
    for (const p of s.plays ?? []) {
      if (p.type?.text !== "Goal") continue;
      const per = p.period?.number;
      const who: string[] = (p.participants ?? []).filter((x: any) => ["scorer", "assister", undefined].includes(x.type)).map((x: any) => x.athlete?.displayName ?? "");
      if (!who.length) continue;
      const pp = p.strength?.abbreviation === "power-play";
      first("firstGoal", who[0]);
      add(who[0], `p${per}:goals`);
      if (pp) add(who[0], "ppGoals");
      for (const a of who.slice(1)) add(a, `p${per}:assists`);
      if (pp) for (const x of who) add(x, "ppPoints");
    }
  } else if (sport === "nfl") {
    const names = Object.keys(out).filter((n) => n !== GAME);
    for (const d of s.drives?.previous ?? []) for (const p of d.plays ?? []) {
      if (!["Pass Reception", "Passing Touchdown"].includes(p.type?.text)) continue;
      const m = String(p.text ?? "").match(/([A-Z][a-zA-Z'-]*)\.\s?([A-Za-z'.-]+(?:\s(?:Jr|Sr|II|III|IV)\.?)?) pass/);
      if (!m) continue;
      const qb = names.find((n) => n.startsWith(m[1][0].toLowerCase()) && n.split(" ").includes(plain(m[2])));
      const y = Number(p.statYardage);
      if (qb && Number.isFinite(y)) out[qb].longCompletion = Math.max(out[qb].longCompletion ?? 0, y);
    }
    for (const p of s.scoringPlays ?? []) {
      const m = String(p.text ?? "").match(/^(.+?) \d+ Yd/);
      if (String(p.type?.text ?? "").includes("Touchdown") && m) { first("firstTd", m[1]); break; }
    }
  } else if (sport === "soccer") {
    for (const k of s.keyEvents ?? []) {
      const typ = String(k.type?.text ?? "").toLowerCase();
      if (typ === "goal" || (k.scoringPlay && !typ.includes("own") && typ.includes("goal"))) {
        const who = (k.participants ?? []).map((x: any) => x.athlete?.displayName ?? "");
        if (who.length) { first("firstGoal", who[0]); break; }
      }
    }
  }
}

// --------------------------------------------------------------------------------------------- names

export const plain = (s: unknown) => String(s ?? "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
  .replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
const SUFFIX = new Set(["jr", "sr", "ii", "iii", "iv", "v"]);
export const normName = (s: unknown) => plain(s).split(" ").filter((t) => !SUFFIX.has(t)).join(" ");
export const lastName = (s: unknown) => { const t = normName(s).split(" "); return t[t.length - 1] ?? ""; };

/** A player in a box score: exact name, else first initial + last name, else a unique last name. */
export function findPlayer<T = Record<string, number>>(box: Record<string, T>, name: string): T | null {
  const n = normName(name);
  if (box[n]) return box[n];
  // one word ("Militao") is his last name too (live_legs.find_player, Nov 9)
  const [first, ...rest] = n.split(" "), last = rest.length ? rest[rest.length - 1] : first;
  const keys = Object.keys(box);
  const byInitial = keys.filter((k) => { const t = k.split(" "); return t[t.length - 1] === last && t[0]?.[0] === first?.[0]; });
  if (byInitial.length === 1) return box[byInitial[0]];
  const byLast = keys.filter((k) => k.split(" ").pop() === last);
  return byLast.length === 1 ? box[byLast[0]] : null;
}

// NHL codes the books use that ESPN writes differently
const ALIAS: Record<string, string> = { njd: "nj", sjs: "sj", tbl: "tb", lak: "la", wsh: "wsh", vgk: "vgk", uta: "utah", clb: "cbj" };
/** The books' club names ESPN writes differently (plain form -> ESPN's display name; lib/soccer-clubs.ts uses it for
 * logos): a slip's "Rennes" is ESPN's "Stade Rennais" (Oct 30: that game's legs never tracked). */
export const CLUB_ALIASES: Record<string, string> = {
  "1 fc koln": "FC Cologne", "agf aarhus": "AGF", "athletic bilbao": "Athletic Club",
  "brighton and hove albion": "Brighton & Hove Albion", "fc copenhagen": "F.C. København", "hamburger sv": "Hamburg SV",
  "hapoel be er sheva": "Hapoel Be'er", "los angeles fc": "LAFC", "new york red bulls": "Red Bull New York",
  "omonoia fc": "Omonia Nicosia", "pfc cska sofia": "CSKA Sofia", "pfc levski sofia": "Levski Sofia",
  "sporting lisbon": "Sporting CP", "union saint gilloise": "Union St.-Gilloise", "universitatea craiova": "CSU Craiova",
  "inter milan": "Internazionale", "fc iberia 1999": "Iberia 1999", "rennes": "Stade Rennais",
  "olympiakos piraeus": "Olympiacos", "hearts": "Heart of Midlothian", "fc nordsjaelland": "FC Nordsjælland",
  "koln": "FC Cologne", "copenhagen": "F.C. København",
};
const GENERIC = new Set(["fc", "cf", "sc", "ac", "club", "city", "united", "real", "de", "sporting", "athletic", "the", "of", "st"]);

/** How well our team text ("Chicago Bears", "CHI", "MIN", "Inter Milan", "Fighter Name") names this side: 3 the full
 * name or abbreviation, 2 the nickname or last name, 1 a shared strong word, 0 not at all. */
export function teamMatch(ours: string, side: Side): number {
  const o = plain(ours);
  if (!o) return 0;
  const abbr = plain(side.abbr), full = plain(side.name);
  if (o === abbr || ALIAS[o] === abbr || o === full || (CLUB_ALIASES[o] !== undefined && plain(CLUB_ALIASES[o]) === full)) return 3;
  const ot = o.split(" "), ft = full.split(" ");
  if (ot.length > 1 && ot[ot.length - 1] === ft[ft.length - 1] && !GENERIC.has(ot[ot.length - 1])) return 2;  // nickname / last name
  const strong = (t: string) => t.length >= 4 && !GENERIC.has(t);
  return ot.filter(strong).some((t) => ft.includes(t)) && ft.filter(strong).some((t) => ot.includes(t)) ? 1 : 0;
}
export const isTeam = (ours: string, side: Side): boolean => teamMatch(ours, side) > 0;

/** Which side of a game our team text names: the better match when both do (Oct 24: "LSU Tigers" at Auburn Tigers read
 * as Auburn by the shared nickname, so LSU's moneyline showed "Down 7" while LSU led). */
export function sideOf(ours: string, g: GameLive): "home" | "away" | null {
  const h = teamMatch(ours, g.home), a = teamMatch(ours, g.away);
  return h === a ? null : h > a ? "home" : "away";     // a tie (neither, or both alike) names no side
}

/** How well our matchup names a game: both teams must match (either way round); the sum of the two matches, else 0. */
export function gameMatch(g: GameLive, x: string, y: string): number {
  const fwd = Math.min(teamMatch(x, g.away), teamMatch(y, g.home)) && teamMatch(x, g.away) + teamMatch(y, g.home);
  const rev = Math.min(teamMatch(x, g.home), teamMatch(y, g.away)) && teamMatch(x, g.home) + teamMatch(y, g.away);
  return Math.max(fwd, rev);
}

/** Our matchup "Away @ Home" / "A vs B" on a scoreboard: the best-named game (Oct 24: "Boise State Broncos @
 * Washington State Cougars" matched Sacramento State @ Ball State by the shared word "State", live first), then a game
 * in progress first. */
export function findGame(games: GameLive[], matchup: string): GameLive | null {
  const [x, y] = String(matchup).split(/ @ | vs\.? | v /);
  if (!x || !y) return null;
  const hits = games.map((g) => ({ g, m: gameMatch(g, x, y) })).filter((h) => h.m > 0);
  return hits.length ? hits.sort((a, b) => b.m - a.m || order(a.g.state) - order(b.g.state))[0].g : null;
}
const order = (s: string) => (s === "in" ? 0 : s === "pre" ? 1 : 2);

// ---------------------------------------------------------------------------------------------- legs

type Parsed =
  | { kind: "ml"; team: string }
  | { kind: "spread"; team: string; point: number }
  | { kind: "total"; side: "over" | "under"; point: number }
  | { kind: "btts" }
  | { kind: "btts_no" }
  | { kind: "draw" }
  | { kind: "draw_or"; team: string }
  | { kind: "no_draw" }                                  // Novig's 3-way "no" sides (Nov 9)
  | { kind: "not_win"; team: string }
  | { kind: "prop"; player: string; stat: string; side: "over" | "under"; need: number; point: number }
  | { kind: "td"; player: string; first: boolean }
  | { kind: "goal_or_assist"; player: string }
  | { kind: "double"; player: string; n: 2 | 3 }       // a double-double (2) or triple-double (3), Oct 25
  | { kind: "leader"; player: string; stat: string }   // "X most receiving yds" in the game (Nov 6)
  | { kind: "card"; player: string }                    // "X to be carded" (Nov 6)
  | { kind: "first"; player: string; what: "basket" | "goal" };   // the game's first basket or goal (Nov 6)

const STAT_WORDS = ["receiving yds", "rushing yds", "passing yds", "receptions", "pts + reb + ast", "pts + reb", "pts + ast",
  "reb + ast", "points", "rebounds", "assists", "threes", "steals", "blocks", "shots on target", "shots on goal", "shots",
  "saves", "goals", "passing tds", "rush + rec yds",
  // Nov 6 (Mike: "track more stats... all possible markets"): what ESPN's box scores carry
  "longest reception", "longest rush", "rush attempts", "pass attempts", "completions", "interceptions", "tackles", "sacks",
  "kicking points", "field goals made", "turnovers", "stl + blk", "free throws made", "offensive rebounds", "blocked shots",
  "hits", "fouls", "longest completion", "power play points", "power play goals",
  // Nov 9: touchdowns by count ("2+ TDs", "1+ rushing TDs"); a rusher's and receiver's together
  "touchdowns", "rushing tds", "receiving tds",
  // quarter and half (NBA) and period (NHL) stats from the play-by-play: "1q points", "2h rebounds", "1p goals"
  ...[1, 2, 3, 4].flatMap((n) => ["points", "rebounds", "assists", "threes"].map((w) => `${n}q ${w}`)),
  ...[1, 2].flatMap((n) => ["points", "rebounds", "assists", "threes"].map((w) => `${n}h ${w}`)),
  ...[1, 2, 3].flatMap((n) => ["goals", "assists", "points"].map((w) => `${n}p ${w}`)),
].sort((a, b) => b.length - a.length);
/** The stats a "most ... in the game" leg can be about (Nov 6). */
const LEADER_WORDS = ["receiving yds", "rushing yds", "passing yds", "receptions", "points", "rebounds", "assists", "threes",
  "shots on goal", "shots", "goals"];
// (wording at the end of a leg or before its "over/under N", our stat words): live_legs.ALIASES, Live.aliases
const END = String.raw`(?=$|\s+(?:over|under)\s+\d)`;
const ALIASES: [RegExp, string][] = ([
  [String.raw`\s+(?:points\s*\+\s*rebounds\s*\+\s*assists|pts\s*\+\s*rebs?\s*\+\s*asts?|pra)`, " pts + reb + ast"],
  [String.raw`\s+(?:points\s*\+\s*rebounds|pts\s*\+\s*rebs?)`, " pts + reb"],
  [String.raw`\s+(?:points\s*\+\s*assists|pts\s*\+\s*asts?)`, " pts + ast"],
  [String.raw`\s+(?:rebounds\s*\+\s*assists|rebs?\s*\+\s*asts?)`, " reb + ast"],
  [String.raw`\s+(?:steals\s*\+\s*blocks|blocks\s*\+\s*steals|stl\s*\+\s*blk|stocks)`, " stl + blk"],
  [String.raw`\s+(?:threes\s+made|made\s+threes|three[\s-]*pointers(?:\s+made)?|3[\s-]*pointers(?:\s+made)?|3pt\s+made|3pm)`, " threes"],
  [String.raw`\s+(?:longest\s+(?:reception|catch|rec)|long\s+reception)(?:\s+(?:yds|yards))?`, " longest reception"],
  [String.raw`\s+(?:longest\s+(?:rush|rushing\s+attempt|run)|long\s+rush)(?:\s+(?:yds|yards))?`, " longest rush"],
  [String.raw`\s+(?:rushing\s+attempts|rush\s+attempts|carries)`, " rush attempts"],
  [String.raw`\s+(?:passing\s+attempts|pass\s+attempts)`, " pass attempts"],
  [String.raw`\s+(?:pass(?:ing)?\s+completions|completions)`, " completions"],
  [String.raw`\s+(?:interceptions\s+thrown|passing\s+interceptions|ints?\s+thrown)`, " interceptions"],
  [String.raw`\s+(?:tackles\s*(?:\+|and|&)\s*assists|total\s+tackles|tackles)`, " tackles"],
  [String.raw`\s+(?:made\s+field\s+goals|field\s+goals(?:\s+made)?|fgm)`, " field goals made"],
  [String.raw`\s+(?:made\s+free\s+throws|free\s+throws(?:\s+made)?|ftm)`, " free throws made"],
  [String.raw`\s+(?:offensive\s+rebounds|off\s+rebounds)`, " offensive rebounds"],
  [String.raw`\s+(?:fouls\s+committed|fouls)`, " fouls"],
  [String.raw`\s+(?:longest\s+(?:pass\s+)?completion|longest\s+pass(?:\s+completed)?)(?:\s+(?:yds|yards))?`, " longest completion"],
  [String.raw`\s+(?:power[\s-]*play\s+points|pp\s+points|ppp)`, " power play points"],
  [String.raw`\s+(?:power[\s-]*play\s+goals|pp\s+goals|ppg)`, " power play goals"],
  // Nov 9: short forms ("25+ Pts", "Over 2.5 SOG") and touchdowns by kind; a combo's last word ("pts + reb") is left alone
  [String.raw`(?<!\s\+)\s+pts`, " points"],
  [String.raw`(?<!\s\+)\s+rebs?`, " rebounds"],
  [String.raw`(?<!\s\+)\s+asts?`, " assists"],
  [String.raw`\s+sog`, " shots on goal"],
  [String.raw`\s+sot`, " shots on target"],
  [String.raw`\s+(?:passing\s+(?:touchdowns|tds?)|pass\s+tds?)`, " passing tds"],
  [String.raw`\s+(?:rushing\s+(?:touchdowns|tds?)|rush\s+tds?)`, " rushing tds"],
  [String.raw`\s+(?:receiving\s+(?:touchdowns|tds?)|rec\s+tds?)`, " receiving tds"],
  [String.raw`(?<=[\d+])\s+(?:touchdowns|tds?)`, " touchdowns"],
] as [string, string][]).map(([p, w]) => [new RegExp(p + END, "i"), w]);
/** A part of a game ("1H", "1st quarter", "2nd period", "first 5 innings", "60 min", "regulation"): a team's line on it
 *  isn't the full game's, so it's not tracked rather than judged on the final score (Nov 9; live_legs.SEGMENT). */
const SEGMENT = /(?:^|[\s(])(?:(?:1st|2nd|3rd|4th|first|second|third|fourth)\s+(?:half|quarter|qtr|period|inning)s?|[1-4][hqp]|[qp][1-4]|first\s+\d+\s+innings?|f5|60[\s-]*min(?:ute)?s?|regulation(?:\s+time)?)\)?(?=$|[\s)])/i;
/** "1st quarter points" -> "1q points", "first half rebounds" -> "1h rebounds", "1st period goals" -> "1p goals" (live_legs._period). */
const PERIOD = new RegExp(String.raw`\s+(?:(1)st|(2)nd|(3)rd|(4)th|first|second|third|fourth|q([1-4])|([1-4])q)\s*(quarter|qtr|half|period)?\s+(points|rebounds|assists|threes|goals)` + END, "i");
const WORD_N: Record<string, string> = { first: "1", second: "2", third: "3", fourth: "4" };

/** The stat's wording as books and slips write it, made ours (Oct 25: "rushing + receiving yds" and "rushing yards" from
 *  slips weren't tracked): rushing + receiving / rush & rec -> "rush + rec yds", "... yards" -> "... yds". Same in
 *  live_legs.py, Live.swift and fun_ledger.py (tests/fixtures/live_legs.json). */
export function canonStat(label: string): string {
  return label.trim()
    .replace(/\s+(?:rushing|rush)\s*(?:\+|&|and)\s*(?:receiving|rec)(?:\s+(?:yds|yards))?$/i, " rush + rec yds")
    .replace(/\s+(rushing|receiving|passing)\s+yards(?=$|\s+(?:over|under)\s+\d)/i, (_m, w: string) => ` ${w.toLowerCase()} yds`)
    // "X Anytime Touchdown Scorer", "X anytime TD scorer" (Nov 9): ours is "X anytime TD"
    .replace(/^(.+?)\s+anytime\s+(?:touchdown|td)(?:\s+scorer)?$/i, "$1 anytime TD")
    // an anytime scorer (Oct 25: "Lamine Yamal anytime goalscorer" wasn't tracked): one goal is the line
    .replace(/^(?!both teams\b)(.+?)\s+(?:anytime\s+(?:goal\s*scorer|goal|scorer)|to\s+score(?:\s+a\s+goal)?|anytime\s+to\s+score)$/i, "$1 1+ goals")
    // Nov 6: the books' other wordings of the stats tracked
    .replace(/^.*$/s, (l) => ALIASES.reduce((x, [re, w]) => x.replace(re, w), l))
    .replace(PERIOD, (m0: string, ...g: string[]) => {
      const n = g.slice(0, 6).find((x) => x) ?? WORD_N[m0.trim().split(/\s+/)[0].toLowerCase()] ?? "1";
      const unit = (g[6] ?? "quarter").toLowerCase();
      return ` ${n}${unit === "half" ? "h" : unit === "period" ? "p" : "q"} ${g[7].toLowerCase()}`;
    })
    // "To Record Double Double", "double-double" (Oct 25, Mike's Towns leg): one wording
    .replace(/^(.+?)\s+(?:to\s+record\s+(?:an?\s+)?)?(double|triple)[\s-]*double$/i, (_m, pl: string, k: string) => `${pl} ${k.toLowerCase()}-double`);
}

export function parseLeg(label: string): Parsed | null {
  let l = canonStat(label);
  let m: RegExpMatchArray | null;
  if (/^both teams to score(?:: ?yes)?$/i.test(l)) return { kind: "btts" };
  if (/^both teams to score: ?no$/i.test(l)) return { kind: "btts_no" };   // Nov 4: Build offers these three; none tracked
  if (/^draw$/i.test(l)) return { kind: "draw" };
  if (/^no draw$/i.test(l)) return { kind: "no_draw" };                     // Nov 9: Novig's 3-way "no" sides (novig_sync)
  if ((m = l.match(/^(.+) not to win$/i))) return { kind: "not_win", team: m[1] };
  if ((m = l.match(/^(.+) or draw$/i))) return { kind: "draw_or", team: m[1] };
  if ((m = l.match(/^(over|under) (\d+(?:\.\d+)?)(?: (?:total points|total goals|total|goals|points|runs|rounds))?$/i)))
    return { kind: "total", side: m[1].toLowerCase() as "over" | "under", point: Number(m[2]) };
  if ((m = l.match(/^(.+) anytime TD$/i))) return { kind: "td", player: m[1], first: false };
  if ((m = l.match(/^(.+?) (?:first TD scorer|first touchdown(?: scorer)?|to score (?:the )?first (?:TD|touchdown))$/i))) return { kind: "td", player: m[1], first: true };
  if ((m = l.match(/^(.+?) (?:to (?:make|score) (?:the )?)?first (basket|field goal|fg)(?: scorer)?$/i))) return { kind: "first", player: m[1], what: "basket" };
  if ((m = l.match(/^(.+?) (?:to score (?:the )?)?first (?:goal\s*scorer|goal)$/i))) return { kind: "first", player: m[1], what: "goal" };
  if ((m = l.match(/^(.+) to score or assist$/i))) return { kind: "goal_or_assist", player: m[1] };
  // "X most receiving yds", "X to have the most receiving yards in the game" (Nov 6, Mike: "most rcv/rush yards in game")
  if ((m = l.match(/^(.+?) (?:to (?:have|record|get) )?(?:the )?most (.+?)(?: in (?:the )?game)?$/i))) {
    const w = canonStat("x " + m[2]).slice(2).toLowerCase();
    if (LEADER_WORDS.includes(w)) return { kind: "leader", player: m[1], stat: w };
  }
  if ((m = l.match(/^(.+?) to (?:be (?:carded|booked|shown a card)|receive a card|get a card)$/i))) return { kind: "card", player: m[1] };
  if ((m = l.match(/^(.+) (double|triple)-double$/i))) return { kind: "double", player: m[1], n: m[2].toLowerCase() === "double" ? 2 : 3 };
  for (const w of STAT_WORDS) {       // the stat before its number ("Puka Nacua longest reception over 22.5"): ours puts it last
    const esc = w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if ((m = l.match(new RegExp(`^(.+?) ${esc} (over|under) (\\d+(?:\\.\\d+)?)$`, "i")))) { l = `${m[1]} ${m[2]} ${m[3]} ${w}`; break; }
  }
  for (const w of STAT_WORDS) {
    if (!l.toLowerCase().endsWith(" " + w)) continue;
    const head = l.slice(0, l.length - w.length - 1);
    const n = head.match(/^(.+?) (\d+)\+$/), ou = n ? null : head.match(/^(.+?) (over|under) (\d+(?:\.\d+)?)$/i);
    if ((n ?? ou) && SEGMENT.test((n ?? ou)![1])) return null;   // "Knicks 1H over 55.5 points": a part of the game, not tracked
    if (n) return { kind: "prop", player: n[1], stat: w, side: "over", need: Number(n[2]), point: Number(n[2]) - 0.5 };
    if (ou) {
      const pt = Number(ou[3]);
      return { kind: "prop", player: ou[1], stat: w, side: ou[2].toLowerCase() as "over" | "under", need: Math.floor(pt) + 1, point: pt };
    }
  }
  let team: Parsed | null = null;
  if ((m = l.match(/^(.+) (?:ML|to win)$/i))) team = { kind: "ml", team: m[1] };
  else if ((m = l.match(/^(.+) ([+-]\d+(?:\.\d+)?)$/))) team = { kind: "spread", team: m[1], point: Number(m[2]) };
  else if ((m = l.match(/^(.+) (?:pk|pick'?em|pick)$/i))) team = { kind: "spread", team: m[1], point: 0 };   // "Chiefs PK" (Nov 9)
  return team && "team" in team && SEGMENT.test(team.team) ? null : team;
}

/** A stat word's value from a player's box line, per sport. */
export function statValue(row: Record<string, number>, stat: string, sport: string): number | null {
  const v = (...ks: string[]) => ks.reduce((s, k) => s + (row[k] ?? 0), 0);
  const has = (k: string) => row[k] !== undefined;
  switch (stat) {
    case "passing yds": return has("passingYards") ? v("passingYards") : null;
    case "rushing yds": return has("rushingYards") ? v("rushingYards") : null;
    case "receiving yds": return has("receivingYards") ? v("receivingYards") : null;
    case "rush + rec yds": return has("rushingYards") || has("receivingYards") ? v("rushingYards", "receivingYards") : null;
    // Nov 9: a player's own scores, rushing and receiving
    case "touchdowns": return has("rushingTouchdowns") || has("receivingTouchdowns") ? v("rushingTouchdowns", "receivingTouchdowns") : null;
    case "rushing tds": return has("rushingTouchdowns") ? v("rushingTouchdowns") : null;
    case "receiving tds": return has("receivingTouchdowns") ? v("receivingTouchdowns") : null;
    case "receptions": return has("receptions") ? v("receptions") : null;
    case "passing tds": return has("passingTouchdowns") ? v("passingTouchdowns") : null;
    case "points": return sport === "nhl" ? v("goals", "assists") : has("points") ? v("points") : null;
    case "rebounds": return has("rebounds") ? v("rebounds") : null;
    case "assists": return has("assists") ? v("assists") : sport === "soccer" && has("goalAssists") ? v("goalAssists") : null;
    case "threes": return has("threePointFieldGoalsMade") ? v("threePointFieldGoalsMade") : null;
    case "steals": return has("steals") ? v("steals") : null;
    case "blocks": return has("blocks") ? v("blocks") : null;
    case "pts + reb": return has("points") ? v("points", "rebounds") : null;
    case "pts + ast": return has("points") ? v("points", "assists") : null;
    case "reb + ast": return has("rebounds") ? v("rebounds", "assists") : null;
    case "pts + reb + ast": return has("points") ? v("points", "rebounds", "assists") : null;
    case "shots": return sport === "soccer" ? (has("totalShots") ? v("totalShots") : null) : has("shotsTotal") ? v("shotsTotal") : null;
    case "shots on goal": return has("shotsTotal") ? v("shotsTotal") : null;
    case "shots on target": return has("shotsOnTarget") ? v("shotsOnTarget") : null;
    case "saves": return has("saves") ? v("saves") : null;
    case "goals": return sport === "soccer" ? (has("totalGoals") ? v("totalGoals") : null) : has("goals") ? v("goals") : null;
    case "stl + blk": return has("steals") || has("blocks") ? v("steals", "blocks") : null;
    case "longest completion": return has("longCompletion") ? v("longCompletion") : null;
    case "power play points": return v("ppPoints");          // play-by-play counts: none yet is 0
    case "power play goals": return v("ppGoals");
    case "field goals made": return has("fieldGoalsMade") ? v("fieldGoalsMade") : null;   // basketball's shots, football's kicks
    default: {
      const pm = stat.match(/^([1-4])([qhp]) (points|rebounds|assists|threes|goals)$/);
      if (pm) {   // play-by-play stats (playStats): NHL periods' points are goals plus assists; halves are two quarters
        const n = Number(pm[1]), w = pm[3];
        if (pm[2] === "p") return (w === "points" ? ["goals", "assists"] : [w]).reduce((t, x) => t + (row[`p${n}:${x}`] ?? 0), 0);
        const qs = pm[2] === "h" ? (n === 1 ? [1, 2] : [3, 4]) : [n];
        return qs.reduce((t, q) => t + (row[`q${q}:${w}`] ?? 0), 0);
      }
      // Nov 6: ESPN's box keys (parseBox keeps both halves of "completions/passingAttempts")
      const k = ({ "longest reception": "longReception", "longest rush": "longRushing", "rush attempts": "rushingAttempts",
        "pass attempts": "passingAttempts", "completions": "completions", "interceptions": "interceptions", "tackles": "totalTackles",
        "sacks": "sacks", "kicking points": "totalKickingPoints", "turnovers": "turnovers", "free throws made": "freeThrowsMade",
        "offensive rebounds": "offensiveRebounds", "blocked shots": "blockedShots", "hits": "hits", "fouls": "foulsCommitted" } as Record<string, string>)[stat];
      return k && has(k) ? v(k) : null;
    }
  }
}

const UNIT: Record<string, string> = { "passing yds": "pass yds", "rushing yds": "rush yds", "receiving yds": "rec yds",
  "rush + rec yds": "yds", "receptions": "rec", "points": "pts", "rebounds": "reb", "assists": "ast", "threes": "3PM",
  "pts + reb": "P+R", "pts + ast": "P+A", "reb + ast": "R+A", "pts + reb + ast": "PRA", "shots on target": "SOT",
  "shots on goal": "SOG", "shots": "shots", "saves": "saves", "goals": "goals", "passing tds": "pass TD",
  "longest reception": "long rec", "longest rush": "long rush", "rush attempts": "carries", "pass attempts": "att",
  "completions": "cmp", "interceptions": "INT", "tackles": "tkl", "sacks": "sacks", "kicking points": "kick pts",
  "field goals made": "FGM", "turnovers": "TO", "stl + blk": "S+B", "free throws made": "FTM", "offensive rebounds": "OREB",
  "blocked shots": "BLK", "hits": "hits", "fouls": "fouls", "longest completion": "long cmp", "power play points": "PPP",
  "power play goals": "PPG", "touchdowns": "TD", "rushing tds": "rush TD", "receiving tds": "rec TD" };

/** A first scorer leg (TD, basket, goal) from the play-by-play's mark: won once his is first, lost once someone else's is
 *  (or the game ends with none). live_legs.first_state. */
function firstState(row: Record<string, number> | null, box: Record<string, Record<string, number>> | null | undefined, key: string,
                    final: boolean, unit: string): { status: LegStatus; current: number; target: number; unit: string; text: string } {
  const mine = !!row?.[key], taken = !!box?.[GAME]?.[key];
  return { status: mine ? "won" : taken || final ? "lost" : "live", current: mine ? 1 : 0, target: 1, unit,
           text: mine ? "Scored first" : taken ? "Someone else scored first" : final ? `No ${unit}` : `No ${unit} yet` };
}

const DOUBLE_CATS: [string, string][] = [["points", "pts"], ["rebounds", "reb"], ["assists", "ast"], ["steals", "stl"], ["blocks", "blk"]];

/** A double-double (n 2) or triple-double (n 3): how many of points, rebounds, assists, steals and blocks are at 10+,
 *  the numbers that count, and how far the closest missing ones are ("18 pts · 7 reb · 3 reb to go"). Done the moment
 *  the nth reaches 10 (stats only go up). */
export function doubleState(row: Record<string, number> | null, n: number, final: boolean):
    Pick<LegLive, "status" | "current" | "target" | "unit" | "text"> {
  const vals = DOUBLE_CATS.map(([k, u]) => ({ u, v: row?.[k] ?? 0 })).sort((a, b) => b.v - a.v);
  const at10 = vals.filter((x) => x.v >= 10).length;
  const shown = vals.slice(0, Math.max(n, 2) + (n === 2 ? 1 : 0)).filter((x, i) => x.v > 0 || i < n).map((x) => `${x.v} ${x.u}`).join(" · ");
  const short = vals.filter((x) => x.v < 10).slice(0, Math.max(n - at10, 0)).map((x) => `${10 - x.v} ${x.u}`).join(", ");
  const done = at10 >= n;
  const text = done ? `Done: ${shown}` : !row ? "No stats yet" : `${shown} · ${short} ${final ? "short" : "to go"}`;
  return { status: done ? "won" : final ? "lost" : "live", current: Math.min(at10, n), target: n, unit: "at 10+", text };
}

const FOOTBALL = new Set(["nfl", "ncaaf"]);

/** A game total or a team's total against its line; landing on a whole-number line at the final is a push (void), as the
 *  grader settles it, not a loss (Nov 9; live_legs.total_state). */
function totalState(total: number, side: "over" | "under", point: number, final: boolean, unit: string):
    Pick<LegLive, "status" | "current" | "target" | "unit" | "text"> {
  const over = total > point;
  const status: LegStatus = final && total === point ? "void"
    : side === "over" ? (over ? "won" : final ? "lost" : "live") : (over ? "lost" : final ? "won" : "live");
  return { status, current: total, target: side === "over" ? Math.floor(point) + 1 : point, unit,
           text: status === "void" ? `Push at ${total}` : `${total} of ${point}` };
}

/** One leg's live state from its game and that game's box score. */
export function judge(label: string, g: GameLive | null, box: Record<string, Record<string, number>> | null,
                      heads?: Record<string, string> | null, onCourt?: string[] | null): LegLive {
  const p = parseLeg(label);
  // a team's own total ("New York Knicks over 110.5 points", Nov 9): the team's score, not a player named after it
  const ttSide = p?.kind === "prop" && g && !(box && findPlayer(box, p.player)) ? sideOf(p.player, g) : null;
  const totalSide = ttSide && g && teamMatch((p as { player: string }).player, g[ttSide]) >= 2 ? ttSide : null;
  const teamSide = p && (p.kind === "ml" || p.kind === "spread") && g ? sideOf(p.team, g) : totalSide;
  const team = teamSide && g ? g[teamSide] : null;
  const img = team?.logo ?? (p && "player" in p && heads ? findPlayer(heads, p.player) : null) ?? null;
  const card = team && g?.sport !== "ufc" ? { kind: "team" as const, name: team.name, abbr: team.abbr }
    : p && "player" in p ? { kind: "player" as const, name: p.player } : null;
  const court = onCourt && p && "player" in p ? findPlayer(Object.fromEntries(onCourt.map((n) => [n, true])), p.player) !== null : null;
  const base = { label, current: null, target: null, unit: "", text: "", gameKey: g?.key ?? null, img, card,
                 ...(court === null ? {} : { onCourt: court }) } as LegLive;
  if (!g) return { ...base, status: "pending", text: "Not live today" };
  if (!p) return { ...base, status: g.state === "pre" ? "pending" : "unknown", text: g.state === "pre" ? "Not started" : "Not tracked" };
  const final = g.state === "post", pre = g.state === "pre";
  const hs = g.home.score ?? 0, as = g.away.score ?? 0;
  const lead = (side: "home" | "away") => (side === "home" ? hs - as : as - hs);
  const outcome = (margin: number): LegStatus => (final ? (margin > 0 ? "won" : margin < 0 ? "lost" : "void")
    : margin > 0 ? "winning" : margin < 0 ? "losing" : "tied");

  if (p.kind === "ml") {
    const s = sideOf(p.team, g);
    if (!s) return { ...base, status: "unknown", text: "Team not found" };
    if (g.sport === "ufc") {
      const w = (g as any).winner as string | null;
      if (final) return { ...base, status: w === s ? "won" : w ? "lost" : "void", text: (g as any).result ?? g.detail };
      return { ...base, status: pre ? "pending" : "live", text: g.detail };
    }
    if (pre) return { ...base, status: "pending", text: "Not started" };
    // soccer's "to win" is 3-way: a draw loses it
    const st = outcome(lead(s));
    const status: LegStatus = g.sport === "soccer" && st === "void" ? "lost" : st;
    return { ...base, status, current: lead(s), text: `${lead(s) > 0 ? "Up" : lead(s) < 0 ? "Down" : "Level"} ${Math.abs(lead(s)) || ""}`.trim() };
  }
  if (p.kind === "spread") {
    const s = sideOf(p.team, g);
    if (!s) return { ...base, status: "unknown", text: "Team not found" };
    if (pre) return { ...base, status: "pending", text: "Not started" };
    const m = lead(s) + p.point;
    return { ...base, status: outcome(m), current: lead(s), text: m > 0 ? `Covering by ${m}` : m < 0 ? `Short by ${-m}` : "Right on the number" };   // Oct 24: "covering by -13.5" read wrong
  }
  if (p.kind === "draw" || p.kind === "draw_or" || p.kind === "btts_no" || p.kind === "no_draw" || p.kind === "not_win") {
    if (pre) return { ...base, status: "pending", text: "Not started" };
    if (p.kind === "btts_no") {
      const both = hs > 0 && as > 0;
      return { ...base, status: both ? "lost" : final ? "won" : "live", text: both ? "Both scored" : `${hs}-${as}` };
    }
    const s = p.kind === "draw_or" || p.kind === "not_win" ? sideOf(p.team, g) : "home";
    if (!s) return { ...base, status: "unknown", text: "Team not found" };
    const d = lead(s);
    const hit = p.kind === "draw" ? hs === as : p.kind === "no_draw" ? hs !== as : p.kind === "not_win" ? d <= 0 : d >= 0;
    return { ...base, status: final ? (hit ? "won" : "lost") : hit ? "winning" : "losing",
             text: d === 0 ? "Level" : d > 0 ? `${hs}-${as}` : `${as}-${hs}` };
  }
  if (p.kind === "total" || p.kind === "btts") {
    if (pre) return { ...base, status: "pending", text: "Not started", target: p.kind === "total" ? p.point : null };
    const total = hs + as;
    if (p.kind === "btts") {
      const both = hs > 0 && as > 0;
      return { ...base, status: both ? "won" : final ? "lost" : "live", text: both ? "Both scored" : `${hs}-${as}` };
    }
    return { ...base, ...totalState(total, p.side, p.point, final, "total") };
  }
  // player legs
  if (pre) {
    const target = p.kind === "prop" ? p.need : p.kind === "double" ? p.n : p.kind === "leader" ? null : 1;
    const unit = p.kind === "prop" || p.kind === "leader" ? UNIT[p.stat] ?? p.stat : p.kind === "td" ? "TD" : p.kind === "first" ? p.what : p.kind === "double" ? "at 10+"
      : p.kind === "card" ? "card" : "G+A";
    return { ...base, status: "pending", current: 0, target, unit, text: "Not started" };
  }
  const row = box ? findPlayer(box, p.player) : null;
  if (!row && p.kind === "prop" && totalSide) {
    if (p.stat !== "points" && p.stat !== "goals") return { ...base, status: "unknown", text: "Not tracked" };
    return { ...base, ...totalState(g[totalSide].score ?? 0, p.side, p.point, final, UNIT[p.stat]) };
  }
  const players = Object.keys(box ?? {}).filter((k) => k !== GAME);
  if (!row && !players.length && final) return { ...base, status: "unknown", text: "No box score" };   // never a guess
  // Nov 9: a basketball, hockey or soccer box lists everyone who dressed, so a player missing from it didn't play (yet):
  // void at the final, as the books settle it; football's leaves out players with no stats, so there he counts 0
  if (!row && players.length && !FOOTBALL.has(g.sport)) {
    const taken = p.kind === "first" && !!box?.[GAME]?.[p.what === "basket" ? "firstBasket" : "firstGoal"];
    if (!taken) return final ? { ...base, status: "void", text: "Didn't play" } : { ...base, status: "pending", current: 0, text: "Not in the box score yet" };
  }
  if (p.kind === "double") return { ...base, ...doubleState(row, p.n, final) };
  if (p.kind === "td") {
    const tds = row ? (row.rushingTouchdowns ?? 0) + (row.receivingTouchdowns ?? 0) : 0;
    if (p.first) return { ...base, ...firstState(row, box, "firstTd", final, "TD") };   // Nov 6: the scoring plays say whose was first
    return { ...base, status: tds >= 1 ? "won" : final ? "lost" : "live", current: tds, target: 1, unit: "TD", text: tds ? "Scored" : "No TD yet" };
  }
  if (p.kind === "goal_or_assist") {
    const n = row ? (row.totalGoals ?? 0) + (row.goalAssists ?? 0) : 0;
    return { ...base, status: n >= 1 ? "won" : final ? "lost" : "live", current: n, target: 1, unit: "G+A", text: n ? "Done" : "Not yet" };
  }
  if (p.kind === "first") return { ...base, ...firstState(row, box, p.what === "basket" ? "firstBasket" : "firstGoal", final, p.what) };
  if (p.kind === "card") {
    const n = row ? (row.yellowCards ?? 0) + (row.redCards ?? 0) : 0;
    return { ...base, status: n >= 1 ? "won" : final ? "lost" : "live", current: n, target: 1, unit: "card",
             text: n ? "Carded" : final ? "No card" : "No card yet" };
  }
  if (p.kind === "leader") {   // one player's count against everyone else's in the box (live_legs.judge)
    const mine = row ? statValue(row, p.stat, g.sport) ?? 0 : 0;
    const best = Math.max(0, ...Object.values(box ?? {}).filter((r) => r !== row).map((r) => statValue(r, p.stat, g.sport) ?? 0));
    const ahead = mine - best;
    // a tie for the most is a dead heat: the books pay a share, so it's a win (as the grader reads it) that rollup never
    // settles at the full price (Nov 9)
    if (final && ahead === 0 && mine > 0)
      return { ...base, status: "won", deadHeat: true, current: mine, target: best, unit: UNIT[p.stat] ?? p.stat, text: `Dead heat at ${mine}` };
    const status: LegStatus = final ? (ahead > 0 ? "won" : "lost") : ahead > 0 ? "winning" : ahead === 0 && mine > 0 ? "tied" : "losing";
    return { ...base, status, current: mine, target: best + (ahead <= 0 ? 1 : 0), unit: UNIT[p.stat] ?? p.stat,
             text: ahead > 0 ? `Most, by ${ahead}` : ahead === 0 && mine > 0 ? `Tied for most at ${mine}` : `${-ahead} behind the leader` };
  }
  const val = row ? statValue(row, p.stat, g.sport) : null;
  const cur = val ?? 0;                                   // not in the box yet = 0 (hasn't recorded one)
  const unit = UNIT[p.stat] ?? p.stat;
  if (final && cur === p.point) return { ...base, status: "void", current: cur, target: p.point, unit, text: `Push at ${cur}` };   // a whole-number line, exactly
  if (p.side === "over") {
    const hit = cur >= p.need;
    return { ...base, status: hit ? "won" : final ? "lost" : "live", current: cur, target: p.need, unit,
             text: hit ? "Hit" : final ? `Missed by ${p.need - cur}` : `${p.need - cur} to go` };
  }
  const busted = cur > p.point;
  return { ...base, status: busted ? "lost" : final ? "won" : "live", current: cur, target: p.point, unit,
           text: busted ? "Over the line" : final ? "Stayed under" : `${Math.floor(p.point - cur + 1)} of room` };
}

// ---------------------------------------------------------------------------------------- one bet

export type BetLive = { games: GameLive[]; legs: LegLive[]; status: "pending" | "live" | "won" | "lost" | "mixed"; hit: number; total: number;
  settle?: "won" | "lost" };

export function rollup(legs: LegLive[], games: GameLive[]): BetLive {
  const lost = legs.some((l) => l.status === "lost");
  const settled = legs.filter((l) => ["won", "void"].includes(l.status)).length;
  const status = lost ? "lost" : legs.length && settled === legs.length ? "won"
    : games.some((g) => g.state !== "pre") ? "live" : "pending";
  // settled from the live state alone (Mike, Oct 23): any lost leg, or every leg won outright (a voided leg's reduced
  // price is the grader's to work out, so a win with a void waits for it)
  // a dead heat ("most X" tied) pays a share too (Nov 9)
  const settle: BetLive["settle"] = lost ? "lost" : legs.length && legs.every((l) => l.status === "won" && !l.deadHeat) ? "won" : undefined;
  return { games, legs, status, hit: legs.filter((l) => l.status === "won").length, total: legs.length, ...(settle ? { settle } : {}) };
}
