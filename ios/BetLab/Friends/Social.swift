import Foundation

// Friends (Mike, Oct 27): a feed of your friends' bets, their profiles, and Tail (W16) to copy one into your own bets.
// Friends come from accepted requests (supabase 0024: profiles, friendships, friend_bets); friends see bets, never
// money (units only). Ported from web/lib/social.ts: **change both together.** Pure, so SocialTests runs the web's
// cases; FriendsView loads and writes.

struct Profile: Codable, Hashable, Identifiable {
    let userId: String
    var name: String
    var handle: String
    var id: String { userId }
}

struct Friendship: Codable, Hashable {
    let requester: String
    let addressee: String
    var status: String          // pending, accepted
    var createdAt: String? = nil
    var acceptedAt: String? = nil
}

/// A reaction on a bet (supabase 0042, bet_reactions_for): who, their name when you're friends, and which of the six.
struct Reaction: Codable, Hashable {
    let betId: String
    let userId: String
    var name: String?
    var reaction: String
    var createdAt: String? = nil
}

enum Social {
    /// "@Mike_B " -> "mike_b"; nil unless 3-20 letters, digits or underscores.
    static func cleanHandle(_ s: String) -> String? {
        var h = s.trimmingCharacters(in: .whitespacesAndNewlines)
        if h.hasPrefix("@") { h.removeFirst() }
        h = h.lowercased()
        return h.range(of: #"^[a-z0-9_]{3,20}$"#, options: .regularExpression) != nil ? h : nil
    }

    /// A starting handle from a name or an email: "Sam" -> "sam", "owner@example.com" -> "owner".
    static func suggestHandle(_ from: String) -> String {
        let head = from.components(separatedBy: "@")[0].lowercased()
        let h = String(head.filter { $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_") }.prefix(20))
        return h.count >= 3 ? h : String("\(h)_bets".prefix(20))
    }

    struct Request: Identifiable { let otherId: String; let other: Profile?; var id: String { otherId } }
    struct Circle { let friends: [Profile]; let incoming: [Request]; let outgoing: [Request] }

    /// Who's who for the signed-in user: friends, requests to answer, requests waiting on someone else.
    static func circle(_ me: String, _ list: [Friendship], _ profiles: [Profile]) -> Circle {
        let who = { (id: String) in profiles.first { $0.userId == id } }
        let other = { (f: Friendship) in f.requester == me ? f.addressee : f.requester }
        let pick = { (f: (Friendship) -> Bool) in list.filter(f).map { Request(otherId: other($0), other: who(other($0))) } }
        return Circle(friends: pick { $0.status == "accepted" }.compactMap(\.other)
                        .sorted { $0.name.localizedCompare($1.name) == .orderedAscending },
                      incoming: pick { $0.status == "pending" && $0.addressee == me },
                      outgoing: pick { $0.status == "pending" && $0.requester == me })
    }

    /// How long a bet with no known game stays tailable after it was entered.
    static let noGameHours = 6.0

    /// A friend's bet you can still copy: not settled, and its game (the first, for a parlay) hasn't started; with no game
    /// known, for noGameHours after it was entered.
    static func canTail(_ b: MyBet, now: Date = Date()) -> Bool {
        if BetMath.isSettled(b) || b.liveSettled != nil { return false }
        if let s = BetMath.start(b), let d = Models.date(s) { return d > now }
        guard let placed = Models.date(b.placedAt) else { return false }
        return now.timeIntervalSince(placed) < noGameHours * 3600
    }

    /// The key that makes a bet the same bet in two accounts: the pick, or the parlay.
    static func betKey(_ b: MyBet) -> String { b.pickId.map { "p:\($0)" } ?? "s:\(b.sgpId ?? "")" }

    /// The row a tail inserts into your bets: the same pick or parlay (so it grades the same way), at the price you got
    /// and your book, 1u once your real money has started (paper before, like marking). Never the friend's bonus, boost,
    /// Bet Protect+, bet reset, cash-out or ladder: those were their slip's, not the bet.
    static func tailRow(_ b: MyBet, price: Double, book: String, real: Bool) -> [String: Any?] {
        ["kind": b.kind, "pick_id": b.pickId, "sgp_id": b.pickId == nil ? b.sgpId : nil,
         "mode": real ? "real" : "paper", "stake": real ? 1.0 : nil,
         "price": price, "book": Marking.bookOf(book), "label": b.label, "matchup": b.matchup, "fair_price": b.fairPrice, "p_fair": b.pFair,
         "legs": b.legs, "games": b.games.map { gamesRow($0) }, "odds_event_id": b.oddsEventId]
    }

    /// A bet's games as stored: my_bets arrives camelCased (gameRef), the table takes game_ref.
    private static func gamesRow(_ j: JSON) -> Any {
        j.array.map { g -> [String: Any] in
            var o: [String: Any] = [:]
            for (k, v) in g.object { o[k == "gameRef" ? "game_ref" : k] = v.any }
            return o
        }
    }

    /// The feed: friends' bets, newest first, each with who placed it.
    static func feed(_ bets: [MyBet], _ profiles: [Profile], limit: Int = 60) -> [(bet: MyBet, who: Profile)] {
        let who = Dictionary(profiles.map { ($0.userId, $0) }, uniquingKeysWith: { a, _ in a })
        return bets.filter { who[$0.userId ?? ""] != nil }
            .sorted { $0.placedAt > $1.placedAt }
            .prefix(limit)
            .map { ($0, who[$0.userId!]!) }
    }

    /// Reactions (Nov 6, 0042): one per friend per bet, drawn as its emoji, in the picker's order (web REACTIONS).
    static let reactions: [(key: String, emoji: String, say: String)] = [
        ("fire", "🔥", "Fire"), ("money", "💰", "Money"), ("sweat", "😬", "Sweating"),
        ("skull", "💀", "Dead"), ("pray", "🙏", "Praying"), ("goat", "🐐", "GOAT"),
    ]
    static func emoji(_ key: String) -> String? { reactions.first { $0.key == key }?.emoji }

    struct Chip: Equatable { let reaction: String; let emoji: String; var count: Int; var mine: Bool; var names: [String] }

    /// One bet's reactions as chips: each kind with its count and who, yours marked; most first, then the first reacted.
    /// You are "You"; a name the database didn't give (a friend's friend) is "Someone" (web tally).
    static func tally(_ list: [Reaction], me: String) -> [Chip] {
        var out: [Chip] = []
        for r in list {
            guard let e = emoji(r.reaction) else { continue }
            var i = out.firstIndex { $0.reaction == r.reaction }
            if i == nil { out.append(Chip(reaction: r.reaction, emoji: e, count: 0, mine: false, names: [])); i = out.count - 1 }
            out[i!].count += 1
            if r.userId == me { out[i!].mine = true; out[i!].names.insert("You", at: 0) } else { out[i!].names.append(r.name ?? "Someone") }
        }
        // a stable sort: the first reacted stays first among equals
        return out.enumerated().sorted { $0.element.count != $1.element.count ? $0.element.count > $1.element.count : $0.offset < $1.offset }.map(\.element)
    }

    /// What a tap does: the reaction you have again takes it back (nil); another replaces it.
    static func nextReaction(_ current: String?, _ tapped: String) -> String? { current == tapped ? nil : tapped }

    /// Who reacted, for a chip's label: "You", "Sam and Cal", "You, Sam and 2 more".
    static func whoText(_ names: [String]) -> String {
        names.count <= 2 ? names.joined(separator: " and ") : "\(names[0]), \(names[1]) and \(names.count - 2) more"
    }

    /// A steady hue (0-359) for a person's initial, from their handle.
    static func hue(_ handle: String) -> Int {
        var h = 0
        for c in handle.utf16 { h = (h * 31 + Int(c)) % 360 }
        return h
    }
}
