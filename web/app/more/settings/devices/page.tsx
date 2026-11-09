import { SubHead } from "@/components/ui/Kit";
import { DevicesCard } from "@/components/me/DevicesCard";
import { deviceSessions } from "@/lib/data";

/** Settings > Signed-in devices (0037). */
export default async function DevicesPage() {
  const sessions = await deviceSessions().catch(() => []);
  return (
    <main className="rail stg"><SubHead title="Signed-in devices" back="/more/settings" backLabel="Settings" />
      {sessions.length ? <DevicesCard sessions={sessions} /> : <p className="st-foot">No other device is signed in.</p>}</main>
  );
}
