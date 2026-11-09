"use client";

// More > Novig challenges (Oct 28): add the Challenges screenshot in the morning; the worker finds each one's best Novig
// bet and alerts you when it's ripe; here you open it in Novig, then tap I placed it (Claude never places bets).

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { challengeState, type Challenge, type History } from "@/lib/challenges";
import { setChallenge } from "@/lib/challenge-actions";
import { dayTime, fmtAm, pct } from "@/lib/format";
import { BookLink } from "@/components/ui/BookLink";
import { shrink } from "@/components/build/SlipUpload";

export function Challenges({ items, history }: { items: Challenge[]; history: History }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();

  async function add(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true); setMsg(null);
    try {
      const images = await Promise.all([...files].slice(0, 4).map(shrink));
      const r = await fetch("/api/challenges", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ images }) });
      const j = await r.json();
      if (!r.ok) setMsg(j.error ?? "Couldn't read those screenshots.");
      else { setMsg(`${j.added} challenge${j.added === 1 ? "" : "s"} added. BetLab is finding the bets now.`); router.refresh(); }
    } catch { setMsg("Couldn't read those screenshots."); }
    setBusy(false);
  }
  const act = (id: string, s: "done" | "skipped" | "open") => start(async () => {
    const r = await setChallenge(id, s);
    if (r.error) setMsg(r.error); else router.refresh();
  });

  const done = items.filter((c) => c.status === "done").length;
  const each = items.find((c) => c.points != null)?.points ?? 50;
  const earned = done * each + (items.length >= 3 && done === items.length ? 100 : 0);
  const ring = items.length ? done / items.length : 0;
  const order = { ready: 0, open: 1, done: 2, skipped: 3 } as const;
  const sorted = [...items].sort((a, b) => order[a.status] - order[b.status]);

  return (
    <div className="chal">
      <section className="card chal-hero">
        <div className="chal-ring" style={{ ["--p" as string]: `${Math.round(ring * 100)}%` }} aria-label={`${done} of ${items.length} placed`}>
          <span>{done}/{items.length || 3}</span>
        </div>
        <div className="chal-hero-text">
          <h2>The Daily Drop</h2>
          <p>{each} points each, 100 more for all {Math.max(items.length, 3)}{earned ? <> · <b>{earned} earned today</b></> : null}</p>
        </div>
        <label className={`btn${items.length ? " quiet" : ""} chal-add`}>{busy ? "Reading…" : items.length ? "Add more" : "Add today's challenges"}
          <input type="file" accept="image/*" multiple hidden disabled={busy} onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
        </label>
        {msg && <p className="chal-msg" role="status">{msg}</p>}
      </section>
      <details className="chal-how">
        <summary>How it works</summary>
        <p>Each morning, screenshot Novig&apos;s Points › Challenges and add it here. BetLab finds the best Novig bet for each
          and alerts you when it&apos;s ripe: its game&apos;s news is in and the price beats the sharp line (+1.5% before 5 PM, fair
          until 10 PM, then the best there is). Place it in Novig, then tap I placed it.</p>
      </details>

      {!items.length ? <div className="card empty"><b>No challenges yet today</b><span>Add the screenshot of Novig&apos;s Challenges to start.</span></div>
        : sorted.map((c) => {
        const s = challengeState(c);
        const b = s.bet;
        const settled = c.status === "done" || c.status === "skipped";
        return (
          <article key={c.challenge_id} className={`card chal-card is-${c.status}${s.tag === "Watching" ? " is-watching" : ""}`}>
            <div className="chal-top">
              <span className="chal-mark" aria-hidden="true">{c.status === "done" ? "✓" : c.status === "skipped" ? "–" : ""}</span>
              <h3>{c.text.replace(/^Place an? /, "").replace(/^./, (x) => x.toUpperCase())}</h3>
              <span className="chal-pill">{s.tag}</span>
            </div>
            {b && !settled && (
              <div className="chal-bet">
                <ul>{b.legs.map((l) => (
                  <li key={l.label}>
                    <span><b>{l.label}</b><small>{l.game.replace(" @ ", " at ")} · {dayTime(l.start)}</small></span>
                    {b.legs.length > 1 && <span className="mono">{fmtAm(l.price)}</span>}
                  </li>))}
                </ul>
                <div className="chal-price">
                  <div><span className="mono chal-big">{fmtAm(b.price)}</span><small>Novig{b.legs.length > 1 ? ` · ${b.dec.toFixed(2)}x` : ""} · ${b.stake}</small></div>
                  <div className="chal-stats mono">
                    <span><b>{pct(b.p, 0)}</b> to hit</span>
                    <span className={b.ev >= 0 ? "pos" : "neg"}>EV {b.ev >= 0 ? "+" : "−"}{Math.abs(b.ev * 100).toFixed(1)}%</span>
                  </div>
                </div>
              </div>
            )}
            {b && settled && c.status === "done" && <p className="chal-line"><b>{b.label}</b> <span className="mono">{fmtAm(b.price)}</span> at Novig</p>}
            {s.note && !settled && <p className="chal-note">{s.note}</p>}
            <div className="actions chal-actions">
              {(c.status === "open" || c.status === "ready") && <>
                <button type="button" className="btn quiet" disabled={pending} onClick={() => act(c.challenge_id, "skipped")}>Skip</button>
                {b && <BookLink book="Novig" links={[b.link]} className={c.status === "ready" ? "btn" : "btn ghost"} />}
                {c.status === "ready" && <button type="button" className="btn ghost" disabled={pending} onClick={() => act(c.challenge_id, "done")}>I placed it</button>}
              </>}
              {settled && <button type="button" className="btn quiet chal-undo" disabled={pending} onClick={() => act(c.challenge_id, "open")}>Undo</button>}
            </div>
          </article>
        );
      })}
      <ChallengeHistory h={history} today={items[0]?.day ?? ""} />
    </div>
  );
}

const MONTH = (key: string) => new Date(`${key}-15T12:00:00Z`).toLocaleDateString("en-US", { month: "long", timeZone: "UTC" });
const DAY = (day: string) => new Date(`${day}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });

/** History (Oct 28): the month's points, challenges placed, 3-for-3 days and how the placed bets did; then each past day. */
function ChallengeHistory({ h, today }: { h: History; today: string }) {
  const past = h.days.filter((d) => d.day !== today).slice(0, 14);
  if (!h.days.length) return null;
  const m = h.month;
  return (
    <section className="chal-hist">
      <p className="section-label">History</p>
      <div className="card chal-month">
        <div><b className="mono">{m.points.toLocaleString()}</b><span>points in {MONTH(m.key)}</span></div>
        <div><b className="mono">{m.done}/{m.total}</b><span>placed</span></div>
        <div><b className="mono">{m.sweeps}</b><span>3-for-3 days</span></div>
        <div><b className={`mono ${m.units >= 0 ? "pos" : "neg"}`}>{m.settled ? `${m.units >= 0 ? "+" : "−"}${Math.abs(m.units).toFixed(2)}u` : "—"}</b>
          <span>{m.settled ? `${m.won} of ${m.settled} won` : "no results yet"}</span></div>
      </div>
      {past.length > 0 && <div className="card chal-days">
        {past.map((d) => (
          <div key={d.day} className="chal-day">
            <div className="chal-day-head"><b>{DAY(d.day)}</b><span className="mono">{d.done}/{d.total}{d.bonus ? " · +100" : ""}</span>
              <span className="mono chal-pts">{d.points} pts</span></div>
            <ul>{d.items.map((i, k) => (
              <li key={k} className={`is-${i.status}`}>
                <span>{i.status === "done" ? (i.label ?? i.text) : i.text.replace(/^Place an? /, "").replace(/^./, (x) => x.toUpperCase())}</span>
                <span className={`mono ${i.result === "won" ? "pos" : i.result === "lost" ? "neg" : "faint"}`}>
                  {i.status !== "done" ? (i.status === "skipped" ? "skipped" : "missed") : i.result === "won" || i.result === "lost"
                    ? `${i.result}${i.profit != null ? ` ${i.profit >= 0 ? "+" : "−"}${Math.abs(i.profit).toFixed(2)}u` : ""}` : i.result ?? "placed"}</span>
              </li>))}</ul>
          </div>
        ))}
      </div>}
      <p className="faint chal-foot">Results come from the Novig sync (straight bets). A parlay placed for a challenge shows as placed.</p>
    </section>
  );
}
