"use client";

// Me > Extras > CFB Pick'em (Nov 7): add screenshots of FanDuel's Pick'em Questions; the worker prices each frozen
// line against the sharp market and names the side to take; edit the picks in FanDuel before the Saturday noon lock
// (Claude never enters picks). Once graded, the score, and what BetLab's side would have scored.

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { chance, flips, score, sideLabel, type PickemRow, type PickemWeek, type Side } from "@/lib/pickem";
import { removePickemRow, setPickemPick, setPickemWeek } from "@/lib/pickem-actions";
import { dayTime } from "@/lib/format";
import { shrink } from "@/components/build/SlipUpload";
import { Art } from "@/components/ui/Art";

const DAY = (day: string) => new Date(`${day}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

export function Pickem({ week, rows, history }: { week: string; rows: PickemRow[]; history: { rows: PickemRow[]; weeks: PickemWeek[] } }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const [partner, setPartner] = useState<string>(String(history.weeks.find((w) => w.week === week)?.partner_best ?? ""));
  const [reward, setReward] = useState<string>(history.weeks.find((w) => w.week === week)?.reward ?? "");

  async function add(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true); setMsg(null);
    try {
      const images = await Promise.all([...files].slice(0, 6).map(shrink));
      const r = await fetch("/api/pickem", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ images }) });
      const j = await r.json();
      if (!r.ok) setMsg(j.error ?? "Couldn't read those screenshots.");
      else { setMsg(`${j.added} game${j.added === 1 ? "" : "s"} added${j.updated ? `, ${j.updated} pick${j.updated === 1 ? "" : "s"} updated` : ""}. BetLab is pricing the lines now.`); router.refresh(); }
    } catch { setMsg("Couldn't read those screenshots."); }
    setBusy(false);
  }
  const setPick = (r: PickemRow, side: Side) => start(async () => {
    const res = await setPickemPick(r.pick_id, r.pick === side ? null : side);
    if (res.error) setMsg(res.error); else router.refresh();
  });
  const remove = (r: PickemRow) => start(async () => { const res = await removePickemRow(r.pick_id); if (res.error) setMsg(res.error); else router.refresh(); });
  const saveWeek = () => start(async () => {
    const res = await setPickemWeek(week, partner === "" ? null : Number(partner), reward.trim() || null);
    if (res.error) setMsg(res.error); else router.refresh();
  });

  const s = score(rows);
  const { toFlip, unpicked } = flips(rows);
  const started = rows.filter((r) => r.start && new Date(r.start) <= new Date()).length;
  const locked = started > 0 || new Date() >= new Date(`${week}T17:00:00Z`);
  const status = s.graded === rows.length && rows.length ? "Graded" : locked ? "Locked" : toFlip.length ? `${toFlip.length} to flip` : unpicked.length ? `${unpicked.length} unpicked` : rows.length ? "Set" : "";

  return (
    <div className="pk">
      <section className="card pk-hero">
        <div className="pk-score">
          <div><b className="mono">{rows.length ? `${s.yours}/${s.graded || rows.length}` : "—"}</b><span>your picks</span></div>
          <div><b className="mono">{rows.length ? `${s.ours}/${s.graded || rows.length}` : "—"}</b><span>BetLab&apos;s</span></div>
        </div>
        <div className="pk-hero-text">
          <h2>Week of {DAY(week)}</h2>
          <p>{rows.length ? <>{rows.length} games · {status}{!locked && <> · locks Saturday noon</>}</> : "Add the Questions screenshots to start"}</p>
        </div>
        <label className={`btn${rows.length ? " quiet" : ""} pk-add`}>{busy ? "Reading…" : rows.length ? "Add again" : "Add screenshots"}
          <input type="file" accept="image/*" multiple hidden disabled={busy} onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
        </label>
        {msg && <p className="pk-msg" role="status">{msg}</p>}
      </section>
      <details className="pk-how">
        <summary>How it works</summary>
        <p>FanDuel freezes the pick&apos;em lines Wednesday morning and settles on those numbers. By Saturday the sharp market has
          moved, so BetLab prices each frozen line against Pinnacle every 15 minutes and names the side that covers more often.
          Screenshot the Questions screens any day after Wednesday; Saturday at 10 AM you get one alert with the picks to flip.
          Edit them in FanDuel before noon, then tap the side you kept here so the score is right. Games with a New York college
          get no pick from BetLab.</p>
      </details>

      {!rows.length ? <div className="card empty"><b>No entry this week</b><span>Screenshot FanDuel&apos;s Pick&apos;em Questions (Rewards › College Football Pick&apos;em › Play Free) and add them.</span></div>
        : <div className="card pk-list">
          {rows.map((r) => {
            const done = r.result != null;
            const won = done && r.pick && (r.result === r.pick || r.result === "push");
            return (
              <article key={r.pick_id} className={`pk-game${done ? (won ? " is-won" : r.pick ? " is-lost" : "") : ""}`}>
                <div className="pk-top">
                  <span className="pk-logos"><Art src={r.away_logo} name={r.away} size={26} className="disc" /><Art src={r.home_logo} name={r.home} size={26} className="disc" /></span>
                  <span className="pk-match">{r.away} at {r.home}</span>
                  <span className="pk-when mono">{done ? `${r.away_pts}-${r.home_pts}` : r.start ? dayTime(r.start) : ""}</span>
                  {!done && !locked && <button type="button" className="pk-x" aria-label="Remove this game" disabled={pending} onClick={() => remove(r)}>×</button>}
                </div>
                <div className="pk-sides">
                  {(["away", "home"] as Side[]).map((side) => {
                    const p = chance(r, side);
                    const mine = r.pick === side, ours = r.ours === side, hit = done && (r.result === side || r.result === "push");
                    return (
                      <button key={side} type="button" disabled={pending || done} onClick={() => setPick(r, side)}
                        className={`pk-side${mine ? " is-mine" : ""}${ours ? " is-ours" : ""}${done ? (hit ? " is-hit" : " is-miss") : ""}`}>
                        <b>{sideLabel(r, side)}</b>
                        <span className="mono">{p != null ? `${Math.round(p * 100)}%` : "—"}</span>
                        <small>{mine && ours ? "you · BetLab" : mine ? "you" : ours ? "BetLab" : ""}</small>
                      </button>);
                  })}
                </div>
                {r.notice && !done && <p className="pk-note">{r.notice}</p>}
                {!done && r.fair_line != null && <p className="pk-note faint">Market now {r.home} {Number(r.fair_line) > 0 ? "+" : ""}{Number(r.fair_line)}</p>}
              </article>);
          })}
        </div>}

      {rows.length > 0 && locked && (
        <section className="card pk-week">
          <p className="section-label">After FanDuel grades it (Sunday)</p>
          <div className="pk-week-form">
            <label>Partners&apos; best score<input inputMode="numeric" value={partner} onChange={(e) => setPartner(e.target.value.replace(/\D/g, "").slice(0, 2))} placeholder="6" /></label>
            <label>What it paid<input value={reward} onChange={(e) => setReward(e.target.value)} placeholder="25% boost, bonus bets, nothing" /></label>
            <button type="button" className="btn quiet" disabled={pending} onClick={saveWeek}>Save</button>
          </div>
        </section>)}

      <PickemHistory rows={history.rows} weeks={history.weeks} />
    </div>
  );
}

/** Past weeks: your score, BetLab's, the partners' and what it paid. */
function PickemHistory({ rows, weeks }: { rows: PickemRow[]; weeks: PickemWeek[] }) {
  const byWeek = new Map<string, PickemRow[]>();
  for (const r of rows) byWeek.set(r.week, [...(byWeek.get(r.week) ?? []), r]);
  if (!byWeek.size) return null;
  const ws = [...byWeek.keys()].sort().reverse();
  return (
    <section className="pk-hist">
      <p className="section-label">Past weeks</p>
      <div className="card pk-weeks">
        {ws.map((w) => {
          const s = score(byWeek.get(w)!);
          const info = weeks.find((x) => x.week === w);
          return (
            <div key={w} className="pk-weekrow">
              <b>{DAY(w)}</b>
              <span className="mono">you {s.yours}/{s.graded}</span>
              <span className="mono">BetLab {s.ours}/{s.graded}</span>
              <span className="mono faint">{info?.partner_best != null ? `partners ${info.partner_best}` : ""}</span>
              <span className="faint">{info?.reward ?? ""}</span>
            </div>);
        })}
      </div>
    </section>
  );
}
