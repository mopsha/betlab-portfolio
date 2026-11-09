import Foundation

/// FanDuel's College Football Pick'em (Nov 7; worker src/betlab/pickem.py, table `pickem`, migration 0044). The lines
/// freeze Wednesday morning and the entry locks Saturday at noon ET; the worker prices each frozen line against the
/// sharp market and names our side. Same rules as the worker and the web: tests/fixtures/pickem.json.
struct PickemRow: Decodable, Identifiable, Equatable {
    var pickId: String?
    var week: String
    var n: Int
    var away: String
    var home: String
    var awayName: String?
    var homeName: String?
    var awayLogo: String?
    var homeLogo: String?
    var homeLine: Double
    var pick: String?
    var ours: String?
    var pHome: Double?
    var fairLine: Double?
    var pricedAt: String?
    var eventId: String?
    var start: String?
    var homePts: Int?
    var awayPts: Int?
    var result: String?
    var notice: String?

    var id: String { pickId ?? "\(week):\(n)" }
    var graded: Bool { result == "home" || result == "away" || result == "push" }
}

struct PickemWeek: Decodable, Equatable {
    var week: String
    var partnerBest: Int?
    var reward: String?
}

enum Pickem {
    static let minFlip = 0.52

    struct Score: Equatable { var games = 0, picked = 0, graded = 0, yours = 0, ours = 0 }

    /// The lock day of the entry a day falls in: the coming Saturday (that day, on a Saturday). `etDay`: "2026-11-07".
    static func weekOf(_ etDay: String) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.timeZone = TimeZone(identifier: "UTC")
        guard let d = f.date(from: etDay) else { return etDay }
        var cal = Calendar(identifier: .gregorian); cal.timeZone = TimeZone(identifier: "UTC")!
        let wd = cal.component(.weekday, from: d)            // 1 Sunday ... 7 Saturday
        let ahead = (7 - wd + 7) % 7
        return f.string(from: cal.date(byAdding: .day, value: ahead, to: d) ?? d)
    }

    /// The week's tally: how many you got right, how many BetLab's side would have. A push counts for both.
    static func score(_ rows: [PickemRow]) -> Score {
        let done = rows.filter(\.graded)
        return Score(games: rows.count, picked: rows.filter { $0.pick != nil }.count, graded: done.count,
                     yours: done.filter { $0.pick != nil && ($0.result == $0.pick || $0.result == "push") }.count,
                     ours: done.filter { $0.ours != nil && ($0.result == $0.ours || $0.result == "push") }.count)
    }

    /// The picks against our side with our side at 52% or better, and the games not picked yet.
    static func flips(_ rows: [PickemRow]) -> (toFlip: [PickemRow], unpicked: [PickemRow]) {
        var toFlip: [PickemRow] = [], unpicked: [PickemRow] = []
        for r in rows {
            if r.pick == nil { unpicked.append(r) }
            else if let o = r.ours, let p = r.pHome, r.pick != o, max(p, 1 - p) >= minFlip { toFlip.append(r) }
        }
        return (toFlip, unpicked)
    }

    /// "Iowa +2.5": the side's team as FanDuel names it and its frozen line.
    static func sideLabel(_ r: PickemRow, _ side: String) -> String {
        let team = side == "home" ? r.home : r.away
        let line = side == "home" ? r.homeLine : -r.homeLine
        return "\(team) \(line > 0 ? "+" : "")\(num(line))"
    }

    /// A spread as FanDuel writes it: "2.5", "6", "-10.5".
    static func num(_ v: Double) -> String { v == v.rounded() ? String(Int(v)) : String(format: "%.1f", v) }

    /// The chance a side covers the frozen line, from the row's home chance.
    static func chance(_ r: PickemRow, _ side: String) -> Double? {
        guard let p = r.pHome else { return nil }
        return side == "home" ? p : 1 - p
    }
}
