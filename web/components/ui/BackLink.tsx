"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

const KEY = "betlab_inapp";   // set once this tab has shown more than one BetLab page

/** In the layout: notes in-app navigation, so BackLink knows the previous history entry is BetLab's. */
export function NavTracker() {
  const path = usePathname();
  useEffect(() => {
    try {
      const first = sessionStorage.getItem(KEY + "_first");
      if (!first) sessionStorage.setItem(KEY + "_first", path);
      else if (first !== path) sessionStorage.setItem(KEY, "1");
    } catch { /* storage blocked: BackLink uses its fallback */ }
  }, [path]);
  return null;
}

/** "‹ Back" to the page you came from, as it was (the Games tab keeps its sport filter and scroll; the
 *  second account's first find, Oct 12: back from a game went Home). Opened straight from a link or a
 *  notification, it goes to `fallback`. */
export function BackLink({ fallback = "/games", label = "Back" }: { fallback?: string; label?: string }) {
  const router = useRouter();
  return (
    <a className="back" href={fallback} onClick={(e) => {
      let inApp = false;
      try { inApp = sessionStorage.getItem(KEY) === "1"; } catch { /* fallback */ }
      if (inApp && window.history.length > 1) { e.preventDefault(); router.back(); }
    }}>‹ {label}</a>
  );
}
