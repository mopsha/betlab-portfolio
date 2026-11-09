import Foundation

/// Watched games (Nov 7, supabase 0045; Mike: "you should be able to signify games you are going to watch and then it
/// gives you parlays for that game, so we don't need a strict knicks rule anymore or a strict prime time nfl rule").
/// Every slice carries its games' own same-game slips; each game's lock by its own start, and Today shows a watched game's
/// from then, with the worker's alert. Ported from web lib/watch.ts: **change them together**, on
/// tests/fixtures/watch.json.
enum Watch {
    /// The signed-in account's watched games, by game id (BetStore sets it from user_settings, like BooksOff.current).
    nonisolated(unsafe) static var current: [String] = []

    static let lockS: TimeInterval = 25 * 60

    /// Whether Today shows this single-game slip: its game is watched, it hasn't started, and its own lock time (25 minutes
    /// before its start) has come. A game's slips lock by their game, never the slice (Mike, Nov 7: "locks on a sgp
    /// shouldn't depend on slices at all"; the worker's sgp_plus.lock_slips).
    static func shows(_ t: Ticket, watching: Set<String>, now: Date = Date()) -> Bool {
        guard t.kind == "sgp", let gid = t.gameId, watching.contains(gid),
              let at = Models.date(t.commenceTime), at > now else { return false }
        return at.timeIntervalSince(now) <= lockS
    }

    /// The watched games' locks still ahead, one per game: "Knicks @ Cavaliers slips" at its start minus 25 minutes.
    static func locks(_ tickets: [Ticket], watching: Set<String>, now: Date = Date()) -> [GameDay.Lock] {
        var seen = Set<String>(), out: [GameDay.Lock] = []
        for t in tickets where t.kind == "sgp" {
            guard let gid = t.gameId, watching.contains(gid), !seen.contains(gid),
                  let start = Models.date(t.commenceTime) else { continue }
            seen.insert(gid)
            let at = start.addingTimeInterval(-lockS)
            if at > now { out.append(GameDay.Lock(slate: "game:\(gid)", title: "\(nicks(t.matchup)) slips", at: at)) }
        }
        return out
    }

    /// The account's watched games with one game turned on or off.
    static func toggled(_ watching: [String], _ gameId: String, on: Bool) -> [String] {
        let rest = watching.filter { $0 != gameId }
        return on ? rest + [gameId] : rest
    }

    /// "Bengals @ Falcons": a matchup by its teams' last words, short enough for a shelf card's chip (web page.tsx nicks).
    static func nicks(_ matchup: String?) -> String {
        (matchup ?? "").components(separatedBy: " @ ").map { $0.split(separator: " ").last.map(String.init) ?? $0 }
            .joined(separator: " @ ")
    }
}
