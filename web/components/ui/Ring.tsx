// A leg as a ring (the overhaul, Nov 4): it fills toward the leg's target around the player's photo or the team's
// logo, with the current number as a badge. A leg that's in is a full green ring with a green badge; a lost one red.
import type { CSSProperties, ReactNode } from "react";

export type RingState = "won" | "lost" | "void" | "ahead" | "behind" | "live" | "pending";

export function Ring({ value, state = "live", badge, size = 46, children, label }:
  { value: number | null; state?: RingState; badge?: ReactNode; size?: number; children: ReactNode; label?: string }) {
  const r = 21, c = 2 * Math.PI * r;
  const done = state === "won" || state === "lost" || state === "void";
  const k = done ? 1 : Math.max(0, Math.min(1, value ?? 0));
  return (
    <span className={`ring ${state}`} style={{ "--ring": `${size}px` } as CSSProperties} role={label ? "img" : undefined} aria-label={label}>
      <svg viewBox="0 0 46 46" aria-hidden="true">
        <circle className="t" cx="23" cy="23" r={r} />
        {k > 0 && <circle className="f" cx="23" cy="23" r={r} strokeDasharray={`${(c * k).toFixed(1)} ${c.toFixed(1)}`} />}
      </svg>
      <span className="ring-in">{children}</span>
      {badge !== undefined && badge !== null && badge !== "" && <b className="ring-badge">{badge}</b>}
    </span>
  );
}
