"use client";
import { useEffect } from "react";
import { forgetSavedPages } from "@/lib/offline";

/** On the login screen: once a sign-in finished elsewhere (the Google sheet over the home-screen app), go home.
 *  Checks when the screen comes back into view, and every few seconds while it's open. */
export default function SignedInWatch() {
  useEffect(() => {
    void forgetSavedPages();      // on the sign-in page, no account's saved pages should stay on this device
    let done = false;
    const check = async () => {
      if (done || document.visibilityState !== "visible") return;
      try {
        const r = await fetch("/auth/status", { cache: "no-store" });
        if (r.ok && (await r.json()).signedIn) { done = true; window.location.replace("/"); }
      } catch { /* offline: try again later */ }
    };
    const timer = setInterval(check, 4000);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check);
    window.addEventListener("pageshow", check);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("focus", check);
      window.removeEventListener("pageshow", check);
    };
  }, []);
  return null;
}
