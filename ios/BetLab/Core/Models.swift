import Foundation

// The rows Home reads, mirroring web/lib/data.ts. Times stay ISO strings (as stored); `Models.date` parses them.

enum Models {
    static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    private static let isoFrac: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let isoPlain = ISO8601DateFormatter()

    static func date(_ s: String?) -> Date? {
        guard let s, !s.isEmpty else { return nil }
        if let d = isoPlain.date(from: s) ?? isoFrac.date(from: s) { return d }
        // ESPN's scoreboards drop the seconds: "2026-10-25T13:30Z"
        if s.range(of: #"T\d{2}:\d{2}Z$"#, options: .regularExpression) != nil { return isoPlain.date(from: s.dropLast() + ":00Z") }
        return nil
    }
}

struct Game: Decodable, Identifiable, Hashable {
    let gameId: String
    let league: String
    let home: String?
    let away: String?
    let matchup: String?
    let commenceTime: String?
    let state: String?
    var id: String { gameId }
}

enum Tier: String, Decodable { case pick, lean, check }

struct Offer: Decodable, Identifiable, Hashable {
    let offerId: String
    var tier: Tier
    let league: String
    let gameId: String?
    let commenceTime: String?
    let matchup: String?
    let market: String?
    let kind: String?
    let player: String?
    let label: String
    var point: Double?
    var price: Double
    var book: String?
    let pModel: Double?
    let pMarket: Double?
    let pFinal: Double?
    var ev: Double?
    let unitsFlat: Double?
    let marketSource: String?
    let why: String?
    let context: String?
    var fdUrl: String?
    var otherBook: String?
    var otherPoint: Double?
    var otherPrice: Double?
    var betLimit: Double? = nil      // Novig: the dollars available at this price (Oct 22)
    var otherEv: Double? = nil       // the other book's EV (a ladder at one book prices a step there, Oct 26)
    var books: [BookRead]? = nil     // every book's own read (books.per_book, Nov 6): shown at the account's books (BooksOff)
    var linkMain: Bool? = nil
    var id: String { offerId }
}

struct Leg: Decodable, Hashable {
    let label: String
    let price: Double?
    let fairPrice: Double?
    let note: String?
    let link: String?
    var linkMain: Bool? = nil       // its link follows the main line, which can move (links.Matcher.main_links)
    var dkLink: String? = nil       // DraftKings' betslip link for this leg (links.attach_dk)
    var dkLinkMain: Bool? = nil
    var dkPrice: Double? = nil
    var dkLabel: String? = nil      // DraftKings' nearest number when it differs
    var nvId: String? = nil         // Novig's outcome id (Oct 28, novig_parlays.attach)
    var nvPrice: Double? = nil      // Novig's price for the leg alone, when $50+ stands behind it
    var player: String? = nil       // the leg's player, when it has one (the ban list reads it)
}

/// The slip at DraftKings (web DkSide): how many legs it posts, its legs' product and the likely SGP quote.
struct DkSide: Decodable, Hashable {
    var legs: Int? = nil
    var of: Int? = nil
    var moved: Int? = nil
    var naivePrice: Double? = nil
    var likelyPrice: Double? = nil
    var standIn: Bool? = nil
}

/// The slip at Novig (web NvSide, Oct 28): legs Novig lists and, when it lists them all, its exact price from Novig's
/// parlay pricer, the largest stake its market maker takes and the whole slip as one link; `refused` when none priced it.
struct NvSide: Decodable, Hashable {
    var legs: Int? = nil
    var of: Int? = nil
    var price: Double? = nil
    var stakeMax: Double? = nil
    var link: String? = nil
    var pricedAt: String? = nil
    var refused: Bool? = nil
}

struct TicketGame: Decodable, Hashable {
    let matchup: String
    let commenceTime: String?
    var legs: [Leg]
    var labelsOnly = false

    enum CodingKeys: String, CodingKey { case matchup, commenceTime, legs }

    init(matchup: String, commenceTime: String?, legs: [Leg]) {
        (self.matchup, self.commenceTime, self.legs) = (matchup, commenceTime, legs)
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        matchup = try c.decode(String.self, forKey: .matchup)
        commenceTime = try c.decodeIfPresent(String.self, forKey: .commenceTime)
        // a lone NBA game's slip lists its game's legs by label only (fun_nba.game_slips, for grading); Ticket fills
        // them in from the flat legs. Oct 20: the strings failed the whole body, so the slip showed empty.
        if let full = try? c.decode([Leg].self, forKey: .legs) {
            legs = full
        } else {
            legs = ((try? c.decode([String].self, forKey: .legs)) ?? []).map { Leg(label: $0, price: nil, fairPrice: nil, note: nil, link: nil) }
            labelsOnly = true
        }
    }
}

struct TicketBody: Decodable, Hashable {
    var label: String?              // an over to root for: "Payton Pritchard 21+ points"
    var theme: String?
    var story: String?
    var why: String?
    var legs: [Leg]?
    var games: [TicketGame]?
    var link: String?
    var linkMain: Bool?
    var cup: String?                // a ticket of one competition's matches ("Conference League", fun_soccer)
    var style: String?              // a game's own slip: value, story, longshot, mini (Nov 7: shown for watched games)
    var longshot: Bool?
    var eventId: String?
    var likelyPrice: Double?        // FanDuel's likely quote (the quote model)
    var dk: DkSide?
    var nv: NvSide?
}

struct Ticket: Decodable, Identifiable, Hashable {
    let sgpId: String
    let kind: String            // sgp, sgp_plus, td, over
    let sport: String
    let gameId: String?
    let slate: String?
    let matchup: String?
    let commenceTime: String?
    let fairPrice: Double?
    let pFair: Double?
    let price: Double?
    var naivePrice: Double? = nil    // the legs' prices multiplied
    let body: TicketBody
    var id: String { sgpId }

    enum CodingKeys: String, CodingKey {
        case sgpId, kind, sport, gameId, slate, matchup, commenceTime, fairPrice, pFair, price, naivePrice, body
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        sgpId = try c.decode(String.self, forKey: .sgpId)
        kind = try c.decode(String.self, forKey: .kind)
        sport = try c.decode(String.self, forKey: .sport)
        gameId = try c.decodeIfPresent(String.self, forKey: .gameId)
        slate = try c.decodeIfPresent(String.self, forKey: .slate)
        matchup = try c.decodeIfPresent(String.self, forKey: .matchup)
        commenceTime = try c.decodeIfPresent(String.self, forKey: .commenceTime)
        fairPrice = try c.decodeIfPresent(Double.self, forKey: .fairPrice)
        pFair = try c.decodeIfPresent(Double.self, forKey: .pFair)
        price = try c.decodeIfPresent(Double.self, forKey: .price)
        // a number, or a numeric string in some rows ("735", seen Oct 15)
        naivePrice = (try? c.decodeIfPresent(Double.self, forKey: .naivePrice))
            ?? (try? c.decodeIfPresent(String.self, forKey: .naivePrice)).flatMap { Double($0) }
        // the body is free-form jsonb from the Python side: an odd field shouldn't drop the ticket
        var b = (try? c.decode(TicketBody.self, forKey: .body)) ?? TicketBody()
        if let flat = b.legs, let games = b.games {   // legs listed by label only: take the full leg by its label
            let byLabel = Dictionary(flat.map { ($0.label, $0) }, uniquingKeysWith: { a, _ in a })
            b.games = games.map { g in
                guard g.labelsOnly else { return g }
                var g = g; g.legs = g.legs.map { byLabel[$0.label] ?? $0 }; return g
            }
        }
        body = b
    }

    init(sgpId: String, kind: String, sport: String, gameId: String?, slate: String?, matchup: String?,
         commenceTime: String?, fairPrice: Double?, pFair: Double?, price: Double?, body: TicketBody) {
        (self.sgpId, self.kind, self.sport, self.gameId, self.slate, self.matchup) = (sgpId, kind, sport, gameId, slate, matchup)
        (self.commenceTime, self.fairPrice, self.pFair, self.price, self.body) = (commenceTime, fairPrice, pFair, price, body)
    }
}

struct Slate: Decodable, Hashable {
    let slate: String
    let sport: String
    let kickoff: String
    let nGames: Int
    let title: String?
    let lockedAt: String?
    var label: String? = nil
    var ticketIds: [String]? = nil     // the slice's tickets ("plus-", "td-"): a slice with none has nothing to lock
}

struct SlatesDoc: Decodable { let slates: [Slate]? }
struct CardMeta: Decodable { let generatedAt: String? }

/// A parlay leg's result (fun_ledger): won/lost/void/push, the stat, and for a void leg its fair chance `p`.
struct LegResult: Decodable, Hashable {
    let leg: String
    let result: String
    var value: Double? = nil
    var p: Double? = nil
    var shown: String? = nil       // the value as text, a score ("3-1") or a stat ("28"), for share cards

    enum CodingKeys: String, CodingKey { case leg, result, value, p }
    init(leg: String, result: String, value: Double? = nil, p: Double? = nil) {
        (self.leg, self.result, self.value, self.p) = (leg, result, value, p)
    }
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        leg = (try? c.decode(String.self, forKey: .leg)) ?? ""
        result = (try? c.decode(String.self, forKey: .result)) ?? "open"
        value = try? c.decodeIfPresent(Double.self, forKey: .value)      // a stat; text in some old rows
        shown = (try? c.decodeIfPresent(String.self, forKey: .value)) ?? value.map(Live.js)
        p = try? c.decodeIfPresent(Double.self, forKey: .p)
    }
}

/// A bet with what it was on (the my_bets view, web/lib/data.ts MyBet): its grading, market and CLV.
struct MyBet: Decodable, Hashable, Identifiable {
    var betId: String = ""
    var kind: String = "pick"           // pick, lean, parlay, custom
    var pickId: String? = nil
    var sgpId: String? = nil
    var mode: String? = "paper"
    var price: Double? = nil
    var stake: Double? = nil
    var book: String? = nil
    var bonus: Bool? = nil             // a bonus bet: the stake is the book's credit, not cash (migration 0012, Oct 19)
    var cashout: Double? = nil         // cashed out early: what the book paid back, in units (migration 0014, Oct 22)
    var boost: Double? = nil           // a profit boost in percent: price is the book's own, a win's profit x (1 + boost/100) (0015)
    var ladderId: String? = nil        // a ladder challenge's step (0020, Oct 26: Ladder.swift)
    var protect: Bool? = nil           // FanDuel Bet Protect+ (0023, Oct 26): a 3% fee; a leg on a player who sits counts as won
    var reset: Bool? = nil             // a bet reset (0031, Nov 1): if it loses, the stake comes back as a bonus bet in the wallet
    var boostCap: Double? = nil        // the most extra winnings the boost adds, in units (0029, Oct 30)
    var promoId: String? = nil         // the wallet token this bet used (0029: Promos.swift)
    var lockId: String? = nil          // a two-book lock's two bets share it (0029)
    var promoEv: Double? = nil         // the token's expected dollars when placed (0029)
    var label: String? = nil
    var matchup: String? = nil
    var placedAt: String = ""
    var pickStatus: String? = nil
    var ticketStatus: String? = nil
    var fairPrice: Double? = nil
    var legs: [String]? = nil
    var profitFlat: Double? = nil
    var profit1u: Double? = nil
    var clv: Double? = nil
    var clvRaw: Double? = nil
    var pickCommenceTime: String? = nil
    var ticketCommenceTime: String? = nil
    var league: String? = nil
    var market: String? = nil
    var pickKind: String? = nil
    var loggedPrice: Double? = nil
    var closePush: Double? = nil
    var legResults: [LegResult]? = nil
    var ticketKind: String? = nil
    var sport: String? = nil           // a fun ticket's sport (my_bets)
    var games: JSON? = nil             // a custom bet's games: [{matchup, game_ref, legs}] (keys arrive camelCased)
    var liveSettled: String? = nil     // "won" / "lost": settled from the live tracker before the worker grades it (not stored)
    var gameStart: String? = nil       // a custom bet's first kickoff, from its games (BetStore.load, Oct 25; not stored)
    var slipP: Double? = nil           // a slip's fair chance when it was read (slip_prices, Nov 4)
    var clvNow: Double? = nil          // live CLV on an open bet (bet_clv, Oct 28; web clv_now): BetStore.load fills it
    var userId: String? = nil          // whose bet: a friend's in the feed (0024, Oct 27: Social.swift); your own otherwise
    var pFair: Double? = nil
    var oddsEventId: String? = nil

    var id: String { betId }
    var key: String? { pickId ?? sgpId }
    var isReal: Bool { mode == "real" }
    var isOpen: Bool { !BetMath.isSettled(self) }
    var isBonus: Bool { bonus == true }

    enum CodingKeys: String, CodingKey {
        case betId, kind, pickId, sgpId, mode, price, stake, book, bonus, cashout, boost, ladderId, protect, reset, boostCap, promoId, lockId, promoEv, label, matchup, placedAt, pickStatus, ticketStatus
        case fairPrice, legs, profitFlat, profit1u = "profit1U", clv, clvRaw, pickCommenceTime, ticketCommenceTime
        case league, market, pickKind, loggedPrice, closePush, legResults, ticketKind, sport, games, userId, pFair, oddsEventId
    }
}

/// A typed book price for a slip (`quotes`; a DraftKings one is saved under "<sgp_id>~dk"), or a parlay Mike built
/// and saved (`custom_parlays`, with its grade and result).
struct Quote: Decodable, Hashable, Identifiable {
    let sgpId: String
    var price: Double? = nil
    var fairPrice: Double? = nil
    var pFair: Double? = nil
    var legs: [String]? = nil
    var nLegs: Int? = nil
    var matchup: String? = nil
    var quotedAt: String? = nil
    var grade: String? = nil
    var status: String? = nil
    var profit1u: Double? = nil
    var games: JSON? = nil             // a saved parlay's games, each with its legs (custom_parlays)
    var id: String { sgpId }

    enum CodingKeys: String, CodingKey {
        case sgpId, price, fairPrice, pFair, legs, nLegs, matchup, quotedAt, grade, status, games, profit1u = "profit1U"
    }
}
