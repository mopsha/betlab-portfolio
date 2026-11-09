// "Open in FanDuel" (Mike, 2026-09-30). Links come from the odds feed, matched to each bet by
// links.py, on the New York host so FanDuel skips its "pick your state" screen (Oct 1). A parlay's
// legs go into one link (marketId[i] / selectionId[i]), the format FanDuel's own bet sharing uses.
// Bets are only added to the betslip; Mike reviews and places them in FanDuel.
const FD_HOST = "https://ny.sportsbook.fanduel.com";
export const nyLink = (u: string) => u.replace(/^https?:\/\/(?:[a-z]{2}\.)?sportsbook\.fanduel\.com/, FD_HOST);

export function fdHref(links: (string | null | undefined)[]): string | null {
  const ok = links.filter((x): x is string => !!x);
  if (!ok.length) return null;
  // one link out of a parlay's legs would open as a single bet, which reads as a broken parlay (Nov 5: 1 of 8)
  if (ok.length === 1) return links.length === 1 ? nyLink(ok[0]) : null;
  const parts = ok.flatMap((u, i) => {
    try {
      const q = new URL(u).searchParams;
      return [`marketId[${i}]=${encodeURIComponent(q.get("marketId") ?? "")}&selectionId[${i}]=${encodeURIComponent(q.get("selectionId") ?? "")}`];
    } catch { return []; }
  });
  return `${FD_HOST}/addToBetslip?${parts.join("&")}`;
}

// From the home-screen app, iOS opens web links in its own browser and never hands them to FanDuel's
// app (Mike's tests, Oct 6: five web-link variants all stayed in a browser). FanDuel's app scheme does
// open it, and with the host kept in the path (round 3 "K") the bet lands in the betslip.
export const FD_APP_SCHEME = "fanduelsportsbook://";
export const appLink = (href: string) => href.replace(/^https?:\/\//, FD_APP_SCHEME);
export const isIOS = (ua: string) => /iPhone|iPad|iPod/.test(ua);

/** Legs whose link is the book's main market, which keeps its id when its line moves, so the slip can open at a new
 *  number (Oct 30: Brunson's "over 1.5 threes" opened as Over 2.5). Ladder rungs are fixed; these aren't (unders,
 *  combos, some spreads and totals): say to check them (Mike: "Keep, flag them"). iPhone `Build.mainLineText`. */
export function mainLineText(flags: unknown[], book = "FanDuel"): string | null {
  const n = flags.filter(Boolean).length;
  if (!n) return null;
  const its = book.endsWith("s") ? `${book}'` : `${book}'s`;
  return n === 1 && flags.length === 1
    ? `Check the number on ${its} slip: this link follows ${its} main line, which can move.`
    : `Check the number on ${n} of these legs on ${its} slip: their links follow ${its} main line, which can move.`;
}
