"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { finishWelcome } from "@/lib/actions";
import { WELCOME, WELCOME_UNIT } from "@/lib/welcome";

export function WelcomeSteps({ again, unit }: { again: boolean; unit: number }) {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [dollars, setDollars] = useState(String(unit));
  const [err, setErr] = useState<string | null>(null);
  const [pending, go] = useTransition();
  const page = WELCOME[step];
  const n = Number(dollars);
  const finish = () => go(async () => {
    const r = await finishWelcome(n);
    if (!r.ok) setErr(r.error ?? "Couldn't save that."); else { router.replace(again ? "/more" : "/"); router.refresh(); }
  });
  return (
    <section className="card welcome">
      <p className="faint welcome-step">{step + 1} of {WELCOME.length + 1}</p>
      {page ? <>
        <h1>{page.title}</h1>
        {page.lines.map((l) => <p key={l}>{l}</p>)}
      </> : <>
        <h1>{WELCOME_UNIT.title}</h1>
        <p>{WELCOME_UNIT.line}</p>
        <label className="field">Dollars per unit<input inputMode="decimal" value={dollars} onChange={(e) => { setDollars(e.target.value); setErr(null); }} /></label>
        <p className="faint">{WELCOME_UNIT.help}</p>
      </>}
      <div className="actions">
        {page ? <button className="btn" type="button" onClick={() => setStep(step + 1)}>Next</button>
          : <button className="btn" type="button" disabled={pending || !(n > 0)} onClick={finish}>{pending ? "Saving…" : "Start"}</button>}
        {step > 0 && <button className="btn quiet" type="button" onClick={() => setStep(step - 1)}>Back</button>}
        {err && <span className="err" role="status">{err}</span>}
      </div>
    </section>
  );
}
