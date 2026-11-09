import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { FdTestLinks } from "@/components/me/FdTestLinks";
import { fdTestOffer } from "@/lib/data";

export const dynamic = "force-dynamic";

/** More > Settings > Test Open in FanDuel (Mike, 2026-10-04): from the home-screen app on iPhone,
 *  Open in FanDuel stayed in a browser. Each button opens FanDuel's New York site a different way;
 *  the one that lands in the FanDuel app becomes how every Open in FanDuel button works. */
export default async function FanDuelTestPage() {
  const offer = await fdTestOffer();
  return (
    <main className="rail">
      <BackLink fallback="/more/settings/links" label="Links" />
      <div className="head"><h1>Test Open in FanDuel</h1></div>
      <FdTestLinks offer={offer} />
    </main>
  );
}
