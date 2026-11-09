import { redirect } from "next/navigation";

/** The old Use a promo page (Oct 24) is gone since the overhaul (Nov 4): promos have one home, the wallet (Me › Promos)
 *  with the finder (Build › Use a promo). Old links land on the finder. */
export default function PromoPage() {
  redirect("/build/promo");
}
