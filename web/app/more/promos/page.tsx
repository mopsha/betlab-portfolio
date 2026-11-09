import { SubHead } from "@/components/ui/Kit";
import { PromoWallet, type WalletBet } from "@/components/promos/PromoWallet";
import { myBetsData, promoSchedule, promosData } from "@/lib/data";

export const dynamic = "force-dynamic";

/** Me > Promos (Oct 30): the bonus bets and profit boosts you hold, and the best place for each (Use: Build).
 *  The last week's real bets come along for I used it (Oct 31): a token that went on a bet saved without it. */
export default async function PromosPage() {
  const [rows, { bets }, games] = await Promise.all([promosData(), myBetsData(), promoSchedule()]);
  const week = Date.now() - 8 * 86400_000;
  const recent: WalletBet[] = bets.filter((b) => b.mode === "real" && Date.parse(b.placed_at) >= week).map((b) => ({
    bet_id: b.bet_id, mode: b.mode, book: b.book ?? null, bonus: b.bonus ?? null, boost: b.boost ?? null, promo_id: b.promo_id ?? null,
    placed_at: b.placed_at, text: b.label ?? b.matchup ?? "A bet", price: b.price, stake: b.stake,
  }));
  const held = [...new Set(bets.map((b) => b.promo_id).filter((x): x is string => !!x))];
  return (
    <main className="rail">
      <SubHead title="Promos" />
      <PromoWallet rows={rows} bets={recent} held={held} games={games} />
    </main>
  );
}
