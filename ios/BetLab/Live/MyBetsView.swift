import SwiftUI

/// Live (the overhaul, Nov 4; it was My bets, web app/bets): your open bets, each a card with its game's score and its
/// legs as rings, and Settled by day behind one tap. Record, Stats, Ladder and Prices are screens of their own under Me
/// (Me/BetScreens.swift), where the P/L leads; the wall is one tap away in the toolbar.
struct MyBetsView: View {
    @EnvironmentObject private var store: BetStore
    @State private var view = "open"
    @State private var adding = false
    @StateObject private var live = LiveModel()
    @Environment(\.scenePhase) private var phase

    // A bet the live tracker already settles (lost, or won on every leg) is filed under Settled and counted before the
    // worker grades it (Live.markLiveSettled, web Oct 23)
    private var bets: [MyBet] { Live.markLiveSettled(store.bets, live.settled) }
    // From the account's real-money start (Oct 18), Settled counts real bets only; paper shows apart (BetMath.recordBets)
    private var split: (useReal: Bool, counted: [MyBet], paper: [MyBet]) { BetMath.recordBets(bets, realMode: store.isReal) }
    private var open: [MyBet] { bets.filter(\.isOpen) }
    /// Ungraded bets (live-settled ones included) are tracked from today's boards; the Settled tab adds the 40 most
    /// recent graded ones, from their own game days.
    private var ungraded: [MyBet] { store.bets.filter(\.isOpen) }
    private var recentGraded: [MyBet] {
        Array(store.bets.filter { !$0.isOpen }.sorted { (BetMath.start($0) ?? $0.placedAt) > (BetMath.start($1) ?? $1.placedAt) }.prefix(40))
    }
    private var settled: [MyBet] { split.counted.filter { !$0.isOpen } }
    private var paperSettled: [MyBet] { split.useReal ? split.paper.filter { !$0.isOpen } : [] }
    private var hasReal: Bool { split.useReal }
    /// Units riding on open bets; a bonus bet's stake is the book's credit, not yours.
    private var inPlay: Double { open.filter { !$0.isBonus }.reduce(0) { $0 + BetMath.stake($1) } }

    var body: some View {
        NavigationStack {
            List { Group {
                Section {
                    segments.cardRow()
                    if view == "open" && !open.isEmpty && live.liveCount > 0 {
                        HStack {
                            LiveCountPill(n: live.liveCount)
                            Spacer()
                            NavigationLink { WallView(open: ungraded, live: live) } label: {
                                Text("The wall").font(.footnote.weight(.semibold)).foregroundStyle(.tint)
                            }
                            .fixedSize()
                        }
                        .cardRow()
                    }
                }
                if let e = store.error { Section { Label(e, systemImage: "exclamationmark.triangle").foregroundStyle(.red) } }
                if view == "open" {
                    byDay(open, newestFirst: false,
                          empty: ("No open bets", "Tap I placed this on a pick or parlay and it shows up here until it's graded."))
                } else {
                    byDay(settled, newestFirst: true,
                          empty: ("Nothing settled yet", "\(hasReal ? "Real bets" : "Bets") show up here the morning after their game, graded with CLV."))
                    if !paperSettled.isEmpty {
                        Section { DisclosureGroup("Paper bets · \(paperSettled.count)") { ForEach(paperSettled) { BetCardView(b: $0, live: live.bets[$0.betId]) } } }
                    }
                }
            }.themedRows() }.themedList()
            .navigationTitle("Live")
            .subtitle(hasReal ? nil : "Paper until Oct 18")
            // Grade now, the wall, + Add and Search small in the corner
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { JobButton(job: .grade, api: store.api) { await store.load() } }
                ToolbarItemGroup(placement: .topBarTrailing) {
                    NavigationLink { WallView(open: ungraded, live: live) } label: { Image(systemName: "square.grid.2x2") }
                        .accessibilityLabel("The wall")
                    Button { adding = true } label: { Image(systemName: "plus") }.accessibilityLabel("Add a bet from a screenshot")
                    NavigationLink { SearchView() } label: { Image(systemName: "magnifyingglass") }.accessibilityLabel("Search")
                }
            }
            .sheet(isPresented: $adding) { SlipAddView() }
            .refreshable { await store.load() }
            // the live tracker: once on appear, then every 20 s while a game is on (or about to start), else every
            // 5 minutes; only while Live is on screen and the app is in the foreground. It restarts when the open bets
            // change (they load after the first appear).
            .task(id: "\(phase == .active)|\(view == "settled")|\(store.refreshTick)|\(ungraded.map(\.betId).sorted().joined(separator: ","))") {
                guard phase == .active else { return }
                while !Task.isCancelled {
                    await live.refresh(store.api, open: Set(ungraded.map(\.betId)),
                                      done: view == "settled" ? Set(recentGraded.map(\.betId)) : [])
                    try? await Task.sleep(for: live.soon ? LiveModel.fast : LiveModel.slow)
                }
            }
            .overlay { if !store.loaded && store.error == nil { ProgressView() } }
        }
    }

    // MARK: - Open / Settled

    /// Two words with an underline, and the units in play at the right.
    private var segments: some View {
        HStack(alignment: .top, spacing: 22) {
            segment(open.isEmpty ? "Open" : "Open \(open.count)", "open")
            segment("Settled", "settled")
            Spacer(minLength: 8)
            if inPlay > 0 {
                Text("\(KitLive.units(inPlay)) in play").font(.footnote.weight(.semibold)).foregroundStyle(.secondary).padding(.top, 3)
            }
        }
        .padding(.horizontal, 4)
    }

    private func segment(_ title: String, _ tag: String) -> some View {
        Button { view = tag } label: {
            VStack(spacing: 7) {
                Text(title).font(.headline).foregroundStyle(view == tag ? .primary : .secondary)
                Capsule().fill(view == tag ? Color.accentColor : .clear).frame(height: 3)
            }
            .fixedSize()
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(view == tag ? .isSelected : [])
    }

    // MARK: - lists

    @ViewBuilder
    private func byDay(_ bets: [MyBet], newestFirst: Bool, empty: (String, String)) -> some View {
        if bets.isEmpty {
            Section {
                GlowCard {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(empty.0).font(.headline)
                        Text(empty.1).font(.footnote).foregroundStyle(.secondary)
                    }
                }
                .cardRow()
            }
        } else {
            let key = { (b: MyBet) in BetMath.start(b) ?? b.placedAt }
            let sorted = bets.sorted { newestFirst ? key($0) > key($1) : key($0) < key($1) }
            let days = sorted.reduce(into: [String]()) { if $0.last != BetMath.day($1) { $0.append(BetMath.day($1)) } }
            ForEach(days, id: \.self) { d in
                Section {
                    ForEach(sorted.filter { BetMath.day($0) == d }) {
                        BetCardView(b: $0, live: live.bets[$0.betId], cashing: live.cashing.contains($0.betId), carded: true, rx: store.reacting($0)).cardRow()
                    }
                } header: {
                    Text(Fmt.longDay(Models.date(d + "T16:00:00Z") ?? Date())).font(.footnote.weight(.semibold)).textCase(nil)
                }
            }
        }
    }
}

/// One open bet on a screen of its own, from Today's live card. It polls for itself: Today's loop is a .task on Today,
/// which SwiftUI cancels once this is pushed over it (the wall's lesson, Oct 27).
struct LiveBetScreen: View {
    let betId: String
    @ObservedObject var live: LiveModel
    @EnvironmentObject private var store: BetStore
    @Environment(\.theme) private var theme
    @Environment(\.scenePhase) private var phase

    var body: some View {
        let bets = Live.markLiveSettled(store.bets, live.settled)
        ScrollView {
            VStack(spacing: 12) {
                if let b = bets.first(where: { $0.betId == betId }) {
                    BetCardView(b: b, live: live.bets[betId], cashing: live.cashing.contains(betId), carded: true, rx: store.reacting(b))
                } else {
                    Text("This bet is no longer open.").font(.footnote).foregroundStyle(.secondary).padding(.top, 40)
                }
            }
            .padding(.horizontal).padding(.vertical, 12)
        }
        .background(theme.page ?? Color(.systemGroupedBackground))
        .navigationTitle("Your bet")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: "\(phase == .active)|\(store.refreshTick)") {
            guard phase == .active else { return }
            while !Task.isCancelled {
                await live.refresh(store.api, open: Set(store.bets.filter(\.isOpen).map(\.betId)))
                try? await Task.sleep(for: live.soon ? LiveModel.fast : LiveModel.slow)
            }
        }
    }
}

/// One bet. `carded` (Live, since the overhaul) draws it as a card of its own: an open bet on one game leads with that
/// game's score between the two logos, the teams' colors a soft glow behind it; a bet across games with a stack of
/// their logos. Then its name and price, book · stake · boost, what a win pays, and its legs as rings (LiveBetView);
/// Edit, Undo and Share while open. Settled, the tracker folds to one line. A friend's bet (Friends, Oct 27) is the
/// same with `friend` set: their name on top (`who`), and Tail while it's open in place of Edit, Undo and Share.
struct BetCardView: View {
    let b: MyBet
    var live: BetLive? = nil
    var cashing = false
    var friend = false
    var who: Profile? = nil
    var tailed = false
    var carded = false
    /// Reactions (0042): a friend's bet takes yours (the smiley beside Tail); your own shows who reacted.
    var rx: Reacting? = nil
    @EnvironmentObject private var store: BetStore
    @State private var busy = false
    @State private var error: String?
    @State private var editing = false

    private var settled: Bool { BetMath.isSettled(b) }
    private var st: Double { BetMath.stake(b) }
    /// What a win pays: stake x (decimal price - 1) x the boost.
    private var win: Double? { b.price.map { BetMath.boosted(b, st * (BetMath.dec($0) - 1)) } }
    /// An open bet on one game: that game leads the card.
    private var headGame: GameLive? {
        guard !settled, let live, live.games.count == 1 else { return nil }
        return live.games.first
    }

    var body: some View {
        Group {
            if carded {
                GlowCard(left: glow.0, right: glow.1) { content }
                    .overlay { if cashing { CashOverlay(win: win) } }
                    .clipShape(RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: Kit.radius, style: .continuous).strokeBorder(Color.green, lineWidth: cashing ? 2 : 0)
                            .shadow(color: .green.opacity(cashing ? 0.6 : 0), radius: 12)
                    }
                    .animation(.easeInOut(duration: 0.4), value: cashing)
                    .reactionBubble(rx)
            } else {
                content.padding(.vertical, 4)
            }
        }
        .sheet(isPresented: $editing) { EditBetSheet(bet: b, parlay: b.kind == "parlay" || b.kind == "custom") }
    }

    /// Team color as light: the one game's two teams; across games, the first game still on.
    private var glow: (Color?, Color?) {
        guard !settled, let live else { return (nil, nil) }
        if let g = headGame { return (Color(hex: g.away.color), Color(hex: g.home.color)) }
        let g = live.games.first { $0.state == "in" } ?? live.games.first
        return (nil, Color(hex: g?.home.color))
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let who {
                NavigationLink { FriendProfileView(friend: who) } label: {
                    HStack(spacing: 8) {
                        AvatarView(p: who, size: 26)
                        Text(who.name).font(.footnote.weight(.semibold))
                        Text(Fmt.dayTime(b.placedAt)).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .buttonStyle(.plain)
            }
            if let g = headGame {
                ScoreHead(g: g)
                Hairline()
            } else if !settled, let live, live.games.count > 1 {
                let on = live.games.filter { $0.state == "in" }.count
                HStack {
                    ArtStack(urls: KitLive.logos(live))
                    Spacer()
                    if on > 0 { LivePill(text: "\(on) of \(live.games.count) live") }
                }
            }
            title
            notes
            if let live, !live.games.isEmpty {
                LiveBetView(b: live, folded: settled, head: headGame == nil)
            }
            actions
            // the tracker is the legs (Mike, Oct 24); the plain list only for a bet the tracker has no game for
            if let legs = b.legs, !legs.isEmpty, live?.games.isEmpty ?? true {
                DisclosureGroup("Legs") {
                    ForEach(Array(legs.enumerated()), id: \.offset) { _, l in
                        let r = b.legResults?.first { $0.leg == l }
                        HStack {
                            Text(l).font(.footnote)
                            Spacer()
                            Text(r.map { $0.result + ($0.value.map { " · \(String(format: "%g", $0))" } ?? "") } ?? "open")
                                .font(.caption).foregroundStyle(r?.result == "won" ? .green : r?.result == "lost" ? .red : .secondary)
                        }
                    }
                }
                .font(.caption)
            }
        }
    }

    /// The name and "FanDuel · 4u · 50% boost" on the left; the price and what a win pays (or what it made) on the right.
    private var title: some View {
        // short (Mike, Oct 24): a parlay is "4-leg parlay", not its long name; a single is its bet
        let n = Stats.legsOf(b), p = BetMath.profit(b)
        var sub = [BetMath.book(b), Marking.units(st) + (b.isBonus ? " bonus" : "")]
        if let bo = b.boost, bo > 0 { sub.append("\(Live.js(bo))% boost") }
        if b.reset == true { sub.append("bet reset") }
        return HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(n > 1 ? Stats.betName(legs: b.legs, label: nil, price: nil, n: n) : BetMath.what(b)).font(.title3.weight(.heavy)).lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                Text(sub.joined(separator: " · ")).font(.footnote).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.85)
            }
            Spacer(minLength: 6)
            VStack(alignment: .trailing, spacing: 5) {
                if let price = b.price {
                    Text(Fmt.am(price)).font(.system(size: 22, weight: .bold, design: .monospaced))
                } else {
                    Text("fair \(Fmt.am(b.fairPrice))").font(.subheadline.monospacedDigit().weight(.semibold)).foregroundStyle(.secondary)
                }
                if settled {
                    Text(BetMath.signedUnits(p)).font(.footnote.weight(.bold)).monospacedDigit()
                        .foregroundStyle((p ?? 0) > 0 ? .green : (p ?? 0) < 0 ? .red : .primary)
                } else if let win {
                    Text("wins \(Marking.units(win))").font(.footnote.weight(.semibold)).foregroundStyle(.green)
                }
            }
            .fixedSize()
        }
    }

    /// When and where, CLV, a read slip's value, a live result waiting for its grade: one quiet block.
    private var notes: some View {
        let clv = BetMath.personalClv(b)
        return VStack(alignment: .leading, spacing: 2) {
            if Stats.legsOf(b) <= 1, b.label != nil, let m = b.matchup { Text(m) }
            HStack(spacing: 4) {
                Text(BetMath.start(b).map { Fmt.dayTime($0) } ?? "marked \(Fmt.dayTime(b.placedAt))")
                if b.price == nil, !settled { Text("· no \(BetMath.book(b)) price typed") }
                if let c = clv {
                    Text("· CLV")
                    Text(Fmt.signed(c)).bold().foregroundStyle(c > 0 ? .green : c < 0 ? .red : .primary)
                } else if !settled, let c = b.clvNow {      // live CLV until the close decides it (web BetCard)
                    Text("· CLV now")
                    Text(Fmt.signed(c)).bold().foregroundStyle(c > 0 ? .green : c < 0 ? .red : .primary)
                }
            }
            .lineLimit(1).minimumScaleFactor(0.85)
            if let sp = b.slipP, let price = b.price {
                let v = Slip.ev(p: sp, price: price, boost: b.boost, bonus: b.isBonus)
                Text("Fair \(Fmt.am(v.fair)) when added · **\(Fmt.signed(v.ev))** value")
            }
            if let ls = b.liveSettled { Text("\(ls) live · not graded yet") }
        }
        .font(.caption).foregroundStyle(.secondary)
    }

    @ViewBuilder private var actions: some View {
        if friend {
            HStack(alignment: .top, spacing: 10) {
                if Social.canTail(b) { TailButton(b: b, done: tailed) } else { Spacer(minLength: 0) }
                if let rx, rx.react != nil { ReactButton(rx: rx) }
            }
        } else {
            HStack(spacing: 14) {
                // a settled real bet keeps Edit (Nov 9: a misread price or stake was wrong for good once graded; its
                // profit follows the edit as grading works it out), never Undo
                if b.isReal {
                    Button(b.price == nil ? "Add the price you got" : "Edit") { editing = true }
                }
                if !settled {
                    Button("Undo") {
                        busy = true
                        Task { error = await store.undo(b); busy = false }
                    }
                    if busy { ProgressView().controlSize(.small) }
                }
                ShareBetButton(b: b)      // the bet as a picture (W13, Oct 24), open or settled
            }
            .font(.caption.weight(.semibold)).buttonStyle(.borderless).disabled(busy)
            if let error { Text(error).font(.caption2).foregroundStyle(.red) }
        }
    }
}
