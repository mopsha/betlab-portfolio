import SwiftUI

/// Me (reorganized Nov 5, docs/OVERHAUL.md; web app/more): about you, in one order. Who you are and Settings; your
/// number (units won, with Week / Month / All changing the number, its chart and the four stats under it); your betting
/// (promos, the ladder, record and stats); badges; friends; BetLab the system; Extras as chips. Each place has one way
/// in from here. Reviews and plan are the owner's only.
struct MoreView: View {
    @EnvironmentObject private var store: BetStore
    @EnvironmentObject private var auth: AuthStore
    @Environment(\.theme) private var theme
    @Environment(\.colorScheme) private var scheme
    @StateObject private var friends = FriendsModel()
    @State private var mine = 0
    @State private var promos: [PromoRow] = []
    @State private var range = MeRange.all
    @State private var badges: [Badge] = []
    @State private var faces: [FaceStack.Item] = []
    @State private var showBadges = false
    @ObservedObject private var push = Push.shared        // a tapped ladder alert opens the ladder (Push.openLadder)
    /// Testing hook (demo checks, Nov 6): `-openScreen <name>` opens that Me screen at launch, so every screen can be
    /// captured by a script (ios/README.md). Normal launches never set it.
    @State private var hook: String?        // set just after the first render (a destination already on at render is ignored)
    static let hooked: Set<String> = ["settings", "record", "stats", "prices", "promos", "ladder", "friends", "chat", "model", "learn",
                                      "wrapped", "challenges", "calendar", "dfs", "intro", "search"]
    /// The live tracker, quiet: a bet it has settled counts at once, as on Today and in Live, before the worker grades it.
    @StateObject private var live: LiveModel = { let m = LiveModel(); m.quiet = true; return m }()
    @Environment(\.scenePhase) private var phase

    private var owner: Bool { auth.session?.userId == ownerUserId }
    private var counted: (useReal: Bool, bets: [MyBet]) {
        let s = BetMath.recordBets(Live.markLiveSettled(store.bets, live.settled), realMode: store.isReal)
        return (s.useReal, s.counted)
    }
    /// When the badges and the pictures are worked out again: the bets changed, or the parlays' games arrived.
    private var tallyKey: String {
        "\(store.bets.count)|\(store.bets.filter(BetMath.isSettled).count)|\(live.settled.count)|\(store.isReal)|\(store.cardTickets?.count ?? -1)"
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    header
                    number
                    betting
                    badgeRow
                    friendRow
                    system
                    extras
                }
                .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 28)
            }
            .background(theme.pageColor.ignoresSafeArea())
            .navigationTitle("Me")
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(isPresented: $push.openLadder) { LadderScreen() }
            .navigationDestination(isPresented: Binding(get: { hook != nil }, set: { if !$0 { hook = nil } })) { hookScreen }
            .task {
                guard let s = UserDefaults.standard.string(forKey: "openScreen"), MoreView.hooked.contains(s) else { return }
                try? await Task.sleep(for: .milliseconds(300)); hook = s
            }
            .refreshable { await store.load(); await load() }
            // both loads sit on the scroll view, which is always there (a section that starts empty never runs its task)
            .task(id: store.refreshTick) { await load() }
            // open bets on the live poll (20 s while a game is on, else 5 minutes), only while the app is in front
            .task(id: "\(phase == .active)|\(store.bets.filter(\.isOpen).map(\.betId).sorted().joined(separator: ","))") {
                let open = Set(store.bets.filter(\.isOpen).map(\.betId))
                guard phase == .active, !open.isEmpty else { return }
                while !Task.isCancelled {
                    await live.refresh(store.api, open: open)
                    try? await Task.sleep(for: live.soon ? LiveModel.fast : LiveModel.slow)
                }
            }
            .task(id: tallyKey) { tally() }
            .sheet(isPresented: $showBadges) { BadgesSheet(badges: badges) }
        }
    }

    /// The screen's own data: the wallet, friends, the parlays' games (for team pictures) and the owner's to-dos.
    private func load() async {
        if let rows: [PromoRow] = try? await store.api.rows("promos") { promos = rows }
        if let me = auth.session?.userId { await friends.load(store.api, me: me) }
        if store.cardTickets == nil { await store.loadCardTickets() }
        if owner {
            let todos: [Todo] = (try? await store.api.rows("todos", .init(eq: [("owner", "you"), ("status", "open")]))) ?? []
            mine = todos.count
        }
    }

    /// The badges and the pictures on Record and stats, worked out once per change (not on every draw).
    private func tally() {
        let bets = counted.bets
        badges = Achievements.all(bets)
        let players = Players.all(bets).prefix(2).map { FaceStack.Item(kind: .player, name: $0.name, sport: $0.sport) }
        let team = store.cardTickets.flatMap { Cards.teams(bets, tickets: $0).first }
            .map { FaceStack.Item(kind: .team, name: $0.name, sport: $0.sport) }
        var list = Array(players)
        if let team { list.insert(team, at: min(1, list.count)) }
        faces = list
    }

    // MARK: who you are

    private var header: some View {
        let email = auth.session?.email ?? ""
        let name = friends.profile?.name ?? email.components(separatedBy: "@")[0]
        let since = Models.date(store.realFrom) ?? Marking.realStart
        let phase = counted.useReal ? "since \(Fmt.shortDay(since))" : "paper until \(Fmt.shortDay(since))"
        return HStack(spacing: 10) {
            Text(name.first.map { String($0).uppercased() } ?? "?").font(.system(size: 18, weight: .heavy))
                .foregroundStyle(theme.onAccent(scheme)).frame(width: 44, height: 44).background(theme.accent, in: Circle())
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 1) {
                Text(name.isEmpty ? "You" : name).font(.headline.weight(.bold)).lineLimit(1)
                Text((friends.profile.map { "@" + $0.handle } ?? email) + " · " + phase)
                    .font(.footnote).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.8)
            }
            Spacer(minLength: 8)
            NavigationLink { SettingsView() } label: {
                Image(systemName: "slider.horizontal.3").font(.body.weight(.semibold)).foregroundStyle(.primary)
                    .frame(width: 44, height: 44).background(theme.cardColor, in: Circle())
            }
            .accessibilityLabel("Settings")
        }
    }

    // MARK: your number

    private var number: some View {
        let all = counted.bets
        let bets = MeNumbers.ranged(all, range)
        let t = BetMath.record(bets).total
        let values = MeNumbers.series(all, range)
        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .bottom, spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    HeroNumber(text: BetMath.signedUnits(t.units), color: tone(t.units) ?? .primary, size: 56)
                        .accessibilityLabel("\(BetMath.signedUnits(t.units)) units")
                    Text(range.label + (t.bets == 0 ? " · nothing settled" : ""))
                        .font(.footnote).foregroundStyle(.secondary).lineLimit(1)
                        .padding(.bottom, 6)        // level with the chips' capsules, which sit in 44pt tap areas
                }
                Spacer(minLength: 4)
                HStack(spacing: 6) {
                    ForEach(MeRange.allCases) { r in RangeChip(text: r.chip, on: range == r) { range = r } }
                }
                .fixedSize()
            }
            if values.count > 1 {
                Spark(values: values, color: (values.last ?? 0) >= (values.first ?? 0) ? .green : .red, fill: true)
                    .frame(height: 100).padding(.horizontal, -16)
            }
            NavigationLink { RecordHub(start: .record) } label: { stats(t, Stats.streaks(bets)) }.buttonStyle(.plain)
        }
    }

    /// Record, return, against the close and the run you are on, for the chosen range: one card, a tap opens the record.
    private func stats(_ t: RecordLine, _ run: (kind: String?, n: Int, bestWin: Int)) -> some View {
        let streak = run.kind.map { ($0 == "won" ? "W" : "L") + "\(run.n)" }
        return HStack(spacing: 12) {
            StatCell(name: "RECORD", value: "\(t.won)-\(t.lost)")
            StatCell(name: "RETURN", value: Fmt.signed(t.roi), color: tone(t.roi) ?? .primary)
            StatCell(name: "VS CLOSE", value: Fmt.signed(t.avgClv), color: tone(t.avgClv) ?? .primary)
            StatCell(name: "STREAK", value: streak ?? "—", color: run.kind == nil ? .primary : run.kind == "won" ? .green : .red)
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
        }
        .lineLimit(1).minimumScaleFactor(0.75)
        .padding(.horizontal, 16).padding(.vertical, 15)
        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
        .contentShape(RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(range.label): \(t.won) won, \(t.lost) lost, return \(Fmt.signed(t.roi)), against the close \(Fmt.signed(t.avgClv)), streak \(streak ?? "none"). Opens your record.")
    }

    // MARK: your betting

    private var betting: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle("Your betting")
            HStack(spacing: 10) {
                NavigationLink { PromosView() } label: { promoTile }.buttonStyle(.plain)
                NavigationLink { LadderScreen() } label: { ladderTile }.buttonStyle(.plain)
            }
            card {
                NavigationLink { RecordHub(start: .stats) } label: {
                    ProfileRow(title: "Record and stats", sub: "By sport, book and price · your players") {
                        if !faces.isEmpty { FaceStack(items: faces) }
                    } trailing: { EmptyView() }
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func big(_ n: String, _ word: String) -> some View {
        (Text(n).font(.system(size: 26, weight: .heavy)) + Text(" " + word).font(.subheadline.weight(.semibold)).foregroundColor(.secondary))
            .lineLimit(1).minimumScaleFactor(0.6)
    }

    /// Bonus dollars waiting and how many boosts (the wallet counts dollars: the one place Me shows money).
    private var promoTile: some View {
        let open = Promos.wallet(promos).open
        let bonus = open.filter { $0.kind == "bonus" }, boosts = open.filter { $0.kind == "boost" }.count
        let dollars = bonus.reduce(0) { $0 + ($1.amountDollars ?? 0) }
        let money = "$" + (dollars == dollars.rounded() ? String(Int(dollars)) : String(format: "%.2f", dollars))
        let boostWord = "boost\(boosts == 1 ? "" : "s")"
        let today = BetMath.etDay(Date())
        let last = open.filter { p in Promos.date(p.expiresAt).map { BetMath.etDay($0) == today } ?? false }.count
        return MeTile(name: "Promos") {
            if dollars > 0 { big(money, boosts > 0 ? "+ \(boosts) \(boostWord)" : "in bonus bets") }
            else if !bonus.isEmpty { big("\(bonus.count)", "bonus bet\(bonus.count == 1 ? "" : "s")" + (boosts > 0 ? " + \(boosts) \(boostWord)" : "")) }
            else if boosts > 0 { big("\(boosts)", boostWord) }
            else { Text("None waiting").font(.headline) }
            if last > 0 { Text("\(last) end\(last == 1 ? "s" : "") today").font(.footnote.weight(.semibold)).foregroundStyle(.orange) }
            else { Text(open.isEmpty ? "Bonus bets and boosts" : "\(open.count) waiting").font(.footnote).foregroundStyle(.secondary) }
        }
    }

    /// The stack of the target with the rungs (as the Ladder screen draws them), or the way to start one.
    private var ladderTile: some View {
        let live = store.ladders.map { ($0, LadderMath.state($0, store.bets)) }
            .first { $0.0.status == "active" && ($0.1.phase == .inPlay || $0.1.phase == .nextStep) }
        return MeTile(name: "Ladder") {
            if let (l, s) = live {
                let toGo = s.stack > LadderMath.dust ? LadderMath.stepsToTarget(s.stack, l.targetUnits, price: 100) : 1
                big(Marking.units(s.stack), "of \(Marking.units(l.targetUnits))")
                RungTrack(won: s.won, toGo: max(1, min(toGo, 12)))
                Text("Step \(s.steps.count + (s.phase == .nextStep ? 1 : 0)) \(s.phase == .inPlay ? "in play" : "next")")
                    .font(.footnote).foregroundStyle(.secondary)
            } else {
                Text("Start one").font(.headline)
                Text("Roll a stack bet to bet toward a target").font(.footnote).foregroundStyle(.secondary)
            }
        }
    }

    // MARK: badges

    @ViewBuilder private var badgeRow: some View {
        if !badges.isEmpty {
            let got = badges.filter { $0.earned != nil }
            let near = Achievements.nextUp(badges, 2)
            let locked = near + badges.filter { b in b.earned == nil && !near.contains { $0.id == b.id } }.prefix(2 - near.count)
            VStack(alignment: .leading, spacing: 12) {
                SectionTitle(title: "Badges", note: "\(got.count) of \(badges.count)") {
                    Button { showBadges = true } label: { more("All") }.buttonStyle(.plain)
                        .accessibilityLabel("All badges")
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(got + locked) { b in
                            Button { showBadges = true } label: { BadgeDot(badge: b) }.buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 16)
                }
                .padding(.horizontal, -16)
            }
        }
    }

    /// A section's link at its right ("All", "Feed"): small text in the accent with a tap area that reaches 44pt.
    private func more(_ text: String) -> some View {
        Text(text).font(.footnote.weight(.semibold)).foregroundStyle(theme.accent)
            .padding(.vertical, 14).padding(.leading, 20)
            .contentShape(Rectangle())
            .padding(.vertical, -14)
    }

    // MARK: friends

    private var friendRow: some View {
        let circle = friends.circle
        let today = BetMath.etDay(Date())
        return VStack(alignment: .leading, spacing: 12) {
            SectionTitle(title: "Friends", note: circle.friends.isEmpty ? nil : "\(circle.friends.count)") {
                if !circle.incoming.isEmpty { TagView(text: "\(circle.incoming.count) to answer", color: .orange) }
                NavigationLink { FriendsView() } label: { more("Feed") }.buttonStyle(.plain)
                    .accessibilityLabel("Friends feed")
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(circle.friends) { f in
                        let n = friends.bets.filter { $0.userId == f.userId && Models.date($0.placedAt).map(BetMath.etDay) == today }.count
                        NavigationLink { FriendProfileView(friend: f) } label: { FriendFace(p: f, today: n) }.buttonStyle(.plain)
                            .accessibilityLabel(n > 0 ? "\(f.name), \(n) bet\(n == 1 ? "" : "s") today" : f.name)
                    }
                    NavigationLink { FriendsView() } label: {
                        VStack(spacing: 6) {
                            Image(systemName: "plus").font(.title3.weight(.medium)).foregroundStyle(.secondary)
                                .frame(width: 52, height: 52).background(theme.cardColor, in: Circle())
                                .padding(4)
                            Text("Add").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        }
                        .frame(width: 70)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Add a friend")
                }
                .padding(.horizontal, 16).padding(.vertical, 4)
            }
            .padding(.horizontal, -16)
        }
    }

    // MARK: BetLab, the system

    private var system: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle("BetLab")
            card {
                link(ProfileRow("Ask BetLab", sub: "Your bets, tonight's board, any game")) { ChatView() }
                Divider()
                link(ProfileRow("How the model is doing", sub: "Strengths and weak spots by market")) { ModelMarketsView() }
                if owner {
                    Divider()
                    link(ProfileRow(title: "Reviews and plan", sub: "The Tuesday review and the to-do list") { EmptyView() } trailing: {
                        if mine > 0 { TagView(text: "\(mine) for you", color: .blue) }
                    }) { ReviewsPlanView() }
                }
            }
        }
    }

    // MARK: Extras

    /// What is opened rarely, as chips. Prices opens Record and stats at its Prices page; Markets is the second page of
    /// How the model is doing.
    private var extras: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionTitle("Extras")
            Flow(spacing: 8) {
                LinkChip(text: "Learn") { LearnView() }
                LinkChip(text: "Wrapped") { WrappedView(bets: counted.bets) }
                if store.myBooks.contains("Novig") { LinkChip(text: "Novig challenges") { ChallengesView() } }   // Novig off (Nov 6): none
                LinkChip(text: "CFB Pick'em") { PickemView() }
                LinkChip(text: "Prices") { RecordHub(start: .prices) }
                LinkChip(text: "Calendar") { CalendarView() }
                LinkChip(text: "DFS lineups") { DfsView() }
                LinkChip(text: "Intro") { WelcomeView() }
            }
        }
    }

    private func card<C: View>(@ViewBuilder _ content: () -> C) -> some View {
        VStack(spacing: 0) { content() }
            .padding(.horizontal, 16).padding(.vertical, 2)
            .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
    }

    @ViewBuilder private var hookScreen: some View {
        switch hook {
        case "settings": SettingsView()
        case "record": RecordHub(start: .record)
        case "stats": RecordHub(start: .stats)
        case "prices": RecordHub(start: .prices)
        case "promos": PromosView()
        case "ladder": LadderScreen()
        case "friends": FriendsView()
        case "chat": ChatView()
        case "model": ModelMarketsView()
        case "learn": LearnView()
        case "wrapped": WrappedView(bets: counted.bets)
        case "challenges": ChallengesView()
        case "pickem": PickemView()
        case "calendar": CalendarView()
        case "dfs": DfsView()
        case "intro": WelcomeView()
        case "search": SearchView()
        default: EmptyView()
        }
    }

    private func link<L: View, D: View>(_ label: L, @ViewBuilder _ dest: @escaping () -> D) -> some View {
        NavigationLink { dest() } label: { label }.buttonStyle(.plain)
    }
}
