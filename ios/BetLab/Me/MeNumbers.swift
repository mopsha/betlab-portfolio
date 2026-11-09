import Foundation

/// The range Me's number, chart and four stats follow.
enum MeRange: String, CaseIterable, Identifiable {
    case week, month, all
    var id: String { rawValue }
    var chip: String { self == .week ? "Week" : self == .month ? "Month" : "All" }
    /// The line under the number.
    var label: String { self == .week ? "this week" : self == .month ? "this month" : "all time" }

    /// The first Eastern day inside the range (7 or 30 days back, by the calendar); nil for all time.
    func from(_ now: Date = Date()) -> String? {
        switch self {
        case .week: BetMath.etDay(BetMath.etShift(now, days: -7))
        case .month: BetMath.etDay(BetMath.etShift(now, days: -30))
        case .all: nil
        }
    }
}

/// Me's numbers in a range. A bet's day is the record's day (BetMath.day: its game's Eastern day, the day Stats.timeline
/// charts it on), so the number is always the chart's rise or fall and the record helpers do all the counting.
enum MeNumbers {
    /// The bets a range counts: all of them for all time, else the settled ones whose day is inside it.
    static func ranged(_ bets: [MyBet], _ range: MeRange, now: Date = Date()) -> [MyBet] {
        guard let from = range.from(now) else { return bets }
        return bets.filter { BetMath.isSettled($0) && BetMath.day($0) >= from }
    }

    /// Units after each day with a settled bet (Stats.timeline), from where the range starts; all time starts at 0.
    static func series(_ bets: [MyBet], _ range: MeRange, now: Date = Date()) -> [Double] {
        let all = Stats.timeline(bets)
        guard let from = range.from(now) else { return all.isEmpty ? [] : [0] + all.map(\.units) }
        let inside = all.filter { $0.day >= from }
        guard let first = inside.first else { return [] }
        return [first.units - first.net] + inside.map(\.units)
    }
}
