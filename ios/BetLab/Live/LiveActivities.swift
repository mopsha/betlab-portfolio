import ActivityKit
import UIKit

/// Live Activities (Mike's #3, Oct 27): a real bet live on the lock screen and in the Dynamic Island, started, updated
/// and ended by the worker over Apple's push service (src/betlab/live_activity.py) while its games are on. The app's part
/// is the tokens: Apple gives this iPhone a push-to-start token, and each activity the worker starts its own update
/// token; both go to `live_activity_tokens` (migration 0025, kind 'start' or 'update'). Apple can start an activity with
/// the app in the background, so this runs from launch (AppDelegate), signed in through the Keychain session
/// (`AuthStore.shared`), not from a screen. The look is BetLabWidgets/BetLiveActivity.swift.
@MainActor
final class LiveActivities {
    static let shared = LiveActivities()
    private var running = false
    private var watching: Set<String> = []
    private let api = SupabaseClient(token: { try await AuthStore.shared.accessToken() })

    func start() {
        guard !running else { return }
        running = true
        Task { for await t in Activity<BetActivityAttributes>.pushToStartTokenUpdates { await save(t, bet: nil) } }
        Task { for await a in Activity<BetActivityAttributes>.activityUpdates { watch(a) } }
        for a in Activity<BetActivityAttributes>.activities { watch(a) }
        Task { await forgetGone() }
        // testing hook: `-demoActivity YES` starts a sample one on this device (Claude's simulator checks)
        if UserDefaults.standard.bool(forKey: "demoActivity") { demo() }
    }

    private func demo() {
        typealias A = BetActivityAttributes
        let s = A.ContentState(status: "live", hit: 1, total: 6,
                               games: [.init(away: "BKN", home: "BOS", awayScore: "18", homeScore: "24", state: "in", detail: "4:12 - 1st",
                                             awayColor: "#000000", homeColor: "#008348",
                                             awayLogo: "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/bkn.png",
                                             homeLogo: "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/bos.png"),
                                       .init(away: "DET", home: "NY", awayScore: nil, homeScore: nil, state: "pre", detail: "8:00 PM",
                                             awayColor: "#1d42ba", homeColor: "#f58426",
                                             awayLogo: "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/det.png",
                                             homeLogo: "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/ny.png")],
                               legs: [.init(label: "Derrick White 5+ assists", status: "live", value: "3/5 ast", progress: 0.6, game: 0),
                                      .init(label: "Payton Pritchard over 9.5 points", status: "won", value: "10/10 pts", progress: 1, game: 0),
                                      .init(label: "Mitchell Robinson over 5.5 points", status: "pending", value: "0/6 pts", progress: nil, game: 1),
                                      .init(label: "Jalen Brunson over 1.5 threes", status: "pending", value: "0/2 3s", progress: nil, game: 1),
                                      .init(label: "Cade Cunningham 8+ assists", status: "pending", value: "0/8 ast", progress: nil, game: 1),
                                      .init(label: "Celtics ML", status: "winning", value: "+6", progress: nil, game: 0)],
                               more: 0, note: nil)
        Task {
            for a in Activity<A>.activities where a.attributes.betId == "demo" { await a.end(nil, dismissalPolicy: .immediate) }
            _ = try? Activity.request(attributes: A(betId: "demo", name: "White, Pritchard and 4 more (+1283)", book: "FanDuel", toWin: "12.83u"),
                                      content: .init(state: s, staleDate: nil))
        }
    }

    private func watch(_ a: Activity<BetActivityAttributes>) {
        guard watching.insert(a.id).inserted else { return }
        Task { for await t in a.pushTokenUpdates { await save(t, bet: a.attributes.betId) } }
        // its teams' logos into the App Group for the lock screen (LogoStore), now and as games join
        Task {
            await LogoStore.fetch(a.content.state.games.flatMap { [$0.awayLogo, $0.homeLogo] })
            for await c in a.contentUpdates { await LogoStore.fetch(c.state.games.flatMap { [$0.awayLogo, $0.homeLogo] }) }
        }
    }

    /// An app update (or a swipe) ends a card, but its update token stays saved, and the worker would keep updating a
    /// card that's gone and never start it again. Drop this iPhone's update tokens for cards no longer on it (older than
    /// two minutes, so one starting right now keeps its own); the worker then starts those bets again (live_activity.py).
    private func forgetGone() async {
        guard AuthStore.shared.session != nil else { return }
        #if targetEnvironment(simulator)
        guard UserDefaults.standard.bool(forKey: "demoActivity") else { return }
        #endif
        let device = UIDevice.current.identifierForVendor?.uuidString ?? "iPhone"
        struct Row: Decodable { let betId: String?; let createdAt: String }
        guard let saved: [Row] = try? await api.rows("live_activity_tokens",
                                                     .init(eq: [("device", device), ("kind", "update")], select: "bet_id,created_at"))
        else { return }
        let here = Set(Activity<BetActivityAttributes>.activities.map(\.attributes.betId))
        let cutoff = Date().addingTimeInterval(-120)
        for r in saved {
            guard let bet = r.betId, !here.contains(bet), let made = Models.date(r.createdAt), made < cutoff else { continue }
            try? await api.delete("live_activity_tokens", eq: [("device", device), ("kind", "update"), ("bet_id", bet)])
        }
    }

    /// One row per token; this iPhone's older start tokens go first, so the worker never starts a bet twice on it.
    private func save(_ token: Data, bet: String?) async {
        guard AuthStore.shared.session != nil else { return }
        #if targetEnvironment(simulator)
        return          // simulator runs (tests, Claude's demo checks) never register: the worker would start real bets there
        #endif
        let device = UIDevice.current.identifierForVendor?.uuidString ?? "iPhone"
        if bet == nil { try? await api.delete("live_activity_tokens", eq: [("device", device), ("kind", "start")]) }
        try? await api.upsert("live_activity_tokens",
                              ["token": token.map { String(format: "%02x", $0) }.joined(), "env": Push.environment,
                               "kind": bet == nil ? "start" : "update", "bet_id": bet, "device": device],
                              onConflict: "user_id,token")
    }
}
