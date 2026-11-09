import { BuildModes } from "@/components/build/BuildModes";
import { ScreenHead } from "@/components/ui/Kit";
import { PromoFinder } from "@/components/promos/PromoFinder";
import { gameArt } from "@/lib/art";
import { buildData, promosData, settingsData, unitOf } from "@/lib/data";
import { gamePair } from "@/lib/pictures";
import { wallet } from "@/lib/promos";

export const dynamic = "force-dynamic";

type Boards = Awaited<ReturnType<typeof gameArt>>;

/** Build > Use a promo (Oct 30): the best place for a bonus bet or boost, in a slice, games you pick, one game, or
 *  today; ?promo_id= from the wallet, ?game= from a game page. */
export default async function PromoFinderPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const [{ games, bands, quoteModel, bans }, rows, settings, sp] = await Promise.all([buildData(), promosData(), settingsData(), searchParams]);
  // each game's two logos for the game choices and the results' legs (ESPN's boards, as Build; a slow one never holds the page)
  const boards = await Promise.race([
    gameArt(games.map((g) => ({ game_id: g.event_id, league: g.sport, odds_event_id: null, home: null, away: null, matchup: g.matchup,
      commence_time: g.commence_time, state: null, home_score: null, away_score: null }))).catch(() => ({}) as Boards),
    new Promise<Boards>((r) => setTimeout(() => r({}), 2500))]);
  const art = Object.fromEntries(Object.entries(boards).map(([id, g]) => [id, gamePair(g)]));
  return (
    <main className="wide pfpage">
      <ScreenHead title="Build" />
      <BuildModes on="promo" />
      <PromoFinder games={games} bands={bands} quoteModel={quoteModel} bans={bans} promos={wallet(rows).open} art={art}
                   start={sp.promo_id ?? null} startGame={sp.game ?? null} unitDollars={unitOf(settings)} />
    </main>
  );
}
