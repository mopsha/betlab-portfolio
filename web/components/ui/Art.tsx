"use client";

// The overhaul's picture block (Nov 4, docs/OVERHAUL.md): anything that names a team, player or league shows its own
// art, from what the app already loads (lib/art.ts, headshots.ts, soccer-clubs.ts). A team-color monogram is only the
// fallback, when there's no picture or it fails to load.
import { useState, type CSSProperties } from "react";
import { leagueLogo, monogram } from "@/lib/league-art";

export type ArtKind = "team" | "player" | "league";
export type ArtOf = { src?: string | null; name: string; abbr?: string | null; color?: string | null; kind?: ArtKind };

/** `alt`: empty by default, since the name is nearly always written beside the picture. */
export function Art({ src, name, abbr, color, kind = "team", size = 48, alt = "", className = "" }: ArtOf & { size?: number; alt?: string; className?: string }) {
  const [ok, setOk] = useState(true);
  const url = src ?? (kind === "league" ? leagueLogo(name) : null);
  const style = { "--art": `${size}px`, "--tc": color ?? undefined } as CSSProperties;
  if (url && ok) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img className={`art ${kind} ${className}`} style={style} src={url} alt={alt} width={size} height={size} loading="lazy" onError={() => setOk(false)} />;
  }
  return <span className={`art mg ${kind}${color ? " tinted" : ""} ${className}`} style={style} role={alt ? "img" : undefined} aria-label={alt || undefined}
               aria-hidden={alt ? undefined : true}>{monogram(name, abbr)}</span>;
}

/** A few small pictures overlapping: a parlay's teams and players. */
export function ArtStack({ items, size = 30, max = 4 }: { items: ArtOf[]; size?: number; max?: number }) {
  if (!items.length) return null;
  const shown = items.slice(0, max);
  return (
    <span className="artstack" style={{ "--art": `${size}px` } as CSSProperties}>
      {shown.map((a, i) => <Art key={`${i}-${a.name}`} {...a} size={size} className="disc" />)}
      {items.length > max && <span className="art mg disc more" style={{ "--art": `${size}px` } as CSSProperties} aria-hidden>+{items.length - max}</span>}
    </span>
  );
}
