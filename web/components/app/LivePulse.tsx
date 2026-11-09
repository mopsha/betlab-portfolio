"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { createBrowserClient } from "@supabase/ssr";
import { SUPABASE_KEY, SUPABASE_URL } from "@/lib/env";

const SETTLE_MS = 2000;        // a burst of changes (a publish, a few bets) is one refresh
const STALE_MS = 60_000;       // back on the tab after this long: refresh even with no change heard

/** Live updates (Nov 4; migration 0033): the database says something changed (`app_pulse`, its row-level security decides
 *  whose), and the page reads it at once. A hidden tab waits until it's looked at. Scores aren't here: ESPN has no feed to
 *  hear, so the tracker keeps checking every 20 seconds (`LiveBets`), and also looks when this fires. */
export function LivePulse() {
  const router = useRouter();
  const path = usePathname();
  const signedOut = path === "/login" || path.startsWith("/auth");
  const [online, setOnline] = useState(true);
  useEffect(() => {                  // the offline copy of each page (public/sw.js) needs the worker from the first visit
    navigator.serviceWorker?.register("/sw.js").catch(() => {});
    const look = () => setOnline(navigator.onLine);
    look();
    window.addEventListener("online", look);
    window.addEventListener("offline", look);
    return () => { window.removeEventListener("online", look); window.removeEventListener("offline", look); };
  }, []);
  useEffect(() => {
    if (signedOut || !SUPABASE_URL || !SUPABASE_KEY) return;
    const sb = createBrowserClient(SUPABASE_URL, SUPABASE_KEY);
    let wait: ReturnType<typeof setTimeout> | null = null, pending = false, last = Date.now();
    const refresh = () => {
      last = Date.now(); pending = false;
      router.refresh();
      window.dispatchEvent(new Event("betlab:pulse"));
    };
    const changed = () => {
      if (wait) clearTimeout(wait);
      wait = setTimeout(() => { if (document.hidden) pending = true; else refresh(); }, SETTLE_MS);
    };
    const back = () => { if (!document.hidden && (pending || Date.now() - last > STALE_MS)) refresh(); };
    let joins = 0;                   // back after a drop or offline: what changed meanwhile was never heard
    const channel = sb.channel("betlab-pulse")
      .on("postgres_changes", { event: "*", schema: "public", table: "app_pulse" }, changed)
      .subscribe((status) => { if (status === "SUBSCRIBED" && joins++) changed(); });
    document.addEventListener("visibilitychange", back);
    window.addEventListener("online", changed);
    return () => {
      if (wait) clearTimeout(wait);
      document.removeEventListener("visibilitychange", back);
      window.removeEventListener("online", changed);
      sb.removeChannel(channel);
    };
  }, [signedOut, router]);
  return online ? null : <div className="offline" role="status">Offline: showing what was last saved</div>;
}
