"use client";

import { useEffect, useState, type ReactNode } from "react";
import { appLink, fdHref, isIOS } from "@/lib/fanduel";

/** Opens the bet (or every leg of a parlay that has a link) in FanDuel's betslip: through FanDuel's
 *  app scheme on iPhone/iPad (lib/fanduel.ts), the web link everywhere else. */
export function FdLink({ links, label, className = "btn ghost", children }: { links: (string | null | undefined)[]; label?: string;
                                                                 className?: string; children?: ReactNode }) {
  const href = fdHref(links);
  const [ios, setIos] = useState(false);
  useEffect(() => setIos(isIOS(navigator.userAgent)), []);
  if (!href) return null;
  const have = links.filter(Boolean).length;
  const text = children ?? label ?? `Open in FanDuel${links.length > 1 ? ` · ${have}/${links.length}` : ""}`;
  return ios
    ? <a className={className} href={appLink(href)} aria-label="Open in FanDuel">{text}</a>
    : <a className={className} href={href} target="_blank" rel="noopener" aria-label="Open in FanDuel">{text}</a>;
}
