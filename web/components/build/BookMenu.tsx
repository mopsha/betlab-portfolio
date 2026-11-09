"use client";

import { useEffect, useRef, useState } from "react";
import type { BuildBook } from "@/lib/builder";
import { BUILD_BOOKS } from "@/lib/build-view";
import { BookMark } from "@/components/promos/Token";

/** The book a slip is built for, as a small menu in Build's header (it was a full-width switch above the games): the
 *  board's prices, the slip's links and its saved id all follow it. `books`: the account's books on (Nov 6). */
export function BookMenu({ book, books = BUILD_BOOKS, onPick }: { book: BuildBook; books?: BuildBook[]; onPick: (b: BuildBook) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (ev: PointerEvent) => { if (!box.current?.contains(ev.target as Node)) setOpen(false); };
    const esc = (ev: KeyboardEvent) => { if (ev.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <span className="bd-book" ref={box}>
      <button type="button" className="bd-bookbtn" aria-haspopup="menu" aria-expanded={open} aria-label={`Prices from ${book}: change book`}
              onClick={() => setOpen(!open)}>
        <BookMark book={book} size={26} /><span className="bd-bookname">{book}</span><span className="bd-caret" aria-hidden>▾</span>
      </button>
      {open && (
        <span className="bd-bookmenu" role="menu" aria-label="Book">
          {books.map((b) => (
            <button key={b} type="button" role="menuitemradio" aria-checked={b === book} onClick={() => { onPick(b); setOpen(false); }}>
              <BookMark book={b} size={26} /><span>{b}</span>{b === book && <span className="bd-tick" aria-hidden>✓</span>}
            </button>
          ))}
        </span>
      )}
    </span>
  );
}
