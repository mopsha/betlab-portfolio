"use client";

// The desktop ticker (Nov 5, W35): your open bets, updating on their own. Pop out floats it over everything in Chrome and Edge
// (Document Picture-in-Picture), and opens a small window elsewhere. A short, wide window crawls; a taller one lists.
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { BetLive } from "@/lib/live";
import { tickerItems, type TickerItem } from "@/lib/ticker";

const FAST = 20_000, SLOW = 120_000;
type PipApi = { requestWindow: (o: { width: number; height: number }) => Promise<Window> };

function Line({ i }: { i: TickerItem }) {
  return (
    <span className={`tick-item tick-${i.state}`}>
      <i aria-hidden className="tick-dot" />
      <b>{i.score || "Your bet"}</b>
      {i.clock && <span className="tick-clock">{i.clock}</span>}
      {i.total > 1 && <span className="tick-count">{i.hit} of {i.total}</span>}
      {i.next && <span className="tick-next">{i.next}</span>}
    </span>
  );
}

function Board({ items, seen }: { items: TickerItem[]; seen: boolean }) {
  if (!items.length) return <p className="tick-empty">{seen ? "No open bets." : "Loading…"}</p>;
  return (
    <>
      <ul className="tick-list" aria-label="Your open bets">{items.map((i) => <li key={i.id}><Line i={i} /></li>)}</ul>
      <div className="tick-crawl" aria-hidden><div style={{ animationDuration: `${Math.max(20, items.length * 10)}s` }}>
        {[...items, ...items].map((i, n) => <Line key={n} i={i} />)}
      </div></div>
    </>
  );
}

export function Ticker({ bare = false }: { bare?: boolean }) {
  const [items, setItems] = useState<TickerItem[]>([]);
  const [seen, setSeen] = useState(false);
  const [pip, setPip] = useState<Window | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let stop = false, run = 0;           // the newest run alone goes on, as the tracker's (LiveBets)
    const tick = async () => {
      if (stop) return;
      const mine = ++run;
      let fast = false;
      try {
        const r = await fetch("/api/live", { cache: "no-store" });
        if (r.ok) {
          const d: { bets: Record<string, BetLive>; live: boolean } = await r.json();
          setItems(tickerItems(d.bets)); setSeen(true); fast = d.live;
        }
      } catch { /* offline: try again next tick */ }
      if (stop || mine !== run) return;
      timer.current = setTimeout(tick, fast ? FAST : SLOW);
    };
    const wake = () => { if (timer.current) clearTimeout(timer.current); tick(); };
    tick();
    window.addEventListener("betlab:pulse", wake);
    return () => { stop = true; if (timer.current) clearTimeout(timer.current); window.removeEventListener("betlab:pulse", wake); };
  }, []);

  async function popOut() {
    const api = (window as unknown as { documentPictureInPicture?: PipApi }).documentPictureInPicture;
    if (!api) { window.open("/ticker?bare=1", "betlab-ticker", "popup,width=720,height=70"); return; }
    const w = await api.requestWindow({ width: 720, height: 70 });
    for (const s of document.querySelectorAll('link[rel="stylesheet"], style')) w.document.head.appendChild(s.cloneNode(true));
    w.document.documentElement.className = document.documentElement.className;
    for (const a of document.documentElement.getAttributeNames()) w.document.documentElement.setAttribute(a, document.documentElement.getAttribute(a) ?? "");
    w.document.body.className = "tick-bare " + document.body.className;
    w.addEventListener("pagehide", () => setPip(null));
    setPip(w);
  }

  if (bare) return <div className="tick-bare-page"><Board items={items} seen={seen} /></div>;
  return (
    <>
      <div className="actions" style={{ marginBottom: 14 }}>
        <button className="btn" type="button" onClick={popOut} disabled={!!pip}>{pip ? "Floating" : "Pop out"}</button>
        <span className="sub">Floats over your other windows in Chrome and Edge. Drag it short and wide to crawl, tall to list.</span>
      </div>
      <section className="card tick-card"><Board items={items} seen={seen} /></section>
      {pip && createPortal(<Board items={items} seen={seen} />, pip.document.body)}
    </>
  );
}
