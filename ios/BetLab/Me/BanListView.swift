import SwiftUI

/// Settings > Ban list (Oct 25, web components/me/BanList.tsx): players and teams BetLab gives no bets on. Their games and
/// stats still show; their props and sides leave Home, game pages, the promo finder, the worker's tickets and pick alerts.
struct BanListView: View {
    @EnvironmentObject private var store: BetStore
    @State private var kind = "player"
    @State private var name = ""
    @State private var league: String?
    @State private var msg: String?
    @State private var busy = false

    /// Teams from the table that start like what's typed, for a tap (a picked team keeps its league).
    private var suggestions: [(league: String, name: String)] {
        let q = Live.plain(name)
        guard kind == "team", q.count >= 2 else { return [] }
        return Array(Bans.teamNames.filter { t in Live.plain(t.name).split(separator: " ").contains { $0.hasPrefix(q) } || Live.plain(t.name).hasPrefix(q) }.prefix(6))
    }

    var body: some View {
        List { Group {
            Section {
                if store.bans.isEmpty { Text("Nobody banned.").foregroundStyle(.secondary) }
                ForEach(store.bans) { b in
                    HStack {
                        Image(systemName: b.kind == "team" ? "shield.slash" : "person.fill.xmark").foregroundStyle(.red)
                        Text(b.name)
                        if let lg = b.league { Text(Bans.leagueNames[lg] ?? lg.uppercased()).font(.caption).foregroundStyle(.secondary) }
                    }
                    .swipeActions { Button("Remove", role: .destructive) { save(store.bans.filter { $0 != b }) } }
                }
            } header: {
                Text("Banned · \(store.bans.count)")
            } footer: {
                if !store.bans.isEmpty { Text("Swipe one to remove it.") }
            }
            Section {
                Picker("Ban a", selection: $kind) { Text("Player").tag("player"); Text("Team").tag("team") }
                    .pickerStyle(.segmented)
                    .onChange(of: kind) { league = nil }
                TextField(kind == "team" ? "New York Jets" : "Josh Allen", text: $name)
                    .textInputAutocapitalization(.words).autocorrectionDisabled()
                    .onChange(of: name) { msg = nil; if league != nil && !Bans.teamNames.contains(where: { $0.name == name }) { league = nil } }
                ForEach(suggestions, id: \.name) { t in
                    Button { name = t.name; league = t.league } label: {
                        HStack { Text(t.name); Spacer(); Text(Bans.leagueNames[t.league] ?? t.league).font(.caption).foregroundStyle(.secondary) }
                    }
                }
                Button(busy ? "Saving…" : "Add") { add() }.disabled(busy || name.trimmingCharacters(in: .whitespaces).isEmpty)
                if let msg { Text(msg).foregroundStyle(.red) }
            } header: {
                Text("Add")
            } footer: {
                Text("BetLab won't suggest bets on these: a player's props, a team's moneyline, spread or to-win, in picks, parlays, the promo finder and pick alerts. Totals aren't on anyone, so they stay. Shared with the web app.")
            }
        }.themedRows() }.themedList()
        .navigationTitle("Ban list")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func add() {
        let n = name.trimmingCharacters(in: .whitespaces)
        guard !n.isEmpty else { return }
        let known = kind == "team" ? Bans.teamNames.first { $0.name.lowercased() == n.lowercased() } : nil
        let b = Ban(kind: kind, name: known?.name ?? n, league: league ?? known?.league)
        name = ""; league = nil
        guard !store.bans.contains(where: { $0.id == b.id }) else { return }
        save(store.bans + [b])
    }

    private func save(_ list: [Ban]) {
        busy = true
        Task {
            msg = await store.setBans(list)
            busy = false
        }
    }
}
