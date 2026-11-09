import Foundation

// The ban list (Mike, Oct 25): players and teams BetLab never gives bets on. Games and players stay visible; a banned
// player's props and a banned team's side (moneyline, spread, to win) leave Home, the game pages, the Games counts and
// the promo finder. Totals, both-teams-to-score and a draw are on no one. Stored on the account (user_settings.bans), so
// the web and the worker read the same list. Ported from src/betlab/bans.py and web/lib/bans.ts; all three run
// tests/fixtures/bans.json, and teams.json is the same file in all three. **Change them together.**

struct Ban: Codable, Hashable, Identifiable {
    var kind: String                 // "player" | "team"
    var name: String
    var league: String? = nil
    var id: String { kind + "|" + name.lowercased() }
    var row: [String: Any] { league.map { ["kind": kind, "name": name, "league": $0] } ?? ["kind": kind, "name": name] }
}

enum Bans {
    /// The signed-in account's list, kept by BetStore; the models filter what they load with it.
    @MainActor static var current: [Ban] = []

    struct TeamRow: Decodable { let name: String; let abbr: [String] }
    static let teams: [String: [TeamRow]] = {
        guard let url = Bundle.main.url(forResource: "teams", withExtension: "json"), let d = try? Data(contentsOf: url) else { return [:] }
        return (try? JSONDecoder().decode([String: [TeamRow]].self, from: d)) ?? [:]
    }()
    static let leagueNames = ["nfl": "NFL", "nba": "NBA", "nhl": "NHL"]
    /// Every team in the table, for the picker: (league, full name).
    static var teamNames: [(league: String, name: String)] {
        teams.keys.sorted().flatMap { lg in teams[lg]!.map { (lg, $0.name) } }
    }

    private static let club: Set<String> = ["fc", "cf", "afc", "sc", "ac"]
    private static func words(_ s: String?) -> [String] { Live.plain(s).split(separator: " ").map(String.init).filter { !club.contains($0) } }

    /// The stored list as entries we can match.
    static func clean(_ raw: JSON?) -> [Ban] {
        (raw?.array ?? []).compactMap { b in
            guard let k = b["kind"].string, k == "player" || k == "team", let n = b["name"].string, !Live.plain(n).isEmpty else { return nil }
            let lg = b["league"].string
            return Ban(kind: k, name: n.trimmingCharacters(in: .whitespaces), league: (lg?.isEmpty ?? true) ? nil : lg)
        }
    }

    /// The NFL/NBA/NHL teams a text names ("NYJ", "Jets", "New York Jets"), as "league:Full Name".
    static func teamKeys(_ text: String?, league: String? = nil) -> Set<String> {
        let t = words(text)
        guard !t.isEmpty else { return [] }
        var out = Set<String>()
        for (lg, rows) in teams where league == nil || lg == league {
            for r in rows {
                let full = words(r.name)
                if t == full || (t.count == 1 && r.abbr.contains { Live.plain($0) == t[0] })
                    || Array(full.suffix(t.count)) == t || Array(full.prefix(t.count)) == t { out.insert("\(lg):\(r.name)") }
            }
        }
        return out
    }

    static func teamHit(_ ban: String, _ ours: String, league: String? = nil, banLeague: String? = nil) -> Bool {
        if let b = banLeague, let l = league, b != l { return false }
        let bk = teamKeys(ban, league: banLeague ?? league), ok = teamKeys(ours, league: league ?? banLeague)
        if !bk.isEmpty || !ok.isEmpty { return !bk.isDisjoint(with: ok) }
        let b = words(ban), o = words(ours)
        return !b.isEmpty && b.count <= o.count && (Array(o.prefix(b.count)) == b || Array(o.suffix(b.count)) == b)
    }

    static func playerHit(_ ban: String, _ ours: String) -> Bool {
        let b = Live.normName(ban).split(separator: " ").map(String.init), o = Live.normName(ours).split(separator: " ").map(String.init)
        guard let bl = b.last, let ol = o.last else { return false }
        if b == o { return true }
        if b.count == 1 { return ol == b[0] }
        guard bl == ol else { return false }
        return (b[0].count == 1 || o[0].count == 1) && b[0].first == o[0].first
    }

    private static func contains(_ label: String, _ name: String) -> Bool { " \(Live.plain(label)) ".contains(" \(Live.plain(name)) ") }

    /// The ban a leg or bet runs into, else nil. `player` is the leg's player when the feed gives one.
    static func hit(_ bans: [Ban], _ label: String, league: String? = nil, player: String? = nil) -> Ban? {
        guard !bans.isEmpty else { return nil }
        let leg = Live.parseLeg(label)
        var who = player.flatMap { $0.isEmpty ? nil : $0 }
        var team: String?
        switch leg {
        case .total?, .btts?, .bttsNo?, .draw?, .noDraw?: return nil
        case .prop(let p, _, _, _, _)?, .td(let p, _)?, .goalOrAssist(let p)?, .double(let p, _)?, .leader(let p, _)?, .card(let p)?, .first(let p, _)?: who = who ?? p
        case .ml(let t)?, .spread(let t, _)?, .drawOr(let t)?, .notWin(let t)?: team = t
        case nil: break
        }
        if Live.plain(label) == "draw" { return nil }
        for b in bans {
            if b.kind == "player" {
                if let w = who, playerHit(b.name, w) { return b }
                if who == nil && leg == nil && contains(label, b.name) { return b }
            } else if let t = team {
                if teamHit(b.name, t, league: league, banLeague: b.league) { return b }
            } else if leg == nil && who == nil && contains(label, b.name) {
                return b
            }
        }
        return nil
    }

    static func banned(_ bans: [Ban], _ label: String, league: String? = nil, player: String? = nil) -> Bool {
        hit(bans, label, league: league, player: player) != nil
    }

    /// A ticket, slip or over with a banned leg: its legs, else its games' legs, else its label.
    static func banned(_ bans: [Ban], ticket t: Ticket) -> Bool {
        guard !bans.isEmpty else { return false }
        let legs = (t.body.legs?.isEmpty == false ? t.body.legs! : (t.body.games ?? []).flatMap(\.legs))
        if !legs.isEmpty { return legs.contains { banned(bans, $0.label, league: t.sport, player: $0.player) } }
        return t.body.label.map { banned(bans, $0, league: t.sport) } ?? false
    }

    /// The offers and tickets with no bet on a banned player or team.
    static func filter(_ offers: [Offer], _ tickets: [Ticket], _ bans: [Ban]) -> ([Offer], [Ticket]) {
        guard !bans.isEmpty else { return (offers, tickets) }
        return (offers.filter { !banned(bans, $0.label, league: $0.league, player: $0.player) },
                tickets.filter { !banned(bans, ticket: $0) })
    }
}
