"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { requestRefresh, refreshStatus } from "@/lib/refresh-actions";
import { pendingRefresh, refreshMessage, refreshWait, type AppJob, type RefreshState } from "@/lib/jobs";

const LABELS: Record<AppJob, [string, string, string]> = {   // idle, pending, failed to queue
  reprice: ["Refresh now", "Refreshing…", "Couldn't queue a refresh. Try again in a moment."],
  grade: ["Grade now", "Grading…", "Couldn't queue grading. Try again in a moment."],
};

/** `compact`: a small button for a page's corner (My bets' Grade now, Oct 24: "out of the way"); the status moves into
 * its tooltip, and only a pending job or an error shows as text. */
export function RefreshControl({ initial, job = "reprice", compact = false, icon = false }: { initial: RefreshState; job?: AppJob; compact?: boolean; icon?: boolean }) {
  const router = useRouter();
  const [state, setState] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => { setState(initial); }, [initial]);
  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);
  const pending = pendingRefresh(state.request);
  useEffect(() => {
    if (!pending) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        if (!document.hidden) {
          const next = await refreshStatus(job);
          if (cancelled) return;
          // A temporary read failure must not erase a pending request.
          if (next.mode !== "unknown") {
            setState(next);
            if (!pendingRefresh(next.request)) {
              if (next.request?.status === "done") router.refresh();
              return;
            }
          }
        }
      } catch { /* Retry transient connection failures without showing server details. */ }
      if (!cancelled) timer = setTimeout(poll, 5000);
    }
    timer = setTimeout(poll, 5000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [pending, router, job]);
  const wait = now === null ? 0 : refreshWait(state.request, now);
  async function refresh() {
    setBusy(true); setError("");
    try {
      const result = await requestRefresh(job);
      setState(result.state); setError(result.error ?? ""); setNow(Date.now());
    } catch { setError(LABELS[job][2]); }
    finally { setBusy(false); }
  }
  const note = `${error || refreshMessage(state, job)}${!pending && state.mode === "active" && wait > 0 ? ` Available in ${Math.ceil(wait / 60_000)} min.` : ""}`;
  // `icon` (the overhaul, Nov 4): a round button in a screen's header; what it's doing shows as a short line beside it
  // only while a job is queued or after an error, and the rest is its tooltip
  if (icon) return <span className="refresh-icon">
    {(error || pending || busy) && <span className={error ? "err" : "faint"} role="status" aria-live="polite">{error || (busy ? "Queuing…" : LABELS[job][1])}</span>}
    <button type="button" className={`ib${pending || busy ? " spin" : ""}`} onClick={refresh} title={`${LABELS[job][0]}. ${note}`} aria-label={LABELS[job][0]}
      disabled={busy || pending || state.mode !== "active" || wait > 0}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={job === "grade" ? "M5 12l5 5 9-10" : "M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"} /></svg>
    </button>
  </span>;
  if (compact) return <span className="refresh-compact">
    <button className="btn quiet small" onClick={refresh} title={note}
      disabled={busy || pending || state.mode !== "active" || wait > 0}>
      {busy ? "Queuing…" : pending ? LABELS[job][1] : LABELS[job][0]}
    </button>
    {error && <span className="err" role="status">{error}</span>}
  </span>;
  return <div className="refresh-control">
    <button className="btn quiet" onClick={refresh}
      disabled={busy || pending || state.mode !== "active" || wait > 0}>
      {busy ? "Queuing…" : pending ? LABELS[job][1] : LABELS[job][0]}
    </button>
    <span className="faint" role="status" aria-live="polite">
      {error || refreshMessage(state, job)}
      {!pending && state.mode === "active" && wait > 0 && ` Available in ${Math.ceil(wait / 60_000)} min.`}
    </span>
  </div>;
}
