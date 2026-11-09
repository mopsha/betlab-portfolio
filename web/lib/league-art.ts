// A league's own logo for sport chips and parlay cards (the overhaul's pictures rule, Nov 4): ESPN's league art, the
// same host as the team logos. A league with none (college sports, plain "soccer") shows its monogram instead.
const E = "https://a.espncdn.com/i";
const SOCCER_ID: Record<string, number> = { epl: 23, la_liga: 15, bundesliga: 10, serie_a: 12, ligue_1: 9, mls: 19, ucl: 2, uel: 2310, uecl: 20296 };
const PLAIN = new Set(["nfl", "nba", "nhl", "ufc", "mlb", "wnba"]);

export function leagueLogo(league?: string | null): string | null {
  const k = String(league ?? "").toLowerCase();
  if (PLAIN.has(k)) return `${E}/teamlogos/leagues/500/${k}.png`;
  if (SOCCER_ID[k]) return `${E}/leaguelogos/soccer/500/${SOCCER_ID[k]}.png`;
  return null;
}

/** The letters a picture falls back to: a team's abbreviation, or the first letters of its name's words. */
export function monogram(name: string, abbr?: string | null): string {
  if (abbr) return abbr.slice(0, 4).toUpperCase();
  const words = name.replace(/[^\p{L}\p{N} ]/gu, " ").split(" ").filter(Boolean);
  if (!words.length) return "";
  return (words.length === 1 ? words[0].slice(0, 3) : words.slice(0, 3).map((w) => w[0]).join("")).toUpperCase();
}
