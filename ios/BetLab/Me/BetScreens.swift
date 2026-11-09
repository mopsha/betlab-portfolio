import SwiftUI

// Record, Stats, Ladder and Prices as screens of their own (the overhaul, Nov 4): they were segments of My bets, which
// is now Live (open and settled bets only); Me links to each. The sections are what those segments showed. They read
// the store's graded bets: a bet the live tracker has settled joins them once the worker grades it.

/// Which bets are "your record": real bets only once real money started, paper apart (BetMath.recordBets).
@MainActor private func recordSplit(_ store: BetStore) -> (useReal: Bool, counted: [MyBet], paper: [MyBet]) {
    BetMath.recordBets(store.bets, realMode: store.isReal)
}

private func unitTone(_ x: Double?) -> Color? { guard let x else { return nil }; return x > 0 ? .green : x < 0 ? .red : nil }

/// The record by market and by book, missed bets, the promos ledger, paper, and what the numbers mean.
struct RecordScreen: View {
    @EnvironmentObject private var store: BetStore
    @State private var missedPicks: [PaperPick] = []

    var body: some View {
        let split = recordSplit(store), hasReal = split.useReal
        let rec = BetMath.record(split.counted)
        List { Group {
            Section(hasReal ? "Real money" : "By market") {
                if rec.total.bets > 0 { RecordTable(lines: rec.lines, total: rec.total, head: "Market") }
                else {
                    Text(hasReal ? "No real bet graded yet. Results land the morning after each game."
                         : "No record yet. It starts with your first graded bet.").font(.footnote).foregroundStyle(.secondary)
                }
            }
            MissedSection(picks: missedPicks)
            promos(split.counted)
            let byBook = BetMath.record(split.counted, by: BetMath.book)
            if byBook.total.bets > 0 {
                Section("By book\(hasReal ? " · real money" : "")") { RecordTable(lines: byBook.lines, total: byBook.total, head: "Book") }
            }
            let paper = BetMath.record(store.bets.filter { !$0.isReal })
            if hasReal && paper.total.bets > 0 {
                Section("Paper") { RecordTable(lines: paper.lines, total: paper.total, head: "Market") }
            }
            Section {
                DisclosureGroup("About these numbers") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Units are at the price you marked: a 1u bet at +120 that wins is +1.20u. A real bet counts its stake in units (1u unless you edit it); paper bets count 1u. Real money and paper are kept apart.")
                        Text("A bonus bet (turn on Bonus bet under Edit) is the book's credit: a win adds only its profit, a loss counts 0, and it stays out of today's 5u cap, the fun bucket and ROI.")
                        Text("CLV is how your price compares with the sharp closing price, the best sign a bet was good whatever the result. Beating the close on most bets matters more than the win-loss record over a few weeks. Parlays have no CLV.")
                    }
                    .font(.footnote).foregroundStyle(.secondary)
                }
            }
        }.themedRows() }.themedList()
        .navigationTitle("Record")
        .refreshable { await store.load() }
        // Missed bets: read from the list, which is always there (a section that starts empty never runs its task)
        .task(id: store.refreshTick) {
            if let p: [PaperPick] = try? await store.api.rows("paper_picks", .init(eq: [("tier", "pick"), ("current_rule", "true")])) {
                missedPicks = p
            }
        }
    }

    /// One Promos section (Oct 30; web app/bets "Promos"): bonus bets, boosts, and the finder's picks against what it expected.
    @ViewBuilder
    private func promos(_ counted: [MyBet]) -> some View {
        let bonus = BetMath.bonusSummary(counted)
        let boosted = BetMath.boostSummary(counted)
        let finder = BetMath.promoLedger(counted, unit: store.unit)
        if bonus.bets > 0 || boosted.bets > 0 {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    if bonus.bets > 0 {
                        Text("**Bonus bets** \(bonus.settled) settled\(bonus.bets > bonus.settled ? ", \(bonus.bets - bonus.settled) open" : ""): \(Marking.units(bonus.face)) of bonus turned into ")
                            + Text(BetMath.signedUnits(bonus.converted)).bold().foregroundColor(unitTone(bonus.converted) ?? .primary)
                            + Text(bonus.rate.map { " · kept **\(Int(($0 * 100).rounded()))%**" } ?? "")
                    }
                    if boosted.bets > 0 {
                        Text("**Profit boosts** \(boosted.settled) settled\(boosted.bets > boosted.settled ? ", \(boosted.bets - boosted.settled) open" : ""), \(boosted.won) won: ")
                            + Text(BetMath.signedUnits(boosted.units)).bold().foregroundColor(unitTone(boosted.units) ?? .primary)
                            + Text(" on \(Marking.units(boosted.staked)) staked; the boosts added ")
                            + Text(BetMath.signedUnits(boosted.fromBoost)).bold().foregroundColor(unitTone(boosted.fromBoost) ?? .primary)
                    }
                    if finder.settled > 0 {
                        Text("**From the finder** \(finder.settled) settled: ")
                            + Text(BetMath.signedUnits(finder.units)).bold().foregroundColor(unitTone(finder.units) ?? .primary)
                            + Text(" against \(BetMath.signedUnits(finder.expected)) expected")
                    }
                    Text("All included in the record above; bonus stakes never count in staked units or ROI. A bonus bet pays only its profit, so a fair +400 keeps about 80% of its face and a -110 favorite about 45%; a boost is worth most on a bet priced near the sharp fair price.")
                        .foregroundStyle(.secondary)
                    NavigationLink("Wallet") { PromosView() }
                }
                .font(.footnote)
            } header: { Text("Promos") }
        }
    }
}

/// Stats and achievements, player and team cards (StatsSections).
struct StatsScreen: View {
    @EnvironmentObject private var store: BetStore

    var body: some View {
        let split = recordSplit(store)
        List { Group {
            StatsSections(bets: split.counted, real: split.useReal)
        }.themedRows() }.themedList()
        .navigationTitle("Stats")
        .refreshable { await store.load() }
    }
}

/// Ladder challenges (LadderView): the climb on the theme's page, as the other rebuilt screens are.
struct LadderScreen: View {
    @EnvironmentObject private var store: BetStore
    @Environment(\.theme) private var theme

    var body: some View {
        ScrollView {
            // the floating tab bar covered "Stop ladder" at the bottom (Nov 6)
            LadderView().padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 96)
        }
        .scrollDismissesKeyboard(.interactively)
        .modifier(HardTopEdge())
        .background(theme.pageColor.ignoresSafeArea())
        .navigationTitle("Ladder")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await store.load() }
    }
}

/// The parlays you built and saved, and the book prices you typed.
struct PricesScreen: View {
    @EnvironmentObject private var store: BetStore

    var body: some View {
        let typed = store.quotes.sorted { ($0.quotedAt ?? "") > ($1.quotedAt ?? "") }
        List { Group {
            Section("Your own parlays") {
                if store.customs.isEmpty {
                    Text("Parlays you build and save show here with their grade and result.").font(.footnote).foregroundStyle(.secondary)
                }
                ForEach(store.customs.sorted { ($0.quotedAt ?? "") > ($1.quotedAt ?? "") }) { PriceRowView(q: $0, custom: true) }
            }
            Section("Prices you typed · \(typed.count)") {
                if typed.isEmpty {
                    Text("Type FanDuel's price into a parlay's price box and it lands here.").font(.footnote).foregroundStyle(.secondary)
                }
                ForEach(typed) { PriceRowView(q: $0, custom: false) }
            }
        }.themedRows() }.themedList()
        .navigationTitle("Prices")
        .refreshable { await store.load() }
    }
}

/// The record as a compact table: market, W–L, units, CLV (ROI and beat-close in a second line).
struct RecordTable: View {
    let lines: [RecordLine]
    let total: RecordLine
    let head: String

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 8) {
            GridRow {
                Text(head); Text("W–L").gridColumnAlignment(.trailing); Text("Units").gridColumnAlignment(.trailing)
                Text("ROI").gridColumnAlignment(.trailing); Text("CLV").gridColumnAlignment(.trailing)
            }
            .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
            ForEach(lines) { row($0, strong: false) }
            if lines.count > 1 { Divider(); row(total, strong: true) }
        }
        .font(.caption.monospacedDigit())
    }

    private func row(_ l: RecordLine, strong: Bool) -> some View {
        GridRow {
            VStack(alignment: .leading, spacing: 1) {
                Text(l.group).fontWeight(strong ? .semibold : .regular).lineLimit(2)
                if l.clvN > 0 { Text("beat close \(l.beat)/\(l.clvN)").font(.caption2).foregroundStyle(.secondary) }
            }
            Text("\(l.won)–\(l.lost)\(l.push > 0 ? "–\(l.push)" : "")")
            Text(BetMath.signedUnits(l.units)).foregroundStyle(l.units > 0 ? .green : l.units < 0 ? .red : .primary)
            Text(Fmt.signed(l.roi)).foregroundStyle((l.roi ?? 0) > 0 ? .green : (l.roi ?? 0) < 0 ? .red : .primary)
            Text(l.avgClv.map { Fmt.signed($0) } ?? "—").foregroundStyle((l.avgClv ?? 0) > 0 ? .green : (l.avgClv ?? 0) < 0 ? .red : .primary)
        }
    }
}

/// A typed price or a saved parlay: what, when, legs, price against fair, and EV.
struct PriceRowView: View {
    let q: Quote
    let custom: Bool

    var body: some View {
        let ev = q.pFair.flatMap { pf in q.price.map { pf * BetMath.dec($0) - 1 } }
        let status = (q.status ?? "open") == "open" ? nil : q.status
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(String((q.matchup ?? q.sgpId).split(separator: ":").first ?? "")).font(.footnote).lineLimit(2)
                Text("\(q.quotedAt.flatMap { Models.date($0) }.map { Fmt.shortDay($0) } ?? "") · \(q.legs?.count ?? q.nLegs ?? 0) legs\(q.grade.map { " · grade \($0)" } ?? "")\(q.sgpId.hasSuffix("~dk") ? " · DraftKings" : "")")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(Fmt.am(q.price)).font(.footnote.monospacedDigit().weight(.semibold))
                Text("fair \(Fmt.am(q.fairPrice)) · EV \(Fmt.signed(ev))").font(.caption2.monospacedDigit())
                    .foregroundStyle((ev ?? 0) > 0 ? .green : .secondary)
                if custom { Text(status ?? "open").font(.caption2).foregroundStyle(status == "won" ? .green : status == "lost" ? .red : .secondary) }
            }
        }
    }
}
