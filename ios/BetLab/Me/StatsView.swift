import SwiftUI
import Charts

/// My bets > Stats (web components/me/StatsView.tsx, Oct 24): personal stats (Mike's #40) and achievements (W29), from the
/// same bets as the Record tab. The logic is Stats.swift.
struct StatsSections: View {
    let bets: [MyBet]
    let real: Bool
    @EnvironmentObject private var store: BetStore

    var body: some View {
        let s = Stats.summary(bets)
        let badges = Achievements.all(bets)
        let got = badges.filter { $0.earned != nil }.count
        if s.total.bets == 0 {
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    Text("No stats yet").bold()
                    Text("Stats start with your first graded \(real ? "real " : "")bet.").font(.footnote).foregroundStyle(.secondary)
                }
            }
        } else {
            if let month = Wrapped.periods(bets).first {
                Section {
                    NavigationLink { WrappedView(bets: bets) } label: {
                        Label {
                            VStack(alignment: .leading) {
                                Text("Your \(Wrapped.periodName(month)) Wrapped").bold()
                                Text("Your month as a story: the big hit, the heartbreaker, your type").font(.caption).foregroundStyle(.secondary)
                            }
                        } icon: { Image(systemName: "gift") }
                    }
                }
            }
            Section {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        pill(real ? "Real P/L" : "Units", BetMath.signedUnits(s.total.units), color: tone(s.total.units))
                        pill("ROI", Fmt.signed(s.total.roi), color: tone(s.total.roi))
                        if let k = s.streaks.kind { pill("Streak", "\(s.streaks.n)\(k == "won" ? "W" : "L")", color: k == "won" ? .green : .red) }
                        pill("Best run", "\(s.streaks.bestWin)W")
                        pill("Badges", "\(got) of \(badges.count)")
                    }
                }
                .bareRow()
            }
            Section("Units over time") { UnitsChart(points: s.timeline) }
                .task(id: bets.count) { await store.loadCardTickets() }   // the parlays' games, for team cards
            if s.extremes.best != nil || s.extremes.worst != nil {
                Section {
                    if let b = s.extremes.best { OneBetRow(b: b, head: "Biggest win") }
                    if let b = s.extremes.worst { OneBetRow(b: b, head: "Worst loss") }
                }
            }
            CardShelfSection(title: "Your players", kind: .player, cards: Players.all(bets),
                             foot: "Gold: 70%+ of 3 or more graded legs hit; silver 50%+; bronze below. Tap a card for every leg.")
            TeamCardsSection(bets: bets)
            table("By sport", "Sport", s.bySport, s.total)
            table("Singles vs parlays", "Type", s.byType, s.total)
            table("By price", "Price", s.byBand, s.total)
            table("Cash, boosts and bonus bets", "Money", s.byMoney, s.total)
            table("By book", "Book", s.byBook, s.total)
            table("By day of the week", "Day", s.byWeekday, s.total)
            Section {
                if got > 0 { BadgeGrid(badges: badges.filter { $0.earned != nil }) }
                let next = Achievements.nextUp(badges)
                if !next.isEmpty {
                    Text("Next up").font(.caption.weight(.semibold)).foregroundStyle(.secondary).textCase(.uppercase).bareRow()
                    BadgeGrid(badges: next)
                }
                DisclosureGroup("All \(badges.count) badges, by kind") {
                    ForEach(Achievements.groups, id: \.self) { g in
                        let list = badges.filter { $0.group == g }
                        Text("\(g) · \(list.filter { $0.earned != nil }.count) of \(list.count)")
                            .font(.caption.weight(.semibold)).foregroundStyle(.secondary).textCase(.uppercase).padding(.top, 6)
                        BadgeGrid(badges: list)
                    }
                }
            } header: {
                Text("Achievements · \(got) of \(badges.count)")
            } footer: {
                Text("Units are at the price you took; ROI is on cash staked (bonus bets add profit, never stake). Badges reward winning and beating the close, never betting more.")
            }
        }
    }

    @ViewBuilder private func table(_ title: String, _ head: String, _ lines: [RecordLine], _ total: RecordLine) -> some View {
        if !lines.isEmpty { Section(title) { RecordTable(lines: lines, total: total, head: head) } }
    }

    private func tone(_ x: Double?) -> Color? { guard let x else { return nil }; return x > 0 ? .green : x < 0 ? .red : nil }

    private func pill(_ title: String, _ value: String, color: Color? = nil) -> some View {
        HStack(spacing: 4) {
            Text(title).foregroundStyle(.secondary)
            Text(value).bold().foregroundStyle(color ?? .primary)
        }
        .font(.caption)
        .padding(.horizontal, 10).padding(.vertical, 5)
        .background(Color.secondary.opacity(0.12), in: Capsule())
    }
}

/// Cumulative units by day as a line, zero marked; green above zero, red below (web UnitsChart).
private struct UnitsChart: View {
    let points: [Stats.Point]

    var body: some View {
        if points.count < 2 {
            Text("The chart starts after a second day with a settled bet.").font(.footnote).foregroundStyle(.secondary)
        } else {
            let last = points.last!, up = last.units >= 0
            VStack(alignment: .leading, spacing: 6) {
                Chart {
                    RuleMark(y: .value("Zero", 0)).lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4])).foregroundStyle(.secondary)
                    ForEach(points) { p in
                        AreaMark(x: .value("Day", day(p.day)), y: .value("Units", p.units))
                            .foregroundStyle((up ? Color.green : .red).opacity(0.15))
                        LineMark(x: .value("Day", day(p.day)), y: .value("Units", p.units))
                            .foregroundStyle(up ? Color.green : .red)
                    }
                    PointMark(x: .value("Day", day(last.day)), y: .value("Units", last.units)).foregroundStyle(up ? Color.green : .red)
                }
                .frame(height: 170)
                (Text("\(Fmt.longDay(day(points[0].day))) to \(Fmt.longDay(day(last.day))) · now ")
                 + Text(BetMath.signedUnits(last.units)).bold().foregroundColor(up ? .green : .red))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func day(_ d: String) -> Date { Models.date(d + "T16:00:00Z") ?? Date() }
}

/// Biggest win / Worst loss.
private struct OneBetRow: View {
    let b: MyBet
    let head: String

    var body: some View {
        let p = BetMath.profit(b)
        let custom = b.kind == "custom" || b.kind == "parlay"
        let name = custom ? "\(Stats.betName(legs: b.legs, label: nil, price: nil, n: Stats.legsOf(b))) · \((b.matchup ?? "").components(separatedBy: ":")[0])"
            : b.label.map(Fmt.label) ?? (b.matchup ?? "").components(separatedBy: ":")[0]
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 2) {
                Text(head).font(.caption).foregroundStyle(.secondary)
                Text(name).font(.subheadline.weight(.semibold)).lineLimit(2)
                Text("\(Fmt.am(b.price)) · \(Marking.units(b.stake)) · \(Fmt.dayTime(b.placedAt))").font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Text(BetMath.signedUnits(p)).bold().foregroundStyle((p ?? 0) > 0 ? .green : .red)
        }
    }
}

private struct BadgeGrid: View {
    let badges: [Badge]
    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible(), alignment: .top), GridItem(.flexible(), alignment: .top)], spacing: 10) {
            ForEach(badges) { BadgeTile(b: $0) }
        }
        .bareRow()
    }
}

/// One badge: earned ones in color with their day (and price for a win), locked ones dimmed with their progress.
private struct BadgeTile: View {
    let b: Badge

    var body: some View {
        let got = b.earned != nil
        VStack(alignment: .leading, spacing: 3) {
            Text(b.icon).font(.title2).grayscale(got ? 0 : 1)
            Text(b.title).font(.subheadline.weight(.semibold))
            Text(b.how).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Group {
                if let e = b.earned {
                    Text(Fmt.longDay(Models.date(e + "T16:00:00Z") ?? Date())
                         + (b.by.map { BetMath.status($0) == "won" && $0.price != nil ? " · \(Fmt.am($0.price))" : "" } ?? ""))
                        .foregroundStyle(.green)
                } else if let p = b.progress {
                    Text("\(p.have) of \(p.need)").foregroundStyle(.secondary)
                } else {
                    Text("Locked").foregroundStyle(.secondary)
                }
            }
            .font(.caption.weight(.medium))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
        .opacity(got ? 1 : 0.55)
    }
}
