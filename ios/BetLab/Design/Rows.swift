import SwiftUI

private let tierName: [Tier: String] = [.pick: "Pick", .lean: "Lean", .check: "Check the news"]

struct TagView: View {
    let text: String
    var color: Color = .secondary
    var body: some View {
        Text(text).font(.caption2.weight(.semibold))
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }
}

extension Tier {
    var color: Color { switch self { case .pick: .green; case .lean: .blue; case .check: .orange } }
}

/// One bet: what, price, one stats line, Open in the book; the reasoning one tap away (web BetRow).
struct BetRowView: View {
    let o: Offer
    var showGame = true
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // what and its price up top, then three numbers (the overhaul's pick card, Nov 4; web BetRow)
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(Fmt.label(o.label)).font(.title3.weight(.heavy)).lineLimit(2)
                    Group {
                        if showGame { Text("\(Fmt.matchup(o.matchup, sport: o.league)) · \(Fmt.dayTime(o.commenceTime))") }
                        Text("\(Fmt.sportName(o.league)) · \(Fmt.marketName(o.market))")
                    }
                    .font(.footnote).foregroundStyle(.secondary)
                    HStack(spacing: 6) {
                        TagView(text: tierName[o.tier]!, color: o.tier.color)
                        if FeedLogic.isEarlyLean(o, now: Date()) { TagView(text: "Early · unproven", color: .orange) }
                    }
                    .padding(.top, 3)
                }
                Spacer(minLength: 4)
                VStack(alignment: .trailing, spacing: 4) {
                    Text(Fmt.am(o.price)).font(.system(.title, design: .monospaced).weight(.bold)).foregroundStyle(.tint)
                    Text((o.book ?? "FanDuel").uppercased()).font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
                }
            }
            if o.tier != .check {
                HStack(spacing: 14) {
                    StatCell(name: "CHANCE", value: Fmt.pct(o.pFinal, 1))
                    Divider()
                    StatCell(name: "FAIR PRICE", value: o.pFinal.map { Fmt.am(Fmt.fair($0)) } ?? "—")
                    Divider()
                    StatCell(name: "EDGE", value: Fmt.signed(o.ev), color: (o.ev ?? 0) >= 0 ? .green : .red)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
            if o.betLimit != nil || (o.otherBook != nil && o.otherPrice != nil) {
                HStack(spacing: 4) {
                    if let lim = o.betLimit { Text("$\(Int(lim.rounded()).formatted()) available") }
                    if o.betLimit != nil, o.otherBook != nil, o.otherPrice != nil { Text("·") }
                    if let ob = o.otherBook, let op = o.otherPrice { Text("\(ob) \(Fmt.am(op))") }
                }
                .font(.footnote).foregroundStyle(.secondary)
            }
            // one row: Place (or what was placed), the book's icon, and Why (Mike, Oct 24)
            HStack(alignment: .center, spacing: 10) {
                if o.tier != .check { MarkControl(input: .offer(o)); BookButton(book: o.book, link: o.fdUrl) }
                Spacer(minLength: 4)
                Button(expanded ? "Hide" : (o.tier == .check ? "Model vs. market" : "Why")) { expanded.toggle() }
                    .font(.caption).buttonStyle(.borderless)
            }
            if expanded {
                VStack(alignment: .leading, spacing: 4) {
                    if let c = o.context { Text(c) }
                    if let w = o.why { Text(w) }
                    Text("Market \(Fmt.pct(o.pMarket, 1)) · our model \(Fmt.pct(o.pModel, 1)) · stake \(o.unitsFlat.map { String(format: "%g", $0) } ?? "1")u\(o.marketSource.map { " · \($0)" } ?? "")")
                        .foregroundStyle(.secondary)
                }
                .font(.footnote)
            }
        }
        .padding(.vertical, 6)
    }
}

/// One number under its small name: the cells on a pick card.
struct StatCell: View {
    let name: String
    let value: String
    var color: Color = .primary
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(name).font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
            Text(value).font(.system(.callout, design: .monospaced).weight(.bold)).foregroundStyle(color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Open the bet at its book: the book's own icon (Mike, Oct 24: "a button with the logo of the sports book instead of
/// that long button"). FanDuel opens its app's betslip, DraftKings its web link (which opens the app), Novig its app's
/// order slip with the outcome and a $5 stake (novigapp://, Oct 28; the web link if the app isn't there).
struct BookButton: View {
    let book: String?
    let link: String?
    var size: CGFloat = 30
    @Environment(\.openURL) private var openURL

    var body: some View {
        if let link, !link.isEmpty {
            let name = Marking.bookOf(book)
            Button {
                if name == "FanDuel", let l = FanDuel.links(link) {
                    openURL(l.app) { ok in if !ok { openURL(l.web) } }
                } else if name == "Novig", let l = Novig.links(link) {     // its app scheme (Oct 28)
                    openURL(l.app) { ok in if !ok { openURL(l.web) } }
                } else if let u = URL(string: link) {
                    openURL(u)
                }
            } label: {
                Image("book-" + name.lowercased()).resizable().interpolation(.high).scaledToFit()
                    .frame(width: size, height: size)
                    .clipShape(RoundedRectangle(cornerRadius: size * 0.24))
                    .overlay(RoundedRectangle(cornerRadius: size * 0.24).strokeBorder(Color.secondary.opacity(0.25), lineWidth: 0.5))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Open in \(name)")
        }
    }
}

/// A game in the feed: when, who, and its one or two best things to look at (web GameRow).
struct GameRowView: View {
    let g: FeedGame

    var body: some View {
        let bets = g.offers.filter { $0.tier != .check }
        let sgps = g.tickets.filter { $0.kind == "sgp" }
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(Fmt.time(g.game.commenceTime)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                Text(Fmt.matchup(g.game.matchup, sport: g.game.league)).font(.subheadline.weight(.semibold)).lineLimit(1)
                Spacer()
                TagView(text: Fmt.sportShort[g.game.league] ?? g.game.league)
            }
            ForEach(bets.prefix(2)) { o in
                HStack(spacing: 6) {
                    TagView(text: o.tier == .pick ? "Pick" : "Lean", color: o.tier.color)
                    Text(Fmt.label(o.label)).font(.footnote).lineLimit(1)
                    Spacer()
                    Text(Fmt.am(o.price)).font(.footnote.monospacedDigit())
                    Text(Fmt.signed(o.ev)).font(.caption.monospacedDigit()).foregroundStyle((o.ev ?? 0) >= 0 ? .green : .red)
                }
            }
            if bets.count > 2 { Text("+\(bets.count - 2) more on this game").font(.caption).foregroundStyle(.secondary) }
            if !sgps.isEmpty {
                let best = sgps.max { ($0.pFair ?? 0) < ($1.pFair ?? 0) }
                Text("\(sgps.count) parlay\(sgps.count == 1 ? "" : "s")\(best.map { " · best \"\($0.body.theme ?? "SGP")\" fair \(Fmt.am($0.fairPrice))" } ?? "")")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }
}

/// A parlay: its title and fair price, the legs one tap away.
struct TicketRowView: View {
    let t: Ticket
    let title: String
    @EnvironmentObject private var store: BetStore

    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 6) {
                if let s = t.body.story ?? t.body.why { Text(s).font(.footnote).foregroundStyle(.secondary) }
                // a multi-game ticket carries its legs twice (per game and flat), so the flat list only when there
                // are no games, as the web's TicketCard does (Oct 15: every SGP+ leg showed twice)
                if let games = t.body.games, !games.isEmpty {
                    ForEach(Array(games.enumerated()), id: \.offset) { _, g in
                        Text("\(Fmt.matchup(g.matchup, sport: t.sport)) · \(Fmt.time(g.commenceTime))").font(.caption.weight(.semibold)).padding(.top, 2)
                        ForEach(Array(g.legs.enumerated()), id: \.offset) { _, l in legRow(l) }
                    }
                } else {
                    ForEach(Array((t.body.legs ?? []).enumerated()), id: \.offset) { _, l in legRow(l) }
                }
                if t.kind == "over" {
                    HStack(spacing: 10) {
                        MarkControl(input: store.input(for: t))
                        if let link = t.body.link, store.myBooks.contains("FanDuel") { BookButton(book: "FanDuel", link: link) }
                    }
                    if t.body.link != nil, t.body.linkMain == true, let main = Build.mainLineText([true]) {
                        Text(main).font(.caption2).foregroundStyle(.secondary)
                    }
                } else {
                    SlipBooks(t: t)
                    MarkControl(input: store.input(for: t))
                }
            }
            .padding(.top, 4)
        } label: {
            HStack {
                Text(Fmt.time(t.commenceTime)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                Text(t.kind == "sgp" ? (t.body.theme ?? "Parlay") : title).font(.subheadline.weight(.semibold)).lineLimit(2)
                if store.marks[t.sgpId] != nil { Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).font(.caption) }
                Spacer()
                TagView(text: "fair \(Fmt.am(t.fairPrice))")
            }
        }
    }

    private func legRow(_ l: Leg) -> some View {
        HStack {
            Text(Fmt.label(l.label)).font(.footnote)
            Spacer()
            // its prices at the account's books (Nov 6): FanDuel's first, the others after it
            let on = store.myBooks
            let prices = [("FanDuel", l.price, "FD"), ("DraftKings", l.dkPrice, "DK"), ("Novig", l.nvPrice, "NV")]
                .filter { on.contains($0.0) && $0.1 != nil }
                .enumerated().map { i, p in (i == 0 && p.0 == "FanDuel" ? "" : "\(p.2) ") + Fmt.am(p.1) }
            Text(prices.isEmpty ? "fair \(Fmt.am(l.fairPrice))" : prices.joined(separator: " · "))
                .font(.footnote.monospacedDigit()).foregroundStyle(.secondary)
        }
    }
}

/// A slip at both books (web TicketCard's PriceBox and DkSide): type each book's SGP price to see the verdict (it
/// saves to `quotes`, as on the web), and open the whole slip in each book's betslip. DraftKings only when it
/// posts every leg; a boosted TD ticket is FanDuel's only.
struct SlipBooks: View {
    let t: Ticket
    @EnvironmentObject private var store: BetStore

    var body: some View {
        let legs = Self.legs(t)
        let on = store.myBooks                       // the account's books (Nov 6): the others' sides are gone
        VStack(alignment: .leading, spacing: 10) {
            if on.contains("FanDuel") { VStack(alignment: .leading, spacing: 6) {
                let fd = Self.line("FanDuel", naive: t.naivePrice, likely: t.body.likelyPrice, standIn: false)
                if !fd.isEmpty { Text(fd).font(.caption2).foregroundStyle(.secondary) }
                HStack(spacing: 10) {
                    PriceBox(t: t, book: "FanDuel", legs: legs.map(\.label),
                             label: t.kind == "td" ? "Boosted price" : t.kind == "sgp_plus" ? "FanDuel SGP+" : "FanDuel SGP")
                    let fdLink = Build.link(book: .fanduel, legs.map(\.link))
                    BookButton(book: "FanDuel", link: fdLink)
                    let linked = legs.filter { !($0.link ?? "").isEmpty }.count
                    if fdLink != nil, linked < legs.count {      // the logo alone hid a partial slip (web FdLink's count)
                        Text("\(linked)/\(legs.count)").font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                    }
                }
                if let miss = Self.fdMissing(legs) { Text(miss).font(.caption2).foregroundStyle(.secondary) }
                if let main = Build.mainLineText(legs.map { $0.link != nil && $0.linkMain == true }) {
                    Text(main).font(.caption2).foregroundStyle(.secondary)
                }
            } }
            if on.contains("DraftKings"), let dk = t.body.dk, let of = dk.of, of > 0, t.kind != "td" {
                VStack(alignment: .leading, spacing: 6) {
                    if (dk.legs ?? 0) < of {
                        Text("DraftKings posts \(dk.legs ?? 0) of these \(of) legs: this slip isn't on DraftKings.")
                            .font(.caption2).foregroundStyle(.secondary)
                    } else {
                        Text(Self.line("DraftKings", naive: dk.naivePrice, likely: dk.likelyPrice, standIn: dk.standIn == true)
                             + ((dk.moved ?? 0) > 0 ? " · \(dk.moved!) leg\(dk.moved! > 1 ? "s" : "") at its nearest number" : ""))
                            .font(.caption2).foregroundStyle(.secondary)
                        HStack(spacing: 10) {
                            PriceBox(t: t, book: "DraftKings", legs: legs.map { $0.dkLabel ?? $0.label },
                                     label: t.kind == "sgp_plus" ? "DraftKings SGP+" : "DraftKings SGP")
                            BookButton(book: "DraftKings", link: Build.link(book: .draftkings, legs.map(\.dkLink)))
                        }
                        if let main = Build.mainLineText(legs.map { $0.dkLink != nil && $0.dkLinkMain == true }, book: "DraftKings") {
                            Text(main).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if on.contains("Novig"), let nv = t.body.nv, let of = nv.of, of > 0, t.kind != "td" {
                // Novig (Oct 28): its exact price from its parlay pricer, nothing to type (web NvSide)
                if (nv.legs ?? 0) < of {
                    Text("Novig lists \(nv.legs ?? 0) of these \(of) legs: this slip isn't on Novig.").font(.caption2).foregroundStyle(.secondary)
                } else if let price = nv.price {
                    HStack(spacing: 10) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Novig \(Fmt.am(price)) exact").font(.subheadline.weight(.semibold).monospacedDigit())
                            Text([nv.stakeMax.map { "up to $\(Int($0))" }, nv.pricedAt.map { "priced \(Fmt.dayTime($0))" }]
                                    .compactMap { $0 }.joined(separator: " · ")).font(.caption2).foregroundStyle(.secondary)
                        }
                        Spacer()
                        BookButton(book: "Novig", link: nv.link)
                    }
                } else if nv.refused == true {
                    Text("No Novig market maker priced this slip just now (they quote parlays live; it's asked again every half hour).")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
    }

    /// Legs FanDuel's odds feed doesn't list have no link (the Conference League's goals markets, Oct 22): say what to
    /// add by hand (web fdMissingText).
    static func fdMissing(_ legs: [Leg]) -> String? {
        let miss = legs.filter { ($0.link ?? "").isEmpty }.count
        guard miss > 0, !legs.isEmpty else { return nil }
        if legs.count - miss == 1 && legs.count > 1 {
            return "Only 1 of these \(legs.count) legs is in FanDuel's odds feed, so there's no parlay link: build it in FanDuel's app."
        }
        return miss == legs.count
            ? "None of these legs are in FanDuel's odds feed, so there's no link: build it in FanDuel's app."
            : "\(miss) of these \(legs.count) legs aren't in FanDuel's odds feed: the button adds the rest, add them in FanDuel's app."
    }

    static func legs(_ t: Ticket) -> [Leg] {
        if let g = t.body.games, !g.isEmpty { return g.flatMap(\.legs) }
        return t.body.legs ?? []
    }

    /// "DraftKings legs +595 · likely +513"; empty when the slip carries neither (an NHL ticket has no legs price).
    static func line(_ book: String, naive: Double?, likely: Double?, standIn: Bool) -> String {
        var parts: [String] = []
        if let naive { parts.append("\(book) legs \(Fmt.am(naive))") }
        if let likely { parts.append("\(parts.isEmpty ? "\(book) " : "")likely \(Fmt.am(likely))" + (standIn ? " (FanDuel's pattern)" : "")) }
        return parts.joined(separator: " · ")
    }
}

/// Type a book's price for a slip (web PriceBox): the verdict updates as you type, the price saves on Done.
struct PriceBox: View {
    let t: Ticket
    let book: String
    let legs: [String]
    let label: String
    @EnvironmentObject private var store: BetStore
    @State private var text = ""
    @State private var state: String?
    @State private var busy = false
    @FocusState private var focused: Bool

    var body: some View {
        let saved = store.quote(t, book: book)
        let price = Marking.parseOdds(text) ?? (t.kind == "td" ? t.price : nil)
        let ev = price.flatMap { p in t.pFair.map { $0 * Odds.dec(p) - 1 } }
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Text(label).font(.caption.weight(.semibold))
                TextField(t.kind == "sgp_plus" ? "+1500" : "+800", text: $text)
                    .keyboardType(.numbersAndPunctuation).submitLabel(.done).focused($focused)
                    .font(.callout.monospacedDigit()).frame(width: 90)
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 7).strokeBorder(.quaternary))
                    .onSubmit { save(saved) }
                    .onChange(of: text) { state = nil }
                if busy { ProgressView().controlSize(.small) }
                else if let state { Text(state).font(.caption2).foregroundStyle(.secondary) }
            }
            Group {
                if let ev {
                    Text(ev >= 0 ? "Worth a fun-bucket dollar: EV \(Fmt.signed(ev))" : "Skip: EV \(Fmt.signed(ev)) (fair \(Fmt.am(t.fairPrice)))")
                        .foregroundStyle(ev >= 0 ? .green : .red)
                } else {
                    Text("Worth it above \(Fmt.am(t.fairPrice))").foregroundStyle(.secondary)
                }
            }
            .font(.caption2)
        }
        .onAppear { if text.isEmpty, let saved { text = Fmt.am(saved).replacingOccurrences(of: Fmt.minus, with: "-"); state = "Saved" } }
        .onChange(of: focused) { if !focused { save(saved) } }
    }

    private func save(_ saved: Double?) {
        guard let p = Marking.parseOdds(text), p != saved, !busy else { return }
        busy = true
        Task {
            let err = await store.saveQuote(t, price: p, book: book, legs: legs)
            state = err ?? "Saved"
            busy = false
        }
    }
}
