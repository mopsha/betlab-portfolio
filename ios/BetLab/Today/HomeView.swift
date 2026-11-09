import SwiftUI

@MainActor
final class HomeModel: ObservableObject {
    @Published var day: DayKey = .today
    @Published var sport: String?
    @Published private(set) var feed = Feed()
    @Published private(set) var pricedAt: String?
    @Published private(set) var slates: [Slate] = []
    @Published private(set) var games: [Game] = []
    /// Slices carrying a watched game's own slips (Nov 7): they count as locks to come even without a ticket.
    @Published private(set) var watchedLocks: [GameDay.Lock] = []
    @Published private(set) var art: [String: GameLive] = [:]     // logos and colors from ESPN (Live.art), as on Games
    @Published private(set) var loading = false
    @Published private(set) var error: String?

    func load(_ api: SupabaseClient) async {
        loading = true
        defer { loading = false }
        await read(api.saved, quiet: true)        // what was last seen, at once (Nov 4)
        await read(api, quiet: false)
    }

    private func read(_ api: SupabaseClient, quiet: Bool) async {
        let (from, to) = FeedLogic.window(day)
        let range = SupabaseClient.Filter(from: ("commence_time", from), to: ("commence_time", to))
        let active = SupabaseClient.Filter(from: range.from, to: range.to, active: true)
        do {
            async let games: [Game] = api.rows("games", range)
            async let offers: [Offer] = api.rows("offers", active)
            async let tickets: [Ticket] = api.rows("fun_tickets", active)
            async let slates: SlatesDoc? = api.doc("fun", "slates")
            async let meta: CardMeta? = api.doc("card", "meta")
            let (g, all0, allT0, s, m) = try await (games, offers, tickets, slates, meta)
            let all = BooksOff.mine(all0)          // at the account's books (Nov 6)
            let allT = BooksOff.tickets(allT0)
            let (o, t) = Bans.filter(all, allT, Bans.current)     // the ban list (Oct 25): the games stay
            feed = FeedLogic.build(games: g, offers: o, tickets: t, slates: s?.slates ?? [], sport: sport)
            // a watched game's own slips lock by their game, never the slice (Nov 7): one lock each
            watchedLocks = Watch.locks(t.filter { sport == nil || $0.sport == sport }, watching: Set(Watch.current))
            self.slates = s?.slates ?? []
            self.games = g
            pricedAt = m?.generatedAt
            error = nil
            // logos don't change: the long cache time, which only answers a reader that accepts it (ESPN.get)
            if !quiet { art = await Live.art(for: g.filter { Models.date($0.commenceTime).map { $0 > Date() } ?? false }, ttl: ESPN.doneTTL) }
        } catch {
            if !quiet { self.error = error.localizedDescription }
        }
    }

}

/// Today (the overhaul, Nov 4; mockup V3-Today): the day's units lead, then one card per open bet with its score and
/// ring legs, the picks, the parlays as cards with the next lock's countdown beside their heading, and the feed of games
/// by start time (Feed.swift's rules, unchanged) with their logos. The day switcher and sport chips sit under the hero.
struct HomeView: View {
    @EnvironmentObject private var auth: AuthStore
    @EnvironmentObject private var store: BetStore
    @StateObject private var model = HomeModel()
    @StateObject private var live = LiveModel()
    @Environment(\.scenePhase) private var phase
    @State private var ticket: Ticket?

    /// The live cards' bets: every ungraded one (web openBetNames).
    private var openBets: [MyBet] { store.bets.filter(\.isOpen) }
    /// Only bets still alive, and wins: a lost bet leaves Today (Mike, Oct 24: the red cards "make me feel bad"; it stays
    /// in Live). A game in progress first, then to come, then won.
    @State private var openBet: String?
    private var cards: [(MyBet, BetLive)] {
        let order = { (b: BetLive) in b.games.contains { $0.state == "in" } ? 0 : b.status == "pending" ? 1 : 2 }
        return openBets.compactMap { b in live.bets[b.betId].flatMap { $0.games.isEmpty || $0.status == "lost" ? nil : (b, $0) } }
            .sorted { order($0.1) < order($1.1) }
    }
    /// Today's locks still to come, in the chosen sport (a ticket joins the parlays once it locks).
    private var todayLocks: [GameDay.Lock] {
        guard model.day == .today else { return [] }
        let today = BetMath.etDay(Date())
        return GameDay.upcomingLocks(model.slates.filter { model.sport == nil || $0.sport == model.sport },
                                     games: model.games.filter { model.sport == nil || $0.league == model.sport },
                                     watched: model.watchedLocks)
            .filter { BetMath.etDay($0.at) == today }
    }
    /// The feed's cross-game tickets: the Parlays row. The games stay in the list below.
    private var tickets: [(Ticket, Slate?)] {
        model.feed.items.compactMap { if case .ticket(let t, let s) = $0 { (t, s) } else { nil } }
    }

    var body: some View {
        NavigationStack {
            List { Group {
                TodayHero(date: model.day == .today ? Fmt.longDay(Date()) : model.day.heading,
                          u: model.day == .today ? TodayUnits.of(Live.markLiveSettled(store.bets, live.settled), realMode: store.isReal) : nil)
                    .cardRow()
                // a failed bets read must not pass for "nothing in play" (web Today, Nov 9)
                if model.day == .today, store.error != nil {
                    GlowCard { Label(store.loaded ? "Couldn't refresh your bets: these are from the last good read. Pull to try again."
                                                  : "Couldn't load your bets, so today's units aren't shown. Pull to try again.",
                                     systemImage: "exclamationmark.triangle").font(.footnote).foregroundStyle(.red) }.cardRow()
                }
                controls
                if let error = model.error {
                    GlowCard { Label(error, systemImage: "exclamationmark.triangle").font(.footnote).foregroundStyle(.red) }.cardRow()
                }
                if model.day == .today { yourBets }
                if !model.feed.picks.isEmpty {
                    SectionTitle(model.feed.picks.count == 1 ? (model.day == .today ? "Today's pick" : "Pick") : "Picks",
                                 note: "\(model.feed.picks.count)").titleRow()
                    ForEach(model.feed.picks) { o in GlowCard { BetRowView(o: o) }.cardRow() }
                }
                parlays
                games
            } }
            .listStyle(.plain)
            .listRowSpacing(0)
            .contentMargins(.horizontal, 16, for: .scrollContent)
            .themedList()
            .navigationTitle("Today")
            .navigationBarTitleDisplayMode(.inline)
            .subtitle(model.pricedAt.map { "Priced \(Fmt.dayTime($0)) ET" })
            .navigationDestination(for: FeedGame.self) { GameView(gameId: $0.id, title: Fmt.matchup($0.game.matchup, sport: $0.game.league)) }
            .navigationDestination(item: $openBet) { LiveBetScreen(betId: $0, live: live) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    JobButton(job: .reprice, api: store.api) { await model.load(store.api); await store.load() }
                }
                ToolbarItemGroup(placement: .topBarTrailing) {
                    NavigationLink { ChatView() } label: { Image(systemName: "bubble.left") }.accessibilityLabel("Ask BetLab")
                    NavigationLink { SearchView() } label: { Image(systemName: "magnifyingglass") }.accessibilityLabel("Search")
                    Menu {
                        if let email = auth.session?.email { Text(email) }
                        Button("Sign out", role: .destructive) { auth.signOut() }
                    } label: { Image(systemName: "person.circle") }.accessibilityLabel("Account")
                }
            }
            .sheet(item: $ticket) { t in
                TicketSheet(t: t, title: FeedLogic.ticketTitle(t, tickets.first { $0.0.id == t.id }?.1))
            }
            .overlay { if model.loading && model.feed.items.isEmpty && model.feed.picks.isEmpty { ProgressView() } }
            .modifier(HardTopEdge())
            .refreshable { async let a: () = model.load(store.api); async let b: () = store.load(); _ = await (a, b) }
            .task(id: "\(model.day.rawValue)|\(model.sport ?? "")|\(store.refreshTick)") { await model.load(store.api) }
            .onChange(of: store.bans) { Task { await model.load(store.api) } }
            .onChange(of: store.watching) { Task { await model.load(store.api) } }
            // the live cards: the Live tab's poll (20 s while a game is on, else 5 minutes), only on Today
            .task(id: "\(phase == .active && model.day == .today)|\(openBets.map(\.betId).sorted().joined(separator: ","))") {
                guard phase == .active, model.day == .today else { return }
                while !Task.isCancelled {
                    await live.refresh(store.api, open: Set(openBets.map(\.betId)))
                    try? await Task.sleep(for: live.soon ? LiveModel.fast : LiveModel.slow)
                }
            }
        }
    }

    /// The day switcher and the sport chips, on the page's background.
    @ViewBuilder private var controls: some View {
        Picker("Day", selection: $model.day) {
            ForEach(DayKey.allCases) { Text($0.title).tag($0) }
        }
        .pickerStyle(.segmented)
        .cardRow()
        if model.feed.sports.count > 1 {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    SportChip(title: "All", selected: model.sport == nil) { model.sport = nil }
                    ForEach(model.feed.sports, id: \.self) { s in
                        SportChip(title: Fmt.sportShort[s] ?? Fmt.sports[s] ?? s, league: s, selected: model.sport == s) { model.sport = s }
                    }
                }
            }
            .cardRow()
        } else if model.sport != nil {
            // the one sport left is the filter itself: keep the way back to All
            SportChip(title: "All sports", selected: false) { model.sport = nil }.cardRow()
        }
    }

    /// Your open bets, one card per game (bets on the same game share it); a tap on a bet opens it (LiveBetScreen).
    @ViewBuilder private var yourBets: some View {
        let cards = cards
        if !openBets.isEmpty && live.bets.isEmpty {
            Text("Loading your bets…").font(.footnote).foregroundStyle(.secondary).cardRow()
        }
        ForEach(TodayGameCard.groups(cards), id: \.[0].0.betId) { group in
            TodayGameCard(bets: group) { openBet = $0 }.cardRow()
        }
    }

    /// Parlays: the locked tickets as cards that scroll sideways, and the locks still to come with their countdowns
    /// (the next one beside the heading).
    @ViewBuilder private var parlays: some View {
        let tickets = tickets, locks = todayLocks
        // only with a lock still ahead: an empty TimelineView is still a row (Mike, Oct 24: "weird empty space")
        let ticking = locks.contains { $0.at > Date().addingTimeInterval(-60) }
        if !tickets.isEmpty || ticking {
            if ticking {
                TimelineView(.periodic(from: .now, by: 1)) { ctx in
                    let next = locks.first { $0.at > ctx.date.addingTimeInterval(-60) }
                    SectionTitle(title: "Parlays", note: tickets.isEmpty ? nil : "\(tickets.count)") {
                        if let next {
                            (Text("next locks in ").foregroundStyle(.secondary)
                                + Text(GameDay.countdown(next.at, now: ctx.date)).foregroundStyle(.orange).monospacedDigit())
                                .font(.footnote.weight(.semibold))
                        }
                    }
                }
                .titleRow()
            } else {
                SectionTitle("Parlays", note: "\(tickets.count)").titleRow()
            }
            if !tickets.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 10) {
                        ForEach(tickets, id: \.0.id) { t, s in
                            Button { ticket = t } label: {
                                TicketCard(t: t, title: FeedLogic.ticketTitle(t, s), logos: logos(t), today: model.day == .today)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .scrollClipDisabled()
                .cardRow()
            }
            if ticking {
                TimelineView(.periodic(from: .now, by: 1)) { ctx in LocksCard(locks: locks, now: ctx.date) }.cardRow()
            }
        }
    }

    /// The logos of a ticket's games, from the same ESPN boards as the feed's.
    private func logos(_ t: Ticket) -> [String] {
        let boards = Array(model.art.values)
        var seen = Set<String>()
        return (t.body.games ?? []).compactMap { Live.findGame(boards, $0.matchup) }
            .flatMap { [$0.away.logo, $0.home.logo] }.compactMap { $0 }.filter { seen.insert($0).inserted }
    }

    /// The games, by start time; This week gets a heading per Eastern day.
    @ViewBuilder private var games: some View {
        let rows = rows
        let nothing = rows.isEmpty && tickets.isEmpty && model.feed.picks.isEmpty
        if !rows.isEmpty {
            SectionTitle(model.feed.picks.isEmpty && tickets.isEmpty ? "By start time" : "Everything else", note: "by start time").titleRow()
        }
        if nothing && !model.loading {
            GlowCard {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Nothing to act on \(model.day == .week ? "this week" : model.day.title.lowercased())").font(.headline)
                    Text("No pick or parlay cleared the bar. Most days the market is priced right; leans are on each game's page.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .cardRow()
        }
        ForEach(rows, id: \.id) { row in
            switch row {
            case .header(let title): Text(title).font(.subheadline.weight(.bold)).foregroundStyle(.secondary).padding(.top, 6).padding(.horizontal, 4).cardRow()
            case .game(let g):
                FeedGameCard(g: g, art: model.art[g.id])
                    .background(NavigationLink(value: g) { EmptyView() }.opacity(0))
                    .cardRow()
            }
        }
        if model.feed.quiet > 0 {
            Text("\(model.feed.quiet) more game\(model.feed.quiet == 1 ? "" : "s") with nothing to act on.")
                .font(.footnote).foregroundStyle(.secondary).padding(.horizontal, 4).cardRow()
        }
    }

    private enum Row { case header(String), game(FeedGame)
        var id: String { switch self { case .header(let h): "h-" + h; case .game(let g): "g-" + g.id } }
    }
    private var rows: [Row] {
        let games = model.feed.items.compactMap { if case .game(let g) = $0 { g } else { nil } }
        guard model.day == .week else { return games.map { .game($0) } }
        var out: [Row] = []
        var last = ""
        for g in games {
            let d = Models.date(g.game.commenceTime).map(Fmt.longDay) ?? ""
            if d != last { out.append(.header(d)); last = d }
            out.append(.game(g))
        }
        return out
    }
}

private extension View {
    /// A section's heading as a list row: on the page, with air above it.
    func titleRow() -> some View {
        padding(.horizontal, 4).listRowBackground(Color.clear).listRowSeparator(.hidden)
            .listRowInsets(EdgeInsets(top: 18, leading: 0, bottom: 4, trailing: 0))
    }
}
