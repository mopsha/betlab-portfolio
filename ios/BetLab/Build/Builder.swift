import Foundation

// Build your own parlay, ported from web/lib/builder.ts (change both together). Each game's legs come with a
// sample of simulated games as bitsets (leg_packs): a parlay's chance is the share of draws where every leg hits,
// scaled by each leg's market-fair chance. The grade compares the book's price with what parlays like it usually
// pay, then checks each leg's price, whether the legs help each other, and Mike's own rules.

struct PackLeg: Decodable, Hashable {
    var label: String
    var player: String? = nil
    var team: String? = nil
    var stat: String? = nil
    var side: String? = nil
    var point: Double? = nil
    var price: Double
    var p: Double
    var pPack: Double
    var source: String? = nil
    var bits: String? = nil
    var not: String? = nil
    var link: String? = nil
    var linkMain: Bool? = nil       // the link follows the main line, which can move (Build.mainLineText)
    var dkPrice: Double? = nil
    var dkLink: String? = nil
    var dkMoved: Bool? = nil
    var dkLinkMain: Bool? = nil
    var nvId: String? = nil         // Novig's outcome id (Oct 28, novig_parlays.attach)
    var nvPrice: Double? = nil      // Novig's price for the leg alone, when $50+ stands behind it
    var unavailable = false

    enum CodingKeys: String, CodingKey {
        case label, player, team, stat, side, point, price, p, pPack, source, bits, not, link, linkMain, dkPrice, dkLink, dkMoved, dkLinkMain, nvId, nvPrice
    }
}

struct Pack {
    let eventId: String
    let matchup: String
    let commenceTime: String
    let gameRef: String?
    let sport: String
    let draws: Int
    let legs: [String: PackLeg]
}

/// One part of a game's pack (`leg_packs.body`); big packs come in parts, merged by `Pack.merge`.
struct PackPart: Decodable {
    let eventId: String?
    let matchup: String?
    let commenceTime: String?
    let gameRef: String?
    let sport: String?
    let draws: Double?
    let part: Double?
    let legs: [PackLeg]?

    enum CodingKeys: String, CodingKey { case eventId, matchup, commenceTime, gameRef, sport, draws, part, legs }
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        eventId = (try? c.decode(String.self, forKey: .eventId)) ?? (try? c.decode(Double.self, forKey: .eventId)).map { String(Int($0)) }
        matchup = try? c.decode(String.self, forKey: .matchup)
        commenceTime = try? c.decode(String.self, forKey: .commenceTime)
        gameRef = try? c.decode(String.self, forKey: .gameRef)
        sport = try? c.decode(String.self, forKey: .sport)
        draws = try? c.decode(Double.self, forKey: .draws)
        part = try? c.decode(Double.self, forKey: .part)
        // a leg the app can't read (a missing price) is skipped, not the whole game
        legs = (try? c.decode([Failable<PackLeg>].self, forKey: .legs))?.compactMap(\.value)
    }
}

extension Pack {
    static func merge(_ parts: [PackPart]) -> Pack? {
        guard !parts.isEmpty else { return nil }
        let first = parts.first { ($0.part ?? 1) == 1 } ?? parts[0]
        var legs: [String: PackLeg] = [:]
        for p in parts { for l in p.legs ?? [] { legs[l.label] = l } }
        return Pack(eventId: first.eventId ?? "", matchup: first.matchup ?? "", commenceTime: first.commenceTime ?? "",
                    gameRef: first.gameRef, sport: first.sport ?? "nfl", draws: Int(first.draws ?? 0), legs: legs)
    }
}

struct Failable<T: Decodable>: Decodable {
    let value: T?
    init(from d: Decoder) throws { value = try? T(from: d) }
}

struct PackGame: Identifiable, Hashable {
    let eventId: String
    let matchup: String
    let commenceTime: String
    let sport: String
    var id: String { eventId }
}

struct Band: Decodable { let maxFair: Double?; let ratio: Double }

/// FanDuel's SGP pricing (fun_ledger.quote_model): log(quote / fair payout) from fair odds, legs, cross-game, leg prices.
struct QuoteModel: Decodable {
    struct Coef: Decodable { let intercept: Double; let logFair: Double; let legs: Double; let crossGame: Double; let naiveGap: Double }
    let coef: Coef
    let rmse: Double?
    func ratio(fairDec: Double, naiveDec: Double, legs: Int, crossGame: Bool) -> Double {
        exp(coef.intercept + coef.logFair * log(fairDec) + coef.legs * Double(legs) + coef.crossGame * (crossGame ? 1 : 0)
            + coef.naiveGap * log(naiveDec / fairDec))
    }
}

struct SlipLeg: Codable, Hashable { let eventId: String; let label: String }

enum BuildBook: String, CaseIterable, Identifiable {
    case fanduel = "FanDuel", draftkings = "DraftKings", novig = "Novig"     // Novig from Oct 28
    var id: String { rawValue }
}

extension BuildBook {
    /// The books the signed-in account has on (BooksOff, Nov 6): Build prices, links and saves at these only.
    static var mine: [BuildBook] { allCases.filter { BooksOff.mine.contains($0.rawValue) } }
}

enum Odds {
    static func dec(_ a: Double) -> Double { a > 0 ? 1 + a / 100 : 1 + 100 / -a }
    static func am(_ d: Double) -> Double { d >= 2 ? (d - 1) * 100 : -100 / (d - 1) }
}

final class Pricer {
    private var cache: [String: [UInt8]] = [:]
    let packs: [String: Pack]
    let book: BuildBook
    private static let pop: [UInt8] = (0..<256).map { UInt8($0.nonzeroBitCount) }

    init(_ packs: [String: Pack], book: BuildBook = .fanduel) { self.packs = packs; self.book = book }

    func pack(_ eid: String) -> Pack? { packs[eid] }

    /// At DraftKings a leg it doesn't post at this exact number is unavailable (a moved rung is a different bet). At
    /// Novig a leg is there when Novig lists it, at Novig's price when $50+ stands behind it, else its fair price (web).
    func leg(_ eid: String, _ label: String) -> PackLeg? {
        guard var l = packs[eid]?.legs[label] else { return nil }
        if book == .fanduel { return l }
        if book == .novig {
            if let id = l.nvId { l.price = l.nvPrice ?? Odds.am(1 / l.p).rounded(); l.link = "https://novig.com/events/\(id)/oddsapi/5"; l.linkMain = nil }
            else { l.price = .nan; l.link = nil; l.unavailable = true }
            return l
        }
        if let dp = l.dkPrice, l.dkMoved != true { l.price = dp; l.link = l.dkLink; l.linkMain = l.dkLinkMain }
        else { l.price = .nan; l.link = nil; l.unavailable = true }
        return l
    }

    /// The slip's Novig outcome ids, in order; nil when a leg isn't on Novig.
    func novigIds(_ slip: [SlipLeg]) -> [String]? {
        let ids = slip.compactMap { packs[$0.eventId]?.legs[$0.label]?.nvId }
        return ids.count == slip.count ? ids : nil
    }

    private func bits(_ eid: String, _ label: String, depth: Int = 0) -> [UInt8]? {
        let key = eid + "|" + label
        if let hit = cache[key] { return hit }
        guard let l = leg(eid, label), depth <= 2 else { return nil }
        var b: [UInt8]?
        if let s = l.bits, let d = Data(base64Encoded: s) { b = [UInt8](d) }
        else if let n = l.not, let o = bits(eid, n, depth: depth + 1) { b = o.map { ~$0 } }
        if let b { cache[key] = b }
        return b
    }

    /// Joint fair chance of some legs of one game: the share of draws where all hit, times each leg's shrink.
    func joint(_ eid: String, _ labels: [String]) -> Double? {
        guard let pk = pack(eid), !labels.isEmpty, pk.draws > 0 else { return nil }
        let bs = labels.compactMap { bits(eid, $0) }
        guard bs.count == labels.count else { return nil }
        var n = 0
        for i in 0..<bs[0].count {
            var a: UInt8 = 255
            for b in bs { a &= i < b.count ? b[i] : 0 }
            n += Int(Self.pop[Int(a)])
        }
        let legs = labels.compactMap { pk.legs[$0] }
        let shrink = legs.reduce(1.0) { $0 * ($1.p / max($1.pPack, 1e-6)) }
        return min(Double(n) / Double(pk.draws) * shrink, legs.map(\.p).min() ?? 1)
    }
}

struct Evaluation {
    struct Fight { let a: String; let b: String; let lift: Double }
    let games: [String]
    let legs: [(slip: SlipLeg, leg: PackLeg)]
    let p: Double, indep: Double, lift: Double, naive: Double, fair: Double
    let worst: (label: String, v: Double)
    let fights: [Fight]
    let rules: [String]
    let typical: Double
    let typed: Double?
    let provisional: Bool
    let grade: String
    let idx: Int
    let why: String
    let notes: [String]
}

enum Build {
    static let grades = ["A+", "A", "A\u{2212}", "B+", "B", "B\u{2212}", "C", "D", "F"]
    /// FanDuel's usual payout share by fair price, until typed quotes replace it (fun_results).
    static let defaultBands = [Band(maxFair: 300, ratio: 0.78), Band(maxFair: 700, ratio: 0.79), Band(maxFair: 1500, ratio: 0.95), Band(maxFair: nil, ratio: 1.05)]
    private static let lines = ["moneyline", "spread", "total"]

    static func evaluate(_ pr: Pricer, _ slip: [SlipLeg], priceText: String, bands: [Band] = defaultBands, model: QuoteModel? = nil) -> Evaluation? {
        var byGame: [String: [String]] = [:]
        var order: [String] = []
        for l in slip { if byGame[l.eventId] == nil { order.append(l.eventId) }; byGame[l.eventId, default: []].append(l.label) }
        let games = order.filter { pr.pack($0) != nil }
        let legs = slip.compactMap { s in pr.leg(s.eventId, s.label).map { (slip: s, leg: $0) } }
        guard !legs.isEmpty, legs.count == slip.count, !legs.contains(where: { $0.leg.unavailable }) else { return nil }
        var p = 1.0
        for eid in games { guard let j = pr.joint(eid, byGame[eid]!) else { return nil }; p *= j }
        let indep = legs.reduce(1.0) { $0 * $1.leg.p }
        let naive = legs.reduce(1.0) { $0 * Odds.dec($1.leg.price) }
        let values = legs.map { (label: $0.slip.label, v: $0.leg.p * Odds.dec($0.leg.price)) }
        let worst = values.min { $0.v < $1.v }!
        var fights: [Evaluation.Fight] = []
        for eid in games {
            let ls = byGame[eid]!
            for i in 0..<ls.count { for k in (i + 1)..<ls.count {
                guard let a = pr.leg(eid, ls[i]), let b = pr.leg(eid, ls[k]) else { continue }
                let lift = (pr.joint(eid, [ls[i], ls[k]]) ?? a.p * b.p) / (a.p * b.p)
                if lift < 0.9 { fights.append(.init(a: ls[i], b: ls[k], lift: lift)) }
            } }
        }
        // Mike's rules (2026-09-24): 55-80% legs, unders only as near-locks, one leg per player.
        var rules: [String] = []
        let players = legs.compactMap(\.leg.player).filter { !$0.isEmpty }      // game lines have no player (web: l.player truthy)
        if let dup = players.enumerated().first(where: { i, x in players.firstIndex(of: x) != i })?.element {
            rules.append("two legs on \(dup) (books price those as nearly one bet)")
        }
        for (s, l) in legs {
            if l.side == "under" && (l.p < 0.75 || l.p > 0.92) { rules.append("\(s.label): unders only as near-locks (75–92%)") }
            else if l.side != "under" && (l.p < 0.55 || l.p > 0.8) && !lines.contains(l.stat ?? "") { rules.append("\(s.label): \(Fmt.pct(l.p)) (your legs are 55–80%)") }
        }
        let fair = Odds.am(1 / p)
        let band = bands.first { $0.maxFair == nil || fair <= $0.maxFair! } ?? bands[bands.count - 1]
        let typical = model.map { $0.ratio(fairDec: 1 / p, naiveDec: naive, legs: legs.count, crossGame: games.count > 1) } ?? band.ratio
        let typed = Marking.parseOdds(priceText)
        var idx: Int, why: String, provisional = false
        if let t = typed {
            let r = p * Odds.dec(t), rel = r / typical
            idx = rel >= 1.25 ? 0 : rel >= 1.15 ? 1 : rel >= 1.08 ? 2 : rel >= 1.03 ? 3 : rel >= 0.98 ? 4 : rel >= 0.93 ? 5 : rel >= 0.88 ? 6 : rel >= 0.8 ? 7 : 8
            why = "\(pr.book.rawValue) pays \(Int((r * 100).rounded()))% of fair; \(model != nil ? "a slip like this usually gets" : "parlays this size usually get") \(Int((typical * 100).rounded()))%. EV \(Fmt.signed(r - 1))."
        } else {
            let avg = values.reduce(0) { $0 + $1.v } / Double(values.count)
            idx = avg >= 1.0 ? 2 : avg >= 0.96 ? 3 : avg >= 0.93 ? 4 : avg >= 0.9 ? 5 : avg >= 0.86 ? 6 : 7
            why = pr.book == .novig ? "Asking Novig for its price…"
                : "Provisional, from the legs' own prices (\(Int((avg * 100).rounded()))% of fair on average). Type \(pr.book == .draftkings ? "DraftKings'" : "FanDuel's") price for the real grade."
            provisional = true
        }
        // Small, likely parlays are what the fun bucket is for (Mike, 2026-09-28); long shots are held down.
        var notes: [String] = []
        if p >= 0.25 { idx -= 1; notes.append("+1: \(Fmt.pct(p)) to hit. Small, likely parlays get a boost") }
        else if p < 0.04 { idx += 2; notes.append("\u{2212}2: \(Fmt.pct(p, 1)) to hit is a long shot (the grade tops out at B\u{2212})") }
        else if p < 0.1 { idx += 1; notes.append("\u{2212}1: \(Fmt.pct(p)) to hit is on the long side") }
        if legs.count >= 6 { idx += 1; notes.append("\u{2212}1: \(legs.count) legs (every leg adds FanDuel's margin)") }
        if let f = fights.first { idx += 1; notes.append("\u{2212}1: \(f.a) and \(f.b) work against each other (hit together \(String(format: "%.2f", f.lift))× as often as chance)") }
        if worst.v < 0.85 { idx += 1; notes.append("\u{2212}1: \(worst.label) is priced \(Int(((1 - worst.v) * 100).rounded()))% under fair: swap it if you can") }
        if p < 0.04 { idx = max(idx, grades.firstIndex(of: "B\u{2212}")!) }
        idx = max(0, min(idx, grades.count - 1))
        return Evaluation(games: games, legs: legs, p: p, indep: indep, lift: p / indep, naive: naive, fair: fair, worst: worst,
                          fights: fights, rules: rules, typical: typical, typed: typed, provisional: provisional,
                          grade: grades[idx], idx: idx, why: why, notes: notes)
    }

    /// A saved parlay's id: the old page's hash of the sorted labels (UTF-16 order, as JavaScript sorts), "~dk" at
    /// DraftKings, "~nv" at Novig. `day` (the slip's first game day, ET; Nov 9) goes into the hash, so the same legs built
    /// for another game are another slip, not the old settled bet (web buildId). Without it: the id slips had before.
    static func id(_ slip: [SlipLeg], book: BuildBook = .fanduel, day: String? = nil) -> String {
        let joined = slip.map(\.label).sorted { $0.utf16.lexicographicallyPrecedes($1.utf16) }.joined(separator: "|") + (day.map { "@" + $0 } ?? "")
        var h: UInt32 = 7
        for c in joined.utf16 { h = h &* 31 &+ UInt32(c) }
        return "custom-" + String(h, radix: 16) + (book == .draftkings ? "~dk" : book == .novig ? "~nv" : "")
    }

    /// The slip's first game day in Eastern time; today when no game says (web slipDay).
    static func day(_ pr: Pricer, _ slip: [SlipLeg], now: Date = Date()) -> String {
        let starts = slip.compactMap { pr.pack($0.eventId).flatMap { Models.date($0.commenceTime) } }
        return BetMath.etDay(starts.min() ?? now)
    }

    /// The id this slip goes under (web slipId): an open bet's old day-less id while that bet is open, so a placed slip
    /// keeps its id; otherwise the id with the slip's game day. `open`: whether an id is one of the account's open bets.
    static func slipId(_ pr: Pricer, _ slip: [SlipLeg], open: (String) -> Bool, now: Date = Date()) -> String {
        let legacy = id(slip, book: pr.book)
        return open(legacy) ? legacy : id(slip, book: pr.book, day: day(pr, slip, now: now))
    }

    /// The custom_parlays row a save writes (web customRow).
    static func row(_ pr: Pricer, _ slip: [SlipLeg], _ e: Evaluation, id sgpId: String? = nil) -> [String: Any?] {
        let games: [[String: Any?]] = e.games.map { eid in
            let pk = pr.pack(eid)!
            return ["matchup": pk.matchup, "event_id": eid, "game_ref": pk.gameRef, "legs": slip.filter { $0.eventId == eid }.map(\.label)]
        }
        let sports = Set(e.games.compactMap { pr.pack($0)?.sport })
        let names = e.games.compactMap { pr.pack($0)?.matchup }
        return ["sgp_id": sgpId ?? id(slip, book: pr.book), "price": e.typed, "fair_price": Int(e.fair.rounded()),
                "naive_price": Int(Odds.am(e.naive).rounded()), "p_fair": e.p, "n_legs": e.legs.count, "legs": e.legs.map(\.slip.label),
                "matchup": games.count > 1 ? "Your SGP+: \(names.joined(separator: ", "))" : names.first ?? "",
                "odds_event_id": games.count == 1 ? e.games[0] : nil, "games": games,
                "sport": sports.count == 1 ? sports.first! : "mixed", "grade": e.grade,
                "grade_parts": ["provisional": e.provisional, "typical": e.typical, "lift": (e.lift * 1000).rounded() / 1000,
                                "worst_leg": e.worst.label, "worst_value": (e.worst.v * 1000).rounded() / 1000,
                                "fights": e.fights.count, "rules": e.rules.count],
                "quoted_at": ISO8601DateFormatter().string(from: Date())]
    }

    struct GradeLine: Identifiable { let grade: String; var graded = 0, won = 0; var expected = 0.0, units = 0.0; var id: String { grade } }

    /// "Record by grade" for saved parlays (graded ones only).
    static func recordByGrade(_ rows: [Quote]) -> [GradeLine] {
        var by: [String: GradeLine] = [:]
        for r in rows where r.status == "won" || r.status == "lost" {
            let g = (r.grade?.isEmpty == false ? r.grade! : "?")
            var x = by[g] ?? GradeLine(grade: g)
            x.graded += 1; x.won += r.status == "won" ? 1 : 0; x.expected += r.pFair ?? 0; x.units += r.profit1u ?? 0
            by[g] = x
        }
        return by.values.sorted { (grades.firstIndex(of: $0.grade) ?? 99) < (grades.firstIndex(of: $1.grade) ?? 99) }
    }

    /// One "Open in" link for the slip: FanDuel's addToBetslip with every leg, or DraftKings' outcome ids joined by %2B
    /// (only when every leg has a DraftKings link) (web fanduel.ts fdHref, draftkings.ts dkHref).
    /// Legs whose link is the book's main market, which keeps its id when its line moves, so the slip can open at a new
    /// number (Oct 30: Brunson's "over 1.5 threes" opened as Over 2.5): say to check them (web fanduel.mainLineText).
    static func mainLineText(_ flags: [Bool], book: String = "FanDuel") -> String? {
        let n = flags.filter { $0 }.count
        guard n > 0 else { return nil }
        let its = book.hasSuffix("s") ? "\(book)'" : "\(book)'s"
        return n == 1 && flags.count == 1
            ? "Check the number on \(its) slip: this link follows \(its) main line, which can move."
            : "Check the number on \(n) of these legs on \(its) slip: their links follow \(its) main line, which can move."
    }

    static func link(book: BuildBook, _ links: [String?]) -> String? {
        if book == .novig {                  // every leg's outcome id in one order-slip link (Oct 28)
            let ids = links.compactMap { l -> String? in
                guard let l, let r = l.range(of: #"(?<=novig\.com/events/)[^/?#]+"#, options: .regularExpression) else { return nil }
                return String(l[r])
            }
            return !ids.isEmpty && ids.count == links.count ? "https://novig.com/events/\(ids.joined(separator: ","))/oddsapi/5" : nil
        }
        if book == .draftkings {
            guard !links.isEmpty, links.allSatisfy({ $0?.contains("draftkings.com") == true }) else { return nil }
            if links.count == 1 { return links[0] }
            let ids = links.compactMap { URLComponents(string: $0!)?.queryItems?.first { $0.name == "outcomes" }?.value }
            guard ids.count == links.count else { return nil }
            return "https://sportsbook.draftkings.com/?outcomes=" + ids.map { $0.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(.init(charactersIn: "-_.~"))) ?? $0 }.joined(separator: "%2B")
        }
        let ok = links.compactMap { $0 }
        guard !ok.isEmpty else { return nil }
        // one link out of a parlay's legs would open as a single bet, which reads as a broken parlay (Nov 5: 1 of 8)
        if ok.count == 1 { return links.count == 1 ? FanDuel.nyLink(ok[0]) : nil }
        let parts = ok.enumerated().compactMap { i, u -> String? in
            guard let q = URLComponents(string: u)?.queryItems else { return nil }
            let enc = { (s: String?) in (s ?? "").addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? "" }
            return "marketId[\(i)]=\(enc(q.first { $0.name == "marketId" }?.value))&selectionId[\(i)]=\(enc(q.first { $0.name == "selectionId" }?.value))"
        }
        return "\(FanDuel.host)/addToBetslip?" + parts.joined(separator: "&")
    }
}

// MARK: - The leg board (Oct 22, web boardTabs)
// A sportsbook's SGP screen: a game's legs as market tabs (Game lines, then one per player stat), each market a set
// of rows of price buttons (Over | Under, away | draw | home, one spread rung per row).

struct BoardRow: Identifiable { let key: Double; let legs: [PackLeg]; var id: Double { key } }
struct BoardSection: Identifiable { let title: String; let sub: String?; let rows: [BoardRow]; var id: String { title } }
struct BoardTab: Identifiable { let key: String; let title: String; let count: Int; let sections: [BoardSection]; var id: String { key } }

extension Build {
    private static let statTitles = [
        "moneyline": "Moneyline", "draw": "Moneyline", "spread": "Spread", "puck line": "Puck line", "total": "Total", "goals": "Total goals",
        "btts": "Both teams to score", "double chance": "Double chance",
        "passing_yards": "Passing yds", "rushing_yards": "Rushing yds", "receiving_yards": "Receiving yds", "receptions": "Receptions",
        "tds": "Touchdowns", "shots": "Shots", "shots_on_target": "Shots on target", "points": "Points", "rebounds": "Rebounds",
        "assists": "Assists", "threes": "Threes", "pra": "Pts + reb + ast",
    ]
    private static let gameOrder = ["moneyline", "spread", "puck line", "total", "goals", "btts", "double chance"]
    private static let sides = ["over", "yes", "under", "no"]

    private static func cap(_ s: String) -> String { s.prefix(1).uppercased() + s.dropFirst() }
    private static func num(_ x: Double) -> String { String(format: "%g", x) }
    static func statTitle(_ s: String?) -> String {
        statTitles[s ?? ""] ?? cap((s ?? "Other").replacingOccurrences(of: "_", with: " "))
    }

    /// A leg's text on its button: the row says the market, so "Over 38.5", "Yes", "CLE +2.5", "Anytime TD".
    static func shortLeg(_ l: PackLeg) -> String {
        let side = l.side ?? ""
        if let who = l.player, !who.isEmpty {
            if side == "over" || side == "under", let pt = l.point { return "\(cap(side)) \(num(pt))" }
            let rest = l.label.hasPrefix(who) ? l.label.dropFirst(who.count).trimmingCharacters(in: .whitespaces) : l.label
            return cap(rest.isEmpty ? l.label : rest)
        }
        if l.stat == "btts" { return side == "no" ? "No" : "Yes" }
        if side == "over" || side == "under", let pt = l.point { return "\(cap(side)) \(num(pt))" }
        if l.stat == "moneyline" { return l.label.replacingOccurrences(of: #" (to win|ML)$"#, with: "", options: .regularExpression) }
        return l.label
    }

    /// A game's legs as the board's tabs. Team order follows the matchup ("Away @ Home"), the draw sits between.
    static func boardTabs(_ legs: [PackLeg], matchup: String = "") -> [BoardTab] {
        func index(_ s: String) -> Int? { matchup.range(of: s).map { matchup.distance(from: matchup.startIndex, to: $0.lowerBound) } }
        let atSign = index(" @ ")
        func at(_ l: PackLeg) -> Int { (l.team ?? "").isEmpty ? 10_000 : index(l.team!) ?? 10_000 }
        func away(_ l: PackLeg) -> Bool { atSign.map { at(l) < $0 } ?? true }
        func order(_ a: PackLeg, _ b: PackLeg) -> Bool {
            if a.stat == "draw" || b.stat == "draw" { return a.stat == "draw" ? !away(b) : away(a) }
            let s = (sides.firstIndex(of: a.side ?? "") ?? -1) - (sides.firstIndex(of: b.side ?? "") ?? -1)
            if s != 0 { return s < 0 }
            if at(a) != at(b) { return at(a) < at(b) }
            return a.label.localizedCompare(b.label) == .orderedAscending
        }
        // A spread rung pairs the away side with the home side's opposite number (BUF +1.5 with CBJ -1.5).
        func rung(_ l: PackLeg) -> Double {
            if l.stat == "spread" || l.stat == "puck line" { return (away(l) ? 1 : -1) * (l.point ?? 0) + 0 }
            if l.side == "over" || l.side == "under", let pt = l.point { return pt }
            return 0
        }
        func rows(_ ls: [PackLeg]) -> [BoardRow] {
            Dictionary(grouping: ls, by: rung).map { BoardRow(key: $0.key, legs: $0.value.sorted(by: order)) }.sorted { $0.key < $1.key }
        }

        let game = legs.filter { ($0.player ?? "").isEmpty }
        var tabs: [BoardTab] = []
        if !game.isEmpty {
            let byStat = Dictionary(grouping: game) { $0.stat == "draw" ? "moneyline" : $0.stat ?? "" }
            let stats = byStat.keys.sorted { a, b in
                let ia = gameOrder.firstIndex(of: a) ?? 99, ib = gameOrder.firstIndex(of: b) ?? 99
                return ia != ib ? ia < ib : a.localizedCompare(b) == .orderedAscending
            }
            let soccer = game.contains { $0.stat == "draw" }
            tabs.append(BoardTab(key: "game", title: "Game lines", count: game.count, sections: stats.map { s in
                // soccer reads home team first (Nov 5): a row of team sides (the result, a spread) runs home, draw, away, as
                // the game card above it does; totals keep Over before Under (web boardTabs)
                BoardSection(title: s == "moneyline" && soccer ? "Result" : statTitle(s), sub: nil, rows: rows(byStat[s]!).map { r in
                    soccer && r.legs.contains(where: { !($0.team ?? "").isEmpty }) ? BoardRow(key: r.key, legs: r.legs.reversed()) : r
                })
            }))
        }
        let props = Dictionary(grouping: legs.filter { !($0.player ?? "").isEmpty }) { $0.stat ?? "" }
        for (stat, ls) in props.sorted(by: { $0.value.count != $1.value.count ? $0.value.count > $1.value.count : $0.key.localizedCompare($1.key) == .orderedAscending }) {
            let players = Dictionary(grouping: ls) { $0.player! }
            tabs.append(BoardTab(key: stat, title: statTitle(stat), count: ls.count, sections: players.keys.sorted { $0.localizedCompare($1) == .orderedAscending }.map { who in
                let pl = players[who]!
                return BoardSection(title: who, sub: (pl[0].team ?? "").isEmpty ? nil : pl[0].team, rows: rows(pl))
            }))
        }
        return tabs
    }
}

// MARK: - Promos (Oct 22, web findPromo; change both together)
// Mike's bonus bets and profit boosts, on parlays: a bonus bet's stake isn't returned, so a win pays only the profit;
// a profit boost multiplies the profit. Both grow as the odds lengthen, so a ranking at the book's likely quote runs to
// the longest slip allowed, where that quote is least sure (the quote model misses by ~12%). So a same-game slip is
// ranked at a cautious quote (one miss below the likely one), and plain parlays (one leg per game) pay exactly their
// legs' product: built from legs priced off a sharp book, they need no guess at all and may run longer.

/// A promo and its token's terms, as the book states them (all optional): stake in dollars, the cap on a boost's extra
/// winnings in dollars, the fewest legs, and the shortest total odds (American) the token accepts.
struct Promo: Equatable, Codable {
    enum Kind: String, Codable { case none, bonus, boost }
    var kind: Kind = .none
    var pct: Double = 50
    var stake: Double?
    var maxExtra: Double?
    var minLegs: Int?
    var minOdds: Double?
    var maxOdds: Double?      // FanDuel's "+200000 Max Odds" (Oct 24): a slip longer than this doesn't qualify
    var market: String?       // a token for one market (Nov 5, Build.marketFits)
    var kinds: [String]?      // the kinds of leg it allows (Nov 9, Promos.legChoices)

    static let none = Promo()
    static let bonus = Promo(kind: .bonus)
    static func boost(_ pct: Double) -> Promo { Promo(kind: .boost, pct: pct) }

    /// Kept in UserDefaults as JSON; a launch argument `-betlab-build-promo bonus` (or `boost:50`, `none`) sets it too.
    /// Sorted keys: the finder's task id is built from it, and an unsorted encoder may order keys differently each time.
    var stored: String {
        let enc = JSONEncoder()
        enc.outputFormatting = .sortedKeys
        return (try? enc.encode(self)).flatMap { String(data: $0, encoding: .utf8) } ?? ""
    }
    init(kind: Kind = .none, pct: Double = 50) { self.kind = kind; self.pct = pct }
    init(stored: String?) {
        let s = stored ?? ""
        if let d = s.data(using: .utf8), let p = try? JSONDecoder().decode(Promo.self, from: d) { self = p }
        else if s == "bonus" { self = .bonus }
        else if s.hasPrefix("boost:"), let b = Double(s.dropFirst(6)), b > 0 { self = .boost(b) }
        else { self = .none }
    }

    /// The same terms on another kind (switching bonus <-> boost keeps stake, min legs and min odds; a boost keeps its cap).
    func switched(to k: Kind) -> Promo {
        guard k != .none else { return .none }
        var p = Promo(kind: k, pct: kind == .boost ? pct : 50)
        if kind != .none { p.stake = stake; p.minLegs = minLegs; p.minOdds = minOdds; p.maxOdds = maxOdds }
        if k == .boost && kind == .boost { p.maxExtra = maxExtra }
        return p
    }
}

struct PromoPick: Identifiable {
    let legs: [SlipLeg]
    let p: Double
    let games: Int
    let plain: Bool       // one leg per game: it pays exactly the legs' product
    let dec: Double       // the likely quote (the exact one for a plain parlay)
    let low: Double       // the quote it's ranked at: cautious for a same-game slip, exact for a plain parlay
    let ev: Double        // the promo's value per dollar at `low`
    var id: String { legs.map { $0.eventId + $0.label }.joined(separator: "+") }
}

extension Build {
    /// Expected value per dollar staked (a bonus bet: per dollar of bonus credit) at decimal odds `dec`. A boost's extra
    /// winnings stop at the token's cap (maxExtra, which needs the stake to compare).
    // MARK: themed slips (Nov 4, web themedSlip; fixture tests/fixtures/themes.json)
    enum SlipTheme: String, CaseIterable, Identifiable {
        case underdogs, favorites, overs, btts
        var id: String { rawValue }
        var title: String { switch self { case .underdogs: "Underdogs"; case .favorites: "Favorites"; case .overs: "Overs only"; case .btts: "Both teams score" } }
        func fits(_ l: PackLeg) -> Bool {
            switch self {
            case .underdogs: l.stat == "moneyline" && l.p >= 0.25 && l.p < 0.48
            case .favorites: l.stat == "moneyline" && l.p >= 0.6 && l.p <= 0.85
            case .overs: l.side == "over" && l.p >= 0.45 && l.p <= 0.75
            case .btts: l.stat == "btts" && l.side == "yes" && l.p >= 0.4
            }
        }
    }
    struct ThemedSlip { let legs: [SlipLeg]; let p: Double; let dec: Double; let ev: Double }

    /// One leg per game, the best-priced leg that fits, from the best games. Plain parlays, so the price is the legs' own, exact.
    static func themedSlip(_ pr: Pricer, _ eids: [String], _ theme: SlipTheme, size: Int = 3, bans: [Ban] = []) -> ThemedSlip? {
        func decimal(_ am: Double) -> Double { am > 0 ? 1 + am / 100 : 1 + 100 / -am }
        var best: [(eid: String, leg: PackLeg, v: Double)] = []
        for eid in eids {
            guard let pack = pr.pack(eid) else { continue }
            var top: (eid: String, leg: PackLeg, v: Double)?
            for raw in pack.legs.values {
                guard let l = pr.leg(eid, raw.label), l.unavailable != true, l.price.isFinite, theme.fits(l) else { continue }
                if pr.book == .fanduel, (l.source ?? "").hasPrefix("fair price") { continue }      // the book doesn't post it
                if Bans.banned(bans, l.label, league: pack.sport, player: (l.player ?? "").isEmpty ? nil : l.player) || (l.bits == nil && l.not == nil) { continue }
                let v = l.p * decimal(l.price)
                if top == nil || v > top!.v || (v == top!.v && l.label < top!.leg.label) { top = (eid, l, v) }
            }
            if let top { best.append(top) }
        }
        best.sort { $0.v != $1.v ? $0.v > $1.v : $0.eid < $1.eid }
        let picks = Array(best.prefix(size))
        guard picks.count >= 2 else { return nil }
        let p = picks.reduce(1) { $0 * $1.leg.p }, dec = picks.reduce(1) { $0 * decimal($1.leg.price) }
        return ThemedSlip(legs: picks.map { SlipLeg(eventId: $0.eid, label: $0.leg.label) }, p: p, dec: dec, ev: p * dec - 1)
    }

    static func promoEv(_ p: Double, _ dec: Double, _ promo: Promo) -> Double {
        switch promo.kind {
        case .bonus: return p * (dec - 1)
        case .none: return p * dec - 1
        case .boost: return p * (dec + boostExtra(dec, promo)) - 1
        }
    }

    private static func boostExtra(_ dec: Double, _ promo: Promo) -> Double {
        var extra = (dec - 1) * promo.pct / 100
        if let s = promo.stake, s != 0, let m = promo.maxExtra { extra = min(extra, m / s) }
        return extra
    }

    /// Whether a slip meets the token's terms: enough legs, and total odds at least minOdds.
    static func promoFits(_ promo: Promo, legs: Int, dec: Double) -> Bool {
        if promo.kind == .none { return true }
        if let m = promo.minLegs, m != 0, legs < m { return false }
        if let mx = promo.maxOdds, dec > Odds.dec(mx) + 1e-9 { return false }
        return promo.minOdds.map { dec >= Odds.dec($0) - 1e-9 } ?? true
    }

    /// The book's usual payout share for a slip (the quote model, else the bands): its likely quote is that over the fair chance.
    static func typicalRatio(_ p: Double, naive: Double, legs: Int, crossGame: Bool, bands: [Band] = defaultBands, model: QuoteModel? = nil) -> Double {
        if let model { return model.ratio(fairDec: 1 / p, naiveDec: naive, legs: legs, crossGame: crossGame) }
        let fair = Odds.am(1 / p)
        return (bands.first { $0.maxFair == nil || fair <= $0.maxFair! } ?? bands[bands.count - 1]).ratio
    }

    /// A leg whose fair chance comes from a sharp book's price, not soft books or a model: NFL, college and NBA packs name
    /// the book ("pinnacle", "betonlineag (market)"); soccer and NHL packs fit every chance to Pinnacle's prices and their
    /// source says where the price came from ("FanDuel price in the feed").
    static func sharpLeg(_ l: PackLeg) -> Bool {
        (l.source ?? "").range(of: "pinnacle|lowvig|betonline|price in the feed", options: [.regularExpression, .caseInsensitive]) != nil
    }

    static let sgpMaxDec = 16.0      // same-game slips to fair +1500: where Mike's typed quotes teach the quote model
    static let plainMaxDec = 26.0    // plain parlays to fair +2500: their price is exact

    /// The best bets for a promo: singles priced off a sharp book at their exact price (Oct 22), 2-3 leg same-game slips from each game's best-priced legs (a token's leg minimum and one more, Oct 26), ranked at a cautious
    /// quote, and 2-4 leg plain parlays across games from legs priced off a sharp book, at their exact price.
    static func findPromo(_ pr: Pricer, _ eids: [String], _ promo: Promo, bands: [Band] = defaultBands, model: QuoteModel? = nil,
                          top: Int = 8, bans: [Ban] = []) -> [PromoPick] {
        let out = promoCandidates(pr, eids, promo, bands: bands, model: model, bans: bans)
        // the best 3 singles always show, apart from the parlays: an uncapped boost ranks long parlays of near-fair legs
        // higher, but a single risks far less, a token's winnings cap favors it, and some tokens take singles only
        let byEv = { (a: PromoPick, b: PromoPick) in a.ev > b.ev }
        return Array(out.filter { $0.legs.count == 1 }.sorted(by: byEv).prefix(3))
            + Array(out.filter { $0.legs.count > 1 }.sorted(by: byEv).prefix(top))
    }

    /// Every bet findPromo weighs, unranked (the promo finder, PromoFinder.swift, ranks them its own way; web promoCandidates).
    /// The markets a token can be limited to (Nov 5, migration 0039; web builder.marketFits, tests/fixtures/promos.json). A
    /// soccer draw is part of the moneyline; both teams to score and double chance fit only a token for any market.
    static let marketChoices = [("moneyline", "Moneyline"), ("spread", "Spread"), ("total", "Total"), ("props", "Player props")]
    static func marketFits(_ market: String?, stat: String?, player: String?, kinds: [String]? = nil) -> Bool {
        let hasPlayer = !(player ?? "").isEmpty
        // a token for certain kinds of leg ("Anytime TD only", Nov 9): a player leg of one of them, in the packs' stat names
        if let kinds, !kinds.isEmpty, !(hasPlayer && kinds.contains(stat ?? "")) { return false }
        guard let market else { return true }
        if market == "props" { return hasPlayer }
        if hasPlayer { return false }
        switch market {
        case "moneyline": return stat == "moneyline" || stat == "draw"
        case "spread": return stat == "spread" || stat == "puck line"
        case "total": return stat == "total" || stat == "goals"
        default: return false
        }
    }

    static func promoCandidates(_ pr: Pricer, _ eids: [String], _ promo: Promo, bands: [Band] = defaultBands, model: QuoteModel? = nil,
                                bans: [Ban] = []) -> [PromoPick] {
        struct L { let leg: PackLeg; let eid: String; let v: Double }
        let per: [[L]] = eids.filter { pr.pack($0) != nil }.map { eid in
            pr.pack(eid)!.legs.keys.compactMap { pr.leg(eid, $0) }
                // a leg the book doesn't post (FanDuel's soccer totals: our fair price stands in) can't carry a promo
                .filter { !$0.unavailable && $0.p >= 0.05 && $0.p <= 0.95 && $0.price.isFinite
                    && !(pr.book == .fanduel && ($0.source ?? "").hasPrefix("fair price"))
                    && marketFits(promo.market, stat: $0.stat, player: $0.player, kinds: promo.kind == .none ? nil : promo.kinds)
                    && !Bans.banned(bans, $0.label, league: pr.pack(eid)?.sport, player: $0.player) }   // the ban list (Oct 25)
                .map { L(leg: $0, eid: eid, v: $0.p * Odds.dec($0.price)) }
                .sorted { $0.v != $1.v ? $0.v > $1.v : $0.leg.label < $1.leg.label }
        }
        var out: [PromoPick] = []
        let cap = bands.map(\.ratio).max() ?? 1
        let miss = exp(-(model?.rmse ?? 0.12))         // one typical miss of the quote model
        func consider(_ ls: [L]) {
            // one leg per player, and one per game market (Over 1.5 with Over 2.5 is one bet twice)
            let keys = ls.map { l in l.eid + "|" + ((l.leg.player ?? "").isEmpty ? (l.leg.stat == "draw" ? "moneyline" : l.leg.stat ?? "") : l.leg.player!) }
            guard Set(keys).count == keys.count else { return }
            var byGame: [(eid: String, labels: [String])] = []
            for l in ls {
                if let i = byGame.firstIndex(where: { $0.eid == l.eid }) { byGame[i].labels.append(l.leg.label) } else { byGame.append((l.eid, [l.leg.label])) }
            }
            // nested legs (A or draw with A to win) are one bet twice; the books refuse them and the quote model overrates them
            for a in ls { for b in ls where a.eid == b.eid && a.leg.label < b.leg.label {
                guard let j = pr.joint(a.eid, [a.leg.label, b.leg.label]), j < 0.97 * min(a.leg.p, b.leg.p) else { return }
            } }
            var p = 1.0
            for g in byGame { guard let j = pr.joint(g.eid, g.labels) else { return }; p *= j }
            let plain = byGame.allSatisfy { $0.labels.count == 1 }
            guard p > 0, 1 / p <= (plain ? plainMaxDec : sgpMaxDec) else { return }
            let naive = ls.reduce(1.0) { $0 * Odds.dec($1.leg.price) }
            // a same-game slip: never more than the best payout share Mike's typed quotes have shown (the model
            // extrapolates past it), nor more than the legs' product; ranked one miss below that
            let ratio = plain ? p * naive : min(typicalRatio(p, naive: naive, legs: ls.count, crossGame: byGame.count > 1, bands: bands, model: model), cap)
            let dec = plain ? naive : min(ratio / p, naive)
            let low = plain ? naive : min(ratio * miss / p, naive)
            guard promoFits(promo, legs: ls.count, dec: low) else { return }
            out.append(PromoPick(legs: ls.map { SlipLeg(eventId: $0.eid, label: $0.leg.label) }, p: p, games: byGame.count, plain: plain,
                                 dec: dec, low: low, ev: promoEv(p, low, promo)))
        }
        // same-game slips: 2-3 legs from each game's 14 best-priced legs. A token with a leg minimum of 3 or more (Mike,
        // Oct 26: one-game boosts with a leg minimum gave no options) gets slips of that many legs and one more (up to 6),
        // from a pool mixing the best-priced legs with the best-priced likely ones (45%+): the best-priced are long shots,
        // and three of them ran past the +1500 fair cap (web findPromo)
        let need = max(2, promo.kind == .none ? 0 : promo.minLegs ?? 0)
        let sizes = need <= 3 ? [2, 3] : Array(Set([need, min(need + 1, 6)])).sorted()
        for g in per {
            var t = need < 3 ? Array(g.prefix(14)) : []
            if need >= 3 {
                for l in Array(g.prefix(7)) + Array(g.filter { $0.leg.p >= 0.45 }.prefix(7)) where !t.contains(where: { $0.leg.label == l.leg.label }) { t.append(l) }
            }
            func pick(_ from: Int, _ chosen: [L], _ n: Int) {
                if chosen.count == n { consider(chosen); return }
                guard from < t.count else { return }
                for i in from..<t.count { pick(i + 1, chosen + [t[i]], n) }
            }
            for n in sizes { pick(0, [], n) }
        }
        // singles: one leg priced off a sharp book pays exactly its price, so a boost or a bonus keeps all of it (Oct 22: a
        // 100% boost on Cole Kmet over 1.5 receptions, FanDuel +178 against a 33.2% fair chance, was worth +51%)
        for g in per { for l in g where sharpLeg(l.leg) { consider([l]) } }
        // plain parlays: each game's best 3 legs priced off a sharp book, one per game, 2-4 legs, from the 8 games whose
        // best leg is priced best (about 7,500 slips at most)
        let sharp = Array(per.map { Array($0.filter { sharpLeg($0.leg) }.prefix(3)) }.filter { !$0.isEmpty }
            .sorted { $0[0].v > $1[0].v }.prefix(8))
        func walk(_ from: Int, _ picked: [L]) {
            if picked.count >= 2 { consider(picked) }
            if picked.count == 4 { return }
            for gi in from..<sharp.count { for l in sharp[gi] { walk(gi + 1, picked + [l]) } }
        }
        if sharp.count > 1 { walk(0, []) }
        return out
    }
}

// MARK: - The two-book lock (Oct 22, web findLocks)
// A promo on one side at the promo's book, the other side with cash at the other book, sized so both outcomes pay the
// same: the promo's value for sure instead of on average (Mike has FanDuel and DraftKings). A bonus bet S at decimal dA
// hedged at dB locks S(dA-1)(1-1/dB); a boosted cash stake S that would win W (profit plus the capped extra) locks
// W - (W+S)/dB. Singles only: hedging a parlay's every outcome takes more bets than it saves.

struct LockPick: Identifiable {
    let eventId: String
    let promoLeg: String, hedgeLeg: String
    let promoPrice: Double, hedgePrice: Double
    let promoLink: String?, hedgeLink: String?
    let locked: Double, hedge: Double
    var id: String { eventId + promoLeg }
}

extension Build {
    /// What both outcomes pay, per promo dollar, and the hedge per promo dollar. Nil for no promo.
    static func lockValue(_ dA: Double, _ dB: Double, _ promo: Promo) -> (locked: Double, hedge: Double)? {
        switch promo.kind {
        case .none: return nil
        case .bonus:
            let hedge = (dA - 1) / dB
            return (hedge * (dB - 1), hedge)
        case .boost:
            let win = dA - 1 + boostExtra(dA, promo)     // the promo bet's profit if it wins
            let hedge = (win + 1) / dB                    // covers the profit and the lost stake
            return (win - hedge, hedge)
        }
    }

    /// The other side of a leg in its game: an explicit opposite (the pack's `not`), the opposite side of the same
    /// number (over/under, yes/no; a player's too), the other team's opposite rung, or the other team in a two-way
    /// moneyline (no draw in the pack).
    static func opposite(_ pk: Pack, _ a: PackLeg) -> PackLeg? {
        let legs = pk.legs.values.sorted { $0.label < $1.label }
        let flip = ["over": "under", "under": "over", "yes": "no", "no": "yes"]
        let ab = ["moneyline", "spread", "puck line"]
        return legs.first { b in b.label != a.label && (a.not == b.label || b.not == a.label) }
            ?? legs.first { b in b.label != a.label && b.stat == a.stat && (b.player ?? "") == (a.player ?? "") && b.point == a.point
                && a.side != nil && flip[a.side!] == b.side && !ab.contains(a.stat ?? "") }
            ?? legs.first { b in b.label != a.label && (a.stat == "spread" || a.stat == "puck line") && b.stat == a.stat
                && b.team != a.team && a.point != nil && b.point == -a.point! }
            ?? (a.stat == "moneyline" && !legs.contains { $0.stat == "draw" }
                ? legs.first { b in b.label != a.label && b.stat == "moneyline" && (b.player ?? "").isEmpty && b.team != a.team } : nil)
    }

    /// A price the book really posts: not a fair-price stand-in (FanDuel's soccer goals and puck lines) nor a moved rung.
    private static func posted(_ pr: Pricer, _ eid: String, _ label: String) -> PackLeg? {
        guard let l = pr.leg(eid, label), !l.unavailable, l.price.isFinite else { return nil }
        if pr.book == .fanduel, (l.source ?? "").range(of: "^(fair price|no fanduel)", options: [.regularExpression, .caseInsensitive]) != nil { return nil }
        return l
    }

    /// The best locks for a promo at `pr`'s book, hedged at `hedge`'s book, from these games' two-sided markets. A pair
    /// whose two prices add to under 98% or over 115% (implied) is a mismatched feed rung, not a bet: it's skipped, as is
    /// a price more than 30% off our fair chance.
    static func findLocks(_ pr: Pricer, _ hedge: Pricer, _ eids: [String], _ promo: Promo, top: Int = 5, bans: [Ban] = []) -> [LockPick] {
        guard promo.kind != .none, pr.book != hedge.book, (promo.minLegs ?? 1) <= 1 else { return [] }
        var out: [LockPick] = []
        for eid in eids {
            guard let pk = pr.pack(eid) else { continue }
            for raw in pk.legs.values where marketFits(promo.market, stat: raw.stat, player: raw.player, kinds: promo.kinds) {
                guard let b0 = opposite(pk, raw), let a = posted(pr, eid, raw.label), let b = posted(hedge, eid, b0.label) else { continue }
                if Bans.banned(bans, a.label, league: pk.sport, player: a.player) || Bans.banned(bans, b.label, league: pk.sport, player: b.player) { continue }   // the ban list
                let dA = Odds.dec(a.price), dB = Odds.dec(b.price)
                let over = 1 / dA + 1 / dB
                guard over >= 0.98, over <= 1.15, abs(a.p * dA - 1) <= 0.3, abs(b.p * dB - 1) <= 0.3,
                      promoFits(promo, legs: 1, dec: dA), let v = lockValue(dA, dB, promo) else { continue }
                out.append(LockPick(eventId: eid, promoLeg: a.label, hedgeLeg: b.label, promoPrice: a.price, hedgePrice: b.price,
                                    promoLink: a.link, hedgeLink: b.link, locked: v.locked, hedge: v.hedge))
            }
        }
        return Array(out.sorted { $0.locked != $1.locked ? $0.locked > $1.locked : $0.promoLeg < $1.promoLeg }.prefix(top))
    }
}
