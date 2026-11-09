import SwiftUI

/// What's searched in the app itself, your bets and the team list (web lib/search.ts, fixture tests/fixtures/search.json); games, fights and
/// players come from the database (search_app, migration 0036).
enum Search {
    static let least = 2
    private static func words(_ q: String) -> [String] { Live.plain(q).split(separator: " ").map(String.init) }

    /// Your bets with every word somewhere in their label, matchup or legs, newest first.
    static func bets(_ all: [MyBet], _ q: String, max: Int = 20) -> [MyBet] {
        let w = words(q)
        guard Live.plain(q).count >= least else { return [] }
        return all.filter { b in
            let t = Live.plain(([b.label, b.matchup] + (b.legs ?? []).map(Optional.some)).compactMap { $0 }.joined(separator: " "))
            return w.allSatisfy { t.contains($0) }
        }.sorted { $0.placedAt > $1.placedAt }.prefix(max).map { $0 }
    }

    /// Teams by name (every word) or exact code, in the list's own order by sport.
    static func teams(_ all: [String: [Bans.TeamRow]], _ q: String, max: Int = 12) -> [(sport: String, team: Bans.TeamRow)] {
        let w = words(q), code = q.trimmingCharacters(in: .whitespaces).uppercased()
        guard Live.plain(q).count >= least else { return [] }
        var out: [(sport: String, team: Bans.TeamRow)] = []
        for sport in all.keys.sorted() {
            for t in all[sport] ?? [] {
                let n = Live.plain(t.name)
                if t.abbr.contains(where: { $0.uppercased() == code }) || w.allSatisfy({ n.contains($0) }) { out.append((sport, t)) }
            }
        }
        return Array(out.prefix(max))
    }
}

extension Search {
    // ESPN's logo files use their own short codes for a few teams (web lib/wallet-view.ts ESPN_CODE)
    private static let espnCode = ["nhl:tbl": "tb", "nhl:lak": "la", "nhl:sjs": "sj", "nba:uta": "utah", "nba:nop": "no"]
    /// An NFL, NBA or NHL team's logo from its code; nil for the rest (their initials show).
    static func logo(_ sport: String, _ abbr: String?) -> String? {
        guard ["nfl", "nba", "nhl"].contains(sport), let a = abbr?.lowercased(), !a.isEmpty else { return nil }
        return "https://a.espncdn.com/i/teamlogos/\(sport)/500/\(espnCode["\(sport):\(a)"] ?? a).png"
    }
    /// A team named in full ("Buffalo Sabres"), or by its code, as its logo: the one NFL, NBA or NHL team it is (web teamMark).
    static func logo(named name: String) -> String? {
        let n = name.lowercased()
        let hits = Bans.teams.flatMap { lg, rows in rows.filter { $0.name.lowercased() == n || $0.abbr.contains(name.uppercased()) }.map { (lg, $0) } }
        guard hits.count == 1, let (lg, t) = hits.first else { return nil }
        return logo(lg, t.abbr.first)
    }
}

struct SearchHit: Decodable, Hashable {
    let kind: String
    let title: String
    let sport: String
    let at: String?
    let gameId: String?
}

/// Teams, players, fighters, games and your bets. A team or player opens your record with it; a game opens its page.
struct SearchView: View {
    @EnvironmentObject private var store: BetStore
    @State private var q = ""
    @State private var hits: [SearchHit] = []
    @State private var failed = false

    private var text: String { q.trimmingCharacters(in: .whitespaces) }
    private var teams: [(sport: String, team: Bans.TeamRow)] { Search.teams(Bans.teams, text) }
    private var bets: [MyBet] { Search.bets(store.bets, text) }
    private var players: [SearchHit] { hits.filter { $0.kind == "player" } }
    private var games: [SearchHit] { hits.filter { $0.kind == "game" } }

    var body: some View {
        List {
            if failed { Label("Search didn't answer. Try again.", systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
            if text.count >= Search.least && teams.isEmpty && players.isEmpty && games.isEmpty && bets.isEmpty {
                Text("Nothing found for \u{201C}\(text)\u{201D}.").foregroundStyle(.secondary)
            }
            if !teams.isEmpty {
                Section("Teams") {
                    ForEach(teams, id: \.team.name) { t in
                        CardTap(ref: CardRef(kind: .team, name: t.team.name, abbr: t.team.abbr.first), sport: t.sport) {
                            row(TeamLogo(url: Search.logo(t.sport, t.team.abbr.first), name: t.team.name, size: 40), t.team.name, Fmt.sports[t.sport] ?? t.sport)
                        }
                    }
                }
            }
            if !players.isEmpty {
                Section("Players") {
                    ForEach(players, id: \.self) { p in
                        CardTap(ref: CardRef(kind: .player, name: p.title), sport: p.sport) {
                            row(PlayerFace(name: p.title, sport: p.sport), p.title, Fmt.sports[p.sport] ?? p.sport)
                        }
                    }
                }
            }
            if !games.isEmpty {
                Section("Games") {
                    ForEach(games, id: \.self) { g in
                        if let id = g.gameId { NavigationLink { GameView(gameId: id) } label: { row(pair(g.title, g.sport), g.title, dated(g.at)) } }
                        else { row(pair(g.title, g.sport), g.title, dated(g.at)) }
                    }
                }
            }
            if !bets.isEmpty {
                Section("Your bets") {
                    ForEach(bets) { b in
                        row(pair(b.matchup, b.sport ?? b.league), (b.legs?.count ?? 0) > 1 ? Stats.betName(legs: b.legs, label: nil, price: b.price) : b.label ?? b.matchup ?? "",
                            dated(b.placedAt))
                    }
                }
            }
        }
        .themedRows().themedList()
        .navigationTitle("Search")
        .searchable(text: $q, placement: .navigationBarDrawer(displayMode: .always), prompt: "Teams, players, fighters, your bets")
        .task(id: text) {
            guard text.count >= Search.least else { hits = []; failed = false; return }
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            do { hits = try await store.api.rpc("search_app", ["q": text]); failed = false }
            catch is CancellationError {} catch { failed = true }
        }
    }

    private static let datedF: DateFormatter = {
        let f = DateFormatter(); f.timeZone = TimeZone(identifier: "America/New_York"); f.locale = Locale(identifier: "en_US"); f.dateFormat = "EEE, MMM d, h:mm a"
        return f
    }()
    /// Games weeks away: "Sat 8:00 PM" alone doesn't say which Saturday.
    private func dated(_ iso: String?) -> String { Models.date(iso).map(Self.datedF.string(from:)) ?? "" }

    /// A row that leads with its picture (web SearchBox, Nov 6): a team's logo, a player's photo, a game's two logos.
    private func row(_ art: some View, _ title: String, _ sub: String) -> some View {
        HStack(spacing: 12) {
            art.frame(width: 46, alignment: .leading)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.semibold)).lineLimit(1)
                if !sub.isEmpty { Text(sub).font(.caption).foregroundStyle(.secondary) }
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 2)
    }

    /// A game's or bet's two teams, overlapping: their logos, or their initials (soccer, college).
    private func pair(_ matchup: String?, _ sport: String?) -> some View {
        let sides = (matchup ?? "").components(separatedBy: " @ ").flatMap { $0.components(separatedBy: " vs ") }
            .map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }.prefix(2)
        return HStack(spacing: -8) {
            ForEach(Array(sides.enumerated()), id: \.offset) { _, n in
                TeamLogo(url: Search.logo(named: n), name: n, size: 24)
                    .frame(width: 30, height: 30).background(Color(.tertiarySystemFill), in: Circle()).clipShape(Circle())
            }
        }
    }
}
