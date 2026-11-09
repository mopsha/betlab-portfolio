"use client";

// A game page's Watch button (Nov 7): mark the games you'll watch, and their own same-game parlays join Today's Parlays
// next to the slice's SGP+ ticket when it locks, with the lock alert (lib/watch.ts). It replaced the Knicks rule and the
// lone prime-time game's slips.

import { useOptimistic, useTransition } from "react";
import { setWatching } from "@/lib/actions";
import { Icon } from "@/components/ui/Kit";

export function WatchButton({ gameId, on }: { gameId: string; on: boolean }) {
  const [pending, start] = useTransition();
  const [watching, set] = useOptimistic(on);
  const label = watching ? "Watching" : "Watch";
  return (
    <button type="button" className={`watchbtn${watching ? " on" : ""}`} aria-pressed={watching} disabled={pending}
      title={watching ? "Its parlays join Today when its slice locks. Tap to stop." : "Get this game's own parlays on Today when its slice locks"}
      onClick={() => start(async () => { set(!watching); await setWatching(gameId, !watching); })}>
      <Icon name="eye" /><span>{label}</span>
    </button>
  );
}
