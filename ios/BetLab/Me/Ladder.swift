import Foundation

// Ladder challenges (Mike, Oct 26): roll the whole stack into one bet at a time, from a start to a target. Ported from
// web/lib/ladder.ts (pure, no I/O); LadderTests runs tests/fixtures/ladder.json, which the web tests run too. A step is
// one of the user's bets carrying the ladder's id (migration 0020), so it settles however that bet settles.

struct Ladder: Decodable, Identifiable, Hashable {
    var ladderId: String
    var startUnits: Double
    var targetUnits: Double
    var status: String = "active"          // active, stopped
    var createdAt: String = ""
    var endedAt: String? = nil
    // migration 0021 (Oct 26): the worker (src/betlab/ladders.py) locks the step once its game's news is in
    var gameId: String? = nil
    var skipped: [String]? = nil
    var locked: LockedStep? = nil
    var lockedAt: String? = nil
    var notice: String? = nil
    var book: String? = nil              // the one book every step is at (0022, Mike Oct 26)
    var id: String { ladderId }
}

/// The step the worker locked: the offer as it was then, with the stake (the whole stack) and the step number.
struct LockedStep: Decodable, Hashable {
    var offerId: String
    var tier: String
    var label: String
    var price: Double
    var book: String? = nil
    var matchup: String? = nil
    var commenceTime: String
    var ev: Double? = nil
    var gameId: String? = nil
    var league: String? = nil
    var stake: Double? = nil          // optional (Nov 6): a lock missing either used to fail the decode and blank every ladder
    var step: Int? = nil
    var fdUrl: String? = nil          // the betslip link at the step's book (Nov 6; older locks: the live offer's)
}

enum LadderPhase: String { case climbed, busted, stopped, inPlay = "in play", nextStep = "next step" }

struct LadderState {
    let phase: LadderPhase
    let stack: Double
    let steps: [MyBet]
    let open: MyBet?
    let won: Int
    let nextStake: Double?
    let toWin: Double?
    let progress: Double
}

enum LadderMath {
    static let dust = 1e-6                   // a stack this small is nothing left
    /// Prices a step can be: near even money, so a step is likelier won than not and still moves the stack.
    static let minPrice = -250.0, maxPrice = 150.0

    /// The ladder's state from its own bets (oldest first): the stack is the start plus every settled step's profit
    /// (bonus, boost, cash-out and a voided leg count as My bets counts them); one open step at a time.
    static func state(_ l: Ladder, _ bets: [MyBet]) -> LadderState {
        let steps = bets.filter { $0.ladderId == l.ladderId }.sorted { $0.placedAt < $1.placedAt }
        let stack = l.startUnits + steps.filter { BetMath.isSettled($0) }.reduce(0) { $0 + (BetMath.profit($1) ?? 0) }
        let open = steps.first { !BetMath.isSettled($0) }
        let won = steps.filter { BetMath.status($0) == "won" }.count
        let phase: LadderPhase = stack >= l.targetUnits - dust ? .climbed : stack <= dust && open == nil ? .busted
            : l.status == "stopped" ? .stopped : open != nil ? .inPlay : .nextStep
        let toWin = open.flatMap { o in o.price.map { BetMath.boosted(o, BetMath.stake(o) * (BetMath.dec($0) - 1)) } }
        // progress on a log scale: each double is the same distance (1u -> 100u is about 6.6 doubles)
        let progress = stack <= 0 ? 0 : min(1, max(0, log(stack / l.startUnits) / log(l.targetUnits / l.startUnits)))
        return LadderState(phase: phase, stack: stack, steps: steps, open: open, won: won,
                           nextStake: phase == .nextStep ? stack : nil, toWin: toWin, progress: progress)
    }

    /// BetLab's suggestion for the next step: its strongest +EV pick (then lean) priced -250 to +150 that starts at
    /// least 15 minutes from now, leaving out the ones you turned down (`skipped` offer ids) and, given a `game`, from
    /// that game only (Mike, Oct 26: "reject options", "the next pick for this game"). Pass offers already cleared of the
    /// ban list. Nil when nothing fits.
    static func suggest(_ offers: [Offer], now: Date = Date(), skipped: [String] = [], game: String? = nil, before: Date? = nil,
                        book: String? = nil) -> Offer? {
        options(offers, now: now, before: before, book: book).first { !skipped.contains($0.offerId) && (game == nil || $0.gameId == game) }
    }

    /// An offer as it stands at one book (web atBook): itself when priced there, else the other book's price and EV
    /// when that book posts the same line (same number); nil when it doesn't. A ladder stays at one book.
    static func atBook(_ o: Offer, _ book: String?) -> Offer? {
        guard let book, (o.book ?? "FanDuel") != book else { return o }
        guard o.otherBook == book, let p = o.otherPrice, o.otherPoint == nil || o.otherPoint == o.point else { return nil }
        var x = o
        x.book = book; x.price = p; x.ev = o.otherEv
        return x
    }

    /// Every offer that could be a step, best first (picks before leans, then EV).
    static func options(_ offers: [Offer], now: Date = Date(), before: Date? = nil, book: String? = nil) -> [Offer] {
        let rank: [Tier: Int] = [.pick: 0, .lean: 1]
        return offers.compactMap { atBook($0, book) }.filter { o in
            guard rank[o.tier] != nil, (o.ev ?? 0) > 0, o.price >= minPrice, o.price <= maxPrice,
                  let at = Models.date(o.commenceTime) else { return false }
            return at.timeIntervalSince(now) >= 15 * 60 && (before == nil || at < before!)
        }.sorted { a, b in rank[a.tier]! != rank[b.tier]! ? rank[a.tier]! < rank[b.tier]! : (a.ev ?? 0) > (b.ev ?? 0) }
    }

    /// How many wins in a row at a price take the stack to the target (the whole stack rolled each time).
    static func stepsToTarget(_ stack: Double, _ target: Double, price: Double) -> Int {
        stack >= target ? 0 : Int((log(target / stack) / log(BetMath.dec(price))).rounded(.up))
    }

    /// When a game's news pull lands, in minutes before its start (config/settings.yaml schedule.pregame; soccer's for
    /// every soccer league): the worker locks a held step then (web newsWindow).
    static func newsWindow(_ league: String?) -> (lo: Double, hi: Double) {
        switch league ?? "" {
        case "nfl", "ncaaf": (30, 85)
        case "nba", "ncaab": (15, 45)
        case "nhl", "ufc": (20, 60)
        default: (15, 55)
        }
    }

    /// What a step is called (web stepName, tests/fixtures/ladder.json step_names): its legs before the slip reader's label,
    /// which is often just its stake ("$10.4 cash", Nov 6); else the label, else the matchup.
    static func stepName(legs: [String]?, label: String?, matchup: String?) -> String {
        if let l = legs, !l.isEmpty { return Stats.betName(legs: l, label: nil, price: nil) }
        let x = Fmt.label(label ?? "")
        return x.isEmpty ? (matchup ?? "").components(separatedBy: ":").first ?? "" : x
    }
    static func stepName(_ b: MyBet) -> String { stepName(legs: b.legs, label: b.label, matchup: b.matchup) }

    /// The stack a ladder shows: never below nothing (a Bet Protect fee makes a lost step cost a hair more; web shownStack).
    static func shownStack(_ u: Double) -> Double { u < 0.005 ? 0 : u }

    /// Midnight Eastern after `now`: a ladder's "today".
    static func endOfDay(_ now: Date = Date()) -> Date {
        var cal = Calendar(identifier: .gregorian); cal.timeZone = Fmt.et
        return cal.date(byAdding: .day, value: 1, to: cal.startOfDay(for: now))!
    }
}
