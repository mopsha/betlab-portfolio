import "server-only";
import { fixtureMode } from "./mode";
import { supabaseServer } from "./supabase/server";
import { workerMode, type AppJob, type RefreshRequest, type RefreshState } from "./jobs";

/** Read only safe status fields, as the signed-in user. RLS isolates requests. */
export async function refreshData(job: AppJob = "reprice"): Promise<RefreshState> {
  if (fixtureMode()) return { mode: "preview", request: null };
  try {
    const sb = await supabaseServer();
    const [worker, request] = await Promise.all([
      sb.from("runs").select("step").eq("job", "worker").order("started_at", { ascending: false }).limit(1),
      sb.from("job_requests").select("id,status,requested_at,finished_at").eq("job", job)
        .order("requested_at", { ascending: false }).limit(1),
    ]);
    if (worker.error || request.error) return { mode: "unknown", request: null };
    return { mode: workerMode(worker.data?.[0]?.step), request: (request.data?.[0] as RefreshRequest) ?? null };
  } catch {
    return { mode: "unknown", request: null };
  }
}
