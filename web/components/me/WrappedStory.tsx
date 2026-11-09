"use client";

// BetLab Wrapped (Mike's W17, Oct 27): the story itself. One slide at a time, like Instagram or Spotify Wrapped: tap
// the right side (or →, space) for the next, the left (or ←) to go back, hold to pause. Slides advance by themselves
// every 8 seconds and stop on the last, which has the Share picture. Numbers count up as a slide opens; with reduced
// motion they just show. Slides with nothing to say (no win yet, no player twice) are left out.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { units, cls } from "@/components/me/RecordTable";
import { ShareButton } from "@/components/live/ShareButton";
import { longDay, signed } from "@/lib/format";
import type { Shown, Wrapped } from "@/lib/wrapped";

const SECONDS = 8;

/** A number that counts up from 0 when it first shows. */
function Count({ to, fmt }: { to: number; fmt: (x: number) => string }) {
  const [x, setX] = useState(to);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    const t0 = performance.now();
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 1100);
      setX(to * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [to]);
  return <>{fmt(x)}</>;
}

function BetBox({ b, mark }: { b: Shown; mark?: string }) {
  return (
    <div className="wr-bet">
      <div className="wr-bet-top"><b>{b.title}</b><span>{b.price}</span></div>
      <ul>
        {b.legs.map((l, i) => (
          <li key={i} className={`wr-leg ${l.result}${mark && l.label === mark ? " mark" : ""}`}>
            <i aria-hidden />{l.label}{l.value && <span className="faint"> · {l.value}</span>}
          </li>
        ))}
        {b.more > 0 && <li className="faint">+{b.more} more legs</li>}
      </ul>
      <div className="wr-bet-foot faint">{b.book} · {longDay(b.day)}</div>
    </div>
  );
}

type Slide = { key: string; tone: "accent" | "pos" | "neg" | "ink"; body: ReactNode };

function slides(w: Wrapped, photo: string | null): Slide[] {
  const t = w.total, out: Slide[] = [];
  const season = w.period === "season";
  out.push({ key: "intro", tone: "accent", body: <>
    <p className="wr-kicker">BetLab Wrapped</p>
    <h2 className="wr-huge">{season ? "Your season" : `Your ${w.name}`}</h2>
    <p className="wr-line"><b><Count to={t.bets} fmt={(x) => String(Math.round(x))} /></b> bets settled over <b>{w.days}</b> day{w.days === 1 ? "" : "s"},
      {" "}<b>{w.legs}</b> leg{w.legs === 1 ? "" : "s"}{w.sports > 1 ? <>, <b>{w.sports}</b> sports</> : ""}.</p>
    <p className="wr-hint faint">Tap to go on</p>
  </> });
  out.push({ key: "bottom", tone: t.units >= 0 ? "pos" : "neg", body: <>
    <p className="wr-kicker">The bottom line</p>
    <h2 className={`wr-huge ${cls(t.units)}`}><Count to={t.units} fmt={(x) => units(x)} /></h2>
    <p className="wr-line">{t.won}-{t.lost}{t.push ? `-${t.push}` : ""}{w.roi !== null && <> · ROI <b className={cls(w.roi)}>{signed(w.roi)}</b></>}</p>
    <p className="wr-sub faint">{t.units > 0 ? "Up is up. Plenty of people can't say that." : t.units < 0 ? "Not this time. Every good run starts somewhere." : "Dead even."}</p>
  </> });
  if (w.best) out.push({ key: "best", tone: "pos", body: <>
    <p className="wr-kicker">Your biggest hit</p>
    <h2 className="wr-big pos"><Count to={w.best.units} fmt={(x) => units(x)} /></h2>
    <BetBox b={w.best} />
  </> });
  if (w.heartbreak) out.push({ key: "heart", tone: "neg", body: <>
    <p className="wr-kicker">The leg that broke your heart</p>
    <h2 className="wr-big">{w.heartbreak.hit} of {w.heartbreak.hit + 1}</h2>
    <p className="wr-line">One leg from {w.heartbreak.bet.price}: <b className="neg">{w.heartbreak.leg.label}</b>
      {w.heartbreak.leg.value ? <> ({w.heartbreak.leg.value})</> : ""}.</p>
    <BetBox b={w.heartbreak.bet} mark={w.heartbreak.leg.label} />
  </> });
  if (w.player) {
    const p = w.player;
    out.push({ key: "player", tone: "accent", body: <>
      <p className="wr-kicker">Your player</p>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {photo && <img className="wr-photo" src={photo} alt="" />}
      <h2 className="wr-big">{p.name}</h2>
      <p className="wr-line"><b>{p.legs.length}</b> legs{p.topStat ? <>, mostly {p.topStat}</> : ""}.
        {p.won + p.lost > 0 && <> <b>{p.won} of {p.won + p.lost}</b> graded legs hit.</>}</p>
      {p.units !== 0 && <p className="wr-sub">Your bets with a {p.name.split(" ").pop()} leg: <b className={cls(p.units)}>{units(p.units)}</b></p>}
    </> });
  }
  if (w.book && w.books.length > 1) out.push({ key: "book", tone: "accent", body: <>
    <p className="wr-kicker">Your best book</p>
    <h2 className="wr-big">{w.book.group}</h2>
    <ul className="wr-books">
      {w.books.map((l) => <li key={l.group}><span>{l.group}</span><span className="faint">{l.won}-{l.lost}</span><b className={cls(l.units)}>{units(l.units)}</b></li>)}
    </ul>
    <p className="wr-sub faint">Shopping more than one book is the easiest edge there is.</p>
  </> });
  out.push({ key: "type", tone: "accent", body: <>
    <p className="wr-kicker">Your betting type</p>
    <h2 className="wr-big">{w.persona.name}</h2>
    <p className="wr-line">{w.persona.why}</p>
  </> });
  if (w.bestDay || w.bestRun > 1) out.push({ key: "days", tone: "pos", body: <>
    <p className="wr-kicker">Your best moments</p>
    {w.bestDay && <><h2 className="wr-big pos">{units(w.bestDay.units)}</h2>
      <p className="wr-line">on {longDay(w.bestDay.day)}, from {w.bestDay.bets} bet{w.bestDay.bets === 1 ? "" : "s"}.</p></>}
    {w.bestRun > 1 && <p className="wr-line">Longest win streak: <b>{w.bestRun} in a row</b>.</p>}
    {w.busiest && w.busiest.day !== w.bestDay?.day && <p className="wr-sub faint">Busiest day: {longDay(w.busiest.day)}, {w.busiest.bets} bets.</p>}
  </> });
  if (w.badges.length) out.push({ key: "badges", tone: "accent", body: <>
    <p className="wr-kicker">Badges you earned</p>
    <h2 className="wr-big">{w.badges.length}</h2>
    <ul className="wr-badges">
      {w.badges.map((b) => <li key={b.title}><span aria-hidden>{b.icon}</span><b>{b.title}</b><span className="faint">{b.how}</span></li>)}
    </ul>
  </> });
  out.push({ key: "end", tone: "ink", body: <>
    <p className="wr-kicker">{season ? "Your season" : w.name}, wrapped</p>
    <ul className="wr-sum">
      <li><span>P/L</span><b className={cls(t.units)}>{units(t.units)}</b></li>
      <li><span>Record</span><b>{t.won}-{t.lost}{t.push ? `-${t.push}` : ""}</b></li>
      {w.best && <li><span>Biggest hit</span><b>{w.best.price}</b></li>}
      {w.player && <li><span>Your player</span><b>{w.player.name}</b></li>}
      <li><span>Your type</span><b>{w.persona.name}</b></li>
    </ul>
    <div className="actions" onClick={(e) => e.stopPropagation()}>
      <ShareButton url={`/api/wrapped?p=${w.period}`} name="betlab-wrapped.png" />
    </div>
  </> });
  return out;
}

export function WrappedStory({ w, photo }: { w: Wrapped; photo: string | null }) {
  const list = slides(w, photo);
  const [i, setI] = useState(0);
  const [held, setHeld] = useState(false);
  const last = list.length - 1;
  const go = useCallback((d: number) => setI((x) => Math.max(0, Math.min(last, x + d))), [last]);
  const down = useRef(0);

  useEffect(() => {          // advance on its own, not past the last slide, not while held, never with reduced motion
    if (held || i >= last || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setTimeout(() => go(1), SECONDS * 1000);
    return () => clearTimeout(t);
  }, [i, held, last, go]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [go]);

  const s = list[i];
  return (
    <section className={`wr tone-${s.tone}`} aria-roledescription="story" aria-label={`Wrapped, slide ${i + 1} of ${list.length}`}
      onPointerDown={() => { down.current = Date.now(); setHeld(true); }}
      onPointerUp={(e) => {
        setHeld(false);
        if (Date.now() - down.current > 400) return;              // a hold paused it: no tap
        const r = e.currentTarget.getBoundingClientRect();
        go(e.clientX - r.left < r.width * 0.3 ? -1 : 1);
      }}
      onPointerLeave={() => setHeld(false)}>
      <div className="wr-bars" aria-hidden>
        {list.map((x, k) => (
          <span key={x.key} className={k < i ? "done" : ""}>
            {k === i && <i style={{ animationDuration: `${SECONDS}s`, animationPlayState: held || i === last ? "paused" : "running" }}
                           className={i === last ? "full" : ""} />}
          </span>
        ))}
      </div>
      <div key={s.key} className="wr-slide" aria-live="polite">{s.body}</div>
      <div className="wr-nav">
        <button type="button" className="btn quiet small" onPointerUp={(e) => e.stopPropagation()} onClick={() => go(-1)} disabled={i === 0}>‹ Back</button>
        <span className="faint">{i + 1} / {list.length}</span>
        <button type="button" className="btn quiet small" onPointerUp={(e) => e.stopPropagation()} onClick={() => go(1)} disabled={i === last}>Next ›</button>
      </div>
    </section>
  );
}
