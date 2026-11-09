// Team cards and one card's lookup (Mike, Oct 25: "add cards for teams", and a tap on any leg's picture opens your
// stats with that player or team). Pure, so the tests run it. A team's legs: its moneyline and spread, and the game legs
// it can sink or carry, both teams to score and the totals, which count for both sides ("teams can also frick us on
// btts or over totals"). Each bet's games come from the live tracker's grouping (lib/live-bets.ts `groups`), so a
// ticket's legs land on the right game. UFC fights have no teams.
import { isSettled, statusOf } from "./bets";
import type { MyBet } from "./data";
import { sportName } from "./format";
import { normName, parseLeg, type Group } from "./live";
import { legResult, players, tally, type Entry, type Player } from "./players";
import TEAMS from "./teams.json";

export type CardKind = "player" | "team";
/** What a picture points at: a player by name, or a team by its name (and code, as ESPN shows it). */
export type CardRef = { kind: CardKind; name: string; abbr?: string | null };

const TEAM_STAT: Record<string, string> = { ml: "moneyline", spread: "spread", total: "total", btts: "both teams to score" };

/** A team's full name: NFL, NBA and NHL legs and matchups often carry codes ("OTT to win", "FLA @ CHI"). */
export function fullName(sport: string | null | undefined, n: string): string {
  const list = (TEAMS as Record<string, { name: string; abbr: string[] }[]>)[String(sport ?? "")] ?? [];
  return list.find((t) => t.abbr.includes(n.trim()))?.name ?? n.trim();
}

const sides = (matchup: string): string[] => {
  const [a, b] = matchup.split(/ @ | vs\.? | v /);
  return a && b ? [a.trim(), b.trim()] : [];
};

/** Every team leg in a bet: (team, leg), in order, with its graded result. `grps`: the bet's games (`groups`). */
export function teamLegs(b: MyBet, grps: Group[]): Entry[] {
  const results = b.leg_results ?? [];
  const used = new Set<number>();
  const settled = isSettled(b), s = statusOf(b);
  const all = grps.reduce((n, g) => n + g.legs.length, 0);
  const out: Entry[] = [];
  for (const g of grps) {
    for (const label of g.legs) {
      const i = results.findIndex((r, k) => !used.has(k) && r.leg === label);
      if (i >= 0) used.add(i);
      if (g.sport === "ufc") continue;
      const p = parseLeg(label);
      if (!p) continue;
      const names = p.kind === "ml" || p.kind === "spread" ? [p.team] : p.kind === "total" || p.kind === "btts" ? sides(g.matchup) : [];
      const leg = { label, stat: TEAM_STAT[p.kind], result: legResult(i >= 0 ? results[i].result : null, settled, all, s),
                    day: b.placed_at.slice(0, 10), betId: b.bet_id, ...(p.kind === "total" || p.kind === "btts" ? { game: g.matchup } : {}) };
      for (const n of names) {
        if (/^draw$/i.test(n)) continue;
        const name = fullName(g.sport, n);
        out.push({ key: normName(name), name, sport: g.sport ? sportName(g.sport) : "Other", leg, bet: b });
      }
    }
  }
  return out;
}

/** Your teams, most-bet first. `grps(b)`: each bet's games. */
export function teams(bets: MyBet[], grps: (b: MyBet) => Group[], min = 2): Player[] {
  return tally(bets.flatMap((b) => teamLegs(b, grps(b))), min);
}

const CLUB = new Set(["fc", "cf", "sc", "afc", "ac", "and", "the"]);
const words = (n: string) => normName(n).split(" ").filter((w) => w && !CLUB.has(w));

/** One team under two spellings: the same name, or one's words all inside the other's ("Genoa" / "Genoa CFC",
 *  "Bournemouth" / "AFC Bournemouth", "Brighton and Hove Albion" / "Brighton & Hove Albion"). Never a shared city:
 *  the Knicks' card took the Rangers, Islanders, Jets, Giants and NYCFC legs (Oct 25) when it matched on parts. */
export function sameTeam(a: string, b: string): boolean {
  const x = words(a), y = words(b);
  if (!x.length || !y.length) return false;
  const [short, long] = x.length <= y.length ? [x, y] : [y, x];
  return short.every((w) => long.includes(w)) && (short.length > 1 || long.length <= 2);
}

/** The one card a picture points at, from every bet (one leg is enough); null when you've never bet on them. A team
 *  matches on its full name (legs' codes are made full names first, "OTT" -> "Ottawa Senators"), see sameTeam. */
export function cardOf(bets: MyBet[], grps: (b: MyBet) => Group[], ref: CardRef): Player | null {
  if (ref.kind === "player") {
    const want = normName(ref.name);
    return players(bets, 1).find((p) => p.key === want) ?? null;
  }
  const mine = (n: string) => sameTeam(n, ref.name);
  const entries = bets.flatMap((b) => teamLegs(b, grps(b))).filter((e) => mine(e.name));
  if (!entries.length) return null;
  const name = entries[0].name;
  return tally(entries.map((e) => ({ ...e, key: normName(name), name })), 1)[0] ?? null;
}
