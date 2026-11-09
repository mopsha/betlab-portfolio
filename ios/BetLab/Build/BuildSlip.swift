import SwiftUI

/// The slip, floating above the tab bar in the accent: its legs' pictures, how many legs and the grade, where the best
/// price is, and that price. A tap opens the sheet.
struct SlipBar: View {
    @ObservedObject var model: BuildModel
    let art: [String: GameLive]
    @ObservedObject private var faces = Faces.shared
    @Environment(\.theme) private var theme
    @Environment(\.colorScheme) private var scheme

    /// A picture per leg where one is known: the player's photo (found by the board's rows), the team's logo.
    private var pictures: [String] {
        model.slip.legs.compactMap { l in
            guard let pk = model.packs[l.eventId], let leg = pk.legs[l.label] else { return nil }
            if let who = leg.player, !who.isEmpty { return faces.urls[who] }
            return BuildArt.logo(leg.team, art[l.eventId], matchup: pk.matchup)
        }
    }

    var body: some View {
        let sides = model.sides
        let at = model.target(sides)
        let e = at.eval
        let n = model.slip.legs.count
        let ink = theme.onAccent(scheme)
        let urls = pictures
        let where_ = SlipWords.where_(model, sides, at)
        Button { model.slipOpen = true } label: {
            HStack(spacing: 12) {
                if urls.isEmpty {
                    Text("\(n)").font(.subheadline.bold()).frame(minWidth: 28, minHeight: 28).background(ink.opacity(0.16), in: Circle())
                } else {
                    ArtStack(urls: urls, size: 30)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text("\(n) leg\(n == 1 ? "" : "s")" + (e.map { " · grade \($0.grade)" } ?? "")).font(.subheadline.weight(.bold))
                    Text(e == nil ? (model.ready ? "Can't price these together" : "Pricing…") : where_).font(.caption).lineLimit(1)
                }
                Spacer(minLength: 4)
                if e != nil, let p = at.exact { Text(Fmt.am(p)).font(.system(size: 22, weight: .bold, design: .monospaced)) }
                else { Image(systemName: "chevron.up").font(.subheadline.weight(.bold)) }
            }
            .foregroundStyle(ink)
            .padding(.horizontal, 16).frame(height: 60)
            .background(theme.accent, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .contentShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 16).padding(.bottom, 6)
        .shadow(color: .black.opacity(0.3), radius: 14, y: 6)
        .accessibilityLabel("Your slip: \(n) leg\(n == 1 ? "" : "s")\(e.map { ", grade \($0.grade), fair \(Fmt.am($0.fair))" } ?? ""), \(where_). Open it")
    }
}

/// The slip's words, shared by the bar and the sheet.
@MainActor
enum SlipWords {
    /// "best price at Novig", "at FanDuel with your promo", or the chance and fair price until a book has an exact price.
    static func where_(_ model: BuildModel, _ sides: [SlipSide], _ at: SlipSide) -> String {
        guard let e = at.eval else { return "" }
        if model.promo.kind != .none, model.promoBook == at.book { return "at \(at.book.rawValue) with your promo" }
        if at.exact != nil { return "best price at \(at.book.rawValue)" }
        return "\(Fmt.pct(e.p)) to hit · fair \(Fmt.am(e.fair))"
    }

    /// The promo's value on the slip at a book's price (per dollar), and whether the slip is inside the token's terms.
    static func promo(_ model: BuildModel, _ at: SlipSide) -> (ev: Double, dec: Double, fits: Bool)? {
        guard model.promo.kind != .none, let e = at.eval else { return nil }
        let dec = at.price.map(Odds.dec) ?? e.naive
        return (Build.promoEv(e.p, dec, model.promo), dec, Build.promoFits(model.promo, legs: model.slip.legs.count, dec: dec))
    }

    /// Whether a wallet token can go on this slip: its sport and teams, a book that posts every leg, and its terms.
    static func fits(_ p: PromoRow, _ model: BuildModel, _ sides: [SlipSide]) -> Bool {
        guard Promos.state(p) == "open" else { return false }
        if let s = Promos.sports(p), !s.contains(where: { model.sport == $0 || model.sport.hasPrefix($0) }) { return false }
        let games = Set(model.slip.legs.map(\.eventId)).compactMap { model.packs[$0]?.matchup }
        if !games.allSatisfy({ Promos.teamFits(p.teams, $0) }) { return false }
        let at = p.book.map { b in sides.filter { $0.book.rawValue.lowercased() == b.lowercased() } } ?? sides
        let promo = Promos.asPromo(p)
        return at.contains { s in
            guard let e = s.eval else { return false }
            return Build.promoFits(promo, legs: model.slip.legs.count, dec: s.price.map(Odds.dec) ?? e.naive)
        }
    }

    /// The book a wallet token is from, when it is one of ours.
    static func book(_ p: PromoRow) -> BuildBook? {
        p.book.flatMap { b in BuildBook.allCases.first { $0.rawValue.lowercased() == b.lowercased() } }
    }
}

/// The open slip (Nov 5): its legs with their pictures, the grade as a badge, chance / fair price / edge, the price at
/// each book with the best one marked (type FanDuel's or DraftKings'; Novig's is asked for), the promo as one row, and
/// I placed this at the best book, Open and Save. Why the grade is folded below.
struct SlipSheet: View {
    @ObservedObject var model: BuildModel
    let art: [String: GameLive]
    @EnvironmentObject private var store: BetStore
    @Environment(\.theme) private var theme
    @Environment(\.openURL) private var openURL
    @State private var busy = false
    @State private var msg: String?
    @State private var wallet: [PromoRow] = []
    // one sheet for both (two .sheet modifiers on one view present only one)
    private enum Sub: Identifiable {
        case promo, place(MarkInput)
        var id: String { if case .place = self { return "place" } else { return "promo" } }
    }
    @State private var sub: Sub?

    var body: some View {
        let sides = model.sides
        let at = model.target(sides)
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                head(at)
                legs(at)
                if let e = at.eval { cells(e, at, sides) }
                books(sides, at)
                notes(sides, at)
                if at.eval != nil { promoRow(sides, at) }
                if let e = at.eval { why(e, at) }
            }
            .padding(.horizontal, 20).padding(.top, 22).padding(.bottom, 12)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(theme.pageColor.ignoresSafeArea())
        .safeAreaInset(edge: .bottom) { if let e = at.eval { actions(e, at) } }
        .task { wallet = (try? await store.api.rows("promos", .init(order: ("created_at", ascending: false)))) ?? [] }
        .sheet(item: $sub) { which in
            switch which {
            case .promo:
                SlipPromoSheet(model: model, wallet: Promos.wallet(wallet).open, fits: { SlipWords.fits($0, model, model.sides) })
            case .place(let input):
                // the wallet token on the slip goes with it (Nov 9); placed, the promo is cleared so the next slip isn't
                // saved as a bonus or boosted bet by mistake
                PlaceBetSheet(input: input, token: model.promo.kind != .none ? model.promoToken : nil) {
                    model.promoToken = nil; model.promo = .none
                    Task { wallet = (try? await store.api.rows("promos", .init(order: ("created_at", ascending: false)))) ?? wallet }
                }
                .environmentObject(store)
            }
        }
    }

    // MARK: the head and the legs

    private func head(_ at: SlipSide) -> some View {
        let n = model.slip.legs.count
        let one = model.slip.legs.first.flatMap { model.packs[$0.eventId]?.matchup } ?? "one game"
        return HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Your slip").font(.title2.weight(.heavy))
                Text("\(n) leg\(n == 1 ? "" : "s") · " + (model.nGames > 1 ? "SGP+ · \(model.nGames) games" : one))
                    .font(.footnote).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 8)
            if let e = at.eval { GradeBadge(grade: e.grade, idx: e.idx) }
            Button { model.slipOpen = false } label: { IconDisc(systemName: "xmark", onCard: true) }
                .buttonStyle(.plain).accessibilityLabel("Close")
        }
    }

    /// Each leg: its picture, what it is, its chance, its price at the slip's book, and remove.
    private func legs(_ at: SlipSide) -> some View {
        let pr = model.pricers[at.book]!
        return VStack(spacing: 0) {
            ForEach(Array(model.slip.legs.enumerated()), id: \.element) { i, l in
                let pk = model.packs[l.eventId]
                let x = pr.leg(l.eventId, l.label)
                if i > 0 { Hairline() }
                HStack(spacing: 12) {
                    LegArt(leg: pk?.legs[l.label], sport: pk?.sport ?? model.sport, matchup: pk?.matchup ?? "", art: art[l.eventId])
                    VStack(alignment: .leading, spacing: 1) {
                        Text(Fmt.label(l.label)).font(.body.weight(.semibold)).lineLimit(2)
                        Text((x.map { "\(Fmt.pct($0.p)) chance" } ?? "…") + (model.nGames > 1 ? " · " + (pk?.matchup ?? "") : ""))
                            .font(.footnote).foregroundStyle(.secondary).lineLimit(1)
                    }
                    Spacer(minLength: 6)
                    Text(x == nil ? "…" : x!.unavailable ? "not at \(at.book.rawValue)" : Fmt.am(x!.price))
                        .font(x?.unavailable == true ? .caption : .system(.callout, design: .monospaced).weight(.bold))
                        .foregroundStyle(x?.unavailable == true ? .red : .primary)
                    Button { model.toggle(l.eventId, l.label) } label: {
                        Image(systemName: "xmark").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
                            .frame(width: 32, height: 44).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain).accessibilityLabel("Remove \(l.label)")
                }
                .padding(.vertical, 6)
            }
            HStack {
                Spacer()
                Button("Clear the slip", role: .destructive) { model.clear() }
                    .font(.footnote.weight(.semibold)).frame(minHeight: 44)
            }
        }
    }

    // MARK: the numbers and the books

    /// Chance, fair price, and the edge at the slip's book.
    private func cells(_ e: Evaluation, _ at: SlipSide, _ sides: [SlipSide]) -> some View {
        let edge = at.price.map { e.p * Odds.dec($0) - 1 }
        let pinned = model.promo.kind != .none && model.promoBook == at.book
        let name = at.exact == nil && at.likely != nil ? "EDGE, LIKELY" : pinned ? "EDGE AT \(at.book.rawValue.uppercased())" : "EDGE AT BEST"
        return CellRow(cells: [.init(name: "CHANCE", value: Fmt.pct(e.p, 1)),
                               .init(name: "FAIR PRICE", value: Fmt.am(e.fair)),
                               .init(name: name, value: edge.map { Fmt.signed($0) } ?? "—",
                                     color: edge.map { $0 >= 0 ? Color.green : .red } ?? .secondary)])
    }

    private func books(_ sides: [SlipSide], _ at: SlipSide) -> some View {
        let best = model.best(sides)?.book
        return VStack(alignment: .leading, spacing: 8) {
            Text("THE PRICE AT EACH BOOK").font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
            HStack(alignment: .top, spacing: 8) {
                ForEach(sides) { s in BookPrice(model: model, side: s, best: s.book == best) }
            }
        }
    }

    /// What the grade says, Novig when it won't price the legs, and legs a book doesn't post.
    @ViewBuilder private func notes(_ sides: [SlipSide], _ at: SlipSide) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let e = at.eval {
                Text(e.why)
            } else if !model.ready {
                Text("Pricing…")
            } else if sides.allSatisfy({ $0.missing.isEmpty }) {
                Text("Can't price these legs together.")
            }
            if model.novigIds != nil, let now = model.novigNow, now.quote == nil {
                Text("No Novig market maker priced these legs together just now. Some same-game pairs aren't allowed (two of one line, a stat inside another on one player); try again or swap a leg.")
            }
            ForEach(sides.filter { !$0.missing.isEmpty }) { s in
                let m = s.missing
                Text("\(s.book.rawValue) doesn't \(s.book == .novig ? "list" : "post") \(m.count == 1 ? "this leg" : "these legs")\(s.book == .draftkings ? " at this number" : ""): \(m.map(Fmt.label).joined(separator: ", ")).")
            }
        }
        .font(.footnote).foregroundStyle(.secondary)
    }

    // MARK: the promo

    /// Add a promo: one row. With one on, what the slip is worth with it.
    private func promoRow(_ sides: [SlipSide], _ at: SlipSide) -> some View {
        let open = Promos.wallet(wallet).open
        let fit = open.first { SlipWords.fits($0, model, sides) }
        let v = SlipWords.promo(model, at)
        return Button { sub = .promo } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    if let v {
                        let name = model.promo.name
                        Text(name.prefix(1).uppercased() + name.dropFirst()).font(.body.weight(.semibold))
                        (Text(model.promo.text(v.ev)).bold().foregroundColor(model.promo.good(v.ev) ? .green : .red)
                         + Text(" at \(Fmt.am(Odds.am(v.dec)))" + (at.exact == nil ? (at.likely != nil ? ", the likely price" : ", the legs' product") : ""))
                         + Text(v.fits ? "" : " · outside the token's terms").foregroundColor(.red))
                            .font(.footnote).foregroundStyle(.secondary)
                    } else {
                        Text("Add a promo").font(.body.weight(.semibold))
                        Text(open.isEmpty ? "A bonus bet or a profit boost: see what this slip is worth with it"
                             : "\(open.count) waiting" + (fit.map { " · your \(Promos.title($0)) fits this slip" } ?? " · none fits this slip as it is"))
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
                .multilineTextAlignment(.leading)
                Spacer(minLength: 6)
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 14).padding(.vertical, 12)
            .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
            .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
            .contentShape(RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    // MARK: why this grade

    private func why(_ e: Evaluation, _ at: SlipSide) -> some View {
        let book = at.book
        return DisclosureGroup("Why this grade") {
            VStack(alignment: .leading, spacing: 8) {
                Text("Legs alone \(Fmt.am(Odds.am(e.naive))) · together \(String(format: "%.2f×", e.lift)) as likely as apart")
                    .font(.caption.monospacedDigit())
                let items = e.notes + e.rules.map { "Your rule: " + $0 }
                ForEach(items.isEmpty ? ["No leg flagged, and your rules all hold."] : items, id: \.self) { Text("• " + $0).font(.caption) }
                ForEach(e.legs.indices, id: \.self) { i in
                    let s = e.legs[i].slip, l = e.legs[i].leg
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(Fmt.label(s.label)).font(.footnote)
                            Text("fair \(Fmt.pct(l.p)) (\(Fmt.am(Odds.am(1 / l.p)))) · \(book.rawValue) pays \(Int((l.p * Odds.dec(l.price) * 100).rounded()))% of fair\(l.source.map { " · " + $0 } ?? "")")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text(Fmt.am(l.price)).font(.footnote.monospacedDigit())
                    }
                }
                Text("The grade compares \(book == .draftkings ? "DraftKings'" : book == .novig ? "Novig's exact" : "FanDuel's") price with what \(model.quoteModel != nil ? "FanDuel usually pays a slip like this\(book == .draftkings ? " (FanDuel's pattern stands in until about 40 DraftKings quotes are typed)" : "")" : "parlays this size usually pay") (\(Int((e.typical * 100).rounded()))% of fair), then checks each leg's price, whether the legs help each other, and your rules.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 6)
        }
        .font(.subheadline)
        .tint(.secondary)
    }

    // MARK: I placed this, Open, Save

    /// The slip's id at a book: an open bet's id while it's open, else one with the slip's game day (Build.slipId, Nov 9).
    private func slipId(_ book: BuildBook) -> String {
        let legs = model.slip.legs, open = store.openMarks
        guard let pr = model.pricers[book] else { return Build.id(legs, book: book) }
        return Build.slipId(pr, legs, open: { open[$0] != nil })
    }

    private func input(_ e: Evaluation, _ book: BuildBook, price: Double?) -> MarkInput {
        let pr = model.pricers[book]!, legs = model.slip.legs
        return MarkInput(kind: "custom", sgpId: slipId(book), price: price,
                         matchup: Build.row(pr, legs, e)["matchup"] as? String,
                         book: book.rawValue, fairPrice: e.fair.rounded(), pFair: e.p,
                         legs: legs.map(\.label), oddsEventId: model.nGames == 1 ? legs[0].eventId : nil,
                         boost: model.promo.kind == .boost ? model.promo.pct : nil, bonus: model.promo.kind == .bonus,
                         games: e.games.compactMap { eid in pr.pack(eid).map { pk in
                             MarkInput.Game(matchup: pk.matchup, gameRef: pk.gameRef, legs: legs.filter { $0.eventId == eid }.map(\.label)) } })
    }

    /// Pinned under the slip: the main button goes to the slip's book (the best price, or the promo's book).
    private func actions(_ e: Evaluation, _ at: SlipSide) -> some View {
        let pr = model.pricers[at.book]!, legs = model.slip.legs
        let id = slipId(at.book)
        let mine = store.customs.first { $0.sgpId == id }
        // a slip already marked and still open, at whichever book it went to (a settled bet on the same legs is another slip)
        let openBets = store.openMarks
        let marked = BuildBook.allCases.first { openBets[slipId($0)] != nil }
        let link = Build.link(book: at.book, legs.map { pr.leg($0.eventId, $0.label)?.link })
        let main = at.book == .novig ? nil : Build.mainLineText(legs.map {
            let x = pr.leg($0.eventId, $0.label); return x?.link != nil && x?.linkMain == true }, book: at.book.rawValue)
        return VStack(alignment: .leading, spacing: 8) {
            if let main, link != nil { Text(main).font(.caption2).foregroundStyle(.secondary) }
            if let msg { Text(msg).font(.footnote).foregroundStyle(.red) }
            if let marked, let me = model.side(marked).eval {
                MarkControl(input: input(me, marked, price: model.side(marked).exact))
            }
            HStack(spacing: 8) {
                if marked == nil {
                    Button(store.isReal ? "I placed this at \(at.book.rawValue)" : "Mark as mine") { place(e, at) }
                        .buttonStyle(KitButton(height: 50)).disabled(busy)
                }
                if let link {
                    Button("Open") { open(at.book, link) }
                        .buttonStyle(KitButton(kind: .quiet, wide: marked != nil, height: 50))
                        .accessibilityLabel("Open in \(at.book.rawValue)")
                }
                Button(busy ? "Saving…" : mine == nil ? "Save" : (mine?.grade == e.grade && mine?.price == e.typed ? "Saved" : "Update")) { save(e, at) }
                    .buttonStyle(KitButton(kind: .quiet, wide: marked != nil, height: 50)).disabled(busy)
                    .accessibilityLabel(mine == nil ? "Save and track this parlay" : "Update the saved parlay")
            }
        }
        .padding(.horizontal, 20).padding(.top, 10).padding(.bottom, 8)
        .background(theme.pageColor)
    }

    /// The rows a save writes: the slip at its book, and at any other book a price was typed for (each typed price
    /// teaches that book's quote model, as when it was saved from that book's side).
    private func rows(_ at: SlipSide) -> [[String: Any?]] {
        let legs = model.slip.legs
        return model.sides.compactMap { s in
            guard let e = s.eval, s.book == at.book || !model.typed(s.book).isEmpty else { return nil }
            return Build.row(model.pricers[s.book]!, legs, e, id: slipId(s.book))
        }
    }

    private func save(_ e: Evaluation, _ at: SlipSide) {
        busy = true
        Task {
            do {
                for row in rows(at) { try await store.api.upsert("custom_parlays", row, onConflict: "user_id,sgp_id") }
                await store.load()
                msg = nil
            } catch { msg = (error as? AuthError)?.message ?? "Couldn't save that." }
            busy = false
        }
    }

    /// I placed this: the slip is saved first (a bet points at its saved parlay), then the usual sheet asks the units,
    /// the price the book gave and the book; before real money it is marked as yours at once.
    private func place(_ e: Evaluation, _ at: SlipSide) {
        let mark = input(e, at.book, price: at.exact)
        busy = true
        Task {
            do {
                for row in rows(at) { try await store.api.upsert("custom_parlays", row, onConflict: "user_id,sgp_id") }
                await store.load()
                msg = nil
                if store.isReal { sub = .place(mark) } else { msg = await store.mark(mark) }
            } catch { msg = (error as? AuthError)?.message ?? "Couldn't save that." }
            busy = false
        }
    }

    /// FanDuel's and Novig's apps through their own schemes, the web link when the app isn't there (as BookButton).
    private func open(_ book: BuildBook, _ link: String) {
        if book == .fanduel, let l = FanDuel.links(link) {
            openURL(l.app) { ok in if !ok { openURL(l.web) } }
        } else if book == .novig, let l = Novig.links(link) {
            openURL(l.app) { ok in if !ok { openURL(l.web) } }
        } else if let u = URL(string: link) {
            openURL(u)
        }
    }
}

/// The slip's price at one book: type FanDuel's or DraftKings' same-game price (the likely one shows until you do);
/// a plain parlay's is its legs' product, exact; Novig's is its own quote. The best exact price is ringed in green.
private struct BookPrice: View {
    @ObservedObject var model: BuildModel
    let side: SlipSide
    let best: Bool

    private var note: String {
        if side.eval == nil {
            let n = side.missing.count
            return n > 0 ? "\(n) leg\(n == 1 ? "" : "s") not here" : "no price"
        }
        if !model.typed(side.book).isEmpty { return "typed" }
        if side.book == .novig {
            if side.exact != nil { return "exact" }
            if model.novigIds == nil { return "no price" }
            return model.novigNow == nil ? "asking…" : "no price now"
        }
        return side.exact != nil ? "exact" : "likely · type it"
    }

    var body: some View {
        let shown = side.eval == nil ? nil : side.price
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                BookIcon(book: side.book.rawValue, size: 20)
                Text(side.book.rawValue).font(.caption).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.7)
            }
            TextField("", text: Binding(get: { model.typed(side.book) }, set: { model.setPrice($0, book: side.book) }),
                      prompt: Text(shown.map { Fmt.am($0) } ?? "—").foregroundColor(side.exact != nil && side.eval != nil ? (best ? .green : .primary) : .secondary))
                .keyboardType(.numbersAndPunctuation).submitLabel(.done).autocorrectionDisabled()
                .font(.system(size: 18, weight: .bold, design: .monospaced))
                .foregroundStyle(best ? Color.green : .primary)
                .frame(minHeight: 28)
                .disabled(side.eval == nil)
                .accessibilityLabel("\(side.book.rawValue) price")
                .accessibilityValue(shown.map { Fmt.am($0) } ?? "none")
            Text(best ? "best · " + note : note).font(.caption2).foregroundStyle(best ? Color.green : .secondary).lineLimit(1).minimumScaleFactor(0.7)
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Kit.inner, style: .continuous).strokeBorder(Color.green, lineWidth: best ? 1.5 : 0))
        .opacity(side.eval == nil ? 0.55 : 1)
    }
}

// MARK: - The promo on the slip

/// Add a promo (Nov 5): the wallet's waiting tokens, the ones that fit this slip first, then the typed bonus bet or
/// profit boost with its terms (what the old "Promo on this slip" card held), and the book it is for.
struct SlipPromoSheet: View {
    @ObservedObject var model: BuildModel
    let wallet: [PromoRow]
    let fits: (PromoRow) -> Bool
    @Environment(\.theme) private var theme
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let ranked = wallet.map { (p: $0, fits: fits($0)) }.sorted { $0.fits && !$1.fits }
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    SectionTitle("In your wallet", note: wallet.isEmpty ? nil : "\(wallet.count) waiting")
                    if wallet.isEmpty {
                        Text("No promos waiting. Add them under Me › Promos, or type one below.").font(.footnote).foregroundStyle(.secondary)
                    }
                    ForEach(ranked, id: \.p.id) { r in token(r.p, fits: r.fits) }
                    SectionTitle("Or type one").padding(.top, 4)
                    VStack(alignment: .leading, spacing: 12) {
                        PromoBar(model: model)
                        if model.promo.kind != .none { bookPick }
                    }
                    .padding(14)
                    .background(theme.cardColor, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                    Text("Picking one shows what this slip is worth with it; I placed this then saves the bet with that token, at its dollars, and takes it out of your wallet. To search every game for the best bet for a promo, use Build's Use a promo.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                .padding()
            }
            .scrollDismissesKeyboard(.interactively)
            .background(theme.pageColor.ignoresSafeArea())
            .navigationTitle("Promo on this slip")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if model.promo.kind != .none { Button("No promo") { model.promo = .none; dismiss() } }
                }
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
        .presentationDetents([.large])
    }

    /// A waiting token: its book, what it is, its terms and when it ends. A tap puts it on the slip.
    private func token(_ p: PromoRow, fits: Bool) -> some View {
        let on = model.promo == Promos.asPromo(p) && model.promoBook == SlipWords.book(p)
        let ends = TokenCard<EmptyView>.ends(p, now: Date())
        let terms = Promos.terms(p)
        return Button {
            model.promo = Promos.asPromo(p)
            model.promoBook = SlipWords.book(p)
            model.promoToken = p
            dismiss()
        } label: {
            HStack(spacing: 12) {
                BookIcon(book: p.book, size: 34)
                VStack(alignment: .leading, spacing: 2) {
                    Text(Promos.title(p).prefix(1).uppercased() + Promos.title(p).dropFirst()).font(.body.weight(.semibold))
                    if !terms.isEmpty { Text(terms).font(.footnote).foregroundStyle(.secondary) }
                    HStack(spacing: 6) {
                        Text(fits ? "Fits this slip" : "Doesn't fit this slip as it is").foregroundStyle(fits ? Color.green : .secondary)
                        if let ends { Text("· " + ends.text).foregroundStyle(ends.soon ? Color.orange : .secondary) }
                    }
                    .font(.caption.weight(.semibold))
                }
                .multilineTextAlignment(.leading)
                Spacer(minLength: 6)
                Image(systemName: on ? "checkmark.circle.fill" : "circle").foregroundStyle(on ? theme.accent : Color.secondary.opacity(0.5))
            }
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
            .background(theme.cardColor, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).strokeBorder(theme.accent, lineWidth: on ? 1.5 : 0))
            .contentShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// The book the promo is from: the slip goes there. Best price leaves it to the three prices.
    private var bookPick: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("The promo is at").font(.caption).foregroundStyle(.secondary)
            Picker("The promo is at", selection: $model.promoBook) {
                Text("Best price").tag(BuildBook?.none)
                ForEach(BuildBook.mine) { Text($0.rawValue).tag(BuildBook?.some($0)) }
            }
            .pickerStyle(.segmented)
        }
    }
}

/// No promo / Bonus bet / Profit boost; a boost has 25, 30, 50, 100% or a typed size; then the token's terms as the book
/// states them (stake, a boost's max extra winnings, min legs, min odds), kept when switching type or size. The choice
/// stays on this phone.
private struct PromoBar: View {
    @ObservedObject var model: BuildModel
    @State private var other = ""

    private enum Kind: String, CaseIterable { case none = "No promo", bonus = "Bonus bet", boost = "Profit boost" }
    private var kind: Binding<Kind> {
        Binding(get: { switch model.promo.kind { case .none: .none; case .bonus: .bonus; case .boost: .boost } },
                set: { k in
                    let to: Promo.Kind = k == .none ? .none : k == .bonus ? .bonus : .boost
                    if to != model.promo.kind { model.promo = model.promo.switched(to: to) }
                })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("Promo", selection: kind) { ForEach(Kind.allCases, id: \.self) { Text($0.rawValue).tag($0) } }.pickerStyle(.segmented)
            if model.promo.kind == .boost {
                let b = model.promo.pct
                HStack(spacing: 6) {
                    ForEach(BuildModel.boosts, id: \.self) { x in
                        PickChip(text: "\(Int(x))%", on: b == x) { other = ""; model.promo.pct = x }
                    }
                    HStack(spacing: 2) {
                        TextField("Other", text: $other).keyboardType(.decimalPad).frame(width: 52).multilineTextAlignment(.trailing)
                            .onChange(of: other) { _, t in
                                if let n = Double(t.filter { $0.isNumber || $0 == "." }), n > 0, n <= 500 { model.promo.pct = n }
                            }
                        Text("%").foregroundStyle(.secondary)
                    }
                    .font(.subheadline).padding(.horizontal, 8).padding(.vertical, 5)
                    .background(BuildModel.boosts.contains(b) ? Color(.tertiarySystemFill) : Color.accentColor.opacity(0.18), in: Capsule())
                }
            }
            if model.promo.kind != .none {
                Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
                    GridRow {
                        TermField(model: model, label: model.promo.kind == .bonus ? "Bonus $" : "Stake $", hint: "10",
                                  get: { $0.stake.map { String(format: "%g", $0) } }, set: { $0.stake = Self.number($1) })
                        if model.promo.kind == .boost {
                            TermField(model: model, label: "Max extra winnings $", hint: "none",
                                      get: { $0.maxExtra.map { String(format: "%g", $0) } }, set: { $0.maxExtra = Self.number($1) })
                        }
                    }
                    GridRow {
                        TermField(model: model, label: "Min legs", hint: "any",
                                  get: { $0.minLegs.map(String.init) }, set: { $0.minLegs = Self.number($1).map { Int($0) } })
                        TermField(model: model, label: "Min odds", hint: "any", odds: true,
                                  get: { $0.minOdds.map { Fmt.am($0) } }, set: { p, t in
                                      let n = Marking.parseOdds(t); p.minOdds = n != nil && n != 0 ? n : nil })
                    }
                    GridRow {
                        TermField(model: model, label: "Max odds", hint: "any", odds: true,
                                  get: { $0.maxOdds.map { Fmt.am($0) } }, set: { p, t in
                                      let n = Marking.parseOdds(t); p.maxOdds = n != nil && n != 0 ? n : nil })
                        Color.clear.frame(height: 1)
                    }
                }
                .id(model.promo.kind)
            }
        }
        .onAppear { if model.promo.kind == .boost, !BuildModel.boosts.contains(model.promo.pct) { other = String(format: "%g", model.promo.pct) } }
    }

    /// A typed amount, or nil when it's empty or zero (web setTerm).
    static func number(_ t: String) -> Double? {
        let n = Double(t.filter { $0.isNumber || $0 == "." })
        return n.flatMap { $0.isFinite && $0 != 0 ? $0 : nil }
    }
}

/// One of a token's terms: a small labeled field that writes to the promo as you type.
private struct TermField: View {
    @ObservedObject var model: BuildModel
    let label: String
    let hint: String
    var odds = false
    let get: (Promo) -> String?
    let set: (inout Promo, String) -> Void
    @State private var text = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            TextField(hint, text: $text).keyboardType(odds ? .numbersAndPunctuation : .decimalPad)
                .textFieldStyle(.roundedBorder).font(.subheadline.monospacedDigit())
                .onChange(of: text) { _, t in var p = model.promo; set(&p, t); if p != model.promo { model.promo = p } }
        }
        .onAppear { text = get(model.promo) ?? "" }
    }
}

extension Promo {
    var name: String {
        switch kind { case .bonus: "a bonus bet"; case .boost: "a \(String(format: "%g", pct))% profit boost"; case .none: "" }
    }
    /// The value in dollars when a stake is set, then a bonus bet's share kept or a boost's EV (web evText).
    func text(_ ev: Double) -> String {
        let dollars = stake.map { "\(ev < 0 ? Fmt.minus : "+")$\(String(format: "%.2f", abs(ev * $0))) · " } ?? ""
        if kind == .bonus { return dollars + "keeps \(Int((ev * 100).rounded()))%" }
        return dollars + "EV " + String(format: "%.1f%%", ev * 100).replacingOccurrences(of: "-", with: Fmt.minus)
    }
    func good(_ ev: Double) -> Bool { ev >= (kind == .bonus ? 0.6 : 0) }
}

// MARK: - Saved parlays

/// Your saved parlays and how each grade has done (behind Build's bookmark).
struct SavedParlaysView: View {
    @EnvironmentObject private var store: BetStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let customs = store.customs.sorted { ($0.quotedAt ?? "") > ($1.quotedAt ?? "") }
        let byGrade = Build.recordByGrade(customs)
        NavigationStack {
            List { Group {
                if customs.isEmpty { Text("Parlays you save from your slip show here with their grade and result.").foregroundStyle(.secondary) }
                if !byGrade.isEmpty {
                    Section("Record by grade") {
                        StatTable(head: ["Grade", "Graded", "Hit", "Expected", "Units"],
                                  rows: byGrade.map { g in [TCell(text: g.grade), TCell(text: "\(g.graded)"), TCell(text: "\(g.won)"),
                                                            TCell(text: String(format: "%.1f", g.expected)),
                                                            TCell(text: BetMath.signedUnits(g.units), color: tone(g.units))] })
                    }
                }
                if !customs.isEmpty {
                    Section("Your parlays · \(customs.count)") {
                        ForEach(customs.prefix(50)) { c in
                            HStack(alignment: .firstTextBaseline) {
                                TagView(text: c.grade ?? "?")
                                Text((c.legs ?? []).map(Fmt.label).joined(separator: " + ")).font(.footnote).lineLimit(3)
                                Spacer()
                                VStack(alignment: .trailing, spacing: 2) {
                                    Text(Fmt.am(c.price)).font(.footnote.monospacedDigit())
                                    Text("fair \(Fmt.am(c.fairPrice))").font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                                    let st = c.status ?? "open"
                                    Text(["won", "lost", "void", "push"].contains(st) ? st : "open").font(.caption2)
                                        .foregroundStyle(st == "won" ? .green : st == "lost" ? .red : .secondary)
                                }
                            }
                        }
                    }
                }
            }.themedRows() }.themedList()
            .navigationTitle("Your parlays")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}
