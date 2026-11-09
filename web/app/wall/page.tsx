import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { Wall } from "@/components/live/Wall";
import { openBetNames, settingsData } from "@/lib/data";

export const dynamic = "force-dynamic";

/** The wall (Mike's W7, Oct 24): every game you have money on, one tile each, live, in your own order (drag a tile's
 *  grip). Made for a laptop or a TV. */
export default async function WallPage() {
  const [open, settings] = await Promise.all([openBetNames(), settingsData()]);
  const names = Object.fromEntries(open.map((b) => [b.id, b.name]));
  return (
    <main className="wall">
      <div className="head"><h1>The wall</h1><BackLink fallback="/bets" label="Live" /></div>
      <Wall names={names} order={settings.wall_order ?? []} />
    </main>
  );
}
