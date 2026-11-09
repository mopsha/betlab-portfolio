"use client";

import { useState, useTransition } from "react";
import { addTodo, setTodoDone } from "@/lib/actions";
import type { Todo } from "@/lib/data";

const ET = "America/New_York";
const today = () => new Date().toLocaleDateString("en-CA", { timeZone: ET });

function Due({ due }: { due: string | null }) {
  if (!due) return null;
  const days = Math.round((Date.parse(due + "T12:00:00") - Date.parse(today() + "T12:00:00")) / 864e5);
  const text = days < 0 ? "overdue" : days === 0 ? "today" : days === 1 ? "tomorrow"
    : new Date(due + "T12:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  return <span className={`tag ${days < 0 ? "lost" : days <= 1 ? "warn" : ""}`}>{text}</span>;
}

function Item({ t }: { t: Todo }) {
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);
  const done = t.status === "done";
  return (
    <div className={`todo${done ? " done" : ""}`}>
      <input type="checkbox" id={`t-${t.id}`} checked={done} disabled={pending}
             onChange={(e) => { const v = e.target.checked; start(async () => { const r = await setTodoDone(t.id, v); setErr(r.ok ? null : r.error); }); }} />
      <label htmlFor={`t-${t.id}`}>{t.title}</label>
      {!done && <Due due={t.due} />}
      {t.detail && (
        <details className="more td">
          <summary>More</summary>
          <div className="more-body"><p>{t.detail}</p></div>
        </details>
      )}
      {err && <span className="err" role="alert">{err}</span>}
    </div>
  );
}

function Column({ title, items }: { title: string; items: Todo[] }) {
  const open = items.filter((t) => t.status !== "done")
    .sort((a, b) => String(a.due ?? "9999").localeCompare(String(b.due ?? "9999")) || a.ord - b.ord);
  const done = items.filter((t) => t.status === "done").sort((a, b) => String(b.done_at).localeCompare(String(a.done_at)));
  return (
    <section>
      <h2 className="section-label">{title} · {open.length} open</h2>
      <div className="card todos">
        {open.length ? open.map((t) => <Item key={t.id} t={t} />) : <p className="faint" style={{ padding: "12px 14px" }}>Nothing open.</p>}
      </div>
      {done.length > 0 && (
        <details className="more" style={{ marginTop: 8 }}>
          <summary>Done ({done.length})</summary>
          <div className="card todos" style={{ marginTop: 8 }}>{done.slice(0, 40).map((t) => <Item key={t.id} t={t} />)}</div>
        </details>
      )}
    </section>
  );
}

/** The shared to-do list: tick items, add your own or a request for Claude (read at the start of every session). */
export function PlanList({ todos }: { todos: Todo[] }) {
  const [owner, setOwner] = useState<"you" | "claude">("you");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const add = (e: React.FormEvent) => {
    e.preventDefault();
    start(async () => {
      const r = await addTodo({ owner, title, due: due || null });
      if (r.ok) { setTitle(""); setDue(""); setErr(null); } else setErr(r.error);
    });
  };
  return (
    <>
      <form className="card addtodo" onSubmit={add}>
        <input aria-label="What needs doing" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a to-do or ask Claude for something" maxLength={300} />
        <div className="addrow">
          <select aria-label="For" value={owner} onChange={(e) => setOwner(e.target.value as "you" | "claude")}>
            <option value="you">For me</option>
            <option value="claude">For Claude</option>
          </select>
          <input aria-label="Due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          <button className="btn" disabled={pending || !title.trim()}>{pending ? "Adding…" : "Add"}</button>
        </div>
        {err && <span className="err" role="alert">{err}</span>}
      </form>
      <div className="plan-cols">
        <Column title="For you" items={todos.filter((t) => t.owner === "you")} />
        <Column title="For Claude" items={todos.filter((t) => t.owner === "claude")} />
      </div>
    </>
  );
}
