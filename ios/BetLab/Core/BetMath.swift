import Foundation

// My bets: results at your own price, and the record by market. Ported from web/lib/bets.ts (pure, no I/O);
// MyBetsTests runs web/tests/bets.test.mjs's cases. Change both together.

struct RecordLine: Identifiable, Hashable {
    let group: String
    var bets = 0, won = 0, lost = 0, push = 0
    var staked = 0.0, units = 0.0
    var clvN = 0, clvSum = 0.0, beat = 0
    var id: String { group }
    var roi: Double? { staked > 0 ? units / staked : nil }
    var avgClv: Double? { clvN > 0 ? clvSum / Double(clvN) : nil }
}

enum BetMath {
    static let settled = ["won", "lost", "push", "void", "cashout"]

    static func dec(_ american: Double) -> Double { american > 0 ? 1 + american / 100 : 1 + 100 / -american }

    /// A cashed-out bet (Oct 22) is settled at what the book paid back, whatever its legs or game do later.
    static func status(_ b: MyBet) -> String { b.cashout != nil ? "cashout" : (b.pickStatus ?? b.ticketStatus ?? "open").lowercased() }
    /// A status as the app says it.
    static func statusName(_ s: String) -> String { s == "cashout" ? "cashed out" : s }
    static func isSettled(_ b: MyBet) -> Bool { settled.contains(status(b)) }
    /// A bet's stake in units; 1 when none is set (units only since Oct 12).
    static func stake(_ b: MyBet) -> Double { b.stake ?? 1 }
    static func start(_ b: MyBet) -> String? { b.pickCommenceTime ?? b.ticketCommenceTime ?? b.gameStart }

    /// A game ref's kickoff where the ref carries it (NBA and soccer refs end in it), else nil (web lib/bets.ts refTime).
    static func refTime(_ ref: String?) -> String? {
        guard let ref, let r = ref.range(of: #"\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?"#, options: .regularExpression) else { return nil }
        return String(ref[r])
    }

    /// The games table's id for a ref without a time: NFL "2026_07_PIT_NO" -> "nfl:2026_07_PIT_NO"; college and NHL refs
    /// are the id. UFC refs name ESPN's fight: nil (web refGameId).
    static func refGameId(_ ref: String?) -> String? {
        guard let r = ref else { return nil }
        if r.range(of: #"^\d{4}_\d{2}_"#, options: .regularExpression) != nil { return "nfl:" + r }
        return r.range(of: #"^(ncaaf|ncaab|nhl|nfl):[^:]+$"#, options: .regularExpression) != nil ? r : nil
    }

    /// A bet entered by hand or from a slip has no start of its own (Mike, Oct 25: "sort my bets in time order at all
    /// times"): its first game's kickoff, from its refs and the games table's starts (web gameStart).
    static func gameStart(_ b: MyBet, starts: [String: String]) -> String? {
        let refs = (b.games?.array ?? []).map { $0["game_ref"].string ?? $0["gameRef"].string }
        let times = refs.compactMap { r in refTime(r) ?? refGameId(r).flatMap { starts[$0] } }.compactMap { Models.date($0) }
        guard let first = times.min() else { return nil }
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: first)
    }
    /// The Eastern day a bet belongs to ("2026-10-15"): its game's start, else when it was marked.
    /// Remembered by the time it reads: Stats, achievements and Wrapped ask for every bet's day many times per view.
    static func day(_ b: MyBet) -> String {
        let t = start(b) ?? b.placedAt
        dayLock.lock(); defer { dayLock.unlock() }
        if let d = days[t] { return d }
        guard let date = Models.date(t) else { return etDay(Date()) }     // no time: today, never remembered
        let d = etDay(date)
        days[t] = d
        return d
    }
    private static let dayLock = NSLock()
    nonisolated(unsafe) private static var days: [String: String] = [:]     // guarded by dayLock

    private static let etDayF: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = Fmt.et
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
    static func etDay(_ d: Date) -> String { etDayF.string(from: d) }
    /// The same Eastern wall time n days away, by the calendar: a clock-change day isn't 24 hours (web `addDays`).
    static func etShift(_ d: Date, days n: Int) -> Date {
        var c = Calendar(identifier: .gregorian); c.timeZone = Fmt.et
        return c.date(byAdding: .day, value: n, to: d) ?? d.addingTimeInterval(Double(n) * 86_400)
    }

    /// A profit boost (Oct 22, `bets.boost` in percent) multiplies a win's profit; the price stays the book's own.
    static func boostFactor(_ b: MyBet) -> Double { 1 + max(b.boost ?? 0, 0) / 100 }

    /// A win's profit with its boost: the book's own profit plus the boost's share, never more than the boost's cap
    /// (`boost_cap`, units: the book's max extra winnings, Oct 30). A loss is unchanged. Web `boosted`,
    /// fun_ledger.marked_profit; one fixture, tests/fixtures/promo_profit.json.
    static func boosted(_ b: MyBet, _ base: Double) -> Double {
        guard base > 0 else { return base }
        let extra = base * (boostFactor(b) - 1)
        if let cap = b.boostCap, cap >= 0 { return base + min(extra, cap) }
        return base + extra
    }

    /// A void or pushed parlay leg takes the price down by its fair chance, as FanDuel settles it.
    static func voidFactor(_ b: MyBet) -> Double {
        (b.legResults ?? []).reduce(1) { f, l in (l.result == "void" || l.result == "push") && l.p != nil ? f * l.p! : f }
    }

    /// Novig (Oct 28; web novigVoidProfit) counts a void leg at its fair value instead of dropping it: the pot times the
    /// legs' values, never under 0.001 of it, so it can pay back less than the stake, and all legs void still pays that
    /// share. Nil when this rule doesn't apply.
    static func novigVoidProfit(_ b: MyBet, _ st: Double) -> Double? {
        let f = voidFactor(b)
        guard Marking.bookOf(b.book) == "Novig", f < 1, let price = b.price else { return nil }
        let p = st * (dec(price) * max((f * 1000).rounded() / 1000, 0.001) - 1)
        return boosted(b, p)
    }

    /// FanDuel's Bet Protect+ (Oct 26, `bets.protect`; web protectFee): 3% of the stake on top, in cash even on a bonus
    /// bet, refunded when the bet is void.
    static let protectFee = 0.03
    static func fee(_ b: MyBet) -> Double { b.protect == true ? protectFee * stake(b) : 0 }

    /// Profit in units at the price you took (not the model's logged price), less a Bet Protect+ fee. Nil until settled.
    static func profit(_ b: MyBet) -> Double? {
        guard let p = profitBeforeFee(b) else { return nil }
        return status(b) == "void" ? p : p - fee(b)
    }

    private static func profitBeforeFee(_ b: MyBet) -> Double? {
        let st = stake(b)
        if status(b) == "won" || status(b) == "void", let p = novigVoidProfit(b, st) { return p }
        switch status(b) {
        case "cashout": return b.cashout! - (b.isBonus ? 0 : st)   // a bonus bet's stake was never yours
        case "won":
            if let price = b.price { return boosted(b, st * (max(dec(price) * voidFactor(b), 1) - 1)) }
            return (b.profitFlat ?? b.profit1u).map { st * $0 }
        case "lost": return b.isBonus ? 0 : -st       // a bonus bet's stake was the book's credit
        case "push", "void": return 0
        default: return nil
        }
    }

    /// CLV at your price, keeping the shared close's push chance. A parlay has no sharp close, so no CLV.
    static func personalClv(_ b: MyBet) -> Double? {
        if b.kind == "parlay" || b.kind == "custom" { return nil }
        let isProp = b.pickKind == "prop" || (b.market ?? "").hasPrefix("player_")
        guard let original = isProp ? b.clvRaw : b.clv else { return nil }
        guard let price = b.price else { return original }        // no personal price: the logged pick's close
        guard let logged = b.loggedPrice else { return nil }
        if price == logged { return original }
        guard let push = b.closePush, push >= 0, push <= 1 else { return nil }
        if abs(price) < 100 || abs(logged) < 100 { return nil }
        // CLV = P(win) * decimal price + P(push) - 1: recover P(win) from the original CLV
        let win = (original + 1 - push) / dec(logged)
        if win < 0 || win > 1 - push { return nil }
        return original + win * (dec(price) - dec(logged))
    }

    private static let ticketKinds = ["sgp": "Same-game parlays", "sgp_plus": "SGP+ tickets", "td": "Anytime TD tickets", "over": "Overs"]

    /// The row a bet counts under: sport and market for single bets, the ticket type for parlays.
    static func group(_ b: MyBet) -> String {
        if b.kind == "custom" { return "Your own parlays" }
        if b.kind == "parlay" {
            if let k = b.ticketKind, let name = ticketKinds[k] { return name }
            let id = b.sgpId ?? ""
            return ticketKinds[id.hasPrefix("plus-") ? "sgp_plus" : id.hasPrefix("td-") ? "td" : "sgp"]!
        }
        let m = Fmt.marketName(b.market)
        return "\(Fmt.sportName(b.league)) · \(m.isEmpty ? "Bet" : m)"
    }

    /// The book a bet was placed at (Novig bets also arrive from the Novig sync, Oct 23); bets before Oct 12 are FanDuel's.
    static func book(_ b: MyBet) -> String { Marking.bookOf(b.book) }

    /// Settled bets grouped (by market unless told otherwise), with a total.
    /// How a bet counts in the win-loss record (Mike, Oct 26; web recordOutcome): won; lost (a push too); void (kept
    /// apart); nil while its outcome is open. A cash-out counts as its bet settles; its P/L stays what the book paid back.
    static func recordOutcome(_ b: MyBet) -> String? {
        switch (b.pickStatus ?? b.ticketStatus ?? "open").lowercased() {
        case "won": "won"
        case "lost", "push": "lost"
        case "void": "void"
        default: nil
        }
    }

    static func record(_ bets: [MyBet], by groupBy: (MyBet) -> String = group) -> (lines: [RecordLine], total: RecordLine) {
        var by: [String: RecordLine] = [:]
        var total = RecordLine(group: "All bets")
        for b in bets where isSettled(b) {
            let g = groupBy(b)
            var line = by[g] ?? RecordLine(group: g)
            let s = status(b), r = recordOutcome(b), clv = personalClv(b)
            for i in 0..<2 {
                var l = i == 0 ? line : total
                l.bets += 1
                if r == "won" { l.won += 1 } else if r == "lost" { l.lost += 1 } else if r == "void" { l.push += 1 }   // push: voids only (Oct 26)
                if s != "void" && !b.isBonus { l.staked += stake(b) }    // ROI is on cash: a bonus stake was never yours
                l.units += profit(b) ?? 0
                if let c = clv { l.clvN += 1; l.clvSum += c; if c > 0 { l.beat += 1 } }
                if i == 0 { line = l } else { total = l }
            }
            by[g] = line
        }
        let lines = by.values.sorted { $0.bets != $1.bets ? $0.bets > $1.bets : $0.group < $1.group }
        return (lines, total)
    }

    /// Which bets are "your record" (Mike, Oct 14: "on October 18th my record is clear"; web recordBets). Once real money
    /// starts for the account (Oct 18 00:00 ET or its real_from), only real bets count, from 0-0 even before the first one
    /// is marked; before that, every bet counts (paper). Paper bets are never deleted: they show apart.
    static func recordBets(_ bets: [MyBet], realMode: Bool) -> (useReal: Bool, counted: [MyBet], paper: [MyBet]) {
        let real = bets.filter(\.isReal)
        let useReal = realMode || !real.isEmpty
        return (useReal, useReal ? real : bets, bets.filter { !$0.isReal })
    }

    /// Units put on parlays this month (the fun bucket); bonus bets cost no cash.
    static func bucketUsed(_ bets: [MyBet], now: Date = Date()) -> Double {
        let month = String(etDay(now).prefix(7))
        return bets.filter { ($0.kind == "parlay" || $0.kind == "custom") && !$0.isBonus && etDay(Models.date($0.placedAt) ?? now).hasPrefix(month) }
            .reduce(0) { $0 + stake($1) }
    }

    /// Units at risk on real bets for games on an Eastern day (the 5-unit daily cap); a bonus bet risks no cash.
    static func atRisk(_ bets: [MyBet], day: String) -> Double {
        bets.filter { $0.isReal && !$0.isBonus && !isSettled($0) && self.day($0) == day }.reduce(0) { $0 + stake($1) }
    }

    struct BonusLine: Equatable { var bets = 0, settled = 0, won = 0; var face = 0.0, converted = 0.0; var rate: Double? }

    /// Bonus bets settled so far: face value used (units), what it turned into, and the conversion rate (cash per unit
    /// of bonus; a fair +400 converts about 80%, a -110 favorite about 45%). Voids return the credit: not used.
    static func bonusSummary(_ bets: [MyBet]) -> BonusLine {
        let all = bets.filter(\.isBonus)
        let done = all.filter { isSettled($0) && status($0) != "void" }
        let face = done.reduce(0) { $0 + stake($1) }, converted = done.reduce(0) { $0 + (profit($1) ?? 0) }
        return BonusLine(bets: all.count, settled: done.count, won: done.filter { status($0) == "won" }.count,
                         face: face, converted: converted, rate: face > 0 ? converted / face : nil)
    }

    struct BoostLine: Equatable { var bets = 0, settled = 0, won = 0; var units = 0.0, fromBoost = 0.0, staked = 0.0 }

    struct PromoLedger { let placed: Int; let settled: Int; let units: Double; let expected: Double }

    /// Bets placed from the promo finder (`promo_ev`, Oct 30; web promoLedger): what they turned into against what the
    /// finder expected, in units at the account's unit size. Settled, non-void ones only.
    static func promoLedger(_ bets: [MyBet], unit: Double) -> PromoLedger {
        let placed = bets.filter { $0.promoEv != nil }
        let done = placed.filter { isSettled($0) && status($0) != "void" }
        return PromoLedger(placed: placed.count, settled: done.count, units: done.reduce(0) { $0 + (profit($1) ?? 0) },
                           expected: done.reduce(0) { $0 + $1.promoEv! / unit })
    }

    /// Boosted cash bets settled so far: their P/L, and the part of it the boosts added (each win's profit beyond what
    /// the book's own price paid, within its cap). Cash-outs count at what they paid back. A boosted bonus bet counts
    /// once, as a bonus (Oct 30).
    static func boostSummary(_ bets: [MyBet]) -> BoostLine {
        let all = bets.filter { ($0.boost ?? 0) > 0 && !$0.isBonus }
        let done = all.filter { isSettled($0) && status($0) != "void" }
        let won = done.filter { status($0) == "won" }
        return BoostLine(bets: all.count, settled: done.count, won: won.count,
                         units: done.reduce(0) { $0 + (profit($1) ?? 0) },
                         fromBoost: won.reduce(0) { s, b in var plain = b; plain.boost = nil; return s + (profit(b) ?? 0) - (profit(plain) ?? 0) },
                         staked: done.filter { !$0.isBonus }.reduce(0) { $0 + stake($1) })
    }

    /// What a bet was on, in one line: its label, or the ticket's title and leg count.
    static func what(_ b: MyBet) -> String {
        if let l = b.label, !l.isEmpty { return Fmt.label(l) }
        let head = String((b.matchup ?? "").split(separator: ":").first ?? "")
        let n = b.legs?.count ?? 0
        return n > 0 ? "\(head) · \(n) legs" : (head.isEmpty ? "Parlay" : head)
    }

    /// "+1.20u" / "−1.00u"
    static func signedUnits(_ u: Double?) -> String {
        guard let u else { return "—" }
        return (u >= 0 ? "+" : Fmt.minus) + String(format: "%.2fu", abs(u))
    }
}
