import { SubHead } from "@/components/ui/Kit";
import { MoneyForm } from "@/components/me/SettingsForm";
import { settingsData } from "@/lib/data";

/** Settings > Units and money. */
export default async function MoneyPage() {
  const s = await settingsData();
  return <main className="rail stg"><SubHead title="Units and money" back="/more/settings" backLabel="Settings" /><MoneyForm s={s} /></main>;
}
