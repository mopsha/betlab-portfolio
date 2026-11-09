import { SubHead } from "@/components/ui/Kit";
import { SetGroup, SetRow, TINT } from "@/components/me/SettingsKit";

/** Settings > Test the Open in links: one live bet link per book, through this phone's app. */
export default function LinksPage() {
  return (
    <main className="rail stg"><SubHead title="Test the links" back="/more/settings" backLabel="Settings" />
      <SetGroup foot="Each opens one live bet in that book's app on this phone, the way Open in does from a pick.">
        <SetRow href="/more/settings/fanduel-test" icon="link" tint={TINT.books} title="Open in FanDuel" />
        <SetRow href="/more/settings/draftkings-test" icon="link" tint={TINT.money} title="Open in DraftKings" />
      </SetGroup>
    </main>
  );
}
