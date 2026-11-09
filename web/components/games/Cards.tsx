"use client";

// Cards (Mike, Oct 25: "cards should be like the iOS on the web app, clickable and brings up stats, also add cards for
// teams, and wherever there's a leg or a reference to a card I can click on the picture to see my stats with them").
// The trading card is the iPhone's (ios/BetLab/Games/Players.swift TradingCard): the team's colors and logo, the photo, jersey
// and position, the hit rate as a ring, the record, the last legs and the tier's foil. A tap on a card, a leg's
// picture (CardTap) or a scoreboard's logo opens the sheet: the card large, the numbers, won-lost by stat and every leg.
// The sheet asks /api/card when it wasn't handed the card (lib/cards.ts `cardOf`).
import { createContext, useCallback, useContext, useEffect, useRef, useState, type CSSProperties, type MouseEvent, type ReactNode } from "react";
import type { CardRef } from "@/lib/cards";
import type { Look } from "@/lib/headshots";
import type { Player } from "@/lib/players";
import { longDay } from "@/lib/format";
import { cls, units } from "@/components/me/RecordTable";

export type Face = { ref: CardRef; card: Player | null; look: Look | null };
type Open = (ref: CardRef, opts?: { sport?: string | null; face?: Face }) => void;

const Ctx = createContext<Open | null>(null);

const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();
export const tierOf = (p: Player | null) =>
  !p || p.won + p.lost < 3 || p.hitRate === null ? null : p.hitRate >= 0.7 ? "gold" : p.hitRate >= 0.5 ? "silver" : "bronze";

/** The hit rate as a ring: green at 50% or better, orange below (Mike, Oct 25: in the team's color a red team's 100%
 *  looked like a loss). */
function Ring({ rate, size = 46 }: { rate: number | null; size?: number }) {
  const color = (rate ?? 0) >= 0.5 ? "var(--pos)" : "var(--warn)";
  const r = size / 2 - size * 0.08, c = 2 * Math.PI * r;
  return (
    <svg className="tc-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-label={rate === null ? "No graded legs" : `${Math.round(rate * 100)}% hit`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line-2)" strokeWidth={size * 0.11} />
      {rate !== null && <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={size * 0.11} strokeLinecap="round"
        strokeDasharray={`${c * rate} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />}
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" style={{ font: `800 ${size * 0.26}px var(--font-display)` }} fill="currentColor">
        {rate === null ? "—" : `${Math.round(rate * 100)}%`}
      </text>
    </svg>
  );
}

function Photo({ look, name, kind, size }: { look: Look | null; name: string; kind: CardRef["kind"]; size: number }) {
  const [ok, setOk] = useState(true);
  const src = look?.photo;
  // eslint-disable-next-line @next/next/no-img-element
  return src && ok ? <img className={`tc-photo ${kind}`} src={src} alt="" height={size} loading="lazy" onError={() => setOk(false)} />
    : <span className="tc-initials" aria-hidden>{initials(name)}</span>;
}

/** One player or team as a trading card. */
export function TradingCard({ face, onClick }: { face: Face; onClick?: () => void }) {
  const { card: p, look, ref } = face;
  const name = p?.name ?? ref.name, tier = tierOf(p);
  const style = { "--tc": look?.color ?? "#5b6472" } as CSSProperties;
  const sub = ref.kind === "team" ? p?.sport ?? "" : [look?.teamShort ?? look?.team ?? p?.sport, look?.position].filter(Boolean).join(" · ");
  return (
    <button type="button" className={`tcard${tier ? ` ${tier}` : ""}`} style={style} onClick={onClick} aria-label={`${name}: your record`}>
      <span className="tc-top">
        {look?.logo && ref.kind === "player" && /* eslint-disable-next-line @next/next/no-img-element */
          <img className="tc-logo" src={look.logo} alt="" width={120} height={120} loading="lazy" />}
        <Photo look={look} name={name} kind={ref.kind} size={ref.kind === "team" ? 84 : 118} />
        {look?.jersey && <b className="tc-jersey">#{look.jersey}</b>}
        {tier && <span className="tc-tier">{tier}</span>}
      </span>
      <span className="tc-body">
        <b className="tc-name">{name}</b>
        <span className="tc-sub">{sub}</span>
        <span className="tc-mid">
          <Ring rate={p?.hitRate ?? null} />
          <span><b className="tc-rec">{p ? `${p.won}–${p.lost}` : "0–0"}</b><span className="tc-stat">{p?.topStat ?? ""}</span></span>
        </span>
        <span className="tc-dots" aria-label="Most recent legs">
          {(p?.legs ?? []).slice(0, 8).map((l, i) => <i key={i} className={l.result} title={`${l.label}: ${l.result}`} />)}
        </span>
        {p && p.won + p.lost > 0 && <b className={`tc-units ${cls(p.units)}`}>{units(p.units, 1)}</b>}
      </span>
    </button>
  );
}

/** Won-lost by stat, the most-bet first. */
function byStat(p: Player) {
  const m = new Map<string, { won: number; lost: number; open: number }>();
  for (const l of p.legs) {
    const s = m.get(l.stat) ?? { won: 0, lost: 0, open: 0 };
    if (l.result === "won") s.won++; else if (l.result === "lost") s.lost++; else if (l.result === "open") s.open++;
    m.set(l.stat, s);
  }
  return [...m.entries()].sort((a, b) => (b[1].won + b[1].lost + b[1].open) - (a[1].won + a[1].lost + a[1].open));
}

const ICON: Record<string, string> = { won: "✓", lost: "✕", void: "–", open: "○" };

function Detail({ face }: { face: Face }) {
  const { card: p, look, ref } = face;
  const name = p?.name ?? ref.name;
  const style = { "--tc": look?.color ?? "#5b6472" } as CSSProperties;
  return (
    <div className="cs-body" style={style}>
      <div className="cs-head">
        <Photo look={look} name={name} kind={ref.kind} size={ref.kind === "team" ? 110 : 170} />
        <div className="cs-who">
          {look?.jersey && <b className="cs-jersey">#{look.jersey}</b>}
          <h2>{name}</h2>
          <span>{ref.kind === "team" ? p?.sport ?? "" : [look?.team ?? p?.sport, look?.position].filter(Boolean).join(" · ")}</span>
        </div>
      </div>
      {!p ? <p className="faint cs-none">No bets with {ref.kind === "team" ? "this team" : "this player"} yet.</p> : <>
        <div className="cs-nums">
          <Ring rate={p.hitRate} size={64} />
          <span><b>{p.won}–{p.lost}</b><small>legs{p.open ? ` · ${p.open} open` : ""}</small></span>
          <span><b>{p.bets}</b><small>{p.bets === 1 ? "bet" : "bets"}</small></span>
          <span><b className={cls(p.units)}>{p.won + p.lost > 0 ? units(p.units, 1) : "—"}</b><small>units</small></span>
        </div>
        <h3 className="section-label">By {ref.kind === "team" ? "market" : "stat"}</h3>
        <ul className="cs-stats">
          {byStat(p).map(([stat, s]) => <li key={stat}><span>{stat[0].toUpperCase() + stat.slice(1)}</span>
            <span className="faint">{s.won}–{s.lost}{s.open ? ` · ${s.open} open` : ""}</span></li>)}
        </ul>
        <h3 className="section-label">Every leg · {p.legs.length}</h3>
        <ul className="cs-legs">
          {p.legs.map((l, i) => <li key={i} className={l.result}><i aria-hidden>{ICON[l.result]}</i>
            <span>{l.label}{l.game && <small className="faint cs-game">{l.game}</small>}</span>
            <span className="faint">{longDay(l.day)}</span></li>)}
        </ul>
      </>}
    </div>
  );
}

/** The sheet any picture opens; wraps the whole app (app/layout.tsx). */
export function CardProvider({ children }: { children: ReactNode }) {
  const [face, setFace] = useState<Face | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dlg = useRef<HTMLDialogElement>(null);
  const asked = useRef(0);

  const open = useCallback<Open>((ref, opts) => {
    setError(null);
    const n = ++asked.current;
    if (opts?.face) { setFace(opts.face); setBusy(false); return; }
    setFace({ ref, card: null, look: null });
    setBusy(true);
    const q = new URLSearchParams({ kind: ref.kind, name: ref.name, ...(ref.abbr ? { abbr: ref.abbr } : {}), ...(opts?.sport ? { sport: opts.sport } : {}) });
    fetch(`/api/card?${q}`).then((r) => r.json()).then((j) => {
      if (n !== asked.current) return;
      if (j.error) setError(j.error); else setFace({ ref, card: j.card, look: j.look });
    }).catch(() => n === asked.current && setError("Couldn't load your stats.")).finally(() => n === asked.current && setBusy(false));
  }, []);

  useEffect(() => {
    const d = dlg.current;
    if (!d) return;
    if (face && !d.open) d.showModal();
    if (!face && d.open) d.close();
  }, [face]);

  const backdrop = (e: MouseEvent<HTMLDialogElement>) => { if (e.target === dlg.current) setFace(null); };
  return (
    <Ctx.Provider value={open}>
      {children}
      <dialog ref={dlg} className="cardsheet" onClose={() => setFace(null)} onClick={backdrop}>
        {face && <>
          <button type="button" className="cs-close" onClick={() => setFace(null)} aria-label="Close">✕</button>
          {error ? <p className="warn-text cs-none">{error}</p> : <Detail face={face} />}
          {busy && <p className="faint cs-none">Loading your record…</p>}
        </>}
      </dialog>
    </Ctx.Provider>
  );
}

export const useCard = () => useContext(Ctx);

/** A picture that opens its card: a leg's headshot or logo, a scoreboard's logo. Inside a link or a draggable tile it
 *  stops the click there. Without the provider (a page outside the app's layout) it's just the picture. */
export function CardTap({ card, sport, className, children }: { card: CardRef | null | undefined; sport?: string | null; className?: string; children: ReactNode }) {
  const open = useCard();
  if (!card || !open) return <>{children}</>;
  return (
    <button type="button" className={`cardtap${className ? ` ${className}` : ""}`} aria-label={`${card.name}: your record`}
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); open(card, { sport }); }}>{children}</button>
  );
}

/** A shelf of cards (Stats > Your players / Your teams): sport chips, then the cards in a row you swipe through. */
export function CardShelf({ title, faces, foot }: { title: string; faces: Face[]; foot?: string }) {
  const open = useCard();
  const [sport, setSport] = useState<string | null>(null);
  if (!faces.length) return null;
  const sports = [...new Set(faces.map((f) => f.card?.sport ?? "Other"))];
  const shown = faces.filter((f) => !sport || (f.card?.sport ?? "Other") === sport);
  return (
    <section className="shelf">
      <h2 className="section-label">{title} · {faces.length}</h2>
      {sports.length > 1 && (
        <nav className="chips" aria-label="Sport">
          <button type="button" aria-current={!sport} onClick={() => setSport(null)}>All</button>
          {sports.map((s) => <button type="button" key={s} aria-current={s === sport} onClick={() => setSport(s)}>{s}</button>)}
        </nav>
      )}
      <div className="shelf-row">
        {shown.map((f) => <TradingCard key={`${f.ref.kind}-${f.card?.key ?? f.ref.name}`} face={f} onClick={() => open?.(f.ref, { face: f })} />)}
      </div>
      {foot && <p className="faint shelf-foot">{foot}</p>}
    </section>
  );
}
