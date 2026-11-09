// Settings' pieces (Nov 6 reorganization; Mike: "it's pretty ah rn"), modeled on the iPhone's own Settings: groups of
// short rows, each with a colored icon, its current value and a chevron to a screen of its own; switches, not checkboxes.
import Link from "next/link";
import type { ReactNode } from "react";

const PATHS: Record<string, string> = {
  books: "M4 7a2 2 0 012-2h12a2 2 0 012 2v2a2 2 0 000 4v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2a2 2 0 000-4zM14 5v12",
  money: "M12 3v18M17 7.5c0-1.9-2.2-3-5-3s-5 1.1-5 3 2.2 2.6 5 3.3 5 1.4 5 3.4-2.2 3.3-5 3.3-5-1.2-5-3.1",
  ban: "M12 3a9 9 0 110 18 9 9 0 010-18zM5.6 5.6l12.8 12.8",
  bell: "M6 16V11a6 6 0 0112 0v5l1.5 2h-15zM10 20.5a2 2 0 004 0",
  friends: "M9 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM2.5 20c.6-3.4 3.2-5.5 6.5-5.5s5.9 2.1 6.5 5.5M16 4.3a3.5 3.5 0 010 6.4M18 14.8c1.9.8 3.1 2.6 3.5 5.2",
  devices: "M7 3h10a1 1 0 011 1v16a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1zM11 18h2",
  look: "M12 3a9 9 0 100 18c1 0 1.5-.7 1.5-1.5 0-1-.8-1.4-.8-2.3 0-.9.7-1.6 1.6-1.6H16a5 5 0 005-5C21 6.4 17 3 12 3zM7.5 12a1 1 0 100-2 1 1 0 000 2zM10 8a1 1 0 100-2 1 1 0 000 2zM14.5 8a1 1 0 100-2 1 1 0 000 2z",
  link: "M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1",
  quiet: "M20 14.5A8 8 0 119.5 4a6.5 6.5 0 0010.5 10.5z",
};

/** A rounded square in a color, with a white line icon: the row's picture. */
export function SetIcon({ name, tint }: { name: string; tint: string }) {
  return (
    <span className="st-ico" style={{ background: tint }} aria-hidden>
      <svg viewBox="0 0 24 24"><path d={PATHS[name] ?? ""} /></svg>
    </span>
  );
}

/** A group of rows under a small title, with an optional note under it. */
export function SetGroup({ title, foot, children }: { title?: string; foot?: ReactNode; children: ReactNode }) {
  return (
    <section className="st-group">
      {title && <h2 className="st-title">{title}</h2>}
      <div className="st-card">{children}</div>
      {foot && <p className="st-foot">{foot}</p>}
    </section>
  );
}

/** A row that opens a screen: icon, title, what it's set to, chevron. */
export function SetRow({ href, icon, tint, title, value }: { href: string; icon: string; tint: string; title: string; value?: ReactNode }) {
  return (
    <Link className="st-row" href={href}>
      <SetIcon name={icon} tint={tint} />
      <span className="st-name">{title}</span>
      {value != null && <span className="st-val">{value}</span>}
      <span className="st-chev" aria-hidden>›</span>
    </Link>
  );
}

export const TINT = { books: "#2f7cf6", money: "#20a35a", ban: "#e5484d", bell: "#f25c3d", friends: "#8e5cf0", devices: "#5b6472",
  look: "#e0447f", link: "#0e9fb3", quiet: "#5b54d6" } as const;
