"use server";

import { fixtureMode } from "./mode";
import { supabaseServer } from "./supabase/server";

export type PushSub = { endpoint: string; p256dh: string; auth: string; device: string };

/** Save this device's push subscription (as the signed-in user; RLS keeps it theirs) and ask the
 *  worker for a test alert, which goes to devices that haven't had an alert yet. */
export async function savePushSubscription(sub: PushSub): Promise<{ ok: boolean; error?: string }> {
  if (fixtureMode()) return { ok: false, error: "Alerts can't be turned on in the local preview." };
  if (!/^https:\/\//.test(sub.endpoint) || !sub.p256dh || !sub.auth) {
    return { ok: false, error: "This browser gave an unusable subscription." };
  }
  try {
    const sb = await supabaseServer();
    const { error } = await sb.from("push_subscriptions")
      .upsert({ endpoint: sub.endpoint, p256dh: sub.p256dh, auth: sub.auth, device: sub.device.slice(0, 80) },
              { onConflict: "user_id,endpoint" });
    if (error) return { ok: false, error: "Couldn't save this device. Try again in a moment." };
    await sb.from("job_requests").insert({ job: "test_alert", status: "queued" });   // best effort
    return { ok: true };
  } catch {
    return { ok: false, error: "Couldn't save this device. Try again in a moment." };
  }
}

export async function deletePushSubscription(endpoint: string): Promise<{ ok: boolean }> {
  if (fixtureMode()) return { ok: true };
  try {
    const sb = await supabaseServer();
    const { error } = await sb.from("push_subscriptions").delete().eq("endpoint", endpoint);
    return { ok: !error };
  } catch {
    return { ok: false };
  }
}
