"use client";

// Reactions (Nov 6, supabase 0042), iMessage-style: a smiley beside Tail opens the six in a floating pill, and the card wears
// what friends picked as a stacked bubble on its bottom edge (a tap on it says who). One per person; your pick again takes
// it back. On your own bets (Live) only the bubble. The card clips its glow, so the bubble sits on the card's wrapper
// (RxHost) and the button inside the card; they share the reactions through context. The rules are lib/social.ts,
// shared with the iPhone through tests/fixtures/reactions.json.
import { createContext, useContext, useEffect, useRef, useState, useTransition, type ReactNode } from "react";
import { reactToBet } from "@/lib/actions";
import { emojiOf, nextReaction, REACTIONS, tally, whoText, type Reaction } from "@/lib/social";

type Rx = { rows: Reaction[]; me: string; mine: string | null; pick: (key: string) => void; pending: boolean; msg: string | null; bump: number };
const Ctx = createContext<Rx | null>(null);

/** Holds one bet's reactions for its button and its bubble; `canReact` false (your own bet) draws the bubble only. */
export function RxHost({ betId, list, me, canReact, children }: { betId: string; list: Reaction[]; me: string; canReact: boolean; children: ReactNode }) {
  const [rows, setRows] = useState(list);
  const [msg, setMsg] = useState<string | null>(null);
  const [bump, setBump] = useState(0);
  const [pending, start] = useTransition();
  const mine = rows.find((r) => r.user_id === me)?.reaction ?? null;
  const pick = (key: string) => {
    const next = nextReaction(mine, key), before = rows;
    setRows([...rows.filter((r) => r.user_id !== me),
      ...(next ? [{ bet_id: betId, user_id: me, name: "You", reaction: next, created_at: new Date().toISOString() }] : [])]);
    if (next) setBump((n) => n + 1);
    start(async () => {
      const r = await reactToBet(betId, next);
      if (!r.ok) { setRows(before); setMsg(r.error); } else setMsg(null);
    });
  };
  return (
    <Ctx.Provider value={canReact ? { rows, me, mine, pick, pending, msg, bump } : { rows, me, mine: null, pick: () => {}, pending: false, msg: null, bump: 0 }}>
      <div className="rx-host">
        {children}
        <Bubble />
      </div>
    </Ctx.Provider>
  );
}

/** The smiley in the card's buttons (your own pick in its place once you've reacted), and the six above it. */
export function ReactButton() {
  const rx = useContext(Ctx);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: Event) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", off);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", off); document.removeEventListener("keydown", esc); };
  }, [open]);
  if (!rx) return null;
  return (
    <span className="rx-btn" ref={box}>
      <button type="button" className={`rx-go${rx.mine ? " on" : ""}`} aria-expanded={open} aria-haspopup="true"
        aria-label={rx.mine ? `Your reaction: ${REACTIONS.find((r) => r.key === rx.mine)?.say}. Change it` : "React"}
        onClick={() => setOpen(!open)}>
        {rx.mine ? <span className="rx-mine" aria-hidden>{emojiOf(rx.mine)}</span> : <Smiley />}
      </button>
      {open && (
        <span className="rx-pick" role="group" aria-label="Pick a reaction">
          {REACTIONS.map((r, i) => (
            <button key={r.key} type="button" className={r.key === rx.mine ? "mine" : ""} aria-pressed={r.key === rx.mine} aria-label={r.say}
              title={r.say} style={{ animationDelay: `${i * 22}ms` }} disabled={rx.pending}
              onClick={() => { rx.pick(r.key); setOpen(false); }}>{r.emoji}</button>
          ))}
        </span>
      )}
      {rx.msg && <span className="err rx-err" role="status">{rx.msg}</span>}
    </span>
  );
}

/** What friends picked, stacked on the card's bottom edge; a tap lists who. */
function Bubble() {
  const rx = useContext(Ctx);
  const [who, setWho] = useState(false);
  const chips = rx ? tally(rx.rows, rx.me) : [];
  if (!chips.length) return null;
  const total = chips.reduce((s, c) => s + c.count, 0);
  const label = chips.map((c) => `${c.emoji} ${whoText(c.names)}`).join(", ");
  return (
    <div className="rx-hang">
      <button key={rx!.bump} type="button" className={`rx-bubble${rx!.bump ? " pop" : ""}`} aria-label={`Reactions: ${label}`} aria-expanded={who}
        onClick={() => setWho(!who)} onBlur={() => setWho(false)}>
        <span className="rx-stack" aria-hidden>{chips.slice(0, 3).map((c) => <i key={c.reaction}>{c.emoji}</i>)}</span>
        {total > 1 && <b>{total}</b>}
      </button>
      {who && (
        <div className="rx-who" role="status">
          {chips.map((c) => <div key={c.reaction}><span aria-hidden>{c.emoji}</span>{whoText(c.names)}</div>)}
        </div>
      )}
    </div>
  );
}

function Smiley() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden>
      <path d="M20.5 11.5A8.5 8.5 0 1 1 12.5 3" />
      <path d="M8.5 14.5c1.6 2 5.4 2 7 0" />
      <circle cx="9" cy="10" r=".6" fill="currentColor" /><circle cx="15" cy="10" r=".6" fill="currentColor" />
      <path d="M19 2.5v5M16.5 5h5" />
    </svg>
  );
}
