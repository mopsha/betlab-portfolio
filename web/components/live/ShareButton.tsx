"use client";

import { useState } from "react";

/** Share a bet as a picture (Mike's W13, Oct 24): the phone's share sheet with the image (Messages, Instagram, save to
 * Photos), else the picture opens in a new tab to save. `url` shares another picture (Wrapped's, Oct 27). */
export function ShareButton({ id, url, name = "betlab-bet.png" }: { id?: string; url?: string; name?: string }) {
  const [busy, setBusy] = useState(false);
  const src = url ?? `/api/share/${id}`;
  async function share() {
    setBusy(true);
    try {
      const r = await fetch(src, { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const file = new File([await r.blob()], name, { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) await navigator.share({ files: [file] });
      else window.open(URL.createObjectURL(file), "_blank");
    } catch (e) {
      if ((e as Error).name !== "AbortError") window.open(src, "_blank");   // share sheet closed: nothing to do
    } finally {
      setBusy(false);
    }
  }
  return <button type="button" className="btn ghost" onClick={share} disabled={busy}>{busy ? "Making…" : "Share"}</button>;
}
