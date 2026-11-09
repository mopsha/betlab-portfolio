"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// The overhaul's tabs (Nov 4, docs/OVERHAUL.md): they follow the three things the app is opened for. Live is My bets
// (open bets and the wall), Me is the old More. The paths stay until the screens themselves are rebuilt.
const TABS = [
  { href: "/", label: "Today", icon: "M3 11l9-7 9 7v9H3z" },
  { href: "/bets", label: "Live", icon: "M2 12h5l3-7 4 14 3-7h5" },
  { href: "/build", label: "Build", icon: "M4 4h16v16H4zM12 8v8M8 12h8" },
  { href: "/games", label: "Games", icon: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4" },
  { href: "/more", label: "Me", icon: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c1-4 4-6 8-6s7 2 8 6" },
];

function useCurrent() {
  const path = usePathname();
  return (href: string) => ((href === "/" ? path === "/" : href === "/more" ? path.startsWith("/more") || path.startsWith("/friends") || path.startsWith("/wrapped") || path.startsWith("/chat") : href === "/bets" ? path.startsWith("/bets") || path.startsWith("/wall") : path.startsWith(href)) ? ("page" as const) : undefined);
}

/** The five tabs down the left side from 1000px (the overhaul's desktop layout, Nov 4), under the name, with Search and
 *  what phase the account is in at the foot. */
export function Nav({ phase }: { phase?: string }) {
  const current = useCurrent();
  const path = usePathname();
  return (
    <aside className="sidenav">
      <Link className="brand" href="/">Bet<b>Lab</b></Link>
      <nav aria-label="Main">
        {TABS.map((t) => (
          <Link key={t.href} href={t.href} aria-current={current(t.href)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={t.icon} /></svg>
            {t.label}
          </Link>
        ))}
        <Link href="/search" aria-current={path.startsWith("/search") ? "page" : undefined} className="sidenav-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4" /></svg>
          Search
        </Link>
      </nav>
      {phase && <span className="phase">{phase}</span>}
    </aside>
  );
}

/** The same places as a bottom tab bar on phones. It lives outside the header: the header's blur
 * makes it the containing block for fixed elements, which pinned the bar to the top. */
export function TabBar() {
  const current = useCurrent();
  return (
    <nav className="tabbar" aria-label="Main">
      {TABS.map((t) => (
        <Link key={t.href} href={t.href} aria-current={current(t.href)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
               strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={t.icon} /></svg>
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
