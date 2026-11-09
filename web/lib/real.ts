// Real money starts on the go-live date (2026-10-18, Eastern). From then, "Mark as mine" records a
// placed bet: mode "real", 1 unit by default (Mike, 2026-10-02), at the price shown, both editable.
// A stake is units (Oct 12: the app tracks units only, not a bankroll or dollars; the Python ledgers
// multiply profit by it either way); a bet with no stake counts as 1 unit.
export const REAL_START = new Date("2026-10-18T00:00:00-04:00");

/** When an account's marks become real money: its own start (user_settings.real_from, Oct 10: one per
 *  account) or the default, Oct 18. */
export const realStart = (realFrom?: string | null) => (realFrom ? new Date(realFrom) : REAL_START);

/** Whether marks are real money now (server and browser alike). A development server can try it early
 *  with NEXT_PUBLIC_BETLAB_PREVIEW_REAL=1; a production build ignores that. */
export function isReal(now = new Date(), realFrom?: string | null): boolean {
  if (process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_BETLAB_PREVIEW_REAL === "1") return true;
  return now.getTime() >= realStart(realFrom).getTime();
}

/** "1u" / "2.5u" / "−0.75u": every amount in the app is units (Oct 12: no bankroll, no dollars). */
export const fmtU = (v: number) => (v < 0 ? "−" : "") + +Math.abs(v).toFixed(2) + "u";

/** Dollars per unit on an account (Settings, Oct 30; user_settings.unit_dollars): the slip reader and promo
 *  placements turn dollars into units with it. $5 until set. Here, not in data.ts, so browser code can use it. */
export const UNIT_DEFAULT = 5;
export const unitOf = (s: { unit_dollars?: number | null }) => (s.unit_dollars && s.unit_dollars > 0 ? s.unit_dollars : UNIT_DEFAULT);
