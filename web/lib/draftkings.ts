// "Open in DraftKings" (docs/DRAFTKINGS_PLAN.md, day 3, Oct 12). The odds feed gives every DraftKings outcome a
// betslip link, `https://sportsbook.draftkings.com/?outcomes=<outcome id>`, matched to each bet by links.py. One
// host serves every state (DraftKings reads the state from its location check). Bets are only added to the
// betslip; the bettor reviews and places them in DraftKings.
//
// Settled by Mike's iPhone test (More > Settings > Test Open in DraftKings, Oct 13): unlike FanDuel's (lib/fanduel.ts),
// DraftKings' plain web link opens its app from the home-screen app (round 1 "A"), and the feed's link lands the
// bet in the betslip (round 2 "E"), so no app-scheme rewrite is needed. dksb:// also opens the app ("B") and
// dksb://sb/addbet/<id> lands the bet too ("F"). A parlay is its outcome ids joined by "+" in one `outcomes`
// parameter: both the bare "+" ("I") and "%2B" ("J") put both bets in one betslip; we send "%2B", which no
// parser can read as a space.
export const DK_HOST = "https://sportsbook.draftkings.com";

/** The outcome id in a DraftKings link ("0ML84695534_3"), or null. */
export function outcomeId(u: string): string | null {
  try { return new URL(u).searchParams.get("outcomes"); } catch { return null; }
}

/** One DraftKings link for a bet or a parlay, or null unless every leg has a DraftKings link (a partial slip would
 *  open a different bet than the one priced). */
export function dkHref(links: (string | null | undefined)[]): string | null {
  if (!links.length || links.some((x) => !x || !x.includes("draftkings.com"))) return null;
  if (links.length === 1) return links[0]!;
  const ids = links.map((u) => outcomeId(u!));
  if (ids.some((x) => !x)) return null;
  return `${DK_HOST}/?outcomes=${ids.map((x) => encodeURIComponent(x!)).join("%2B")}`;
}
