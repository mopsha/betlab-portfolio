import { BadgesAnchor } from "@/components/me/BadgesAnchor";
import { RecordSwitch } from "@/components/me/RecordSwitch";
import { StatsView } from "@/components/me/StatsView";
import { betsView } from "@/app/bets/load";

/** Me › Stats (in My bets until the overhaul, Nov 4): units over time, streaks, the record every way, achievements,
 *  and your player and team cards. */
export default async function Stats() {
  const { counted, hasReal } = await betsView();
  return (
    <main className="rail">
      <RecordSwitch on="stats" />
      <StatsView bets={counted} real={hasReal} />
      <BadgesAnchor />
    </main>
  );
}
