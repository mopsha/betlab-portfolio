import Foundation

/// Books on and off (Nov 6, supabase 0043; Mike: "turn on or off different books for EVERYTHING", "like one universal
/// off switch for novig"). An account's user_settings.books_off, never all three. Ported from web lib/books.ts (onBooks,
/// atBooks) and the worker's books.at_books: **change them together**, on tests/fixtures/books_off.json.

/// A book's entry in an offer's `books` (the worker's books.per_book): its own line, price, EV, tier and link.
struct BookRead: Decodable, Hashable {
    let book: String
    var price: Double?
    var point: Double?
    var ev: Double?
    var tier: String?
    var unitsTier: Double?
    var betLimit: Double?
    var link: String?
    var linkMain: Bool?
}

enum BooksOff {
    /// The signed-in account's books off (BetStore sets it from user_settings, like Bans.current).
    nonisolated(unsafe) static var current: [String] = []

    /// The books an account has on, in the tie-break order; all three off reads as none off.
    static func on(_ off: [String]) -> [String] {
        let on = Marking.books.filter { !off.contains($0) }
        return on.isEmpty ? Marking.books : on
    }
    static var mine: [String] { on(current) }

    private static func best(_ list: [BookRead], _ on: [String], needTier: Bool, skip: String? = nil) -> BookRead? {
        var best: BookRead?
        for e in list where on.contains(e.book) && e.book != skip && e.price != nil && (!needTier || (e.tier ?? "") != "") {
            if best == nil || (e.ev ?? 0) > (best!.ev ?? 0) { best = e }
        }
        return best
    }

    /// A card bet as an account with `off` books sees it: at its own book while that's on, else at the best book on that
    /// makes it a bet by itself (its own tier, so a pick can show as a lean), or nil (hidden). The other price is the best
    /// other book on.
    static func atBooks(_ o: Offer, off: [String]) -> Offer? {
        let on = on(off)
        if on.count == Marking.books.count { return o }
        let list = o.books ?? []
        var out = o
        if !on.contains(Marking.bookOf(o.book)) {
            guard let e = best(list, on, needTier: true), let price = e.price, let tier = Tier(rawValue: e.tier ?? "") else { return nil }
            out.tier = tier; out.book = e.book; out.price = price; out.point = e.point; out.ev = e.ev
            out.betLimit = e.betLimit; out.fdUrl = e.link; out.linkMain = e.linkMain
        } else if let ob = o.otherBook, on.contains(Marking.bookOf(ob)) {
            return out
        }
        let x = best(list, on, needTier: false, skip: out.book)
        out.otherBook = x?.book; out.otherPoint = x?.point; out.otherPrice = x?.price; out.otherEv = x?.ev
        return out
    }

    /// Offers at the signed-in account's books.
    static func mine(_ offers: [Offer]) -> [Offer] {
        current.isEmpty ? offers : offers.compactMap { atBooks($0, off: current) }
    }

    /// Tickets at the signed-in account's books: a boosted TD ticket and an over to root for are FanDuel's alone.
    static func tickets(_ ts: [Ticket]) -> [Ticket] {
        mine.contains("FanDuel") ? ts : ts.filter { $0.kind != "td" && $0.kind != "over" }
    }
}
