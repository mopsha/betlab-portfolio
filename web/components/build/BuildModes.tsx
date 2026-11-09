import Link from "next/link";

const MODES = [["build", "/build", "Build"], ["check", "/build/check", "Check a slip"], ["promo", "/build/promo", "Use a promo"]] as const;

/** Build's three modes (the overhaul, Nov 4): build a parlay, check a slip you already have, or spend a promo. */
export function BuildModes({ on }: { on: (typeof MODES)[number][0] }) {
  return (
    <nav className="segx" aria-label="Build">
      {MODES.map(([k, href, title]) => <Link key={k} href={href} aria-current={k === on ? "page" : undefined}>{title}</Link>)}
    </nav>
  );
}
