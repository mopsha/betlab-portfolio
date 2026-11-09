import SwiftUI

/// What a game's page reads (web/lib/data.ts gameData): the game, all its active offers and tickets, its analysis.
@MainActor
final class GameModel: ObservableObject {
    @Published private(set) var game: Game?
    @Published private(set) var offers: [Offer] = []
    @Published private(set) var tickets: [Ticket] = []
    @Published private(set) var analysis: [String: JSON] = [:]
    @Published private(set) var error: String?
    @Published private(set) var loaded = false
    @Published private(set) var art: GameLive?        // ESPN's game: logos, colors, score and clock (Live.art)

    private struct AnalysisRow: Decodable { let kind: String; let body: JSON }

    func load(_ api: SupabaseClient, gameId: String) async {
        let one = SupabaseClient.Filter(eq: [("game_id", gameId)])
        let active = SupabaseClient.Filter(eq: [("game_id", gameId)], active: true)
        do {
            async let g: [Game] = api.rows("games", one)
            async let o: [Offer] = api.rows("offers", active)
            async let t: [Ticket] = api.rows("fun_tickets", active)
            async let a: [AnalysisRow] = api.rows("game_analysis", SupabaseClient.Filter(eq: [("game_id", gameId)], select: "kind,body"), plain: true)
            let (games, offers0, tickets0, rows) = try await (g, o, t, a)
            let offers = BooksOff.mine(offers0)     // at the account's books (Nov 6)
            let tickets = BooksOff.tickets(tickets0)
            game = games.first
            self.offers = offers.sorted(by: FeedLogic.byEv)
            self.tickets = tickets
            analysis = Dictionary(rows.map { ($0.kind, $0.body) }, uniquingKeysWith: { a, _ in a })
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
        await refreshScore()
    }

    func refreshScore() async {
        if let g = game, let a = await Live.art(for: [g])[g.gameId] { art = a }
    }

    /// Poll again soon: the game is on, or starts within 20 minutes (LiveModel.soon).
    var scoreSoon: Bool {
        guard let a = art else { return false }
        return a.state == "in" || (a.state == "pre" && (Models.date(a.start)?.timeIntervalSinceNow ?? .infinity) < 20 * 60)
    }
}

/// A game's page (the overhaul, Nov 4; web game page): the score large between the two logos with the teams' colors
/// as light behind it, your own bet on it, the bets and parlays to act on, then the analysis as sections and folds.
struct GameView: View {
    let gameId: String
    var title: String? = nil
    @EnvironmentObject private var store: BetStore
    @StateObject private var model = GameModel()
    /// Your bets' legs on this game as rings (web GameBets): the Live tab's tracker, quiet.
    @StateObject private var live: LiveModel = { let m = LiveModel(); m.quiet = true; return m }()
    @Environment(\.scenePhase) private var phase
    @Environment(\.theme) private var theme

    /// Your open bets with a leg in this game: a built or read slip names its games; a pick or a ticket carries the matchup.
    private var mine: [MyBet] {
        let matchup = model.game?.matchup ?? ""
        return store.bets.filter { b in
            guard b.isOpen else { return false }
            if Stats.games(b).contains(where: { $0.ref == gameId }) { return true }
            return !matchup.isEmpty && b.matchup == matchup
        }
    }

    var body: some View {
        let (offers, tickets) = Bans.filter(model.offers, model.tickets, store.bans)   // the ban list (Oct 25)
        let bets = offers.filter { $0.tier != .check }
        let checks = offers.filter { $0.tier == .check }
        let sgps = tickets.filter { $0.kind == "sgp" }
        let overs = tickets.filter { $0.kind == "over" }
        let (top, folds) = GameAnalysis.sections(model.analysis)
        let yours = mine
        List { Group {
            if model.game != nil || model.art != nil {
                Section {
                    GameHero(game: model.game, art: model.art?.reading, chance: GameHero.chance(model.analysis, model.game).map { c in
                        // soccer reads home team first (Nov 5): its chance goes first too
                        Fmt.isSoccer(model.game?.league ?? model.art?.sport) ? GameHero.Chance(away: c.home, home: c.away, note: c.note) : c }).bareRow()
                }
            }
            if let g = model.game {
                let meta = GameAnalysis.meta(model.analysis), badges = GameAnalysis.badges(model.analysis)
                Section {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("\(Fmt.sportName(g.league)) · \(Fmt.dayTime(g.commenceTime)) ET").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        ForEach(meta, id: \.self) { Text($0).font(.footnote) }
                        if !badges.isEmpty {
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack { ForEach(badges, id: \.self) { TagView(text: $0, color: .orange) } }
                            }
                        }
                    }
                }
            }
            if let e = model.error { Section { Label(e, systemImage: "exclamationmark.triangle").foregroundStyle(.red) } }
            if !yours.isEmpty {
                Section { ForEach(yours) { YourBetRow(b: $0, legs: legsHere($0)) } } header: { head(yours.count == 1 ? "Your bet" : "Your bets") }
            }
            if let nb = model.analysis["nfl_preview"]?["notebook"], NotebookView.has(nb) {
                Section { NotebookView(nb: nb, bet: bets.first) }
            }
            if !bets.isEmpty || !sgps.isEmpty {
                Section {
                    ForEach(bets) { BetRowView(o: $0, showGame: false) }
                    ForEach(sgps) { TicketRowView(t: $0, title: $0.body.theme ?? "Parlay") }
                } header: {
                    head("Bets on this game", note: [count(bets.count, "bet"), count(sgps.count, "parlay")].compactMap { $0 }.joined(separator: " · "))
                } footer: {
                    if !sgps.isEmpty, let g = model.game, (Models.date(g.commenceTime).map { $0 > Date() } ?? false) {
                        Text(store.watching.contains(g.gameId) ? "You're watching: its parlays join Today's Parlays when the slice locks, with an alert."
                             : "Tap the eye to watch: its parlays join Today when the slice locks, with an alert.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            if !overs.isEmpty {
                Section { ForEach(overs) { TicketRowView(t: $0, title: $0.body.label ?? $0.body.theme ?? "Over") } } header: { head("To root for") }
            }
            // the Notebook says it itself ("Nothing worth betting in this game")
            if model.loaded && model.game != nil && bets.isEmpty && sgps.isEmpty && overs.isEmpty
                && !NotebookView.has(model.analysis["nfl_preview"]?["notebook"]) {
                Section {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Nothing to act on in this game").bold()
                        Text("No pick, lean or parlay cleared the bar.\(model.analysis.isEmpty ? "" : " The analysis is below.")").font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            ForEach(top) { f in Section { f.body } header: { head(f.title, note: f.n.map(String.init)) } }
            if !checks.isEmpty || !folds.isEmpty {
                Section {
                    if !checks.isEmpty {
                        Fold(title: "Check the news", n: checks.count) { ForEach(checks) { BetRowView(o: $0, showGame: false) } }
                    }
                    ForEach(folds) { f in
                        Fold(title: f.title, n: f.n) { f.body.padding(.vertical, 4) }
                    }
                } header: { head("Analysis") }
            }
        }.themedRows() }
        // the page, with the two teams' colors as light in its top corners (never a painted band)
        .scrollContentBackground(.hidden)
        .background {
            ZStack {
                theme.pageColor
                PageGlow(left: Color(hex: model.art?.reading.away.color), right: Color(hex: model.art?.reading.home.color))
            }
            .ignoresSafeArea()
        }
        .navigationTitle(model.game.map { Fmt.matchup($0.matchup, sport: $0.league) } ?? title ?? "Game")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            // Watch (Nov 7): this game's own parlays join Today when its slice locks, with the lock alert
            if let g = model.game, (Models.date(g.commenceTime).map { $0 > Date() } ?? false) {
                let on = store.watching.contains(g.gameId)
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { _ = await store.setWatching(g.gameId, !on) } } label: {
                        Label(on ? "Watching" : "Watch", systemImage: on ? "eye.fill" : "eye")
                    }
                    .accessibilityHint(on ? "Stop getting its parlays on Today" : "Get this game's own parlays on Today when its slice locks")
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink { SearchView() } label: { Label("Search", systemImage: "magnifyingglass") }
            }
        }
        .overlay { if !model.loaded { ProgressView() } }
        .modifier(HardTopEdge())       // the hero and notes scrolled through the header's title (Nov 6)
        .refreshable { await model.load(store.api, gameId: gameId) }
        .task(id: store.refreshTick) { await model.load(store.api, gameId: gameId) }
        // the scoreboard keeps up: My bets' pace (20 s while the game is on, else 5 minutes), only while it's on screen
        .task(id: phase == .active) {
            guard phase == .active else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: model.scoreSoon ? LiveModel.fast : LiveModel.slow)
                if !Task.isCancelled { await model.refreshScore() }
            }
        }
        // your bets' legs: read at once, then at the scoreboard's pace
        .task(id: "\(phase == .active)|\(mine.map(\.betId).sorted().joined(separator: ","))") {
            let open = Set(mine.map(\.betId))
            guard phase == .active, !open.isEmpty else { return }
            while !Task.isCancelled {
                await live.refresh(store.api, open: open)
                try? await Task.sleep(for: live.soon || model.scoreSoon ? LiveModel.fast : LiveModel.slow)
            }
        }
    }

    /// A bet's legs on this game: its tracked game with this game's ESPN id or teams (web GameBets); nil before the tracker
    /// answers, so the row shows the legs as text until then.
    private func legsHere(_ b: MyBet) -> [LegLive]? {
        guard let l = live.bets[b.betId] else { return nil }
        let a = model.art?.reading
        let g = l.games.first { g in
            guard let a else { return false }
            return (!a.espnId.isEmpty && g.espnId == a.espnId) || (g.home.name == a.home.name && g.away.name == a.away.name)
        } ?? (l.games.count == 1 ? l.games.first : nil)
        guard let g else { return nil }
        let here = l.legs.filter { $0.gameKey == g.key }
        return here.isEmpty ? nil : here
    }

    private func head(_ title: String, note: String? = nil) -> some View {
        SectionTitle(title, note: note?.isEmpty == true ? nil : note).foregroundStyle(.primary).padding(.bottom, 4)
    }

    private func count(_ n: Int, _ word: String) -> String? { n == 0 ? nil : "\(n) \(word)\(n == 1 ? "" : "s")" }
}

/// The top of a game's page: both logos large, the score (the start before the game), the clock as a pill while it's
/// on, and where a chance to win is known, a bar in the two teams' colors. A logo opens the team's card.
struct GameHero: View {
    let game: Game?
    let art: GameLive?
    let chance: Chance?

    struct Chance { let away: Double; let home: Double; let note: String }

    /// A chance to win where the analysis carries one: the NHL's line (else our model), soccer's market with the draw between.
    static func chance(_ an: [String: JSON], _ g: Game?) -> Chance? {
        let ok = { (p: Double) in p > 0 && p < 1 }
        if let n = an["nhl"] {
            if let p = n["line"]["p_home"].double, ok(p) { return Chance(away: 1 - p, home: p, note: "The market's chance to win") }
            if let p = n["model"]["p_home"].double, ok(p) { return Chance(away: 1 - p, home: p, note: "Our model's chance to win") }
        }
        if let s = an["soccer"], let h = g?.home, let a = g?.away {
            let p = { (side: String) in s["lines"].array.first { $0["side"].string == side }?["p_market"].double }
            if let ph = p(h), let pa = p(a), ok(ph), ok(pa), ph + pa <= 1.001 {
                return Chance(away: pa, home: ph, note: "The market's chance to win")
            }
        }
        return nil
    }

    private var names: (away: String, home: String) {
        let parts = (game?.matchup ?? "").components(separatedBy: " @ ")
        let full = { (s: LiveSide?) in s.flatMap { $0.name.isEmpty ? nil : $0.name } }
        let away = game?.away ?? parts.first ?? "", home = game?.home ?? (parts.count > 1 ? parts[1] : "")
        let flip = Fmt.isSoccer(art?.sport ?? game?.league)          // `art` is in reading order already
        return (full(art?.away) ?? (flip ? home : away), full(art?.home) ?? (flip ? away : home))
    }

    var body: some View {
        let ufc = (art?.sport ?? game?.league) == "ufc"
        let state = art?.state ?? "pre"
        let scored = !ufc && state != "pre" && art != nil
        let a = art?.away.score ?? 0, h = art?.home.score ?? 0
        VStack(spacing: 16) {
            HStack(alignment: .center, spacing: 4) {
                side(art?.away, name: names.away, ufc: ufc, ball: art?.ball == "away", won: art?.winner == "away")
                Spacer(minLength: 0)
                VStack(spacing: 8) {
                    if state == "in", let g = art {
                        LivePill(text: (g.redZone ? "Red zone · " : "") + (g.detail.isEmpty ? "Live" : g.detail))
                    } else if state == "post" {
                        Text("FINAL").font(.caption2.weight(.heavy)).foregroundStyle(.secondary)
                    }
                    if scored {
                        HStack(alignment: .firstTextBaseline, spacing: 14) {
                            score(a, lead: a >= h)
                            score(h, lead: h >= a)
                        }
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel("\(names.away) \(Live.js(a)), \(names.home) \(Live.js(h))")
                    } else if state == "post" {
                        Text(art?.result ?? "").font(.footnote.weight(.semibold)).multilineTextAlignment(.center)
                    } else {
                        let start = game?.commenceTime ?? art?.start
                        Text(Fmt.time(start)).font(.system(size: 32, weight: .heavy)).monospacedDigit().lineLimit(1).minimumScaleFactor(0.6)
                        if let d = Models.date(start) {
                            Text(BetMath.etDay(d) == BetMath.etDay(Date()) ? "Today" : Fmt.longDay(d)).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        }
                    }
                    // the down and distance on its own line under the score (football)
                    if state == "in", let down = art?.down {
                        Text(down).font(.caption2.weight(.semibold).monospaced()).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                .frame(maxWidth: .infinity)
                Spacer(minLength: 0)
                side(art?.home, name: names.home, ufc: ufc, ball: art?.ball == "home", won: art?.winner == "home")
            }
            if let c = chance { bar(c) }
        }
        .padding(.top, 6).padding(.bottom, 2)
    }

    private func score(_ v: Double, lead: Bool) -> some View {
        Text(Live.js(v)).font(.system(size: 58, weight: .heavy)).monospacedDigit().kerning(-1.5)
            .foregroundStyle(lead ? Color.primary : .secondary).lineLimit(1).minimumScaleFactor(0.5)
    }

    private func side(_ s: LiveSide?, name: String, ufc: Bool, ball: Bool, won: Bool) -> some View {
        VStack(spacing: 6) {
            CardTap(ref: ufc || s == nil ? nil : CardRef(kind: .team, name: s!.name, abbr: s!.abbr)) {
                TeamLogo(url: s?.logo, name: name, size: 64, round: ufc)
            }
            Text(name).font(.subheadline.weight(.bold)).multilineTextAlignment(.center).lineLimit(2).minimumScaleFactor(0.7)
                .fixedSize(horizontal: false, vertical: true)
            if ball {
                Text("has the ball").font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
            } else if won {
                Text("won").font(.caption2.weight(.heavy)).foregroundStyle(.green)
            }
        }
        .frame(width: 104)
    }

    /// Away's share, the draw's (soccer) in gray, home's: each in its team color.
    private func bar(_ c: Chance) -> some View {
        let draw = max(0, 1 - c.away - c.home)
        let left = Color(hex: art?.away.color) ?? .gray, right = Color(hex: art?.home.color) ?? Color.accentColor
        return VStack(spacing: 8) {
            GeometryReader { g in
                let w = g.size.width - (draw > 0.005 ? 6 : 3)
                HStack(spacing: 3) {
                    Capsule().fill(left).frame(width: max(4, w * c.away))
                    if draw > 0.005 { Capsule().fill(Color(.systemFill)).frame(width: max(4, w * draw)) }
                    Capsule().fill(right)
                }
            }
            .frame(height: 8)
            HStack {
                Text(Fmt.pct(c.away)).monospacedDigit().foregroundStyle(c.away >= c.home ? Color.primary : .secondary)
                Spacer()
                Text(c.note + (draw > 0.005 ? " · draw \(Fmt.pct(draw))" : "")).foregroundStyle(.secondary)
                Spacer()
                Text(Fmt.pct(c.home)).monospacedDigit().foregroundStyle(c.home >= c.away ? Color.primary : .secondary)
            }
            .font(.footnote)
            .padding(.horizontal, 4)      // the hero is a bare row: at its very edge the numbers lost their outer strokes (Nov 6)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(c.note): \(names.away) \(Fmt.pct(c.away)), \(names.home) \(Fmt.pct(c.home))")
    }
}

/// Your own open bet on this game, compact: what it is, where and how much, and its price; its legs on this game as rings
/// once the tracker has them (web GameBets), else as text.
private struct YourBetRow: View {
    let b: MyBet
    var legs: [LegLive]? = nil

    var body: some View {
        let all = b.legs ?? []
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(all.count > 1 ? Stats.betName(legs: all, label: nil, price: nil) : BetMath.what(b)).font(.headline).lineLimit(2)
                if let legs {
                    HStack(spacing: 8) {
                        ForEach(Array(legs.prefix(5).enumerated()), id: \.offset) { _, l in LegRing(l: l, size: legs.count > 4 ? 40 : 46, tap: false) }
                        if legs.count > 5 { Text("+\(legs.count - 5)").font(.footnote).foregroundStyle(.secondary) }
                    }
                    .padding(.vertical, 2)
                    if all.count > legs.count { Text("\(legs.count) of its \(all.count) legs are on this game").font(.footnote).foregroundStyle(.secondary) }
                } else if all.count > 1 {
                    Text(all.map(Fmt.label).joined(separator: " · ")).font(.footnote).foregroundStyle(.secondary).lineLimit(3)
                }
                Text([b.book ?? "FanDuel", Marking.units(b.stake), b.isBonus ? "bonus bet" : nil,
                      (b.boost ?? 0) > 0 ? "\(Int(b.boost!))% boost" : nil, b.isReal ? nil : "paper"].compactMap { $0 }.joined(separator: " · "))
                    .font(.caption.weight(.semibold)).foregroundStyle(.tertiary)
            }
            Spacer(minLength: 4)
            Text(Fmt.am(b.price)).font(.system(.title3, design: .monospaced).weight(.bold)).foregroundStyle(.tint)
        }
        .padding(.vertical, 2)
    }
}

/// A folded analysis section; open from the start under the `-expandFolds YES` testing hook.
private struct Fold<Content: View>: View {
    let title: String
    var n: Int? = nil
    @ViewBuilder let content: () -> Content
    @State private var open = UserDefaults.standard.bool(forKey: "expandFolds")
    var body: some View {
        DisclosureGroup(isExpanded: $open, content: content) {
            HStack(spacing: 8) {
                Text(title).font(.body.weight(.semibold)).foregroundStyle(.primary)
                if let n { Text("\(n)").font(.footnote.weight(.semibold)).foregroundStyle(.secondary) }
            }
        }
    }
}
