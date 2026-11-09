import Foundation

// My bets' live tracker (Oct 23), ported from web/lib/live.ts and web/lib/live-bets.ts. ESPN's free scoreboards and game
// summaries carry the live score, clock and every player's box score in each league we bet, ~15-30 s behind the
// broadcast, with no ids to match: a bet's game is found on today's scoreboard by its teams (or fighters), and each leg
// is judged from the live numbers. The app calls ESPN itself (the web's /api/live reads the web's sign-in cookies), through
// a 15-second cache, so many bets on one game cost one request. LiveTests runs web/tests/live.test.mjs's cases.
// **Change both together.**

struct LiveSide: Equatable {
    var name: String
    var abbr: String
    var score: Double?
    var logo: String? = nil        // ESPN's team logo; UFC: the fighter's photo
    var color: String? = nil       // "#rrggbb" that reads on light and dark screens (Live.teamColor), or none
}

struct GameLive: Identifiable, Equatable {
    var key: String
    var sport: String
    var espnId: String
    var state: String              // pre, in, post
    var detail: String
    var start: String
    var home: LiveSide
    var away: LiveSide
    var neutral = false
    var winner: String? = nil      // UFC: "home" / "away"
    var result: String? = nil      // UFC: "Decision - Unanimous"
    // football while live (Mike, Oct 25: "signify who has the ball", "a redzone indicator"): ESPN's situation
    var ball: String? = nil        // "home" / "away"
    var redZone = false
    var down: String? = nil        // "3rd & Goal at ATL 1"
    var id: String { key }

    /// The game in reading order: soccer reads home team first (Mike, Nov 5), so its copy swaps the sides (and who has
    /// the ball or won, with them); the rest stay away first. A view that draws `away` then `home` draws this.
    var reading: GameLive {
        guard Fmt.isSoccer(sport) else { return self }
        var g = self
        (g.away, g.home) = (home, away)
        let other = { (s: String?) in s == "home" ? "away" : s == "away" ? "home" : s }
        g.ball = other(ball); g.winner = other(winner)
        return g
    }
    /// The word between the two sides: "vs" for a fight or a soccer match, "@" for the rest.
    var between: String { sport == "ufc" || Fmt.isSoccer(sport) ? "vs" : "@" }
}

enum LegStatus: String { case pending, live, winning, losing, tied, won, lost, void, unknown }

struct LegLive: Equatable {
    var label: String
    var status: LegStatus
    var current: Double? = nil
    var target: Double? = nil
    var unit = ""
    var text = ""
    var gameKey: String?
    var img: String? = nil         // a prop's player headshot, a team leg's logo (Oct 23)
    var card: CardRef? = nil       // whose card its picture opens (Oct 25)
    var onCourt: Bool? = nil       // a basketball player's leg while live: on the floor now (Oct 25); nil when unknown
    var deadHeat: Bool? = nil      // a tie for "most X": won at a share, so never settled live at the full price (Nov 9)
}

struct LiveGroup: Equatable { var sport: String?; var league: String?; var matchup: String; var legs: [String]; var start: String? = nil; var ref: String? = nil }

struct BetLive: Equatable {
    var games: [GameLive]
    var legs: [LegLive]
    var status: String             // pending, live, won, lost
    var hit: Int
    var total: Int
    var settle: String? = nil      // "won" / "lost": settled from the live state alone (rollup)
}

typealias LiveBox = [String: [String: Double]]
/// Players' headshots: {normalized name: url}.
typealias LiveHeads = [String: String]

/// The open bet the tracker reads: `my_bets` keys as stored (`games` is free-form, so this row decodes without key
/// conversion), and a fun ticket's body by its sgp_id.
struct LiveBetRow: Decodable {
    var bet_id: String
    var kind: String? = nil
    var sgp_id: String? = nil
    var label: String? = nil
    var legs: [String]? = nil
    var matchup: String? = nil
    var league: String? = nil
    var sport: String? = nil
    var games: JSON? = nil
    var pick_commence_time: String? = nil
    var ticket_commence_time: String? = nil
    var placed_at: String? = nil
    /// A bet's first kickoff and its games' kickoffs by the games table's id (LiveModel.refresh, as BetStore.withStarts):
    /// each game is looked for on its own days (Live.searchDays). Not stored columns: never decoded.
    var game_start: String? = nil
    var game_starts: [String: String]? = nil

    private enum CodingKeys: String, CodingKey {
        case bet_id, kind, sgp_id, label, legs, matchup, league, sport, games, pick_commence_time, ticket_commence_time, placed_at
    }
}

enum Live {
    static let paths = ["nfl": "football/nfl", "ncaaf": "football/college-football", "nba": "basketball/nba",
                        "ncaab": "basketball/mens-college-basketball", "nhl": "hockey/nhl", "ufc": "mma/ufc",
                        "wnba": "basketball/wnba", "mlb": "baseball/mlb"]
    static let soccer = ["epl": "eng.1", "la_liga": "esp.1", "serie_a": "ita.1", "bundesliga": "ger.1", "ligue_1": "fra.1",
                         "mls": "usa.1", "ucl": "uefa.champions", "uel": "uefa.europa", "uecl": "uefa.europa.conf"]
    static let soccerOrder = ["epl", "la_liga", "serie_a", "bundesliga", "ligue_1", "mls", "ucl", "uel", "uecl"]
    private static let extra = ["ncaaf": "&groups=80&limit=300", "ncaab": "&groups=50&limit=400"]
    static let base = "https://site.api.espn.com/apis/site/v2/sports"
    static let guess = ["nfl", "nba", "nhl", "ncaaf", "ncaab", "ufc"]     // a bet that doesn't say its sport

    static func path(_ sport: String, _ league: String?) -> String? {
        sport == "soccer" ? "soccer/\(soccer[league ?? ""] ?? league ?? "")" : paths[sport]
    }

    static func scoreboardURL(_ sport: String, _ league: String?, day: String) -> String? {
        path(sport, league).map { "\(base)/\($0)/scoreboard?dates=\(day)\(extra[sport] ?? "")" }
    }

    static let headshot = "https://a.espncdn.com/i/headshots"

    /// A team color that reads on both the light and dark themes: the primary unless it's near white or near black,
    /// then the alternate; none if both are. ESPN gives hex without '#'.
    static func teamColor(_ primary: String?, _ alternate: String?) -> String? {
        func lum(_ h: String) -> Double {
            let v = [0, 2, 4].map { i -> Double in
                let a = h.index(h.startIndex, offsetBy: i)
                return Double(Int(h[a..<h.index(a, offsetBy: 2)], radix: 16) ?? 0) / 255
            }
            return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
        }
        for c in [primary, alternate] {
            guard let c, c.range(of: "^[0-9a-fA-F]{6}$", options: .regularExpression) != nil else { continue }
            if lum(c) > 0.08 && lum(c) < 0.85 { return "#" + c }
        }
        return nil
    }

    /// JavaScript's Number(): blank is 0, anything unparseable is NaN.
    static func jsNumber(_ s: String) -> Double {
        let t = s.trimmingCharacters(in: .whitespaces)
        return t.isEmpty ? 0 : Double(t) ?? .nan
    }

    /// A number as JavaScript prints it: 3 → "3", 2.5 → "2.5".
    static func js(_ x: Double) -> String { x == x.rounded() && abs(x) < 1e15 ? String(Int(x)) : String(x) }

    // MARK: ESPN

    /// One scoreboard's games (UFC: one entry per fight).
    static func parseBoard(_ sb: JSON, sport: String) -> [GameLive] {
        var out: [GameLive] = []
        for e in sb["events"].array {
            let comps = sport == "ufc" ? e["competitions"].array : [e["competitions"][0]]
            for c in comps where !c.isNull {
                let comp = c["competitors"].array
                func side(_ x: JSON) -> LiveSide {
                    let s = x["score"]
                    let score: Double? = s.isNull || s.string == "" ? nil : jsNumber(s["value"].isNull ? (s.string ?? "") : (s["value"].string ?? ""))
                    let fighter = x["athlete"]["id"].string ?? x["id"].string     // ESPN puts the fighter's id on the competitor
                    return LiveSide(name: sport == "ufc" ? x["athlete"]["displayName"].string ?? "" : x["team"]["displayName"].string ?? "",
                                    abbr: sport == "ufc" ? lastName(x["athlete"]["displayName"].string) : x["team"]["abbreviation"].string ?? "",
                                    score: score,
                                    logo: sport == "ufc" ? fighter.map { "\(headshot)/mma/players/full/\($0).png" } : x["team"]["logo"].string,
                                    color: sport == "ufc" ? nil : teamColor(x["team"]["color"].string, x["team"]["alternateColor"].string))
                }
                guard let home = comp.first(where: { $0["homeAway"].string == "home" }) ?? comp.first,
                      let away = comp.first(where: { $0["homeAway"].string == "away" }) ?? comp[safe: 1] else { continue }
                let st = c["status"]["type"].isNull ? e["status"]["type"] : c["status"]["type"]
                var g = GameLive(key: "\(sport):\(sport == "ufc" ? c["id"].string ?? "" : e["id"].string ?? "")", sport: sport,
                                 espnId: e["id"].string ?? "", state: st["state"].string ?? "pre",
                                 detail: st["shortDetail"].string ?? st["detail"].string ?? "",
                                 start: c["date"].string ?? e["date"].string ?? "", home: side(home), away: side(away),
                                 neutral: c["neutralSite"].bool == true)
                let sit = c["situation"]
                if (sport == "nfl" || sport == "ncaaf") && g.state == "in" && !sit.isNull {
                    let id = sit["possession"].string ?? ""
                    g.ball = !id.isEmpty && id == home["team"]["id"].string ? "home" : !id.isEmpty && id == away["team"]["id"].string ? "away" : nil
                    g.redZone = g.ball != nil && sit["isRedZone"].bool == true     // ESPN leaves the flag on between possessions
                    g.down = g.ball != nil ? sit["downDistanceText"].string ?? sit["shortDownDistanceText"].string : nil
                }
                if sport == "ufc" {        // a fight has a winner, not a score
                    let hw = home["winner"].bool == true, aw = away["winner"].bool == true
                    g.home.score = hw ? 1 : nil
                    g.away.score = aw ? 1 : nil
                    g.winner = hw ? "home" : aw ? "away" : nil
                    g.result = c["status"]["result"]["displayName"].string
                }
                out.append(g)
            }
        }
        return out
    }

    /// A game's players: {normalized name: {stat: value}} from the summary's box score (soccer: its rosters).
    static func parseBox(_ s: JSON, sport: String) -> LiveBox {
        var out: LiveBox = [:]
        func put(_ name: String, _ k: String, _ v: Double) {
            guard !name.isEmpty, v.isFinite else { return }
            let key = normName(name)
            out[key, default: [:]][k, default: 0] += v
        }
        if sport == "soccer" {
            for team in s["rosters"].array {
                for pl in team["roster"].array {
                    for st in pl["stats"].array {
                        put(pl["athlete"]["displayName"].string ?? "", st["name"].string ?? "", st["value"].double ?? jsNumber(st["value"].string ?? "x"))
                    }
                }
            }
            playStats(s, sport: sport, &out)
            return out
        }
        let sep = CharacterSet(charactersIn: "-/")
        for team in s["boxscore"]["players"].array {
            for grp in team["statistics"].array {
                let keys = grp["keys"].array.compactMap(\.string)
                // football: a QB's "sacks" (taken) and "interceptions" (thrown) aren't a defender's (made); Nov 6
                let rename: [String: String] = grp["name"].string == "passing" ? ["sacks": "sacksTaken"]
                    : grp["name"].string == "interceptions" ? ["interceptions": "interceptionsMade"] : [:]
                for a in grp["athletes"].array {
                    let name = a["athlete"]["displayName"].string ?? "", stats = a["stats"].array
                    for (i, k) in keys.enumerated() {
                        let raw = stats[safe: i]?.string ?? ""
                        if raw.isEmpty || raw.contains(":") { continue }            // clocks (time on ice) aren't counts
                        // "6-10" made-attempted, "24/31" comp/att: both halves (Nov 6: pass attempts were dropped); a leading
                        // minus ("-5") is a sign, not a separator
                        let ks = k.components(separatedBy: sep)
                        let vs = raw.hasPrefix("-") || raw.hasPrefix("+") ? [raw] : raw.components(separatedBy: sep)
                        for (j, kk) in ks.enumerated() where j < vs.count { put(name, rename[kk] ?? kk, jsNumber(vs[j])) }
                    }
                }
            }
        }
        playStats(s, sport: sport, &out)
        return out
    }

    /// A box's game-wide row: who scored first is decided ("firstBasket", "firstGoal", "firstTd": 1).
    static let game = "_game"

    /// What only ESPN's play-by-play says (Nov 6), added to the box's rows: NBA quarter stats ("q1:points", "q2:rebounds",
    /// "q3:assists", "q4:threes") and the first basket (the first field goal; free throws don't count); NHL period stats,
    /// power-play goals and points, the first goal; NFL longest completion and the first TD; soccer's first goal.
    /// live_legs.play_stats and web playStats are the same.
    static func playStats(_ s: JSON, sport: String, _ out: inout LiveBox) {
        func add(_ name: String, _ k: String, _ v: Double = 1) {
            guard !name.isEmpty else { return }
            out[normName(name), default: [:]][k, default: 0] += v
        }
        func first(_ k: String, _ name: String) {
            guard !name.isEmpty, out[game]?[k] == nil else { return }
            out[game, default: [:]][k] = 1
            add(name, k)
        }
        switch sport {
        case "nba":
            var ids: [String: String] = [:]
            for t in s["boxscore"]["players"].array { for g in t["statistics"].array { for a in g["athletes"].array {
                ids[a["athlete"]["id"].string ?? ""] = a["athlete"]["displayName"].string ?? ""
            } } }
            for p in s["plays"].array {
                let q = p["period"]["number"].int ?? 0
                let who = p["participants"].array.map { ids[$0["athlete"]["id"].string ?? ""] ?? "" }
                let typ = p["type"]["text"].string ?? ""
                if p["scoringPlay"].bool == true, let w0 = who.first {
                    let v = p["scoreValue"].double ?? 0
                    add(w0, "q\(q):points", v)
                    if v >= 2 {
                        first("firstBasket", w0)
                        if v == 3 { add(w0, "q\(q):threes") }
                        if who.count > 1 { add(who[1], "q\(q):assists") }
                    }
                } else if typ.contains("Rebound"), let w0 = who.first {
                    add(w0, "q\(q):rebounds")
                }
            }
        case "nhl":
            for p in s["plays"].array where p["type"]["text"].string == "Goal" {
                let per = p["period"]["number"].int ?? 0
                let who = p["participants"].array.filter { ["scorer", "assister", nil].contains($0["type"].string) }
                    .map { $0["athlete"]["displayName"].string ?? "" }
                guard let w0 = who.first else { continue }
                let pp = p["strength"]["abbreviation"].string == "power-play"
                first("firstGoal", w0)
                add(w0, "p\(per):goals")
                if pp { add(w0, "ppGoals") }
                for a in who.dropFirst() { add(a, "p\(per):assists") }
                if pp { for x in who { add(x, "ppPoints") } }
            }
        case "nfl":
            let names = out.keys.filter { $0 != game }
            for d in s["drives"]["previous"].array {
                for p in d["plays"].array where ["Pass Reception", "Passing Touchdown"].contains(p["type"]["text"].string ?? "") {
                    guard let m = search(#"([A-Z][a-zA-Z'-]*)\.\s?([A-Za-z'.-]+(?:\s(?:Jr|Sr|II|III|IV)\.?)?) pass"#, p["text"].string ?? ""),
                          let y = p["statYardage"].double else { continue }
                    let ini = String(m[1].prefix(1)).lowercased(), last = plain(m[2])
                    if let qb = names.first(where: { $0.hasPrefix(ini) && $0.split(separator: " ").map(String.init).contains(last) }) {
                        out[qb]!["longCompletion"] = max(out[qb]!["longCompletion"] ?? 0, y)
                    }
                }
            }
            for p in s["scoringPlays"].array where (p["type"]["text"].string ?? "").contains("Touchdown") {
                if let m = match(#"^(.+?) \d+ Yd.*$"#, p["text"].string ?? "") { first("firstTd", m[1]); break }
            }
        case "soccer":
            for k in s["keyEvents"].array {
                let typ = (k["type"]["text"].string ?? "").lowercased()
                guard typ == "goal" || (k["scoringPlay"].bool == true && !typ.contains("own") && typ.contains("goal")),
                      let w0 = k["participants"].array.first?["athlete"]["displayName"].string else { continue }
                first("firstGoal", w0); break
            }
        default: break
        }
    }

    /// The groups of the first regex match anywhere in s, or nil.
    private static func search(_ pattern: String, _ s: String) -> [String]? {
        guard let re = try? NSRegularExpression(pattern: pattern),
              let m = re.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)) else { return nil }
        return (0..<m.numberOfRanges).map { i in Range(m.range(at: i), in: s).map { String(s[$0]) } ?? "" }
    }

    /// Who's on the floor in a live basketball game: ESPN's box score marks them `active`, five a side (web parseOnCourt).
    static func parseOnCourt(_ s: JSON) -> [String] {
        var out: [String] = []
        for t in s["boxscore"]["players"].array {
            for grp in t["statistics"].array {
                for a in grp["athletes"].array where a["active"].bool == true {
                    let n = normName(a["athlete"]["displayName"].string)
                    if !n.isEmpty && !out.contains(n) { out.append(n) }
                }
            }
        }
        return out
    }

    /// Players' headshots: the box score's own (NFL, NBA, NHL), else ESPN's headshot address by player id (soccer).
    static func parseHeads(_ s: JSON, sport: String) -> LiveHeads {
        var out: LiveHeads = [:]
        func put(_ a: JSON) {
            guard let name = a["displayName"].string, !name.isEmpty else { return }
            let href = a["headshot"]["href"].string ?? a["headshot"].string
            let url = (href?.isEmpty == false ? href : nil) ?? (sport == "soccer" ? a["id"].string.map { "\(headshot)/soccer/players/full/\($0).png" } : nil)
            if let url, out[normName(name)] == nil { out[normName(name)] = url }
        }
        if sport == "soccer" {
            for t in s["rosters"].array { for pl in t["roster"].array { put(pl["athlete"]) } }
        } else {
            for t in s["boxscore"]["players"].array { for grp in t["statistics"].array { for a in grp["athletes"].array { put(a["athlete"]) } } }
        }
        return out
    }

    // MARK: names

    static func plain(_ s: String?) -> String {
        let folded = String(String.UnicodeScalarView((s ?? "").decomposedStringWithCompatibilityMapping.unicodeScalars
            .filter { !(0x300...0x36F).contains($0.value) })).lowercased()
        let mapped = String(folded.map { ("a"..."z").contains($0) || ("0"..."9").contains($0) || $0 == " " ? $0 : " " })
        return mapped.split(separator: " ").joined(separator: " ")
    }
    private static let suffix: Set<String> = ["jr", "sr", "ii", "iii", "iv", "v"]
    static func normName(_ s: String?) -> String { plain(s).split(separator: " ").map(String.init).filter { !suffix.contains($0) }.joined(separator: " ") }
    static func lastName(_ s: String?) -> String { normName(s).components(separatedBy: " ").last ?? "" }

    /// A player in a box score: exact name, else first initial + last name, else a unique last name.
    static func findPlayer<T>(_ box: [String: T], _ name: String) -> T? {
        let n = normName(name)
        if let r = box[n] { return r }
        // one word ("Militao") is his last name too (live_legs.find_player, Nov 9)
        let t = n.components(separatedBy: " "), first = t.first ?? "", last = t.last ?? ""
        let byInitial = box.keys.filter { k in let kt = k.components(separatedBy: " "); return kt.last == last && kt[0].first == first.first }
        if byInitial.count == 1 { return box[byInitial[0]] }
        let byLast = box.keys.filter { $0.components(separatedBy: " ").last == last }
        return byLast.count == 1 ? box[byLast[0]] : nil
    }

    // NHL codes the books use that ESPN writes differently
    private static let alias = ["njd": "nj", "sjs": "sj", "tbl": "tb", "lak": "la", "wsh": "wsh", "vgk": "vgk", "uta": "utah", "clb": "cbj"]
    private static let generic: Set<String> = ["fc", "cf", "sc", "ac", "club", "city", "united", "real", "de", "sporting", "athletic", "the", "of", "st"]

    /// How well our team text ("Chicago Bears", "CHI", "MIN", "Inter Milan", "Fighter Name") names this side: 3 the full
    /// name or abbreviation, 2 the nickname or last name, 1 a shared strong word, 0 not at all.
    static func teamMatch(_ ours: String, _ side: LiveSide) -> Int {
        let o = plain(ours)
        if o.isEmpty { return 0 }
        let abbr = plain(side.abbr), full = plain(side.name)
        if o == abbr || alias[o] == abbr || o == full || SoccerClubs.aliases[o].map(plain) == full { return 3 }
        let ot = o.components(separatedBy: " "), ft = full.components(separatedBy: " ")
        if ot.count > 1 && ot.last == ft.last && !generic.contains(ot.last!) { return 2 }    // nickname / last name
        let strong = { (t: String) in t.count >= 4 && !generic.contains(t) }
        return ot.filter(strong).contains { ft.contains($0) } && ft.filter(strong).contains { ot.contains($0) } ? 1 : 0
    }
    static func isTeam(_ ours: String, _ side: LiveSide) -> Bool { teamMatch(ours, side) > 0 }

    /// Which side of a game our team text names: the better match when both do (Oct 24: "LSU Tigers" at Auburn Tigers
    /// read as Auburn by the shared nickname, so LSU's moneyline showed "Down 7" while LSU led). A tie names no side.
    static func sideOf(_ ours: String, _ g: GameLive) -> String? {
        let h = teamMatch(ours, g.home), a = teamMatch(ours, g.away)
        return h == a ? nil : h > a ? "home" : "away"
    }

    /// How well our matchup names a game: both teams must match (either way round); the sum of the two matches, else 0.
    static func gameMatch(_ g: GameLive, _ x: String, _ y: String) -> Int {
        let fwd = min(teamMatch(x, g.away), teamMatch(y, g.home)) > 0 ? teamMatch(x, g.away) + teamMatch(y, g.home) : 0
        let rev = min(teamMatch(x, g.home), teamMatch(y, g.away)) > 0 ? teamMatch(x, g.home) + teamMatch(y, g.away) : 0
        return max(fwd, rev)
    }

    /// Our matchup "Away @ Home" / "A vs B" on a scoreboard: the best-named game (Oct 24: "Boise State Broncos @
    /// Washington State Cougars" matched Sacramento State @ Ball State by the shared word "State", live first), then a
    /// game in progress first.
    static func findGame(_ games: [GameLive], _ matchup: String) -> GameLive? {
        let parts = matchup.replacingOccurrences(of: #" @ | vs\.? | v "#, with: "\u{1}", options: .regularExpression)
            .components(separatedBy: "\u{1}")
        guard parts.count > 1, !parts[0].isEmpty, !parts[1].isEmpty else { return nil }
        let x = parts[0], y = parts[1]
        let order = ["in": 0, "pre": 1]
        let hits = games.enumerated().map { (i: $0.offset, g: $0.element, m: gameMatch($0.element, x, y)) }.filter { $0.m > 0 }
        return hits.min { a, b in
            let (oa, ob) = (order[a.g.state] ?? 2, order[b.g.state] ?? 2)
            return a.m != b.m ? a.m > b.m : oa != ob ? oa < ob : a.i < b.i
        }?.g
    }

    // MARK: legs

    enum Parsed: Equatable {
        case ml(team: String)
        case spread(team: String, point: Double)
        case total(side: String, point: Double)
        case btts
        case bttsNo
        case draw
        case drawOr(team: String)
        case noDraw                               // Novig's 3-way "no" sides (Nov 9)
        case notWin(team: String)
        case prop(player: String, stat: String, side: String, need: Double, point: Double)
        case td(player: String, first: Bool)
        case goalOrAssist(player: String)
        case double(player: String, n: Int)      // a double-double (2) or triple-double (3), Oct 25
        case leader(player: String, stat: String) // "X most receiving yds" in the game (Nov 6)
        case card(player: String)                 // "X to be carded" (Nov 6)
        case first(player: String, what: String)  // the game's first basket or goal (Nov 6)
    }

    private static let statWords = (["receiving yds", "rushing yds", "passing yds", "receptions", "pts + reb + ast", "pts + reb", "pts + ast",
        "reb + ast", "points", "rebounds", "assists", "threes", "steals", "blocks", "shots on target", "shots on goal", "shots",
        "saves", "goals", "passing tds", "rush + rec yds",
        // Nov 6 (Mike: "track more stats... all possible markets"): what ESPN's box scores carry
        "longest reception", "longest rush", "rush attempts", "pass attempts", "completions", "interceptions", "tackles", "sacks",
        "kicking points", "field goals made", "turnovers", "stl + blk", "free throws made", "offensive rebounds", "blocked shots",
        "hits", "fouls", "longest completion", "power play points", "power play goals",
        // Nov 9: touchdowns by count ("2+ TDs", "1+ rushing TDs"); a rusher's and receiver's together
        "touchdowns", "rushing tds", "receiving tds"] as [String] + periodWords).sorted { $0.count > $1.count }
    /// Quarter and half (NBA) and period (NHL) stats from the play-by-play: "1q points", "2h rebounds", "1p goals".
    private static let periodWords: [String] = {
        let bb = ["points", "rebounds", "assists", "threes"], hk = ["goals", "assists", "points"]
        var out: [String] = []
        for n in 1...4 { for w in bb { out.append("\(n)q \(w)") } }
        for n in 1...2 { for w in bb { out.append("\(n)h \(w)") } }
        for n in 1...3 { for w in hk { out.append("\(n)p \(w)") } }
        return out
    }()
    /// The stats a "most ... in the game" leg can be about (Nov 6).
    private static let leaderWords: Set<String> = ["receiving yds", "rushing yds", "passing yds", "receptions", "points", "rebounds",
                                                   "assists", "threes", "shots on goal", "shots", "goals"]
    /// (wording at the end of a leg or before its "over/under N", our stat words): live_legs.ALIASES, web ALIASES
    private static let aliases: [(String, String)] = [
        (#"\s+(?:points\s*\+\s*rebounds\s*\+\s*assists|pts\s*\+\s*rebs?\s*\+\s*asts?|pra)"#, " pts + reb + ast"),
        (#"\s+(?:points\s*\+\s*rebounds|pts\s*\+\s*rebs?)"#, " pts + reb"),
        (#"\s+(?:points\s*\+\s*assists|pts\s*\+\s*asts?)"#, " pts + ast"),
        (#"\s+(?:rebounds\s*\+\s*assists|rebs?\s*\+\s*asts?)"#, " reb + ast"),
        (#"\s+(?:steals\s*\+\s*blocks|blocks\s*\+\s*steals|stl\s*\+\s*blk|stocks)"#, " stl + blk"),
        (#"\s+(?:threes\s+made|made\s+threes|three[\s-]*pointers(?:\s+made)?|3[\s-]*pointers(?:\s+made)?|3pt\s+made|3pm)"#, " threes"),
        (#"\s+(?:longest\s+(?:reception|catch|rec)|long\s+reception)(?:\s+(?:yds|yards))?"#, " longest reception"),
        (#"\s+(?:longest\s+(?:rush|rushing\s+attempt|run)|long\s+rush)(?:\s+(?:yds|yards))?"#, " longest rush"),
        (#"\s+(?:rushing\s+attempts|rush\s+attempts|carries)"#, " rush attempts"),
        (#"\s+(?:passing\s+attempts|pass\s+attempts)"#, " pass attempts"),
        (#"\s+(?:pass(?:ing)?\s+completions|completions)"#, " completions"),
        (#"\s+(?:interceptions\s+thrown|passing\s+interceptions|ints?\s+thrown)"#, " interceptions"),
        (#"\s+(?:tackles\s*(?:\+|and|&)\s*assists|total\s+tackles|tackles)"#, " tackles"),
        (#"\s+(?:made\s+field\s+goals|field\s+goals(?:\s+made)?|fgm)"#, " field goals made"),
        (#"\s+(?:made\s+free\s+throws|free\s+throws(?:\s+made)?|ftm)"#, " free throws made"),
        (#"\s+(?:offensive\s+rebounds|off\s+rebounds)"#, " offensive rebounds"),
        (#"\s+(?:fouls\s+committed|fouls)"#, " fouls"),
        (#"\s+(?:longest\s+(?:pass\s+)?completion|longest\s+pass(?:\s+completed)?)(?:\s+(?:yds|yards))?"#, " longest completion"),
        (#"\s+(?:power[\s-]*play\s+points|pp\s+points|ppp)"#, " power play points"),
        (#"\s+(?:power[\s-]*play\s+goals|pp\s+goals|ppg)"#, " power play goals"),
        // Nov 9: short forms ("25+ Pts", "Over 2.5 SOG") and touchdowns by kind; a combo's last word ("pts + reb") is left alone
        (#"(?<!\s\+)\s+pts"#, " points"),
        (#"(?<!\s\+)\s+rebs?"#, " rebounds"),
        (#"(?<!\s\+)\s+asts?"#, " assists"),
        (#"\s+sog"#, " shots on goal"),
        (#"\s+sot"#, " shots on target"),
        (#"\s+(?:passing\s+(?:touchdowns|tds?)|pass\s+tds?)"#, " passing tds"),
        (#"\s+(?:rushing\s+(?:touchdowns|tds?)|rush\s+tds?)"#, " rushing tds"),
        (#"\s+(?:receiving\s+(?:touchdowns|tds?)|rec\s+tds?)"#, " receiving tds"),
        (#"(?<=[\d+])\s+(?:touchdowns|tds?)"#, " touchdowns"),
    ].map { ($0.0 + #"(?=$|\s+(?:over|under)\s+\d)"#, $0.1) }
    /// A part of a game ("1H", "1st quarter", "2nd period", "first 5 innings", "60 min", "regulation"): a team's line on it
    /// isn't the full game's, so it's not tracked rather than judged on the final score (Nov 9; live_legs.SEGMENT).
    static func segment(_ s: String) -> Bool {
        s.range(of: #"(?:^|[\s(])(?:(?:1st|2nd|3rd|4th|first|second|third|fourth)\s+(?:half|quarter|qtr|period|inning)s?|[1-4][hqp]|[qp][1-4]|first\s+\d+\s+innings?|f5|60[\s-]*min(?:ute)?s?|regulation(?:\s+time)?)\)?(?=$|[\s)])"#,
                options: [.regularExpression, .caseInsensitive]) != nil
    }

    /// The groups of a whole-string regex match, or nil.
    private static func match(_ pattern: String, _ s: String, ci: Bool = true) -> [String]? {
        guard let re = try? NSRegularExpression(pattern: pattern, options: ci ? [.caseInsensitive] : []),
              let m = re.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)) else { return nil }
        return (0..<m.numberOfRanges).map { i in Range(m.range(at: i), in: s).map { String(s[$0]) } ?? "" }
    }

    /// The stat's wording as books and slips write it, made ours (web live.ts canonStat, Oct 25): rushing + receiving /
    /// rush & rec -> "rush + rec yds", "... yards" -> "... yds".
    static func canonStat(_ label: String) -> String {
        var l = label.trimmingCharacters(in: .whitespacesAndNewlines)
        l = l.replacingOccurrences(of: #"\s+(?:rushing|rush)\s*(?:\+|&|and)\s*(?:receiving|rec)(?:\s+(?:yds|yards))?$"#,
                                   with: " rush + rec yds", options: [.regularExpression, .caseInsensitive])
        for w in ["rushing", "receiving", "passing"] {
            l = l.replacingOccurrences(of: "\\s+\(w)\\s+yards(?=$|\\s+(?:over|under)\\s+\\d)", with: " \(w) yds", options: [.regularExpression, .caseInsensitive])
        }
        // "X Anytime Touchdown Scorer", "X anytime TD scorer" (Nov 9): ours is "X anytime TD"
        l = l.replacingOccurrences(of: #"^(.+?)\s+anytime\s+(?:touchdown|td)(?:\s+scorer)?$"#, with: "$1 anytime TD",
                                   options: [.regularExpression, .caseInsensitive])
        // an anytime scorer (Oct 25: "Lamine Yamal anytime goalscorer" wasn't tracked): one goal is the line
        l = l.replacingOccurrences(of: #"^(?!both teams\b)(.+?)\s+(?:anytime\s+(?:goal\s*scorer|goal|scorer)|to\s+score(?:\s+a\s+goal)?|anytime\s+to\s+score)$"#,
                                   with: "$1 1+ goals", options: [.regularExpression, .caseInsensitive])
        // Nov 6: the books' other wordings of the stats tracked
        for (pat, ours) in aliases { l = l.replacingOccurrences(of: pat, with: ours, options: [.regularExpression, .caseInsensitive]) }
        // "1st quarter points" -> "1q points", "first half rebounds" -> "1h rebounds", "1st period goals" -> "1p goals"
        if let m = match(#"^(.*?)\s+(?:(1)st|(2)nd|(3)rd|(4)th|(first|second|third|fourth)|q([1-4])|([1-4])q)\s*(quarter|qtr|half|period)?\s+(points|rebounds|assists|threes|goals)(\s+(?:over|under)\s+\d.*)?$"#, l) {
            let words = ["first": "1", "second": "2", "third": "3", "fourth": "4"]
            let n = [m[2], m[3], m[4], m[5], words[m[6].lowercased()] ?? "", m[7], m[8]].first { !$0.isEmpty } ?? "1"
            let unit = m[9].lowercased(), k = unit == "half" ? "h" : unit == "period" ? "p" : "q"
            l = "\(m[1]) \(n)\(k) \(m[10].lowercased())\(m[11])"
        }
        // "To Record Double Double", "double-double" (Oct 25, Mike's Towns leg): one wording
        if let m = match(#"^(.+?)\s+(?:to\s+record\s+(?:an?\s+)?)?(double|triple)[\s-]*double$"#, l) {
            l = "\(m[1]) \(m[2].lowercased())-double"
        }
        return l
    }

    static func parseLeg(_ label: String) -> Parsed? {
        var l = canonStat(label)
        if match("^both teams to score(?:: ?yes)?$", l) != nil { return .btts }
        if match("^both teams to score: ?no$", l) != nil { return .bttsNo }   // Nov 4: Build offers these three; none tracked
        if match("^draw$", l) != nil { return .draw }
        if match("^no draw$", l) != nil { return .noDraw }            // Nov 9: Novig's 3-way "no" sides (novig_sync)
        if let m = match("^(.+) not to win$", l) { return .notWin(team: m[1]) }
        if let m = match("^(.+) or draw$", l) { return .drawOr(team: m[1]) }
        if let m = match(#"^(over|under) (\d+(?:\.\d+)?)(?: (?:total points|total goals|total|goals|points|runs|rounds))?$"#, l) {
            return .total(side: m[1].lowercased(), point: Double(m[2])!)
        }
        if let m = match("^(.+) anytime TD$", l) { return .td(player: m[1], first: false) }
        if let m = match(#"^(.+?) (?:first TD scorer|first touchdown(?: scorer)?|to score (?:the )?first (?:TD|touchdown))$"#, l) { return .td(player: m[1], first: true) }
        if let m = match(#"^(.+?) (?:to (?:make|score) (?:the )?)?first (basket|field goal|fg)(?: scorer)?$"#, l) { return .first(player: m[1], what: "basket") }
        if let m = match(#"^(.+?) (?:to score (?:the )?)?first (?:goal\s*scorer|goal)$"#, l) { return .first(player: m[1], what: "goal") }
        if let m = match("^(.+) to score or assist$", l) { return .goalOrAssist(player: m[1]) }
        // "X most receiving yds", "X to have the most receiving yards in the game" (Nov 6, Mike: "most rcv/rush yards in game")
        if let m = match(#"^(.+?) (?:to (?:have|record|get) )?(?:the )?most (.+?)(?: in (?:the )?game)?$"#, l) {
            let w = String(canonStat("x " + m[2]).dropFirst(2)).lowercased()
            if leaderWords.contains(w) { return .leader(player: m[1], stat: w) }
        }
        if let m = match(#"^(.+?) to (?:be (?:carded|booked|shown a card)|receive a card|get a card)$"#, l) { return .card(player: m[1]) }
        if let m = match("^(.+) (double|triple)-double$", l) { return .double(player: m[1], n: m[2].lowercased() == "double" ? 2 : 3) }
        for w in statWords {      // the stat before its number ("Puka Nacua longest reception over 22.5"): ours puts it last
            if let m = match("^(.+?) \(NSRegularExpression.escapedPattern(for: w)) (over|under) (\\d+(?:\\.\\d+)?)$", l) {
                l = "\(m[1]) \(m[2]) \(m[3]) \(w)"; break
            }
        }
        for w in statWords where l.lowercased().hasSuffix(" " + w) {
            let head = String(l.dropLast(w.count + 1))
            let n = match(#"^(.+?) (\d+)\+$"#, head, ci: false), ou = n == nil ? match(#"^(.+?) (over|under) (\d+(?:\.\d+)?)$"#, head) : nil
            if let m = n ?? ou, segment(m[1]) { return nil }     // "Knicks 1H over 55.5 points": a part of the game, not tracked
            if let m = n {
                let k = Double(m[2])!
                return .prop(player: m[1], stat: w, side: "over", need: k, point: k - 0.5)
            }
            if let m = ou {
                let pt = Double(m[3])!
                return .prop(player: m[1], stat: w, side: m[2].lowercased(), need: pt.rounded(.down) + 1, point: pt)
            }
        }
        var team: Parsed? = nil, name = ""
        if let m = match("^(.+) (?:ML|to win)$", l) { team = .ml(team: m[1]); name = m[1] }
        else if let m = match(#"^(.+) ([+-]\d+(?:\.\d+)?)$"#, l, ci: false) { team = .spread(team: m[1], point: Double(m[2])!); name = m[1] }
        else if let m = match(#"^(.+) (?:pk|pick'?em|pick)$"#, l) { team = .spread(team: m[1], point: 0); name = m[1] }   // "Chiefs PK" (Nov 9)
        return team != nil && segment(name) ? nil : team
    }

    /// A stat word's value from a player's box line, per sport.
    static func statValue(_ row: [String: Double], _ stat: String, _ sport: String) -> Double? {
        let v = { (ks: [String]) in ks.reduce(0) { $0 + (row[$1] ?? 0) } }
        let has = { (k: String) in row[k] != nil }
        switch stat {
        case "passing yds": return has("passingYards") ? v(["passingYards"]) : nil
        case "rushing yds": return has("rushingYards") ? v(["rushingYards"]) : nil
        case "receiving yds": return has("receivingYards") ? v(["receivingYards"]) : nil
        case "rush + rec yds": return has("rushingYards") || has("receivingYards") ? v(["rushingYards", "receivingYards"]) : nil
        // Nov 9: a player's own scores, rushing and receiving
        case "touchdowns": return has("rushingTouchdowns") || has("receivingTouchdowns") ? v(["rushingTouchdowns", "receivingTouchdowns"]) : nil
        case "rushing tds": return has("rushingTouchdowns") ? v(["rushingTouchdowns"]) : nil
        case "receiving tds": return has("receivingTouchdowns") ? v(["receivingTouchdowns"]) : nil
        case "receptions": return has("receptions") ? v(["receptions"]) : nil
        case "passing tds": return has("passingTouchdowns") ? v(["passingTouchdowns"]) : nil
        case "points": return sport == "nhl" ? v(["goals", "assists"]) : has("points") ? v(["points"]) : nil
        case "rebounds": return has("rebounds") ? v(["rebounds"]) : nil
        case "assists": return has("assists") ? v(["assists"]) : sport == "soccer" && has("goalAssists") ? v(["goalAssists"]) : nil
        case "threes": return has("threePointFieldGoalsMade") ? v(["threePointFieldGoalsMade"]) : nil
        case "steals": return has("steals") ? v(["steals"]) : nil
        case "blocks": return has("blocks") ? v(["blocks"]) : nil
        case "pts + reb": return has("points") ? v(["points", "rebounds"]) : nil
        case "pts + ast": return has("points") ? v(["points", "assists"]) : nil
        case "reb + ast": return has("rebounds") ? v(["rebounds", "assists"]) : nil
        case "pts + reb + ast": return has("points") ? v(["points", "rebounds", "assists"]) : nil
        case "shots": return sport == "soccer" ? (has("totalShots") ? v(["totalShots"]) : nil) : has("shotsTotal") ? v(["shotsTotal"]) : nil
        case "shots on goal": return has("shotsTotal") ? v(["shotsTotal"]) : nil
        case "shots on target": return has("shotsOnTarget") ? v(["shotsOnTarget"]) : nil
        case "saves": return has("saves") ? v(["saves"]) : nil
        case "goals": return sport == "soccer" ? (has("totalGoals") ? v(["totalGoals"]) : nil) : has("goals") ? v(["goals"]) : nil
        case "stl + blk": return has("steals") || has("blocks") ? v(["steals", "blocks"]) : nil
        case "longest completion": return has("longCompletion") ? v(["longCompletion"]) : nil
        case "power play points": return v(["ppPoints"])        // play-by-play counts: none yet is 0
        case "power play goals": return v(["ppGoals"])
        case "field goals made": return has("fieldGoalsMade") ? v(["fieldGoalsMade"]) : nil    // basketball's shots, football's kicks
        default:
            // play-by-play stats (playStats): NHL periods' points are goals plus assists; halves are two quarters
            if let m = match(#"^([1-4])([qhp]) (points|rebounds|assists|threes|goals)$"#, stat), let n = Int(m[1]) {
                if m[2] == "p" { return (m[3] == "points" ? ["goals", "assists"] : [m[3]]).reduce(0) { $0 + (row["p\(n):\($1)"] ?? 0) } }
                let qs = m[2] == "h" ? (n == 1 ? [1, 2] : [3, 4]) : [n]
                return qs.reduce(0) { $0 + (row["q\($1):\(m[3])"] ?? 0) }
            }
            // Nov 6: ESPN's box keys (parseBox keeps both halves of "completions/passingAttempts")
            let keys = ["longest reception": "longReception", "longest rush": "longRushing", "rush attempts": "rushingAttempts",
                        "pass attempts": "passingAttempts", "completions": "completions", "interceptions": "interceptions",
                        "tackles": "totalTackles", "sacks": "sacks", "kicking points": "totalKickingPoints", "turnovers": "turnovers",
                        "free throws made": "freeThrowsMade", "offensive rebounds": "offensiveRebounds", "blocked shots": "blockedShots",
                        "hits": "hits", "fouls": "foulsCommitted"]
            guard let k = keys[stat], has(k) else { return nil }
            return v([k])
        }
    }

    private static let units = ["passing yds": "pass yds", "rushing yds": "rush yds", "receiving yds": "rec yds",
        "rush + rec yds": "yds", "receptions": "rec", "points": "pts", "rebounds": "reb", "assists": "ast", "threes": "3PM",
        "pts + reb": "P+R", "pts + ast": "P+A", "reb + ast": "R+A", "pts + reb + ast": "PRA", "shots on target": "SOT",
        "shots on goal": "SOG", "shots": "shots", "saves": "saves", "goals": "goals", "passing tds": "pass TD",
        "longest reception": "long rec", "longest rush": "long rush", "rush attempts": "carries", "pass attempts": "att",
        "completions": "cmp", "interceptions": "INT", "tackles": "tkl", "sacks": "sacks", "kicking points": "kick pts",
        "field goals made": "FGM", "turnovers": "TO", "stl + blk": "S+B", "free throws made": "FTM", "offensive rebounds": "OREB",
        "blocked shots": "BLK", "hits": "hits", "fouls": "fouls", "longest completion": "long cmp", "power play points": "PPP",
        "power play goals": "PPG", "touchdowns": "TD", "rushing tds": "rush TD", "receiving tds": "rec TD"]

    /// A game total or a team's total against its line; landing on a whole-number line at the final is a push (void), as
    /// the grader settles it, not a loss (Nov 9; live_legs.total_state).
    private static func totalState(_ total: Double, _ side: String, _ point: Double, final: Bool) -> (status: LegStatus, text: String, target: Double) {
        let over = total > point
        let status: LegStatus = final && total == point ? .void
            : side == "over" ? (over ? .won : final ? .lost : .live) : (over ? .lost : final ? .won : .live)
        return (status, status == .void ? "Push at \(js(total))" : "\(js(total)) of \(js(point))", side == "over" ? point.rounded(.down) + 1 : point)
    }

    private static let football: Set<String> = ["nfl", "ncaaf"]

    /// A first scorer leg (TD, basket, goal) from the play-by-play's mark: won once his is first, lost once someone else's
    /// is (or the game ends with none). live_legs.first_state.
    private static func firstState(_ row: [String: Double]?, _ box: LiveBox?, _ key: String, final: Bool, unit: String) -> (status: LegStatus, text: String, current: Double) {
        let mine = (row?[key] ?? 0) > 0, taken = (box?[game]?[key] ?? 0) > 0
        return (mine ? .won : taken || final ? .lost : .live,
                mine ? "Scored first" : taken ? "Someone else scored first" : final ? "No \(unit)" : "No \(unit) yet", mine ? 1 : 0)
    }

    private static let doubleCats = [("points", "pts"), ("rebounds", "reb"), ("assists", "ast"), ("steals", "stl"), ("blocks", "blk")]

    /// A double-double (n 2) or triple-double (n 3): web lib/live.ts doubleState.
    static func doubleState(_ row: [String: Double]?, n: Int, final: Bool) -> (status: LegStatus, current: Double, text: String) {
        let vals = doubleCats.map { (u: $0.1, v: row?[$0.0] ?? 0) }.enumerated()
            .sorted { $0.element.v != $1.element.v ? $0.element.v > $1.element.v : $0.offset < $1.offset }.map(\.element)
        let at10 = vals.filter { $0.v >= 10 }.count
        let keep = max(n, 2) + (n == 2 ? 1 : 0)
        let shown = vals.prefix(keep).enumerated().filter { $0.element.v > 0 || $0.offset < n }.map { "\(js($0.element.v)) \($0.element.u)" }.joined(separator: " · ")
        let short = vals.filter { $0.v < 10 }.prefix(max(n - at10, 0)).map { "\(js(10 - $0.v)) \($0.u)" }.joined(separator: ", ")
        let done = at10 >= n
        let text = done ? "Done: \(shown)" : row == nil ? "No stats yet" : "\(shown) · \(short) \(final ? "short" : "to go")"
        return (done ? .won : final ? .lost : .live, Double(min(at10, n)), text)
    }

    /// One leg's live state from its game and that game's box score.
    static func judge(_ label: String, _ g: GameLive?, _ box: LiveBox?, _ heads: LiveHeads? = nil, _ onCourt: [String]? = nil) -> LegLive {
        // the leg's picture: a team leg's logo, a player leg's headshot (matched as its stats are)
        var img: String? = nil, card: CardRef? = nil
        // a team's own total ("New York Knicks over 110.5 points", Nov 9): the team's score, not a player named after it
        var totalSide: String? = nil
        if let g, case .prop(let pl, _, _, _, _)? = parseLeg(label), box.flatMap({ findPlayer($0, pl) }) == nil,
           let s = sideOf(pl, g), teamMatch(pl, s == "home" ? g.home : g.away) >= 2 { totalSide = s }
        func teamPicture(_ side: String, _ g: GameLive) {
            let s = side == "home" ? g.home : g.away
            img = s.logo
            if g.sport != "ufc" { card = CardRef(kind: .team, name: s.name, abbr: s.abbr) }
        }
        switch parseLeg(label) {
        case .ml(let t)?, .spread(let t, _)?:
            if let g, let side = sideOf(t, g) { teamPicture(side, g) }
        case .prop(let pl, _, _, _, _)?, .td(let pl, _)?, .goalOrAssist(let pl)?, .double(let pl, _)?, .leader(let pl, _)?, .card(let pl)?, .first(let pl, _)?:
            if let g, let totalSide { teamPicture(totalSide, g); break }
            img = heads.flatMap { findPlayer($0, pl) }
            card = CardRef(kind: .player, name: pl)
        default: break
        }
        var base = LegLive(label: label, status: .unknown, gameKey: g?.key, img: img, card: card)
        if let onCourt, case .prop(let pl, _, _, _, _)? = parseLeg(label) {
            base.onCourt = findPlayer(Dictionary(uniqueKeysWithValues: onCourt.map { ($0, true) }), pl) != nil
        }
        func with(_ s: LegStatus, _ text: String, current: Double? = nil, target: Double? = nil, unit: String = "") -> LegLive {
            var x = base; x.status = s; x.text = text; x.current = current; x.target = target; x.unit = unit; return x
        }
        let p = parseLeg(label)
        guard let g else { return with(.pending, "Not live today") }
        guard let p else { return g.state == "pre" ? with(.pending, "Not started") : with(.unknown, "Not tracked") }
        let final = g.state == "post", pre = g.state == "pre"
        let hs = g.home.score ?? 0, as_ = g.away.score ?? 0
        let lead = { (side: String) in side == "home" ? hs - as_ : as_ - hs }
        let outcome = { (m: Double) -> LegStatus in final ? (m > 0 ? .won : m < 0 ? .lost : .void) : m > 0 ? .winning : m < 0 ? .losing : .tied }

        switch p {
        case .ml(let team):
            guard let s = sideOf(team, g) else { return with(.unknown, "Team not found") }
            if g.sport == "ufc" {
                if final { return with(g.winner == s ? .won : g.winner != nil ? .lost : .void, g.result ?? g.detail) }
                return with(pre ? .pending : .live, g.detail)
            }
            if pre { return with(.pending, "Not started") }
            // soccer's "to win" is 3-way: a draw loses it
            let st = outcome(lead(s)), d = lead(s)
            let word = d > 0 ? "Up" : d < 0 ? "Down" : "Level"
            return with(g.sport == "soccer" && st == .void ? .lost : st, d == 0 ? word : "\(word) \(js(abs(d)))", current: d)
        case .spread(let team, let point):
            guard let s = sideOf(team, g) else { return with(.unknown, "Team not found") }
            if pre { return with(.pending, "Not started") }
            let m = lead(s) + point      // Oct 24: "covering by -13.5" read wrong
            return with(outcome(m), m > 0 ? "Covering by \(js(m))" : m < 0 ? "Short by \(js(-m))" : "Right on the number", current: lead(s))
        case .bttsNo:
            if pre { return with(.pending, "Not started") }
            let both = hs > 0 && as_ > 0
            return with(both ? .lost : final ? .won : .live, both ? "Both scored" : "\(js(hs))-\(js(as_))")
        case .draw, .drawOr, .noDraw, .notWin:
            var side = "home"
            if case .drawOr(let team) = p {
                guard let s = sideOf(team, g) else { return with(.unknown, "Team not found") }
                side = s
            }
            if case .notWin(let team) = p {
                guard let s = sideOf(team, g) else { return with(.unknown, "Team not found") }
                side = s
            }
            if pre { return with(.pending, "Not started") }
            let d = lead(side)
            var hit = d >= 0
            if case .draw = p { hit = d == 0 }
            if case .noDraw = p { hit = d != 0 }
            if case .notWin = p { hit = d <= 0 }
            return with(final ? (hit ? .won : .lost) : hit ? .winning : .losing,
                        d == 0 ? "Level" : d > 0 ? "\(js(hs))-\(js(as_))" : "\(js(as_))-\(js(hs))")
        case .btts:
            if pre { return with(.pending, "Not started") }
            let both = hs > 0 && as_ > 0
            return with(both ? .won : final ? .lost : .live, both ? "Both scored" : "\(js(hs))-\(js(as_))")
        case .total(let side, let point):
            if pre { return with(.pending, "Not started", target: point) }
            let total = hs + as_, t = totalState(total, side, point, final: final)
            return with(t.status, t.text, current: total, target: t.target, unit: "total")
        default: break
        }
        // player legs
        if pre {
            if case .prop(_, let stat, _, let need, _) = p { return with(.pending, "Not started", current: 0, target: need, unit: units[stat] ?? stat) }
            if case .td = p { return with(.pending, "Not started", current: 0, target: 1, unit: "TD") }
            if case .double(_, let n) = p { return with(.pending, "Not started", current: 0, target: Double(n), unit: "at 10+") }
            if case .leader(_, let stat) = p { return with(.pending, "Not started", current: 0, unit: units[stat] ?? stat) }
            if case .card = p { return with(.pending, "Not started", current: 0, target: 1, unit: "card") }
            if case .first(_, let what) = p { return with(.pending, "Not started", current: 0, target: 1, unit: what) }
            return with(.pending, "Not started", current: 0, target: 1, unit: "G+A")
        }
        let who: String? = {
            switch p {
            case .prop(let pl, _, _, _, _), .td(let pl, _), .goalOrAssist(let pl), .double(let pl, _), .leader(let pl, _), .card(let pl), .first(let pl, _): return pl
            default: return nil
            }
        }()
        let row = who.flatMap { pl in box.flatMap { findPlayer($0, pl) } }
        if row == nil, case .prop(_, let stat, let side, _, let point) = p, let totalSide {
            guard stat == "points" || stat == "goals" else { return with(.unknown, "Not tracked") }
            let t = totalState((totalSide == "home" ? g.home : g.away).score ?? 0, side, point, final: final)
            return with(t.status, t.text, current: (totalSide == "home" ? g.home : g.away).score ?? 0, target: t.target, unit: units[stat] ?? stat)
        }
        let players = (box ?? [:]).keys.filter { $0 != game }
        if row == nil && players.isEmpty && final { return with(.unknown, "No box score") }     // never a guess
        // Nov 9: a basketball, hockey or soccer box lists everyone who dressed, so a player missing from it didn't play (yet):
        // void at the final, as the books settle it; football's leaves out players with no stats, so there he counts 0
        if row == nil && !players.isEmpty && !football.contains(g.sport) {
            var taken = false
            if case .first(_, let what) = p { taken = (box?[game]?[what == "basket" ? "firstBasket" : "firstGoal"] ?? 0) > 0 }
            if !taken { return final ? with(.void, "Didn't play") : with(.pending, "Not in the box score yet", current: 0) }
        }
        switch p {
        case .td(let player, let first):
            let row = box.flatMap { findPlayer($0, player) }
            let tds = row.map { ($0["rushingTouchdowns"] ?? 0) + ($0["receivingTouchdowns"] ?? 0) } ?? 0
            if first {          // Nov 6: the scoring plays say whose TD was first (it read "Scored: check if first")
                let f = firstState(row, box, "firstTd", final: final, unit: "TD")
                return with(f.status, f.text, current: f.current, target: 1, unit: "TD")
            }
            return with(tds >= 1 ? .won : final ? .lost : .live, tds > 0 ? "Scored" : "No TD yet", current: tds, target: 1, unit: "TD")
        case .double(let player, let n):
            let d = doubleState(box.flatMap { findPlayer($0, player) }, n: n, final: final)
            return with(d.status, d.text, current: d.current, target: Double(n), unit: "at 10+")
        case .goalOrAssist(let player):
            let row = box.flatMap { findPlayer($0, player) }
            let n = row.map { ($0["totalGoals"] ?? 0) + ($0["goalAssists"] ?? 0) } ?? 0
            return with(n >= 1 ? .won : final ? .lost : .live, n > 0 ? "Done" : "Not yet", current: n, target: 1, unit: "G+A")
        case .first(let player, let what):
            let f = firstState(box.flatMap { findPlayer($0, player) }, box, what == "basket" ? "firstBasket" : "firstGoal", final: final, unit: what)
            return with(f.status, f.text, current: f.current, target: 1, unit: what)
        case .card(let player):
            let row = box.flatMap { findPlayer($0, player) }
            let n = row.map { ($0["yellowCards"] ?? 0) + ($0["redCards"] ?? 0) } ?? 0
            return with(n >= 1 ? .won : final ? .lost : .live, n > 0 ? "Carded" : final ? "No card" : "No card yet", current: n, target: 1, unit: "card")
        case .leader(let player, let stat):        // one player's count against everyone else's in the box (live_legs.judge)
            let row = box.flatMap { findPlayer($0, player) }
            let mine = row.flatMap { statValue($0, stat, g.sport) } ?? 0
            // everyone else: drop his own line once (rows are values, so two players on the same numbers are equal; Nov 6)
            var others = Array((box ?? [:]).values)
            if let row, let i = others.firstIndex(of: row) { others.remove(at: i) }
            let best = others.map { statValue($0, stat, g.sport) ?? 0 }.max() ?? 0
            let ahead = mine - best
            // a tie for the most is a dead heat: the books pay a share, so it's a win (as the grader reads it) that rollup
            // never settles at the full price (Nov 9)
            if final && ahead == 0 && mine > 0 {
                var x = with(.won, "Dead heat at \(js(mine))", current: mine, target: best, unit: units[stat] ?? stat)
                x.deadHeat = true
                return x
            }
            let status: LegStatus = final ? (ahead > 0 ? .won : .lost) : ahead > 0 ? .winning : ahead == 0 && mine > 0 ? .tied : .losing
            return with(status, ahead > 0 ? "Most, by \(js(ahead))" : ahead == 0 && mine > 0 ? "Tied for most at \(js(mine))" : "\(js(-ahead)) behind the leader",
                        current: mine, target: best + (ahead <= 0 ? 1 : 0), unit: units[stat] ?? stat)
        case .prop(let player, let stat, let side, let need, let point):
            let row = box.flatMap { findPlayer($0, player) }
            let cur = row.flatMap { statValue($0, stat, g.sport) } ?? 0      // not in the box yet = 0 (hasn't recorded one)
            let unit = units[stat] ?? stat
            if final && cur == point { return with(.void, "Push at \(js(cur))", current: cur, target: point, unit: unit) }   // a whole-number line, exactly
            if side == "over" {
                let hit = cur >= need
                return with(hit ? .won : final ? .lost : .live, hit ? "Hit" : final ? "Missed by \(js(need - cur))" : "\(js(need - cur)) to go",
                            current: cur, target: need, unit: unit)
            }
            let busted = cur > point
            return with(busted ? .lost : final ? .won : .live,
                        busted ? "Over the line" : final ? "Stayed under" : "\(js((point - cur + 1).rounded(.down))) of room",
                        current: cur, target: point, unit: unit)
        default: return base
        }
    }

    // MARK: one bet

    static func rollup(_ legs: [LegLive], _ games: [GameLive]) -> BetLive {
        let lost = legs.contains { $0.status == .lost }
        let settled = legs.filter { $0.status == .won || $0.status == .void }.count
        let status = lost ? "lost" : !legs.isEmpty && settled == legs.count ? "won" : games.contains { $0.state != "pre" } ? "live" : "pending"
        // settled from the live state alone (Mike, Oct 23): any lost leg, or every leg won outright (a voided leg's reduced
        // price is the grader's to work out, so a win with a void waits for it)
        // a dead heat ("most X" tied) pays a share too (Nov 9)
        let settle: String? = lost ? "lost" : !legs.isEmpty && legs.allSatisfy { $0.status == .won && $0.deadHeat != true } ? "won" : nil
        return BetLive(games: games, legs: legs, status: status, hit: legs.filter { $0.status == .won }.count, total: legs.count, settle: settle)
    }

    /// A leg's sport (and soccer league) from its game ref: "nhl:2026020162", "2026_07_NE_CHI", "nba|NYK|BOS|tip",
    /// "epl|Home|Away|kickoff", "ufc:<event>:<fight>".
    static func refSport(_ ref: String?) -> (sport: String?, league: String?) {
        let s = ref ?? ""
        if s.contains("|") {
            let head = s.components(separatedBy: "|")[0]
            return head == "nba" ? ("nba", nil) : soccer[head] != nil ? ("soccer", head) : (nil, nil)
        }
        let head = s.components(separatedBy: ":")[0]
        if ["nhl", "ncaaf", "ncaab", "ufc", "nba", "nfl"].contains(head) && s.contains(":") { return (head, nil) }
        if s.range(of: #"^\d{4}_\d{2}_"#, options: .regularExpression) != nil { return ("nfl", nil) }
        return (nil, nil)
    }

    private static func sportOf(_ key: String?) -> (sport: String?, league: String?) {
        let k = (key ?? "").lowercased()
        if soccer[k] != nil { return ("soccer", k) }
        return (!k.isEmpty && k != "mixed" ? k : nil, nil)
    }

    private static func labelOf(_ l: JSON) -> String { l.string ?? l["label"].string ?? "" }

    /// A bet's games and the legs on each: a saved parlay's `games`, else its fun ticket's games, else one group.
    static func groups(_ b: LiveBetRow, tickets: [String: JSON]) -> [LiveGroup] {
        let games = b.games?.array ?? []
        if !games.isEmpty {
            return games.map { g in
                let ref = g["game_ref"].string
                let r = refSport(ref), s = r.sport != nil ? r : sportOf(b.sport ?? b.league)
                // its own kickoff: the ref's time, else the games table's by its id (Nov 9)
                let start = BetMath.refTime(ref) ?? BetMath.refGameId(ref).flatMap { b.game_starts?[$0] }
                return LiveGroup(sport: s.sport, league: s.league, matchup: g["matchup"].string ?? "", legs: g["legs"].array.map(labelOf),
                                 start: start, ref: ref)
            }
        }
        let t = b.sgp_id.flatMap { tickets[$0] }
        if let tg = t?["games"].array, !tg.isEmpty {
            return tg.map { g in
                let r = refSport(g["game_ref"].string), s = r.sport != nil ? r : sportOf(t?["_sport"].string ?? b.sport)
                return LiveGroup(sport: s.sport, league: s.league, matchup: g["matchup"].string ?? "",
                                 legs: g["legs"].array.map(labelOf), start: g["commence_time"].string, ref: g["game_ref"].string)
            }
        }
        let legs = !(b.legs ?? []).isEmpty ? b.legs! : b.label.map { [$0] } ?? []
        let matchup = t?["matchup"].string ?? t?["_matchup"].string ?? b.matchup ?? ""
        let s = sportOf(b.league ?? b.sport ?? t?["_sport"].string)
        return [LiveGroup(sport: s.sport, league: s.league, matchup: matchup, legs: legs, start: b.pick_commence_time ?? b.ticket_commence_time)]
    }

    private static let ymdFormat: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = Fmt.et
        f.dateFormat = "yyyyMMdd"
        return f
    }()
    /// An Eastern date, "YYYYMMDD".
    static func ymd(_ d: Date) -> String { ymdFormat.string(from: d) }

    /// Yesterday's and today's Eastern dates (a late game can run past midnight).
    static func days(_ now: Date = Date()) -> [String] { [ymd(BetMath.etShift(now, days: -1)), ymd(now)] }

    /// The Eastern days to look for a group's game (web searchDays, live_legs.search_days; tests/fixtures/live_legs.json
    /// "days"): its game's day and the next (late games run past midnight) when the start is known (the group's, the
    /// bet's, the time in its ref, or for a one-game bet its first kickoff); else the day it was placed and the next, and
    /// for an open bet yesterday and today too. Nov 9: an open bet looked only at yesterday and today, so a game two days
    /// back that wasn't graded yet (Mike's Georgia slip), or one tomorrow, had no tracker, in Live and in Friends.
    static func searchDays(_ b: LiveBetRow, _ grp: LiveGroup, open: Bool, now: Date = Date(), single: Bool = true) -> [String] {
        let start = grp.start ?? b.pick_commence_time ?? b.ticket_commence_time ?? BetMath.refTime(grp.ref) ?? (single ? b.game_start : nil)
        if let t = start.flatMap({ Models.date($0) }) { return [ymd(t), ymd(BetMath.etShift(t, days: 1))] }
        var out: [String] = []
        if let p = b.placed_at.flatMap({ Models.date($0) }) { out = [ymd(p), ymd(BetMath.etShift(p, days: 1))] }
        if open || out.isEmpty { out += days(now) }
        return Array(Set(out)).sorted()
    }

    /// The days a settled bet's game can be on (searchDays for a settled one-game bet).
    static func daysOf(_ b: LiveBetRow, _ grp: LiveGroup) -> [String] { searchDays(b, grp, open: false) }

    /// Bets settled from the live tracker (Mike, Oct 23: lost or won live moves to Settled before the worker grades it):
    /// the status says won or lost (pick_status if it has one, else ticket_status), flagged as not graded yet. A graded
    /// bet is left alone: the worker's result replaces the live one.
    static func markLiveSettled(_ bets: [MyBet], _ settled: [String: String]) -> [MyBet] {
        bets.map { b in
            guard let s = settled[b.betId], !BetMath.isSettled(b) else { return b }
            var x = b
            if x.pickStatus != nil { x.pickStatus = s } else { x.ticketStatus = s }
            x.liveSettled = s
            return x
        }
    }
}

/// ESPN JSON through a shared cache per URL.
actor ESPN {
    static let shared = ESPN()
    private var cache: [String: (at: Date, ttl: TimeInterval, task: Task<JSON?, Never>)] = [:]
    private let live: TimeInterval = 15
    private let fetch: @Sendable (String) async -> JSON?
    private let clock: @Sendable () -> Date

    static let doneTTL: TimeInterval = 6 * 3600    // a finished game's board or box score never changes

    init(fetch: @escaping @Sendable (String) async -> JSON? = ESPN.network, clock: @escaping @Sendable () -> Date = { Date() }) {
        self.fetch = fetch
        self.clock = clock
    }

    private static let network: @Sendable (String) async -> JSON? = { url in
        guard let u = URL(string: url) else { return nil }
        var req = URLRequest(url: u)
        req.setValue("BetLab", forHTTPHeaderField: "User-Agent")
        req.cachePolicy = .reloadIgnoringLocalCacheData
        req.timeoutInterval = 10        // a stalled box score must not hold the tracker's whole poll (web: 8 s)
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return try? JSON.plainDecoder.decode(JSON.self, from: data)
    }

    /// ESPN JSON through a shared cache: 15 s (ESPN itself says max-age=10), or `ttl` for finished games. A copy answers
    /// only while it's young enough for both whoever saved it and whoever asks: the Games list saves today's boards for
    /// 6 hours (it wants logos), and that copy froze every live tracker until the app was closed (Nov 1, 2026). A failed
    /// fetch isn't kept: the next poll tries again.
    func get(_ url: String, ttl: TimeInterval? = nil) async -> JSON? {
        let want = ttl ?? live
        if let hit = cache[url], clock().timeIntervalSince(hit.at) < min(hit.ttl, want) { return await hit.task.value }
        let fetch = fetch
        let task = Task<JSON?, Never> { await fetch(url) }
        cache[url] = (clock(), want, task)
        if cache.count > 800 { cache = cache.filter { clock().timeIntervalSince($0.value.at) < $0.value.ttl } }
        let value = await task.value
        if value == nil, cache[url]?.task == task { cache[url] = nil }
        return value
    }
}

extension Live {
    /// Live (or final) state of bets: open ones from yesterday's and today's boards, `settled` ones from their own game
    /// days (web liveBets). {bet_id: BetLive}, and whether any game is in progress.
    static func liveBets(_ list: [LiveBetRow], tickets: [String: JSON], settled: Set<String> = [], now: Date = Date(),
                         get: @escaping @Sendable (String, TimeInterval?) async -> JSON? = { await ESPN.shared.get($0, ttl: $1) }) async -> (bets: [String: BetLive], live: Bool) {
        let yday = days(now)[0]
        // every bet at once, as the web's Promise.all: the ESPN cache shares a request already in flight, so many bets on
        // one game still cost one request (one at a time, the Settled tab's 40 bets took half a minute)
        @Sendable func board(_ sport: String, _ league: String?, _ days: [String]) async -> [GameLive] {
            var out: [GameLive] = []
            for d in days {
                guard let url = scoreboardURL(sport, league, day: d), let sb = await get(url, d < yday ? ESPN.doneTTL : nil) else { continue }
                out += parseBoard(sb, sport: sport)
            }
            return out
        }
        @Sendable func box(_ g: GameLive, _ league: String?) async -> (stats: LiveBox, heads: LiveHeads, onCourt: [String]?) {
            guard g.sport != "ufc", let p = path(g.sport, league),
                  let s = await get("\(base)/\(p)/summary?event=\(g.espnId)", g.state == "post" ? ESPN.doneTTL : nil) else { return ([:], [:], nil) }
            let hoops = ["nba", "ncaab", "wnba"].contains(g.sport) && g.state == "in"
            return (parseBox(s, sport: g.sport), parseHeads(s, sport: g.sport), hoops ? parseOnCourt(s) : nil)
        }
        @Sendable func one(_ b: LiveBetRow) async -> BetLive {
            var gs: [GameLive] = []
            var legs: [LegLive] = []
            let grps = groups(b, tickets: tickets)
            for grp in grps {
                let days = searchDays(b, grp, open: !settled.contains(b.bet_id), now: now, single: grps.count == 1)
                var game: GameLive? = nil, league = grp.league
                let tries: [(String, String?)] = grp.sport == "soccer" && league == nil ? soccerOrder.map { ("soccer", $0) }
                    : grp.sport.map { [($0, league)] } ?? guess.map { ($0, nil) }
                for (sport, lg) in tries {
                    game = findGame(await board(sport, lg, days), grp.matchup)
                    if game != nil { league = lg; break }
                }
                if let game, !gs.contains(where: { $0.key == game.key }) { gs.append(game) }
                let bx = game != nil && game!.state != "pre" ? await box(game!, league) : nil
                legs += grp.legs.map { judge($0, game, bx?.stats, bx?.heads, bx?.onCourt) }
            }
            return rollup(legs, gs)
        }
        let result = await withTaskGroup(of: (String, BetLive).self) { group in
            for b in list { group.addTask { (b.bet_id, await one(b)) } }
            var out: [String: BetLive] = [:]
            for await (id, live) in group { out[id] = live }
            return out
        }
        return (result, result.values.contains { $0.games.contains { $0.state == "in" } })
    }
}

extension Live {
    /// The ESPN scoreboard game for each of our games (logos, team colors, score and clock), for the Games tab and game
    /// pages (Mike, Oct 24: "make game tab sexier too as well as separate game pages"). One board per sport and Eastern
    /// day, through the shared cache; a game ESPN doesn't list is left out.
    /// `ttl`: the cache time (the Games list asks for logos, which don't change; a game page wants the live score).
    static func art(for games: [Game], ttl: TimeInterval? = nil,
                    get: @escaping @Sendable (String, TimeInterval?) async -> JSON? = { await ESPN.shared.get($0, ttl: $1) }) async -> [String: GameLive] {
        // where a game's board is: soccer games are stored as "soccer" without the competition, so every league's
        func where_(_ league: String) -> [(sport: String, league: String?)] {
            if league == "soccer" { return soccerOrder.map { ("soccer", $0) } }
            if soccer[league] != nil { return [("soccer", league)] }
            return paths[league] != nil ? [(league, nil)] : []
        }
        var keys: [String: (sport: String, league: String?, day: String)] = [:]
        for g in games {
            guard let t = Models.date(g.commenceTime) else { continue }
            let day = ymd(t)
            for w in where_(g.league) { keys["\(w.sport)|\(w.league ?? "")|\(day)"] = (w.sport, w.league, day) }
        }
        let boards = await withTaskGroup(of: (String, [GameLive]).self) { group in
            for (k, v) in keys {
                group.addTask {
                    guard let url = scoreboardURL(v.sport, v.league, day: v.day), let sb = await get(url, ttl) else { return (k, []) }
                    return (k, parseBoard(sb, sport: v.sport))
                }
            }
            var out: [String: [GameLive]] = [:]
            for await (k, b) in group { out[k] = b }
            return out
        }
        var out: [String: GameLive] = [:]
        for g in games {
            guard let t = Models.date(g.commenceTime) else { continue }
            let board = where_(g.league).flatMap { w in boards["\(w.sport)|\(w.league ?? "")|\(ymd(t))"] ?? [] }
            let matchup = g.away.flatMap { a in g.home.map { "\(a) @ \($0)" } } ?? g.matchup ?? ""
            if let hit = findGame(board, matchup) ?? findGame(board, g.matchup ?? "") { out[g.gameId] = hit }
        }
        // soccer games the scoreboards didn't place: their clubs from the directories (logos and colors, no score)
        let missing = games.filter { (g: Game) in out[g.gameId] == nil && (g.league == "soccer" || soccer[g.league] != nil) }
        if !missing.isEmpty {
            let clubs = await SoccerClubs.load(get: get)
            for g in missing {
                guard let h = g.home, let a = g.away else { continue }
                let side = { (n: String) -> LiveSide in
                    let c = SoccerClubs.find(n, in: clubs)
                    return LiveSide(name: n, abbr: c?.abbr ?? "", score: nil, logo: c?.logo, color: c?.color)   // our name, ESPN's art
                }
                out[g.gameId] = GameLive(key: g.gameId, sport: "soccer", espnId: "", state: "pre", detail: "", start: g.commenceTime ?? "",
                                         home: side(h), away: side(a))
            }
        }
        return out
    }
}

/// Every soccer club's logo and colors from ESPN's team directories (Mike, Oct 24: "find a way to resolve ALL soccer
/// logos + colors"). The scoreboards only list a day's games under each competition, and the books name clubs their own
/// way, so a club is found by name in the directories of the leagues and cups we bet plus their neighbors (second
/// divisions, the cup qualifiers' leagues), through `aliases` where the names differ. Checked Oct 24: all 196 clubs in
/// our soccer games resolve.
enum SoccerClubs {
    struct Club: Equatable { let name: String; let abbr: String; let logo: String?; let color: String? }

    static let leagues = ["eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "usa.1", "uefa.champions", "uefa.europa", "uefa.europa.conf",
                          "eng.2", "esp.2", "ita.2", "ger.2", "fra.2", "por.1", "ned.1", "bel.1", "tur.1", "sco.1", "gre.1",
                          "aut.1", "sui.1", "den.1", "nor.1", "swe.1", "cze.1", "cro.1", "pol.1", "srb.1", "rou.1", "bul.1",
                          "cyp.1", "isr.1", "ukr.1", "uefa.champions_qual", "uefa.europa_qual", "uefa.europa.conf_qual"]

    /// The books' names ESPN writes differently (plain form → ESPN's display name); Live.teamMatch reads it too:
    /// a slip's "Rennes" is ESPN's "Stade Rennais" (Oct 30: that game's legs never tracked).
    static let aliases: [String: String] = [
        "1 fc koln": "FC Cologne", "agf aarhus": "AGF", "athletic bilbao": "Athletic Club",
        "brighton and hove albion": "Brighton & Hove Albion", "fc copenhagen": "F.C. København", "hamburger sv": "Hamburg SV",
        "hapoel be er sheva": "Hapoel Be'er", "los angeles fc": "LAFC", "new york red bulls": "Red Bull New York",
        "omonoia fc": "Omonia Nicosia", "pfc cska sofia": "CSKA Sofia", "pfc levski sofia": "Levski Sofia",
        "sporting lisbon": "Sporting CP", "union saint gilloise": "Union St.-Gilloise", "universitatea craiova": "CSU Craiova",
        "inter milan": "Internazionale", "fc iberia 1999": "Iberia 1999", "rennes": "Stade Rennais",
        "olympiakos piraeus": "Olympiacos", "hearts": "Heart of Midlothian", "fc nordsjaelland": "FC Nordsjælland",
        "koln": "FC Cologne", "copenhagen": "F.C. København",
    ]
    private static let generic: Set<String> = ["fc", "cf", "sc", "ac", "afc", "club", "city", "united", "real", "de", "sporting",
        "athletic", "the", "of", "st", "fk", "sk", "nk", "cd", "ud", "sd", "rc", "as", "jk", "bc", "tc", "aif", "if", "bk", "sv",
        "vfb", "vfl", "tsg", "fsv"]

    /// Lowercase ASCII words: accents off, ø/ł/æ/ß spelled out, "&" as "and".
    static func plain(_ s: String) -> String {
        let t = s.lowercased().replacingOccurrences(of: "ø", with: "o").replacingOccurrences(of: "ł", with: "l")
            .replacingOccurrences(of: "æ", with: "ae").replacingOccurrences(of: "ß", with: "ss").replacingOccurrences(of: "&", with: " and ")
        return Live.plain(t)
    }
    private static func core(_ p: String) -> String { p.split(separator: " ").map(String.init).filter { !generic.contains($0) }.joined(separator: " ") }
    private static func strong(_ p: String) -> Set<String> { Set(p.split(separator: " ").map(String.init).filter { $0.count >= 4 && !generic.contains($0) }) }

    /// Clubs by every name form ESPN gives (display, short, name, location), from directory JSON.
    static func index(_ directories: [JSON]) -> [String: Club] {
        var out: [String: Club] = [:]
        for d in directories {
            for t in d["sports"][0]["leagues"][0]["teams"].array {
                let x = t["team"]
                let club = Club(name: x["displayName"].string ?? "", abbr: x["abbreviation"].string ?? "",
                                logo: x["logos"][0]["href"].string, color: Live.teamColor(x["color"].string, x["alternateColor"].string))
                for n in [x["displayName"], x["shortDisplayName"], x["name"], x["location"]].compactMap(\.string) where !n.isEmpty {
                    let k = plain(n)
                    if out[k] == nil { out[k] = club }
                }
            }
        }
        return out
    }

    /// A club by our name: an alias, the exact name, the name without generic words, else one club sharing a strong word.
    static func find(_ name: String, in index: [String: Club]) -> Club? {
        let p = plain(name)
        if let a = aliases[p], let c = index[plain(a)] { return c }
        if let c = index[p] { return c }
        let cp = core(p)
        if !cp.isEmpty, let c = index[cp] ?? index.first(where: { core($0.key) == cp })?.value { return c }
        let sw = strong(p)
        guard !sw.isEmpty else { return nil }
        var hits: [String: Club] = [:]
        for (k, c) in index where !sw.isDisjoint(with: strong(k)) { hits[c.name] = c }
        return hits.count == 1 ? hits.first!.value : nil
    }

    /// The directories, through the shared cache for a day (clubs' logos don't change mid-season).
    static func load(get: @escaping @Sendable (String, TimeInterval?) async -> JSON? = { await ESPN.shared.get($0, ttl: $1) }) async -> [String: Club] {
        let dirs = await withTaskGroup(of: JSON?.self) { group in
            for l in leagues { group.addTask { await get("\(Live.base)/soccer/\(l)/teams?limit=300", 86_400) } }
            var out: [JSON] = []
            for await d in group { if let d { out.append(d) } }
            return out
        }
        return index(dirs)
    }
}
