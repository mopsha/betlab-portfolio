"use client";

// Settings rows that act in place (Nov 6 reorganization): friends see my bets, sign out.
import { useState, useTransition } from "react";
import { setShareBets, signOut } from "@/lib/actions";
import { SetIcon, TINT } from "@/components/me/SettingsKit";
import { forgetSavedPages } from "@/lib/offline";

export function ShareRow({ on }: { on: boolean }) {
  const [value, setValue] = useState(on);
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const toggle = () => {
    const next = !value;
    setValue(next); setMsg(null);
    start(async () => { const r = await setShareBets(next); if (!r.ok) { setValue(!next); setMsg(r.error); } });
  };
  return (
    <label className="field toggle">
      <SetIcon name="friends" tint={TINT.friends} />
      <span className="st-name">Friends see my bets<small>{msg ?? "Your bets, results and units, never money"}</small></span>
      <input type="checkbox" checked={value} disabled={pending} onChange={toggle} />
    </label>
  );
}

export function SignOutRow({ preview }: { preview: boolean }) {
  const [pending, start] = useTransition();
  if (preview) return null;
  return <button type="button" className="st-out" disabled={pending} onClick={() => start(async () => { await forgetSavedPages(); await signOut(); })}>{pending ? "Signing out…" : "Sign out"}</button>;
}
