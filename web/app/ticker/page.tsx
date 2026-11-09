import { SubHead } from "@/components/ui/Kit";
import { Ticker } from "@/components/live/Ticker";

export const dynamic = "force-dynamic";

/** Me > Extras > Desktop ticker (Nov 5, W35): your open bets in a small window beside your work. ?bare=1 is the popped-out window. */
export default async function TickerPage({ searchParams }: { searchParams: Promise<{ bare?: string }> }) {
  const { bare } = await searchParams;
  if (bare) return <Ticker bare />;
  return (
    <main className="rail">
      <SubHead title="Desktop ticker" />
      <Ticker />
    </main>
  );
}
