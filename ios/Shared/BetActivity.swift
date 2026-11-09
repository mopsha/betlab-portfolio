import ActivityKit
import Foundation

// A real bet live on the lock screen and in the Dynamic Island (Mike's #3 in docs/IDEAS.md, Oct 27). The worker starts,
// updates and ends each one over Apple's push service (src/betlab/live_activity.py, every minute from the leg alerts'
// judging); the app only saves the tokens Apple hands it (LiveActivities.swift). Shared by the app and the widget
// extension. The worker writes ContentState's JSON by these exact keys: **change both together.**
struct BetActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var status: String          // pending, live, won, lost, final (every game over, the grader still to come)
        var hit: Int
        var total: Int
        var games: [Game]
        var legs: [Leg]
        var more: Int               // legs past the ones sent
        var note: String?           // the latest event: "Leg hit: Josh Allen 2+ passing TDs"
    }

    struct Game: Codable, Hashable {
        var away: String
        var home: String
        var awayScore: String?
        var homeScore: String?
        var state: String           // pre, in, post
        var detail: String          // "Q3 4:12", "Final"
        var awayColor: String? = nil   // "#rrggbb" from ESPN, for the scoreboard band (Oct 27)
        var homeColor: String? = nil
        var awayLogo: String? = nil    // ESPN's logo, saved into the App Group by the app (LogoStore)
        var homeLogo: String? = nil
    }

    struct Leg: Codable, Hashable {
        var label: String
        var status: String          // pending, live, winning, losing, tied, won, lost, void, unknown
        var value: String?          // "62/75 yds"
        var progress: Double?       // 0...1 toward a prop's target
        var game: Int? = nil        // its game in `games`, to sit under that scoreboard as the tracker shows it
    }

    var betId: String
    var name: String                // "4-leg parlay (+1200)"
    var book: String?
    var toWin: String? = nil        // "10.48u", boost included (activities started before Oct 27's build have none)
}

extension BetActivityAttributes.ContentState {
    var over: Bool { status == "won" || status == "lost" || status == "final" }
}
