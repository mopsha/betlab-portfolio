"use server";

import { refreshData } from "./refresh";
import { isAppJob, pendingRefresh, refreshWait, type AppJob, type RefreshRequest, type RefreshState } from "./jobs";
import { supabaseServer } from "./supabase/server";

export async function refreshStatus(job: AppJob = "reprice"): Promise<RefreshState> {
  return refreshData(isAppJob(job) ? job : "reprice");
}

/** Only the guarded app jobs (reprice, grade); no arbitrary job names or privileged credentials. */
export async function requestRefresh(job: AppJob = "reprice"): Promise<{ state: RefreshState; error?: string }> {
  const fail = job === "grade" ? "Couldn't queue grading. Try again in a moment." : "Couldn't queue a refresh. Try again in a moment.";
  if (!isAppJob(job)) return { state: { mode: "unknown", request: null }, error: fail };
  const state = await refreshData(job);
  if (state.mode !== "active" || pendingRefresh(state.request) || refreshWait(state.request)) return { state };
  try {
    const sb = await supabaseServer();
    const { data, error } = await sb.from("job_requests").insert({ job, status: "queued" })
      .select("id,status,requested_at,finished_at").single();
    if (error) return { state, error: fail };
    return { state: { ...state, request: data as RefreshRequest } };
  } catch {
    return { state, error: fail };
  }
}
