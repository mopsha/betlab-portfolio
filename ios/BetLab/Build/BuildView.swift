import SwiftUI

/// The slip at one book: its evaluation there (nil when a leg isn't posted or the legs can't be priced together), the
/// legs that book doesn't post, and its price: exact (typed, a plain parlay's own product, Novig's quote) or, for a
/// same-game slip nobody has typed a price for, the likely quote (the book's usual payout share).
struct SlipSide: Identifiable {
    let book: BuildBook
    let eval: Evaluation?
    let missing: [String]
    let exact: Double?
    let likely: Double?
    var id: String { book.rawValue }
    var price: Double? { exact ?? likely }
}

/// What Build reads (web buildData): the games with a leg pack that haven't started, and FanDuel's usual payout
/// pattern (fun_results). Packs load per game (an NFL pack reaches 200 KB). Slips are kept on this phone, one per
/// sport, until saved (the web keeps them in the browser the same way).
@MainActor
final class BuildModel: ObservableObject {
    @Published private(set) var games: [PackGame] = []
    @Published private(set) var bands: [Band] = Build.defaultBands
    @Published private(set) var quoteModel: QuoteModel?
    @Published private(set) var packs: [String: Pack] = [:] { didSet { pricers = Self.pricers(packs) } }
    @Published private(set) var failed: Set<String> = []
    @Published private(set) var loaded = false
    @Published private(set) var error: String?
    @Published var sport = "nfl"
    @Published var gameId = ""
    @Published var query = ""
    @Published var tab = ""
    /// The book the board's prices come from (the header's menu). The slip shows all three.
    @Published var book: BuildBook = .fanduel
    @Published private(set) var slips: [String: Slip] = [:]
    @Published var slipOpen = false
    /// A bonus bet or profit boost on the slip (Oct 22): the slip shows its value. A launch argument sets it too.
    @Published var promo = Promo(stored: UserDefaults.standard.string(forKey: BuildModel.promoKey)) {
        didSet {
            UserDefaults.standard.set(promo.stored, forKey: Self.promoKey)
            if promo.kind == .none, promoBook != nil { promoBook = nil }
            if let t = promoToken, Promos.asPromo(t) != promo { promoToken = nil }     // typed over: no longer that token
        }
    }
    /// The wallet token on the slip, when the promo is one (Nov 9): I placed this saves the bet with it (its id and dollars).
    /// Not kept across launches: the wallet may have changed.
    @Published var promoToken: PromoRow?
    /// The book the promo is from, when it names one (a wallet token's, or picked): the slip goes there, not to the
    /// best price. Nil: the best price.
    @Published var promoBook: BuildBook? = BuildBook(rawValue: UserDefaults.standard.string(forKey: BuildModel.promoKey + "-book") ?? "") {
        didSet { UserDefaults.standard.set(promoBook?.rawValue ?? "", forKey: Self.promoKey + "-book") }
    }
    /// Novig's exact price for the slip (Oct 28; web api/novig), asked when the legs change.
    @Published private(set) var novig: (key: String, quote: NovigQuote?)?
    /// The themed slips (Nov 4), worked out when the Ideas tab is open.
    @Published private(set) var ideas: [Build.SlipTheme: Build.ThemedSlip] = [:]
    @Published private(set) var ideasFor = ""
    /// One pricer per book for a set of packs, so each one's bitset cache lasts across renders.
    private(set) var pricers: [BuildBook: Pricer] = BuildModel.pricers([:])
    var pricer: Pricer { pricers[book]! }

    /// A slip's legs, and a price typed for it at each book (by the book's name).
    struct Slip: Codable { var legs: [SlipLeg] = []; var prices: [String: String]? = nil }
    private static let key = "betlab-build-v2"
    static let promoKey = "betlab-build-promo"
    static let boosts: [Double] = [25, 30, 50, 100]
    static let scan = 16                                  // the themed slips search the sport's next 16 games
    static let ideasTab = "ideas"

    nonisolated private static func pricers(_ packs: [String: Pack]) -> [BuildBook: Pricer] {
        Dictionary(uniqueKeysWithValues: BuildBook.allCases.map { ($0, Pricer(packs, book: $0)) })
    }

    var sports: [String] { Array(Set(games.map(\.sport))).sorted { a, b in games.firstIndex { $0.sport == a }! < games.firstIndex { $0.sport == b }! } }
    var inSport: [PackGame] { games.filter { $0.sport == sport } }
    var slip: Slip { slips[sport] ?? Slip() }
    var current: String { inSport.contains { $0.eventId == gameId } ? gameId : inSport.first?.eventId ?? "" }
    var ready: Bool { slip.legs.allSatisfy { packs[$0.eventId] != nil } }
    var nGames: Int { Set(slip.legs.map(\.eventId)).count }

    // MARK: the slip at each book

    /// The price typed for the slip at a book; at Novig, its live quote when nothing is typed.
    func priceText(_ b: BuildBook) -> String {
        let typed = slip.prices?[b.rawValue] ?? ""
        if !typed.isEmpty || b != .novig { return typed }
        guard let n = novig, n.key == novigKey, let q = n.quote else { return "" }
        return Fmt.am(q.price).replacingOccurrences(of: Fmt.minus, with: "-")
    }
    func typed(_ b: BuildBook) -> String { slip.prices?[b.rawValue] ?? "" }

    func side(_ b: BuildBook) -> SlipSide {
        let pr = pricers[b]!, legs = slip.legs
        let missing = legs.filter { pr.leg($0.eventId, $0.label)?.unavailable == true }.map(\.label)
        guard !legs.isEmpty, ready, let e = Build.evaluate(pr, legs, priceText: priceText(b), bands: bands, model: quoteModel) else {
            return SlipSide(book: b, eval: nil, missing: missing, exact: nil, likely: nil)
        }
        if let t = e.typed { return SlipSide(book: b, eval: e, missing: missing, exact: t, likely: nil) }
        if b == .novig {
            // one leg: Novig's own price for it, when $50+ stands behind it (else the pricer shows our fair price)
            let own = legs.count == 1 ? packs[legs[0].eventId]?.legs[legs[0].label]?.nvPrice : nil
            return SlipSide(book: b, eval: e, missing: missing, exact: own, likely: nil)
        }
        // one leg per game pays exactly the legs' product; a same-game slip the usual payout share, capped as the finder caps it
        if e.games.count == legs.count { return SlipSide(book: b, eval: e, missing: missing, exact: Odds.am(e.naive).rounded(), likely: nil) }
        let dec = min(min(e.typical, bands.map(\.ratio).max() ?? 1) / e.p, e.naive)
        return SlipSide(book: b, eval: e, missing: missing, exact: nil, likely: Odds.am(dec).rounded())
    }
    var sides: [SlipSide] { BuildBook.mine.map(side) }

    /// The book with the best exact price (a tie goes to FanDuel, then DraftKings, as on a ticket).
    func best(_ sides: [SlipSide]) -> SlipSide? {
        var best: SlipSide?
        for s in sides where s.eval != nil {
            if let p = s.exact, best == nil || Odds.dec(p) > Odds.dec(best!.exact!) + 1e-9 { best = s }
        }
        return best
    }

    /// Where the slip goes: the promo's book when it names one, else the best exact price, else the header's book.
    func target(_ sides: [SlipSide]) -> SlipSide {
        if promo.kind != .none, let b = promoBook, let s = sides.first(where: { $0.book == b }) { return s }
        return best(sides) ?? sides.first { $0.book == book && $0.eval != nil } ?? sides.first { $0.eval != nil }
            ?? sides.first { $0.book == book } ?? sides[0]
    }

    // MARK: Novig's quote

    var novigIds: [String]? { slip.legs.count >= 2 && BuildBook.mine.contains(.novig) ? pricers[.novig]!.novigIds(slip.legs) : nil }
    var novigKey: String { novigIds?.joined(separator: ",") ?? "" }
    var novigNow: (key: String, quote: NovigQuote?)? { novig?.key == novigKey ? novig : nil }

    /// Ask Novig's pricer once the legs have stood still for a moment (each change would be a call).
    func askNovig() async {
        guard let ids = novigIds else { return }
        let key = novigKey
        try? await Task.sleep(nanoseconds: 700_000_000)
        guard !Task.isCancelled else { return }
        let q = await NovigQuote.fetch(ids)
        guard key == novigKey else { return }
        novig = (key, q)
    }

    // MARK: ideas (themed slips)

    var scanned: [String] { inSport.prefix(Self.scan).map(\.eventId) }        // games are sorted by start
    var wantsIdeas: Bool { tab == Self.ideasTab }
    var ideasLoading: Bool { scanned.contains { packs[$0] == nil && !failed.contains($0) } }
    var ideasKey: String {
        guard wantsIdeas else { return "" }
        return "\(Bans.current.count)|\(book.rawValue)|" + scanned.filter { packs[$0] != nil }.joined(separator: ",")
    }

    /// One slip per theme, worked out off the main thread (each looks through every leg of the next 16 games).
    func refreshIdeas() async {
        guard wantsIdeas else { return }
        try? await Task.sleep(nanoseconds: 250_000_000)      // packs arrive one after another: wait for a pause
        guard !Task.isCancelled else { return }
        let (packs, book, ids, bans, key) = (packs, book, scanned, Bans.current, ideasKey)
        let out = await Task.detached(priority: .userInitiated) {
            let pr = Pricer(packs, book: book)
            var d: [Build.SlipTheme: Build.ThemedSlip] = [:]
            for t in Build.SlipTheme.allCases { d[t] = Build.themedSlip(pr, ids, t, bans: bans) }
            return d
        }.value
        guard key == ideasKey else { return }           // the book or games changed meanwhile: a newer run has it
        (ideas, ideasFor) = (out, key)
    }

    // MARK: loading

    private struct Meta: Decodable { let oddsEventId: String; let sport: String?; let commenceTime: String; let matchup: String?; let part: String? }
    private struct FunResults: Decodable {
        struct Typical: Decodable { let bands: [Band]?; let model: QuoteModel? }
        let typicalRatio: Typical?
    }
    private struct PackRow: Decodable { let body: PackPart }

    func load(_ api: SupabaseClient) async {
        do {
            async let m: [Meta] = api.rows("leg_packs", .init(select: "odds_event_id,sport,commence_time,matchup:body->>matchup,part:body->>part",
                                                              gt: ("commence_time", Date()), limit: 2000))
            async let f: FunResults? = api.doc("app", "fun_results")
            let (meta, fun) = try await (m, f)
            games = meta.filter { Double($0.part ?? "1") ?? 1 == 1 }
                .map { PackGame(eventId: $0.oddsEventId, matchup: $0.matchup ?? "", commenceTime: $0.commenceTime, sport: $0.sport ?? "nfl") }
                .sorted { $0.commenceTime < $1.commenceTime }
            if let b = fun?.typicalRatio?.bands, !b.isEmpty { bands = b }
            quoteModel = fun?.typicalRatio?.model
            restore()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
        await loadPacks(api)
    }

    /// Back in the foreground or 5 minutes on: the game list and the prices of what's open, keeping the slip as it is.
    func refresh(_ api: SupabaseClient) async {
        guard loaded else { return }
        failed = []             // a game with no pack 5 minutes ago may have one now
        if let m: [Meta] = try? await api.rows("leg_packs", .init(select: "odds_event_id,sport,commence_time,matchup:body->>matchup,part:body->>part",
                                                                  gt: ("commence_time", Date()), limit: 2000)) {
            games = m.filter { Double($0.part ?? "1") ?? 1 == 1 }
                .map { PackGame(eventId: $0.oddsEventId, matchup: $0.matchup ?? "", commenceTime: $0.commenceTime, sport: $0.sport ?? "nfl") }
                .sorted { $0.commenceTime < $1.commenceTime }
        }
        let open = Set([current] + slip.legs.map(\.eventId)).filter { !$0.isEmpty }
        await withTaskGroup(of: (String, Pack?).self) { group in
            for eid in open {
                group.addTask {
                    let parts: [PackRow]? = try? await api.rows("leg_packs", .init(eq: [("odds_event_id", eid)], select: "body"))
                    return (eid, parts.flatMap { Pack.merge($0.map(\.body)) })
                }
            }
            for await (eid, pk) in group { if let pk { packs[eid] = pk } }
        }
        await loadPacks(api)        // and Ideas' games that had none before
    }

    /// Each pack once: the picked game's, every game on the slip, and the next games when Ideas looks through them. A
    /// game whose read failed (a timeout, a 5xx) is asked again after a pause, up to 3 more times; only a game that
    /// answered with no usable pack is `failed` (Nov 9: one timeout left a game with no markets for the whole session).
    func loadPacks(_ api: SupabaseClient, attempt: Int = 0) async {
        let extra = wantsIdeas ? scanned : []
        let need = Set([current] + slip.legs.map(\.eventId) + extra).filter { !$0.isEmpty && packs[$0] == nil && !failed.contains($0) }
        guard !need.isEmpty else { return }
        var errored = false
        await withTaskGroup(of: (String, Pack?, Bool).self) { group in
            for eid in need {
                group.addTask {
                    do {
                        let parts: [PackRow] = try await api.rows("leg_packs", .init(eq: [("odds_event_id", eid)], select: "body"))
                        return (eid, Pack.merge(parts.map(\.body)), false)
                    } catch { return (eid, nil, true) }
                }
            }
            for await (eid, pk, threw) in group {
                if let pk { packs[eid] = pk } else if threw { errored = true } else { failed.insert(eid) }
            }
        }
        guard errored, attempt < 3 else { return }
        try? await Task.sleep(for: .seconds(10 << attempt))      // 10, 20, 40 s; a new game or tab cancels this task
        guard !Task.isCancelled else { return }
        await loadPacks(api, attempt: attempt + 1)
    }

    // MARK: the slip

    func toggle(_ eid: String, _ label: String) {
        var s = slip
        if let i = s.legs.firstIndex(where: { $0.eventId == eid && $0.label == label }) { s.legs.remove(at: i) }
        else { s.legs.append(SlipLeg(eventId: eid, label: label)) }
        if s.legs.isEmpty { slipOpen = false }
        slips[sport] = s
        persist()
    }
    func setPrice(_ p: String, book b: BuildBook) {
        var s = slip
        var prices = s.prices ?? [:]
        prices[b.rawValue] = p.isEmpty ? nil : p
        s.prices = prices
        slips[sport] = s
        persist()
    }
    func clear() { slips[sport] = Slip(); slipOpen = false; persist() }
    func choose(sport s: String) { sport = s; query = ""; tab = ""; persist() }
    func choose(game id: String) { gameId = id; tab = "" }
    func has(_ eid: String, _ label: String) -> Bool { slip.legs.contains { $0.eventId == eid && $0.label == label } }
    /// An idea replaces the slip and opens it.
    func use(_ legs: [SlipLeg]) { slips[sport] = Slip(legs: legs); persist(); slipOpen = true }

    private func persist() {
        if let d = try? JSONEncoder().encode(slips) { UserDefaults.standard.set(d, forKey: Self.key) }
        UserDefaults.standard.set(sport, forKey: Self.key + "-sport")
    }

    /// The slips on this phone, minus legs whose game has started.
    private func restore() {
        let live = Set(games.map(\.eventId))
        if let d = UserDefaults.standard.data(forKey: Self.key), let s = try? JSONDecoder().decode([String: Slip].self, from: d) {
            slips = s.mapValues { var x = $0; x.legs = x.legs.filter { live.contains($0.eventId) }; return x }
        }
        let sp = UserDefaults.standard.string(forKey: Self.key + "-sport")
        if let sp, sports.contains(sp) { sport = sp } else if let first = sports.first { sport = first }
    }
}

/// Build, reorganized (Nov 5; docs/OVERHAUL.md, web Builder.tsx: change both together). Three layers, then the
/// markets: the header (the title, the book the prices come from, saved parlays, search), the modes (Build · Check a
/// slip · Use a promo), and the sport with its strip of games. Below, one row of tabs for the picked game: Popular,
/// Lines, a tab per stat, Ideas (BuildMarkets.swift, BuildIdeas.swift). The slip floats above the tab bar and opens
/// into a sheet with its price at each book, its promo, and I placed this / Open / Save (BuildSlip.swift).
/// Legs from one sport only (Mike's rule); legs from more than one game make an SGP+.
struct BuildView: View {
    @EnvironmentObject private var store: BetStore
    @Environment(\.theme) private var theme
    @StateObject private var model = BuildModel()
    @State private var showSaved = false
    // testing hook (demo checks, Nov 6): `-openScreen check|promo` opens that mode at launch
    @State private var checking = false
    @State private var usingPromo = false
    @State private var searching = false
    @FocusState private var searchFocus: Bool
    @State private var art: [String: GameLive] = [:]     // ESPN's logos and colors, by the pack's event id

    /// What makes the packs worth loading again.
    private var packsKey: String {
        model.current + "|" + model.slip.legs.map(\.eventId).joined() + "|\(model.wantsIdeas)"
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                header
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        modes
                        if let e = model.error { Label(e, systemImage: "exclamationmark.triangle").foregroundStyle(.red).padding(.horizontal) }
                        if model.loaded && model.games.isEmpty {
                            ContentUnavailableView("Nothing to build from yet", systemImage: "hammer",
                                                   description: Text("Games show up here the morning of game day, once they're priced."))
                                .padding(.top, 40)
                        } else if !model.games.isEmpty {
                            sports
                            strip
                            Board(model: model, art: art)
                        }
                    }
                    .padding(.bottom, 12)
                }
                .scrollDismissesKeyboard(.immediately)
            }
            .background(theme.pageColor.ignoresSafeArea())
            .navigationTitle("Build")
            .toolbar(.hidden, for: .navigationBar)
            .safeAreaInset(edge: .bottom) { if !model.slip.legs.isEmpty { SlipBar(model: model, art: art) } }
            .sheet(isPresented: $model.slipOpen) {
                SlipSheet(model: model, art: art).environmentObject(store)
                    .presentationDetents([.large]).presentationDragIndicator(.visible)
            }
            .sheet(isPresented: $showSaved) { SavedParlaysView().environmentObject(store) }
            .sheet(isPresented: $checking) { SlipAddView() }
            .navigationDestination(isPresented: $usingPromo) { PromoFinderView(startGame: model.current.isEmpty ? nil : model.current) }
            .overlay { if !model.loaded { ProgressView() } }
            .task { if !model.loaded { await model.load(store.api) } }
            .onAppear { if !BuildBook.mine.contains(model.book) { model.book = BuildBook.mine.first ?? .fanduel } }   // a book that's off (Nov 6)
            .onChange(of: store.booksOff) { _, _ in if !BuildBook.mine.contains(model.book) { model.book = BuildBook.mine.first ?? .fanduel } }
            // testing hook (demo checks, Nov 6): `-openScreen check|promo` opens that mode just after launch
            .task {
                let s = UserDefaults.standard.string(forKey: "openScreen")
                guard s == "check" || s == "promo" else { return }
                try? await Task.sleep(for: .milliseconds(300))
                if s == "check" { checking = true } else { usingPromo = true }
            }
            .task(id: store.refreshTick) { if store.refreshTick > 0 { await model.refresh(store.api) } }
            .task(id: packsKey) { await model.loadPacks(store.api) }
            .task(id: model.inSport.map(\.eventId).joined(separator: ",")) { await loadArt() }
            .task(id: model.novigKey) { await model.askNovig() }
            .task(id: model.ideasKey) { await model.refreshIdeas() }
        }
    }

    /// The logos and colors of this sport's games, from ESPN's boards (cached; logos don't change).
    private func loadArt() async {
        let games = model.inSport.prefix(60).map { g -> Game in
            let parts = g.matchup.components(separatedBy: " @ ")
            return Game(gameId: g.eventId, league: g.sport, home: parts.count == 2 ? parts[1] : nil, away: parts.count == 2 ? parts[0] : nil,
                        matchup: g.matchup, commenceTime: g.commenceTime, state: nil)
        }
        guard !games.isEmpty else { return }
        let found = await Live.art(for: games, ttl: ESPN.doneTTL)
        art.merge(found) { _, new in new }
    }

    // MARK: layer 1, the header

    /// The title; on the right the book the prices come from, your saved parlays, and search. Search takes the row over.
    @ViewBuilder private var header: some View {
        if searching {
            HStack(spacing: 10) {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("Find a team or player", text: $model.query)
                        .focused($searchFocus).submitLabel(.search).autocorrectionDisabled()
                    if !model.query.isEmpty {
                        Button { model.query = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary) }
                            .buttonStyle(.plain).accessibilityLabel("Clear the search")
                    }
                }
                .kitField()
                Button("Cancel") { model.query = ""; searching = false }
                    .font(.subheadline.weight(.semibold)).frame(minHeight: 44)
            }
            .padding(.horizontal).padding(.vertical, 6)
            .onAppear { searchFocus = true }
        } else {
            HStack(spacing: 8) {
                Text("Build").font(.system(size: 30, weight: .heavy)).fixedSize()
                    .accessibilityAddTraits(.isHeader)
                Spacer(minLength: 4)
                bookMenu
                Button { showSaved = true } label: { IconDisc(systemName: "bookmark") }
                    .buttonStyle(.plain).accessibilityLabel("Your saved parlays")
                Button { searching = true } label: { IconDisc(systemName: "magnifyingglass") }
                    .buttonStyle(.plain).accessibilityLabel("Search teams and players")
            }
            .padding(.horizontal).padding(.vertical, 6)
        }
    }

    /// The book the board's prices come from: its icon and name; a tap lists the three.
    private var bookMenu: some View {
        Menu {
            Picker("Prices from", selection: $model.book) { ForEach(BuildBook.mine) { Text($0.rawValue).tag($0) } }
        } label: {
            HStack(spacing: 7) {
                BookIcon(book: model.book.rawValue, size: 22)
                Text(model.book.rawValue).font(.subheadline.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.8)
                Image(systemName: "chevron.down").font(.caption2.weight(.bold)).foregroundStyle(.tertiary)
            }
            .foregroundStyle(.primary)
            .padding(.horizontal, 12).frame(height: 40)
            .background(theme.cardColor, in: Capsule())
            .frame(minHeight: 44)
            .contentShape(Rectangle())
        }
        .accessibilityLabel("Prices from \(model.book.rawValue), change book")
    }

    // MARK: layer 2, the modes

    /// Build · Check a slip · Use a promo: the builder is this screen, the other two open their own.
    private var modes: some View {
        UnderTabs(items: [.init(key: "build", title: "Build"), .init(key: "check", title: "Check a slip"), .init(key: "promo", title: "Use a promo")],
                  selected: "build", spacing: 22, font: .headline) { key in
            if key == "check" { checking = true } else if key == "promo" { usingPromo = true }
        }
    }

    // MARK: layer 3, the sport and its games

    private var sports: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(model.sports, id: \.self) { s in
                    let n = model.slips[s]?.legs.count ?? 0
                    SportChip(title: (Fmt.sports[s] ?? s) + (n > 0 ? " · \(n)" : ""), league: s, selected: s == model.sport) { model.choose(sport: s) }
                        .frame(minHeight: 44)
                }
            }
            .padding(.horizontal)
        }
    }

    /// The games as small cards. The search finds games by team; when no game matches, the board filters its legs instead.
    private var strip: some View {
        let q = model.query.trimmingCharacters(in: .whitespaces).lowercased()
        let hits = q.isEmpty ? [] : model.inSport.filter { $0.matchup.lowercased().contains(q) }
        return ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(hits.isEmpty ? model.inSport : hits) { g in
                        GameCard(g: g, art: art[g.eventId], selected: g.eventId == model.current,
                                 picked: model.slip.legs.filter { $0.eventId == g.eventId }.count) {
                            model.choose(game: g.eventId)
                            if !hits.isEmpty { model.query = ""; searching = false }
                        }
                        .id(g.eventId)
                    }
                }
                .padding(.horizontal).padding(.vertical, 2)
            }
            .onChange(of: model.current) { _, id in withAnimation { proxy.scrollTo(id, anchor: .center) } }
        }
    }
}

/// Where a leg's picture comes from: its team's logo off the game's art.
enum BuildArt {
    static func logo(_ team: String?, _ g: GameLive?, matchup: String) -> String? {
        guard let team, !team.isEmpty, let g else { return nil }
        let parts = matchup.components(separatedBy: " @ ")
        if parts.count == 2 {
            if parts[0].contains(team) { return g.away.logo }
            if parts[1].contains(team) { return g.home.logo }
        }
        let t = team.lowercased()
        for s in [g.away, g.home] where !s.name.isEmpty && (s.name.lowercased().contains(t) || t.contains(s.name.lowercased())) { return s.logo }
        return nil
    }
}

/// A game to build from: both logos, the matchup, its start, and how many legs you've picked from it. The picked game
/// is ringed in the accent, with its home color as a soft light.
private struct GameCard: View {
    let g: PackGame
    let art: GameLive?
    let selected: Bool
    let picked: Int
    let action: () -> Void
    @Environment(\.theme) private var theme
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        // soccer reads home team first (Nov 5): its parts and logos in that order
        let soc = Fmt.isSoccer(g.sport), art = art?.reading
        let stored = g.matchup.components(separatedBy: " @ ")
        let parts = soc && stored.count == 2 ? Array(stored.reversed()) : stored
        let sep = soc ? "vs" : "@"
        let ufc = g.sport == "ufc"
        let short = art.flatMap { a in !a.away.abbr.isEmpty && !a.home.abbr.isEmpty ? "\(a.away.abbr) \(sep) \(a.home.abbr)" : nil }
        Button(action: action) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    TeamLogo(url: art?.away.logo, name: parts[0], size: 34, round: ufc)
                    if parts.count > 1 || art != nil { TeamLogo(url: art?.home.logo, name: parts.count > 1 ? parts[1] : "", size: 34, round: ufc) }
                    Spacer(minLength: 0)
                    if picked > 0 {
                        Text("\(picked)").font(.caption.bold().monospacedDigit()).frame(minWidth: 22, minHeight: 22)
                            .background(theme.accent, in: Capsule()).foregroundStyle(theme.onAccent(scheme))
                            .accessibilityLabel("\(picked) on your slip")
                    }
                }
                VStack(alignment: .leading, spacing: 2) {
                    if let short {
                        Text(short).font(.subheadline.weight(.bold)).lineLimit(1).minimumScaleFactor(0.8)
                    } else {
                        Text(parts[0]).font(.footnote.weight(.bold)).lineLimit(1)
                        if parts.count > 1 { Text("\(sep) " + parts[1]).font(.footnote.weight(.bold)).lineLimit(1) }
                    }
                    Text(Fmt.dayTime(g.commenceTime)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
            }
            .frame(width: 112, alignment: .leading)
            .padding(.horizontal, 14).padding(.vertical, 12)
            .background {
                ZStack(alignment: .topLeading) {
                    theme.cardColor
                    if selected, let c = Color(hex: art?.home.color) {
                        Circle().fill(c).frame(width: 120, height: 120).blur(radius: 34).opacity(scheme == .dark ? 0.32 : 0.2).offset(x: -40, y: -50)
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).strokeBorder(theme.accent, lineWidth: selected ? 1.5 : 0))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(g.matchup), \(Fmt.dayTime(g.commenceTime))")
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}
