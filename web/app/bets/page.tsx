import Link from "next/link";
import { redirect } from "next/navigation";
import { BetCard } from "@/components/live/BetCard";
import { LiveCount, LiveProvider } from "@/components/live/LiveBets";
import { Wall } from "@/components/live/Wall";
import { RefreshControl } from "@/components/app/RefreshControl";
import { IconLink, ScreenHead } from "@/components/ui/Kit";
import { refreshData } from "@/lib/refresh";
import { dayOf, isBonus, isSettled, stakeOf, startOf } from "@/lib/bets";
import { myId, reactionsFor, type MyBet } from "@/lib/data";
import type { Reaction } from "@/lib/social";
import { RxHost } from "@/components/friends/Reactions";
import { betName } from "@/lib/gameday";
import { longDay } from "@/lib/format";
import { betsView } from "./load";

const VIEWS = [["open", "Open"], ["settled", "Settled"], ["wall", "Wall"]] as const;
type View = (typeof VIEWS)[number][0];
// Record, Stats, Ladder and Prices live under Me since the overhaul (Nov 4): their old links land there
const MOVED: Record<string, string> = { record: "/more/record", stats: "/more/stats", ladder: "/more/ladder", prices: "/more/prices" };

/** Who reacted to your bets (0042): the bubble on the card's edge, no picker (a reaction is a friend's). */
type Rx = { list: Reaction[]; me: string };

function byDay(bets: MyBet[], newestFirst: boolean, fold = false, rx?: Rx) {
  const sorted = [...bets].sort((a, b) => {
    const x = String(startOf(a) ?? a.placed_at), y = String(startOf(b) ?? b.placed_at);
    return newestFirst ? y.localeCompare(x) : x.localeCompare(y);
  });
  let last = "";
  return sorted.flatMap((b) => {
    const d = dayOf(b);
    const head = d !== last ? <h2 className="day" key={`d-${d}`}>{longDay(d)}</h2> : null;
    last = d;
    const mine = rx?.list.filter((r) => r.bet_id === b.bet_id) ?? [];
    const card = <BetCard key={b.bet_id} b={b} fold={fold} />;
    return [head, mine.length ? <RxHost key={b.bet_id} betId={b.bet_id} list={mine} me={rx!.me} canReact={false}>{card}</RxHost> : card];
  });
}

/** Live (the overhaul, Nov 4; My bets before): your open bets as live cards, what's settled, and the wall. */
export default async function Live({ searchParams }: { searchParams: Promise<{ view?: string; tab?: string }> }) {
  const sp = await searchParams;
  const asked = sp.view ?? sp.tab ?? "";
  if (MOVED[asked]) redirect(MOVED[asked]);
  const view = (VIEWS.some(([k]) => k === asked) ? asked : "open") as View;
  const [{ d, settledLive, hasReal, counted, paper, open }, grading] = await Promise.all([betsView(), refreshData("grade")]);
  const settled = counted.filter(isSettled), paperSettled = hasReal ? paper.filter(isSettled) : [];
  const inPlay = open.filter((b) => !isBonus(b)).reduce((s, b) => s + stakeOf(b), 0);
  // reactions only reach recent bets (a friend reacts in the feed, which shows the newest 60)
  const recentIds = [...open, ...settled].filter((b) => Date.now() - Date.parse(b.placed_at) < 14 * 86400_000).map((b) => b.bet_id);
  const rx: Rx = { list: await reactionsFor(recentIds).catch(() => []), me: await myId() };
  const names = Object.fromEntries(open.map((b) => { const n = betName(b); return [b.bet_id, n.startsWith("Bet") ? b.matchup ?? n : n]; }));

  return (
    <main className={view === "wall" ? "rail livepage live-wall" : "rail livepage"}>
      {d.fixture && <p className="banner">Local preview: sample bets, no sign-in. Changes reset when the preview restarts.</p>}
      <ScreenHead title="Live">
        <RefreshControl initial={grading} job="grade" icon />
        <IconLink href="/bets/add" icon="plus" label="Add a bet from a slip" />
      </ScreenHead>
      <nav className="segx" aria-label="View">
        {VIEWS.map(([k, l]) => (
          <Link key={k} href={k === "open" ? "/bets" : `/bets?view=${k}`} aria-current={k === view ? "page" : undefined}>
            {l}{k === "open" && open.length ? ` ${open.length}` : ""}
          </Link>
        ))}
        <span className="segx-right">{inPlay > 0 ? `${inPlay.toFixed(1)}u in play` : !hasReal ? "paper until Oct 18" : ""}</span>
      </nav>

      {view === "open" && (open.length ? <LiveProvider known={[...settledLive.keys()]}>
        <div className="live-sub"><LiveCount /><span /></div>
        <div className="live-feed">{byDay(open, false, false, rx)}</div></LiveProvider> : (
        <div className="card empty">
          <b>No open bets</b>
          <span>Tap I placed this on a pick, lean or parlay and it shows up here until it&apos;s graded.</span>
          <Link href="/">Back to Today</Link>
        </div>
      ))}

      {view === "settled" && (settled.length ? <LiveProvider src="/api/live?view=settled" known={[...settledLive.keys()]}>
        <div className="live-feed">{byDay(settled, true, true, rx)}</div></LiveProvider> : (
        <div className="card empty"><b>Nothing settled yet</b><span>{hasReal ? "Real bets" : "Bets"} show up here the morning after their game, graded with CLV.</span></div>
      ))}
      {view === "settled" && paperSettled.length > 0 && (
        <details className="fold"><summary>Paper bets <span className="n">{paperSettled.length}</span></summary>
          <div className="live-feed">{byDay(paperSettled, true)}</div>
        </details>
      )}
      {view === "settled" && <p className="note" style={{ marginTop: 14 }}>Your record, stats and prices are under <Link href="/more">Me</Link>.</p>}

      {view === "wall" && (
        <>
          <p className="sub live-wallnote">Every game you have a bet on, one tile each. Drag a tile by its grip to arrange them. <Link href="/wall">Full screen ›</Link></p>
          <Wall names={names} order={d.settings.wall_order ?? []} />
        </>
      )}
    </main>
  );
}
