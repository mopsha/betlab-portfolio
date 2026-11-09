import { isSettled, startOf } from "@/lib/bets";
import { friendBets, myBetsData, socialData } from "@/lib/data";
import { liveBets } from "@/lib/live-bets";
import { circle, feed, profileBets } from "@/lib/social";

export const dynamic = "force-dynamic";

const SETTLED_SHOWN = 40;   // the most recent settled bets get their final tracker; older ones keep the plain legs

/** My bets' live tracker (lib/live-bets.ts): the signed-in user's open bets, each game's score and clock and every
 * leg's live state from ESPN; with ?view=settled also the recent settled bets, read from their own game days. The page
 * polls it while a game is in progress. ?friends=all (or a friend's user id) tracks friends' shared bets instead (Friends,
 * Oct 27: friend_bets, accepted friends who share only): exactly the bets that page shows (Nov 9: the feed showed its 60
 * newest by placed time, the tracker took 40 settled by start, so some cards in the feed had no tracker). */
export async function GET(req: Request) {
  try {
    const q = new URL(req.url).searchParams;
    const settledView = q.get("view") === "settled", friends = q.get("friends");
    let list;
    if (friends === "all") {
      const [bets, s] = await Promise.all([friendBets(), socialData()]);
      list = feed(bets, circle(s.me, s.friendships, s.profiles).friends).map((x) => x.bet);
    } else if (friends) {
      const { open, recent } = profileBets(await friendBets(friends));
      list = [...open, ...recent];
    } else {
      const bets = (await myBetsData()).bets;
      list = [...bets.filter((b) => !isSettled(b)), ...(settledView ? bets.filter(isSettled)
        .sort((a, b) => String(startOf(b) ?? b.placed_at).localeCompare(String(startOf(a) ?? a.placed_at))).slice(0, SETTLED_SHOWN) : [])];
    }
    if (friends && !settledView) list = list.filter((b) => !isSettled(b));
    return Response.json(await liveBets(undefined, new Date(), list), { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return Response.json({ error: String((e as Error).message ?? e) }, { status: 500 });
  }
}
