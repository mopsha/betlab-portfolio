import SwiftUI

/// Record, Stats and Prices as one place (Me, reorganized Nov 5): the three screens of BetScreens.swift behind a switch
/// at the top, so Me has one way in. Each screen is drawn as it was.
struct RecordHub: View {
    enum Part: String, CaseIterable, Identifiable {
        case record = "Record", stats = "Stats", prices = "Prices"
        var id: String { rawValue }
    }
    @State private var show: Part

    init(start: Part = .record) { _show = State(initialValue: start) }

    var body: some View {
        Group {
            switch show {
            case .record: RecordScreen()
            case .stats: StatsScreen()
            case .prices: PricesScreen()
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                Picker("Show", selection: $show) { ForEach(Part.allCases) { Text($0.rawValue).tag($0) } }
                    .pickerStyle(.segmented).frame(width: 250)
            }
        }
    }
}

/// Reviews and Plan as one place (the owner's only): the Tuesday reviews and the shared to-do list.
struct ReviewsPlanView: View {
    @State private var show: String

    init(plan: Bool = false) { _show = State(initialValue: plan ? "plan" : "reviews") }

    var body: some View {
        Group {
            if show == "plan" { PlanView() } else { ReviewsView() }
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                Picker("Show", selection: $show) { Text("Reviews").tag("reviews"); Text("Plan").tag("plan") }
                    .pickerStyle(.segmented).frame(width: 200)
            }
        }
    }
}

/// Every badge, by kind: the ones closest first, then each group with what is earned and what is still locked.
struct BadgesSheet: View {
    let badges: [Badge]
    @Environment(\.dismiss) private var dismiss
    @Environment(\.theme) private var theme

    var body: some View {
        let next = Achievements.nextUp(badges, 3)
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if !next.isEmpty {
                        SectionTitle("Next up")
                        card(next)
                    }
                    ForEach(Achievements.groups, id: \.self) { g in
                        let list = badges.filter { $0.group == g }
                        if !list.isEmpty {
                            SectionTitle(g, note: "\(list.filter { $0.earned != nil }.count) of \(list.count)").padding(.top, 8)
                            card(list)
                        }
                    }
                    Text("Badges reward winning and beating the close, never betting more.")
                        .font(.footnote).foregroundStyle(.secondary).padding(.top, 4)
                }
                .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 28)
            }
            .background(theme.pageColor.ignoresSafeArea())
            .navigationTitle("Badges · \(badges.filter { $0.earned != nil }.count) of \(badges.count)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }

    private func card(_ list: [Badge]) -> some View {
        VStack(spacing: 0) {
            ForEach(Array(list.enumerated()), id: \.element.id) { i, b in
                if i > 0 { Divider() }
                row(b)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 2)
        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
    }

    private func row(_ b: Badge) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text(b.icon).font(.title2).grayscale(b.earned != nil ? 0 : 1).opacity(b.earned != nil ? 1 : 0.5)
                .frame(width: 40, height: 40).background(Color(.tertiarySystemFill), in: Circle())
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(b.title).font(.subheadline.weight(.semibold))
                Text(b.how).font(.footnote).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
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
            Spacer(minLength: 0)
        }
        .padding(.vertical, 11)
        .opacity(b.earned != nil ? 1 : 0.7)
    }
}
