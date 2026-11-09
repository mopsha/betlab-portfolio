"use client";

import { useState, useTransition } from "react";
import { setNotify } from "@/lib/actions";
import { SetGroup } from "@/components/me/SettingsKit";

const SPORTS = [["nfl", "NFL"], ["ncaaf", "College football"], ["nba", "NBA"], ["ncaab", "College basketball"], ["nhl", "NHL"],
  ["soccer", "Soccer"], ["ufc", "UFC"]] as const;
const SWITCHES = [["picks", "New picks", "The moment one is found", true], ["leans", "Leans too", "A lot more alerts", false],
  ["locks", "Parlay locks", "Each slice's tickets, 15 minutes out", true], ["legs", "My legs", "A leg hits, one is left, it loses, the bet wins", true],
  ["news", "A player on my bet goes out", "With the book's rule for it", true], ["reactions", "A friend reacts to my bet", "", true]] as const;

type Notify = { legs?: boolean; picks?: boolean; leans?: boolean; locks?: boolean; news?: boolean; reactions?: boolean; min_ev?: number | null;
  sports?: Record<string, boolean>; quiet?: { from: string; to: string } | null };

/** Settings > Alert settings (Mike's #47, Nov 2; iPhone AlertSettingsSection): user_settings.notify, read by the worker's
 *  alert_prefs.py. Times are Eastern. During quiet hours alerts wait for the morning, and leg alerts are skipped. */
export function AlertSettings({ notify }: { notify: Notify }) {
  const [n, setN] = useState<Notify>(notify ?? {});
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const save = (patch: Notify) => {
    const before = n;
    setN({ ...n, ...patch }); setMsg(null);
    start(async () => {
      const r = await setNotify(patch);
      if (!r.ok) { setN(before); setMsg(r.error); }
    });
  };
  const quiet = n.quiet ?? null;
  return (
    <>
      <SetGroup title="Send me">
        {SWITCHES.map(([k, label, sub, dflt]) => (
          <label className="field toggle" key={k}>
            <span className="st-name">{label}{sub && <small>{sub}</small>}</span>
            <input type="checkbox" checked={n[k] ?? dflt} disabled={pending} onChange={(e) => save({ [k]: e.target.checked })} />
          </label>
        ))}
        <label className="st-field" htmlFor="min-ev"><span>Minimum EV (%)</span>
          <input id="min-ev" type="number" min="0" max="50" step="0.5" inputMode="decimal" defaultValue={n.min_ev ?? ""} placeholder="Any" disabled={pending}
            onBlur={(e) => { const v = e.target.value.trim(); const next = v === "" ? null : Number(v);
              if (next !== (n.min_ev ?? null) && (next === null || (next >= 0 && next <= 50))) save({ min_ev: next }); }} />
        </label>
      </SetGroup>
      <SetGroup title="Sports" foot="For picks, leans and locks.">
        <div className="st-chips" role="group" aria-label="Sports">
          {SPORTS.map(([k, label]) => (
            <button key={k} type="button" aria-pressed={n.sports?.[k] !== false} disabled={pending}
              onClick={() => save({ sports: { ...(n.sports ?? {}), [k]: n.sports?.[k] === false } })}>{label}</button>
          ))}
        </div>
      </SetGroup>
      <SetGroup title="Quiet hours" foot="Eastern time. What's found in quiet hours arrives when they end, unless the game has started by then; leg alerts are skipped.">
        <label className="field toggle">
          <span className="st-name">Quiet hours</span>
          <input type="checkbox" checked={!!quiet} disabled={pending} onChange={(e) => save({ quiet: e.target.checked ? { from: "23:00", to: "08:00" } : null })} />
        </label>
        {quiet && <>
          <label className="st-field" htmlFor="quiet-from"><span>From</span>
            <input id="quiet-from" type="time" value={quiet.from} disabled={pending} onChange={(e) => e.target.value && save({ quiet: { ...quiet, from: e.target.value } })} />
          </label>
          <label className="st-field" htmlFor="quiet-to"><span>To</span>
            <input id="quiet-to" type="time" value={quiet.to} disabled={pending} onChange={(e) => e.target.value && save({ quiet: { ...quiet, to: e.target.value } })} />
          </label>
        </>}
      </SetGroup>
      {msg && <p className="err" role="status">{msg}</p>}
    </>
  );
}
