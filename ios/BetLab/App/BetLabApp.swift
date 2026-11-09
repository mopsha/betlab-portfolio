import SwiftUI

@main
struct BetLabApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var auth = AuthStore.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
        }
    }
}

/// Signed out: the login screen. Signed in: the tabs.
struct RootView: View {
    @EnvironmentObject private var auth: AuthStore
    @AppStorage("appearance") private var appearance = "system"
    @AppStorage(AppLock.key) private var appLock = false
    @Environment(\.scenePhase) private var phase
    @State private var locked = true          // from launch; shown only with the lock turned on
    @State private var leftAt: Date?

    var body: some View {
        if !Config.isConfigured {
            ContentUnavailableView("Not set up",
                                   systemImage: "gearshape",
                                   description: Text("Run ios/scripts/make_secrets.sh on the Mac, then build again."))
        } else if auth.session == nil {
            LoginView()
        } else {
            // the theme (Settings): its scheme, accent, page and cards (Theme.swift)
            let theme = Theme.named(appearance)
            SignedInView(auth: auth)
                .overlay { if appLock && locked { AppLockView { locked = false }.environmentObject(auth) } }
                .onChange(of: phase) { _, now in
                    if now == .background { leftAt = Date() }
                    if now == .active, AppLock.needsUnlock(enabled: appLock, leftAt: leftAt) { locked = true }
                }
                .preferredColorScheme(theme.scheme)
                .tint(theme.accent)
                .environment(\.theme, theme)
        }
    }
}

/// The tabs, sharing one store of the user's bets (Home marks them, My bets lists them).
struct SignedInView: View {
    @StateObject private var store: BetStore
    @AppStorage("appearance") private var appearance = "system"   // saved to the account for the alerts' voice
    @Environment(\.scenePhase) private var phase

    init(auth: AuthStore) {
        _store = StateObject(wrappedValue: BetStore(api: SupabaseClient(token: { [auth] in try await auth.accessToken() })))
    }

    /// Testing hook: launched with `-openGame <game_id>`, the app opens on that game's page (Claude's simulator
    /// checks; `-expandFolds YES` also opens every analysis section; `-tab build` opens a tab). Normal launches never set either.
    @State private var tab = UserDefaults.standard.string(forKey: "tab") ?? (UserDefaults.standard.string(forKey: "openGame") == nil ? "home" : "games")

    var body: some View {
        TabView(selection: $tab) {
            // The overhaul's tabs (Nov 4, docs/OVERHAUL.md): what the app is opened for. Live is My bets (open bets and
            // the wall), Me is the old More. The values stay, so `-tab bets` and saved links still land.
            Tab("Today", systemImage: "house", value: "home") { HomeView() }
            Tab("Live", systemImage: "waveform.path.ecg", value: "bets") { MyBetsView() }
                .badge(store.liveCount)        // bets live right now, not every open bet (Mike, Nov 5)
            Tab("Build", systemImage: "plus.square", value: "build") { BuildView() }
            Tab("Games", systemImage: "calendar", value: "games") { GamesView() }
            Tab("Me", systemImage: "person", value: "more") { MoreView() }
        }
        .environmentObject(store)
        // a tapped alert's link (Push.route): its tab, and the ladder on Me for a ladder alert
        .onReceive(Push.shared.$route.compactMap { $0 }) { url in
            let to = Push.destination(url)
            tab = to.tab
            if to.ladder { Push.shared.openLadder = true }
            Push.shared.route = nil
        }
        .modifier(LiveBadgeWatch(store: store))
        .fullScreenCover(isPresented: $store.needsWelcome) { WelcomeView().environmentObject(store) }
        .overlay(alignment: .top) { OfflineBanner() }
        .task {
            Push.shared.api = store.api
            await Push.shared.refresh()
            await store.saveTheme(appearance)
        }
        // iOS keeps the app alive for hours: reload on the way back to the foreground and every 5 minutes while open. Its own
        // Task, so leaving the app doesn't cancel a load halfway and show that as an error.
        .task(id: phase == .active) {
            guard phase == .active else { return }
            while !Task.isCancelled {
                Task { await store.reload() }
                try? await Task.sleep(for: .seconds(300))
            }
        }
        // Live updates (Nov 4): the database says something changed, every screen reads it at once; only in the foreground
        .task(id: phase == .active) {
            guard phase == .active else { return }
            await LivePulse.run(token: { [api = store.api] in try await api.token() }, onChange: { store.pulsed() })
        }
        .onChange(of: appearance) { _, theme in Task { await store.saveTheme(theme) } }
    }
}
