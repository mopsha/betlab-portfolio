import Foundation

// Home's feed, ported from web/lib/data.ts `homeData` so the app shows what the web app shows.
// Pure functions of the rows and the time: FeedTests checks them.

enum DayKey: String, CaseIterable, Identifiable {
    case today, tomorrow, week
    var id: String { rawValue }
    var title: String { ["today": "Today", "tomorrow": "Tomorrow", "week": "This week"][rawValue]! }
    var heading: String { ["today": "Tonight and today", "tomorrow": "Tomorrow", "week": "This week"][rawValue]! }
}

struct FeedGame: Identifiable, Hashable {
    let game: Game
    var offers: [Offer] = []
    var tickets: [Ticket] = []
    var id: String { game.gameId }
}

enum FeedItem: Identifiable, Hashable {
    case game(FeedGame)
    case ticket(Ticket, Slate?)

    var id: String {
        switch self {
        case .game(let g): "g-" + g.id
        case .ticket(let t, _): "t-" + t.id
        }
    }
    var at: String {
        switch self {
        case .game(let g): g.game.commenceTime ?? ""
        case .ticket(let t, _): t.commenceTime ?? ""
        }
    }
}

struct Feed {
    var items: [FeedItem] = []
    var picks: [Offer] = []
    var quiet = 0
    var sports: [String] = []
}

enum FeedLogic {
    static var et: Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = Fmt.et
        return c
    }

    /// [from, to) for the day switcher. Today starts now-ish: games that started in the last 4 hours stay
    /// in the query (the feed itself drops anything already started).
    static func window(_ day: DayKey, now: Date = Date()) -> (from: Date, to: Date) {
        let cal = et
        let start = cal.startOfDay(for: now)
        let plus = { (n: Int) in cal.date(byAdding: .day, value: n, to: start)! }
        switch day {
        case .tomorrow: return (plus(1), plus(2))
        case .today: return (max(start, now.addingTimeInterval(-4 * 3600)), plus(1))
        case .week: return (max(start, now.addingTimeInterval(-4 * 3600)), plus(7))
        }
    }

    /// Game-line leans more than 36 hours out get an "Early · unproven" tag on game pages (web/lib/early.ts, Mike, Oct 14).
    static func isEarlyLean(_ o: Offer, now: Date) -> Bool {
        guard o.tier == .lean, !(o.market ?? "").hasPrefix("player"), let t = Models.date(o.commenceTime) else { return false }
        return t.timeIntervalSince(now) > 36 * 3600
    }

    static func byEv(_ a: Offer, _ b: Offer) -> Bool {
        let rank: [Tier: Int] = [.pick: 0, .lean: 1, .check: 2]
        if rank[a.tier]! != rank[b.tier]! { return rank[a.tier]! < rank[b.tier]! }
        return (a.ev ?? 0) > (b.ev ?? 0)
    }

    static func build(games: [Game], offers: [Offer], tickets: [Ticket], slates: [Slate],
                      sport: String?, watching: Set<String> = Set(Watch.current), now: Date = Date()) -> Feed {
        let want = { (league: String) in sport == nil || league == sport }
        let future = { (iso: String?) in (Models.date(iso).map { $0 > now }) ?? false }
        let ms = { (iso: String?) in Models.date(iso)?.timeIntervalSince1970 ?? .nan }
        let lockS: TimeInterval = 25 * 60
        let slateBy = Dictionary(slates.map { ($0.slate, $0) }, uniquingKeysWith: { a, _ in a })
        // A game's own slips show for the games you watch (Mike, Nov 7: no Knicks rule, no lone prime-time rule), in
        // Parlays next to the slices' tickets once the slice locks (Watch.swift). Until then a window with an SGP+
        // ticket hid its games' slips (Oct 12) and a lone game showed its own.
        let showTicket = { (t: Ticket) in future(t.commenceTime) && t.slate.flatMap { slateBy[$0]?.lockedAt } != nil }

        var byGame: [String: FeedGame] = [:]
        var order: [String] = []
        for g in games where want(g.league) && future(g.commenceTime) {
            byGame[g.gameId] = FeedGame(game: g)
            order.append(g.gameId)
        }
        var feed = Feed()
        for o in offers {
            guard let gid = o.gameId, byGame[gid] != nil, future(o.commenceTime) else { continue }
            if o.tier == .lean { continue }     // Home shows no leans (Mike, Oct 22): they stay on each game's page and Games
            if o.tier == .pick { continue }     // picks have their own list above the games (Mike, Oct 28: not twice)
            byGame[gid]!.offers.append(o)
        }
        // a game row carries its overs to root for in the last 25 minutes (the game page lists them); slips go to Parlays
        for t in tickets where t.kind == "over" {
            guard let gid = t.gameId, byGame[gid] != nil, future(t.commenceTime),
                  ms(t.commenceTime) - now.timeIntervalSince1970 <= lockS else { continue }
            byGame[gid]!.tickets.append(t)
        }
        for k in order { byGame[k]!.offers.sort(by: byEv) }

        // Home lists picks and parlays; leans (Oct 22), "check the news" flags and overs stay on the game page.
        let acts = { (g: FeedGame) in g.offers.contains { $0.tier != .check } || g.tickets.contains { $0.kind != "over" } }
        let gamesIn = order.compactMap { byGame[$0] }
        var items: [FeedItem] = gamesIn.filter(acts).map { .game($0) }
        items += tickets.filter { want($0.sport) && (($0.gameId == nil && ($0.kind == "sgp_plus" || $0.kind == "td") && showTicket($0))
                                                     || Watch.shows($0, watching: watching, now: now)) }
            .map { .ticket($0, $0.slate.flatMap { slateBy[$0] }) }
        feed.items = items.sorted { $0.at < $1.at }
        feed.picks = offers.filter { $0.tier == .pick && want($0.league) && future($0.commenceTime) }.sorted(by: byEv)
        let withPick = Set(feed.picks.compactMap(\.gameId))
        feed.quiet = gamesIn.filter { !acts($0) && !withPick.contains($0.id) }.count
        feed.sports = Array(Set(games.map(\.league))).sorted()
        return feed
    }

    /// "Saturday noon games · SGP+ · locked" (web/app/page.tsx ticketTitle).
    static func ticketTitle(_ t: Ticket, _ s: Slate?) -> String {
        if t.kind == "sgp" {           // a watched game's own parlay (Nov 7): its game, and what kind of slip it is
            let kind = t.body.style == "single" ? "best single" : t.body.style == "longshot" || t.body.longshot == true ? "long shot" : "parlay"
            return "\(Fmt.matchup(t.matchup ?? "", sport: t.sport)) · \(kind) · watching" + (s?.lockedAt != nil ? " · locked" : "")
        }
        let what = (t.body.cup.map { "\($0) " } ?? "") + (t.kind == "td" ? "anytime TD ticket" : "SGP+") + (s?.lockedAt != nil ? " · locked" : "")
        if let title = s?.title { return "\(title) · \(what)" }
        let f = DateFormatter()
        f.timeZone = Fmt.et
        f.dateFormat = "EEEE"
        let day = Models.date(t.commenceTime).map { f.string(from: $0) } ?? ""
        let names = ["early": "early games", "late": "late games", "night": "night"]
        if let slate = s?.slate, let w = names.first(where: { slate.hasSuffix("-" + $0.key) })?.value {
            return "\(day) \(w) · \(what)"
        }
        return "\(day) · \(s?.nGames ?? t.body.games?.count ?? 0) games · \(what)"
    }
}
