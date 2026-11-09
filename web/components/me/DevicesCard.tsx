"use client";
import { useState, useTransition } from "react";
import { endSessions } from "@/lib/actions";
import { deviceName, type DeviceSession } from "@/lib/devices";

const when = (iso: string) => new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** Where you're signed in. Ending one stops its next refresh, so it's out within the hour at the latest. */
export function DevicesCard({ sessions }: { sessions: DeviceSession[] }) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const others = sessions.filter((s) => !s.current);
  const end = (id: string | null) => start(async () => {
    const r = await endSessions(id);
    setMsg(r.error ?? `Signed out ${r.ended} device${r.ended === 1 ? "" : "s"}. It can take up to an hour to take effect.`);
  });
  return (
    <div className="card settings">
      {sessions.map((s) => (
        <div key={s.id} className="calrow" style={{ padding: "6px 0" }}>
          <span><b>{deviceName(s.user_agent)}</b>{s.current && <span className="tag lean" style={{ marginLeft: 6 }}>This device</span>}
            <br /><span className="faint">Last active {when(s.last_active)}{s.ip && s.user_agent !== "node" ? ` · ${s.ip}` : ""}</span></span>
          {!s.current && <button className="btn quiet small" disabled={pending} onClick={() => end(s.id)}>Sign out</button>}
        </div>
      ))}
      {others.length > 1 && <div className="actions"><button className="btn quiet" disabled={pending} onClick={() => end(null)}>Sign out all other devices</button></div>}
      {msg && <p className="faint" role="status">{msg}</p>}
    </div>
  );
}
