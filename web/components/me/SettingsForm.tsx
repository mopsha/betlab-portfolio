"use client";

import { useState, useTransition } from "react";
import { saveSettings, setFont, setTheme, setUnitDollars } from "@/lib/actions";
import { FONTS, THEMES } from "@/lib/looks";
import type { Settings } from "@/lib/data";
import { UNIT_DEFAULT } from "@/lib/real";
import { SetGroup } from "@/components/me/SettingsKit";

/** Settings > Units and money: the unit's dollars, parlay units a month, the real-money date. The apps count units
 *  (Oct 12); the unit's dollars only turn a slip's or a promo's dollars into units (Oct 30). */
export function MoneyForm({ s }: { s: Settings }) {
  const [fun, setFun] = useState(String(s.fun_bucket_monthly));
  const etDate = (iso: string) => new Date(iso).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  const [realFrom, setRealFrom] = useState(s.real_from ? etDate(s.real_from) : "");
  const [unit, setUnit] = useState(String(s.unit_dollars ?? UNIT_DEFAULT));
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const f = Number(fun);
  const valid = fun.trim() !== "" && f >= 0 && f <= 1000;
  // 05:00 UTC is just after midnight Eastern in both summer and winter time
  const realIso = realFrom ? new Date(`${realFrom}T05:00:00Z`).toISOString() : null;
  const u = Number(unit);
  const unitOk = u > 0 && u <= 100000;
  const changed = f !== s.fun_bucket_monthly || u !== (s.unit_dollars ?? UNIT_DEFAULT)
    || (realFrom || "") !== (s.real_from ? etDate(s.real_from) : "");
  const save = (e: React.FormEvent) => {
    e.preventDefault();
    start(async () => {
      const r = await saveSettings({ fun_bucket_monthly: f, book: s.book, real_from: realIso });
      const ru = r.ok && u !== (s.unit_dollars ?? UNIT_DEFAULT) ? await setUnitDollars(u) : r;
      setMsg(ru.ok ? "Saved" : ru.error);
    });
  };
  const edit = (set: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => { set(e.target.value); setMsg(null); };
  return (
    <form onSubmit={save}>
      <SetGroup title="Units" foot="A unit is your standard bet, whatever size you choose; everything counts in units, 5u a day at most. Keep it the same size for a month at a time, never bigger after a win or a loss.">
        <label className="st-field"><span>One unit is</span><input inputMode="decimal" value={`$${unit}`} onChange={(e) => { setUnit(e.target.value.replace(/[^0-9.]/g, "")); setMsg(null); }} /></label>
        <label className="st-field"><span>Parlays a month</span><input inputMode="decimal" value={fun} onChange={edit(setFun)} aria-label="Parlay units a month" /></label>
      </SetGroup>
      <SetGroup title="Real money" foot="From this date, I placed this records a real bet (1 unit at the price shown, both editable); before it, bets are paper. Empty means Oct 18. You must be 21 to bet in New York.">
        <label className="st-field"><span>Real money from</span><input type="date" value={realFrom} onChange={edit(setRealFrom)} /></label>
      </SetGroup>
      {!valid && <p className="st-foot neg">Parlay units a month: 0 or more.</p>}
      <div className="actions" style={{ marginTop: 18 }}>
        <button className="btn" disabled={pending || !valid || !unitOk || !changed}>{pending ? "Saving…" : "Save"}</button>
        {msg && <span className={msg === "Saved" ? "mine" : "err"} role="status">{msg}</span>}
      </div>
    </form>
  );
}

/** Settings > Theme and font. */
export function LookPicker({ theme, font }: { theme: string; font: string }) {
  const [, start] = useTransition();
  return (
    <>
      <SetGroup title="Theme">
        <div className="looks st-looks" role="group" aria-label="Theme">
          {THEMES.map((t) => (
            <a key={t.id} href="#" role="button" aria-current={t.id === theme} onClick={(e) => { e.preventDefault(); start(() => setTheme(t.id)); }}>
              <span className="sw" aria-hidden style={{ background: t.bg ? `linear-gradient(135deg, ${t.bg} 50%, ${t.accent} 50%)`
                : "linear-gradient(135deg, #f4f5f7 50%, #0d0f13 50%)" }} />
              {t.label}
            </a>
          ))}
        </div>
      </SetGroup>
      <SetGroup title="Font">
        <div className="looks st-looks" role="group" aria-label="Font">
          {FONTS.map((f) => (
            <a key={f.id} href="#" role="button" aria-current={f.id === font} style={{ fontFamily: f.css }}
               onClick={(e) => { e.preventDefault(); start(() => setFont(f.id)); }}>
              {f.label}
            </a>
          ))}
        </div>
      </SetGroup>
    </>
  );
}
