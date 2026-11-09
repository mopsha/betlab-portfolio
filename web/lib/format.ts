// Odds math and the app's one name for everything (Mike, 2026-10-01: names must match everywhere).

export const MINUS = "−";
export const ET = "America/New_York";

export const SPORTS: Record<string, string> = {
  nfl: "NFL", ncaaf: "College football", nhl: "NHL", nba: "NBA", ncaab: "College basketball",
  soccer: "Soccer", ufc: "UFC", mlb: "MLB", wnba: "WNBA",
};
export const SPORT_SHORT: Record<string, string> = {
  nfl: "NFL", ncaaf: "CFB", nhl: "NHL", nba: "NBA", ncaab: "CBB", soccer: "Soccer", ufc: "UFC", mlb: "MLB", wnba: "WNBA",
};
export const sportName = (k?: string | null) => SPORTS[String(k ?? "").toLowerCase()] ?? "Soccer";

const MARKET: Record<string, string> = { h2h: "Moneyline", spreads: "Spread", totals: "Total", h2h_3_way: "Result (3-way)" };
export const marketName = (m?: string | null) =>
  String(m ?? "").startsWith("player_") ? "Player prop" : MARKET[String(m)] ?? String(m ?? "");

export const bookName = (b?: string | null) =>
  ({ fanduel: "FanDuel", draftkings: "DraftKings", "draft kings": "DraftKings", pinnacle: "Pinnacle" } as Record<string, string>)[
    String(b ?? "").toLowerCase()] ?? (b ?? "");

export const num = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export function fmtAm(v: unknown): string {
  const a = num(v);
  if (a === null) return "—";
  return (a >= 0 ? "+" : MINUS) + Math.round(Math.abs(a));
}

export function pct(v: unknown, d = 0): string {
  const p = num(v);
  return p === null ? "—" : (p * 100).toFixed(d) + "%";
}

export function signed(v: unknown, d = 1, suffix = "%", scale = 100): string {
  const x = num(v);
  if (x === null) return "—";
  return (x >= 0 ? "+" : MINUS) + Math.abs(x * scale).toFixed(d) + suffix;
}

export const toDec = (a: number) => (a > 0 ? 1 + a / 100 : 1 + 100 / -a);
export const toAm = (d: number) => (d >= 2 ? (d - 1) * 100 : -100 / (d - 1));
export const implied = (a: number) => 1 / toDec(a);

/** Odds typed by a person ("-110", "+150", "150", "−110"). */
export function parseOdds(v: string): number | null {
  const n = Number(String(v).trim().replace(MINUS, "-").replace(/^\+/, ""));
  return Number.isFinite(n) && (n >= 100 || n <= -100) ? n : null;
}

/** Bet labels with a real minus sign. */
export const label = (s?: string | null) => String(s ?? "").replace(/ -(\d)/g, ` ${MINUS}$1`).replace(/^-(\d)/, `${MINUS}$1`);

export function time(iso?: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-US", { timeZone: ET, hour: "numeric", minute: "2-digit" });
}

export function dayTime(iso?: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-US", { timeZone: ET, weekday: "short", hour: "numeric", minute: "2-digit" });
}

/** "Thursday, Oct 1" */
export function longDay(day: string): string {
  return new Date(day + "T12:00:00Z").toLocaleDateString("en-US", { timeZone: "UTC", weekday: "long", month: "short", day: "numeric" });
}

/** The scorecard's market names ("NCAAF totals") in the app's words ("College football totals"). */
/** Soccer's leagues and the Odds API's soccer keys ("soccer", "epl", "uecl", "soccer_uefa_europa_league"). */
export const isSoccer = (sport?: string | null) =>
  /^(soccer|epl|la_liga|serie_a|bundesliga|ligue_1|mls|ucl|uel|uecl)(?![a-z])/.test(String(sport ?? "").toLowerCase());

/** Soccer reads home team first (Mike, Nov 5): our stored "Away @ Home" (every parser still reads that) is shown as
 *  "Home vs Away", each match of a ticket's list too. Other sports as stored. iPhone Fmt.matchup; fixture
 *  tests/fixtures/soccer_matchups.json. */
export function matchupText(text?: string | null, sport?: string | null): string {
  const s = String(text ?? "");
  return isSoccer(sport) ? s.replace(/(^|[,:]\s*)([^,:]+?) @ ([^,]+?)(?=,|$)/g, (_, pre, away, home) => `${pre}${home.trim()} vs ${away.trim()}`) : s;
}

/** A game's two sides in reading order: home first for soccer, away first for the rest. */
export const inOrder = <T,>(sport: string | null | undefined, away: T, home: T): [T, T] => isSoccer(sport) ? [home, away] : [away, home];

export const scoreName = (m: string) => m.replace(/^NCAAF\b/, "College football").replace(/^NCAAB\b/, "College basketball").replace(/^MLS\b/, "Soccer (MLS)");
