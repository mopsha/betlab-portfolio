// Every soccer club's logo and colors from ESPN's team directories (ported from the iPhone, ios/BetLab/Live/Live.swift
// SoccerClubs, Oct 24: "find a way to resolve ALL soccer logos + colors"). Our soccer games carry the books' club names
// and no competition, and the scoreboards only list a day's games, so a club is found by name in the directories of
// the leagues and cups we bet plus their neighbors, through `ALIASES` where the names differ. Pure but for `load`.
import { CLUB_ALIASES, espn, plain as livePlain, teamColor, type Fetcher } from "./live";

export type Club = { name: string; abbr: string; logo: string | null; color: string | null };

export const LEAGUES = ["eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "usa.1", "uefa.champions", "uefa.europa", "uefa.europa.conf",
  "eng.2", "esp.2", "ita.2", "ger.2", "fra.2", "por.1", "ned.1", "bel.1", "tur.1", "sco.1", "gre.1", "aut.1", "sui.1", "den.1",
  "nor.1", "swe.1", "cze.1", "cro.1", "pol.1", "srb.1", "rou.1", "bul.1", "cyp.1", "isr.1", "ukr.1", "uefa.champions_qual",
  "uefa.europa_qual", "uefa.europa.conf_qual"];

/** The books' names ESPN writes differently (plain form -> ESPN's display name): the live tracker's list. */
export const ALIASES: Record<string, string> = CLUB_ALIASES;
const GENERIC = new Set(["fc", "cf", "sc", "ac", "afc", "club", "city", "united", "real", "de", "sporting", "athletic", "the", "of",
  "st", "fk", "sk", "nk", "cd", "ud", "sd", "rc", "as", "jk", "bc", "tc", "aif", "if", "bk", "sv", "vfb", "vfl", "tsg", "fsv"]);

/** Lowercase ASCII words: accents off, ø/ł/æ/ß spelled out, "&" as "and". */
export const plain = (s: string) => livePlain(s.toLowerCase().replaceAll("ø", "o").replaceAll("ł", "l").replaceAll("æ", "ae")
  .replaceAll("ß", "ss").replaceAll("&", " and "));
const core = (p: string) => p.split(" ").filter((w) => !GENERIC.has(w)).join(" ");
const strong = (p: string) => new Set(p.split(" ").filter((w) => w.length >= 4 && !GENERIC.has(w)));

/** Clubs by every name form ESPN gives (display, short, name, location), from directory JSON. */
export function index(directories: any[]): Map<string, Club> {
  const out = new Map<string, Club>();
  for (const d of directories) {
    for (const t of d?.sports?.[0]?.leagues?.[0]?.teams ?? []) {
      const x = t.team ?? {};
      const club: Club = { name: x.displayName ?? "", abbr: x.abbreviation ?? "", logo: x.logos?.[0]?.href ?? null,
                           color: teamColor(x.color, x.alternateColor) };
      for (const n of [x.displayName, x.shortDisplayName, x.name, x.location]) {
        if (n && !out.has(plain(n))) out.set(plain(n), club);
      }
    }
  }
  return out;
}

/** A club by our name: an alias, the exact name, the name without generic words, else one club sharing a strong word. */
export function find(name: string, idx: Map<string, Club>): Club | null {
  const p = plain(name);
  const alias = ALIASES[p];
  if (alias && idx.get(plain(alias))) return idx.get(plain(alias))!;
  if (idx.get(p)) return idx.get(p)!;
  const cp = core(p);
  if (cp) {
    if (idx.get(cp)) return idx.get(cp)!;
    for (const [k, c] of idx) if (core(k) === cp) return c;
  }
  const sw = strong(p);
  if (!sw.size) return null;
  const hits = new Map<string, Club>();
  for (const [k, c] of idx) if ([...strong(k)].some((w) => sw.has(w))) hits.set(c.name, c);
  return hits.size === 1 ? [...hits.values()][0] : null;
}

/** The directories through the shared ESPN cache for a day (clubs' logos don't change mid-season). */
export async function load(get: Fetcher = espn): Promise<Map<string, Club>> {
  const dirs = await Promise.all(LEAGUES.map((l) => get(`https://site.api.espn.com/apis/site/v2/sports/soccer/${l}/teams?limit=300`, 86_400_000)));
  return index(dirs.filter(Boolean));
}
