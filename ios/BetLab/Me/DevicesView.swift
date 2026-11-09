import LocalAuthentication
import SwiftUI

/// A signed-in session (my_sessions, migration 0037). The name comes from its user agent (web lib/devices.ts, fixture tests/fixtures/devices.json).
struct DeviceSession: Decodable, Identifiable, Hashable {
    let id: String
    let lastActive: String
    let userAgent: String?
    let ip: String?
    let current: Bool

    static func name(_ ua: String?) -> String {
        let u = ua ?? ""
        func has(_ s: String) -> Bool { u.contains(s) }
        if u.hasPrefix("BetLab/") { return "BetLab iPhone app" }
        if u == "node" { return "Website sign-in" }     // went through our server: its IP is the server's, so the row leaves it out
        let os = has("iPhone") ? "iPhone" : has("iPad") ? "iPad" : has("Android") ? "Android" : has("Windows") ? "Windows" : has("Macintosh") ? "Mac" : has("Linux") ? "Linux" : ""
        let browser = has("Edg/") ? "Edge" : has("Firefox/") || has("FxiOS/") ? "Firefox" : has("Chrome/") || has("CriOS/") ? "Chrome" : has("Safari/") ? "Safari" : ""
        return !os.isEmpty && !browser.isEmpty ? "\(browser) on \(os)" : "Unknown device"
    }
}

/// Where you're signed in. Ending one stops its next refresh, so it's out within the hour at the latest.
struct DevicesView: View {
    @EnvironmentObject private var store: BetStore
    @State private var sessions: [DeviceSession] = []
    @State private var msg: String?
    @State private var busy = false

    var body: some View {
        List {
            Section {
                ForEach(sessions) { s in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) { Text(DeviceSession.name(s.userAgent)).font(.subheadline.weight(.semibold)); if s.current { TagView(text: "This device", color: .accentColor) } }
                            Text("Last active \(Self.when(s.lastActive))\(s.ip != nil && s.userAgent != "node" ? " · \(s.ip!)" : "")").font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if !s.current {
                            Button("Sign out") { end(s.id) }.buttonStyle(.borderless).font(.subheadline).disabled(busy)
                                .accessibilityLabel("Sign out \(DeviceSession.name(s.userAgent))")
                        }
                    }
                }
            } footer: { Text("Signing a device out can take up to an hour to take effect.") }
            if sessions.filter({ !$0.current }).count > 1 {
                Section { Button("Sign out all other devices", role: .destructive) { end(nil) }.disabled(busy) }
            }
            if let msg { Section { Text(msg).font(.subheadline).foregroundStyle(.secondary) } }
        }
        .themedRows().themedList()
        .navigationTitle("Signed-in devices")
        .task { await load() }
        .refreshable { await load() }
    }

    private static let whenF: DateFormatter = {
        let f = DateFormatter(); f.timeZone = TimeZone(identifier: "America/New_York"); f.locale = Locale(identifier: "en_US"); f.dateFormat = "MMM d, h:mm a"
        return f
    }()
    /// With its date: "Wed 2:11 PM" read as this week for a session last used three weeks ago.
    private static func when(_ iso: String) -> String { Models.date(iso).map(whenF.string(from:)) ?? "" }

    private func load() async {
        do { sessions = try await store.api.rpc("my_sessions") }
        catch is CancellationError {} catch { msg = error.localizedDescription }
    }

    private func end(_ id: String?) {
        busy = true
        Task {
            defer { busy = false }
            do {
                let n: [Int] = try await store.api.rpc("end_sessions", id.map { ["session": $0] } ?? [:])
                msg = "Signed out \(n.first ?? 0) device\(n.first == 1 ? "" : "s")."
                await load()
            } catch { msg = error.localizedDescription }
        }
    }
}

/// The app's Face ID lock (Nov 4; off until turned on in Settings, on this phone only). It guards the screen, not the account: the session and
/// its alerts keep working behind it. The phone's passcode is the fallback, and Sign out always gets you out.
enum AppLock {
    static let key = "appLock"
    static let after: TimeInterval = 5 * 60      // away this long: locked again

    static func needsUnlock(enabled: Bool, leftAt: Date?, now: Date = Date()) -> Bool {
        guard enabled else { return false }
        guard let leftAt else { return true }    // just launched
        return now.timeIntervalSince(leftAt) >= after
    }

    /// Asks Face ID, then the passcode; the reason it couldn't, or nil once unlocked.
    static func unlock() async -> String? {
        let ctx = LAContext()
        // no Face ID or passcode on this phone: nothing could ever open the lock, or turn it off, so it lets you in
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: nil) else { return nil }
        do {
            return try await ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: "Unlock BetLab") ? nil : "Not unlocked"
        } catch { return error.localizedDescription }
    }
}

struct AppLockView: View {
    @EnvironmentObject private var auth: AuthStore
    let onUnlock: () -> Void
    @State private var msg: String?

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "faceid").font(.system(size: 52)).foregroundStyle(Color.accentColor).accessibilityHidden(true)
            Text("BetLab is locked").font(.title2.bold())
            if let msg { Text(msg).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center) }
            Button("Unlock") { attempt() }.buttonStyle(.borderedProminent)
            Button("Sign out", role: .destructive) { auth.signOut() }.font(.subheadline)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.background)
        .task { attempt() }
    }

    private func attempt() {
        Task {
            if let why = await AppLock.unlock() { msg = why } else { onUnlock() }
        }
    }
}
