"use client";

// Today's live cards (the overhaul, Nov 4; they replace the Oct 24 game-day hub's rows): each open bet still alive as
// one glow card from the same /api/live poll as Live: its game's logos and big score with the clock, or a parlay's
// pictures across games; the bet's name, how many legs are in and its price; every leg as a ring. A lost bet leaves
// (Mike, Oct 24: the red cards "make me feel bad"); it stays in Live for the record. Live games first.

import Link from "next/link";
import { useEffect, useState } from "react";
import { BigBoard, GameLine, LegRing, LiveProvider, betArt, betColors, useLive } from "@/components/live/LiveBets";
import { ArtStack } from "@/components/ui/Art";
import { Glow } from "@/components/ui/Kit";
import { fmtAm } from "@/lib/format";
import { countdown } from "@/lib/gameday";
import type { BetLive } from "@/lib/live";

export type OpenBet = { id: string; name: string; price: number | null };
export type HubLock = { slate: string; title: string; at: string };

/** The time, ticking; null until the page is on the device, so the server's render and the first client one agree. */
function useNow(ms = 1000): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => { setNow(Date.now()); const t = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(t); }, [ms]);
  return now;
}

const RINGS = 5;

type Shown = { bet: OpenBet; b: BetLive };

/** One game, once: its score, then every open bet on it as a row (Mike, Nov 4: "it shouldn't have two cards for the
 * same game"). A bet across several games has a card of its own, headed by its pictures. */
function Card({ group }: { group: Shown[] }) {
  const b = group[0].b;
  const one = b.games.length === 1 ? b.games[0] : null;
  const live = b.games.filter((g) => g.state === "in");
  return (
    <Glow href="/bets" colors={betColors(b)} className={`tl-card ${group.every((x) => x.b.status === "won") ? "won" : b.status}`}>
      {one ? <BigBoard g={one} tap={false} /> : (
        <div className="tl-multi">
          <ArtStack items={betArt(b)} max={5} />
          <span className="tl-lines">{(live.length ? live : b.games).slice(0, 2).map((g) => <GameLine key={g.key} g={g} />)}
            {b.games.length > 2 && <span className="sub">{b.games.length} games{live.length ? ` · ${live.length} live` : ""}</span>}</span>
        </div>
      )}
      {group.map(({ bet, b }) => {
        const status = b.status === "won" ? "Won" : b.legs.length > 1 ? `${b.hit} of ${b.total} in` : b.legs[0]?.text || (b.games.some((g) => g.state === "in") ? "Live" : "Not started");
        return (
          <div key={bet.id} className="tl-bet">
            <hr className="hairline" />
            <div className="tl-foot">
              <div className="tl-what">
                <span className="tl-name">{bet.name}</span>
                <span className="sub">{status}{bet.price !== null && <> · <b className="numx">{fmtAm(bet.price)}</b></>}</span>
              </div>
              <span className="tl-rings">
                {b.legs.slice(0, RINGS).map((l, i) => <LegRing key={`${i}-${l.label}`} l={l} tap={false} size={b.legs.length > 4 ? 40 : 46} />)}
                {b.legs.length > RINGS && <span className="sub">+{b.legs.length - RINGS}</span>}
              </span>
            </div>
          </div>
        );
      })}
    </Glow>
  );
}

/** Bets on a single game share that game's card, in the order given; the rest stand alone. */
function byGame(shown: Shown[]): Shown[][] {
  const out: Shown[][] = [];
  const at = new Map<string, number>();
  for (const x of shown) {
    const key = x.b.games.length === 1 ? x.b.games[0].key : null;
    if (key !== null && at.has(key)) out[at.get(key)!].push(x);
    else { if (key !== null) at.set(key, out.length); out.push([x]); }
  }
  return out;
}

function alive(bets: OpenBet[], live: Record<string, BetLive> | undefined) {
  const shown = bets.map((n) => ({ bet: n, b: live?.[n.id] })).filter((x) => x.b && x.b.games.length && x.b.status !== "lost") as Shown[];
  const order = (b: BetLive) => (b.games.some((g) => g.state === "in") ? 0 : b.status === "pending" ? 1 : 2);
  return shown.sort((a, b) => order(a.b) - order(b.b));
}

function Cards({ bets }: { bets: OpenBet[] }) {
  const data = useLive();
  const shown = alive(bets, data?.bets);
  if (!data) return bets.length ? <p className="sub tl-wait">Loading your bets…</p> : null;
  if (!shown.length) return null;
  return (
    <section className="tl" aria-label="Your live bets">
      <div className="tl-head"><h2 className="section-title"><span>Live</span><small>{shown.length}</small>
        <span className="section-right"><Link href="/bets">All bets</Link></span></h2></div>
      <div className="tl-cards">{byGame(shown).map((g) => <Card key={g[0].bet.id} group={g} />)}</div>
    </section>
  );
}

export function LiveCards({ bets }: { bets: OpenBet[] }) {
  return <LiveProvider><Cards bets={bets} /></LiveProvider>;
}

/** Beside the Parlays heading: "next locks in 12m 30s", ticking; nothing once today's locks have passed. */
export function NextLock({ locks }: { locks: HubLock[] }) {
  const now = useNow();
  const ahead = now === null ? locks : locks.filter((l) => Date.parse(l.at) > now - 60_000);
  if (!ahead.length) return null;
  const l = ahead[0];
  return <span title={`${l.title} locks first${ahead.length > 1 ? `, then ${ahead.slice(1).map((x) => x.title).join(", ")}` : ""}`}>
    next locks in <span className="warn" aria-label={now === null ? undefined : `locks in ${countdown(l.at, now)}`}>{now === null ? "" : countdown(l.at, now)}</span></span>;
}

/** Today's parlays still to lock, each with its countdown (a parlay shows on Today once it locks: no draft prices). */
export function LockList({ locks }: { locks: HubLock[] }) {
  const now = useNow();
  const ahead = now === null ? locks : locks.filter((l) => Date.parse(l.at) > now - 60_000);
  if (!ahead.length) return null;
  return (
    <ul className="card rows locklist" aria-label="Parlays locking today">
      {ahead.slice(0, 4).map((l) => (
        <li className="rowx" key={l.slate}><span className="grow">{l.title}</span>
          <span className="numx warn">{now === null ? "" : countdown(l.at, now)}</span></li>
      ))}
      {ahead.length > 4 && <li className="rowx sub">+{ahead.length - 4} more later today</li>}
    </ul>
  );
}
