"use client";

// My bets' live tracker (Oct 23), in the style of FanDuel's and DraftKings' open-bet cards: a score strip per game
// with team logos, each leg with the player's headshot (or the team's logo), its status and a progress bar to its
// target, a parlay's legs as segments. Numbers tick when they change, a leg glows when it hits, and a bet that cashes
// gets confetti and its winnings counting up (Mike, Oct 23: "woah + cool"). Motion is off for reduce-motion users.
// One poll of /api/live feeds every card: every 20 s while a game is in progress (or starts within 20 minutes), paused
// while the tab is hidden; otherwise every 5 minutes so a game that starts is picked up.

import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import type { BetLive, GameLive, LegLive, Side } from "@/lib/live";
import { inOrder } from "@/lib/format";
import { CardTap } from "@/components/games/Cards";
import { Art, ArtStack, type ArtOf } from "@/components/ui/Art";
import { Ring, type RingState } from "@/components/ui/Ring";
import { Glow, LivePill } from "@/components/ui/Kit";

type LiveData = { at: string; bets: Record<string, BetLive>; live: boolean } | null;
const Ctx = createContext<LiveData>(null);
export const useLive = () => useContext(Ctx);

const FAST = 20_000, SLOW = 300_000;
const CELEBRATE_MS = 4500;     // a won bet stays on Open this long before it moves to Settled

const calm = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function LiveProvider({ children, known = [], src = "/api/live" }: { children: ReactNode; known?: string[]; src?: string }) {
  const [data, setData] = useState<LiveData>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const router = useRouter();
  const moved = useRef(new Set(known));      // bets the page already files under Settled from their live state
  useEffect(() => {
    // a bet that settles live (lost, or won on every leg) moves to Settled: re-render the page once per new one (the
    // server files it there); a win waits for its celebration first
    const fresh = data ? Object.entries(data.bets).filter(([id, b]) => b.settle && !moved.current.has(id)) : [];
    if (!fresh.length) return;
    fresh.forEach(([id]) => moved.current.add(id));
    const t = setTimeout(() => router.refresh(), fresh.some(([, b]) => b.settle === "won") ? CELEBRATE_MS : 0);
    return () => clearTimeout(t);
  }, [data, router]);
  useEffect(() => {
    let stop = false, run = 0;     // the newest run alone goes on: a wake during a fetch must not start a second loop (Nov 4)
    // the last good answer: a failed or timed-out poll keeps the cadence it set (Nov 9: the effect's own `data` was the
    // first render's null, so one 500 mid-game slowed the scores to every 5 minutes)
    let last: LiveData = null;
    const soon = (d: LiveData) => !!d && (d.live || Object.values(d.bets).some((b) => b.games.some((g) =>
      g.state === "pre" && Date.parse(g.start) - Date.now() < 20 * 60_000)));
    const tick = async () => {
      if (stop) return;
      const mine = ++run;
      if (!document.hidden) {
        try {
          // a hung request must not stop the loop: give up after 15 s and try again on the next tick
          const r = await fetch(src, { cache: "no-store", signal: AbortSignal.timeout(15_000) });
          if (r.ok) { const next: LiveData = await r.json(); if (!stop && mine === run) { last = next; setData(next); } }
        } catch { /* offline or timed out: try again next tick */ }
      }
      if (stop || mine !== run) return;
      timer.current = setTimeout(tick, soon(last) ? FAST : SLOW);
    };
    const wake = () => { if (!document.hidden) { if (timer.current) clearTimeout(timer.current); tick(); } };
    tick();
    document.addEventListener("visibilitychange", wake);
    window.addEventListener("betlab:pulse", wake);           // something changed (LivePulse): look now
    return () => { stop = true; if (timer.current) clearTimeout(timer.current); document.removeEventListener("visibilitychange", wake); window.removeEventListener("betlab:pulse", wake); };
  }, [src]);
  return <Ctx.Provider value={data}>{children}</Ctx.Provider>;
}

// ------------------------------------------------------------------------------------------------ motion

/** The previous value of something across renders. */
function usePrev<T>(v: T): T | undefined {
  const r = useRef<T | undefined>(undefined);
  useEffect(() => { r.current = v; }, [v]);
  return r.current;
}

/** A number that counts from its old value to its new one (600 ms, eased). */
export function Ticker({ value, digits = 0, className }: { value: number; digits?: number; className?: string }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (from.current === value || calm()) { from.current = value; setShown(value); return; }
    const a = from.current, start = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / 600), e = 1 - (1 - k) ** 3;
      setShown(a + (value - a) * e);
      if (k < 1) raf = requestAnimationFrame(step); else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span className={className}>{shown.toFixed(digits)}</span>;
}

/** A class that's on for `ms` after `key` changes (not on first render): a pulse when a score or status moves. */
function useFlash(key: unknown, ms = 1200): boolean {
  const prev = usePrev(key);
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (prev === undefined || prev === key) return;
    setOn(true);
    const t = setTimeout(() => setOn(false), ms);
    return () => clearTimeout(t);
  }, [key, prev, ms]);
  return on;
}

// ----------------------------------------------------------------------------------------------- pieces

export function Logo({ src, alt, size = 18 }: { src?: string | null; alt: string; size?: number }) {
  const [ok, setOk] = useState(true);
  if (!src || !ok) return null;
  // eslint-disable-next-line @next/next/no-img-element
  return <img className="llogo" src={src} alt={alt} width={size} height={size} loading="lazy" onError={() => setOk(false)} />;
}

/** How a leg's ring reads (the overhaul, Nov 4): how full, which color, and the number on its badge. */
export function legRing(l: LegLive): { value: number | null; state: RingState; badge: string | null } {
  const n = (x: number) => String(+x.toFixed(1));
  const counted = l.current !== null && l.target !== null && l.target > 0;
  if (l.status === "won") return { value: 1, state: "won", badge: counted ? n(l.current!) : "\u2713" };
  if (l.status === "lost") return { value: 1, state: "lost", badge: counted ? n(l.current!) : "\u2715" };
  if (l.status === "void") return { value: 1, state: "void", badge: "\u2013" };
  if (l.status === "winning" || l.status === "losing" || l.status === "tied") {
    const lead = l.current;
    return { value: l.status === "winning" ? 0.78 : l.status === "tied" ? 0.5 : 0.24, state: l.status === "winning" ? "ahead" : l.status === "tied" ? "live" : "behind",
             badge: lead === null ? null : lead > 0 ? `+${n(lead)}` : lead < 0 ? `\u2212${n(-lead)}` : "0" };
  }
  if (l.status === "pending" || l.status === "unknown") return { value: 0, state: "pending", badge: null };
  if (!counted) return { value: 0.5, state: "live", badge: null };
  const k = l.current! / l.target!;
  const under = / of room$/.test(l.text);           // an under: the ring is how much of its room is used
  return { value: k, state: under && k > 0.8 ? "behind" : "live", badge: n(l.current!) };
}

/** A leg's status in words under its name: the tracker's own text, with the count for a leg still going. */
function legText(l: LegLive): string {
  const counted = l.current !== null && l.target !== null && l.target > 0;
  const unit = l.unit && l.unit !== "total" ? ` ${l.unit}` : "";
  if (l.status === "won") return counted && !/^Done/.test(l.text) ? `In \u00b7 ${+l.current!.toFixed(1)}${unit}` : l.text && l.text !== "Hit" ? `In \u00b7 ${l.text}` : "In";
  if (l.status === "pending" && counted) return `${l.text} \u00b7 needs ${l.target}${unit}`;
  if (counted && !["lost", "void"].includes(l.status) && !/ of /.test(l.text)) return `${l.text} \u00b7 ${+l.current!.toFixed(1)} of ${l.target}${unit}`;
  return l.text;
}

/** The letters in the ring of a leg that's on no one (a total, both teams to score, a draw). */
const marketMark = (label: string) => (/^over\b/i.test(label) ? "O" : /^under\b/i.test(label) ? "U" : /^both teams/i.test(label) ? "BTS" : /^draw/i.test(label) ? "X" : null);

/** A leg's ring alone (Today's live card): the picture, how far along, the number. */
export function LegRing({ l, size = 46, tap = true }: { l: LegLive; size?: number; tap?: boolean }) {
  const r = legRing(l);
  const ring = (
    <Ring value={r.value} state={r.state} badge={r.badge} size={size} label={`${l.label}: ${legText(l) || l.status}`}>
      <Art src={l.img} name={l.card?.name ?? l.label} abbr={l.card ? (l.card.kind === "team" ? l.card.abbr : null) : marketMark(l.label)} kind={l.card?.kind ?? "team"} />
    </Ring>
  );
  return tap ? <CardTap card={l.card ?? null}>{ring}</CardTap> : ring;
}

export function Leg({ l }: { l: LegLive }) {
  const state = ["won", "lost", "void"].includes(l.status) ? l.status : l.status === "pending" ? "pending" : l.status === "losing" ? "behind" : "live";
  const prev = usePrev(l.status);
  const [glow, setGlow] = useState(false);
  useEffect(() => {
    if (prev && prev !== "won" && l.status === "won") { setGlow(true); const t = setTimeout(() => setGlow(false), 1600); return () => clearTimeout(t); }
  }, [l.status, prev]);
  const tone = l.status === "won" || l.status === "winning" ? " pos" : l.status === "lost" ? " neg" : "";
  return (
    <li className={`rleg ${state}${glow ? " justhit" : ""}`}>
      <LegRing l={l} />
      <span className="rleg-body">
        <span className="rleg-label">{l.label}</span>
        <span className={`sub${tone}`}>{legText(l)}
          {l.onCourt === true && <span className="rleg-court on"> {"\u00b7"} on the court</span>}
          {l.onCourt === false && <span className="rleg-court"> {"\u00b7"} on the bench</span>}</span>
      </span>
    </li>
  );
}

const LEG_DONE = ["won", "lost", "void"];
/** A parlay's legs as dots: green in, red lost, a ring for one in play. */
export function LegDots({ legs }: { legs: LegLive[] }) {
  return <span className="dots" aria-hidden>{legs.map((l, i) => <i key={i} className={LEG_DONE.includes(l.status) ? l.status : ["pending", "unknown"].includes(l.status) ? "" : "live"} />)}</span>;
}

// ----------------------------------------------------------------------------------------------- the scoreboard

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });

function BoardTeam({ s, g, right }: { s: Side; g: GameLive; right?: boolean }) {
  const started = g.state !== "pre", ufc = g.sport === "ufc";
  return (
    <div className={`wb-team${right ? " right" : ""}`}>
      <CardTap card={ufc ? null : { kind: "team", name: s.name, abbr: s.abbr }} sport={g.sport}>
        <span className="wb-logo" data-abbr={(s.abbr || s.name).slice(0, 4)}><Logo src={s.logo} alt={s.name} size={44} /></span>
      </CardTap>
      <div className="wb-num">
        {!ufc && started ? <b><Ticker value={s.score ?? 0} /></b> : <b className="wb-name">{ufc ? s.name : ""}</b>}
        <span className="wb-abbr">{ufc ? "" : s.abbr || s.name}{g.ball && g[g.ball] === s && <i className="bb-ball" role="img" aria-label="has the ball" />}</span>
      </div>
    </div>
  );
}

/** A game's scoreboard in its teams' colors (the wall's, Oct 24; `compact` in My bets' trackers, from the iPhone). */
export function Board({ g, compact = false }: { g: GameLive; compact?: boolean }) {
  const style = { "--ca": g.away.color ?? "#5b6472", "--ch": g.home.color ?? "#5b6472" } as CSSProperties;
  return (
    <div className={`wb-board ${g.state}${compact ? " compact" : ""}`} style={style}>
      <BoardTeam s={g.away} g={g} />
      <span className="wb-mid">
        <span className={`wb-pill${g.redZone ? " redzone" : ""}`}>
          {g.state === "in" ? <><i className="ldot" /> {g.redZone ? "RED ZONE" : "LIVE"}</> : g.state === "post" ? "FINAL" : time(g.start)}
          {g.state === "in" && <small>{g.detail}</small>}
        </span>
        {g.state === "in" && g.down && <span className="wb-down">{g.down}</span>}
      </span>
      <BoardTeam s={g.home} g={g} right />
    </div>
  );
}


/** What's inside only for a bet the tracker found no game for (Oct 24, from the iPhone: "the tracker is the legs"). */
export function WithoutTracker({ id, children }: { id: string; children: ReactNode }) {
  const data = useContext(Ctx);
  return data?.bets[id]?.games.length ? null : <>{children}</>;
}

// ----------------------------------------------------------------------------------------------- the cash

const CONFETTI = ["var(--pos)", "var(--accent)", "#f6c445", "#ff6fb1", "#5ad1ff", "#ffffff"];

/** Confetti and the winnings counting up, over the card (Mike, Oct 23: the cash animation). */
function Cash({ win }: { win: number | null }) {
  const pieces = useRef(Array.from({ length: 46 }, (_, i) => ({
    left: Math.random() * 100, delay: Math.random() * 0.35, dur: 1.6 + Math.random() * 1.2, rot: Math.random() * 720 - 360,
    drift: Math.random() * 60 - 30, color: CONFETTI[i % CONFETTI.length], w: 5 + Math.random() * 5, round: i % 3 === 0,
  }))).current;
  return (
    <div className="lcash" aria-live="polite">
      {!calm() && pieces.map((p, i) => (
        <i key={i} style={{ left: `${p.left}%`, background: p.color, width: p.w, height: p.round ? p.w : p.w * 1.8,
          borderRadius: p.round ? "50%" : 2, animationDelay: `${p.delay}s`, animationDuration: `${p.dur}s`,
          "--rot": `${p.rot}deg`, "--drift": `${p.drift}px` } as CSSProperties} />
      ))}
      <div className="lcash-badge"><span>CASHED</span>{win !== null && <b>+<Ticker value={win} digits={2} />u</b>}</div>
    </div>
  );
}

// ----------------------------------------------------------------------------------------------- one bet

const nameOf = (s: Side) => s.abbr || s.name;

function BigSide({ s, g, right, tap }: { s: Side; g: GameLive; right?: boolean; tap: boolean }) {
  const ufc = g.sport === "ufc", started = g.state !== "pre";
  const flash = useFlash(s.score);
  const ball = !!g.ball && g[g.ball] === s;
  const logo = (
    <CardTap card={ufc || !tap ? null : { kind: "team", name: s.name, abbr: s.abbr }} sport={g.sport}>
      <span className="bb-logo"><Art src={s.logo} name={s.name} abbr={s.abbr} color={s.color} alt={s.name} size={48} kind={ufc ? "player" : "team"} />
        {ball && <i className="bb-ball" title="Has the ball" role="img" aria-label="has the ball" />}</span>
    </CardTap>
  );
  const num = !ufc && started ? <span className={`score-num${flash ? " bump" : ""}`}><Ticker value={s.score ?? 0} /></span>
    : <span className="bb-name">{ufc ? s.name : nameOf(s)}</span>;
  return <div className={`bb-side${right ? " right" : ""}`}>{right ? <>{num}{logo}</> : <>{logo}{num}</>}</div>;
}

/** One game's score, big, between its two logos, the clock as a pill (the overhaul's live card and game page). */
export function BigBoard({ g, tap = true }: { g: GameLive; tap?: boolean }) {
  const tall = g.sport === "ufc" || (g.state !== "pre" && Math.max(g.away.score ?? 0, g.home.score ?? 0) >= 100);
  return (
    <div className={`bb ${g.state}${tall ? " tall" : ""}`}>
      <BigSide s={inOrder(g.sport, g.away, g.home)[0]} g={g} tap={tap} />
      <span className="bb-mid">
        <LivePill state={g.state} detail={g.detail} start={g.start} note={g.redZone ? "Red zone" : null} />
        {g.state === "in" && g.down && <span className="sub">{g.down}</span>}
      </span>
      <BigSide s={inOrder(g.sport, g.away, g.home)[1]} g={g} right tap={tap} />
    </div>
  );
}

/** One game as a line: small logos, the score, the clock (a parlay across games, the legs' group headers). */
export function GameLine({ g }: { g: GameLive }) {
  const ufc = g.sport === "ufc", started = g.state !== "pre";
  const [a, b] = inOrder(g.sport, g.away, g.home);       // soccer: home first (Nov 5)
  return (
    <span className={`gline ${g.state}`}>
      <Art src={a.logo} name={a.name} abbr={a.abbr} color={a.color} size={20} kind={ufc ? "player" : "team"} />
      <b>{nameOf(a)}{!ufc && started ? ` ${a.score ?? 0}` : ""}</b>
      <span className="faint">{ufc || (!started && a === g.home) ? "vs" : started ? "\u2013" : "@"}</span>
      <b>{!ufc && started ? `${b.score ?? 0} ` : ""}{nameOf(b)}</b>
      <Art src={b.logo} name={b.name} abbr={b.abbr} color={b.color} size={20} kind={ufc ? "player" : "team"} />
      <LivePill state={g.state} detail={g.detail} start={g.start} note={g.redZone ? "Red zone" : null} />
    </span>
  );
}

/** The pictures a bet stands on: each leg's own (its player or team), then its games' teams, no picture twice. */
export function betArt(b: BetLive): ArtOf[] {
  const seen = new Set<string>(), out: ArtOf[] = [];
  const add = (a: ArtOf) => { const k = a.src ?? a.name; if (!seen.has(k)) { seen.add(k); out.push(a); } };
  for (const l of b.legs) if (l.img) add({ src: l.img, name: l.card?.name ?? l.label, kind: l.card?.kind ?? "team" });
  if (!out.length) for (const g of b.games) for (const s of [g.away, g.home]) add({ src: s.logo, name: s.name, abbr: s.abbr, color: s.color });
  return out;
}

/** The two colors behind a bet's card: its one game's teams, or the first colors among a parlay's games. */
export function betColors(b: BetLive | undefined): (string | null | undefined)[] {
  if (!b?.games.length) return [];
  if (b.games.length === 1) return [b.games[0].away.color, b.games[0].home.color];
  const colors = [...new Set(b.games.flatMap((g) => [g.away.color, g.home.color]).filter(Boolean))];
  return [null, colors[0]];
}

/** A bet's card: the glow in its teams' colors once the tracker knows them, and the confetti when it cashes while you
 * watch. `win`: units it pays, for the cash animation. */
export function BetGlow({ id, className = "", win = null, children }: { id: string; className?: string; win?: number | null; children: ReactNode }) {
  const data = useContext(Ctx);
  const b = data?.bets[id];
  const prevSettle = usePrev(b?.settle);
  const [cash, setCash] = useState(false);
  useEffect(() => {
    // confetti only when a bet turns won while you watch (not on load), or on demand (betlab:celebrate, for testing)
    if (b?.settle === "won" && prevSettle !== undefined && prevSettle !== "won") setCash(true);
  }, [b?.settle, prevSettle]);
  useEffect(() => {
    const on = (e: Event) => { if ((e as CustomEvent).detail === id) setCash(true); };
    window.addEventListener("betlab:celebrate", on);
    return () => window.removeEventListener("betlab:celebrate", on);
  }, [id]);
  useEffect(() => { if (!cash) return; const t = setTimeout(() => setCash(false), CELEBRATE_MS); return () => clearTimeout(t); }, [cash]);
  return (
    <Glow as="article" colors={betColors(b)} className={`betk ${className}${b ? ` l-${b.status}` : ""}${cash ? " cashing" : ""}`}>
      {cash && <Cash win={win} />}
      {children}
    </Glow>
  );
}

/** The top of a bet's card: one game's big score, or a parlay's pictures and its games as lines. Nothing when the
 * tracker found no game. */
export function LiveTop({ id, compact = false }: { id: string; compact?: boolean }) {
  const b = useContext(Ctx)?.bets[id];
  if (!b || !b.games.length) return null;
  if (compact) return <div className="bk-multi"><ArtStack items={[...b.games.flatMap((g) => [g.away, g.home]).map((x) => ({ src: x.logo, name: x.name, abbr: x.abbr, color: x.color }))]} max={6} size={28} />
    <span className="sub">{b.games.length === 1 ? `${nameOf(b.games[0].away)}${b.games[0].sport === "ufc" ? "" : ` ${b.games[0].away.score ?? ""}`} @ ${nameOf(b.games[0].home)}${b.games[0].sport === "ufc" ? "" : ` ${b.games[0].home.score ?? ""}`}` : `${b.games.length} games`}</span></div>;
  if (b.games.length === 1) return <><BigBoard g={b.games[0]} /><hr className="hairline" /></>;
  return (
    <>
      <div className="bk-multi">
        <ArtStack items={betArt(b)} max={6} />
        <span className="sub">{b.games.length} games{b.games.some((g) => g.state === "in") ? ` \u00b7 ${b.games.filter((g) => g.state === "in").length} live` : ""}</span>
      </div>
      <hr className="hairline" />
    </>
  );
}

/** One bet's legs as rings with their status lines, game by game for a parlay across games; nothing when none of its
 * games was found. `collapsed` (Settled, Mike Oct 23) folds them behind a one-line summary: the dots and the result. */
export function LiveBet({ id, collapsed = false }: { id: string; collapsed?: boolean }) {
  const data = useContext(Ctx);
  const b = data?.bets[id];
  if (!b || !b.games.length) return null;
  const many = b.legs.length > 1, multi = b.games.length > 1;
  // one section per game, its legs under its score line (an SGP+ reads game by game, as FanDuel shows it); legs whose
  // game isn't on today come last
  const sections = b.games.map((g) => ({ g, legs: b.legs.filter((l) => l.gameKey === g.key) }));
  const elsewhere = b.legs.filter((l) => !l.gameKey || !b.games.some((g) => g.key === l.gameKey));
  const count = b.status === "lost" ? "Lost" : b.status === "won" ? "Won" : `${b.hit} of ${b.total} in`;
  const body = (
    <div className={`ltrack2 ${b.status}`}>
      {sections.map(({ g, legs }) => (
        <section className="lgame2" key={g.key}>
          {multi && <GameLine g={g} />}
          <ul className="rlegs">{legs.map((l, i) => <Leg key={`${i}-${l.label}`} l={l} />)}</ul>
        </section>
      ))}
      {elsewhere.length > 0 && (
        <section className="lgame2">
          <span className="gline pre"><span className="faint">Not on today</span></span>
          <ul className="rlegs">{elsewhere.map((l, i) => <Leg key={`x${i}-${l.label}`} l={l} />)}</ul>
        </section>
      )}
    </div>
  );
  const dots = multi ? <div className="bk-dots" aria-label={`${b.hit} of ${b.total} legs in`}><LegDots legs={b.legs} /><span className="sub">{count}</span></div> : null;
  if (collapsed || (multi && b.legs.length > 4)) {
    return (
      <details className={`bk-fold ${b.status}`}>
        <summary>
          {many ? <LegDots legs={b.legs} /> : null}
          <span className="sub">{many ? count : b.legs[0]?.text ?? ""}</span>
          <span className="bk-fold-more">Legs</span>
        </summary>
        {body}
      </details>
    );
  }
  return <>{dots}{body}</>;
}

/** "3 live" next to Open: how many open bets have a game in progress. */
export function LiveCount() {
  const data = useContext(Ctx);
  const n = data ? Object.values(data.bets).filter((b) => b.games.some((g) => g.state === "in")).length : 0;
  return n ? <span className="livepill"><i aria-hidden />{n} live</span> : null;
}
