import Foundation

// BetLab Wrapped (Mike's W17, Oct 27): a month or the season as a tap-through story, like Spotify Wrapped. Your bottom
// line, the biggest hit, the leg that broke your heart, your player, your book, your betting type, your best day and the
// badges you earned. Ported from web/lib/wrapped.ts: **change both together.** Pure, from the same settled bets as the
// Record tab (BetMath.record, profit, Stats.chrono), so every number matches it; WrappedView draws the story and the
// picture to share. MyBetsTests runs web/tests/wrapped.test.mjs's cases.

enum Wrapped {
    static let months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

    /// A period's name: "October" (this year's), "October 2025", "Your season". A period is "2026-10" or "season".
    static func periodName(_ p: String, now: Date = Date()) -> String {
        if p == "season" { return "Your season" }
        let parts = p.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 2 else { return p }
        var utc = Calendar(identifier: .gregorian); utc.timeZone = TimeZone(identifier: "UTC")!
        return months[parts[1] - 1] + (parts[0] == utc.component(.year, from: now) ? "" : " \(parts[0])")
    }

    /// The months with a settled bet, newest first, then "season" when there's more than one month.
    static func periods(_ bets: [MyBet]) -> [String] {
        let ms = Array(Set(Stats.chrono(bets).map { String(BetMath.day($0).prefix(7)) })).sorted(by: >)
        return ms.count > 1 ? ms + ["season"] : ms
    }

    static func inPeriod(_ b: MyBet, _ p: String) -> Bool { p == "season" || BetMath.day(b).hasPrefix(p) }

    /// A bet as Wrapped shows it: what it was, its price and day, the units, and its legs with their results.
    struct Shown { let title: String, price: String, day: String; let units: Double; let legs: [ShareCard.Leg]; let more: Int; let book: String }
    static func shown(_ b: MyBet) -> Shown {
        let c = ShareCard.of(b)
        return Shown(title: c.title, price: c.price, day: BetMath.day(b), units: BetMath.profit(b) ?? 0, legs: c.legs, more: c.more, book: c.book)
    }

    /// Your betting type: the first that fits, in this order (each needs enough bets to mean something).
    struct Persona: Equatable { let name: String, why: String }
    static func persona(_ bets: [MyBet]) -> Persona {
        let n = bets.count
        let share = { (f: (MyBet) -> Bool) in Double(bets.filter(f).count) / Double(max(n, 1)) }
        let clv = bets.compactMap(BetMath.personalClv)
        let prices = bets.compactMap(\.price).sorted()
        let median = prices.isEmpty ? nil : prices[prices.count / 2]
        let pct = { (x: Double) in "\(Int((x * 100).rounded()))%" }
        let bySport = BetMath.record(bets, by: Stats.sportOf).lines.filter { $0.group != "Multi-sport" && $0.group != "Other" }
        let beat = clv.filter { $0 > 0 }.count
        if clv.count >= 5 && Double(beat) / Double(clv.count) >= 0.6 {
            return Persona(name: "The Sharp", why: "You beat the closing line on \(beat) of \(clv.count) bets. That's the real scoreboard.")
        }
        if n >= 5 && share({ Stats.legsOf($0) >= 5 }) >= 0.5 {
            return Persona(name: "The Parlay Architect", why: "\(pct(share { Stats.legsOf($0) >= 5 })) of your bets had 5 or more legs. Go big or go home.")
        }
        if n >= 5 && share(\.isBonus) >= 0.5 {
            return Persona(name: "The Bonus Hunter", why: "\(pct(share(\.isBonus))) of your bets were the books' own money.")
        }
        if n >= 5, let m = median, m >= 800 {
            return Persona(name: "The Long-Shot Dreamer", why: "Your typical bet paid +\(Live.js(m)). One hit pays for a lot of misses.")
        }
        if n >= 5, let top = bySport.first, Double(top.bets) / Double(n) >= 0.6 {
            return Persona(name: "The \(top.group) Loyalist", why: "\(top.bets) of your \(n) bets were \(top.group).")
        }
        if n >= 5 && share({ Stats.legsOf($0) == 1 }) >= 0.6 {
            return Persona(name: "The Straight Shooter", why: "\(pct(share { Stats.legsOf($0) == 1 })) of your bets were singles.")
        }
        return Persona(name: "The All-Rounder", why: "\(bySport.count) sport\(bySport.count == 1 ? "" : "s"), singles and parlays: a bit of everything.")
    }

    /// The parlay that lost by exactly one leg (every other leg won), the longest price first: the leg that broke your heart.
    struct Heartbreak { let bet: Shown; let leg: ShareCard.Leg; let hit: Int }
    static func heartbreak(_ bets: [MyBet]) -> Heartbreak? {
        var best: (b: MyBet, leg: ShareCard.Leg)? = nil
        for b in bets {
            let c = ShareCard.of(b)
            guard c.status == "ONE LEG AWAY", let leg = c.legs.first(where: { $0.result == "lost" }) else { continue }   // past 10 legs: skipped
            if best == nil || (b.price ?? 0) > (best!.b.price ?? 0) { best = (b, leg) }
        }
        return best.map { Heartbreak(bet: shown($0.b), leg: $0.leg, hit: Stats.legsOf($0.b) - 1) }
    }

    struct Story {
        let period: String, name: String
        let total: RecordLine
        let days: Int, sports: Int, legs: Int
        let best: Shown?
        let heartbreak: Heartbreak?
        let player: PlayerCard?
        let book: RecordLine?, books: [RecordLine]
        let persona: Persona
        let bestDay: (day: String, units: Double, bets: Int)?
        let busiest: (day: String, bets: Int)?
        let bestRun: Int
        let badges: [Badge]
        var roi: Double? { total.roi }
    }

    /// Everything a period's story shows, or nil when it has no settled bet.
    static func story(_ all: [MyBet], _ period: String, now: Date = Date()) -> Story? {
        let bets = Stats.chrono(all).filter { inPeriod($0, period) }
        guard !bets.isEmpty else { return nil }
        let total = BetMath.record(bets).total
        var order: [String] = [], byDay: [String: (units: Double, bets: Int)] = [:]
        for b in bets {
            let d = BetMath.day(b)
            if byDay[d] == nil { order.append(d); byDay[d] = (0, 0) }
            byDay[d]!.units += BetMath.profit(b) ?? 0; byDay[d]!.bets += 1
        }
        let days = order.map { (day: $0, units: byDay[$0]!.units, bets: byDay[$0]!.bets) }
        var bestDay: (day: String, units: Double, bets: Int)? = nil
        for d in days where d.units > 0 && (bestDay == nil || d.units > bestDay!.units) { bestDay = d }
        var busiest = days[0]
        for d in days where d.bets > busiest.bets { busiest = d }
        var winner: MyBet? = nil
        for b in bets { let p = BetMath.profit(b) ?? 0; if p > 0 && (winner == nil || p > BetMath.profit(winner!)!) { winner = b } }
        let books = BetMath.record(bets, by: BetMath.book).lines
        var book = books.first
        if books.count > 1 { for l in books where l.units > book!.units { book = l } }   // the first with the most units
        // badges count from your whole history (one is earned once), shown when the bet that earned it is in this period
        let badges = Achievements.all(all).filter { $0.by.map { inPeriod($0, period) } == true }
        return Story(period: period, name: periodName(period, now: now), total: total,
                     days: byDay.count, sports: Set(bets.map(Stats.sportOf).filter { $0 != "Multi-sport" && $0 != "Other" }).count,
                     legs: bets.reduce(0) { $0 + Stats.legsOf($1) },
                     best: winner.map(shown), heartbreak: heartbreak(bets), player: Players.all(bets, min: 2).first, book: book, books: books,
                     persona: persona(bets), bestDay: bestDay, busiest: busiest.bets > 1 ? (busiest.day, busiest.bets) : nil,
                     bestRun: Stats.streaks(bets).bestWin, badges: badges)
    }
}
