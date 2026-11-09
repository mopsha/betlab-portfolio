import SwiftUI

// Team cards and one card for any picture (Mike, Oct 25: "add cards for teams", and a tap on a leg's picture shows his
// record with that player or team), from web lib/cards.ts and components/games/Cards.tsx. **Change both together.** A team's
// legs: its moneyline and spread, and the game legs it can sink or carry, both teams to score and the totals, which
// count for both sides ("teams can also frick us on btts or over totals"). Each bet's games come from the live
// tracker's grouping (Live.groups), so a ticket's legs land on the right game. UFC fights have no teams.

/// What a picture points at: a player by name, or a team by its name (and code, as ESPN shows it).
struct CardRef: Identifiable, Hashable {
    enum Kind: String { case player, team }
    let kind: Kind
    let name: String
    var abbr: String? = nil
    var id: String { "\(kind.rawValue):\(name)" }
}

enum Cards {
    private static let stat = ["ml": "moneyline", "spread": "spread", "total": "total", "btts": "both teams to score"]

    /// A team's full name: NFL, NBA and NHL legs and matchups often carry codes ("OTT to win", "FLA @ CHI").
    static func fullName(_ sport: String?, _ n: String) -> String {
        let t = n.trimmingCharacters(in: .whitespaces)
        return Bans.teams[sport ?? ""]?.first { $0.abbr.contains(t) }?.name ?? t
    }

    private static func sides(_ matchup: String) -> [String] {
        let parts = matchup.components(separatedBy: " @ ").count == 2 ? matchup.components(separatedBy: " @ ")
            : matchup.range(of: #" vs\.? | v "#, options: .regularExpression).map { [String(matchup[..<$0.lowerBound]), String(matchup[$0.upperBound...])] } ?? []
        return parts.count == 2 ? parts.map { $0.trimmingCharacters(in: .whitespaces) } : []
    }

    /// A bet's games and the legs on each, as the live tracker groups them (a saved bet's games keep camelCased keys).
    static func groups(_ b: MyBet, tickets: [String: JSON]) -> [LiveGroup] {
        let games: JSON? = b.games?.array.isEmpty == false
            ? .array(b.games!.array.map { g in .object(["matchup": g["matchup"], "legs": g["legs"],
                                                        "game_ref": g["game_ref"].isNull ? g["gameRef"] : g["game_ref"]]) })
            : nil
        let row = LiveBetRow(bet_id: b.betId, kind: b.kind, sgp_id: b.sgpId, label: b.label, legs: b.legs, matchup: b.matchup,
                             league: b.league, sport: b.sport, games: games, pick_commence_time: b.pickCommenceTime,
                             ticket_commence_time: b.ticketCommenceTime, placed_at: b.placedAt, game_start: b.gameStart)
        return Live.groups(row, tickets: tickets)
    }

    /// Every team leg in a bet: (team, leg), in order, with its graded result.
    static func teamLegs(_ b: MyBet, _ grps: [LiveGroup]) -> [Players.Entry] {
        let results = b.legResults ?? []
        var used: Set<Int> = []
        let settled = BetMath.isSettled(b), s = BetMath.status(b)
        let all = grps.reduce(0) { $0 + $1.legs.count }
        var out: [Players.Entry] = []
        for g in grps {
            for label in g.legs {
                let i = results.indices.first { !used.contains($0) && results[$0].leg == label }
                if let i { used.insert(i) }
                if g.sport == "ufc" { continue }
                let names: [String], kind: String
                switch Live.parseLeg(label) {
                case .ml(let t)?: (names, kind) = ([t], "ml")
                case .spread(let t, _)?: (names, kind) = ([t], "spread")
                case .total?: (names, kind) = (sides(g.matchup), "total")
                case .btts?: (names, kind) = (sides(g.matchup), "btts")
                default: continue
                }
                let leg = PlayerCard.Leg(label: label, stat: stat[kind]!, result: Players.result(i.map { results[$0].result }, settled: settled, legs: all, status: s),
                                         day: String(b.placedAt.prefix(10)), betId: b.betId, game: kind == "total" || kind == "btts" ? g.matchup : nil)
                for n in names where n.range(of: "^draw$", options: [.regularExpression, .caseInsensitive]) == nil {
                    let name = fullName(g.sport, n)
                    out.append(Players.Entry(key: Live.normName(name), name: name, sport: g.sport.map(Fmt.sportName) ?? "Other", leg: leg, bet: b))
                }
            }
        }
        return out
    }

    /// Your teams, most-bet first.
    static func teams(_ bets: [MyBet], tickets: [String: JSON], min: Int = 2) -> [PlayerCard] {
        Players.tally(bets.flatMap { teamLegs($0, groups($0, tickets: tickets)) }, min: min)
    }

    private static let club: Set<String> = ["fc", "cf", "sc", "afc", "ac", "and", "the"]

    /// One team under two spellings: the same name, or one's words all inside the other's ("Genoa" / "Genoa CFC",
    /// "Bournemouth" / "AFC Bournemouth"). Never a shared city: the Knicks' card took the Rangers, Islanders, Jets,
    /// Giants and NYCFC legs (Oct 25) when it matched on parts (web cards.ts sameTeam).
    static func sameTeam(_ a: String, _ b: String) -> Bool {
        let w = { (n: String) in Live.normName(n).split(separator: " ").map(String.init).filter { !$0.isEmpty && !club.contains($0) } }
        let x = w(a), y = w(b)
        guard !x.isEmpty, !y.isEmpty else { return false }
        let (short, long) = x.count <= y.count ? (x, y) : (y, x)
        return short.allSatisfy { long.contains($0) } && (short.count > 1 || long.count <= 2)
    }

    /// The one card a picture points at, from every bet (one leg is enough); nil when you've never bet on them. A team
    /// matches on its full name (legs' codes are made full names first, "OTT" -> "Ottawa Senators"), see sameTeam.
    static func card(_ bets: [MyBet], tickets: [String: JSON], ref: CardRef) -> PlayerCard? {
        if ref.kind == .player {
            let want = Live.normName(ref.name)
            return Players.all(bets, min: 1).first { $0.key == want }
        }
        let mine = bets.flatMap { teamLegs($0, groups($0, tickets: tickets)) }.filter { sameTeam($0.name, ref.name) }
        guard let name = mine.first?.name else { return nil }
        return Players.tally(mine.map { Players.Entry(key: Live.normName(name), name: name, sport: $0.sport, leg: $0.leg, bet: $0.bet) }, min: 1).first
    }

    /// The fun tickets' bodies for parlay bets (their games), as the live tracker loads them.
    static func tickets(_ api: SupabaseClient, _ bets: [MyBet]) async -> [String: JSON] {
        let ids = Array(Set(bets.filter { $0.kind == "parlay" }.compactMap(\.sgpId)))
        guard !ids.isEmpty, let rows: [JSON] = try? await api.rows("fun_tickets", .init(select: "sgp_id,sport,matchup,commence_time,body", inList: ("sgp_id", ids)), plain: true)
        else { return [:] }
        var out: [String: JSON] = [:]
        for r in rows {
            guard let id = r["sgp_id"].string else { continue }
            var body = r["body"].object
            body["_sport"] = r["sport"]; body["_matchup"] = r["matchup"]; body["_start"] = r["commence_time"]
            out[id] = .object(body)
        }
        return out
    }

    private static let leagues = ["NFL": "nfl", "NBA": "nba", "NHL": "nhl", "WNBA": "wnba", "NCAAF": "college-football", "NCAAB": "mens-college-basketball"]

    /// A card's face: a player's from Players.headshot; a team's logo, name, code and color from ESPN's team search,
    /// trying the name as the odds feed writes it, then ESPN's way ("Brighton and Hove Albion" / "&").
    static func look(_ kind: CardRef.Kind, _ name: String, sport: String) async -> Players.Headshot {
        if kind == .player { return await Players.headshot(name, sport: sport) }
        var tries: [String] = []
        for q in [name, name.replacingOccurrences(of: " and ", with: " & "),
                  name.replacingOccurrences(of: #"^(AFC|FC|CF|SC) | (FC|CF|SC|AFC)$"#, with: "", options: .regularExpression)] where !tries.contains(q) {
            tries.append(q)
        }
        for q in tries {
            let enc = q.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? q
            guard let j = await ESPN.shared.get("https://site.web.api.espn.com/apis/common/v3/search?query=\(enc)&limit=5&type=team", ttl: 86_400)
            else { continue }
            let items = j["items"].array
            let hit = sport == "Soccer" ? items.first { $0["sport"].string == "soccer" }
                : leagues[sport].map { lg in items.first { $0["league"].string == lg } } ?? items.first
            guard let hit else { continue }
            let logo = hit["logos"][0]["href"].string
            return Players.Headshot(url: logo, team: hit["displayName"].string ?? name, teamShort: hit["abbreviation"].string,
                                    color: Live.teamColor(hit["color"].string, hit["alternateColor"].string), logo: logo)
        }
        return Players.Headshot()
    }
}

/// "Your teams" on Stats, once the parlays' games are in (StatsSections loads them: an empty row runs no task).
struct TeamCardsSection: View {
    let bets: [MyBet]
    @EnvironmentObject private var store: BetStore

    var body: some View {
        if let tickets = store.cardTickets {
            CardShelfSection(title: "Your teams", kind: .team, cards: Cards.teams(bets, tickets: tickets),
                             foot: "A team's moneylines and spreads, and its games' totals and both-teams-to-score legs. Tap a card for every leg.")
        }
    }
}

/// A picture that opens its card (a leg's headshot or logo, a scoreboard's logo): your record with that player or team
/// in a sheet. Each carries its own sheet, so it opens from anywhere, the wall's full screen included.
struct CardTap<Label: View>: View {
    let ref: CardRef?
    var sport: String? = nil
    @ViewBuilder let label: () -> Label
    @EnvironmentObject private var store: BetStore
    @State private var open: CardRef?

    var body: some View {
        if let ref {
            Button { open = ref } label: { label() }
                .buttonStyle(.plain)
                .accessibilityLabel("\(ref.name): your record")
                .sheet(item: $open) { r in CardSheet(ref: r, sport: sport, store: store) }
        } else {
            label()
        }
    }
}

/// The sheet a picture opens: your bets and their games loaded, then the card.
private struct CardSheet: View {
    let ref: CardRef
    let sport: String?
    let store: BetStore
    @State private var card: PlayerCard?
    @State private var shot: Players.Headshot?
    @State private var loading = true

    var body: some View {
        CardDetail(kind: ref.kind, name: ref.name, p: card, shot: shot, loading: loading)
            .foregroundStyle(Color.primary)  // a scoreboard's logo opens it: its white text color mustn't carry in
            .task {
                if store.cardTickets == nil { await store.loadCardTickets() }
                let tickets = store.cardTickets ?? [:]
                card = Cards.card(store.bets, tickets: tickets, ref: ref)
                loading = false
                shot = await Cards.look(ref.kind, ref.kind == .team ? ref.name : card?.name ?? ref.name,
                                        sport: card?.sport ?? sport.map(Fmt.sportName) ?? "")
            }
    }
}
