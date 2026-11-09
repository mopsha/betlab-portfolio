// The overhaul's small shared pieces (Nov 4, docs/OVERHAUL.md), styled in app/kit.css from the approved mockups.
import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";
import { BackLink } from "@/components/ui/BackLink";

/** A card with team color as a soft light behind its top: up to two colors, left and right. Never a painted band. */
export function Glow({ colors = [], className = "", children, href, as = "div", style }:
  { colors?: (string | null | undefined)[]; className?: string; children: ReactNode; href?: string; as?: "div" | "article" | "section"; style?: CSSProperties }) {
  const [a, b] = colors;
  const lights = (
    <>
      {a && <span className="glow l" style={{ background: a }} aria-hidden />}
      {b && <span className="glow r" style={{ background: b }} aria-hidden />}
    </>
  );
  if (href) return <Link className={`card glowcard ${className}`} href={href} style={style}>{lights}{children}</Link>;
  const Tag = as;
  return <Tag className={`card glowcard ${className}`} style={style}>{lights}{children}</Tag>;
}

const clock = (iso: string) => new Date(iso).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });

/** A game's clock as a pill: red with a dot while live, quiet for a start time or Final. */
export function LivePill({ state, detail, start, note }: { state: "pre" | "in" | "post"; detail?: string; start?: string; note?: string | null }) {
  if (state === "in") return <span className="livepill"><i aria-hidden />{detail || "Live"}{note ? ` · ${note}` : ""}</span>;
  return <span className="livepill quiet">{state === "post" ? "Final" : start ? clock(start) : "Soon"}</span>;
}

/** A section's title as a real heading, with a small count or note beside it and an optional link at the right. */
export function SectionTitle({ children, note, right, id }: { children: ReactNode; note?: ReactNode; right?: ReactNode; id?: string }) {
  return (
    <h2 className="section-title" id={id}>
      <span>{children}</span>
      {note !== undefined && note !== null && note !== "" && <small>{note}</small>}
      {right && <span className="section-right">{right}</span>}
    </h2>
  );
}

export type Cell = { label: string; value: ReactNode; tone?: "pos" | "neg" | "" };
/** Two to four numbers side by side under small labels (a pick's chance, fair price and edge). */
export function StatCells({ cells }: { cells: Cell[] }) {
  return <div className="cells">{cells.map((c) => <div key={c.label}><small>{c.label}</small><b className={c.tone ?? ""}>{c.value}</b></div>)}</div>;
}

const ICONS: Record<string, string> = {
  search: "M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4",
  chat: "M4 5h16v11H9l-5 4z",
  plus: "M12 5v14M5 12h14",
  settings: "M4 7h10M18 7h2M4 17h2M10 17h10M16 4v6M8 14v6",
  saved: "M6 4h12v16l-6-4-6 4z",
  wall: "M3 4h8v7H3zM13 4h8v7h-8zM3 13h8v7H3zM13 13h8v7h-8z",
  refresh: "M20 11a8 8 0 10-2.3 5.7M20 4v7h-7",
  back: "M15 5l-7 7 7 7",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  eye: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6z",
};
export function Icon({ name }: { name: keyof typeof ICONS | string }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[name] ?? ""} /></svg>;
}

/** A round 44px icon button in a screen's header: a link, named for screen readers. */
export function IconLink({ href, icon, label }: { href: string; icon: string; label: string }) {
  return <Link className="ib" href={href} aria-label={label} title={label}><Icon name={icon} /></Link>;
}

/** A main screen's header: its title (or any lead, like Today's date) and round icon buttons; Search is always last. */
export function ScreenHead({ title, lead, children, search = true }: { title?: string; lead?: ReactNode; children?: ReactNode; search?: boolean }) {
  return (
    <div className="shead">
      {title ? <h1>{title}</h1> : lead}
      <span className="shead-tools">{children}{search && <IconLink href="/search" icon="search" label="Search" />}</span>
    </div>
  );
}

/** A sub-page's header: the one back link (to where you came from, or `back` when opened cold), its title, and
 *  anything for the right side. */
export function SubHead({ title, back = "/more", backLabel = "Me", children }: { title: string; back?: string; backLabel?: string; children?: ReactNode }) {
  return (
    <div className="subhead">
      <BackLink fallback={back} label={backLabel} />
      <div className="subhead-row"><h1>{title}</h1>{children && <span className="shead-tools">{children}</span>}</div>
    </div>
  );
}
