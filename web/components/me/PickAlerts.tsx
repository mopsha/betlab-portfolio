"use client";

import { useEffect, useState } from "react";
import { deletePushSubscription, savePushSubscription } from "@/lib/push-actions";
import { keyBytes, staleKey } from "@/lib/pushkey";

const KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";

type State = "loading" | "unsupported" | "install-first" | "no-keys" | "denied" | "off" | "on";

const NOTE: Record<State, string> = {
  loading: "",
  on: "On for this device: a notification whenever a new pick is found (picks only, not leans).",
  off: "Get a notification on this device whenever a new pick is found (picks only, not leans).",
  "install-first": "On iPhone, add BetLab to your home screen first (Share, then Add to Home Screen) and open it from there.",
  unsupported: "This browser can't receive alerts.",
  "no-keys": "Alerts aren't switched on yet: the server is waiting for their keys.",
  denied: "Notifications are blocked for BetLab. Allow them in your phone's settings, then come back.",
};

const b64 = (buf: ArrayBuffer | null) => (buf ? btoa(String.fromCharCode(...new Uint8Array(buf))) : "");

/** Settings > Pick alerts: a push to this device whenever a new pick (not a lean) is logged. */
export function PickAlerts() {
  const [state, setState] = useState<State>("loading");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    (async () => {
      const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
      const standalone = window.matchMedia("(display-mode: standalone)").matches
        || (navigator as Navigator & { standalone?: boolean }).standalone === true;
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
        setState(ios && !standalone ? "install-first" : "unsupported");
        return;
      }
      if (!KEY) { setState("no-keys"); return; }
      if (Notification.permission === "denied") { setState("denied"); return; }
      const reg = await navigator.serviceWorker.register("/sw.js");
      const sub = await reg.pushManager.getSubscription();
      if (sub && staleKey(sub, KEY)) {
        // made with an older VAPID key (rotated Oct 23): every push to it fails, yet it looked "on"
        await deletePushSubscription(sub.endpoint).catch(() => undefined);
        await sub.unsubscribe();
        setState("off");
        setMsg("Alerts were reset after a key change: turn them on again.");
        return;
      }
      setState(sub ? "on" : "off");
    })().catch(() => setState("unsupported"));
  }, []);

  async function turnOn() {
    setBusy(true); setMsg("");
    try {
      if ((await Notification.requestPermission()) !== "granted") { setState("denied"); return; }
      await navigator.serviceWorker.register("/sw.js");
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(KEY) as BufferSource });
      const device = /iPhone/.test(navigator.userAgent) ? "iPhone" : /Android/.test(navigator.userAgent) ? "Android" : "Browser";
      const r = await savePushSubscription({ endpoint: sub.endpoint, p256dh: b64(sub.getKey("p256dh")),
                                             auth: b64(sub.getKey("auth")), device });
      if (!r.ok) { await sub.unsubscribe(); setMsg(r.error ?? "Couldn't turn alerts on."); return; }
      setState("on"); setMsg("On. A test alert should arrive within a minute.");
    } catch {
      setMsg("Couldn't turn alerts on. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  async function turnOff() {
    setBusy(true); setMsg("");
    try {
      const sub = await (await navigator.serviceWorker.ready).pushManager.getSubscription();
      if (sub) { await deletePushSubscription(sub.endpoint); await sub.unsubscribe(); }
      setState("off");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="st-status">
      <p style={{ margin: "0 0 8px" }}>{NOTE[state]}</p>
      {(state === "off" || state === "on") && (
        <div className="actions">
          {state === "off"
            ? <button className="btn" disabled={busy} onClick={turnOn}>{busy ? "Turning on…" : "Turn on pick alerts"}</button>
            : <button className="btn quiet" disabled={busy} onClick={turnOff}>{busy ? "Turning off…" : "Turn off on this device"}</button>}
          {msg && <span role="status">{msg}</span>}
        </div>
      )}
    </section>
  );
}
