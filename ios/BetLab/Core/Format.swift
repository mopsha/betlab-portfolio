import Foundation

// Odds and names, as web/lib/format.ts writes them.

enum Fmt {
    /// Soccer's leagues and the Odds API's soccer keys ("soccer", "epl", "uecl", "soccer_uefa_europa_league").
    static func isSoccer(_ sport: String?) -> Bool {
        (sport ?? "").lowercased().range(of: #"^(soccer|epl|la_liga|serie_a|bundesliga|ligue_1|mls|ucl|uel|uecl)(?![a-z])"#,
                                         options: .regularExpression) != nil
    }

    /// Soccer reads home team first (Mike, Nov 5): our stored "Away @ Home" (every parser still reads that) is shown as
    /// "Home vs Away", each match of a ticket's list too. Other sports as stored. Web format.ts matchupText; fixture
    /// tests/fixtures/soccer_matchups.json.
    static func matchup(_ text: String?, sport: String?) -> String {
        let s = text ?? ""
        guard isSoccer(sport), let re = try? NSRegularExpression(pattern: #"(^|[,:]\s*)([^,:]+?) @ ([^,]+?)(?=,|$)"#) else { return s }
        var out = s
        for m in re.matches(in: s, range: NSRange(s.startIndex..., in: s)).reversed() {
            let part = { (i: Int) in Range(m.range(at: i), in: s).map { String(s[$0]) } ?? "" }
            let r = Range(m.range, in: s)!
            out.replaceSubrange(r, with: part(1) + part(3).trimmingCharacters(in: .whitespaces) + " vs " + part(2).trimmingCharacters(in: .whitespaces))
        }
        return out
    }

    static let minus = "\u{2212}"
    static let et = TimeZone(identifier: "America/New_York")!

    static let sports: [String: String] = ["nfl": "NFL", "ncaaf": "College football", "nhl": "NHL", "nba": "NBA",
                                          "ncaab": "College basketball", "soccer": "Soccer", "ufc": "UFC", "mlb": "MLB", "wnba": "WNBA"]
    static let sportShort: [String: String] = ["nfl": "NFL", "ncaaf": "CFB", "nhl": "NHL", "nba": "NBA",
                                              "ncaab": "CBB", "soccer": "Soccer", "ufc": "UFC", "mlb": "MLB", "wnba": "WNBA"]
    static func sportName(_ k: String?) -> String { sports[(k ?? "").lowercased()] ?? "Soccer" }

    static func marketName(_ m: String?) -> String {
        let m = m ?? ""
        if m.hasPrefix("player_") { return "Player prop" }
        return ["h2h": "Moneyline", "spreads": "Spread", "totals": "Total", "h2h_3_way": "Result (3-way)"][m] ?? m
    }

    /// American odds: +150, −110.
    static func am(_ v: Double?) -> String {
        guard let a = v, a.isFinite else { return "—" }
        return (a >= 0 ? "+" : minus) + String(Int(abs(a).rounded()))
    }

    static func pct(_ v: Double?, _ d: Int = 0) -> String {
        guard let x = v, x.isFinite else { return "—" }
        return String(format: "%.\(d)f%%", x * 100)
    }

    /// +4.2% / −1.0%
    static func signed(_ v: Double?, _ d: Int = 1) -> String {
        guard let x = v, x.isFinite else { return "—" }
        return (x >= 0 ? "+" : minus) + String(format: "%.\(d)f%%", abs(x * 100))
    }

    /// The American price a chance is worth with no vig (a pick card's fair price).
    static func fair(_ p: Double) -> Double {
        guard p > 0, p < 1 else { return .nan }
        return (p >= 0.5 ? -100 * p / (1 - p) : 100 * (1 - p) / p).rounded()
    }

    static func implied(_ american: Double) -> Double {
        let dec = american > 0 ? 1 + american / 100 : 1 + 100 / -american
        return 1 / dec
    }

    /// A bet's label with real minus signs ("Bills -3.5" → "Bills −3.5").
    static func label(_ s: String?) -> String {
        var out = s ?? ""
        if out.hasPrefix("-"), out.dropFirst().first?.isNumber == true { out = minus + out.dropFirst() }
        return out.replacingOccurrences(of: #" -(\d)"#, with: " \(minus)$1", options: .regularExpression)
    }

    private static func formatter(_ fmt: String) -> DateFormatter {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = et
        f.dateFormat = fmt
        return f
    }
    private static let timeF = formatter("h:mm a")
    private static let dayTimeF = formatter("EEE h:mm a")
    private static let longDayF = formatter("EEEE, MMM d")
    private static let shortDayF = formatter("MMM d")

    /// "7:15 PM" (Eastern)
    static func time(_ iso: String?) -> String { Models.date(iso).map { timeF.string(from: $0) } ?? "" }
    /// "Thu 7:15 PM" (Eastern)
    static func dayTime(_ iso: String?) -> String { Models.date(iso).map { dayTimeF.string(from: $0) } ?? "" }
    /// "Thursday, Oct 15" (Eastern)
    static func longDay(_ d: Date) -> String { longDayF.string(from: d) }
    /// "Oct 15" (Eastern)
    static func shortDay(_ d: Date) -> String { shortDayF.string(from: d) }
}
