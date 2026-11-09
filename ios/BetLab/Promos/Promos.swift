import SwiftUI

// More > Promos (web app/more/promos, components/promos/PromoWallet.tsx and lib/promos.ts, Oct 30; migration 0029): the bonus
// bets and profit boosts you hold, soonest to expire first. Add one by typing its terms or from a screenshot of the
// book's promos screen (the web's /api/promos reads it); Use opens the finder with it (Build), and the bet you place
// with it marks it used. One fixture for both apps: tests/fixtures/promos.json. The screens are in WalletView.swift.

/// A game picked for a token from the schedule (Nov 5, migration 0039): ESPN's row, known days before the odds are.
struct PromoGame: Decodable, Hashable {
    var eventId: String
    var matchup: String
    var commenceTime: String
    var sport: String? = nil
}

struct PromoRow: Decodable, Identifiable, Hashable {
    var promoId: String = ""
    var kind: String = "bonus"               // bonus | boost
    var book: String? = nil
    var amountDollars: Double? = nil         // a bonus bet's face; a boost's max wager
    var pct: Double? = nil
    var maxExtraDollars: Double? = nil
    var minLegs: Int? = nil
    var minOdds: Double? = nil
    var maxOdds: Double? = nil
    var sports: [String]? = nil
    var teams: [String]? = nil               // a token for some games only: the teams it names (Oct 31, migration 0030)
    var market: String? = nil                // a token for one market (Build.marketChoices), Nov 5
    var games: [PromoGame]? = nil            // and for the games picked from the board
    var legKinds: [String]? = nil            // and for certain kinds of leg (Promos.legChoices), Nov 9, migration 0047
    var note: String? = nil
    var expiresAt: String? = nil
    var status: String = "open"              // open | used | void
    var source: String? = nil
    var createdAt: String? = nil
    var problem: String? = nil               // a draft read off a screenshot: why it can't be kept as read (web promoDraft)
    var id: String { promoId }

    /// The row the database takes (web cleanPromo has checked it).
    /// Dollars to the cent, as a decimal (Nov 9: a Double went out as 10.609999999999999 for a $10.61 bonus bet).
    static func cents(_ v: Double?) -> NSDecimalNumber? {
        v.map { NSDecimalNumber(string: String(format: "%.2f", $0)) }
    }

    var row: [String: Any?] {
        ["kind": kind, "book": book, "amount_dollars": PromoRow.cents(amountDollars), "pct": kind == "boost" ? pct : nil,
         "max_extra_dollars": kind == "boost" ? PromoRow.cents(maxExtraDollars) : nil, "min_legs": minLegs, "min_odds": minOdds,
         "max_odds": maxOdds, "sports": sports, "teams": Promos.splitTeams(teams ?? []), "market": market,
         "games": (games ?? []).isEmpty ? nil : games!.map { ["event_id": $0.eventId, "matchup": $0.matchup, "commence_time": $0.commenceTime, "sport": $0.sport ?? ""] },
         "leg_kinds": (legKinds ?? []).isEmpty ? nil : legKinds, "note": note, "expires_at": expiresAt, "source": source ?? "typed"]
    }
}

/// Every field optional when it's read (Nov 9): the synthesized decoder ignored the defaults and required promo_id and status,
/// which a screenshot's drafts never had, so every read on the iPhone failed to decode and said "Couldn't read those screenshots."
extension PromoRow {
    enum CodingKeys: String, CodingKey {
        case promoId, kind, book, amountDollars, pct, maxExtraDollars, minLegs, minOdds, maxOdds, sports, teams, market, games, legKinds, note,
             expiresAt, status, source, createdAt, problem
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func str(_ k: CodingKeys) -> String? { (try? c.decodeIfPresent(String.self, forKey: k)) ?? nil }
        func dbl(_ k: CodingKeys) -> Double? { (try? c.decodeIfPresent(Double.self, forKey: k)) ?? nil }
        func strs(_ k: CodingKeys) -> [String]? { (try? c.decodeIfPresent([String].self, forKey: k)) ?? nil }
        self.init()
        promoId = str(.promoId) ?? ""
        kind = str(.kind) ?? "bonus"
        book = str(.book)
        amountDollars = dbl(.amountDollars); pct = dbl(.pct); maxExtraDollars = dbl(.maxExtraDollars)
        minLegs = dbl(.minLegs).map { Int($0.rounded()) }
        minOdds = dbl(.minOdds); maxOdds = dbl(.maxOdds)
        sports = strs(.sports); teams = strs(.teams); market = str(.market)
        games = (try? c.decodeIfPresent([PromoGame].self, forKey: .games)) ?? nil
        legKinds = strs(.legKinds)
        note = str(.note); expiresAt = str(.expiresAt)
        status = str(.status) ?? "open"
        source = str(.source); createdAt = str(.createdAt); problem = str(.problem)
    }
}

enum Promos {
    /// The wager on a token (Nov 3; web wagerOf): what was typed, at most its max; blank or nonsense is the max.
    static func wager(_ typed: String, max: Double?) -> Double? {
        let m = (max ?? 0) > 0 ? max : nil
        guard let n = Double(typed.trimmingCharacters(in: .whitespaces)), n > 0 else { return m }
        return m.map { Swift.min(n, $0) } ?? n
    }

    /// What's left of a bonus bet after this wager, in cents (web bonusLeft). A boost has none: it's used once.
    static func bonusLeft(_ face: Double?, _ wager: Double) -> Double {
        let left = (((face ?? 0) - wager) * 100).rounded() / 100
        return left >= 0.01 ? left : 0
    }

    static func date(_ s: String?) -> Date? { s.flatMap { Models.date($0) } }

    /// Open, used, voided by hand, or expired (an open token past its expiry; never stored).
    static func state(_ p: PromoRow, now: Date = Date()) -> String {
        guard p.status == "open" else { return p.status }
        if let e = date(p.expiresAt), e <= now { return "expired" }
        return "open"
    }

    /// The wallet: open tokens soonest-expiring first (no expiry last), then the rest newest first.
    static func wallet(_ rows: [PromoRow], now: Date = Date()) -> (open: [PromoRow], done: [PromoRow]) {
        let exp = { (p: PromoRow) in date(p.expiresAt)?.timeIntervalSince1970 ?? .infinity }
        let open = rows.filter { state($0, now: now) == "open" }
            .sorted { exp($0) != exp($1) ? exp($0) < exp($1) : ($0.createdAt ?? "") < ($1.createdAt ?? "") }
        let done = rows.filter { state($0, now: now) != "open" }
            .sorted { ($0.expiresAt ?? $0.createdAt ?? "") > ($1.expiresAt ?? $1.createdAt ?? "") }
        return (open, done)
    }

    /// Open tokens that expire within `hours` (My bets' expiring soon, Home's chip).
    static func expiringSoon(_ rows: [PromoRow], now: Date = Date(), hours: Double = 48) -> [PromoRow] {
        wallet(rows, now: now).open.filter { p in date(p.expiresAt).map { $0.timeIntervalSince(now) <= hours * 3600 } ?? false }
    }

    /// The sports a token can be used on; nil for any. Its `sports`, else the sports its note names (Oct 30: "NBA Only"
    /// in a note; web promoSports, same order).
    static let sportChoices: [(String, String)] = [("nfl", "NFL"), ("nba", "NBA"), ("nhl", "NHL"), ("ncaaf", "CFB"),
                                                   ("ncaab", "CBB"), ("soccer", "Soccer"), ("ufc", "UFC")]
    private static let noteSports: [(String, String)] = [
        (#"\bcbb\b|\bncaab\b|\bcollege basketball\b|\bncaa basketball\b|\bncaam\b"#, "ncaab"),
        (#"\bcollege football\b|\bcfb\b|\bncaaf\b"#, "ncaaf"),
        (#"\bnba\b"#, "nba"), (#"\bnfl\b"#, "nfl"), (#"\bnhl\b|\bhockey\b"#, "nhl"),
        (#"\bsoccer\b|\bepl\b|\bpremier league\b|\bla liga\b|\bserie a\b|\bbundesliga\b|\bligue 1\b|\bmls\b|\bchampions league\b|\bucl\b"#, "soccer"),
        (#"\bufc\b|\bmma\b"#, "ufc"),
    ]
    static func sports(_ p: PromoRow) -> [String]? {
        if let s = p.sports, !s.isEmpty { return s }
        let note = p.note ?? ""
        var found: [String] = []
        for (re, sp) in noteSports where note.range(of: re, options: [.regularExpression, .caseInsensitive]) != nil && !found.contains(sp) { found.append(sp) }
        return found.isEmpty ? nil : found
    }

    /// A token for some games only (Oct 31, Mike: "boosts for specific games"): its teams, typed as "Knicks, Celtics" or
    /// "Knicks vs Celtics", split into single teams (web splitTeams).
    static func splitTeams(_ texts: [String]) -> [String]? {
        var out: [String] = []
        for t in texts {
            let parts = t.replacingOccurrences(of: #",|\s+(?:vs\.?|v\.?|@|at)\s+|\s*/\s*"#, with: "\u{1}", options: [.regularExpression, .caseInsensitive])
                .split(separator: "\u{1}").map { $0.trimmingCharacters(in: .whitespaces) }
            for x in parts where !x.isEmpty && !out.contains(x) { out.append(x) }
        }
        return out.isEmpty ? nil : out
    }
    private static func teamWords(_ s: String) -> [String] {
        s.folding(options: .diacriticInsensitive, locale: nil).lowercased()
            .split { !($0.isASCII && ($0.isLetter || $0.isNumber)) }.map(String.init)
    }
    /// Is this game ("Away @ Home") one the token is for? Any of its teams whose words are all in one side's name; no
    /// teams fits every game (web teamFits).
    static func teamFits(_ teams: [String]?, _ matchup: String) -> Bool {
        guard let teams, !teams.isEmpty else { return true }
        let sides = matchup.replacingOccurrences(of: #"\s+@\s+|\s+vs\.?\s+"#, with: "\u{1}", options: [.regularExpression, .caseInsensitive])
            .split(separator: "\u{1}").map { teamWords(String($0)) }
        return teams.contains { t in let w = teamWords(t); return !w.isEmpty && sides.contains { s in w.allSatisfy { s.contains($0) } } }
    }

    /// I used it (Oct 31: Mike's $5 Novig bonus went on a bet saved without the token): the bets a token may have gone
    /// on. Real ones with no token yet, at its book (any when it names none), from the last `days`; those already marked
    /// as this kind (bonus, or boosted) first, then newest; at most 8 (web usedOnChoices).
    static func usedOnChoices(_ p: PromoRow, _ bets: [MyBet], now: Date = Date(), days: Double = 7) -> [MyBet] {
        let since = now.addingTimeInterval(-days * 86400)
        let flagged = { (b: MyBet) in p.kind == "bonus" ? b.bonus == true : b.boost != nil }
        return Array(bets.filter { b in
            b.mode == "real" && b.promoId == nil && (p.book == nil || b.book == p.book) && (Models.date(b.placedAt).map { $0 >= since } ?? false)
        }.sorted { a, b in
            flagged(a) != flagged(b) ? flagged(a) : (Models.date(a.placedAt) ?? .distantPast) > (Models.date(b.placedAt) ?? .distantPast)
        }.prefix(8))
    }

    /// The token as the finder takes it (Builder.swift Promo).
    static func asPromo(_ p: PromoRow) -> Promo {
        var out = p.kind == "boost" ? Promo.boost(p.pct ?? 0) : Promo.bonus
        out.stake = p.amountDollars; out.minLegs = p.minLegs; out.minOdds = p.minOdds; out.maxOdds = p.maxOdds; out.market = p.market
        if let k = p.legKinds, !k.isEmpty { out.kinds = k }
        if p.kind == "boost" { out.maxExtra = p.maxExtraDollars }
        return out
    }

    static func dollars(_ n: Double) -> String { n.rounded() == n ? "$\(Int(n))" : String(format: "$%.2f", n) }

    /// "$50 bonus bet", "30% profit boost".
    static func title(_ p: PromoRow) -> String {
        if p.kind == "bonus" { return (p.amountDollars.map { "\(dollars($0)) " } ?? "") + "bonus bet" }
        return "\(p.pct.map { String(format: "%g", $0) } ?? "?")% profit boost"
    }

    /// Its terms in one line: "up to $25 · max $10 extra · 3+ legs · −200 or longer · NFL".
    static func terms(_ p: PromoRow) -> String {
        var parts: [String] = []
        if p.kind == "boost", let a = p.amountDollars { parts.append("up to \(dollars(a))") }
        if let c = p.maxExtraDollars { parts.append("max \(dollars(c)) extra") }
        if let l = p.minLegs, l > 1 { parts.append("\(l)+ legs") }
        switch (p.minOdds, p.maxOdds) {
        case let (lo?, hi?): parts.append("\(Fmt.am(lo)) to \(Fmt.am(hi))")
        case let (lo?, nil): parts.append("\(Fmt.am(lo)) or longer")
        case let (nil, hi?): parts.append("\(Fmt.am(hi)) or shorter")
        default: break
        }
        if let s = sports(p) { parts.append(s.map { k in sportChoices.first { $0.0 == k }?.1 ?? k.uppercased() }.joined(separator: ", ")) }
        if let m = p.market { parts.append(marketName(m)) }
        if let k = p.legKinds, !k.isEmpty { parts.append("\(k.map(legKindName).joined(separator: " or ")) only") }
        if let g = p.games, !g.isEmpty { parts.append(g.map(\.matchup).joined(separator: ", ")) }
        if let t = p.teams, !t.isEmpty { parts.append("\(t.joined(separator: ", ")) games") }
        return parts.joined(separator: " · ")
    }

    static func marketName(_ k: String) -> String { Build.marketChoices.first { $0.0 == k }?.1 ?? k }
    /// Is this game one the token is for? Its picked games and its teams' games both count; neither fits any game (web tokenFitsGame).
    static func fitsGame(_ p: PromoRow, eventId: String, matchup: String, start: String = "") -> Bool {
        fitsGame(teams: p.teams, games: p.games, eventId: eventId, matchup: matchup, start: start)
    }
    static func fitsGame(teams: [String]?, games: [PromoGame]?, eventId: String, matchup: String, start: String = "") -> Bool {
        let t = teams ?? [], g = games ?? []
        if t.isEmpty && g.isEmpty { return true }
        return g.contains { $0.eventId == eventId || (!start.isEmpty && sameGame($0.matchup, $0.commenceTime, matchup, start)) }
            || (!t.isEmpty && teamFits(t, matchup))
    }
    /// The same game, written two ways (ESPN's schedule, the odds feed's pack): within 3 hours, with a side in common (web sameGame).
    static func sameGame(_ a: String, _ aStart: String, _ b: String, _ bStart: String) -> Bool {
        guard let x = date(aStart), let y = date(bStart), abs(x.timeIntervalSince(y)) <= 3 * 3600 else { return false }
        func sides(_ m: String) -> [[String]] {
            m.replacingOccurrences(of: #"\s+vs\.?\s+"#, with: " @ ", options: [.regularExpression, .caseInsensitive])
                .components(separatedBy: " @ ").map(sideWords).filter { !$0.isEmpty }
        }
        let inside = { (p: [String], q: [String]) in p.allSatisfy { q.contains($0) } }
        return sides(a).contains { p in sides(b).contains { q in inside(p, q) || inside(q, p) } }
    }
    /// A side's words, a code read as its team's name: the NHL's packs say "CGY @ SEA".
    private static func sideWords(_ side: String) -> [String] {
        let code = side.trimmingCharacters(in: .whitespaces).uppercased()
        let row = Bans.teams.values.joined().first { $0.abbr.contains(code) }
        return teamWords(row?.name ?? side)
    }
    /// "Thu 7:40 PM"; a game in the dropdown says just its time, under its day ("Thu Nov 5").
    static func gameTime(_ iso: String) -> String { date(iso).map { fmt("EEE h:mm a").string(from: $0) } ?? "" }
    static func clock(_ iso: String) -> String { date(iso).map { fmt("h:mm a").string(from: $0) } ?? "" }
    static func gameDay(_ iso: String) -> String { date(iso).map { fmt("EEE MMM d").string(from: $0) } ?? "" }

    private static func fmt(_ format: String) -> DateFormatter {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = Fmt.et; f.dateFormat = format
        return f
    }

    /// "expires in 5 h", "expires today 11:59 PM", "expires Sun", "expired Oct 28", or "" with no expiry.
    static func expires(_ p: PromoRow, now: Date = Date()) -> String {
        guard let t = date(p.expiresAt) else { return "" }
        let s = t.timeIntervalSince(now)
        if s <= 0 { return "expired \(fmt("MMM d").string(from: t))" }
        if s < 12 * 3600 { return "expires in \(max(1, Int((s / 3600).rounded()))) h" }
        if fmt("yyyy-MM-dd").string(from: t) == fmt("yyyy-MM-dd").string(from: now) { return "expires today \(fmt("h:mm a").string(from: t))" }
        if s < 6 * 86400 { return "expires \(fmt("EEE").string(from: t))" }
        return "expires \(fmt("MMM d").string(from: t))"
    }

    /// A typed or read token, checked before it's saved (web cleanPromo): a reason when it can't be one.
    static func problem(_ p: PromoRow) -> String? {
        if p.kind == "boost", !((p.pct ?? 0) > 0 && (p.pct ?? 0) <= 500) { return "A boost needs its size, 1 to 500%." }
        if p.kind == "bonus", !((p.amountDollars ?? 0) > 0) { return "A bonus bet needs its dollar amount." }
        if let a = p.amountDollars, a <= 0 { return "Dollars must be above 0." }
        return nil
    }

    /// A sports list as the finder's keys: "NFL ", "CFB" or "College Football" read as nfl and ncaaf, anything else dropped
    /// (web cleanSports).
    static func cleanSports(_ list: [String]?) -> [String]? {
        let keys = sportChoices.map(\.0)
        var out: [String] = []
        for raw in list ?? [] {
            let s = raw.trimmingCharacters(in: .whitespaces).lowercased()
            let hit = keys.contains(s) ? [s] : noteSports.filter { s.range(of: $0.0, options: [.regularExpression, .caseInsensitive]) != nil }.map(\.1)
            for k in hit where !out.contains(k) { out.append(k) }
        }
        return out.isEmpty ? nil : out
    }

    /// The kinds of leg a token can be for (Nov 9, Mike: "boosts like td only or first td only"; migration 0047; web LEG_CHOICES),
    /// in the Build packs' stat names, so the finder tests each candidate leg (Build.marketFits). Every leg of the bet must be one.
    /// "first_td" is kept and shown, but no pack prices a first TD, so the finder says it can't build one (`unpricedKinds`).
    static let legChoices: [(String, String)] = [("tds", "Anytime TD"), ("first_td", "First TD"), ("passing_yards", "Passing yards"),
        ("rushing_yards", "Rushing yards"), ("receiving_yards", "Receiving yards"), ("receptions", "Receptions"), ("points", "Points"),
        ("rebounds", "Rebounds"), ("assists", "Assists"), ("threes", "Threes"), ("pra", "Pts + reb + ast"), ("shots", "Shots"),
        ("saves", "Saves"), ("goals", "Goals")]
    private static let unpricedKindKeys = ["first_td"]
    static func legKindName(_ k: String) -> String { legChoices.first { $0.0 == k }?.1 ?? k }
    /// A leg-kinds list as legChoices keys ("anytime td" and "TD scorer" read as tds); anything else dropped, none left is nil
    /// (web cleanKinds, tests/fixtures/promos.json `clean_kinds`).
    static func cleanKinds(_ list: [String]?) -> [String]? {
        var out: [String] = []
        for raw in list ?? [] {
            let s = raw.trimmingCharacters(in: .whitespaces).lowercased()
                .replacingOccurrences(of: #"[\s-]+"#, with: "_", options: .regularExpression)
            let k: String? = legChoices.contains { $0.0 == s } ? s
                : s.range(of: #"first_?(td|touchdown)"#, options: .regularExpression) != nil ? "first_td"
                : s.range(of: #"(anytime_)?(td|touchdown)(_scorer)?s?$"#, options: .regularExpression) != nil ? "tds" : nil
            if let k, !out.contains(k) { out.append(k) }
        }
        return out.isEmpty ? nil : out
    }
    /// The kinds a token allows that no pack prices: all of them means the finder can't build a bet for it (web unpricedKinds).
    static func unpricedKinds(_ p: PromoRow) -> [String] { (p.legKinds ?? []).filter { unpricedKindKeys.contains($0) } }

    /// A typed or read token, checked and cleaned before it's saved (Nov 9; web cleanPromo, tests/fixtures/promos.json `clean`):
    /// the row, or why it can't be one. A 0 cap, legs outside 1 to 20 and odds under 100 are dropped, as the database refuses them.
    static func clean(_ p: PromoRow) -> (row: PromoRow?, error: String?) {
        guard p.kind == "bonus" || p.kind == "boost" else { return (nil, "Pick bonus bet or profit boost.") }
        if let e = problem(p) { return (nil, e) }
        var r = p
        let book = p.book?.trimmingCharacters(in: .whitespaces) ?? ""
        r.book = book.isEmpty ? nil : Marking.books.first { $0.lowercased() == book.lowercased() } ?? book
        if r.kind != "boost" { r.pct = nil; r.maxExtraDollars = nil }
        if let c = r.maxExtraDollars, !(c > 0) { r.maxExtraDollars = nil }
        if let l = r.minLegs, !(1...20).contains(l) { r.minLegs = nil }
        if let o = r.minOdds, abs(o) < 100 { r.minOdds = nil }
        if let o = r.maxOdds, abs(o) < 100 { r.maxOdds = nil }
        r.sports = cleanSports(r.sports)
        r.teams = splitTeams(r.teams ?? [])
        if let m = r.market, !Build.marketChoices.contains(where: { $0.0 == m }) { r.market = nil }
        let note = r.note?.trimmingCharacters(in: .whitespaces) ?? ""
        r.note = note.isEmpty ? nil : note
        if let g = r.games, g.isEmpty { r.games = nil }
        r.legKinds = cleanKinds(r.legKinds)
        r.problem = nil
        return (r, nil)
    }

    /// Can this token go on a bet now? Nil when it can, else why not (Nov 9; web promoUsable).
    static func usable(_ p: PromoRow?, now: Date = Date()) -> String? {
        guard let p else { return "That promo is gone." }
        switch state(p, now: now) {
        case "open": return nil
        case "used": return "That promo is already used."
        case "expired": return "That promo has ended."
        default: return "That promo is set aside: bring it back first."
        }
    }

    /// A slip read from a screenshot (Nov 9; web slipTokens): the open wallet tokens it may have used. Kind and book must match (a
    /// token for any book fits any), a boost's size when both say it, the wager at most its dollars, its fewest legs and its odds;
    /// an exact dollar match first, then soonest to end. The draft preselects one only when exactly one fits.
    static func slipTokens(book: String, bonus: Bool, boost: Double?, stake: Double, price: Double?, legs: Int?, _ rows: [PromoRow],
                           now: Date = Date()) -> [PromoRow] {
        let kind = bonus ? "bonus" : (boost ?? 0) > 0 ? "boost" : nil
        guard let kind else { return [] }
        let dec = price.flatMap { abs($0) >= 100 ? Odds.dec($0) : nil }
        let fits = { (p: PromoRow) -> Bool in
            guard p.kind == kind, p.book == nil || p.book == book else { return false }
            if kind == "boost", let pct = p.pct, abs(pct - (boost ?? 0)) >= 0.01 { return false }
            if let a = p.amountDollars, stake > a + 0.004 { return false }
            if let l = p.minLegs, let legs, legs < l { return false }
            if let dec {
                if let lo = p.minOdds, dec < Odds.dec(lo) - 1e-9 { return false }
                if let hi = p.maxOdds, dec > Odds.dec(hi) + 1e-9 { return false }
            }
            return true
        }
        let exact = { (p: PromoRow) in abs((p.amountDollars ?? -1) - stake) < 0.005 }
        let open = wallet(rows, now: now).open.filter(fits)
        return open.filter(exact) + open.filter { !exact($0) }
    }
}
