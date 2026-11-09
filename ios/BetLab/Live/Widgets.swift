import Foundation
import WidgetKit

/// The widgets' data (Oct 27): today's and the week's units from your record's bets, and your open bets soonest first,
/// written to the App Group each time your bets change (BetStore) so the home-screen and lock-screen widgets
/// (BetLabWidgets) show them. The widget can't sign in, so it shows what the app last saw and when.
enum WidgetFeed {
    static let shown = 4

    static func snapshot(_ bets: [MyBet], realMode: Bool, now: Date = Date()) -> WidgetSnapshot {
        let rec = BetMath.recordBets(bets, realMode: realMode)
        let today = BetMath.etDay(now)
        let weekStart = BetMath.etDay(BetMath.etShift(now, days: -6))
        let settled = rec.counted.filter(BetMath.isSettled)
        let sum = { (l: [MyBet]) in l.reduce(0) { $0 + (BetMath.profit($1) ?? 0) } }
        let todays = settled.filter { BetMath.day($0) == today }
        let open = rec.counted.filter { !BetMath.isSettled($0) && $0.liveSettled == nil }
        let soon = open.map { b in (b, BetMath.start(b).flatMap(Models.date)) }
            .sorted { ($0.1 ?? .distantFuture) < ($1.1 ?? .distantFuture) }
        return WidgetSnapshot(updated: now, today: sum(todays), week: sum(settled.filter { BetMath.day($0) >= weekStart }),
                              settledToday: todays.count, openCount: open.count,
                              open: soon.prefix(shown).map { b, start in
                                  let legs = (b.legs ?? []).isEmpty ? 1 : b.legs!.count
                                  return .init(title: Stats.betName(legs: b.legs, label: b.label, price: nil, n: legs),
                                               price: b.price.map { Fmt.am($0) } ?? "", start: start, legs: legs)
                              },
                              real: rec.useReal)
    }

    /// Signed out: the widgets forget the last account (they show their signed-out face until the next one loads).
    static func clear() {
        WidgetSnapshot.clear()
        WidgetCenter.shared.reloadAllTimelines()
    }

    /// Save and redraw the widgets, only when what they show changed (a reload spends the widgets' daily budget).
    static func write(_ bets: [MyBet], realMode: Bool) {
        let s = snapshot(bets, realMode: realMode)
        if var o = WidgetSnapshot.load() { o.updated = s.updated; if o == s { return } }
        s.save()
        WidgetCenter.shared.reloadAllTimelines()
    }
}
