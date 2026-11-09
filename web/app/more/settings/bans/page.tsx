import { SubHead } from "@/components/ui/Kit";
import { BanList } from "@/components/me/BanList";
import { settingsData } from "@/lib/data";

/** Settings > Ban list (Oct 25): players and teams BetLab suggests no bets on. */
export default async function BansPage() {
  const s = await settingsData();
  return <main className="rail stg"><SubHead title="Ban list" back="/more/settings" backLabel="Settings" /><BanList bans={s.bans ?? []} /></main>;
}
