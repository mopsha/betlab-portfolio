import type { Offer } from "./data";

// Game-line leans more than 36 hours before the start (the pick window, config picks.horizon_hours) closed about 4%
// against us in weekly review #3 (29 leans, 45% beat the close) while late ones beat it: Mike chose to label them,
// not hide them (Oct 13). Props held up early, so they keep the plain tag. Oct 14 (weak-spot review: 61 real closes
// 36h+ out, -1.8% CLV, 48% beat): Mike chose to hide them from Home by default (?early=1 shows them); they're still
// logged and graded on paper, and every game page still lists them with the label.
const EARLY_HOURS = 36;
export const isEarlyLean = (o: Pick<Offer, "tier" | "market" | "commence_time">, now = Date.now()) => o.tier === "lean" && !String(o.market ?? "").startsWith("player")
  && !!o.commence_time && Date.parse(o.commence_time) - now > EARLY_HOURS * 3600e3;
