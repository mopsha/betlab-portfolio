import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { Challenges } from "@/components/promos/Challenges";
import { challengeHistoryData, challengesData } from "@/lib/data";
import { etDay } from "@/lib/time";

export const dynamic = "force-dynamic";

/** More > Novig challenges (Oct 28): today's Novig Points challenges, each one's best bet and when it's ripe. */
export default async function ChallengesPage() {
  const today = etDay(new Date());
  const [items, history] = await Promise.all([challengesData(today), challengeHistoryData(today)]);
  return (
    <main className="wide">
      <BackLink fallback="/more" label="Me" />
      <div className="head"><h1>Novig challenges</h1></div>
      <Challenges items={items} history={history} />
    </main>
  );
}
