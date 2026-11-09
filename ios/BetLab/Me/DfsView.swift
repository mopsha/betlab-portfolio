import SwiftUI

/// A slate of the DFS optimizer (Nov 5, idea #38; written by the worker's dfs.py, migration 0040; web lib/dfs.ts).
struct DfsPlayer: Decodable, Hashable {
    let slot: String
    let id: String
    let name: String
    let team: String
    let salary: Double
    let proj: Double
    let basis: String
    let status: String?
}
struct DfsLineup: Decodable, Hashable {
    let salary: Double
    let proj: Double
    let players: [DfsPlayer]
}
struct DfsSlate: Decodable, Identifiable, Hashable {
    let slateId: String
    let league: String
    let label: String?
    let lockAt: String
    let games: Int?
    let priced: Int?
    let players: Int?
    let lineups: [DfsLineup]
    var id: String { slateId }
    var lock: Date { Models.date(lockAt) ?? .distantPast }

    /// Slates still open first, soonest lock first; then what locked in the last day (web dfsOrder).
    static func order(_ rows: [DfsSlate], now: Date = Date()) -> [DfsSlate] {
        rows.filter { $0.lock > now }.sorted { $0.lock < $1.lock }
            + rows.filter { $0.lock <= now && now.timeIntervalSince($0.lock) < 86400 }.sorted { $0.lock > $1.lock }
    }
}

/// Me > Extras > DFS lineups: the best DraftKings classic lineups at what the betting market expects of each player. Built by
/// the worker each pregame tick until the slate locks.
struct DfsView: View {
    @EnvironmentObject private var store: BetStore
    @State private var slates: [DfsSlate] = []
    @State private var loaded = false

    var body: some View {
        List {
            Section {
                Text("The most projected points under DraftKings' cap, from the betting market's prices. Not a pick: contests take about 15%, and this doesn't know who else is playing whom.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if loaded && slates.isEmpty {
                Section { Text("DFS lineups are off. DraftKings blocks BetLab's server from reading its salaries, so nothing is built.").foregroundStyle(.secondary) }
            }
            ForEach(slates) { s in
                let locked = s.lock <= Date()
                Section {
                    ForEach(Array(s.lineups.enumerated()), id: \.offset) { i, l in lineup(i, l) }
                    if !locked, let url = URL(string: "https://www.draftkings.com/lobby#/\(s.league.uppercased())") {
                        Link("Open DraftKings", destination: url)
                    }
                } header: {
                    Text("\(s.league.uppercased()) · \(s.label ?? "Main")")
                } footer: {
                    Text("\(locked ? "Locked" : "Locks") \(Promos.gameTime(s.lockAt)) · \(s.games ?? 0) game\(s.games == 1 ? "" : "s") · \(s.priced ?? 0) of \(s.players ?? 0) players priced by the market. * is his DraftKings average: the market has no lines for him.")
                }
            }
        }
        .themedRows().themedList()
        .navigationTitle("DFS lineups")
        .task(id: store.refreshTick) { await load() }
        .refreshable { await load() }
    }

    private func lineup(_ i: Int, _ l: DfsLineup) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Lineup \(i + 1)").font(.subheadline.weight(.semibold))
                Spacer()
                Text("\(String(format: "%.1f", l.proj)) proj · \(Self.money(l.salary))").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            }
            ForEach(l.players, id: \.id) { p in
                HStack(spacing: 8) {
                    Text(p.slot).font(.caption2).foregroundStyle(.secondary).frame(width: 34, alignment: .leading)
                    Text(p.name).font(.footnote).lineLimit(1)
                    Text(p.team + ((p.status ?? "").isEmpty ? "" : " · \(p.status!)")).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                    Spacer(minLength: 4)
                    Text(Self.money(p.salary)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    Text(String(format: "%.1f", p.proj) + (p.basis == "average" ? "*" : "")).font(.caption.monospacedDigit()).frame(width: 40, alignment: .trailing)
                }
                .accessibilityElement(children: .combine)
            }
        }
        .padding(.vertical, 2)
    }

    private static func money(_ n: Double) -> String { "$" + Int(n).formatted() }

    private func load() async {
        let rows: [DfsSlate] = (try? await store.api.rows("dfs_slates")) ?? slates
        slates = DfsSlate.order(rows)
        loaded = true
    }
}
