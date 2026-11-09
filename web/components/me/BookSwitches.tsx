"use client";

// Settings > Your books (Nov 6, supabase 0043): one switch per book for everything, picks, parlays, Build, promos,
// ladders, challenges and alerts (Mike: "like one universal off switch for novig"). The last one on can't go off.
import { useState, useTransition } from "react";
import { setBooksOff } from "@/lib/actions";
import { BOOKS } from "@/lib/books";
import { BookMark } from "@/components/promos/Token";
import { SetGroup } from "@/components/me/SettingsKit";

const WHAT: Record<string, string> = {
  FanDuel: "Picks, parlays and links",
  DraftKings: "Picks, parlays and links",
  Novig: "Game lines, parlay prices, challenges",
};

export function BookSwitches({ off }: { off: string[] }) {
  const [value, setValue] = useState(off);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const flip = (b: string) => {
    const next = value.includes(b) ? value.filter((x) => x !== b) : [...value, b];
    if (next.length >= BOOKS.length) { setMsg("Keep at least one book on."); return; }
    const before = value;
    setValue(next); setMsg(null);
    start(async () => { const r = await setBooksOff(next); if (!r.ok) { setValue(before); setMsg(r.error); } });
  };
  return (
    <SetGroup foot={<>A book that&apos;s off is gone everywhere: a pick shows at your next best book (or not at all, if no book you have
      on makes it a bet), parlays, Build and promos price at your books only, and alerts follow.{msg && <><br /><b className="neg">{msg}</b></>}</>}>
      {BOOKS.map((b) => (
        <label key={b} className="field toggle">
          <BookMark book={b} size={32} />
          <span className="st-name">{b}<small>{WHAT[b]}</small></span>
          <input type="checkbox" checked={!value.includes(b)} disabled={pending} onChange={() => flip(b)} aria-label={`${b} on`} />
        </label>
      ))}
    </SetGroup>
  );
}
