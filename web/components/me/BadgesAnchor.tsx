"use client";

import { useEffect } from "react";

/** Me's "All" beside Badges opens Stats at its achievements (`/more/stats#badges`). The Stats view's heading has no id
 *  of its own, so this gives it one once the page is drawn and scrolls there when the link asked for it. */
export function BadgesAnchor() {
  useEffect(() => {
    const h = [...document.querySelectorAll<HTMLElement>("h2.section-label")].find((e) => e.textContent?.trim().startsWith("Achievements"));
    if (!h) return;
    h.id = "badges";
    h.style.scrollMarginTop = "16px";
    if (window.location.hash === "#badges") h.scrollIntoView({ block: "start" });
  }, []);
  return null;
}
