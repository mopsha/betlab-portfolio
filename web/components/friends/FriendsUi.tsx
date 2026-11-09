"use client";

// Friends (Oct 27): the buttons. Your name and @handle, adding a friend, answering requests, sharing on or off, and Tail
// (W16), which copies a friend's open bet into your bets at the price you got. Server pieces: components/friends/Friends.tsx.
import { useState, useTransition } from "react";
import { answerFriend, endFriend, requestFriend, saveProfile, setShareBets, tailBet, type Result } from "@/lib/actions";
import { BOOKS } from "@/lib/books";
import { useMyBooks } from "@/components/app/MyBooks";

function useAction() {
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const run = (f: () => Promise<Result>, ok?: string) => start(async () => {
    const r = await f();
    setMsg(r.ok ? ok ?? null : r.error);
  });
  return { msg, pending, run };
}

export function ProfileForm({ name, handle, fresh }: { name: string; handle: string; fresh: boolean }) {
  const [n, setN] = useState(name), [h, setH] = useState(handle);
  const { msg, pending, run } = useAction();
  return (
    <form className="fx-form" onSubmit={(e) => { e.preventDefault(); run(() => saveProfile(n, h), "Saved."); }}>
      {fresh && <p className="sub">Pick the name friends see and an @handle they can find you by.</p>}
      <div className="fx-fields">
        <label className="field">Name<input value={n} maxLength={40} onChange={(e) => setN(e.target.value)} /></label>
        <label className="field">@handle<input value={h} maxLength={21} autoCapitalize="none" autoCorrect="off"
          onChange={(e) => setH(e.target.value.toLowerCase())} /></label>
      </div>
      <button className="btn" disabled={pending}>{pending ? "Saving…" : fresh ? "Save" : "Update"}</button>
      {msg && <p className={msg === "Saved." ? "sub" : "err"} role="status">{msg}</p>}
    </form>
  );
}

export function AddFriend() {
  const [q, setQ] = useState("");
  const { msg, pending, run } = useAction();
  return (
    <form className="fx-form" onSubmit={(e) => { e.preventDefault(); run(async () => { const r = await requestFriend(q); if (r.ok) setQ(""); return r; }, "Request sent."); }}>
      <div className="fx-fields one">
        <label className="field">Their @handle or email<input value={q} onChange={(e) => setQ(e.target.value)} autoCapitalize="none"
          autoCorrect="off" placeholder="@sam or name@icloud.com" /></label>
      </div>
      <button className="btn" disabled={pending || q.trim().length < 3}>{pending ? "Sending…" : "Send request"}</button>
      <p className="sub">Exact matches only: nobody can browse who uses BetLab. They accept before either of you sees the other&apos;s bets.</p>
      {msg && <p className={msg === "Request sent." ? "sub pos" : "err"} role="status">{msg}</p>}
    </form>
  );
}

/** Under your hero: Add a friend as the clear button, Edit profile beside it; each opens its form in place.
 *  `start`: the form to show at once (Add a friend while you have no friends). */
export function HeroTools({ name, handle, start = null }: { name: string; handle: string; start?: "add" | null }) {
  const [open, setOpen] = useState<"add" | "edit" | null>(start);
  const flip = (k: "add" | "edit") => setOpen(open === k ? null : k);
  return (
    <div className="fx-tools">
      <div className="fx-tools-row">
        <button type="button" className="btn" aria-expanded={open === "add"} onClick={() => flip("add")}>Add a friend</button>
        <button type="button" className="btn quiet" aria-expanded={open === "edit"} onClick={() => flip("edit")}>Edit profile</button>
      </div>
      {open === "add" && <AddFriend />}
      {open === "edit" && <ProfileForm name={name} handle={handle} fresh={false} />}
    </div>
  );
}

export function Answer({ from }: { from: string }) {
  const { msg, pending, run } = useAction();
  return (
    <div className="fx-answer">
      <button type="button" className="btn" disabled={pending} onClick={() => run(() => answerFriend(from, true))}>Accept</button>
      <button type="button" className="btn quiet" disabled={pending} onClick={() => run(() => answerFriend(from, false))}>Decline</button>
      {msg && <span className="err" role="status">{msg}</span>}
    </div>
  );
}

export function EndFriend({ other, label = "Remove" }: { other: string; label?: string }) {
  const [sure, setSure] = useState(false);
  const { msg, pending, run } = useAction();
  if (!sure) return <button type="button" className="btn quiet" onClick={() => setSure(true)}>{label}</button>;
  return (
    <span className="fx-sure">
      <button type="button" className="btn danger" disabled={pending} onClick={() => run(() => endFriend(other))}>{label === "Cancel" ? "Cancel request" : "Yes, remove"}</button>
      <button type="button" className="btn quiet" onClick={() => setSure(false)}>Keep</button>
      {msg && <span className="err" role="status">{msg}</span>}
    </span>
  );
}

/** Settings > Friends: whether friends see your bets. */
export function ShareToggle({ on }: { on: boolean }) {
  const [value, setValue] = useState(on);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const toggle = () => {
    const next = !value;
    setValue(next); setMsg(null);
    start(async () => { const r = await setShareBets(next); if (!r.ok) { setValue(!next); setMsg(r.error); } });
  };
  return (
    <div className="card settings">
      <label className="field toggle">
        <input type="checkbox" checked={value} disabled={pending} onChange={toggle} />
        Friends see my bets
      </label>
      <p className="faint">Your bets, results and units show in your friends&apos; feed and on your profile, never money. Off: they see your
        name only. Friends are in Me › Friends.</p>
      {msg && <p className="err" role="status">{msg}</p>}
    </div>
  );
}

/** Tail (W16): copy a friend's open bet into your bets, at the odds you got (theirs to start) and your book. The
 *  card's main button. */
export function TailButton({ betId, price, book, mine }: { betId: string; price: number | null; book: string; mine: boolean }) {
  const [open, setOpen] = useState(false);
  const [odds, setOdds] = useState(price != null ? `${price > 0 ? "+" : ""}${price}` : "");
  const myBooks = useMyBooks();          // tail at one of the account's books (Nov 6)
  const [bk, setBk] = useState<string>(myBooks.includes(book as (typeof BOOKS)[number]) ? book : myBooks[0]);
  const [done, setDone] = useState(mine);
  const { msg, pending, run } = useAction();
  if (done) return <span className="fx-tailed" role="status">Tailed: in your bets</span>;
  if (!open) return <button type="button" className="btn fx-tail-go" onClick={() => setOpen(true)}>Tail</button>;
  return (
    <form className="fx-tail" onSubmit={(e) => { e.preventDefault(); run(async () => { const r = await tailBet(betId, odds, bk); if (r.ok) setDone(true); return r; }); }}>
      <div className="fx-fields">
        <label className="field">Your odds<input value={odds} onChange={(e) => setOdds(e.target.value)} inputMode="text" /></label>
        <label className="field">Book<select value={bk} onChange={(e) => setBk(e.target.value)}>{myBooks.map((b) => <option key={b}>{b}</option>)}</select></label>
      </div>
      <div className="fx-tools-row">
        <button className="btn" disabled={pending}>{pending ? "Adding…" : "Add to my bets"}</button>
        <button type="button" className="btn quiet" onClick={() => setOpen(false)}>Cancel</button>
      </div>
      {msg && <p className="err" role="status">{msg}</p>}
    </form>
  );
}
