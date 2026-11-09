import Foundation

// What the home-screen and lock-screen widgets show (Oct 27): the app writes it to the shared App Group whenever your
// bets load or change (Widgets.swift), and the widget extension reads it. Units only, like the apps.
struct WidgetSnapshot: Codable, Equatable {
    struct Bet: Codable, Hashable {
        var title: String
        var price: String
        var start: Date?
        var legs: Int
    }

    var updated: Date
    var today: Double               // units won or lost on today's settled bets (your record's bets)
    var week: Double                // the last 7 Eastern days
    var settledToday: Int
    var openCount: Int
    var open: [Bet]                 // the next few, soonest first
    var real: Bool                  // real money (else paper)

    static let group = "group.com.mopsha.betlab"
    private static let key = "widget-snapshot"

    static func load() -> WidgetSnapshot? {
        guard let d = UserDefaults(suiteName: group)?.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(WidgetSnapshot.self, from: d)
    }

    func save() {
        guard let d = try? JSONEncoder().encode(self) else { return }
        UserDefaults(suiteName: Self.group)?.set(d, forKey: Self.key)
    }

    /// Sign-out: one account's units and open bets must not stay on the home screen for the next.
    static func clear() {
        UserDefaults(suiteName: group)?.removeObject(forKey: key)
    }

    static let sample = WidgetSnapshot(updated: Date(), today: 2.4, week: -1.15, settledToday: 3, openCount: 2,
                                       open: [Bet(title: "4-leg parlay", price: "+1200", start: Date().addingTimeInterval(3600), legs: 4),
                                              Bet(title: "Jets +3.5", price: "-110", start: Date().addingTimeInterval(7200), legs: 1)],
                                       real: true)
}

/// Signed units as the apps show them (BetMath.signedUnits): "+2.40u", "−1.15u".
func unitsText(_ u: Double) -> String {
    (u >= 0 ? "+" : "\u{2212}") + String(format: "%.2fu", abs(u))
}
