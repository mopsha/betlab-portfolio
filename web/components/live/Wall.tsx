"use client";

// The wall (Mike's W7, Oct 24): every game you have money on, one tile each, live, with your legs on it, for a laptop
// or a TV across the room. Same /api/live poll as My bets (every 20 s while a game is on). Each tile is a scoreboard in
// the two teams' colors (away to home), big logos and scores, the clock in a live pill, then your legs grouped under
// each bet (Mike, Oct 24: the iPhone's version, which this follows). Tiles go in your own order: drag one by its grip
// onto another's spot, by mouse or touch (pointer events: HTML drag and drop doesn't work by touch on the iPhone), or
// focus the grip and use the arrow keys; saved to your account on drop (Mike, Oct 25; lib/order.ts).

import { useEffect, useLayoutEffect, useRef, useState, useTransition, type KeyboardEvent, type PointerEvent } from "react";
import { Board, LiveProvider, Leg, useLive } from "@/components/live/LiveBets";
import { resetWallOrder, setWallOrder } from "@/lib/actions";
import { wallTiles, type Tile } from "@/lib/gameday";
import { moved, ordered } from "@/lib/order";

/** How the tile's legs stand: a lost or losing leg tints it red, every leg won green, else the live color. */
function tone(t: Tile): string {
  if (t.legs.some((l) => l.status === "lost" || l.status === "losing")) return "behind";
  if (t.legs.length && t.legs.every((l) => l.status === "won")) return "won";
  return t.game.state;
}

const GLIDE = "transform .3s cubic-bezier(.2, .8, .2, 1)";

function Tiles({ names, order: saved }: { names: Record<string, string>; order: string[] }) {
  const data = useLive();
  const [order, setOrder] = useState(saved);
  const [dragKey, setDragKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, start] = useTransition();
  const els = useRef(new Map<string, HTMLElement>());
  const grid = useRef<HTMLDivElement>(null);
  // the lifted tile: where it was grabbed (from its corner) and where the pointer is now
  // `slots`: every tile's box when it was picked up, in that order; `at`: the slot it's aimed at now
  type Slot = { key: string; x: number; y: number; w: number; h: number };
  const drag = useRef<{ key: string; before: string[]; grabX: number; grabY: number; x: number; y: number; slots: Slot[]; at: number } | null>(null);
  const first = useRef<Map<string, { x: number; y: number }> | null>(null);   // every tile's slot before a reorder
  const keysRef = useRef<string[]>([]);                         // the order as shown (the scroll loop reads it)
  const timer = useRef(0);

  // The lifted tile sits under the pointer wherever its slot is (offsets ignore transforms; the grid is their parent).
  const place = () => {
    const d = drag.current, el = d && els.current.get(d.key), g = grid.current?.getBoundingClientRect();
    if (!d || !el || !g) return;
    el.style.transform = `translate(${d.x - g.left - d.grabX - el.offsetLeft}px, ${d.y - g.top - d.grabY - el.offsetTop}px) scale(1.04)`;
  };
  const remember = () => {
    first.current = new Map([...els.current].map(([k, el]) => [k, { x: el.offsetLeft, y: el.offsetTop }]));
  };
  const keyList = data ? ordered(wallTiles(data.bets, names), order, (t) => t.game.key).map((t) => t.game.key).join() : "";
  // After a reorder the others glide from their old slots to their new ones (FLIP), like apps on the iPhone's home screen.
  useLayoutEffect(() => {
    const was = first.current;
    first.current = null;
    if (!was) return;
    for (const [k, el] of els.current) {
      if (k === drag.current?.key) { place(); continue; }
      const p = was.get(k);
      const dx = p ? p.x - el.offsetLeft : 0, dy = p ? p.y - el.offsetTop : 0;
      if (!dx && !dy) continue;
      el.style.transition = "none";
      el.style.transform = `translate(${dx}px, ${dy}px)`;
      void el.offsetWidth;                                     // commit the start before gliding
      el.style.transition = GLIDE;
      el.style.transform = "";
    }
  }, [keyList]);

  useEffect(() => () => clearInterval(timer.current), []);   // no scrolling after the wall is gone

  if (!data) return <p className="faint">Loading…</p>;
  const tiles = ordered(wallTiles(data.bets, names), order, (t) => t.game.key);
  const keys = tiles.map((t) => t.game.key);

  const save = (shown: string[], before: string[]) => {
    if (shown.join() === before.join()) return;
    start(async () => {
      const r = await setWallOrder(shown);
      setError(r.ok ? null : r.error);
      if (!r.ok) { remember(); setOrder(before); }               // back as it was
    });
  };
  keysRef.current = keys;
  // Where the lifted tile goes, decided on the boxes as they were when it was picked up (Oct 25): tiles are as tall as
  // their legs, so every move re-sizes the rows, and aiming at the layout as it reflows kept chasing a moving target
  // (a swap moved the slots, which called for another swap). On the frozen boxes one spot always means one order, so
  // it can't flicker or fight; the others still glide to where that order puts them. The tile's head picks the box
  // it's over (in a gap, the nearest box in its column), and the box it's aimed at holds on 16px past its edge.
  const retarget = () => {
    const d = drag.current, me = d && els.current.get(d.key), g = grid.current?.getBoundingClientRect();
    if (!d || !me || !g) return;
    // its head, not its middle: a tall tile is held near its top, and its middle would sit far below the finger
    const cx = d.x - d.grabX + me.offsetWidth / 2 - g.left, cy = d.y - d.grabY + Math.min(me.offsetHeight / 2, 120) - g.top;
    const inside = (s: Slot, pad: number) => cx >= s.x - pad && cx <= s.x + s.w + pad && cy >= s.y - pad && cy <= s.y + s.h + pad;
    if (inside(d.slots[d.at], 16)) return;
    let at = d.slots.findIndex((s) => inside(s, 0));
    if (at < 0) {
      // a gap (under a short tile beside a tall one): the nearest box in that column, else the nearest box at all
      const edge = (s: Slot) => Math.max(s.y - cy, cy - (s.y + s.h), 0);
      const column = d.slots.map((s, i) => [s, i] as const).filter(([s]) => cx >= s.x && cx <= s.x + s.w);
      const dist = (s: Slot) => Math.hypot(s.x + s.w / 2 - cx, s.y + s.h / 2 - cy);
      at = column.length ? column.reduce((b, c) => (edge(c[0]) < edge(b[0]) ? c : b))[1]
        : d.slots.reduce((best, s, i) => (dist(s) < dist(d.slots[best]) ? i : best), d.at);
    }
    if (at === d.at) return;
    d.at = at;
    const next = moved(d.before, d.before.indexOf(d.key), at);
    if (next.join() !== keysRef.current.join()) { remember(); setOrder(next); }
  };
  // While held near the top or bottom of the screen the page keeps scrolling, faster nearer the edge, and the tile
  // keeps its place under the finger.
  const tick = () => {
    const d = drag.current;
    if (!d) return;
    const edge = 90, h = window.innerHeight;
    const v = d.y < edge ? -(edge - d.y) / 4 : d.y > h - edge ? (d.y - (h - edge)) / 4 : 0;
    if (v) { window.scrollBy(0, v); place(); retarget(); }
  };
  const down = (e: PointerEvent<HTMLButtonElement>, key: string) => {
    const el = els.current.get(key);
    if (e.button !== 0 || !el) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    const r = el.getBoundingClientRect();
    const slots = keys.map((k) => { const t = els.current.get(k)!; return { key: k, x: t.offsetLeft, y: t.offsetTop, w: t.offsetWidth, h: t.offsetHeight }; });
    drag.current = { key, before: keys, grabX: e.clientX - r.left, grabY: e.clientY - r.top, x: e.clientX, y: e.clientY,
                     slots, at: keys.indexOf(key) };
    el.style.transition = "transform .15s ease";                 // the lift
    place();
    setDragKey(key);
    clearInterval(timer.current);
    timer.current = window.setInterval(tick, 16);               // a timer, not frames: a hidden pane skips frames
  };
  const move = (e: PointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    if (!d) return;
    d.x = e.clientX; d.y = e.clientY;
    const el = els.current.get(d.key);
    if (el) el.style.transition = "none";                        // follows the finger exactly
    place();
    retarget();
  };
  const up = () => {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    clearInterval(timer.current);
    const el = els.current.get(d.key);
    if (el) { el.style.transition = GLIDE; el.style.transform = ""; }   // settles into its slot
    setDragKey(null);
    save(keysRef.current, d.before);
  };
  const key = (e: KeyboardEvent<HTMLButtonElement>, k: string) => {
    const step = e.key === "ArrowUp" || e.key === "ArrowLeft" ? -1 : e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : 0;
    if (!step) return;
    e.preventDefault();
    const from = keys.indexOf(k), to = from + step;
    if (to < 0 || to >= keys.length) return;
    const next = moved(keys, from, to);
    remember();
    setOrder(next);
    save(next, keys);
  };

  if (!tiles.length) return <div className="card empty"><b>No games on</b><span>Your open bets have no game today.</span></div>;
  const live = tiles.filter((t) => t.game.state === "in").length;
  return (
    <>
      <p className="wall-sub">
        {live > 0 && <span className="lcountpill"><i className="ldot" />{live} live</span>}
        <span className="faint">{tiles.length} game{tiles.length === 1 ? "" : "s"} with your money on them</span>
        {tiles.length > 1 && <span className="faint">· drag ⠿ to arrange</span>}
        {order.length > 0 && tiles.length > 1 && (
          <button type="button" className="btn quiet small" onClick={() => {
            const before = order; remember(); setOrder([]);
            start(async () => { const r = await resetWallOrder(); if (!r.ok) { setError(r.error); remember(); setOrder(before); } });
          }}>Sort by size</button>
        )}
      </p>
      {error && <p className="warn-text">{error}</p>}
      <div className={`wall-grid${dragKey ? " arranging" : ""}`} ref={grid}>
        {tiles.map((t) => {
          const byBet = new Map<string, typeof t.legs>();
          for (const l of t.legs) byBet.set(l.bet, [...(byBet.get(l.bet) ?? []), l]);
          return (
            <section key={t.game.key} className={`wall-tile ${tone(t)}${dragKey === t.game.key ? " dragging" : ""}`}
                     ref={(el) => { if (el) els.current.set(t.game.key, el); else els.current.delete(t.game.key); }}>
              <Board g={t.game} />
              <div className="wall-legs">
                {tiles.length > 1 && (
                  <button type="button" className="wall-grip" aria-label="Move this game: drag, or arrow keys"
                          onPointerDown={(e) => down(e, t.game.key)} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
                          onKeyDown={(e) => key(e, t.game.key)}>⠿</button>
                )}
                <div className="wall-scroll">
                  {[...byBet.entries()].map(([bet, legs]) => (
                    <div key={bet} className="wall-bet-group">
                      <span className="wall-bet">{bet}</span>
                      <ul className="llegs">{legs.map((l, i) => <Leg key={`${i}-${l.label}`} l={l} />)}</ul>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          );
        })}
      </div>
    </>
  );
}

export function Wall({ names, order }: { names: Record<string, string>; order: string[] }) {
  return <LiveProvider><Tiles names={names} order={order} /></LiveProvider>;
}
