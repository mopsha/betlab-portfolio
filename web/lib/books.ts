// Mike's books (Oct 12: FanDuel and DraftKings, docs/DRAFTKINGS_PLAN.md; Oct 22: Novig, the sports exchange, for game
// lines), as the app names them.
export const BOOKS = ["FanDuel", "DraftKings", "Novig"] as const;
export type Book = (typeof BOOKS)[number];

/** A book name as the app spells it ("draftkings" -> "DraftKings"); anything else is FanDuel. */
export const bookOf = (b: string | null | undefined): Book =>
  BOOKS.find((x) => x.toLowerCase() === String(b ?? "").toLowerCase()) ?? "FanDuel";

// ------------------------------------------------------------------------------------- books on and off (Nov 6, 0043)
// Mike: "I need the ability to turn on or off different books for EVERYTHING", "like one universal off switch for novig".
// An account's user_settings.books_off; never all three. The worker's books.at_books and the iPhone's BooksOff do the
// same, on tests/fixtures/books_off.json.

/** The books an account has on, in the tie-break order; all three off reads as none off. */
export function onBooks(off: readonly string[] | null | undefined): Book[] {
  const on = BOOKS.filter((b) => !(off ?? []).includes(b));
  return on.length ? on : [...BOOKS];
}

/** A book's entry in an offer's `books` (the worker's books.per_book): its own line, price, EV, tier and link. */
export type BookRead = { book: string; price: number | null; point?: number | null; ev?: number | null; tier?: string | null;
  units_tier?: number | null; bet_limit?: number | null; link?: string | null; link_main?: boolean | null };

type Priced = { book: string | null; price: number; point: number | null; ev: number | null; tier: string; units_tier: number | null;
  fd_url: string | null; bet_limit?: number | null; other_book?: string | null; other_point?: number | null; other_price?: number | null;
  other_ev?: number | null; books?: BookRead[] | null; link_main?: boolean | null };

function bestRead(list: BookRead[], on: string[], needTier: boolean, skip?: string | null): BookRead | null {
  let best: BookRead | null = null;
  for (const e of list) {
    if (!on.includes(e.book) || e.book === skip || e.price == null || (needTier && !e.tier)) continue;
    if (!best || (e.ev ?? 0) > (best.ev ?? 0)) best = e;
  }
  return best;
}

/** A card bet as an account with `off` books sees it: at its own book while that's on, else at the best book on that
 *  makes it a bet by itself (its own tier, so a pick can show as a lean), or null (hidden). The other price is the best
 *  other book on. */
export function atBooks<T extends Priced>(o: T, off: readonly string[] | null | undefined): T | null {
  const on = onBooks(off);
  if (on.length === BOOKS.length) return o;
  const list = o.books ?? [];
  const out = { ...o };
  if (!on.includes(bookOf(o.book))) {
    const e = bestRead(list, on, true);
    if (!e) return null;
    Object.assign(out, { tier: e.tier, book: e.book, price: e.price, point: e.point ?? null, ev: e.ev ?? null,
      units_tier: e.units_tier ?? null, bet_limit: e.bet_limit ?? null, fd_url: e.link ?? null, link_main: e.link_main ?? null });
  } else if (o.other_book && on.includes(bookOf(o.other_book))) {
    return out;
  }
  const x = bestRead(list, on, false, out.book);
  return Object.assign(out, { other_book: x?.book ?? null, other_point: x?.point ?? null, other_price: x?.price ?? null,
    other_ev: x?.ev ?? null });
}
