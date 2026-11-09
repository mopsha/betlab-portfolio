import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { DkTestLinks } from "@/components/me/DkTestLinks";
import { dkTestOffers } from "@/lib/data";

export const dynamic = "force-dynamic";

/** More > Settings > Test Open in DraftKings (docs/DRAFTKINGS_PLAN.md, day 3): which link opens DraftKings' app
 *  from the home-screen app, whether a bet lands in the betslip, and how two bets combine into a parlay. The
 *  answers decide how every Open in DraftKings button works (lib/draftkings.ts), as FanDuel's test did. */
export default async function DraftKingsTestPage() {
  const offers = await dkTestOffers();
  return (
    <main className="rail">
      <BackLink fallback="/more/settings/links" label="Links" />
      <div className="head"><h1>Test Open in DraftKings</h1></div>
      <DkTestLinks offers={offers} />
    </main>
  );
}
