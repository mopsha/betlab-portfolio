import SwiftUI

// The promo finder's screen (web components/promos/PromoFinder.tsx; the ranking and its rules are in PromoFinder.swift):
// three steps on one page, then the results. 1 Your token: the wallet's tokens as small cards (or type one), how much
// of it to use, and the book. 2 Where: a kickoff slice, games you pick, one game, or today, the games with their
// logos. 3 Rank by: Max value, Balanced or Safe, and whether to show two-book locks. Each result is a card built like
// the pick card (what, the price, three numbers); a lock shows its two bets linked. Place opens the sheet that saves it.

struct PromoFinderView: View {
    @EnvironmentObject private var store: BetStore
    @Environment(\.theme) private var theme
    @StateObject private var model = FinderModel()
    var promoId: String? = nil
    var startGame: String? = nil
    @State private var wallet: [PromoRow] = []
    @State private var pick = "typed"
    @State private var typedKind = "bonus"
    @State private var typedPct = "30"
    @State private var typedDollars = "10"
    /// The wager (Nov 3): up to the token's max, not always all of it; the results reprice at it (web PromoFinder).
    @State private var wager = ""
    @State private var book: BuildBook = .fanduel
    @State private var scopeKind = "slice"
    @State private var sliceKey = ""
    @State private var gameKey = ""
    @State private var picked: Set<String> = []
    @AppStorage("betlab-promo-mode") private var modeRaw = PromoFinder.Mode.balanced.rawValue
    /// Two-book locks only when asked (Mike, Oct 30: a lock tied up $35 of cash to make $2.18; web showLocks).
    @AppStorage("betlab-promo-locks") private var showLocks = false
    @State private var placing: PromoFinder.Result?
    @State private var art: [String: GameLive] = [:]      // ESPN's logos and colors, by the pack's event id

    private var mode: PromoFinder.Mode { PromoFinder.Mode(rawValue: modeRaw) ?? .balanced }
    private var token: PromoRow? { wallet.first { $0.promoId == pick } }
    private var promo: Promo {
        if let t = token {
            var p = Promos.asPromo(t)
            p.stake = Promos.wager(wager, max: t.amountDollars)
            return p
        }
        var p = typedKind == "boost" ? Promo.boost(min(max(Double(typedPct) ?? 0, 1), 500)) : Promo.bonus
        p.stake = Double(typedDollars)
        return p
    }
    /// A token for some sports only (its sports, or its note: "NBA Only") sees only their games (Oct 30).
    private var sports: [String]? { token.flatMap { Promos.sports($0) } }
    /// And one for some teams only (Oct 31: "boosts for specific games") only theirs.
    private var teams: [String]? { token?.teams.flatMap { $0.isEmpty ? nil : $0 } }
    /// Or the games picked for it when it was added (Nov 5).
    private var named: [PromoGame]? { token?.games.flatMap { $0.isEmpty ? nil : $0 } }
    private var games: [PackGame] {
        model.games.filter { g in (sports?.contains(g.sport) ?? true) && (token.map { Promos.fitsGame($0, eventId: g.eventId, matchup: g.matchup, start: g.commenceTime) } ?? true) }
    }
    private var slices: [Slices.Slice] { Slices.slicesOf(games) }
    private var scope: PromoFinder.Scope {
        switch scopeKind {
        case "slice": return .slice(slices.contains { $0.key == sliceKey } ? sliceKey : slices.first?.key ?? "")
        case "game": return .game(games.contains { $0.eventId == gameKey } ? gameKey : games.first?.eventId ?? "")
        case "games": return .games(games.map(\.eventId).filter { picked.contains($0) })
        default: return .today
        }
    }
    private var events: [String] { PromoFinder.scopeEvents(scope, games, slices, sports: sports) }
    private var runKey: String { "\(pick)|\(wager)|\(typedKind)|\(typedPct)|\(typedDollars)|\(book.rawValue)|\(modeRaw)|\(showLocks)|\(events.joined(separator: ","))|\(model.packs.count)" }
    private var hedgeBook: BuildBook { FinderModel.hedge(book) ?? book }

    /// A token for some games starts on all of them, whichever day they're on (web PromoFinder).
    private func pickTeamGames() {
        guard teams != nil || named != nil else { return }
        picked = Set(games.map(\.eventId)); scopeKind = "games"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                FinderStep(n: 1, title: "Your token")
                tokenStep
                FinderStep(n: 2, title: "Where").padding(.top, 10)
                whereStep
                FinderStep(n: 3, title: "Rank by").padding(.top, 10)
                rankStep
                results.padding(.top, 10)
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(theme.pageColor.ignoresSafeArea())
        .navigationTitle("Use a promo")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadWallet()
            if !BuildBook.mine.contains(book) { book = BuildBook.mine.first ?? .fanduel }
            if let id = promoId, wallet.contains(where: { $0.promoId == id }) { pick = id } else if let f = wallet.first { pick = f.promoId }
            if let b = token?.book, let bb = BuildBook(rawValue: b) { book = bb }
            await model.load(store.api)
            if let g = startGame, model.games.contains(where: { $0.eventId == g }) { scopeKind = "game"; gameKey = g }
        }
        .task(id: runKey) {
            await model.loadPacks(store.api, events)
            await model.refresh(events, promo: promo, book: book, mode: mode, locks: showLocks)
            await loadArt(games.filter { events.contains($0.eventId) })
        }
        .task(id: "\(games.count)|\(games.first?.eventId ?? "")") { await loadArt(Array(games.prefix(80))) }
        .onChange(of: pick) { _, _ in
            wager = ""
            if let b = token?.book, let bb = BuildBook(rawValue: b) { book = bb }
            pickTeamGames()
        }
        .onChange(of: games.count) { _, _ in pickTeamGames() }
        // Nov 9: a placed token leaves the wallet here too; it stayed picked, and the next result saved it on a second bet
        .sheet(item: $placing, onDismiss: {
            Task {
                await loadWallet()
                if pick != "typed", !wallet.contains(where: { $0.promoId == pick }) { pick = wallet.first?.promoId ?? "typed" }
            }
        }) { r in
            PromoPlaceSheet(r: r, promo: promo, token: token, book: book, pricer: model.pricer(book),
                            hedge: model.pricer(hedgeBook), bands: model.bands, quoteModel: model.quoteModel)
        }
    }

    /// The wallet's open tokens, at the account's books only (Nov 6); a token for any book stays.
    private func loadWallet() async {
        wallet = Promos.wallet((try? await store.api.rows("promos")) ?? []).open
            .filter { $0.book == nil || BooksOff.mine.contains(Marking.bookOf($0.book)) }
    }

    /// The logos and colors of these games, from ESPN's boards (cached; logos don't change), as Build loads them.
    private func loadArt(_ list: [PackGame]) async {
        let need = list.filter { art[$0.eventId] == nil }.map { g -> Game in
            let parts = g.matchup.components(separatedBy: " @ ")
            return Game(gameId: g.eventId, league: g.sport, home: parts.count == 2 ? parts[1] : nil, away: parts.count == 2 ? parts[0] : nil,
                        matchup: g.matchup, commenceTime: g.commenceTime, state: nil)
        }
        guard !need.isEmpty else { return }
        let found = await Live.art(for: need, ttl: ESPN.doneTTL)
        art.merge(found) { _, new in new }
    }

    // MARK: 1 your token

    @ViewBuilder private var tokenStep: some View {
        if !wallet.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 10) {
                    ForEach(wallet) { p in
                        Button { pick = p.promoId } label: {
                            TokenCard(p: p, compact: true, selected: pick == p.promoId).frame(width: 158)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(Promos.title(p) + (p.book.map { ", \($0)" } ?? ""))
                        .accessibilityAddTraits(pick == p.promoId ? .isSelected : [])
                    }
                    Button { pick = "typed" } label: { typeOneCard }.buttonStyle(.plain)
                        .accessibilityAddTraits(pick == "typed" ? .isSelected : [])
                }
                .padding(.horizontal, 16)
            }
            .padding(.horizontal, -16)
        }
        GlowCard(padding: 16) {
            VStack(alignment: .leading, spacing: 12) {
                if let t = token {
                    FinderField(label: t.kind == "bonus" ? "Bonus dollars to use" : "Dollars to wager",
                                note: t.amountDollars.map { "up to \(Promos.dollars($0))" },
                                placeholder: t.amountDollars.map { String(format: "%g", $0) } ?? "10", text: $wager)
                    if let m = t.amountDollars, (Double(wager) ?? 0) > m {
                        Text("This one's max is \(PromoFinder.money(m)), so the results use that.").font(.caption).foregroundStyle(.secondary)
                    }
                    let chips = TokenCard<EmptyView>.chips(t)
                    if !chips.isEmpty || teams != nil {
                        ChipFlow(spacing: 6) {
                            ForEach(Array(chips.enumerated()), id: \.offset) { _, c in
                                TermChip(text: c.text) { if let lg = c.league { LeagueMark(league: lg, size: 14) } }
                            }
                            ForEach(teams ?? [], id: \.self) { tm in
                                TermChip(text: tm) { TeamFace(name: tm, sport: sports?.first, size: 15) }
                            }
                        }
                    }
                    if let m = t.market {
                        Text("\(Promos.marketName(m)) only: other bets aren't searched.").font(.caption).foregroundStyle(.secondary)
                    }
                    if teams != nil || named != nil {
                        Text(games.isEmpty ? "Only those games count. Their prices come about an hour before each starts." : "Only those games count: they start ticked.")
                            .font(.caption).foregroundStyle(.secondary)
                    } else if sports != nil {
                        Text("Only those sports' games are searched.").font(.caption).foregroundStyle(.secondary)
                    }
                } else {
                    if wallet.isEmpty {
                        Text("Your wallet is empty, so type the promo here.").font(.footnote).foregroundStyle(.secondary)
                    }
                    Picker("Kind", selection: $typedKind) { Text("Bonus bet").tag("bonus"); Text("Profit boost").tag("boost") }.pickerStyle(.segmented)
                    if typedKind == "boost" { FinderField(label: "Boost percent", note: nil, placeholder: "30", text: $typedPct) }
                    FinderField(label: typedKind == "bonus" ? "Bonus dollars" : "Dollars to wager", note: nil, placeholder: "10", text: $typedDollars)
                }
                Hairline()
                HStack(spacing: 10) {
                    Text("Book").font(.subheadline.weight(.semibold))
                    Spacer(minLength: 6)
                    ForEach(BuildBook.mine) { b in
                        Button { book = b } label: {
                            BookIcon(book: b.rawValue, size: 32)
                                .padding(3)
                                .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).strokeBorder(theme.accent, lineWidth: book == b ? 2 : 0))
                                .opacity(book == b ? 1 : 0.5)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(b.rawValue)
                        .accessibilityAddTraits(book == b ? .isSelected : [])
                    }
                }
            }
        }
    }

    private var typeOneCard: some View {
        let on = pick == "typed"
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "pencil").font(.subheadline.weight(.bold)).foregroundStyle(.secondary)
                    .frame(width: 26, height: 26).background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: 7, style: .continuous))
                Spacer(minLength: 0)
                if on { Image(systemName: "checkmark.circle.fill").foregroundStyle(theme.accent) }
            }
            Text("Type one").font(.headline)
            Text("A promo not in your wallet").font(.caption).foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(width: 140, alignment: .leading)
        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
        .overlay { if on { RoundedRectangle(cornerRadius: Kit.radius, style: .continuous).strokeBorder(theme.accent, lineWidth: 1.5) } }
    }

    // MARK: 2 where

    @ViewBuilder private var whereStep: some View {
        HStack(spacing: 8) {
            PickChip(text: "Slice", on: scopeKind == "slice") { scopeKind = "slice" }
            PickChip(text: "Games", on: scopeKind == "games") { scopeKind = "games" }
            PickChip(text: "One game", on: scopeKind == "game") { scopeKind = "game" }
            PickChip(text: "Today", on: scopeKind == "today") { scopeKind = "today" }
        }
        switch scopeKind {
        case "slice":
            // every slice, the one searched marked (Oct 31, Mike: "choose which slice the promo is used on")
            let current: String? = { if case .slice(let k) = scope { return k }; return nil }()
            if slices.isEmpty { quiet("No slices left on the board.") }
            else {
                strip {
                    ForEach(slices) { s in
                        Button { sliceKey = s.key } label: { sliceCard(s, on: current == s.key) }.buttonStyle(.plain)
                            .accessibilityAddTraits(current == s.key ? .isSelected : [])
                    }
                }
            }
        case "game":
            let current: String? = { if case .game(let e) = scope { return e }; return nil }()
            if games.isEmpty { quiet("No games left on the board.") }
            else {
                strip {
                    ForEach(games.prefix(80)) { g in
                        FinderGameCard(g: g, art: art[g.eventId], on: current == g.eventId) { gameKey = g.eventId }
                    }
                }
            }
        case "games":
            if games.isEmpty { quiet("No games left on the board.") }
            else {
                strip {
                    ForEach(games.prefix(80)) { g in
                        FinderGameCard(g: g, art: art[g.eventId], on: picked.contains(g.eventId)) {
                            if picked.contains(g.eventId) { picked.remove(g.eventId) } else { picked.insert(g.eventId) }
                        }
                    }
                }
                Text(events.isEmpty ? "Tap the games to search." : "\(events.count) game\(events.count == 1 ? "" : "s") picked")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        default:
            quiet(events.isEmpty ? "No games left today." : "Every game still to start today: \(events.count) game\(events.count == 1 ? "" : "s"), across sports.")
        }
    }

    private func strip<C: View>(@ViewBuilder _ content: () -> C) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            LazyHStack(alignment: .top, spacing: 10) { content() }.padding(.horizontal, 16)
        }
        .padding(.horizontal, -16)
    }

    private func quiet(_ text: String) -> some View {
        Text(text).font(.footnote).foregroundStyle(.secondary).padding(.vertical, 4)
    }

    private func sliceCard(_ s: Slices.Slice, on: Bool) -> some View {
        // "NFL early · Sun": the sport and slice lead, the day joins the first kickoff below
        let name = s.title.components(separatedBy: " · ").first ?? s.title
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                LeagueMark(league: s.sport, size: 20)
                Spacer(minLength: 0)
                Image(systemName: on ? "checkmark.circle.fill" : "circle").foregroundStyle(on ? AnyShapeStyle(theme.accent) : AnyShapeStyle(.tertiary))
            }
            .frame(height: 22)
            Text(name).font(.subheadline.weight(.bold)).lineLimit(2).multilineTextAlignment(.leading)
            Text("\(s.events.count) game\(s.events.count == 1 ? "" : "s") · \(Fmt.dayTime(s.first))").font(.caption).foregroundStyle(.secondary).lineLimit(1)
        }
        .padding(13)
        .frame(width: 168, alignment: .leading)
        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay { if on { RoundedRectangle(cornerRadius: 20, style: .continuous).strokeBorder(theme.accent, lineWidth: 1.5) } }
    }

    // MARK: 3 rank by

    private var rankStep: some View {
        GlowCard(padding: 16) {
            VStack(alignment: .leading, spacing: 12) {
                Picker("Rank by", selection: $modeRaw) {
                    ForEach(PromoFinder.Mode.allCases) { Text(PromoFinder.label($0)).tag($0.rawValue) }
                }
                .pickerStyle(.segmented)
                Text(PromoFinder.blurb(mode)).font(.footnote).foregroundStyle(.secondary)
                Hairline()
                Toggle(isOn: $showLocks) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Show locks").font(.subheadline.weight(.semibold))
                        Text("The promo at one book, cash on the other side at another: a small sure profit, but the cash side can be large.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                .tint(theme.accent)
            }
        }
    }

    // MARK: the results

    @ViewBuilder private var results: some View {
        let ready = events.filter { model.packs[$0] != nil }.count
        SectionTitle("Best at \(book.rawValue)", note: events.isEmpty ? nil : "\(ready) of \(events.count) games priced")
        if events.isEmpty {
            quiet(scopeKind == "games" ? "Tap the games to search." : "No games left here.")
        } else if ready == 0 {
            HStack(spacing: 8) { ProgressView(); Text("Pricing").font(.footnote).foregroundStyle(.secondary) }.padding(.vertical, 4)
        } else if model.results.isEmpty {
            // a token only for legs no pack prices ("First TD only", Nov 9; web PromoFinder): say so, not "nothing fits"
            if let t = token, let k = t.legKinds, !k.isEmpty, Promos.unpricedKinds(t).count == k.count {
                quiet("We don't price \(k.map(Promos.legKindName).joined(separator: " or ")) legs, so there's nothing to build for this one: bet it at \(book.rawValue) yourself.")
            } else {
                quiet("No bet here meets the token's terms at \(book.rawValue).")
            }
        }
        let perDefault = !((promo.stake ?? 0) > 0)
        ForEach(Array(model.results.enumerated()), id: \.element.id) { i, r in
            FinderCard(n: i + 1, r: r, promo: promo, perDefault: perDefault, pricer: model.pricer(book), hedge: model.pricer(hedgeBook), art: art) { placing = r }
        }
    }
}

/// A step's heading: its number in the accent, then the title as a real heading.
private struct FinderStep: View {
    let n: Int
    let title: String
    @Environment(\.theme) private var theme

    var body: some View {
        HStack(spacing: 9) {
            Text("\(n)").font(.footnote.weight(.heavy)).foregroundStyle(theme.accent)
                .frame(width: 24, height: 24).background(theme.accent.opacity(0.16), in: Circle())
            Text(title).font(.title3.weight(.bold))
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Step \(n): \(title)")
        .accessibilityAddTraits(.isHeader)
    }
}

/// A number to type, in a soft cell at the right of its name.
private struct FinderField: View {
    let label: String
    let note: String?
    let placeholder: String
    @Binding var text: String

    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 1) {
                Text(label).font(.subheadline.weight(.semibold))
                if let note { Text(note).font(.caption).foregroundStyle(.secondary) }
            }
            Spacer(minLength: 6)
            TextField(placeholder, text: $text).keyboardType(.decimalPad).multilineTextAlignment(.trailing)
                .font(.system(.body, design: .monospaced).weight(.semibold))
                .padding(.horizontal, 12).frame(width: 110, height: 40)
                .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
                .accessibilityLabel(label)
        }
    }
}

/// A game to search: both logos, who plays, when; ringed in the accent once picked.
private struct FinderGameCard: View {
    let g: PackGame
    let art: GameLive?
    let on: Bool
    let action: () -> Void
    @Environment(\.theme) private var theme

    var body: some View {
        // soccer reads home team first (Nov 5): its parts and logos in that order
        let soc = Fmt.isSoccer(g.sport), art = art?.reading
        let stored = g.matchup.components(separatedBy: " @ ")
        let parts = soc && stored.count == 2 ? Array(stored.reversed()) : stored
        let sep = soc ? "vs" : "@"
        let ufc = g.sport == "ufc"
        let short = art.flatMap { a in !a.away.abbr.isEmpty && !a.home.abbr.isEmpty ? "\(a.away.abbr) \(sep) \(a.home.abbr)" : nil }
        Button(action: action) {
            VStack(alignment: .leading, spacing: 7) {
                HStack(spacing: 6) {
                    TeamLogo(url: art?.away.logo, name: parts[0], size: 30, round: ufc)
                    if parts.count > 1 { TeamLogo(url: art?.home.logo, name: parts[1], size: 30, round: ufc) }
                    Spacer(minLength: 0)
                    Image(systemName: on ? "checkmark.circle.fill" : "circle").foregroundStyle(on ? AnyShapeStyle(theme.accent) : AnyShapeStyle(.tertiary))
                }
                Text(short ?? Fmt.matchup(g.matchup, sport: g.sport)).font(.footnote.weight(.bold)).lineLimit(short == nil ? 2 : 1).multilineTextAlignment(.leading)
                Text(Fmt.dayTime(g.commenceTime)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            .padding(12)
            .frame(width: 140, alignment: .leading)
            .background(theme.cardColor, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay { if on { RoundedRectangle(cornerRadius: 20, style: .continuous).strokeBorder(theme.accent, lineWidth: 1.5) } }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(g.matchup)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// A leg's picture: the player's photo, the team's logo, or both teams' logos for a leg on the game itself.
private struct FinderLegArt: View {
    let leg: PackLeg?
    let pack: Pack?
    let art: GameLive?
    var size: CGFloat = 34

    var body: some View {
        if let who = leg?.player, !who.isEmpty {
            PlayerFace(name: who, sport: pack?.sport ?? "", size: size)
        } else if let team = leg?.team, !team.isEmpty {
            TeamLogo(url: BuildArt.logo(team, art, matchup: pack?.matchup ?? ""), name: team, size: size, round: pack?.sport == "ufc")
        } else if let a = art, a.away.logo != nil || a.home.logo != nil {
            ZStack {
                TeamLogo(url: a.away.logo, name: a.away.name, size: size * 0.62).offset(x: -size * 0.19, y: -size * 0.19)
                TeamLogo(url: a.home.logo, name: a.home.name, size: size * 0.62).offset(x: size * 0.19, y: size * 0.19)
            }
            .frame(width: size, height: size)
        } else {
            Monogram(name: pack?.matchup.replacingOccurrences(of: " @ ", with: " ") ?? "?", size: size)
        }
    }
}

/// One result, built like the pick card: what it is and its price, three numbers, and Place. A lock is two bets, so
/// it shows them as two cells joined by a link.
private struct FinderCard: View {
    let n: Int
    let r: PromoFinder.Result
    let promo: Promo
    let perDefault: Bool
    let pricer: Pricer
    let hedge: Pricer
    let art: [String: GameLive]
    let place: () -> Void
    @Environment(\.theme) private var theme

    private var kind: String {
        switch r.kind { case .single: "Single"; case .parlay: "Parlay"; case .sgp: "Same-game parlay"; case .lock: "Lock" }
    }
    private var price: String { Fmt.am(r.lock?.promoPrice ?? Odds.am(r.dec)) }
    /// One game's result glows in its teams' colors; a parlay across games stays plain.
    private var game: GameLive? {
        let ids = Set(r.legs.map(\.eventId))
        return ids.count == 1 ? art[ids.first!] : nil
    }

    var body: some View {
        GlowCard(left: Color(hex: game?.away.color), right: Color(hex: game?.home.color)) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("\(n)").font(.caption.weight(.heavy)).foregroundStyle(.secondary)
                        .frame(minWidth: 22, minHeight: 22).background(Color.primary.opacity(0.08), in: Circle())
                    Text(kind.uppercased()).font(.caption2.weight(.bold)).foregroundStyle(r.kind == .lock ? Color.green : Color.secondary)
                    Spacer(minLength: 6)
                    if r.kind != .lock {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text(price).font(.system(.title2, design: .monospaced).weight(.bold)).foregroundStyle(.tint)
                            if r.kind == .sgp { Text("LIKELY").font(.caption2.weight(.semibold)).foregroundStyle(.tertiary) }
                        }
                    }
                }
                if let k = r.lock { lockPair(k) } else { legs }
                HStack(spacing: 14) {
                    if r.lock != nil {
                        StatCell(name: perDefault ? "SURE PROFIT PER $10" : "SURE PROFIT", value: PromoFinder.money(r.value), color: r.value > 0 ? .green : .red)
                        Divider()
                        StatCell(name: "CASH SIDE", value: PromoFinder.money(PromoFinder.tokenDollars(promo) * (r.lock?.hedge ?? 0)))
                        Divider()
                        StatCell(name: "WINS", value: "Either way")
                    } else {
                        StatCell(name: perDefault ? "EXPECTED PER $10" : "EXPECTED", value: PromoFinder.money(r.value), color: r.value > 0 ? .green : .red)
                        Divider()
                        StatCell(name: "CHANCE", value: "\(Int((r.p * 100).rounded()))%")
                        Divider()
                        if r.legs.count == 1 { StatCell(name: "BOOK", value: pricer.book.rawValue) }
                        else { StatCell(name: "LEGS", value: r.games > 1 ? "\(r.legs.count) · \(r.games) games" : "\(r.legs.count)") }
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                if let note { Text(note).font(.caption).foregroundStyle(.secondary) }
                HStack(spacing: 10) {
                    Button(action: place) { Text(r.kind == .lock ? "Place both" : "Place").frame(maxWidth: .infinity) }
                        .buttonStyle(SolidButton())
                    // open the bet at its book, and a lock's cash side at the other (Nov 8, Mike: "give me the link"; web BookLink)
                    if let k = r.lock {
                        BookButton(book: pricer.book.rawValue, link: Build.link(book: pricer.book, [k.promoLink]), size: 44)
                        BookButton(book: hedge.book.rawValue, link: Build.link(book: hedge.book, [k.hedgeLink]), size: 44)
                    } else {
                        BookButton(book: pricer.book.rawValue, link: Build.link(book: pricer.book, r.legs.map { pricer.leg($0.eventId, $0.label)?.link }), size: 44)
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
    }

    /// What the numbers don't already say: a boost's own share, a same-game slip's cautious price, how a lock works.
    private var note: String? {
        if r.kind == .lock { return "The promo goes on the first bet and cash on the second, at two books." }
        var parts: [String] = []
        if promo.kind == .boost { parts.append("The boost adds \(PromoFinder.money(r.boostAdds)).") }
        if r.kind == .sgp { parts.append("The price is the likely quote; ranked at \(Fmt.am(Odds.am(r.at))) in case it comes in lower.") }
        if r.kind != .lock, let m = Build.mainLineText(r.legs.map { l in pricer.leg(l.eventId, l.label).map { $0.link != nil && $0.linkMain == true } ?? false },
                                                       book: pricer.book.rawValue) { parts.append(m) }
        return parts.isEmpty ? nil : parts.joined(separator: " ")
    }

    private var legs: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(r.legs, id: \.self) { l in
                let pk = pricer.pack(l.eventId)
                HStack(spacing: 11) {
                    FinderLegArt(leg: pk?.legs[l.label], pack: pk, art: art[l.eventId], size: r.legs.count == 1 ? 44 : 34)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(Fmt.label(l.label)).font(r.legs.count == 1 ? .title3.weight(.heavy) : .subheadline.weight(.bold)).lineLimit(2)
                        Text(Fmt.matchup(pk?.matchup, sport: pk?.sport)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
            }
        }
    }

    private func lockPair(_ k: LockPick) -> some View {
        let pk = pricer.pack(k.eventId)
        return VStack(alignment: .leading, spacing: 4) {
            if let m = pk?.matchup, !m.isEmpty { Text(m).font(.caption).foregroundStyle(.secondary).padding(.bottom, 2) }
            lockSide(book: pricer.book.rawValue, leg: k.promoLeg, how: promo.kind == .bonus ? "your bonus bet" : "your boosted bet",
                     price: k.promoPrice, art: FinderLegArt(leg: pk?.legs[k.promoLeg], pack: pk, art: art[k.eventId], size: 30))
            lockSide(book: hedge.book.rawValue, leg: k.hedgeLeg, how: "cash", price: k.hedgePrice,
                     art: FinderLegArt(leg: hedge.pack(k.eventId)?.legs[k.hedgeLeg], pack: pk, art: art[k.eventId], size: 30))
        }
        .overlay(alignment: .leading) {
            // the link between the two bets, sitting on the seam
            Image(systemName: "link").font(.system(size: 11, weight: .heavy)).foregroundStyle(.green)
                .frame(width: 26, height: 26).background(theme.cardColor, in: Circle())
                .offset(x: 13, y: pk?.matchup.isEmpty == false ? 11 : 0)
                .accessibilityHidden(true)
        }
    }

    private func lockSide<A: View>(book: String, leg: String, how: String, price: Double, art: A) -> some View {
        HStack(spacing: 10) {
            BookIcon(book: book, size: 30)
            art
            VStack(alignment: .leading, spacing: 1) {
                Text(Fmt.label(leg)).font(.subheadline.weight(.bold)).lineLimit(2)
                Text("\(how) at \(book)").font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 6)
            Text(Fmt.am(price)).font(.system(.callout, design: .monospaced).weight(.bold)).foregroundStyle(.tint)
        }
        .padding(11)
        .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
    }
}

/// Place: the price and dollars taken (and a lock's hedge), saved at the token's dollars over the account's unit.
struct PromoPlaceSheet: View {
    @EnvironmentObject private var store: BetStore
    @Environment(\.dismiss) private var dismiss
    let r: PromoFinder.Result
    let promo: Promo
    let token: PromoRow?
    let book: BuildBook
    let pricer: Pricer
    let hedge: Pricer
    let bands: [Band]
    let quoteModel: QuoteModel?
    @State private var price = ""
    @State private var dollars = ""
    @State private var hedgePrice = ""
    @State private var hedgeDollars = ""
    @State private var err: String?
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form { Group {
                Section {
                    side(book.rawValue, r.legs.map { Fmt.label($0.label) }.joined(separator: " + "))
                    LabeledContent("\(book.rawValue) price") { TextField("+150", text: $price).keyboardType(.numbersAndPunctuation).multilineTextAlignment(.trailing) }
                    LabeledContent(promo.kind == .bonus ? "Bonus $" : "Stake $") { TextField("10", text: $dollars).keyboardType(.decimalPad).multilineTextAlignment(.trailing) }
                } header: { Text(r.lock != nil ? "The promo's side" : "The bet") }
                if let k = r.lock {
                    Section {
                        side(hedge.book.rawValue, Fmt.label(k.hedgeLeg))
                        LabeledContent("Price") { TextField("-150", text: $hedgePrice).keyboardType(.numbersAndPunctuation).multilineTextAlignment(.trailing) }
                        LabeledContent("Cash $") { TextField("9", text: $hedgeDollars).keyboardType(.decimalPad).multilineTextAlignment(.trailing) }
                    } header: { Text("The cash side") }
                }
                Section {
                    let u = store.unit
                    Text("Saved as \(String(format: "%.2f", (Double(dollars) ?? 0) / u))u at \(PromoFinder.money(u)) a unit" + (token.map { "; uses your \(Promos.title($0))" } ?? "") + ".")
                        .font(.footnote).foregroundStyle(.secondary)
                    if let t = token, let face = t.amountDollars, let d = Double(dollars), d > 0, d < face {
                        Text(t.kind == "bonus" ? "The other \(PromoFinder.money(Promos.bonusLeft(face, d))) stays in your wallet as its own bonus bet."
                             : "A boost is used once, so the rest of its max wager doesn't carry over.").font(.footnote).foregroundStyle(.secondary)
                    }
                    if let err { Text(err).foregroundStyle(.red) }
                }
            }.themedRows() }
            .themedList()
            .onChange(of: dollars) { _, v in
                if let k = r.lock, let d = Double(v), d > 0 { hedgeDollars = String(format: "%.2f", d * k.hedge) }
            }
            .navigationTitle(r.lock != nil ? "Placed both?" : "Placed it?")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button(busy ? "Saving…" : "Save") { Task { await save() } }.disabled(busy) }
            }
            .onAppear {
                let S = PromoFinder.tokenDollars(promo)
                price = Fmt.am(r.lock?.promoPrice ?? Odds.am(r.dec)).replacingOccurrences(of: Fmt.minus, with: "-")
                dollars = String(format: "%g", S)
                if let k = r.lock {
                    hedgePrice = Fmt.am(k.hedgePrice).replacingOccurrences(of: Fmt.minus, with: "-")
                    hedgeDollars = String(format: "%.2f", S * k.hedge)
                }
            }
        }
    }

    /// Which bet this is: the book's picture and what was bet.
    private func side(_ book: String, _ what: String) -> some View {
        HStack(spacing: 10) {
            BookIcon(book: book, size: 30)
            Text(what).font(.subheadline.weight(.semibold))
        }
        .padding(.vertical, 2)
    }

    private func save() async {
        guard let p = Marking.parseOdds(price), let d = Double(dollars), d > 0,
              let e = Build.evaluate(pricer, r.legs, priceText: price, bands: bands, model: quoteModel) else { err = "Enter the book's odds and the dollars."; return }
        if let t = token, let m = t.amountDollars, d > m + 0.004 {
            err = "This \(t.kind == "bonus" ? "bonus bet" : "boost's max wager") is \(PromoFinder.money(m))."; return
        }
        let lockId = r.lock != nil ? UUID().uuidString.lowercased() : nil
        let u = store.unit, real = store.isReal
        var customs = [Build.row(pricer, r.legs, e)]
        customs[0]["price"] = p
        var bets = [PromoFinder.betRow(custom: customs[0], price: p, book: book.rawValue, dollars: d, unit: u, real: real, lockId: lockId, extra: [
            "bonus": promo.kind == .bonus, "boost": promo.kind == .boost ? promo.pct : nil,
            "boost_cap": promo.kind == .boost ? promo.maxExtra.map { ($0 / u * 1000).rounded() / 1000 } : nil,
            "promo_id": token?.promoId, "promo_ev": (r.value * d / PromoFinder.tokenDollars(promo) * 100).rounded() / 100])]
        if let k = r.lock {
            let hl = [SlipLeg(eventId: k.eventId, label: k.hedgeLeg)]
            guard let hp = Marking.parseOdds(hedgePrice), let hd = Double(hedgeDollars), hd > 0,
                  let he = Build.evaluate(hedge, hl, priceText: hedgePrice, bands: bands, model: quoteModel) else { err = "Enter the hedge's odds and dollars."; return }
            var hc = Build.row(hedge, hl, he); hc["price"] = hp
            customs.append(hc)
            bets.append(PromoFinder.betRow(custom: hc, price: hp, book: hedge.book.rawValue, dollars: hd, unit: u, real: real, lockId: lockId))
        }
        busy = true
        defer { busy = false }
        if let e = await store.placePromo(customs: customs, bets: bets, token: token?.promoId, dollars: d) { err = e } else { dismiss() }
    }
}
