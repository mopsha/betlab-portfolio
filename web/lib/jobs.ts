export type RefreshRequest = {
  id: number; status: "queued" | "running" | "done" | "refused" | "failed";
  requested_at: string; finished_at: string | null;
};
export type RefreshState = {
  mode: "active" | "shadow" | "unknown" | "preview";
  request: RefreshRequest | null;
};
/** The jobs a signed-in user may queue from the app (the worker's REQUESTABLE and the job_requests check agree). */
export const APP_JOBS = ["reprice", "grade"] as const;
export type AppJob = (typeof APP_JOBS)[number];
export const isAppJob = (j: unknown): j is AppJob => typeof j === "string" && (APP_JOBS as readonly string[]).includes(j);
export const REFRESH_COOLDOWN = 30 * 60 * 1000;
export const pendingRefresh = (r: RefreshRequest | null) => r?.status === "queued" || r?.status === "running";
export function refreshWait(r: RefreshRequest | null, now = Date.now()): number {
  if (!r) return 0;
  const at = Date.parse(r.requested_at);
  return Number.isFinite(at) ? Math.max(0, at + REFRESH_COOLDOWN - now) : 0;
}
export function workerMode(step: string | undefined): RefreshState["mode"] {
  return step === "started" ? "active" : step === "started (shadow)" ? "shadow" : "unknown";
}
const GRADE_MESSAGES: Record<RefreshRequest["status"] | "idle", string> = {
  queued: "Grading queued. You can keep browsing.",
  running: "Grading finished games…",
  done: "Grading finished. Results are up to date.",
  refused: "Grading could not start. The worker may be busy or cooling down.",
  failed: "Grading failed. The morning run grades again.",
  idle: "Grade finished games now instead of at the 9:55 AM run. Once every 30 minutes.",
};
export function refreshMessage(s: RefreshState, job: AppJob = "reprice"): string {
  if (s.mode === "preview") return job === "grade" ? "Grading is unavailable in the local preview." : "Refresh is unavailable in the local preview.";
  if (job === "grade" && s.mode === "active") return GRADE_MESSAGES[s.request?.status ?? "idle"];
  if (s.mode === "shadow") return "On-demand refresh is not enabled yet. Scheduled updates continue.";
  if (s.mode !== "active") return "Refresh is unavailable right now. Try reloading the page.";
  switch (s.request?.status) {
    case "queued": return "Refresh queued. You can keep browsing.";
    case "running": return "Refreshing prices and picks…";
    case "done": return "Refresh finished. Check the priced time above.";
    case "refused": return "Refresh could not start. The worker may be busy or cooling down.";
    case "failed": return "Refresh failed. Scheduled updates continue.";
    default: return "Refresh prices and picks. Limited to once every 30 minutes.";
  }
}
