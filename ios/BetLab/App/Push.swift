import SwiftUI
import UserNotifications

/// Pick alerts on the iPhone (Oct 14): the app registers with Apple's push service and saves its device token in
/// `push_subscriptions` as 'apns:<environment>:<token>' (migration 0011). The worker's `betlab alert` sends new picks,
/// locked tickets, problems and the test alert there through APNs (src/betlab/apns.py), as it does to the web app.
@MainActor
final class Push: NSObject, ObservableObject {
    static let shared = Push()
    @Published private(set) var status: UNAuthorizationStatus = .notDetermined
    @Published private(set) var saved = false
    @Published var message: String?
    /// Where a tapped alert goes (Nov 6: a ladder alert opened the app wherever it was): its `url` ("/bets?view=ladder",
    /// "/more/ladder", "/bets", "/games/..."); SignedInView picks the tab, and Me opens the ladder (`openLadder`).
    @Published var route: String?
    @Published var openLadder = false

    /// A tapped alert's tab, and whether it opens the ladder: a ladder link ("/bets?view=ladder", "/more/ladder") opens it
    /// on Me; "/bets" is Live, "/games/..." Games, "/more..." Me, anything else Today.
    nonisolated static func destination(_ url: String) -> (tab: String, ladder: Bool) {
        if url.contains("ladder") { return ("more", true) }
        if url.hasPrefix("/bets") { return ("bets", false) }
        if url.hasPrefix("/games") { return ("games", false) }
        if url.hasPrefix("/more") { return ("more", false) }
        return ("home", false)
    }
    var api: SupabaseClient?
    private var sendTest = false

    /// Builds installed from Xcode get sandbox tokens; TestFlight and App Store builds get production ones.
    static var environment: String {
        #if DEBUG
        "sandbox"
        #else
        "production"
        #endif
    }

    static func endpoint(_ token: Data) -> String { "apns:\(environment):" + token.map { String(format: "%02x", $0) }.joined() }

    func refresh() async {
        status = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
        if status == .authorized { UIApplication.shared.registerForRemoteNotifications() }   // the token can change
    }

    /// "Turn on pick alerts": ask, register, then save and queue the confirmation alert.
    func turnOn() async {
        do {
            let ok = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])
            status = ok ? .authorized : .denied
            guard ok else { message = "Notifications are off for BetLab. Turn them on in the iPhone's Settings > Notifications > BetLab."; return }
            sendTest = true
            UIApplication.shared.registerForRemoteNotifications()
        } catch {
            message = "Couldn't ask for notifications."
        }
    }

    func registered(_ token: Data) {
        guard let api else { return }
        let test = sendTest
        sendTest = false
        Task {
            do {
                try await api.upsert("push_subscriptions", ["endpoint": Self.endpoint(token), "device": "iPhone app"], onConflict: "user_id,endpoint")
                saved = true
                if test {
                    try? await api.insert("job_requests", ["job": "test_alert", "status": "queued"])
                    message = "Alerts are on. A test notification is on its way (within a minute or two)."
                }
            } catch {
                message = "Couldn't save this iPhone for alerts. Try again in a moment."
            }
        }
    }

    func failed(_ error: Error) { message = "Apple didn't register this iPhone for alerts (\(error.localizedDescription))." }
}

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ app: UIApplication, didFinishLaunchingWithOptions opts: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        KeyboardDone.install()          // a Done bar above every number pad (Nov 6)
        Task { @MainActor in LiveActivities.shared.start() }
        return true
    }
    func application(_ app: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken token: Data) {
        Task { @MainActor in Push.shared.registered(token) }
    }
    func application(_ app: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        Task { @MainActor in Push.shared.failed(error) }
    }
    /// A tapped alert: go where its `url` points (Push.route).
    func userNotificationCenter(_ c: UNUserNotificationCenter, didReceive r: UNNotificationResponse) async {
        let url = r.notification.request.content.userInfo["url"] as? String
        await MainActor.run { Push.shared.route = url ?? "/" }
    }
    /// Show alerts as banners while the app is open too.
    func userNotificationCenter(_ c: UNUserNotificationCenter, willPresent n: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .sound, .list]
    }
}

/// Settings' "Pick alerts" section.
struct PushSection: View {
    @ObservedObject var push = Push.shared
    var body: some View {
        Section {
            switch push.status {
            case .authorized, .provisional, .ephemeral:
                Label(push.saved ? "On for this iPhone" : "On", systemImage: "bell.badge.fill").foregroundStyle(.green)
            case .denied:
                Text("Off. Turn them on in the iPhone's Settings > Notifications > BetLab.").foregroundStyle(.secondary)
            default:
                Button("Turn on pick alerts") { Task { await push.turnOn() } }
            }
            if let m = push.message { Text(m).font(.footnote).foregroundStyle(.secondary) }
        } header: {
            Text("Pick alerts")
        } footer: {
            Text("A notification when a new pick is found and when a parlay ticket locks. Choose which below.")
        }
    }
}
