import SwiftUI

/// Me › Ladder (Mike, Oct 26; web components/me/Ladder.tsx): a ladder challenge, start to target, the whole stack on one
/// bet at a time. Choose a game or not: the worker (src/betlab/ladders.py) holds the day's best step (or that game's)
/// and locks it once its game's news is in, then alerts you. Place the locked step at the book and confirm it here, turn
/// it down for the next one, or make one of your own open bets the step. Ladder steps sit outside the 5u-a-day rule.
///
/// The screen makes the climb visible (the overhaul, Nov 5): the stack as the number that leads with the target beside
/// it and a rung per step, the step you are on as the main card, then the climb so far as a timeline, newest on top.
/// The rules (LadderMath, BetStore's ladder writes) are unchanged.
struct LadderView: View {
    @EnvironmentObject private var store: BetStore
    @Environment(\.theme) private var theme
    @State private var offers: [Offer] = []
    @State private var from = "1"
    @State private var to = "100"
    @State private var error: String?
    @State private var busy = false
    @State private var stopping: Ladder?
    @State private var today: [Game] = []
    @State private var startBook = BooksOff.mine.first ?? "FanDuel"      // one of your books (Nov 6)
    @State private var starting = false
    @State private var openPast: Set<String> = []
    @State private var art: [String: GameLive] = [:]       // ESPN's logos and colors: by game id, and the open step's by bet id
    /// The ladder's one book (0022): every step is priced and locked there.
    private var atBk: String { live?.l.book ?? "FanDuel" }
    /// Turned-down offers and the chosen game live on the ladder (migration 0021), shared with the web and the worker.
    private var skipped: [String] { live?.l.skipped ?? [] }
    private var game: String { live?.l.gameId ?? "" }
    private func gameName(_ id: String) -> String { today.first { $0.gameId == id }?.matchup ?? "your game" }
    private static let clockF: DateFormatter = { let f = DateFormatter(); f.timeZone = Fmt.et; f.dateFormat = "h:mm a"; return f }()
    private func clock(_ d: Date) -> String { Self.clockF.string(from: d) }

    private var states: [(l: Ladder, s: LadderState)] { store.ladders.map { ($0, LadderMath.state($0, store.bets)) } }
    private var live: (l: Ladder, s: LadderState)? {
        states.first { $0.l.status == "active" && ($0.s.phase == .inPlay || $0.s.phase == .nextStep) }
    }
    private var own: [MyBet] { store.bets.filter { $0.isOpen && $0.ladderId == nil && $0.isReal } }
    /// With none running, the newest one that busted or climbed in the last 3 days leads, saying what happened (web
    /// LadderView, Nov 6: it was folded under Past ladders, so the screen read "No ladder going" the morning after a loss).
    private var ended: (l: Ladder, s: LadderState)? {
        guard live == nil else { return nil }
        return states.first { x in
            guard x.s.phase == .busted || x.s.phase == .climbed else { return false }
            let last = Models.date(x.s.steps.last?.placedAt ?? x.l.endedAt ?? x.l.createdAt) ?? .distantPast
            return Date().timeIntervalSince(last) < 3 * 86_400
        }
    }
    private static let dayF: DateFormatter = { let f = DateFormatter(); f.timeZone = Fmt.et; f.dateFormat = "MMM d"; return f }()
    /// "Oct 28": a past ladder's day.
    static func dated(_ iso: String) -> String { Models.date(iso).map(dayF.string(from:)) ?? "" }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let e = error {
                Label(e, systemImage: "exclamationmark.triangle").font(.footnote.weight(.semibold)).foregroundStyle(.red)
            }
            if let (l, s) = live {
                let n = s.steps.count + (s.phase == .nextStep ? 1 : 0)
                hero(l, s, n: n)
                stepCard(l, s, n: n)
                SectionTitle("The climb", note: s.won == 0 ? nil : "\(s.won) won").padding(.top, 6)
                GlowCard { LadderTimeline(steps: s.steps, start: l.startUnits, target: l.targetUnits) }
                Button(s.steps.isEmpty ? "Remove ladder" : "Stop ladder") { stopping = l }
                    .buttonStyle(SoftButton(tall: false, danger: true)).disabled(busy)
            } else {
                if let e = ended { endedCard(e.l, e.s) }
                startCard
            }
            FoldCard(title: "How a ladder works") {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Start small and roll the whole stack into one bet at a time until you hit the target. One loss ends it.")
                    Text("Choose a game or not: BetLab holds the day's best step (its strongest +EV pick near even money), locks it once that game's news is in and alerts you.")
                    Text("The whole ladder stays at the book you pick. Ladder steps are real bets outside the 5u-a-day rule.")
                }
                .font(.footnote).foregroundStyle(.secondary)
            }
            past
        }
        .task(id: "\(store.refreshTick)|\(store.ladders.map(\.ladderId).joined())") {
            async let o = store.ladderOffers()
            async let g = store.ladderGames()
            (offers, today) = await (o, g)
            await loadArt()
        }
        .confirmationDialog(stopping.map { l in store.bets.contains { $0.ladderId == l.ladderId } } == true
                            ? "Stop this ladder? Its bets stay in Live." : "Remove this ladder? It has no steps yet.", isPresented: Binding(get: { stopping != nil }, set: { if !$0 { stopping = nil } }),
                            titleVisibility: .visible) {
            Button(stopping.map { l in store.bets.contains { $0.ladderId == l.ladderId } } == true ? "Stop ladder" : "Remove ladder",
                   role: .destructive) { if let l = stopping { run { await store.stopLadder(l) } } }
        }
    }

    private func phaseName(_ p: LadderPhase) -> String {
        switch p { case .climbed: "Climbed"; case .busted: "Busted"; case .stopped: "Stopped"; case .inPlay: "Step in play"; case .nextStep: "Next step" }
    }

    private func run(_ op: @escaping () async -> String?) {
        busy = true
        Task { error = await op(); busy = false }
    }

    /// Logos and colors for today's games (a held or locked step) and for the game of the step in play.
    private func loadArt() async {
        var games = today
        if let o = live?.s.open, let m = o.matchup, !m.isEmpty {
            let parts = m.components(separatedBy: " @ ")
            games.append(Game(gameId: o.betId, league: o.league ?? o.sport ?? "", home: parts.count == 2 ? parts[1] : nil,
                              away: parts.count == 2 ? parts[0] : nil, matchup: m, commenceTime: BetMath.start(o), state: nil))
        }
        guard !games.isEmpty else { return }
        let found = await Live.art(for: games, ttl: ESPN.doneTTL)
        art.merge(found) { _, new in new }
    }

    // MARK: the stack, the target and the rungs

    private func hero(_ l: Ladder, _ s: LadderState, n: Int) -> some View {
        let toGo = LadderMath.stepsToTarget(s.stack, l.targetUnits, price: 100)
        // what the step is doing, in words (Nov 6: "Step 1 next" said nothing; web "Waiting for a step")
        let held = LadderMath.suggest(offers, skipped: skipped, game: game.isEmpty ? nil : game, before: LadderMath.endOfDay(), book: atBk)
        let state = s.phase == .inPlay ? "in play" : l.locked != nil ? "locked" : held != nil ? "holding a step" : "looking for a step"
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                BookIcon(book: atBk, size: 22)
                Text("Step \(n)").font(.title3.weight(.bold))
                Text(state).font(.subheadline.weight(.semibold)).foregroundStyle(.secondary)
                Spacer(minLength: 4)
            }
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                HeroNumber(text: Marking.units(s.stack), size: 56)
                Text("of \(Marking.units(l.targetUnits))").font(.title3.weight(.semibold)).foregroundStyle(.secondary)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Stack \(Marking.units(s.stack)), target \(Marking.units(l.targetUnits))")
            RungTrack(won: s.won, toGo: max(1, toGo))
            Text("Started at \(Marking.units(l.startUnits)) · \(toGo) more even-money win\(toGo == 1 ? "" : "s") to the target")
                .font(.footnote).foregroundStyle(.secondary)
        }
    }

    // MARK: the step you are on

    @ViewBuilder
    private func stepCard(_ l: Ladder, _ s: LadderState, n: Int) -> some View {
        if let o = s.open {
            let g = art[o.betId]
            GlowCard(left: Color(hex: g?.away.color), right: Color(hex: g?.home.color)) {
                VStack(alignment: .leading, spacing: 14) {
                    stepTag("Step \(n) · in play", tier: nil)
                    stepHead(g, player: nil, league: o.league ?? o.sport, name: LadderMath.stepName(o),
                             sub: [o.matchup ?? "", o.book ?? atBk].filter { !$0.isEmpty }.joined(separator: " · "), price: o.price)
                    HStack(spacing: 14) {
                        StatCell(name: "ON IT", value: Marking.units(BetMath.stake(o)))
                        if let w = s.toWin {
                            Divider()
                            StatCell(name: "TO WIN", value: Marking.units(w))
                            Divider()
                            StatCell(name: "A WIN MAKES", value: Marking.units(s.stack + w), color: .green)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    Text("It settles with your bet in Live.").font(.footnote).foregroundStyle(.secondary)
                }
            }
        } else if s.phase == .nextStep {
            nextStep(l, s, n: n)
        }
    }

    @ViewBuilder
    private func nextStep(_ l: Ladder, _ s: LadderState, n: Int) -> some View {
        if let k = l.locked {
            let g = k.gameId.flatMap { art[$0] }
            GlowCard(left: Color(hex: g?.away.color), right: Color(hex: g?.home.color)) {
                VStack(alignment: .leading, spacing: 14) {
                    stepTag("Step \(n) · locked\(Models.date(l.lockedAt).map { " " + clock($0) } ?? "")", tier: k.tier)
                    stepHead(g, player: nil, league: k.league, name: Fmt.label(k.label),
                             sub: "\(k.matchup ?? "") · \(Fmt.dayTime(k.commenceTime))", price: k.price)
                    HStack(spacing: 14) {
                        StatCell(name: "ON IT", value: Marking.units(s.stack))
                        if let ev = k.ev {
                            Divider()
                            StatCell(name: "EDGE", value: Fmt.signed(ev), color: ev >= 0 ? .green : .red)
                        }
                        Divider()
                        StatCell(name: "A WIN MAKES", value: Marking.units(s.stack * BetMath.dec(k.price)), color: .green)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    Text("Place \(Marking.units(s.stack)) at \(k.book ?? "FanDuel") before it starts (\(Fmt.dayTime(k.commenceTime))), then confirm here.")
                        .font(.footnote).foregroundStyle(.secondary)
                    HStack(spacing: 8) {
                        // the betslip at the book (Nov 6): the lock's own link, else the live offer's (older locks carry none)
                        BookButton(book: k.book ?? atBk, link: k.fdUrl ?? offers.first { $0.offerId == k.offerId }?.fdUrl, size: 44)
                        Button { run { await store.ladderStep(l, stake: s.stack, locked: k) } } label: { Text("I placed it").frame(maxWidth: .infinity) }
                            .buttonStyle(SolidButton()).disabled(busy)
                        Button("Not this one") { run { await store.changeLadder(l, skip: k.offerId) } }.buttonStyle(SoftButton()).disabled(busy)
                    }
                }
            }
        } else {
            let before = LadderMath.endOfDay()
            let opts = LadderMath.options(offers, before: before, book: atBk).filter { !skipped.contains($0.offerId) }
            let held = LadderMath.suggest(offers, skipped: skipped, game: game.isEmpty ? nil : game, before: before, book: atBk)
            let g = held?.gameId.flatMap { art[$0] }
            GlowCard(left: Color(hex: g?.away.color), right: Color(hex: g?.home.color)) {
                VStack(alignment: .leading, spacing: 14) {
                    if let note = l.notice, note.hasPrefix("none:") {
                        notice("\(gameName(String(note.dropFirst(5))))'s news is in and BetLab has no +EV step there. Choose another game or any game.",
                               icon: "exclamationmark.circle")
                    }
                    if let note = l.notice, note.hasPrefix("missed:") {
                        notice("Your locked step (\(note.dropFirst(7))) started before it was placed. BetLab will lock the next one.",
                               icon: "clock.badge.exclamationmark")
                    }
                    if let o = held, let start = Models.date(o.commenceTime) {
                        let w = LadderMath.newsWindow(o.league)
                        stepTag("Step \(n) · holding", tier: o.tier.rawValue)
                        stepHead(g, player: o.player, league: o.league, name: Fmt.label(o.label),
                                 sub: "\(o.matchup ?? "") · \(Fmt.dayTime(o.commenceTime))", price: o.price)
                        HStack(spacing: 14) {
                            StatCell(name: "ON IT", value: Marking.units(s.stack))
                            Divider()
                            StatCell(name: "EDGE", value: Fmt.signed(o.ev), color: (o.ev ?? 0) >= 0 ? .green : .red)
                            Divider()
                            StatCell(name: "A WIN MAKES", value: Marking.units(s.stack * BetMath.dec(o.price)), color: .green)
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        Text("Nothing to place yet. BetLab locks \(game.isEmpty ? "the day's best step" : "this game's best step") once its game's news is in (around \(clock(start.addingTimeInterval(-w.hi * 60)))–\(clock(start.addingTimeInterval(-w.lo * 60)))) and alerts you. Until then it can change as the card is re-priced.")
                            .font(.footnote).foregroundStyle(.secondary)
                    } else {
                        stepTag("Step \(n) · looking", tier: nil)
                        Text(game.isEmpty
                             ? "Nothing on today's card fits a step at \(atBk) yet (a +EV pick or lean at −250 to +150). BetLab keeps looking through the day's pulls and locks the best one once its news is in."
                             : "Nothing in \(gameName(game)) fits a step at \(atBk) yet (a +EV pick or lean at −250 to +150). BetLab prices it again in its last pull before kickoff and locks its best step then, or tells you it has none.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    Hairline()
                    // the game the step comes from, as a full-width field on one line (Nov 6, Mike's screenshots: an inline
                    // picker beside "From" wrapped "Massachusetts Minutemen @ Boston College Eagles" onto three lines and the
                    // card cut it off)
                    VStack(alignment: .leading, spacing: 6) {
                        Text("STEP FROM").font(.caption2.weight(.bold)).foregroundStyle(.secondary)
                        Menu {
                            Picker("Step from", selection: Binding(get: { game }, set: { g in run { await store.changeLadder(l, game: .some(g)) } })) {
                                Text("Any game today").tag("")
                                ForEach(today) { g in
                                    let k = opts.filter { $0.gameId == g.gameId }.count
                                    Text("\(g.matchup ?? "") · \(Fmt.time(g.commenceTime)) · \(k > 0 ? "\(k) step\(k > 1 ? "s" : "") now" : "nothing yet")").tag(g.gameId)
                                }
                            }
                        } label: {
                            HStack(spacing: 8) {
                                Text(game.isEmpty ? "Any game today" : gameName(game)).lineLimit(1).truncationMode(.tail)
                                Spacer(minLength: 4)
                                if !game.isEmpty {
                                    Text(Fmt.time(today.first { $0.gameId == game }?.commenceTime)).foregroundStyle(.secondary).fixedSize()
                                }
                                Image(systemName: "chevron.up.chevron.down").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            }
                            .font(.subheadline.weight(.semibold)).foregroundStyle(.primary)
                            .padding(.horizontal, 14).frame(height: 44)
                            .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
                        }
                        .disabled(busy)
                    }
                    if let o = held {
                        Button("Not this one") { run { await store.changeLadder(l, skip: o.offerId) } }.buttonStyle(SoftButton(tall: false)).disabled(busy)
                    }
                    if !skipped.isEmpty {
                        Button("Show the \(skipped.count) you turned down again") { run { await store.changeLadder(l, unskip: true) } }
                            .font(.footnote.weight(.semibold)).tint(theme.accent).disabled(busy)
                    }
                }
            }
        }
        if !own.isEmpty && l.locked == nil {
            Menu {
                ForEach(own) { b in
                    Button("\(LadderMath.stepName(b))\(b.price.map { " \(Fmt.am($0))" } ?? "")") { run { await store.ladderStep(l, stake: s.stack, bet: b) } }
                }
            } label: {
                Text("Or make one of your open bets step \(n)").font(.footnote.weight(.semibold))
            }
            .tint(theme.accent).disabled(busy)
        }
    }

    private func notice(_ text: String, icon: String) -> some View {
        Label(text, systemImage: icon).font(.footnote).foregroundStyle(.orange)
    }

    private func stepTag(_ text: String, tier: String?) -> some View {
        HStack(spacing: 8) {
            Text(text.uppercased()).font(.caption2.weight(.bold)).foregroundStyle(.secondary)
            if let tier { TagView(text: tier == "pick" ? "Pick" : "Lean", color: tier == "pick" ? .green : .blue) }
        }
    }

    /// The bet itself: its picture (the player's photo, else the game's two logos), what it is, and its price.
    private func stepHead(_ g: GameLive?, player: String?, league: String?, name: String, sub: String, price: Double?) -> some View {
        HStack(alignment: .center, spacing: 12) {
            if let who = player, !who.isEmpty {
                PlayerFace(name: who, sport: league ?? "", size: 46)
            } else if let g = g?.reading {
                HStack(spacing: -6) {
                    TeamLogo(url: g.away.logo, name: g.away.name, size: 36, round: g.sport == "ufc")
                    TeamLogo(url: g.home.logo, name: g.home.name, size: 36, round: g.sport == "ufc")
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(name).font(.title3.weight(.heavy)).lineLimit(2).minimumScaleFactor(0.8)
                if !sub.isEmpty { Text(sub).font(.footnote).foregroundStyle(.secondary).lineLimit(2) }
            }
            Spacer(minLength: 4)
            if let price { Text(Fmt.am(price)).font(.system(.title2, design: .monospaced).weight(.bold)).foregroundStyle(.tint) }
        }
    }

    // MARK: the one that just ended

    private func endedCard(_ l: Ladder, _ s: LadderState) -> some View {
        let busted = s.phase == .busted, last = s.steps.last
        return GlowCard {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("YOUR LAST LADDER · \(Marking.units(l.startUnits)) TO \(Marking.units(l.targetUnits))").font(.caption2.weight(.bold)).foregroundStyle(.secondary)
                    Spacer(minLength: 4)
                    TagView(text: busted ? "Busted" : "Climbed", color: busted ? .red : .green)
                }
                Text(busted ? "It ended at step \(s.steps.count)" : "You climbed to \(Marking.units(LadderMath.shownStack(s.stack)))").font(.title2.weight(.heavy))
                if let b = last {
                    (Text(LadderMath.stepName(b)).bold() + Text(busted
                        ? "\(b.price.map { " \(Fmt.am($0))" } ?? "") lost with \(Marking.units(BetMath.stake(b))) on it. \(s.won) of \(s.steps.count) steps won · ended at \(Marking.units(LadderMath.shownStack(s.stack)))."
                        : " took it over the target. \(s.won) of \(s.steps.count) steps won."))
                        .font(.footnote).foregroundStyle(.secondary)
                }
                LadderTimeline(steps: s.steps, start: l.startUnits, target: nil)
            }
        }
    }

    // MARK: starting one

    private var startCard: some View {
        GlowCard {
            VStack(alignment: .leading, spacing: 12) {
                Text(ended == nil ? "No ladder going" : "Start another").font(.title2.weight(.heavy))
                if ended == nil { Text("Roll a small stack from bet to bet toward a target. One loss ends it.").font(.footnote).foregroundStyle(.secondary) }
                if !starting {
                    Button { withAnimation(.easeOut(duration: 0.2)) { starting = true } } label: { Text("Start a ladder").frame(maxWidth: .infinity) }
                        .buttonStyle(SolidButton())
                } else {
                    Hairline()
                    unitField("Start", "the stack you begin with, in units", "1", $from)
                    unitField("Target", "where the ladder ends, in units", "100", $to)
                    HStack(spacing: 10) {
                        Text("Book").font(.subheadline.weight(.semibold))
                        Spacer(minLength: 6)
                        ForEach(BooksOff.mine, id: \.self) { b in
                            Button { startBook = b } label: {
                                BookIcon(book: b, size: 32)
                                    .padding(3)
                                    .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).strokeBorder(theme.accent, lineWidth: startBook == b ? 2 : 0))
                                    .opacity(startBook == b ? 1 : 0.5)
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel(b)
                            .accessibilityAddTraits(startBook == b ? .isSelected : [])
                        }
                    }
                    if let a = Double(from), let b = Double(to), a > 0, b > a {
                        let n = LadderMath.stepsToTarget(a, b, price: 100)
                        RungTrack(won: 0, toGo: max(1, n))
                        Text("\(n) even-money wins in a row (\(LadderMath.stepsToTarget(a, b, price: -110)) at −110). At a fair coin flip that's about 1 in \(Int(pow(2, Double(n)))).")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    HStack(spacing: 8) {
                        Button { run { await store.startLadder(start: Double(from) ?? 0, target: Double(to) ?? 0, book: startBook) } } label: {
                            Text("Start at \(startBook)").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(SolidButton()).disabled(busy)
                        Button("Not now") { withAnimation(.easeOut(duration: 0.2)) { starting = false } }.buttonStyle(SoftButton())
                    }
                }
            }
        }
    }

    private func unitField(_ label: String, _ note: String, _ placeholder: String, _ text: Binding<String>) -> some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 1) {
                Text(label).font(.subheadline.weight(.semibold))
                Text(note).font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 6)
            TextField(placeholder, text: text).keyboardType(.decimalPad).multilineTextAlignment(.trailing)
                .font(.system(.body, design: .monospaced).weight(.semibold))
                .padding(.horizontal, 12).frame(width: 96, height: 40)
                .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
                .accessibilityLabel("\(label), in units")
        }
    }

    // MARK: past ladders, folded

    @ViewBuilder private var past: some View {
        let done = states.filter { $0.l.ladderId != live?.l.ladderId && $0.l.ladderId != ended?.l.ladderId }
        if !done.isEmpty {
            FoldCard(title: "Past ladders", note: "\(done.count)") {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(done.enumerated()), id: \.element.l.ladderId) { i, x in
                        let (l, s) = (x.l, x.s)
                        let open = openPast.contains(l.ladderId)
                        if i > 0 { Hairline() }
                        Button {
                            withAnimation(.easeOut(duration: 0.2)) { if open { openPast.remove(l.ladderId) } else { openPast.insert(l.ladderId) } }
                        } label: {
                            HStack(spacing: 8) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("\(Marking.units(l.startUnits)) to \(Marking.units(l.targetUnits))").font(.subheadline.weight(.bold)).foregroundStyle(.primary)
                                    Text("\(s.won) of \(s.steps.count) steps won · ended at \(Marking.units(LadderMath.shownStack(s.stack))) · \(Self.dated(l.createdAt))").font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer(minLength: 6)
                                Text(phaseName(s.phase)).font(.caption.weight(.semibold))
                                    .foregroundStyle(s.phase == .climbed ? Color.green : s.phase == .busted ? Color.red : Color.secondary)
                                Image(systemName: "chevron.down").font(.caption.weight(.semibold)).foregroundStyle(.tertiary).rotationEffect(.degrees(open ? 180 : 0))
                            }
                            .padding(.vertical, 10).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        if open { LadderTimeline(steps: s.steps, start: l.startUnits, target: nil).padding(.bottom, 10) }
                    }
                }
            }
        }
    }
}

/// The ladder as rungs: one segment per step, won in green, the one you are on in the accent, the rest to come.
struct RungTrack: View {
    let won: Int
    let toGo: Int
    @Environment(\.theme) private var theme

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<(won + toGo), id: \.self) { i in
                // the one you're on is outlined, not filled: in a green theme a filled accent read as a won step (Nov 6)
                if i == won {
                    Capsule().strokeBorder(theme.accent, lineWidth: 2).background(Capsule().fill(theme.accent.opacity(0.18))).frame(height: 8)
                } else {
                    Capsule().fill(i < won ? Color.green : Color(.systemFill)).frame(height: 6)
                }
            }
        }
        .frame(height: 8)
        .accessibilityElement()
        .accessibilityLabel("\(won) step\(won == 1 ? "" : "s") won, about \(toGo) to go")
    }
}

/// The climb as a timeline, newest on top: the target (when still ahead), each step with the stack after it, the start.
struct LadderTimeline: View {
    let steps: [MyBet]
    let start: Double
    let target: Double?
    @Environment(\.theme) private var theme

    private struct Row: Identifiable {
        let id: String
        let n: Int
        let bet: MyBet
        let after: Double?
    }

    private var rows: [Row] {
        var stack = start
        return steps.enumerated().map { i, b in
            if BetMath.isSettled(b) { stack += BetMath.profit(b) ?? 0; return Row(id: b.betId, n: i + 1, bet: b, after: LadderMath.shownStack(stack)) }
            return Row(id: b.betId, n: i + 1, bet: b, after: nil)
        }.reversed()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let target {
                line(first: true, last: false) { mark("flag.fill", Color(.systemGray3), ink: .white) } content: {
                    row("Target", nil, Marking.units(target), .secondary)
                }
            }
            ForEach(Array(rows.enumerated()), id: \.element.id) { i, r in
                let st = BetMath.status(r.bet)
                let tone: Color = st == "won" ? .green : st == "lost" ? .red : .secondary
                line(first: target == nil && i == 0, last: false) {
                    if r.after == nil { Circle().strokeBorder(theme.accent, lineWidth: 3).frame(width: 22, height: 22).background(theme.cardColor, in: Circle()) }
                    else { mark(st == "won" ? "checkmark" : st == "lost" ? "xmark" : "minus", st == "won" ? .green : st == "lost" ? .red : Color(.systemGray2), ink: st == "won" ? .black : .white) }
                } content: {
                    row("Step \(r.n)", "\(LadderMath.stepName(r.bet))\(r.bet.price.map { " \(Fmt.am($0))" } ?? "") · \(Marking.units(BetMath.stake(r.bet)))",
                        r.after.map { Marking.units($0) } ?? "in play", r.after == nil ? theme.accent : tone,
                        note: r.after == nil ? nil : BetMath.statusName(st))
                }
            }
            line(first: target == nil && rows.isEmpty, last: true) {
                Circle().fill(Color(.systemGray3)).frame(width: 10, height: 10).frame(width: 22, height: 22).background(theme.cardColor, in: Circle())
            } content: {
                row("Start", nil, Marking.units(start), .secondary)
            }
        }
    }

    /// One row on the rail: the marker over a line that runs up to the row above and down to the one below.
    private func line<M: View, C: View>(first: Bool, last: Bool, @ViewBuilder marker: () -> M, @ViewBuilder content: () -> C) -> some View {
        HStack(alignment: .center, spacing: 12) {
            marker().frame(width: 22)
            content()
        }
        .padding(.vertical, 9)
        .background(alignment: .leading) {
            VStack(spacing: 0) {
                Rectangle().fill(Color.primary.opacity(first ? 0 : 0.12))
                Rectangle().fill(Color.primary.opacity(last ? 0 : 0.12))
            }
            .frame(width: 2).padding(.leading, 10)
        }
    }

    private func mark(_ symbol: String, _ color: Color, ink: Color) -> some View {
        Image(systemName: symbol).font(.system(size: 10, weight: .heavy)).foregroundStyle(ink)
            .frame(width: 22, height: 22).background(color, in: Circle())
    }

    private func row(_ title: String, _ sub: String?, _ value: String, _ tone: Color, note: String? = nil) -> some View {
        HStack(alignment: .center, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.bold))
                if let sub { Text(sub).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
            }
            Spacer(minLength: 6)
            VStack(alignment: .trailing, spacing: 2) {
                Text(value).font(.system(.callout, design: .monospaced).weight(.bold)).foregroundStyle(tone)
                if let note { Text(note).font(.caption2.weight(.semibold)).foregroundStyle(.secondary) }
            }
        }
    }
}
