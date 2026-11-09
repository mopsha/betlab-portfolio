import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { SlipUpload } from "@/components/build/SlipUpload";
import { chatReady } from "@/lib/chat";
import { promosData, settingsData } from "@/lib/data";
import { wallet } from "@/lib/promos";

export const dynamic = "force-dynamic";

/** My bets > Add (Oct 24): log a bet from a screenshot of the slip; a bonus or boosted slip offers the wallet token it used (Nov 9). */
export default async function AddBet() {
  const [settings, promos] = await Promise.all([settingsData(), promosData()]);
  return (
    <main className="rail">
      <BackLink fallback="/bets" label="Live" />
      <div className="head"><h1>Add a bet</h1></div>
      <p className="faint">A screenshot of your FanDuel, DraftKings or Novig slip: Claude reads the legs, odds, wager, bonus and boost,
        matches each game, and you confirm before it&apos;s saved.</p>
      <SlipUpload ready={chatReady()} unitDollars={settings.unit_dollars} tokens={wallet(promos).open} />
    </main>
  );
}
