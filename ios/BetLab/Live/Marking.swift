import Foundation

// "Mark as mine", as web/lib/actions.ts markBet / updateBet / undoBet and web/lib/real.ts do it.
// Paper until real money starts (Oct 18, the go-live date, or the account's own `real_from`); from then a
// mark is a placed bet: 1 unit at the price shown, editable after. Units only: no bankroll, no dollars (Oct 12).

/// What a mark saves, before the mode and stake are added.
struct MarkInput: Equatable {
    var kind: String                // pick, lean, parlay
    var pickId: String? = nil
    var sgpId: String? = nil
    var price: Double? = nil
    var label: String? = nil
    var matchup: String? = nil
    var book: String = "FanDuel"
    var fairPrice: Double? = nil
    var pFair: Double? = nil
    var legs: [String]? = nil
    var oddsEventId: String? = nil
    var boost: Double? = nil        // a profit boost in percent (Oct 22: marked from Build's promo mode)
    var bonus: Bool? = nil          // a bonus bet (Build's promo mode)
    var games: [Game]? = nil        // a Build slip's games, each with its legs (the live tracker reads them)

    struct Game: Equatable { var matchup: String; var gameRef: String?; var legs: [String] }

    var key: String { pickId ?? sgpId ?? "" }

    static func offer(_ o: Offer) -> MarkInput {
        MarkInput(kind: o.tier == .pick ? "pick" : "lean", pickId: o.offerId, price: o.price, label: o.label,
                  matchup: o.matchup, book: Marking.bookOf(o.book))
    }

    /// A parlay goes to the book with the best known price (web bestBook, Oct 28): a typed FanDuel or DraftKings quote
    /// or Novig's exact one when its market maker takes at least a unit ($5); a tie goes to FanDuel, then DraftKings.
    /// With none, FanDuel at the ticket's own price. A TD ticket is FanDuel's (web TicketCard).
    static func bestBook(_ t: Ticket, quote: Double?, dkQuote: Double?, on: [String] = BooksOff.mine) -> (book: String, price: Double?) {
        if t.kind == "td" { return ("FanDuel", quote ?? t.price) }
        let nv = t.body.nv
        let nvPrice = nv?.price != nil && (nv?.stakeMax == nil || nv!.stakeMax! >= 5) ? nv?.price : nil
        var best: (String, Double)?
        for (book, price) in [("FanDuel", quote), ("DraftKings", dkQuote), ("Novig", nvPrice)] where on.contains(book) {
            if let price, best == nil || price > best!.1 { best = (book, price) }
        }
        // nothing known at a book that's on (Nov 6): its first book, at FanDuel's listed price only if that's FanDuel
        let first = on.first ?? "FanDuel"
        return best.map { ($0.0, $0.1) } ?? (first, first == "FanDuel" ? t.price : nil)
    }

    static func ticket(_ t: Ticket, quote: Double?, dkQuote: Double?) -> MarkInput {
        let games = t.body.games ?? (t.body.legs.map { [TicketGame(matchup: t.matchup ?? "", commenceTime: t.commenceTime, legs: $0)] } ?? [])
        let at = bestBook(t, quote: quote, dkQuote: dkQuote)
        return MarkInput(kind: "parlay", sgpId: t.sgpId, price: at.price, matchup: t.matchup,
                         book: at.book, fairPrice: t.fairPrice, pFair: t.pFair,
                         legs: games.flatMap { $0.legs.map(\.label) }, oddsEventId: t.body.eventId)
    }
}

enum Marking {
    /// Mike's books (web lib/books.ts): FanDuel and DraftKings (Oct 12), Novig, the sports exchange, for game lines (Oct 22).
    static let books = ["FanDuel", "DraftKings", "Novig"]
    /// Real money starts at midnight Eastern on 2026-10-18 unless the account has its own date.
    static let realStart = Models.date("2026-10-18T04:00:00Z")!

    static func bookOf(_ b: String?) -> String { books.first { $0.lowercased() == (b ?? "").lowercased() } ?? "FanDuel" }

    static func isReal(now: Date = Date(), realFrom: String?) -> Bool {
        now >= (Models.date(realFrom) ?? realStart)
    }

    /// The `bets` row a mark inserts.
    static func row(_ m: MarkInput, real: Bool) -> [String: Any?] {
        var r: [String: Any?] = ["kind": m.kind, "price": m.price, "label": m.label, "matchup": m.matchup,
                                 "book": bookOf(m.book), "mode": real ? "real" : "paper", "stake": real ? 1 : nil]
        if let p = m.pickId { r["pick_id"] = p }
        if let s = m.sgpId {
            r["sgp_id"] = s
            r["fair_price"] = m.fairPrice
            r["p_fair"] = m.pFair
            r["legs"] = m.legs
            r["odds_event_id"] = m.oddsEventId
        }
        if let b = m.boost { r["boost"] = b }
        if let b = m.bonus { r["bonus"] = b }
        if let g = m.games { r["games"] = g.map { ["matchup": $0.matchup, "game_ref": $0.gameRef, "legs": $0.legs] as [String: Any?] } }
        return r
    }

    /// "-110", "+150", "−110" → the price; anything between −100 and +100 isn't one.
    static func parseOdds(_ s: String) -> Double? {
        let t = s.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: Fmt.minus, with: "-")
        guard let n = Double(t.hasPrefix("+") ? String(t.dropFirst()) : t), n.isFinite, n >= 100 || n <= -100 else { return nil }
        return n
    }

    /// The change Edit saves on a placed bet (units, price, book, bonus bet, what a cash-out paid back in units: blank
    /// is not cashed out, the profit boost in percent: the price stays the book's), or the message to show (web updateBet).
    /// `current`: the stake saved now, written again only when it changed (Nov 9: slips save 3 decimals, and rounding an
    /// untouched 0.382u to 0.38 on every edit moved the bankroll). `ladder`: a ladder step, whose stake is the whole
    /// stack (up to 100,000u); the 100u cap is for a changed stake outside a ladder.
    static func edit(stake: String, price: String, book: String, bonus: Bool? = nil,
                     cashout: String? = nil, boost: String? = nil, protect: Bool? = nil, reset: Bool? = nil,
                     current: Double? = nil, ladder: Bool = false) -> Result<[String: Any?], AuthError> {
        let units = Double(stake.trimmingCharacters(in: .whitespaces)).map { ($0 * 1000).rounded() / 1000 }
        let same = units != nil && current != nil && abs(units! - current!) < 0.0005
        let cap: Double = ladder ? 100_000 : 100
        guard let units, same || (units > 0 && units <= cap) else {
            return .failure(AuthError(message: "Enter a stake in units, above 0 and at most \(ladder ? "100,000" : "100")."))
        }
        let typed = price.trimmingCharacters(in: .whitespaces)
        let odds = typed.isEmpty ? nil : parseOdds(typed)
        if !typed.isEmpty && odds == nil { return .failure(AuthError(message: "Enter a price like -110 or +150.")) }
        var change: [String: Any?] = ["price": odds, "book": bookOf(book)]
        if !same { change["stake"] = units }
        if let bonus { change["bonus"] = bonus }
        if let protect { change["protect"] = protect }      // Bet Protect+ (0023, Oct 26)
        if let reset { change["reset"] = reset }            // a bet reset (0031, Nov 1)
        if let cashout {
            let t = cashout.trimmingCharacters(in: .whitespaces)
            if t.isEmpty { change["cashout"] = .some(nil) } else {
                guard let c = Double(t), c.isFinite, c >= 0, c <= 1000 else {
                    return .failure(AuthError(message: "Enter what the cash-out paid back in units, like 1.06."))
                }
                change["cashout"] = (c * 1000).rounded() / 1000
            }
        }
        if let boost {
            let t = boost.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "%", with: "")
            if t.isEmpty { change["boost"] = .some(nil) } else {
                guard let v = Double(t), v.isFinite, v > 0, v <= 500 else {
                    return .failure(AuthError(message: "Enter the profit boost in percent, like 50."))
                }
                change["boost"] = v
            }
        }
        return .success(change)
    }

    static func friendly(_ message: String) -> String {
        if message.range(of: "row-level security|permission denied", options: [.regularExpression, .caseInsensitive]) != nil {
            return "You can view this but not change it."
        }
        if message.range(of: "duplicate key", options: .caseInsensitive) != nil { return "Already marked." }
        return "Couldn't save that. Try again in a moment."
    }

    /// "1u", "2.5u"
    static func units(_ v: Double?) -> String {
        let x = v ?? 1
        return (x == x.rounded() ? String(Int(x)) : String(format: "%g", (x * 100).rounded() / 100)) + "u"
    }
}
