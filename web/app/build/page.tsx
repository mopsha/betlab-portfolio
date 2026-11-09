import { redirect } from "next/navigation";
import { Builder } from "@/components/build/Builder";
import { gameArt } from "@/lib/art";
import { gamePair } from "@/lib/pictures";
import { promoFromParams } from "@/lib/builder";
import { buildData, openMarks, promosData } from "@/lib/data";
import { wallet } from "@/lib/promos";

/** Build your own parlay. The header (book, saved parlays, search), the modes and everything under them are the
 *  Builder's (the book is its state); your saved parlays have their own page, /build/saved (Nov 5). */
export default async function Build({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const [{ games, bands, quoteModel, customs, bans }, marks, tokens, sp] = await Promise.all([buildData(), openMarks(), promosData().catch(() => []), searchParams]);
  if (sp.promo_id) redirect(`/build/promo?promo_id=${encodeURIComponent(sp.promo_id)}`);   // a wallet token: the finder (Oct 30)
  const preset = promoFromParams(sp);       // a promo from the helper's link (/promo, Oct 24)
  // each game's two logos for the strip, the main lines and the slip (ESPN's boards; a slow one never holds the page)
  const boards = await Promise.race([
    gameArt(games.map((g) => ({ game_id: g.event_id, league: g.sport, odds_event_id: null, home: null, away: null, matchup: g.matchup,
      commence_time: g.commence_time, state: null, home_score: null, away_score: null }))).catch(() => ({}) as Awaited<ReturnType<typeof gameArt>>),
    new Promise<Awaited<ReturnType<typeof gameArt>>>((r) => setTimeout(() => r({}), 2500))]);
  const art = Object.fromEntries(Object.entries(boards).map(([id, g]) => [id, gamePair(g)]));
  return (
    <main className="wide bd-page">
      <Builder games={games} bands={bands} quoteModel={quoteModel} art={art}
               saved={customs.map((c) => ({ sgp_id: c.sgp_id, grade: c.grade, price: c.price == null ? null : Number(c.price) }))}
               marked={marks} preset={preset} bans={bans} promos={wallet(tokens).open} />
    </main>
  );
}
