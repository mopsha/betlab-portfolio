import { SubHead } from "@/components/ui/Kit";
import { AlertSettings } from "@/components/me/AlertSettings";
import { PickAlerts } from "@/components/me/PickAlerts";
import { SetGroup } from "@/components/me/SettingsKit";
import { settingsData } from "@/lib/data";

/** Settings > Notifications: this device's push, then what to send and when (user_settings.notify, alert_prefs.py). */
export default async function AlertsPage() {
  const s = await settingsData();
  return (
    <main className="rail stg"><SubHead title="Notifications" back="/more/settings" backLabel="Settings" />
      <SetGroup title="This device"><PickAlerts /></SetGroup>
      <AlertSettings notify={s.notify ?? {}} />
    </main>
  );
}
