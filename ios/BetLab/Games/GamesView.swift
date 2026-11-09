import SwiftUI

@MainActor
final class GamesModel: ObservableObject {
    @Published var sport: String?
    @Published private(set) var games: [Game] = []
    @Published private(set) var sports: [String] = []
    @Published private(set) var counts: [String: Int] = [:]
    @Published private(set) var error: String?
    @Published private(set) var loaded = false
    @Published private(set) var art: [String: GameLive] = [:]     // logos and colors from ESPN (Live.art)

    /// Every game not yet started, to a week out, with how many things there are to act on in each (web allGames).
    func load(_ api: SupabaseClient) async {
        await read(api.saved, quiet: true)        // what was last seen, at once (Nov 4)
        await read(api, quiet: false)
    }

    private func read(_ api: SupabaseClient, quiet: Bool) async {
        let (from, to) = FeedLogic.window(.week)
        let range = SupabaseClient.Filter(from: ("commence_time", from), to: ("commence_time", to))
        let active = SupabaseClient.Filter(from: range.from, to: range.to, active: true)
        do {
            async let g: [Game] = api.rows("games", range)
            async let o: [Offer] = api.rows("offers", active)
            async let t: [Ticket] = api.rows("fun_tickets", active)
            let (games, allO0, allT0) = try await (g, o, t)
            let allO = BooksOff.mine(allO0)         // at the account's books (Nov 6)
            let allT = BooksOff.tickets(allT0)
            let (offers, tickets) = Bans.filter(allO, allT, Bans.current)     // the ban list (Oct 25)
            var c: [String: Int] = [:]
            for id in offers.filter({ $0.tier != .check }).compactMap(\.gameId) + tickets.compactMap(\.gameId) { c[id, default: 0] += 1 }
            counts = c
            let now = Date()
            self.games = games.filter { g in Models.date(g.commenceTime).map { $0 > now } ?? true }
                .sorted { ($0.commenceTime ?? "") < ($1.commenceTime ?? "") }
            sports = Array(Set(games.map(\.league))).sorted()
            error = nil
            loaded = true
            art = await Live.art(for: self.games, ttl: ESPN.doneTTL)
        } catch {
            if quiet { return }               // nothing saved yet: the real read decides
            self.error = error.localizedDescription
        }
        loaded = true
    }
}

/// One game in the list (the overhaul, Nov 4): a card with both logos and names, the start, and how many things there
/// are to act on, its two teams' colors as soft light in the corners (never a painted band or stripe). Without ESPN's
/// art (a game it doesn't list), the plain matchup with initials.
struct GameCardRow: View {
    let g: Game
    let art: GameLive?
    let count: Int?
    var chevron = true          // false: a game with no page yet (the calendar lists games weeks ahead)
    @Environment(\.theme) private var theme
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let art = art?.reading                  // soccer: home first (Nov 5)
        let flip = Fmt.isSoccer(g.league)
        let away = Color(hex: art?.away.color), home = Color(hex: art?.home.color)
        let names = flip && !(g.home ?? "").isEmpty ? (g.home ?? "", g.away ?? "") : (g.away ?? "", g.home ?? "")
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 8) {
                team(art?.away, fallback: names.0.isEmpty ? (g.matchup ?? "") : names.0, ufc: g.league == "ufc")
                if !names.1.isEmpty || art != nil { team(art?.home, fallback: names.1, ufc: g.league == "ufc") }
            }
            Spacer(minLength: 6)
            VStack(alignment: .trailing, spacing: 6) {
                Text(Fmt.time(g.commenceTime)).font(.subheadline.monospacedDigit().weight(.bold))
                HStack(spacing: 4) {
                    if let count { TagView(text: "\(count)", color: .accentColor) }
                    TagView(text: Fmt.sportShort[g.league] ?? g.league)
                }
            }
            if chevron { Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary) }
        }
        .padding(.vertical, 12).padding(.horizontal, 14)
        .background {
            ZStack {
                theme.cardColor
                GeometryReader { geo in
                    if let away { light(away).position(x: 10, y: -10) }
                    if let home { light(home).position(x: geo.size.width - 10, y: geo.size.height + 10) }
                }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private func light(_ c: Color) -> some View {
        Circle().fill(c).frame(width: 130, height: 130).blur(radius: 36).opacity(scheme == .dark ? 0.3 : 0.18)
    }

    private func team(_ s: LiveSide?, fallback: String, ufc: Bool) -> some View {
        let name = s?.name.isEmpty == false ? s!.name : fallback
        return HStack(spacing: 10) {
            TeamLogo(url: s?.logo, name: name, size: 28, round: ufc)
            Text(name).font(.subheadline.weight(.semibold)).lineLimit(1)
        }
    }
}

/// Games: every game in the next week, by day, filterable by sport. Each opens its own page.
struct GamesView: View {
    @EnvironmentObject private var store: BetStore
    @StateObject private var model = GamesModel()
    @State private var path: [String] = UserDefaults.standard.string(forKey: "openGame").map { [$0] } ?? []

    var body: some View {
        let shown = model.games.filter { model.sport == nil || $0.league == model.sport }
        let days = shown.reduce(into: [String]()) { d, g in
            let k = Models.date(g.commenceTime).map(BetMath.etDay) ?? ""
            if d.last != k { d.append(k) }
        }
        NavigationStack(path: $path) {
            List { Group {
                Section {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            chip("All", model.sport == nil) { model.sport = nil }
                            ForEach(model.sports, id: \.self) { s in chip(Fmt.sports[s] ?? s, model.sport == s) { model.sport = s } }
                        }
                    }
                    .bareRow()
                }
                if let e = model.error { Section { Label(e, systemImage: "exclamationmark.triangle").foregroundStyle(.red) } }
                ForEach(days, id: \.self) { d in
                    Section {
                        ForEach(shown.filter { (Models.date($0.commenceTime).map(BetMath.etDay) ?? "") == d }) { g in
                            // the card is the whole row, its chevron inside the team colors (Mike, Oct 24): the link is
                            // invisible underneath, so the list draws no chevron of its own
                            GameCardRow(g: g, art: model.art[g.gameId], count: model.counts[g.gameId])
                                .background(NavigationLink(value: g.gameId) { EmptyView() }.opacity(0))
                            .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
                            .listRowBackground(Color.clear).listRowSeparator(.hidden)
                        }
                    } header: {
                        SectionTitle(d.isEmpty ? "Date to be set" : Fmt.longDay(Models.date(d + "T16:00:00Z") ?? Date()))
                            .foregroundStyle(.primary).padding(.leading, -16)
                    }
                }
            }.themedRows() }.themedList()
            .navigationTitle("Games")
            .toolbar {
                NavigationLink { SearchView() } label: { Label("Search", systemImage: "magnifyingglass") }
                NavigationLink { CalendarView() } label: { Label("Calendar", systemImage: "calendar") }
            }
            .navigationDestination(for: String.self) { GameView(gameId: $0) }
            .overlay { if !model.loaded { ProgressView() } }
            .refreshable { await model.load(store.api) }
            .task(id: store.refreshTick) { await model.load(store.api) }
            .onChange(of: store.bans) { Task { await model.load(store.api) } }
        }
    }

    private func chip(_ title: String, _ selected: Bool, _ action: @escaping () -> Void) -> some View {
        PickChip(text: title, on: selected, action: action)
    }
}
