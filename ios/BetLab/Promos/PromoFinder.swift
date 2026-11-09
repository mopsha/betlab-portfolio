import SwiftUI

// The promo finder (web app/build/promo, components/promos/PromoFinder.tsx, lib/promo-finder.ts and lib/slices.ts, Oct 30):
// pick a token from the wallet (or type one), where to look (a slice, games you pick, one game, or today across
// sports) and how to rank (Max value, Balanced, Safe), then place the best one at the token's dollars; a lock saves
// both of its bets under one lock_id. Shared fixtures: tests/fixtures/promo_finder.json and slices.json.

// MARK: - kickoff slices (web lib/slices.ts; src/betlab/sgp_plus.SLICES and slice_of)

enum Slices {
    /// sport: [(name, ends before this ET hour, what its title calls it)]
    static let table: [String: [(String, Double, String)]] = [
        "nfl": [("morning", 12, "morning"), ("early", 15, "early"), ("late", 19, "late"), ("night", 24, "night")],
        "ncaaf": [("noon", 15, "noon"), ("afternoon", 19, "afternoon"), ("night", 24, "night")],
        "soccer": [("early", 8.75, "early"), ("nine", 9.75, "9 AM"), ("ten", 11, "10 AM"), ("eleven", 12, "11 AM"),
                   ("noon", 12.67, "noon"), ("lunch", 14.25, "12:45"), ("three", 17, "3 PM"), ("five", 18.75, "5:30 PM"),
                   ("mls", 20.25, "7:30 PM"), ("evening", 21.25, "8:30 PM"), ("night", 24, "late")],
        "nhl": [("afternoon", 17, "afternoon"), ("dusk", 18.75, "5 PM"), ("evening", 21, "evening"), ("late", 24, "late")],
        "ncaab": [("morning", 12, "morning"), ("afternoon", 17, "afternoon"), ("evening", 21, "evening"), ("late", 24, "late")],
        "nba": [("afternoon", 17, "afternoon"), ("dusk", 18.75, "5 PM"), ("early", 21, "early"), ("late", 24, "late")],
        "ufc": [("morning", 11.5, "morning"), ("midday", 13.5, "midday"), ("afternoon", 17, "afternoon"),
                ("evening", 19.5, "evening"), ("prelims", 21.5, "prelims"), ("main", 24, "main card")],
    ]
    static let sportName = ["nfl": "NFL", "ncaaf": "College football", "soccer": "Soccer", "nhl": "NHL", "ncaab": "College basketball",
                            "nba": "NBA", "ufc": "UFC"]
    private static let et: Calendar = { var c = Calendar(identifier: .gregorian); c.timeZone = Fmt.et; return c }()
    private static let dayF: DateFormatter = {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = Fmt.et; f.dateFormat = "yyyy-MM-dd"; return f
    }()

    /// (ET day, slice name) for a kickoff; nil for a sport with no slices.
    static func sliceOf(_ sport: String, _ commence: String) -> (String, String)? {
        guard let table = table[sport], let t = Models.date(commence) else { return nil }
        let c = et.dateComponents([.hour, .minute], from: t)
        if c.hour! < 4 { return (dayF.string(from: t.addingTimeInterval(-86400)), table.last!.0) }
        let h = Double(c.hour!) + Double(c.minute!) / 60
        return (dayF.string(from: t), (table.first { h < $0.1 } ?? table.last!).0)
    }

    /// A slice's word in its title: the table's, but the "dusk" slice says its first start, "5:10 PM" (sgp_plus.slice_names,
    /// web slices.ts sliceWord).
    static func word(_ sport: String, _ name: String, first: Date) -> String {
        guard name == "dusk" else { return table[sport]?.first { $0.0 == name }?.2 ?? name }
        let c = et.dateComponents([.hour, .minute], from: first)
        let h = (c.hour ?? 0) % 12 == 0 ? 12 : (c.hour ?? 0) % 12, m = c.minute ?? 0
        return "\(h)\(m == 0 ? "" : String(format: ":%02d", m)) \((c.hour ?? 0) < 12 ? "AM" : "PM")"
    }

    struct Slice: Identifiable, Hashable { let key: String; let sport: String; let title: String; let first: String; var events: [String]; var id: String { key } }

    /// The games grouped into slices, soonest first: "NFL early · Sun".
    static func slicesOf(_ games: [PackGame]) -> [Slice] {
        var by: [String: Slice] = [:]
        for g in games.sorted(by: { $0.commenceTime < $1.commenceTime }) {
            guard let (day, name) = sliceOf(g.sport, g.commenceTime) else { continue }
            let key = "\(day)-\(g.sport)-\(name)"
            if by[key] != nil { by[key]!.events.append(g.eventId); continue }
            let word = Models.date(g.commenceTime).map { Slices.word(g.sport, name, first: $0) } ?? name
            let dowF = DateFormatter(); dowF.locale = Locale(identifier: "en_US_POSIX"); dowF.timeZone = TimeZone(identifier: "UTC"); dowF.dateFormat = "EEE"
            let dow = dowF.string(from: ISO8601DateFormatter().date(from: day + "T12:00:00Z")!)
            by[key] = Slice(key: key, sport: g.sport, title: "\(sportName[g.sport] ?? g.sport) \(word) · \(dow)", first: g.commenceTime, events: [g.eventId])
        }
        return by.values.sorted { $0.first < $1.first }
    }
}

// MARK: - ranking (web lib/promo-finder.ts)

enum PromoFinder {
    enum Mode: String, CaseIterable, Identifiable { case max, balanced, safe; var id: String { rawValue } }
    static func label(_ m: Mode) -> String { m == .max ? "Max value" : m == .balanced ? "Balanced" : "Safe" }
    static func floor(_ m: Mode) -> Double { m == .max ? 0.08 : m == .balanced ? 0.25 : 0.45 }
    static func blurb(_ m: Mode) -> String {
        switch m {
        case .max: return "The most the token is worth on average, long shots included."
        case .balanced: return "The most it's worth among its likelier bets (1 in 4 or better when it has them)."
        case .safe: return "The likeliest bets this token allows that are still worth having."
        }
    }
    static let safeShare = 0.6

    /// The q-th quantile, linear between ranks (web quantile).
    static func quantile(_ xs: [Double], _ q: Double) -> Double {
        guard !xs.isEmpty else { return 0 }
        let s = xs.sorted(), pos = Double(s.count - 1) * q, lo = Int(pos.rounded(.down))
        return lo + 1 < s.count ? s[lo] + (s[lo + 1] - s[lo]) * (pos - Double(lo)) : s[lo]
    }

    /// The chance a mode asks for on this token (Nov 6, Mike: boosts "never have safe or balanced options"): Max value's
    /// fixed 8%; Balanced and Safe their floor, or lower when the bets worth something don't reach it (their median, their
    /// top quarter). Web floorFor.
    static func floorFor(_ m: Mode, _ worth: [Double]) -> Double {
        guard m != .max, !worth.isEmpty else { return floor(m) }
        return min(floor(m), quantile(worth, m == .balanced ? 0.5 : 0.75))
    }
    static let defaultDollars = 10.0
    static let todayCap = 30

    enum Kind: String { case single, parlay, sgp, lock }
    struct Result: Identifiable {
        let kind: Kind
        let legs: [SlipLeg]
        let p: Double
        let games: Int
        let dec: Double
        let at: Double
        let value: Double
        let boostAdds: Double
        var lock: LockPick? = nil
        var text = ""
        var id: String { kind.rawValue + "|" + legs.map { "\($0.eventId):\($0.label)" }.sorted().joined(separator: "+") }
    }

    static func tokenDollars(_ promo: Promo) -> Double { promo.kind != .none && (promo.stake ?? 0) > 0 ? promo.stake! : defaultDollars }

    private static func extra(_ dec: Double, _ promo: Promo, _ S: Double) -> Double {
        guard promo.kind == .boost else { return 0 }
        let x = (dec - 1) * promo.pct / 100
        if let m = promo.maxExtra, m > 0 { return min(x, m / S) }
        return x
    }

    /// The token's expected dollars (web tokenValue).
    static func tokenValue(_ p: Double, _ dec: Double, _ promo: Promo, _ S: Double) -> Double {
        if promo.kind == .bonus { return S * p * (dec - 1) }
        return S * (p * (dec - 1 + extra(dec, promo, S)) - (1 - p))
    }
    static func boostAdds(_ p: Double, _ dec: Double, _ promo: Promo, _ S: Double) -> Double { S * p * extra(dec, promo, S) }

    static func money(_ x: Double) -> String { (x < 0 ? Fmt.minus : "") + String(format: "$%.2f", abs(x)) }

    /// What a result does, in words (web explain).
    static func explain(_ r: Result, _ promo: Promo, _ S: Double, perDefault: Bool) -> String {
        let tok = perDefault ? "each $10 of it" : "your \(money(S).replacingOccurrences(of: ".00", with: "")) \(promo.kind == .bonus ? "bonus bet" : "boosted bet")"
        // a lock's sure thing is the pair, not either bet (Oct 30: "100% to hit" on a +250 read as the +250 being sure)
        if r.kind == .lock { return "Two bets: the promo on the first side, \(money(S * (r.lock?.hedge ?? 0))) cash on the other. Whichever side wins, you're up \(money(r.value))" }
        let hits = "hits \(Int((r.p * 100).rounded()))%"
        if promo.kind == .bonus { return "Turns \(tok) into \(money(r.value)) on average · \(hits)" }
        return "Expected \(money(r.value)) on \(tok) · the boost adds \(money(r.boostAdds)) · \(hits)"
    }

    private static let order: [Kind: Int] = [.single: 0, .parlay: 1, .lock: 2, .sgp: 3]

    /// The ranked list for a token: at most `top`, each bet once (web rank).
    static func rank(_ picks: [PromoPick], _ locks: [LockPick], _ promo: Promo, _ mode: Mode, top: Int = 10) -> [Result] {
        guard promo.kind != .none else { return [] }
        let S = tokenDollars(promo), perDefault = !((promo.stake ?? 0) > 0)
        var all: [Result] = picks.map { k in
            let kind: Kind = k.legs.count == 1 ? .single : k.plain ? .parlay : .sgp
            let at = mode == .safe && kind == .sgp ? k.low * (k.low / k.dec) : k.low
            return Result(kind: kind, legs: k.legs, p: k.p, games: k.games, dec: k.dec, at: at, value: tokenValue(k.p, at, promo, S),
                          boostAdds: boostAdds(k.p, at, promo, S))
        }
        all += locks.map { l in
            let d = Odds.dec(l.promoPrice)
            return Result(kind: .lock, legs: [SlipLeg(eventId: l.eventId, label: l.promoLeg)], p: 1, games: 1, dec: d, at: d,
                          value: S * l.locked, boostAdds: 0, lock: l)
        }
        // Balanced and Safe ask only what this token's bets worth something can reach
        let fl = floorFor(mode, all.filter { $0.value > 1e-9 }.map(\.p))
        var list = all.filter { $0.p >= fl - 1e-12 }
        if mode != .max { list = list.filter { $0.value > 1e-9 } }
        if mode == .safe {
            let best = max(0, list.map(\.value).max() ?? 0)
            list = list.filter { $0.value >= safeShare * best - 1e-9 }.sorted { a, b in
                let la = a.kind == .lock ? 1 : 0, lb = b.kind == .lock ? 1 : 0
                if la != lb { return la > lb }
                if a.p != b.p { return a.p > b.p }
                if a.value != b.value { return a.value > b.value }
                return order[a.kind]! < order[b.kind]!
            }
        } else {
            list.sort { a, b in a.value != b.value ? a.value > b.value : order[a.kind]! < order[b.kind]! }
        }
        var seen = Set<String>(), uses: [String: Int] = [:], out: [Result] = [], skipped: [Result] = [], unders = 0
        func key(_ l: SlipLeg) -> String { "\(l.eventId):\(l.label)" }
        func take(_ r: Result) {
            var r = r
            for l in r.legs { uses[key(l), default: 0] += 1 }
            if allUnder(r.legs) { unders += 1 }
            r.text = explain(r, promo, S, perDefault: perDefault)
            out.append(r)
        }
        for r in list where !seen.contains(r.id) {
            if out.count >= top { break }
            seen.insert(r.id)
            // a varied list (Nov 8, Mike: "shouldn't give all unders"): a leg in two results at most, all-under bets half the list
            if r.legs.contains(where: { uses[key($0), default: 0] >= maxLegUses }) || (allUnder(r.legs) && unders >= top / 2) {
                skipped.append(r)
                continue
            }
            take(r)
        }
        for r in skipped where out.count < top { take(r) }     // too few others: the best of the rest, in order
        return out
    }

    /// A leg shows in at most this many results, and bets whose legs are all unders fill at most half the list (web
    /// promo-finder.ts MAX_LEG_USES / allUnder, Nov 8).
    static let maxLegUses = 2
    static func allUnder(_ legs: [SlipLeg]) -> Bool {
        !legs.isEmpty && legs.allSatisfy { $0.label.range(of: #"\bunder\b"#, options: [.regularExpression, .caseInsensitive]) != nil }
    }

    enum Scope: Hashable { case slice(String), games([String]), game(String), today }

    /// The games a scope searches, soonest first; a token's sports narrow it (web scopeEvents).
    static func scopeEvents(_ scope: Scope, _ games: [PackGame], _ slices: [Slices.Slice], sports: [String]? = nil, now: Date = Date()) -> [String] {
        let ok = games.filter { g in (Models.date(g.commenceTime).map { $0 > now } ?? false) && (sports?.isEmpty != false || sports!.contains(g.sport)) }
            .sorted { $0.commenceTime < $1.commenceTime }
        let has = Set(ok.map(\.eventId))
        switch scope {
        case .game(let e): return has.contains(e) ? [e] : []
        case .games(let es): return es.filter { has.contains($0) }
        case .slice(let k): return (slices.first { $0.key == k }?.events ?? []).filter { has.contains($0) }
        case .today:
            let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = Fmt.et; f.dateFormat = "yyyy-MM-dd"
            let day = { (t: String) in Models.date(t).map { f.string(from: $0) } ?? "" }
            let today = f.string(from: now)
            var first = ok.filter { day($0.commenceTime) == today }
            if first.isEmpty, let d = ok.first.map({ day($0.commenceTime) }) { first = ok.filter { day($0.commenceTime) == d } }
            return first.prefix(todayCap).map(\.eventId)
        }
    }

    /// A bets row for one side of a promo placement (web placePromo): the token's dollars over the account's unit.
    static func betRow(custom c: [String: Any?], price: Double, book: String, dollars: Double, unit: Double, real: Bool,
                       lockId: String?, extra: [String: Any?] = [:]) -> [String: Any?] {
        let units = (dollars / unit * 1000).rounded() / 1000
        let games = (c["games"] as? [[String: Any?]] ?? []).map { g -> [String: Any?] in ["matchup": g["matchup"] ?? nil, "game_ref": g["game_ref"] ?? nil, "legs": g["legs"] ?? nil] }
        var row: [String: Any?] = ["kind": "custom", "sgp_id": c["sgp_id"] ?? nil, "price": price, "book": book, "matchup": c["matchup"] ?? nil,
                                   "fair_price": c["fair_price"] ?? nil, "p_fair": c["p_fair"] ?? nil, "legs": c["legs"] ?? nil,
                                   "odds_event_id": c["odds_event_id"] ?? nil, "games": games, "mode": real ? "real" : "paper",
                                   "stake": real ? units : nil, "lock_id": lockId]
        for (k, v) in extra { row[k] = v }
        return row
    }
}

// MARK: - the screen

@MainActor
final class FinderModel: ObservableObject {
    @Published private(set) var games: [PackGame] = []
    @Published private(set) var bands: [Band] = Build.defaultBands
    @Published private(set) var quoteModel: QuoteModel?
    @Published private(set) var packs: [String: Pack] = [:]
    @Published private(set) var failed: Set<String> = []
    @Published private(set) var results: [PromoFinder.Result] = []
    @Published private(set) var loaded = false
    private var runKey = ""

    private struct Meta: Decodable { let oddsEventId: String; let sport: String?; let commenceTime: String; let matchup: String?; let part: String? }
    private struct FunResults: Decodable { struct Typical: Decodable { let bands: [Band]?; let model: QuoteModel? }; let typicalRatio: Typical? }
    private struct PackRow: Decodable { let body: PackPart }

    func load(_ api: SupabaseClient) async {
        async let m: [Meta] = api.rows("leg_packs", .init(select: "odds_event_id,sport,commence_time,matchup:body->>matchup,part:body->>part",
                                                          gt: ("commence_time", Date()), limit: 2000))
        async let f: FunResults? = api.doc("app", "fun_results")
        if let meta = try? await m {
            games = meta.filter { Double($0.part ?? "1") ?? 1 == 1 }
                .map { PackGame(eventId: $0.oddsEventId, matchup: $0.matchup ?? "", commenceTime: $0.commenceTime, sport: $0.sport ?? "nfl") }
                .sorted { $0.commenceTime < $1.commenceTime }
        }
        if let fun = try? await f {
            if let b = fun.typicalRatio?.bands, !b.isEmpty { bands = b }
            quoteModel = fun.typicalRatio?.model
        }
        loaded = true
    }

    func loadPacks(_ api: SupabaseClient, _ events: [String]) async {
        let need = events.filter { packs[$0] == nil && !failed.contains($0) }
        await withTaskGroup(of: (String, Pack?).self) { group in
            for eid in need {
                group.addTask {
                    let parts: [PackRow]? = try? await api.rows("leg_packs", .init(eq: [("odds_event_id", eid)], select: "body"))
                    return (eid, parts.flatMap { Pack.merge($0.map(\.body)) })
                }
            }
            for await (eid, pk) in group { if let pk { packs[eid] = pk } else { failed.insert(eid) } }
        }
    }

    /// The ranked results, worked out off the main thread.
    func refresh(_ events: [String], promo: Promo, book: BuildBook, mode: PromoFinder.Mode, locks: Bool) async {
        let ready = events.filter { self.packs[$0] != nil }
        let key = "\(promo.stored)|\(promo.stake ?? 0)|\(promo.maxExtra ?? 0)|\(book.rawValue)|\(mode.rawValue)|\(locks)|\(ready.joined(separator: ","))|\(Bans.current.count)"
        runKey = key
        guard !ready.isEmpty else { results = []; return }
        let (packs, bands, model, bans) = (self.packs, self.bands, self.quoteModel, Bans.current)
        let hedge = Self.hedge(book)
        let out = await Task.detached(priority: .userInitiated) {
            let pr = Pricer(packs, book: book)
            return PromoFinder.rank(Build.promoCandidates(pr, ready, promo, bands: bands, model: model, bans: bans),
                                    locks && hedge != nil ? Build.findLocks(pr, Pricer(packs, book: hedge!), ready, promo, top: 20, bans: bans) : [], promo, mode)
        }.value
        if key == runKey { results = out }
    }
    func pricer(_ book: BuildBook) -> Pricer { Pricer(packs, book: book) }

    /// A lock's other book (web hedgeOf): FanDuel hedges at DraftKings, any other book at FanDuel; with that one off,
    /// another the account has on (Nov 6), or none (no locks with one book).
    nonisolated static func hedge(_ b: BuildBook, on: [BuildBook] = BuildBook.mine) -> BuildBook? {
        [b == .fanduel ? .draftkings : .fanduel, .draftkings, .novig].first { $0 != b && on.contains($0) }
    }
}
