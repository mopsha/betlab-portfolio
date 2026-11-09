// "Open in Novig" on an iPhone (Mike, Oct 28: the link opened novig.com in the browser, never the app). novig.com has
// no universal links (Apple's CDN has no association file for it), so iOS always keeps it in a browser. Novig's app
// answers to its own scheme, novigapp://, and reads the same events/<outcome ids>/<partner>/<amount> path into its
// order slip (Novig's web bundle, the same React Native code: prefixes novigapp:// and novig.onelink.me/JHQQ).
export const NOVIG_APP_SCHEME = "novigapp://";

/** novig.com/events/<ids>/oddsapi/5 -> novigapp://events/<ids>/oddsapi/5; null for any other link. */
export function novigApp(href: string): string | null {
  const m = /^https?:\/\/(?:www\.)?novig\.com\/(events\/[^?#]+)/.exec(href);
  return m ? NOVIG_APP_SCHEME + m[1] : null;
}

// Novig's exact parlay price (novig_parlays.py): its free parlay pricer answers 2-20 outcome ids with one price, the
// parlay's chance. Oct 30: it moved to /rfq/v2/quote/unauthenticated ({outcomeIds} in, {price, expiresAt} out; the Oct 28
// route was gone by Oct 29). It no longer says the largest payout, so stake_max stays null. 400: won't combine; 404: no
// price right now; 429: over its limit (Retry-After).
export const NOVIG_PRICER = "https://api.novig.com/rfq/v2/quote/unauthenticated";
export type NovigQuote = { price: number; p: number; payout_max: number | null; stake_max: number | null };

/** The pricer's answer as a quote: price as American odds, null when it priced nothing. */
export function novigQuote(body: unknown): NovigQuote | null {
  const q = body && typeof body === "object" && !Array.isArray(body) ? (body as { price?: unknown }) : null;
  const p = Number(q?.price);
  if (!(p > 0 && p < 1)) return null;
  const price = Math.round(p >= 0.5 ? -100 * p / (1 - p) : 100 * (1 - p) / p);
  return { price, p, payout_max: null, stake_max: null };
}

/** One link that opens the whole slip in Novig's order slip ($5, 1u, filled in). */
export const novigSlipLink = (ids: string[], wager = 5) => `https://novig.com/events/${ids.join(",")}/oddsapi/${wager}`;
