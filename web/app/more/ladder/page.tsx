import { LadderView } from "@/components/me/Ladder";
import type { ArtOf } from "@/components/ui/Art";
import { SubHead } from "@/components/ui/Kit";
import { sampleLadder } from "@/components/ladder/sample";
import { gameArt } from "@/lib/art";
import { ladderData, type Game } from "@/lib/data";
import { stepName, stepOptions } from "@/lib/ladder";
import { fixtureMode } from "@/lib/mode";
import { gamePair, legArt } from "@/lib/pictures";
import { betsView } from "@/app/bets/load";

const soon = <T,>(p: Promise<T>, fallback: T, ms = 2500) => Promise.race([p.catch(() => fallback), new Promise<T>((r) => setTimeout(() => r(fallback), ms))]);
type Boards = Awaited<ReturnType<typeof gameArt>>;

/** Me › Ladder (in My bets until the overhaul, Nov 4): roll the stack bet to bet toward a target, outside the 5u cap. */
export default async function LadderPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const [{ d }, sp] = await Promise.all([betsView(), searchParams]);
  const ladder = await ladderData(d.settings.bans ?? []);
  let ladders = ladder.ladders, bets = d.bets;
  // the local preview only: invented ladders when the fixture carries none (?empty=1 shows the start instead)
  if (fixtureMode() && !ladders.length && sp.empty !== "1") {
    const o = stepOptions(ladder.offers, Date.now(), null, "FanDuel")[0] ?? ladder.offers[0];
    const s = sampleLadder(Date.now(), o ? { ...o, tier: o.tier } : undefined);
    ladders = s.ladders; bets = [...bets, ...s.bets];
  }

  // pictures (the overhaul's rule): each possible step's player or team, the locked step's, and every past step's
  // a step read from a slip has no league of its own (Nov 6: its pictures were missing): its game's id says it
  const leagueOf = (b: (typeof bets)[number]) => b.league ?? b.sport ?? (() => {
    const ref = String(b.games?.[0]?.game_ref ?? "");
    return /^\d{4}_\d{2}_/.test(ref) ? "nfl" : (/^(nba|nhl|ncaab|ncaaf|ufc|soccer)[|:]/.exec(ref)?.[1] ?? "");
  })();
  const steps = bets.filter((b) => b.ladder_id && leagueOf(b));
  const locked = ladders.flatMap((l) => (l.locked ? [l.locked] : []));
  const offers = ladder.offers.slice(0, 40);
  const game = (id: string, league: string, matchup: string | null, at: string | null): Game =>
    ({ game_id: id, league, odds_event_id: null, home: null, away: null, matchup, commence_time: at, state: null, home_score: null, away_score: null });
  const art = await soon((async () => {
    const boards: Boards = await gameArt([
      ...offers.map((o) => game(`o:${o.offer_id}`, o.league, o.matchup, o.commence_time)),
      ...locked.map((k) => game(`o:${k.offer_id}`, k.league ?? "", k.matchup, k.commence_time)),
      ...steps.map((b) => game(`b:${b.bet_id}`, leagueOf(b), b.matchup, b.pick_commence_time ?? b.ticket_commence_time ?? b.placed_at)),
    ]);
    const of = async (key: string, label: string, league: string, player?: string | null): Promise<[string, ArtOf[]]> => {
      const a = await legArt(label, league, boards[key], player).catch(() => null);
      return [key.slice(2), a ? [a] : gamePair(boards[key])];
    };
    return Object.fromEntries(await Promise.all([
      ...offers.map((o) => of(`o:${o.offer_id}`, o.label, o.league, o.player)),
      ...locked.map((k) => of(`o:${k.offer_id}`, k.label, k.league ?? "")),
      ...steps.map((b) => of(`b:${b.bet_id}`, stepName(b), leagueOf(b))),
    ]));
  })(), {} as Record<string, ArtOf[]>, 3000);

  return (
    <main className="rail">
      <SubHead title="Ladder" />
      <LadderView ladders={ladders} bets={bets} offers={ladder.offers} games={ladder.games} dayEnd={ladder.dayEnd} art={art} />
    </main>
  );
}
