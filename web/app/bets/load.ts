import "server-only";
// What Live and the pages that left it for Me (Record, Stats, Ladder, Prices; the overhaul, Nov 4) all start from: the
// account's bets with the live tracker's settles applied, and the real-money split. One loader, so every page counts
// the same bets the same way.
import { isSettled, recordBets } from "@/lib/bets";
import { myBetsData } from "@/lib/data";
import { liveSettled, markLiveSettled } from "@/lib/live-bets";
import { isReal } from "@/lib/real";

export async function betsView() {
  const d0 = await myBetsData();
  // a bet the live tracker already shows as lost (or won, every leg) is settled now, before the worker grades it (Oct 23)
  const settledLive = await liveSettled(d0.bets);
  const d = { ...d0, bets: markLiveSettled(d0.bets, settledLive) };
  // From the account's real-money start (Oct 18), the record, By book, Settled and the fun bucket count real bets
  // only, from 0-0; paper shows apart (recordBets)
  const { useReal: hasReal, counted, paper } = recordBets(d.bets, isReal(new Date(), d.settings.real_from));
  return { d, settledLive, hasReal, counted, paper, open: d.bets.filter((b) => !isSettled(b)) };
}
