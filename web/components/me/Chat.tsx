"use client";

// Chat with BetLab (Mike's W22, Oct 24; the overhaul's look, Nov 5): ask about your bets, tonight's board or a game,
// answered from the app's own numbers (lib/chat.ts). Your messages are accent bubbles on the right; BetLab's answers
// are plain text on the left under a small mark, with game links as cards (components/chat/Answer.tsx). The field
// floats above the tab bar. The conversation stays on this device for the session (sessionStorage), never in the database.

import { useEffect, useRef, useState } from "react";
import { Answer, type GameRefs } from "@/components/chat/Answer";
import { Art, type ArtOf } from "@/components/ui/Art";
import { Icon, SubHead } from "@/components/ui/Kit";

export type Turn = { role: "user" | "assistant"; content: string };
/** A question to start from: a small label, the question a tap sends, and pictures when it names a game. */
export type Idea = { cap: string; q: string; art?: ArtOf[] };
const KEY = "betlab-chat";
const IDEAS: Idea[] = [
  { cap: "Tonight", q: "What's the best bet tonight?" },
  { cap: "My bets", q: "How are my open bets doing?" },
  { cap: "This week", q: "How am I doing this week?" },
  { cap: "A parlay", q: "Build me a 3-leg parlay from today's board" },
  { cap: "The math", q: "What does my CLV say about my bets?" },
];

const Mark = () => <span className="cx-mark" aria-hidden>B</span>;

function Copy({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  useEffect(() => { if (!done) return; const t = setTimeout(() => setDone(false), 1800); return () => clearTimeout(t); }, [done]);
  return (
    <button type="button" className="cx-copy" onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); } catch { /* no clipboard here */ } }}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={done ? "M5 12l5 5 9-10" : "M9 9h10v11H9zM5 15V4h10"} /></svg>
      <span role="status">{done ? "Copied" : "Copy"}</span>
    </button>
  );
}

/** `game`: a question about a game on today's board, with its logos. `sample`: a made-up conversation for the local
 *  preview (never saved). */
export function Chat({ ready, games = {}, game = null, sample = null }: { ready: boolean; games?: GameRefs; game?: Idea | null; sample?: Turn[] | null }) {
  const [turns, setTurns] = useState<Turn[]>(sample ?? []);
  const [loaded, setLoaded] = useState(!!sample);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (sample) return;
    try { const s = sessionStorage.getItem(KEY); if (s) setTurns(JSON.parse(s)); } catch { /* private window */ }
    setLoaded(true);
  }, [sample]);
  useEffect(() => {
    if (!loaded) return;
    if (!sample) { try { sessionStorage.setItem(KEY, JSON.stringify(turns)); } catch { /* storage off */ } }
    if (turns.length || busy) end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy, loaded, sample]);
  // the field grows with its text, to a few lines (browsers without field-sizing)
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
  }, [draft]);

  async function ask(q: string) {
    const text = q.trim();
    if (!text || busy || !ready) return;
    const next = [...turns, { role: "user" as const, content: text }];
    setTurns(next); setDraft(""); setErr(null); setBusy(true);
    try {
      const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: next }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.answer) setErr(j.error ?? "No answer came back: try again.");
      else setTurns([...next, { role: "assistant", content: j.answer }]);
    } catch {
      setErr("You look offline: try again.");
    } finally {
      setBusy(false);
    }
  }

  const ideas = game ? [...IDEAS.slice(0, 3), game, ...IDEAS.slice(3)] : IDEAS;   // the wide game card between two pairs
  const fresh = loaded && turns.length === 0 && !busy;
  return (
    <div className="cx">
      <SubHead title="Ask BetLab">
        {turns.length > 0 && (
          <button type="button" className="ib" aria-label="New chat" title="New chat" onClick={() => { setTurns([]); setErr(null); box.current?.focus(); }}><Icon name="plus" /></button>
        )}
      </SubHead>
      {!ready && <p className="banner">Chat is waiting for its key: add ANTHROPIC_API_KEY to the web service in Railway.</p>}

      {fresh && (
        <section className="cx-start">
          <span className="cx-mark big" aria-hidden>B</span>
          <h2>What do you want to know?</h2>
          <p className="sub">Answers come from your bets and the app&apos;s prices. It can explain and suggest; placing a bet stays with you.</p>
          <div className="cx-ideas">
            {ideas.map((it) => (
              <button key={it.q} type="button" className={`cx-idea${it.art?.length ? " game" : ""}`} disabled={!ready} onClick={() => ask(it.q)}>
                <span className="cap">{it.cap}</span>
                {it.art?.length ? <span className="artstack" style={{ ["--art" as string]: "30px" }}>{it.art.map((a, i) => <Art key={i} {...a} size={30} className="disc" />)}</span> : null}
                <b>{it.q}</b>
              </button>
            ))}
          </div>
        </section>
      )}

      <div className="cx-log" aria-live="polite">
        {turns.map((t, i) => t.role === "user"
          ? <div key={i} className="cx-you"><span className="cx-bubble">{t.content}</span></div>
          : (
            <article key={i} className="cx-bl">
              <div className="cx-from"><Mark /><span className="cap">BetLab</span></div>
              <div className="cx-text"><Answer text={t.content} games={games} /></div>
              <Copy text={t.content} />
            </article>
          ))}
        {busy && (
          <div className="cx-bl" role="status" aria-label="BetLab is answering">
            <div className="cx-from"><Mark /><span className="cap">BetLab</span><span className="cx-dots" aria-hidden><i /><i /><i /></span></div>
          </div>
        )}
        {err && <p className="err cx-err" role="status">{err}</p>}
        <div ref={end} className="cx-end" />
      </div>

      <form className={`cx-box${draft.trim() ? " has" : ""}`} onSubmit={(e) => { e.preventDefault(); ask(draft); }}>
        <textarea ref={box} rows={1} value={draft} maxLength={4000} aria-label="Your question"
          placeholder={ready ? "Ask about your bets, tonight, a game" : "Waiting for the key"}
          disabled={!ready} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); ask(draft); } }} />
        <button className="cx-send" aria-label="Send" title="Send" disabled={!ready || busy || !draft.trim()}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
        </button>
      </form>
    </div>
  );
}
