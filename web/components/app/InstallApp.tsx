"use client";

import { createContext, useContext, useEffect, useState } from "react";

type InstallPrompt = Event & {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};
const InstallContext = createContext<{ visible: boolean; ios: boolean; prompt: InstallPrompt | null;
  busy: boolean; error: string; install: () => Promise<void> } | null>(null);

/** Capture the prompt on every route, including Home before someone opens More. */
export function InstallProvider({ children }: { children: React.ReactNode }) {
  const [visible, setVisible] = useState(false);
  const [ios, setIos] = useState(false);
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const standalone = window.matchMedia("(display-mode: standalone)");
    const update = () => setVisible(!standalone.matches && !(navigator as Navigator & { standalone?: boolean }).standalone);
    update();
    setIos(/iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1));
    const ready = (event: Event) => { event.preventDefault(); setPrompt(event as InstallPrompt); };
    const installed = () => { setVisible(false); setPrompt(null); };
    window.addEventListener("beforeinstallprompt", ready);
    window.addEventListener("appinstalled", installed);
    standalone.addEventListener("change", update);
    return () => {
      window.removeEventListener("beforeinstallprompt", ready);
      window.removeEventListener("appinstalled", installed);
      standalone.removeEventListener("change", update);
    };
  }, []);
  async function install() {
    if (!prompt) return;
    setBusy(true); setError("");
    try {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      if (choice.outcome === "accepted") setVisible(false);
    } catch { setError("Use your browser menu to install BetLab."); }
    finally { setPrompt(null); setBusy(false); }
  }
  return <InstallContext.Provider value={{ visible, ios, prompt, busy, error, install }}>{children}</InstallContext.Provider>;
}

export function InstallApp() {
  const state = useContext(InstallContext);
  if (!state?.visible) return null;
  const { ios, prompt, busy, error, install } = state;
  return <section className="card install-card" aria-labelledby="install-title">
    <h2 id="install-title">BetLab on your home screen</h2>
    <p>Open your picks with one tap. An internet connection is required.</p>
    {prompt ? <button className="btn" disabled={busy} onClick={install}>{busy ? "Opening…" : "Install BetLab"}</button>
      : <p className="faint">{ios
        ? "In Safari, tap Share, then Add to Home Screen. Turn on Open as Web App if offered."
        : "Open your browser menu and choose Install app or Add to Home Screen, if available."}</p>}
    {error && <p role="status">{error}</p>}
  </section>;
}
