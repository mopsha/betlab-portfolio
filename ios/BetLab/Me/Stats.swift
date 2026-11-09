import Foundation

// My bets > Stats (Mike's #40, Oct 24: "personal stats") and achievements (W29), ported from web/lib/stats.ts and
// web/lib/achievements.ts; the share card's content from web/lib/share.ts. Pure. The groupings feed BetMath.record, so
// units, ROI and CLV mean exactly what they do on the Record tab. MyBetsTests runs web/tests/stats.test.mjs's cases.
// **Change both together.**

enum Stats {
    private static let soccer: Set<String> = ["epl", "la_liga", "serie_a", "bundesliga", "ligue_1", "mls", "ucl", "uel", "uecl", "soccer"]
    private static func sportKey(_ k: String?) -> String { let s = (k ?? "").lowercased(); return soccer.contains(s) ? "soccer" : s }

    /// A custom bet's games: [{matchup, game_ref, legs}] (my_bets arrives camelCased: gameRef).
    static func games(_ b: MyBet) -> [(ref: String?, legs: [String])] {
        (b.games?.array ?? []).map { g in ((g["gameRef"].string ?? g["game_ref"].string), g["legs"].array.compactMap(\.string)) }
    }

    /// A game ref's sport: "ncaaf:401856731", "epl|Home|Away|kickoff", "ufc:<event>:<fight>", "2026_07_NE_CHI".
    static func refSportKey(_ ref: String?) -> String? {
        let s = ref ?? ""
        if s.contains("|") { let k = sportKey(s.components(separatedBy: "|")[0]); return k.isEmpty ? nil : k }
        if s.range(of: #"^\d{4}_\d{2}_"#, options: .regularExpression) != nil { return "nfl" }
        let head = s.components(separatedBy: ":")[0]
        return s.contains(":") && !head.isEmpty ? head : nil
    }

    // A custom bet entered without game ids (most before Oct 24): its sport from what it says. A title ("NBA late games"),
    // then prop wording (college player props are never bet in New York, so yardage props are the NFL's), then NBA nicknames.
    private static let title: [(String, String, Bool)] = [(#"\bNBA\b"#, "nba", false), (#"\bNHL\b"#, "nhl", false), (#"\bNFL\b"#, "nfl", false),
        ("college football", "ncaaf", true), ("college basketball", "ncaab", true), (#"\bUFC\b"#, "ufc", false), (#"soccer|SGP\+ .*matches"#, "soccer", true)]
    private static let prop: [(String, String, Bool)] = [(#"passing yds|receiving yds|rushing yds|receptions|anytime TD|first TD"#, "nfl", true),
        (#"shots on goal|saves\b"#, "nhl", true), ("shots on target|to score or assist", "soccer", true),
        (#"rebounds|threes|\d+\+ points|over [\d.]+ (points|assists)"#, "nba", true)]
    private static let nba = #"\b(Celtics|Knicks|Nets|76ers|Raptors|Bulls|Cavaliers|Pistons|Pacers|Bucks|Hawks|Hornets|Heat|Magic|Wizards|Nuggets|Timberwolves|Thunder|Trail Blazers|Jazz|Warriors|Clippers|Lakers|Suns|Kings|Mavericks|Rockets|Grizzlies|Pelicans|Spurs)\b"#

    static func guessSport(_ b: MyBet) -> String? {
        let text = ([b.matchup ?? ""] + (b.legs ?? [])).joined(separator: " | ")
        for (re, k, ci) in title + prop where text.range(of: re, options: ci ? [.regularExpression, .caseInsensitive] : .regularExpression) != nil { return k }
        return text.range(of: nba, options: .regularExpression) != nil ? "nba" : nil
    }

    /// The sport a bet counts under: a single's league, a ticket's sport, a custom bet's games (else what it says);
    /// "Multi-sport" when its legs span more than one.
    static func sportOf(_ b: MyBet) -> String {
        if b.kind == "pick" || b.kind == "lean" { return Fmt.sportName(sportKey(b.league)) }
        var fromGames: [String] = []
        for g in games(b) { if let k = refSportKey(g.ref), !fromGames.contains(k) { fromGames.append(k) } }
        if fromGames.count > 1 { return "Multi-sport" }
        let k = fromGames.first ?? (b.sport != nil && b.sport != "mixed" ? sportKey(b.sport) : b.sport == "mixed" ? "mixed" : guessSport(b))
        return k == "mixed" ? "Multi-sport" : k.map { $0.isEmpty ? "Other" : Fmt.sportName($0) } ?? "Other"
    }

    static func legsOf(_ b: MyBet) -> Int { max(b.legs?.count ?? 0, games(b).reduce(0) { $0 + $1.legs.count }, 1) }
    static func typeOf(_ b: MyBet) -> String { legsOf(b) == 1 ? "Single" : legsOf(b) <= 4 ? "Parlay, 2-4 legs" : "Parlay, 5+ legs" }

    /// Price bands, shortest first.
    static let bands = ["Favorite (-111 or shorter)", "Near even (-110 to +150)", "Underdog (+151 to +400)", "Long shot (+401 to +1000)", "Lottery (+1001 or longer)"]
    static func bandOf(_ b: MyBet) -> String {
        guard let p = b.price else { return "No price" }
        return p <= -111 ? bands[0] : p <= 150 ? bands[1] : p <= 400 ? bands[2] : p <= 1000 ? bands[3] : bands[4]
    }
    static func moneyOf(_ b: MyBet) -> String { b.isBonus ? "Bonus bets" : (b.boost ?? 0) > 0 ? "Boosted cash" : "Plain cash" }
    static let weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    static func weekdayOf(_ b: MyBet) -> String { weekdays[weekday(BetMath.day(b))] }

    /// 0 = Sunday, for an Eastern day "2026-10-24".
    private static func weekday(_ day: String) -> Int {
        var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(identifier: "UTC")!
        guard let d = Models.date(day + "T12:00:00Z") else { return 0 }
        return c.component(.weekday, from: d) - 1
    }

    /// Settled bets in the order they settled (game day, then when placed).
    static func chrono(_ bets: [MyBet]) -> [MyBet] {
        // each bet's day worked out once: BetMath.day parses a date, and in the comparator it ran ~30 times a bet (0.7 s
        // for 101 bets, every Stats render)
        let keyed: [(day: String, b: MyBet)] = bets.filter(BetMath.isSettled).map { (BetMath.day($0), $0) }
        return keyed.sorted { x, y in x.day != y.day ? x.day < y.day : x.b.placedAt < y.b.placedAt }.map(\.b)
    }

    struct Point: Equatable, Identifiable { let day: String; let units: Double; let net: Double; var id: String { day } }

    /// Units after each day with a settled bet.
    static func timeline(_ bets: [MyBet]) -> [Point] {
        var days: [String] = [], net: [String: Double] = [:]
        for b in chrono(bets) {
            let d = BetMath.day(b)
            if net[d] == nil { days.append(d) }
            net[d, default: 0] += BetMath.profit(b) ?? 0
        }
        var run = 0.0
        return days.map { d in run += net[d]!; return Point(day: d, units: run, net: net[d]!) }
    }

    /// The current run of wins or losses and the longest winning run (pushes and voids neither extend nor break one).
    static func streaks(_ bets: [MyBet]) -> (kind: String?, n: Int, bestWin: Int) {
        var kind: String? = nil, n = 0, best = 0, run = 0
        for b in chrono(bets) {
            // counted as the record counts them (BetMath.recordOutcome: a push is a loss, a cash-out as its bet settled)
            guard let s = BetMath.recordOutcome(b), s != "void" else { continue }
            n = s == kind ? n + 1 : 1; kind = s
            run = s == "won" ? run + 1 : 0; best = max(best, run)
        }
        return (kind, n, best)
    }

    /// The biggest win and the worst loss in units (a bonus loss costs nothing, so it's never the worst).
    static func extremes(_ bets: [MyBet]) -> (best: MyBet?, worst: MyBet?) {
        var best: MyBet? = nil, worst: MyBet? = nil
        for b in chrono(bets) {
            guard let p = BetMath.profit(b) else { continue }
            if p > 0 && (best == nil || p > BetMath.profit(best!)!) { best = b }
            if p < 0 && (worst == nil || p < BetMath.profit(worst!)!) { worst = b }
        }
        return (best, worst)
    }

    struct Summary {
        var total: RecordLine
        var bySport, byType, byBand, byMoney, byBook, byWeekday: [RecordLine]
        var timeline: [Point]
        var streaks: (kind: String?, n: Int, bestWin: Int)
        var extremes: (best: MyBet?, worst: MyBet?)
    }

    static func summary(_ bets: [MyBet]) -> Summary {
        let order = { (keys: [String]) in { (lines: [RecordLine]) in lines.sorted { (keys.firstIndex(of: $0.group) ?? -1) < (keys.firstIndex(of: $1.group) ?? -1) } } }
        return Summary(total: BetMath.record(bets).total,
                       bySport: BetMath.record(bets, by: sportOf).lines,
                       byType: order(["Single", "Parlay, 2-4 legs", "Parlay, 5+ legs"])(BetMath.record(bets, by: typeOf).lines),
                       byBand: order(bands + ["No price"])(BetMath.record(bets, by: bandOf).lines),
                       byMoney: order(["Plain cash", "Boosted cash", "Bonus bets"])(BetMath.record(bets, by: moneyOf).lines),
                       byBook: BetMath.record(bets, by: BetMath.book).lines,
                       byWeekday: order(weekdays)(BetMath.record(bets, by: weekdayOf).lines),
                       timeline: timeline(bets), streaks: streaks(bets), extremes: extremes(bets))
    }

    /// "Fagnano, Lawrence and 2 more +940", or the single's leg "Michigan Wolverines ML +250" (web lib/gameday.ts betName,
    /// on tests/fixtures/bet_names.json).
    static func betName(legs: [String]?, label: String?, price: Double?, n: Int? = nil) -> String {
        let l = !(legs ?? []).isEmpty ? legs! : label.map { [$0] } ?? []
        let count = n ?? l.count
        let p = price.map { " \($0 > 0 ? "+" : "")\(Live.js($0))" } ?? ""
        return (count > 1 ? parlayName(l, count) : l.first ?? "Bet") + p
    }

    /// Who a leg is about: a team by its full name, a player without his first name; nil for a leg with no name
    /// ("Over 47.5"). Where the name stops: a number, a side or a market word (web legName).
    static func legName(_ leg: String, full: Bool = false) -> String? {
        let w = leg.split(whereSeparator: \.isWhitespace).map(String.init)
        let stops: Set<String> = ["over", "under", "ml", "anytime", "to", "yes", "no", "draw", "first", "last", "alt", "both", "total", "btts"]
        let stop = { (x: String) -> Bool in
            x.range(of: #"^([+\-.]?\d|o\d|u\d)"#, options: .regularExpression) != nil || stops.contains(x.lowercased())
        }
        let i = w.firstIndex(where: stop) ?? w.count
        let who = Array(w[..<i]), rest = Array(w[i...])
        guard !who.isEmpty else { return nil }
        // a team line is the name and then only a moneyline, a spread or "to win"; anything else is a player's prop
        let team = rest.isEmpty
            || (rest.count == 1 && rest[0].range(of: #"^(ml|[+\-]\d+(\.\d+)?|draw)$"#, options: [.regularExpression, .caseInsensitive]) != nil)
            || (rest.first?.lowercased() == "to" && rest.dropFirst().first?.lowercased() == "win")
        let suffix = who.count == 2 && who[1].range(of: #"^(jr\.?|sr\.?|ii|iii|iv)$"#, options: [.regularExpression, .caseInsensitive]) != nil
        if team || who.count < 2 || suffix { return who.joined(separator: " ") }
        return full ? who.joined(separator: " ") : who.dropFirst().joined(separator: " ")
    }

    /// A parlay by who is in it (overhaul, Nov 6): two names, then "and N more" for the other names and the legs with no
    /// name; one name on every leg is "Rashod Bateman, 2 legs"; no name at all, "4-leg parlay".
    static func parlayName(_ legs: [String], _ count: Int) -> String {
        guard legs.count == count else { return "\(count)-leg parlay" }
        var names: [String] = [], bare = 0
        for l in legs {
            if let n = legName(l) { if !names.contains(n) { names.append(n) } } else { bare += 1 }
        }
        if names.isEmpty { return "\(count)-leg parlay" }
        if names.count == 1 && bare == 0 { return "\(legName(legs[0], full: true) ?? names[0]), \(count) legs" }
        let more = names.count - min(2, names.count) + bare
        let shown = names.prefix(2).joined(separator: ", ")
        return more > 0 ? "\(shown) and \(more) more" : shown
    }
}

// MARK: - Achievements (W29; "a crap ton" more, Oct 27): badges from the bet history, worked out on every view, never
// stored. Ported from web/lib/achievements.ts: **change both together.** Nothing here rewards betting more: no badge
// counts bets placed or stakes; they're about winning, hitting legs, trying markets and books, and beating the close.

struct Badge: Identifiable {
    let id: String, icon: String, title: String, how: String, group: String
    var earned: String?             // the Eastern day it was earned
    var by: MyBet?
    var progress: (have: Int, need: Int)?
}

enum Achievements {
    static let groups = ["Milestones", "Long shots", "Parlays", "Sports", "Legs", "Books and promos", "Sharp", "Days and runs"]

    typealias Hit = (by: MyBet?, have: Int?, need: Int?)
    private typealias Test = ([MyBet]) -> Hit
    private static func won(_ b: MyBet) -> Bool { BetMath.status(b) == "won" }
    private static func lost(_ b: MyBet) -> Bool { BetMath.status(b) == "lost" }
    private static func price(_ b: MyBet) -> Double { b.price ?? 0 }
    private static func games(_ b: MyBet) -> Int {
        Set((b.games?.array ?? []).map { g in g["gameRef"].string ?? g["game_ref"].string ?? g["matchup"].string ?? "" }).count
    }
    private static func clv(_ b: MyBet) -> Double { BetMath.personalClv(b) ?? 0 }

    /// The first bet meeting `f`, in settled order.
    private static func first(_ f: @escaping (MyBet) -> Bool) -> Test { { bets in (bets.first(where: f), nil, nil) } }
    /// The bet that brings a count to `need`, with progress.
    private static func count(_ need: Int, _ f: @escaping (MyBet) -> Bool) -> Test {
        { bets in
            var have = 0
            for b in bets where f(b) { have += 1; if have == need { return (b, have, need) } }
            return (nil, have, need)
        }
    }
    /// The bet that makes the distinct values of `key` (over bets meeting `f`) reach `need`.
    private static func distinct(_ need: Int, _ f: @escaping (MyBet) -> Bool, _ key: @escaping (MyBet) -> String) -> Test {
        { bets in
            var seen: Set<String> = []
            for b in bets where f(b) { seen.insert(key(b)); if seen.count == need { return (b, need, need) } }
            return (nil, seen.count, need)
        }
    }
    /// `need` wins in a row (a loss breaks it; voids and cash-outs neither extend nor break it).
    private static func run(_ need: Int) -> Test {
        { bets in
            var n = 0, best = 0
            for b in bets {
                if won(b) { n += 1; best = max(best, n); if n == need { return (b, need, need) } } else if lost(b) { n = 0 }
            }
            return (nil, best, need)
        }
    }
    /// Up `need` units overall at some point.
    private static func up(_ need: Int) -> Test {
        { bets in
            var total = 0.0, best = 0.0
            for b in bets { total += BetMath.profit(b) ?? 0; best = max(best, total); if total >= Double(need) { return (b, need, need) } }
            return (nil, max(0, Int(best.rounded(.down))), need)
        }
    }

    // ---- legs: each leg with its graded result (a single takes the bet's own), as the share card and player cards read them
    struct Leg { let label: String; let result: String; let value: Double? }   // won, lost, void, open
    static func legsWithResults(_ b: MyBet) -> [Leg] {
        let labels = !(b.legs ?? []).isEmpty ? b.legs! : b.label.map { [$0] } ?? []
        let results = b.legResults ?? []
        var used: Set<Int> = []
        let s = BetMath.status(b)
        return labels.map { l in
            let i = results.indices.first { !used.contains($0) && results[$0].leg == l }
            if let i { used.insert(i) }
            let r = i.map { results[$0] }
            let res = r?.result == "won" || r?.result == "lost" ? r!.result : r?.result == "void" || r?.result == "push" ? "void"
                : labels.count == 1 && (s == "won" || s == "lost") ? s : "open"
            return Leg(label: l, result: res, value: r?.value)
        }
    }
    private static func oneLegShort(_ b: MyBet) -> Bool {
        let l = legsWithResults(b)
        return l.filter { $0.result == "lost" }.count == 1 && l.allSatisfy { $0.result != "open" }
    }
    nonisolated(unsafe) private static var compiled: [String: NSRegularExpression] = [:]    // the main actor's: views only
    private static func match(_ s: String, _ re: String) -> [String]? {
        if compiled[re] == nil { compiled[re] = try? NSRegularExpression(pattern: re, options: .caseInsensitive) }
        guard let r = compiled[re],
              let m = r.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)) else { return nil }
        return (0..<m.numberOfRanges).map { i in Range(m.range(at: i), in: s).map { String(s[$0]) } ?? "" }
    }
    /// The bet that brings the count of won legs matching `re` (and `min`: the line it needed, 300 for "300+") to `need`.
    private static func legs(_ need: Int, _ re: String, _ min: Double = 0) -> Test {
        { bets in
            var have = 0
            for b in bets {
                for l in legsWithResults(b) where l.result == "won" && match(l.label, re) != nil {
                    let plus = match(l.label, #"(\d+(?:\.\d+)?)\+"#)?[1], over = match(l.label, #"over (\d+(?:\.\d+)?)"#)?[1]
                    let line = plus.flatMap(Double.init) ?? over.flatMap(Double.init).map { $0.rounded(.up) } ?? 0   // "over 299.5" is 300+
                    if line >= min { have += 1; if have == need { return (b, have, need) } }
                }
            }
            return (nil, have, need)
        }
    }
    private static func wonLegs(_ need: Int) -> Test { legs(need, ".") }

    // ---- days, weeks and months (Eastern game days)
    private static let utc: Calendar = { var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(identifier: "UTC")!; return c }()
    private static let ymd: DateFormatter = {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = TimeZone(identifier: "UTC"); f.dateFormat = "yyyy-MM-dd"; return f
    }()
    private static func noon(_ d: String) -> Date? { Models.date(d + "T12:00:00Z") }
    private static func shift(_ d: String, _ days: Int) -> String { noon(d).map { ymd.string(from: utc.date(byAdding: .day, value: days, to: $0)!) } ?? d }
    private static func etHour(_ iso: String) -> Int? {
        guard let d = Models.date(iso) else { return nil }
        var c = Calendar(identifier: .gregorian); c.timeZone = Fmt.et
        return c.component(.hour, from: d)
    }
    private static func weekOf(_ b: MyBet) -> String {
        let d = BetMath.day(b)
        guard let n = noon(d) else { return d }
        return shift(d, -((utc.component(.weekday, from: n) - 1 + 6) % 7))
    }
    private struct Span { var n = 0, won = 0, lost = 0; var units = 0.0; var last: MyBet }
    /// Spans in the order first seen.
    private static func spans(_ bets: [MyBet], _ key: (MyBet) -> String) -> [(String, Span)] {
        var order: [String] = [], by: [String: Span] = [:]
        for b in bets {
            let k = key(b)
            if by[k] == nil { order.append(k); by[k] = Span(last: b) }
            by[k]!.n += 1; by[k]!.units += BetMath.profit(b) ?? 0; by[k]!.last = b
            if won(b) { by[k]!.won += 1 }; if lost(b) { by[k]!.lost += 1 }
        }
        return order.map { ($0, by[$0]!) }
    }
    /// A finished span (a week, a month) that meets `f`; the bet that closed it. `ends`: the span's last day from its key.
    private static func span(_ key: @escaping (MyBet) -> String, _ ends: @escaping (String) -> String, _ f: @escaping (Span) -> Bool) -> Test {
        { bets in
            let today = ymd.string(from: Date())
            for (k, s) in spans(bets, key) where ends(k) < today && f(s) { return (s.last, nil, nil) }
            return (nil, nil, nil)
        }
    }
    private static func monthEnd(_ k: String) -> String {
        guard let d = noon(k + "-01"), let next = utc.date(byAdding: .month, value: 1, to: d) else { return k }
        return ymd.string(from: utc.date(byAdding: .day, value: -1, to: next)!)
    }
    /// A day (all of a day's bets) that meets `f`.
    private static func day(_ f: @escaping (Span) -> Bool) -> Test {
        { bets in
            for (_, s) in spans(bets, BetMath.day) where f(s) { return (s.last, nil, nil) }
            return (nil, nil, nil)
        }
    }
    /// Days in a row with a winning bet.
    private static func winDays(_ need: Int) -> Test {
        { bets in
            let wins = bets.filter(won)
            let days = Set(wins.map(BetMath.day)).sorted()
            var n = 0, best = 0
            for (i, d) in days.enumerated() {
                n = i > 0 && shift(days[i - 1], 1) == d ? n + 1 : 1
                best = max(best, n)
                if n == need { return (wins.first { BetMath.day($0) == d }, need, need) }
            }
            return (nil, best, need)
        }
    }

    private static func sport(_ s: String) -> (MyBet) -> Bool { { won($0) && Stats.sportOf($0) == s } }
    private static func realSport(_ b: MyBet) -> Bool { Stats.sportOf(b) != "Multi-sport" && Stats.sportOf(b) != "Other" }
    private static func boosted(_ b: MyBet) -> Bool { (b.boost ?? 0) > 0 }

    private typealias Def = (id: String, group: String, icon: String, title: String, how: String, test: Test)
    private static let defs: [Def] = [
        // ---- Milestones
        ("first-win", "Milestones", "🎯", "On the board", "Win your first bet", first(won)),
        ("wins-10", "Milestones", "🔟", "Ten-piece", "Win 10 bets", count(10, won)),
        ("wins-25", "Milestones", "🥉", "Quarter century", "Win 25 bets", count(25, won)),
        ("wins-50", "Milestones", "🥈", "Half century", "Win 50 bets", count(50, won)),
        ("wins-100", "Milestones", "🥇", "Centurion", "Win 100 bets", count(100, won)),
        ("up-ten", "Milestones", "🏔️", "Double digits", "Be up 10 units overall", up(10)),
        ("up-25", "Milestones", "🗻", "Quarter stack", "Be up 25 units overall", up(25)),
        ("up-50", "Milestones", "🚁", "Fifty up", "Be up 50 units overall", up(50)),
        ("up-100", "Milestones", "🛰️", "Triple digits", "Be up 100 units overall", up(100)),
        ("comeback", "Milestones", "🔄", "Comeback kid", "Get back above zero after being down 5 units", { bets in
            var total = 0.0, low = 0.0
            for b in bets { total += BetMath.profit(b) ?? 0; low = min(low, total); if low <= -5 && total > 0 { return (b, nil, nil) } }
            return (nil, nil, nil)
        }),
        ("big-win", "Milestones", "💰", "Big score", "Win 10 units or more on one bet", first { (BetMath.profit($0) ?? 0) >= 10 }),
        ("huge-win", "Milestones", "🏦", "Bank job", "Win 25 units or more on one bet", first { (BetMath.profit($0) ?? 0) >= 25 }),

        // ---- Long shots
        ("dog-day", "Long shots", "🐶", "Dog day", "Win a bet at +200 or longer", first { won($0) && price($0) >= 200 }),
        ("long-shot", "Long shots", "🚀", "Long shot", "Win a bet at +500 or longer", first { won($0) && price($0) >= 500 }),
        ("four-figures", "Long shots", "💎", "Four figures", "Win a bet at +1000 or longer", first { won($0) && price($0) >= 1000 }),
        ("moonshot", "Long shots", "🌙", "Moonshot", "Win a bet at +2500 or longer", first { won($0) && price($0) >= 2500 }),
        ("lottery", "Long shots", "🎰", "Lottery ticket", "Win a bet at +5000 or longer", first { won($0) && price($0) >= 5000 }),
        ("unicorn", "Long shots", "🦄", "Unicorn", "Win a bet at +10000 or longer", first { won($0) && price($0) >= 10000 }),
        ("dog-pack", "Long shots", "🐺", "Dog pack", "Win 5 bets at +300 or longer", count(5) { won($0) && price($0) >= 300 }),
        ("chalk", "Long shots", "🧱", "Chalk eater", "Win 5 bets at -200 or shorter", count(5) { won($0) && price($0) <= -200 }),
        ("coin-flip", "Long shots", "🪙", "Coin flip", "Win a bet at even money (+100)", first { won($0) && price($0) == 100 }),
        ("lucky-sevens", "Long shots", "7️⃣", "Lucky sevens", "Win a bet priced +777 or +7777", first { won($0) && (price($0) == 777 || price($0) == 7777) }),

        // ---- Parlays
        ("two-step", "Parlays", "✌️", "Two-step", "Hit a 2-leg parlay", first { won($0) && Stats.legsOf($0) == 2 }),
        ("three-peat", "Parlays", "🔺", "Three-peat", "Hit a parlay with 3 or more legs", first { won($0) && Stats.legsOf($0) >= 3 }),
        ("five-legs", "Parlays", "🖐️", "Five alive", "Hit a parlay with 5 or more legs", first { won($0) && Stats.legsOf($0) >= 5 }),
        ("eight-legs", "Parlays", "🎱", "Eight ball", "Hit a parlay with 8 or more legs", first { won($0) && Stats.legsOf($0) >= 8 }),
        ("ten-legs", "Parlays", "🐙", "Octopus and then some", "Hit a parlay with 10 or more legs", first { won($0) && Stats.legsOf($0) >= 10 }),
        ("parlays-5", "Parlays", "🧩", "Puzzle master", "Hit 5 parlays", count(5) { won($0) && Stats.legsOf($0) > 1 }),
        ("parlays-20", "Parlays", "🏗️", "Parlay architect", "Hit 20 parlays", count(20) { won($0) && Stats.legsOf($0) > 1 }),
        ("cross-country", "Parlays", "🗺️", "Cross-country", "Hit a parlay across 3 or more games", first { won($0) && games($0) >= 3 }),
        ("mixtape", "Parlays", "📼", "Mixtape", "Hit a parlay that mixes sports", first { won($0) && Stats.sportOf($0) == "Multi-sport" }),
        ("sgp-hero", "Parlays", "🎬", "Same-game hero", "Hit a 4+ leg parlay on one game", first { won($0) && Stats.legsOf($0) >= 4 && games($0) <= 1 }),
        ("heartbreak", "Parlays", "💔", "Heartbreaker", "Lose a 4+ leg parlay by one leg (it happens)", first { lost($0) && Stats.legsOf($0) >= 4 && oneLegShort($0) }),
        ("agony", "Parlays", "😩", "Agony", "Lose 3 parlays by one leg", count(3) { lost($0) && Stats.legsOf($0) >= 2 && oneLegShort($0) }),

        // ---- Sports
        ("gridiron", "Sports", "🏈", "Gridiron", "Win an NFL bet", first(sport("NFL"))),
        ("campus", "Sports", "🎓", "Campus", "Win a college football bet", first(sport("College football"))),
        ("buckets", "Sports", "🏀", "Buckets", "Win an NBA bet", first(sport("NBA"))),
        ("march", "Sports", "🏆", "Ready for March", "Win a college basketball bet", first(sport("College basketball"))),
        ("biscuit", "Sports", "🏒", "Biscuit in the basket", "Win an NHL bet", first(sport("NHL"))),
        ("golazo", "Sports", "⚽", "Golazo", "Win a soccer bet", first(sport("Soccer"))),
        ("fight-night", "Sports", "🥊", "Fight night", "Win a UFC bet", first(sport("UFC"))),
        ("all-rounder", "Sports", "🌎", "All-rounder", "Win bets in 4 different sports", distinct(4, { won($0) && realSport($0) }, Stats.sportOf)),
        ("globetrotter", "Sports", "✈️", "Globetrotter", "Win bets in 6 different sports", distinct(6, { won($0) && realSport($0) }, Stats.sportOf)),
        ("specialist", "Sports", "🔬", "Specialist", "Win 15 bets in one sport", { bets in
            var by: [String: Int] = [:]
            for b in bets where won(b) && realSport(b) {
                let n = by[Stats.sportOf(b), default: 0] + 1; by[Stats.sportOf(b)] = n
                if n == 15 { return (b, 15, 15) }
            }
            return (nil, by.values.max() ?? 0, 15)
        }),

        // ---- Legs
        ("legs-25", "Legs", "🦵", "Leg day", "Hit 25 legs", wonLegs(25)),
        ("legs-100", "Legs", "🦿", "Never skip leg day", "Hit 100 legs", wonLegs(100)),
        ("legs-250", "Legs", "🐛", "Centipede", "Hit 250 legs", wonLegs(250)),
        ("td", "Legs", "🙌", "Six points", "Hit an anytime TD leg", legs(1, "anytime TD")),
        ("td-10", "Legs", "🏟️", "End zone regular", "Hit 10 anytime TD legs", legs(10, "anytime TD")),
        ("air-raid", "Legs", "🛩️", "Air raid", "Hit a 300+ passing yards leg", legs(1, "passing yds", 300)),
        ("ground", "Legs", "🚜", "Ground and pound", "Hit a 100+ rushing yards leg", legs(1, "rushing yds", 100)),
        ("deep-threat", "Legs", "🎣", "Deep threat", "Hit a 100+ receiving yards leg", legs(1, "receiving yds", 100)),
        ("splash", "Legs", "💦", "Splash", "Hit a 4+ threes leg", legs(1, "threes", 4)),
        ("thirty-piece", "Legs", "💯", "Thirty-piece", "Hit a 30+ points leg", legs(1, #"\bpoints\b"#, 30)),
        ("double-double", "Legs", "✖️", "Double-double", "Hit a double-double leg", legs(1, "double.double")),
        ("goal", "Legs", "🥅", "Goal!", "Hit a goalscorer leg", legs(1, #"goals?\b|goalscorer|to score"#)),
        ("shots", "Legs", "🏹", "Trigger happy", "Hit 10 shots legs (soccer or hockey)", legs(10, #"\bshots\b"#)),

        // ---- Books and promos
        ("line-shopper", "Books and promos", "🛒", "Line shopper", "Win at 2 different books", distinct(2, won, BetMath.book)),
        ("three-books", "Books and promos", "🏬", "Mall rat", "Win at FanDuel, DraftKings and Novig", distinct(3, won, BetMath.book)),
        ("exchange", "Books and promos", "🔁", "Exchange trader", "Win a bet at Novig", first { won($0) && BetMath.book($0) == "Novig" }),
        ("free-money", "Books and promos", "🎁", "Free money", "Cash a bonus bet", first { won($0) && $0.isBonus }),
        ("bonus-5", "Books and promos", "🎀", "Bonus baron", "Cash 5 bonus bets", count(5) { won($0) && $0.isBonus }),
        ("bonus-big", "Books and promos", "🎉", "House money", "Turn a bonus bet into 10 units or more", first { $0.isBonus && (BetMath.profit($0) ?? 0) >= 10 }),
        ("boosted", "Books and promos", "⚡", "Boosted", "Win a profit-boosted bet", first { won($0) && boosted($0) }),
        ("boost-5", "Books and promos", "🔋", "Supercharged", "Win 5 profit-boosted bets", count(5) { won($0) && boosted($0) }),
        ("protected", "Books and promos", "🛡️", "Insured", "Win a Bet Protect+ bet", first { won($0) && $0.protect == true }),
        ("cash-out", "Books and promos", "💸", "Take the money", "Cash out a bet for a profit", first { $0.cashout != nil && (BetMath.profit($0) ?? 0) > 0 }),
        ("ladder", "Books and promos", "🪜", "First rung", "Win a ladder step", first { won($0) && !($0.ladderId ?? "").isEmpty }),
        ("ladder-3", "Books and promos", "🧗", "Climber", "Win 3 ladder steps", count(3) { won($0) && !($0.ladderId ?? "").isEmpty }),

        // ---- Sharp
        ("first-clv", "Sharp", "📐", "Ahead of the market", "Beat the closing line once", first { clv($0) > 0 }),
        ("sharp", "Sharp", "🔪", "Sharp", "Beat the closing line on 10 bets", count(10) { clv($0) > 0 }),
        ("closer", "Sharp", "🗝️", "Closer", "Beat the closing line on 25 bets", count(25) { clv($0) > 0 }),
        ("wiseguy", "Sharp", "🕶️", "Wiseguy", "Beat the closing line on 50 bets", count(50) { clv($0) > 0 }),
        ("steam", "Sharp", "♨️", "Steam chaser", "Beat the close by 5% or more on one bet", first { clv($0) >= 0.05 }),
        ("sharp-week", "Sharp", "🧠", "Sharp week", "Beat the close on 5 bets in one Monday-to-Sunday week", { bets in
            var by: [String: Int] = [:]
            for b in bets where clv(b) > 0 { let n = by[weekOf(b), default: 0] + 1; by[weekOf(b)] = n; if n == 5 { return (b, nil, nil) } }
            return (nil, nil, nil)
        }),

        // ---- Days and runs
        ("hat-trick", "Days and runs", "🎩", "Hat trick", "Win 3 bets in a row", run(3)),
        ("on-fire", "Days and runs", "🔥", "On fire", "Win 5 bets in a row", run(5)),
        ("unstoppable", "Days and runs", "🌋", "Unstoppable", "Win 10 bets in a row", run(10)),
        ("bounce-back", "Days and runs", "🪃", "Bounce back", "Win right after losing 3 in a row", { bets in
            var losses = 0
            for b in bets { if lost(b) { losses += 1 } else if won(b) { if losses >= 3 { return (b, nil, nil) }; losses = 0 } }
            return (nil, nil, nil)
        }),
        ("perfect-day", "Days and runs", "✨", "Perfect day", "Win every bet on a day with 3 or more", day { $0.n >= 3 && $0.won == $0.n }),
        ("big-day", "Days and runs", "☀️", "Big day", "Finish a day up 5 units", day { $0.units >= 5 }),
        ("monster-day", "Days and runs", "👹", "Monster day", "Finish a day up 10 units", day { $0.units >= 10 }),
        ("green-week", "Days and runs", "📈", "Green week", "Finish a Monday-to-Sunday week up, with 5+ bets settled",
         span(weekOf, { shift($0, 6) }, { $0.n >= 5 && $0.units > 0 })),
        ("green-month", "Days and runs", "🗓️", "Green month", "Finish a calendar month up, with 10+ bets settled",
         span({ String(BetMath.day($0).prefix(7)) }, monthEnd, { $0.n >= 10 && $0.units > 0 })),
        ("win-days-3", "Days and runs", "📆", "Three-day run", "Win a bet 3 days in a row", winDays(3)),
        ("win-days-7", "Days and runs", "🗞️", "Daily news", "Win a bet 7 days in a row", winDays(7)),
        ("weekend", "Days and runs", "🎊", "Weekend warrior", "Win on a Saturday and the Sunday after it", { bets in
            let wins = bets.filter(won), days = Set(wins.map(BetMath.day))
            for b in wins {
                let d = BetMath.day(b)
                guard let n = noon(d), utc.component(.weekday, from: n) == 1 else { continue }
                if days.contains(shift(d, -1)) { return (b, nil, nil) }
            }
            return (nil, nil, nil)
        }),
        ("early-bird", "Days and runs", "🐦", "Early bird", "Win a bet on a game that starts before noon ET",
         first { won($0) && BetMath.start($0).flatMap(etHour).map { $0 < 12 } == true }),
        ("night-owl", "Days and runs", "🦉", "Night owl", "Win a bet on a game that starts at 10 PM ET or later",
         first { won($0) && BetMath.start($0).flatMap(etHour).map { $0 >= 22 } == true }),
    ]
    static var ids: [String] { defs.map(\.id) }
    static var icons: [String] { defs.map(\.icon) }

    /// Every badge, earned first (newest first), then the locked ones in list order.
    static func all(_ bets: [MyBet]) -> [Badge] {
        let done = Stats.chrono(bets)
        let list = defs.map { d -> Badge in
            let r = d.test(done)
            return Badge(id: d.id, icon: d.icon, title: d.title, how: d.how, group: d.group, earned: r.by.map(BetMath.day), by: r.by,
                         progress: r.need != nil && r.by == nil ? (r.have ?? 0, r.need!) : nil)
        }
        let got = list.filter { $0.earned != nil }.enumerated().sorted { a, b in
            a.element.earned! != b.element.earned! ? a.element.earned! > b.element.earned! : a.offset < b.offset
        }.map(\.element)
        return got + list.filter { $0.earned == nil }
    }

    /// The locked badges closest to done (by progress), for "Next up".
    static func nextUp(_ badges: [Badge], _ n: Int = 6) -> [Badge] {
        let open = badges.enumerated().filter { $0.element.earned == nil && ($0.element.progress?.have ?? 0) > 0 }
        return open.sorted { a, b in
            let pa = a.element.progress!, pb = b.element.progress!
            let fa = Double(pa.have) / Double(pa.need), fb = Double(pb.have) / Double(pb.need)
            return fa != fb ? fa > fb : pa.need != pb.need ? pa.need < pb.need : a.offset < b.offset
        }.prefix(n).map(\.element)
    }
}

// MARK: - Share cards (W13): a bet as a picture to send. A parlay that lost by one leg says so: the brutal ones are worth
// sharing too. ShareCardView draws it.

struct ShareCard: Equatable {
    struct Leg: Equatable { let label: String; let result: String; let value: String? }   // won, lost, void, open
    let status: String, tone: String, title: String, price: String
    let legs: [Leg]
    let more: Int
    let headline: String, detail: String, book: String, when: String

    static let maxLegs = 10

    static func of(_ b: MyBet) -> ShareCard {
        let s = BetMath.status(b), settled = BetMath.isSettled(b), p = BetMath.profit(b)
        let results = b.legResults ?? []
        let labels = !(b.legs ?? []).isEmpty ? b.legs! : b.label.map { [$0] } ?? []
        var used: Set<Int> = []
        let legs: [Leg] = labels.map { l in
            let i = results.indices.first { !used.contains($0) && results[$0].leg == l }    // repeated labels ("Over 2.5 goals") in order
            if let i { used.insert(i) }
            let r = i.map { results[$0] }
            let res = r?.result == "won" || r?.result == "lost" ? r!.result : r?.result == "void" || r?.result == "push" ? "void"
                : settled && labels.count == 1 && (s == "won" || s == "lost") ? s : "open"
            return Leg(label: Fmt.label(l), result: res, value: r?.shown)
        }
        let lost = legs.filter { $0.result == "lost" }.count
        let oneAway = s == "lost" && legs.count > 1 && lost == 1 && legs.allSatisfy { $0.result != "open" }
        let stake = BetMath.stake(b), boost = b.boost ?? 0
        let toWin = b.price.map { stake * ($0 > 0 ? $0 / 100 : 100 / -$0) * (1 + boost / 100) }
        let u = { (x: Double) in "\(x >= 0 ? "+" : Fmt.minus)\(String(format: "%.2f", abs(x)))u" }
        let tone = s == "won" ? "win" : s == "lost" ? "loss" : settled ? "even" : "open"
        let status = s == "won" ? "WON" : s == "lost" ? (oneAway ? "ONE LEG AWAY" : "LOST") : s == "cashout" ? "CASHED OUT" : settled ? s.uppercased() : "OPEN"
        let st = Live.js(stake)
        let money = b.isBonus ? "\(st)u bonus bet" : "\(st)u\(boost > 0 ? " · \(Live.js(boost))% boost" : "")"
        let price = b.price.map { pr in
            Fmt.am(pr) + (boost > 0 ? " → " + Fmt.am((pr > 0 ? pr * (1 + boost / 100) : (100 / -pr) * (1 + boost / 100) * 100).rounded()) : "")
        } ?? ""
        let f = DateFormatter(); f.timeZone = Fmt.et; f.dateFormat = "MMM d, yyyy"
        return ShareCard(status: status, tone: tone, title: Stats.betName(legs: labels, label: nil, price: nil, n: labels.count), price: price,
                         legs: Array(legs.prefix(maxLegs)), more: max(0, legs.count - maxLegs),
                         headline: settled && p != nil ? u(p!) : toWin.map { "to win " + String(u($0).dropFirst()) } ?? "",
                         detail: oneAway ? "\(legs.count - 1) of \(legs.count) hit · \(money)" : money,
                         book: BetMath.book(b), when: f.string(from: Models.date(b.placedAt) ?? Date()))
    }
}
