import SwiftUI

// Player cards (Mike's W21, Oct 24), from web/lib/players.ts and components/games/PlayerCards.tsx: the players you bet on
// most, each with your record on them. Every player prop leg in your bets (parsed as the live tracker reads labels),
// matched in order to the bet's graded leg results, so a player twice in one parlay or in two parlays counts each time.
// Headshots from ESPN's site search by name (web lib/headshots.ts). **Change both together.**

struct PlayerCard: Identifiable {
    struct Leg { let label: String; let stat: String; let result: String; let day: String; let betId: String
                 var game: String? = nil }   // a team card's game leg (BTTS, a total) names its matchup
    let key: String
    var name: String
    var sport: String
    var legs: [Leg] = []
    var won = 0, lost = 0, open = 0
    var hitRate: Double?
    var topStat: String?
    var bets = 0
    var units = 0.0
    var id: String { key }
    /// gold 70%+, silver 50%+, else bronze, on 3+ graded legs; none before
    var tier: String? {
        guard won + lost >= 3, let h = hitRate else { return nil }
        return h >= 0.7 ? "gold" : h >= 0.5 ? "silver" : "bronze"
    }
}

enum Players {
    private static let statName = ["td": "touchdowns", "goal_or_assist": "goal or assist"]

    /// Every player leg in a bet, with its graded result (in order: repeated labels each get their own).
    static func legs(_ b: MyBet) -> [(player: String, leg: PlayerCard.Leg)] {
        let labels = !(b.legs ?? []).isEmpty ? b.legs! : b.label.map { [$0] } ?? []
        let results = b.legResults ?? []
        var used: Set<Int> = []
        let settled = BetMath.isSettled(b), s = BetMath.status(b)
        var out: [(String, PlayerCard.Leg)] = []
        for label in labels {
            let i = results.indices.first { !used.contains($0) && results[$0].leg == label }
            if let i { used.insert(i) }
            let player: String, stat: String
            switch Live.parseLeg(label) {
            case .prop(let p, let st, _, _, _)?: (player, stat) = (p, st)
            case .td(let p, _)?: (player, stat) = (p, statName["td"]!)
            case .goalOrAssist(let p)?: (player, stat) = (p, statName["goal_or_assist"]!)
            default: continue
            }
            let result = Self.result(i.map { results[$0].result }, settled: settled, legs: labels.count, status: s)
            out.append((player, PlayerCard.Leg(label: label, stat: stat, result: result, day: String(b.placedAt.prefix(10)), betId: b.betId)))
        }
        return out
    }

    /// A leg's result from its graded result; a single bet's leg takes the bet's own once it's settled.
    static func result(_ r: String?, settled: Bool, legs: Int, status: String) -> String {
        r == "won" || r == "lost" ? r! : r == "void" || r == "push" ? "void"
            : settled && legs == 1 && (status == "won" || status == "lost") ? status : "open"
    }

    /// One leg on a card, with who it's about and the bet it came from (players here, teams in Cards.swift).
    struct Entry { let key: String; let name: String; let sport: String; let leg: PlayerCard.Leg; let bet: MyBet }

    /// Cards from entries, most-bet first (ties: the better hit rate, then the name). `min` legs to make the list. A
    /// bet's units count once per card, however many of its legs are on it (web lib/players.ts `tally`).
    static func tally(_ entries: [Entry], min: Int = 2) -> [PlayerCard] {
        var order: [String] = [], by: [String: PlayerCard] = [:], betIds: [String: Set<String>] = [:], stats: [String: [String: Int]] = [:]
        for e in entries {
            let key = e.key, l = e.leg, b = e.bet
            if by[key] == nil { order.append(key); by[key] = PlayerCard(key: key, name: e.name, sport: e.sport) }
            if by[key]!.sport == "Multi-sport" && e.sport != "Multi-sport" { by[key]!.sport = e.sport }
            by[key]!.legs.append(l)
            if l.result == "won" { by[key]!.won += 1 } else if l.result == "lost" { by[key]!.lost += 1 } else if l.result == "open" { by[key]!.open += 1 }
            stats[key, default: [:]][l.stat, default: 0] += 1
            if !(betIds[key]?.contains(b.betId) ?? false) {
                betIds[key, default: []].insert(b.betId)
                by[key]!.bets += 1
                if BetMath.isSettled(b) { by[key]!.units += BetMath.profit(b) ?? 0 }
            }
        }
        return order.compactMap { k -> PlayerCard? in
            guard var p = by[k], p.legs.count >= min else { return nil }
            p.hitRate = p.won + p.lost > 0 ? Double(p.won) / Double(p.won + p.lost) : nil
            p.topStat = stats[k]?.sorted { $0.value > $1.value }.first?.key
            p.legs.sort { $0.day > $1.day }
            return p
        }
        .sorted { a, b in
            a.legs.count != b.legs.count ? a.legs.count > b.legs.count
                : (a.hitRate ?? -1) != (b.hitRate ?? -1) ? (a.hitRate ?? -1) > (b.hitRate ?? -1) : a.name < b.name
        }
    }

    /// Your players, most-bet first (ties: the better hit rate, then the name). `min` legs to make the list.
    static func all(_ bets: [MyBet], min: Int = 2) -> [PlayerCard] {
        tally(bets.flatMap { b in legs(b).map { Entry(key: Live.normName($0.player), name: $0.player, sport: Stats.sportOf(b), leg: $0.leg, bet: b) } }, min: min)
    }

    /// What ESPN's search knows about a player: headshot, team (name, short name, color, logo), jersey, position.
    struct Headshot { var url: String?; var team: String?; var teamShort: String? = nil; var color: String? = nil
                      var logo: String? = nil; var jersey: String? = nil; var position: String? = nil }

    /// A player's headshot and team from ESPN's search, preferring the bet's league; cached a day. A miss: all nil.
    static func headshot(_ name: String, sport: String) async -> Headshot {
        let q = name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? name
        guard let j = await ESPN.shared.get("https://site.web.api.espn.com/apis/common/v3/search?query=\(q)&limit=5&type=player", ttl: 86_400)
        else { return Headshot() }
        let fits: ((JSON) -> Bool)? = {
            switch sport {
            case "NBA": return { $0["league"].string == "nba" }
            case "NFL": return { $0["league"].string == "nfl" }
            case "NHL": return { $0["league"].string == "nhl" }
            case "WNBA": return { $0["league"].string == "wnba" }
            case "Soccer": return { $0["sport"].string == "soccer" }
            default: return nil
            }
        }()
        let items = j["items"].array
        guard let hit = fits.map({ f in items.first(where: f) }) ?? items.first else { return Headshot() }
        let t = hit["teamRelationships"].array.first { !$0["core"].isNull || $0["displayName"].string != nil } ?? .null
        let core = t["core"]
        return Headshot(url: hit["headshot"]["href"].string, team: core["displayName"].string ?? t["displayName"].string,
                        teamShort: core["shortDisplayName"].string, color: Live.teamColor(core["color"].string, core["alternateColor"].string),
                        logo: core["logos"][0]["href"].string, jersey: hit["jersey"].string, position: hit["position"]["abbreviation"].string)
    }

    /// Won-lost by stat, the most-bet first.
    static func byStat(_ p: PlayerCard) -> [(stat: String, won: Int, lost: Int, open: Int)] {
        var order: [String] = [], m: [String: (Int, Int, Int)] = [:]
        for l in p.legs {
            if m[l.stat] == nil { order.append(l.stat); m[l.stat] = (0, 0, 0) }
            if l.result == "won" { m[l.stat]!.0 += 1 } else if l.result == "lost" { m[l.stat]!.1 += 1 } else if l.result == "open" { m[l.stat]!.2 += 1 }
        }
        return order.map { (stat: $0, won: m[$0]!.0, lost: m[$0]!.1, open: m[$0]!.2) }
            .sorted { ($0.won + $0.lost + $0.open) > ($1.won + $1.lost + $1.open) }
    }
}

/// A row of trading cards on Stats (redesigned Oct 25, Mike: "it can be cooler maybe organized better"): sport chips,
/// then the cards in a row you swipe through, most-bet first; a tap opens the card's whole history. "Your players" and,
/// since Oct 25, "Your teams" (Cards.swift).
struct CardShelfSection: View {
    let title: String
    let kind: CardRef.Kind
    let cards: [PlayerCard]
    let foot: String
    @State private var shots: [String: Players.Headshot] = [:]
    @State private var sport: String?
    @State private var open: PlayerCard?
    private static let shown = 20

    var body: some View {
        let all = cards
        let sports = all.reduce(into: [String]()) { if !$0.contains($1.sport) { $0.append($1.sport) } }
        let list = Array(all.filter { sport == nil || $0.sport == sport }.prefix(Self.shown))
        if !all.isEmpty {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    if sports.count > 1 {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                chip("All", sport == nil) { sport = nil }
                                ForEach(sports, id: \.self) { s in chip(s, sport == s) { sport = s } }
                            }
                        }
                    }
                    ScrollView(.horizontal, showsIndicators: false) {
                        LazyHStack(spacing: 12) {
                            ForEach(list) { p in
                                Button { open = p } label: { TradingCard(p: p, shot: shots[p.key], kind: kind) }.buttonStyle(.plain)
                            }
                        }
                        .padding(.vertical, 6)
                    }
                    .scrollClipDisabled()
                }
                .bareRow()
            } header: {
                Text("\(title) · \(all.count)")
            } footer: {
                Text(foot)
            }
            .task(id: all.map(\.key).joined(separator: ",")) {
                await withTaskGroup(of: (String, Players.Headshot).self) { g in
                    for p in all.prefix(40) where shots[p.key] == nil { g.addTask { (p.key, await Cards.look(kind, p.name, sport: p.sport)) } }
                    for await (k, h) in g { shots[k] = h }
                }
            }
            .sheet(item: $open) { p in CardDetail(kind: kind, name: p.name, p: p, shot: shots[p.key]) }
        }
    }

    private func chip(_ t: String, _ on: Bool, _ action: @escaping () -> Void) -> some View {
        Button(t, action: action).font(.caption.weight(.semibold))
            .padding(.horizontal, 12).padding(.vertical, 5)
            .background(on ? Color.accentColor.opacity(0.2) : Color.secondary.opacity(0.12), in: Capsule())
            .foregroundStyle(on ? Color.accentColor : .primary).buttonStyle(.plain)
    }
}

/// The foil of a tier: gold, silver, bronze.
private func tierFoil(_ tier: String?) -> [Color]? {
    switch tier {
    case "gold": [Color(hex: "#f7e08a")!, Color(hex: "#e2b13c")!, Color(hex: "#a8781c")!, Color(hex: "#f7e08a")!]
    case "silver": [Color(hex: "#f2f5f8")!, Color(hex: "#a9b4c2")!, Color(hex: "#6d7886")!, Color(hex: "#f2f5f8")!]
    case "bronze": [Color(hex: "#e9b48c")!, Color(hex: "#b9784a")!, Color(hex: "#7a4526")!, Color(hex: "#e9b48c")!]
    default: nil
    }
}

/// One player as a trading card: the team's colors and logo, the headshot, jersey and position, the hit rate as a ring,
/// the record, the last legs, and the tier's foil edge.
struct TradingCard: View {
    let p: PlayerCard
    let shot: Players.Headshot?
    var kind: CardRef.Kind = .player

    var body: some View {
        let team = Color(hex: shot?.color) ?? .gray
        let foil = tierFoil(p.tier)
        VStack(spacing: 0) {
            ZStack(alignment: .bottom) {
                LinearGradient(colors: [team, team.opacity(0.55)], startPoint: .topLeading, endPoint: .bottomTrailing)
                if kind == .player, let l = shot?.logo, let u = URL(string: l) {
                    AsyncImage(url: u) { $0.resizable().scaledToFit() } placeholder: { Color.clear }
                        .frame(width: 120, height: 120).opacity(0.18).offset(x: 40, y: -20)
                }
                if let u = shot?.url.flatMap(URL.init(string:)) {
                    if kind == .team {      // a logo on a white disc, as the scoreboard shows them (a red crest on red reads)
                        AsyncImage(url: u) { $0.resizable().scaledToFit() } placeholder: { Color.clear }
                            .frame(width: 64, height: 64).padding(12).background(.white.opacity(0.92), in: Circle())
                            .shadow(color: .black.opacity(0.25), radius: 5, y: 2)
                            .frame(maxHeight: .infinity)
                    } else {
                        AsyncImage(url: u) { $0.resizable().scaledToFit() } placeholder: { Color.clear }.frame(height: 118)
                    }
                } else {
                    Text(p.name.split(separator: " ").compactMap(\.first).prefix(2).map(String.init).joined().uppercased())
                        .font(.system(size: 40, weight: .black, design: .rounded)).foregroundStyle(.white.opacity(0.8))
                        .frame(maxHeight: .infinity)
                }
                VStack {
                    HStack(alignment: .top) {
                        if let j = shot?.jersey {
                            Text("#\(j)").font(.system(size: 18, weight: .black, design: .rounded)).foregroundStyle(.white)
                        }
                        Spacer()
                        if let t = p.tier, let foil {
                            Text(t.uppercased()).font(.system(size: 9, weight: .black)).tracking(1)
                                .foregroundStyle(.black.opacity(0.8))
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(LinearGradient(colors: foil, startPoint: .leading, endPoint: .trailing), in: Capsule())
                        }
                    }
                    Spacer()
                }
                .padding(8)
            }
            .frame(height: 128)
            .clipped()
            VStack(alignment: .leading, spacing: 6) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(p.name).font(.subheadline.weight(.heavy)).lineLimit(1).minimumScaleFactor(0.8)
                    Text(kind == .team ? p.sport : [shot?.teamShort ?? shot?.team ?? p.sport, shot?.position].compactMap { $0 }.joined(separator: " · "))
                        .font(.caption2.weight(.semibold)).foregroundStyle(.secondary).lineLimit(1)
                }
                HStack(alignment: .center, spacing: 10) {
                    HitRing(rate: p.hitRate)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(p.won)–\(p.lost)").font(.system(.headline, design: .rounded).weight(.heavy)).monospacedDigit()
                        Text(p.topStat ?? "").font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                HStack(spacing: 3) {
                    ForEach(Array(p.legs.prefix(8).enumerated()), id: \.offset) { _, l in
                        Capsule().fill(l.result == "won" ? Color.green : l.result == "lost" ? .red : l.result == "void" ? .secondary : Color(.systemGray4))
                            .frame(width: 12, height: 5)
                    }
                }
                if p.won + p.lost > 0 {
                    Text(BetMath.signedUnits(p.units)).font(.caption.weight(.bold)).monospacedDigit()
                        .foregroundStyle(p.units > 0 ? .green : p.units < 0 ? .red : .secondary)
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(width: 168, height: 262, alignment: .top)
        .themedCard(radius: 18)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(
            RoundedRectangle(cornerRadius: 18).strokeBorder(
                foil.map { AnyShapeStyle(AngularGradient(colors: $0, center: .center)) } ?? AnyShapeStyle(Color.secondary.opacity(0.2)),
                lineWidth: foil == nil ? 1 : 3)
        )
        .shadow(color: (foil?[1] ?? .black).opacity(foil == nil ? 0.08 : 0.35), radius: foil == nil ? 6 : 10, y: 4)
    }
}

/// The hit rate as a ring: green at 50% or better, orange below (Mike, Oct 25: in the team's color a red team's 100%
/// looked like a loss).
struct HitRing: View {
    let rate: Double?
    var size: CGFloat = 46
    var body: some View {
        let tone: Color = (rate ?? 0) >= 0.5 ? .green : .orange
        ZStack {
            Circle().stroke(Color.secondary.opacity(0.2), lineWidth: size * 0.11)
            Circle().trim(from: 0, to: rate ?? 0).stroke(rate == nil ? Color.clear : tone, style: StrokeStyle(lineWidth: size * 0.11, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text(rate.map { "\(Int(($0 * 100).rounded()))%" } ?? "—").font(.system(size: size * 0.26, weight: .heavy, design: .rounded))
        }
        .frame(width: size, height: size)
    }
}

/// A player's or team's whole story: the card's header large, the numbers, won-lost by stat (a team's: by market), and
/// every leg, newest first; a team's game legs name their game. `p` nil: no bets with them yet.
struct CardDetail: View {
    let kind: CardRef.Kind
    let name: String
    let p: PlayerCard?
    let shot: Players.Headshot?
    var loading = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let team = Color(hex: shot?.color) ?? .gray
        NavigationStack {
            List { Group {
                Section {
                    ZStack(alignment: .bottomLeading) {
                        LinearGradient(colors: [team, team.opacity(0.5)], startPoint: .topLeading, endPoint: .bottomTrailing)
                        if let u = shot?.url.flatMap(URL.init(string:)) {
                            if kind == .team {
                                AsyncImage(url: u) { $0.resizable().scaledToFit() } placeholder: { Color.clear }
                                    .frame(width: 92, height: 92).padding(16).background(.white.opacity(0.92), in: Circle())
                                    .padding(.trailing, 16).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
                            } else {
                                AsyncImage(url: u) { $0.resizable().scaledToFit() } placeholder: { Color.clear }
                                    .frame(height: 170).frame(maxWidth: .infinity, alignment: .trailing)
                            }
                        }
                        VStack(alignment: .leading, spacing: 2) {
                            if let j = shot?.jersey { Text("#\(j)").font(.system(size: 30, weight: .black, design: .rounded)) }
                            Text(p?.name ?? name).font(.title2.weight(.heavy))
                            Text(kind == .team ? p?.sport ?? "" : [shot?.team ?? p?.sport, shot?.position].compactMap { $0 }.joined(separator: " · "))
                                .font(.footnote.weight(.semibold))
                        }
                        .foregroundStyle(.white).shadow(radius: 4).padding(14)
                    }
                    .frame(height: 190)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .listRowInsets(EdgeInsets()).listRowBackground(Color.clear)
                }
                if let p {
                    Section {
                        HStack {
                            HitRing(rate: p.hitRate, size: 64)
                            Spacer()
                            stat("\(p.won)–\(p.lost)", p.open > 0 ? "legs · \(p.open) open" : "legs")
                            Spacer()
                            stat("\(p.bets)", p.bets == 1 ? "bet" : "bets")
                            Spacer()
                            stat(p.won + p.lost > 0 ? BetMath.signedUnits(p.units) : "—", "units", color: p.units > 0 ? .green : p.units < 0 ? .red : nil)
                        }
                    }
                    Section(kind == .team ? "By market" : "By stat") {
                        ForEach(Players.byStat(p), id: \.stat) { s in
                            HStack {
                                Text(s.stat.prefix(1).uppercased() + s.stat.dropFirst())
                                Spacer()
                                Text("\(s.won)–\(s.lost)\(s.open > 0 ? " · \(s.open) open" : "")").monospacedDigit().foregroundStyle(.secondary)
                            }
                        }
                    }
                    Section("Every leg · \(p.legs.count)") {
                        ForEach(Array(p.legs.enumerated()), id: \.offset) { _, l in
                            HStack(spacing: 10) {
                                Image(systemName: l.result == "won" ? "checkmark.circle.fill" : l.result == "lost" ? "xmark.circle.fill" : l.result == "void" ? "minus.circle.fill" : "circle")
                                    .foregroundStyle(l.result == "won" ? .green : l.result == "lost" ? .red : .secondary)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(Fmt.label(l.label)).font(.subheadline)
                                    if let g = l.game { Text(g).font(.caption).foregroundStyle(.secondary) }
                                }
                                Spacer()
                                Text(Fmt.longDay(Models.date(l.day + "T16:00:00Z") ?? Date())).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                } else {
                    Section {
                        if loading { HStack { ProgressView(); Text("Loading your record…").foregroundStyle(.secondary) } }
                        else { Text("No bets with \(kind == .team ? "this team" : "this player") yet.").foregroundStyle(.secondary) }
                    }
                }
            }.themedRows() }.themedList()
            .navigationTitle(p?.name ?? name).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() }.foregroundStyle(.tint) } }
        }
    }

    private func stat(_ v: String, _ label: String, color: Color? = nil) -> some View {
        VStack(spacing: 2) {
            Text(v).font(.system(.title3, design: .rounded).weight(.heavy)).monospacedDigit().foregroundStyle(color ?? .primary)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
    }
}
