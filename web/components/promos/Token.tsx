"use client";

// A promo as a thing you hold (the overhaul, Nov 5): the book's mark, what kind it is, its value as the big number, a
// tear line, then when it ends and its limits as chips. The wallet puts its actions under it; the finder shows it small.
import { useEffect, useState, type ReactNode } from "react";
import { Art } from "@/components/ui/Art";
import { Glow } from "@/components/ui/Kit";
import { leagueLogo } from "@/lib/league-art";
import type { PromoRow } from "@/lib/promos";
import { endsOf, kindName, tokenChips, tokenValueText } from "@/lib/wallet-view";

const BOOK_FILES: Record<string, string> = { fanduel: "fanduel", draftkings: "draftkings", novig: "novig" };

/** A book's own mark (its app icon, as the "Open in" buttons show it); "Any book" keeps a plain disc. */
export function BookMark({ book, size = 28 }: { book: string | null | undefined; size?: number }) {
  const file = BOOK_FILES[String(book ?? "").toLowerCase()];
  // eslint-disable-next-line @next/next/no-img-element
  if (file) return <img className="bookmark" src={`/books/${file}.png`} alt="" width={size} height={size} style={{ width: size, height: size }} />;
  return <span className="bookmark none" style={{ width: size, height: size }} aria-hidden>{book ? book.slice(0, 2).toUpperCase() : "any"}</span>;
}

/** The time now, ticking each half minute so countdowns move; starts on the minute so the server's text matches. */
export function useNow(): Date {
  const [now, setNow] = useState(() => new Date(Math.floor(Date.now() / 60_000) * 60_000));
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 30_000); return () => clearInterval(t); }, []);
  return now;
}

/** When it ends: the warning color on its last day, with the time left under a day. */
export function Ends({ p, now }: { p: Pick<PromoRow, "expires_at">; now: Date }) {
  const e = endsOf(p, now);
  if (!e) return <span className="tk-ends">No end date</span>;
  return <span className={`tk-ends${e.today ? " warn" : ""}`} suppressHydrationWarning>{e.text.replace(/^e/, "E")}{e.left ? ` · ${e.left}` : ""}</span>;
}

export function TokenCard({ p, now, compact = false, children, tag }: { p: PromoRow; now: Date; compact?: boolean; children?: ReactNode; tag?: ReactNode }) {
  const chips = tokenChips(p);
  const today = !!endsOf(p, now)?.today;
  return (
    <Glow as="article" className={`tk${compact ? " compact" : ""} is-${p.kind}`} colors={[today && !compact ? "var(--warn)" : null]}>
      <div className="tk-top">
        <BookMark book={p.book} size={compact ? 32 : 44} />
        <div className="tk-what">
          <span className="cap">{kindName(p.kind)}</span>
          <span className="tk-book">{p.book ?? "Any book"}</span>
        </div>
        {tag}
        <span className="tk-value">{tokenValueText(p)}</span>
      </div>
      <div className="tk-tear" aria-hidden />
      <div className="tk-terms">
        <Ends p={p} now={now} />
        {(chips.length > 0 || p.note) && (
          <span className="tk-chips">
            {chips.map((c) => (
              <span key={c.key} className="chipx">
                {c.league && leagueLogo(c.league) && <Art kind="league" name={c.league} size={16} />}
                {c.team?.src && <Art kind="team" name={c.team.name} abbr={c.team.abbr} src={c.team.src} size={16} />}
                {c.text}
              </span>
            ))}
            {p.note && <span className="chipx note">{p.note}</span>}
          </span>
        )}
      </div>
      {children}
    </Glow>
  );
}
