import { BuildModes } from "@/components/build/BuildModes";
import { SlipUpload } from "@/components/build/SlipUpload";
import { ScreenHead } from "@/components/ui/Kit";
import { chatReady } from "@/lib/chat";
import { promosData, settingsData } from "@/lib/data";
import { wallet } from "@/lib/promos";

export const dynamic = "force-dynamic";

/** Build › Check a slip (the overhaul, Nov 4): the slip reader (Live's + Add is the same one) as one of Build's three
 *  modes: a screenshot of a slip, each leg priced against the sharp books, then save it or leave it. */
export default async function CheckSlip() {
  const [settings, promos] = await Promise.all([settingsData(), promosData()]);
  return (
    <main className="rail">
      <ScreenHead title="Build" />
      <BuildModes on="check" />
      <p className="sub" style={{ margin: "0 0 12px" }}>A screenshot of your FanDuel, DraftKings or Novig slip: Claude reads the legs, odds, wager, bonus and boost,
        matches each game and prices it, and you confirm before anything is saved.</p>
      <SlipUpload ready={chatReady()} unitDollars={settings.unit_dollars} tokens={wallet(promos).open} />
    </main>
  );
}
