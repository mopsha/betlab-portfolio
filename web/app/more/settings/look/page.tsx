import { cookies } from "next/headers";
import { SubHead } from "@/components/ui/Kit";
import { LookPicker } from "@/components/me/SettingsForm";

/** Settings > Theme and font (this device's, in cookies). */
export default async function LookPage() {
  const jar = await cookies();
  return (
    <main className="rail stg"><SubHead title="Theme and font" back="/more/settings" backLabel="Settings" />
      <LookPicker theme={jar.get("theme")?.value ?? "system"} font={jar.get("font")?.value ?? "classic"} /></main>
  );
}
