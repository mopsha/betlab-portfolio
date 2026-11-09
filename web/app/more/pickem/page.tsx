import { BackLink } from "@/components/ui/BackLink";
import { Pickem } from "@/components/promos/Pickem";
import { pickemData, pickemHistoryData } from "@/lib/data";
import { weekOf } from "@/lib/pickem";
import { etDay } from "@/lib/time";

export const dynamic = "force-dynamic";

/** Me > Extras > CFB Pick'em (Nov 7): this week's FanDuel College Football Pick'em entry, each frozen line priced
 *  against the sharp market, the side to take, and the score once graded. */
export default async function PickemPage() {
  const week = weekOf(etDay(new Date()));
  const [rows, history] = await Promise.all([pickemData(week), pickemHistoryData(week)]);
  return (
    <main className="wide">
      <BackLink fallback="/more" label="Me" />
      <div className="head"><h1>CFB Pick&apos;em</h1></div>
      <Pickem week={week} rows={rows} history={history} />
    </main>
  );
}
