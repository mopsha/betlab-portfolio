import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { WrappedStory } from "@/components/me/WrappedStory";
import { recordBets } from "@/lib/bets";
import { myBetsData } from "@/lib/data";
import { look } from "@/lib/headshots";
import { liveSettled, markLiveSettled } from "@/lib/live-bets";
import { isReal } from "@/lib/real";
import { periodName, periods, wrapped } from "@/lib/wrapped";

export const dynamic = "force-dynamic";

/** BetLab Wrapped (Mike's W17, Oct 27): a month, or the season, as a story you tap through. The bets are your record's
 *  (real money once it starts), so every number matches My bets. ?p=2026-10 or ?p=season; the newest month by default. */
export default async function WrappedPage({ searchParams }: { searchParams: Promise<{ p?: string }> }) {
  const sp = await searchParams;
  const d = await myBetsData();
  // bets the live tracker already settled count, as on My bets (its P/L and this one always agree)
  const bets = markLiveSettled(d.bets, await liveSettled(d.bets));
  const { counted } = recordBets(bets, isReal(new Date(), d.settings.real_from));
  const list = periods(counted);
  const p = sp.p && list.includes(sp.p) ? sp.p : list[0];
  const w = p ? wrapped(counted, p) : null;
  const photo = w?.player ? (await look("player", w.player.name, w.player.sport).catch(() => null))?.photo ?? null : null;
  return (
    <main className="rail wrapped-page">
      <div className="head"><h1>Wrapped</h1><BackLink fallback="/more" label="Me" /></div>
      {list.length > 1 && (
        <nav className="chips" aria-label="Which recap">
          {list.map((x) => (
            <Link key={x} href={`/wrapped?p=${x}`} aria-current={x === p ? "true" : undefined}>
              {periodName(x)}
            </Link>
          ))}
        </nav>
      )}
      {w ? <WrappedStory key={w.period} w={w} photo={photo} />
        : <div className="card empty"><b>Nothing to wrap yet</b><span>Your recap starts with your first graded bet.</span></div>}
    </main>
  );
}
