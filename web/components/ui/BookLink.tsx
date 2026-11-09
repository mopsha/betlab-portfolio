"use client";

import { useEffect, useState, type ReactNode } from "react";
import { dkHref } from "@/lib/draftkings";
import { isIOS } from "@/lib/fanduel";
import { novigApp } from "@/lib/novig";
import { FdLink } from "@/components/ui/FdLink";

/** "Open in FanDuel", "Open in DraftKings" or "Open in Novig": the button for the book a bet is priced at (Oct 12). A
 *  DraftKings bet opens its web link, which opens DraftKings' app with the bet in the betslip (iPhone test, Oct 13); a
 *  Novig link opens its order slip with the outcome and a $5 stake filled in (links.book_link, Oct 22), through
 *  Novig's app scheme on iPhone/iPad (lib/novig.ts, Oct 28). */
export function BookLink({ book, links, className = "btn ghost", icon = false }: { book: string | null | undefined;
    links: (string | null | undefined)[]; className?: string;
    /** the book's app icon instead of a long button (Oct 24, from the iPhone: "a button with the logo of the sports book") */
    icon?: boolean }) {
  const name = (book ?? "").toLowerCase() === "novig" ? "Novig" : (book ?? "FanDuel").toLowerCase() === "draftkings" ? "DraftKings" : "FanDuel";
  // eslint-disable-next-line @next/next/no-img-element
  const face = icon ? <img src={`/books/${name.toLowerCase()}.png`} alt="" width={32} height={32} /> : null;
  const cls = icon ? "book-icon" : className;
  if (name === "Novig") return <NovigLink href={links.find((l) => l)} className={cls}>{face}</NovigLink>;
  if (name === "FanDuel") return <FdLink links={links} className={cls}>{face}</FdLink>;
  const href = dkHref(links);
  return href ? <a className={cls} href={href} target="_blank" rel="noopener" aria-label="Open in DraftKings">{face ?? "Open in DraftKings"}</a> : null;
}

function NovigLink({ href, className, children }: { href: string | null | undefined; className: string; children: ReactNode }) {
  const [ios, setIos] = useState(false);
  useEffect(() => setIos(isIOS(navigator.userAgent)), []);
  if (!href) return null;
  const app = ios ? novigApp(href) : null;
  return app
    ? <a className={className} href={app} aria-label="Open in Novig">{children ?? "Open in Novig"}</a>
    : <a className={className} href={href} target="_blank" rel="noopener" aria-label="Open in Novig">{children ?? "Open in Novig"}</a>;
}
