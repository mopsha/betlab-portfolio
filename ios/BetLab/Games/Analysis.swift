import SwiftUI

// A game's analysis (game_analysis rows: nfl_preview, ncaaf_preview, nhl, soccer, nba, ufc, nfl_fun), drawn as the web
// game page draws it (web/components/games/Analysis.tsx): a header line per league, badges, then folded sections.
// The shared sections come first (the story, matchups, who's hurt, weather, data notes); each league's stat
// tables are still web-only.

struct AnalysisFold: Identifiable {
    let key: String
    let title: String
    var n: Int? = nil
    let body: AnyView
    var id: String { key }
}

enum GameAnalysis {
    /// A prop's Novig over / under (web novigOu; novig_parlays.attach_tables, Oct 28): a side with $50+ behind it, green
    /// when it's priced above the sharp chance.
    static func novigOu(_ x: JSON) -> TCell {
        let o = x["nv_over"].double, u = x["nv_under"].double
        guard o != nil || u != nil else { return TCell(text: "—") }
        let good = (x["nv_ev_over"].double ?? -1) >= 0 || (x["nv_ev_under"].double ?? -1) >= 0
        return TCell(text: "\(o.map { Fmt.am($0) } ?? "—") / \(u.map { Fmt.am($0) } ?? "—")", color: good ? .green : nil)
    }

    private static func num(_ x: Double?, _ d: Int = 1) -> String {
        guard let x else { return "—" }
        return String(format: "%.\(d)f", x).replacingOccurrences(of: "-", with: Fmt.minus)
    }
    private static func trimmed(_ x: Double) -> String { String(format: "%g", (x * 10).rounded() / 10) }

    /// The line under the matchup: the market's line, our read, and the like.
    static func meta(_ an: [String: JSON]) -> [String] {
        if let g = an["nfl_preview"] {
            var out: [String] = []
            let m = g["market"], o = g["ours"], teams = g["teams"].array
            if let sp = m["spread_home"].double {
                let fav = sp > 0 ? (teams[safe: 1]?["name"].string ?? g["home"].string ?? "") : (teams.first?["name"].string ?? g["away"].string ?? "")
                out.append("\(fav) \(Fmt.minus)\(trimmed(abs(sp))) · total \(m["total"].string ?? "—")")
                if let ap = m["away_points"].double, let hp = m["home_points"].double {
                    out.append("Market \(g["away"].string ?? "") \(Int(ap.rounded())), \(g["home"].string ?? "") \(Int(hp.rounded()))")
                }
            }
            if let mg = o["margin"].double { out.append("Our ratings: \(mg > 0 ? g["home"].string ?? "" : g["away"].string ?? "") by \(num(abs(mg)))") }
            return out
        }
        if let g = an["ncaaf_preview"] {
            var out: [String] = []
            let m = g["market"], o = g["ours"]
            if let sp = m["spread_home"].double {
                out.append("\(sp > 0 ? g["home"].string ?? "" : g["away"].string ?? "") \(Fmt.minus)\(trimmed(abs(sp))) · total \(m["total"].string ?? "—")")
            }
            if let mg = o["margin"].double {
                out.append("Our read: \(mg > 0 ? g["home"].string ?? "" : g["away"].string ?? "") by \(num(abs(mg))), \(num(o["total"].double, 0)) pts")
            }
            return out
        }
        if let g = an["nhl"] {
            var out: [String] = []
            let L = g["line"], Mo = g["model"]
            if let mlh = L["ml_home"].double {
                let favHome = (L["p_home"].double ?? Mo["p_home"].double ?? 0) >= 0.5
                out.append("\(favHome ? g["home"].string ?? "" : g["away"].string ?? "") \(Fmt.am(favHome ? mlh : L["ml_away"].double)) · total \(L["total"].string ?? "—")")
            }
            out.append("Our model: \(g["home"].string ?? "") \(Fmt.pct(Mo["p_home"].double)) to win, \(num(Mo["exp_total"].double)) goals")
            return out
        }
        if let g = an["soccer"] {
            var out: [String] = []
            if let c = g["competition"].string { out.append(c) }
            let fav = g["lines"].array.filter { $0["side"].string != "Draw" }.max { ($0["p_market"].double ?? 0) < ($1["p_market"].double ?? 0) }
            if let f = fav { out.append("\(f["side"].string ?? "") \(Fmt.pct(f["p_market"].double)) to win") }
            let t = g["analysis"]["teams"].array
            if let hs = t[safe: 0]?["shots"].double, let as_ = t[safe: 1]?["shots"].double { out.append("Shots projected \(num(hs, 0))–\(num(as_, 0))") }
            return out
        }
        if let g = an["nba"] {
            var out: [String] = []
            if let sp = g["spread_home"].double {
                let fav = sp >= 0 ? g["home"].string ?? "" : g["away"].string ?? ""
                out.append("\(fav) \(abs(sp) < 0.25 ? "pick'em" : "\(Fmt.minus)\(trimmed(abs(sp)))") · total \(g["total"].string ?? "—")")
            }
            let tv = g["national_tv"].array.compactMap(\.string)
            if !tv.isEmpty { out.append("National TV: \(tv.joined(separator: ", "))") }
            let m = g["model"]
            if let mg = m["margin"].double {
                let out_ = m["key_out"].int ?? 0
                out.append("Our model: \(mg >= 0 ? g["home"].string ?? "" : g["away"].string ?? "") by \(trimmed(abs(mg))), \(trimmed(m["total"].double ?? 0)) points"
                           + (out_ > 0 ? " (\(out_) key player\(out_ > 1 ? "s" : "") out, not adjusted)" : ""))
            }
            return out
        }
        if let g = an["ufc"] {       // segment, weight class and rounds (web ufcMeta)
            let wc = g["weight_class"].string
            return [g["segment"].string, g["title"].bool == true ? wc.map { "\($0) title fight" } : wc,
                    g["rounds"].int.flatMap { $0 != 0 ? "\($0) rounds" : nil }].compactMap { $0 }.filter { !$0.isEmpty }
        }
        return []
    }

    /// Warnings for the header: a new QB, an unconfirmed goalie, a back-to-back, soccer lineups and rotation.
    static func badges(_ an: [String: JSON]) -> [String] {
        var out: [String] = []
        if let s = an["soccer"]?["analysis"] {
            if s["lineup"].string == "expected" { out.append("Lineups not out yet: last XIs shown") }
            for t in s["teams"].array {
                let r = t["rotation"], missing = r["missing"].array.compactMap(\.string)
                if !missing.isEmpty { out.append("\(t["team"].string ?? "") without \(missing.prefix(2).joined(separator: ", "))") }
                else if let c = r["changes"].int, c >= 4 { out.append("\(t["team"].string ?? ""): \(c) changes") }
            }
        }
        for t in an["nfl_preview"]?["teams"].array ?? [] where t["qb"]["change"].bool == true {
            out.append("New QB: \(t["qb"]["name"].string ?? "")")
        }
        for t in an["nhl"]?["teams"].array ?? [] {
            if let st = t["goalie_status"].string, st != "confirmed" { out.append("\(t["team"].string ?? "") goalie \(st)") }
            if t["b2b"].bool == true { out.append("\(t["team"].string ?? "") on a back-to-back") }
        }
        return out
    }

    /// The page's analysis: `top` sections shown open under the bets, `folds` folded below (web game page).
    static func sections(_ an: [String: JSON]) -> (top: [AnalysisFold], folds: [AnalysisFold]) {
        if let g = an["nfl_preview"] { return (nflTop(g), nflFolds(g, an["nfl_fun"])) }
        if let g = an["ncaaf_preview"] { return (ncaafTop(g), ncaafFolds(g)) }
        if let g = an["nhl"] { return (nhlTop(g), nhlFolds(g)) }
        if let g = an["soccer"] { return (soccerTop(g), soccerFolds(g)) }
        if let g = an["nba"] { return (nbaTop(g), nbaFolds(g)) }
        if let g = an["ufc"] { return (ufcTop(g), ufcFolds(g)) }
        return ([], [])
    }

    private static func fold<V: View>(_ key: String, _ title: String, n: Int? = nil, @ViewBuilder _ body: () -> V) -> AnalysisFold {
        AnalysisFold(key: key, title: title, n: n, body: AnyView(VStack(alignment: .leading, spacing: 10) { body() }))
    }

    private static func prose(_ s: String) -> some View { Text(s).font(.footnote).frame(maxWidth: .infinity, alignment: .leading) }

    private static func edgesView(_ g: JSON) -> some View {
        let edges = g["matchups"].array.compactMap { m in m["text"].string.map { ($0, m["size"].double) } }
        return VStack(alignment: .leading, spacing: 8) { ForEach(edges, id: \.0) { EdgeRow(text: $0.0, size: $0.1) } }
    }

    private static func hurt(_ g: JSON, names: [String: String] = [:]) -> (view: HurtList, n: Int)? {
        let injured = g["injuries"].object.filter { !$0.value.array.isEmpty }.sorted { $0.key < $1.key }
        let effects = g["injury_effects"].object.values.compactMap(\.string).sorted()
        guard !injured.isEmpty || !effects.isEmpty else { return nil }
        return (HurtList(teams: injured.map { (names[$0.key] ?? $0.key, $0.value.array) }, effects: effects),
                injured.reduce(0) { $0 + $1.value.array.count })
    }

    private static func weatherAndNotes(_ g: JSON) -> [AnalysisFold] {
        var out: [AnalysisFold] = []
        if let w = g["weather"]["text"].string { out.append(fold("weather", "Weather") { prose(w) }) }
        let notes = g["notes"].array.compactMap(\.string)
        if !notes.isEmpty { out.append(fold("data", "Data notes") { ForEach(notes, id: \.self) { prose("• " + $0) } }) }
        return out
    }

    // MARK: - NFL

    private static let nflStat = ["receptions": "receptions", "receiving_yards": "receiving yds", "rushing_yards": "rushing yds",
                                  "passing_yards": "passing yds", "tds": "anytime TD"]

    static func nflTop(_ g: JSON) -> [AnalysisFold] {
        let lines = g["lines"].array.sorted { ($0["ev_if_right"].double ?? -9) > ($1["ev_if_right"].double ?? -9) }
        guard !lines.isEmpty else { return [] }
        let head = ["Line", "FanDuel", "Market", "With script", "EV if right"]
        let row = { (l: JSON) -> [TCell] in
            let ev = l["ev_if_right"].double
            return [TCell(text: Fmt.label(l["label"].string)), TCell(text: Fmt.am(l["price"].double)), TCell(text: Fmt.pct(l["p_market"].double)),
                    TCell(text: Fmt.pct(l["p_script"].double)), TCell(text: Fmt.signed(ev, 0), color: (ev ?? 0) >= 0 ? .green : .red)]
        }
        let whys = g["script_read"].object.values.compactMap { $0["why"].string }.sorted()
        return [fold("script", "Lines that fit the script") {
            if !whys.isEmpty { ReadLines(lines: whys) }
            StatTable(head: head, rows: lines.prefix(4).map(row))
            if lines.count > 4 {
                DisclosureGroup("All \(lines.count) lines") { StatTable(head: head, rows: lines.map(row)) }.font(.caption)
            }
            AboutView(text: "Market is the sharp books' no-vig chance of that side. With script moves it by this game's pass matchup and projected dropbacks, the one effect that held up on 2025 prop lines. A read to shop with, not a pick. Rushing props showed no such effect, so they aren't leaned.")
        }]
    }

    static func nflFolds(_ g: JSON, _ fun: JSON?) -> [AnalysisFold] {
        var out: [AnalysisFold] = []
        let teams = g["teams"].array
        let names = Dictionary(teams.compactMap { t in t["team"].string.map { ($0, t["name"].string ?? $0) } }, uniquingKeysWith: { a, _ in a })
        let funRead = (fun?["read"].object.values.compactMap(\.string) ?? []).sorted()
        if g["script"].string != nil || !funRead.isEmpty {
            out.append(fold("story", "How the game goes") {
                if !funRead.isEmpty { ReadLines(lines: funRead) }
                if let s = g["script"].string { prose(s) }
            })
        }
        if let a = teams[safe: 0], let h = teams[safe: 1] {
            let qb = { (t: JSON) in t["qb"].isNull ? "—" : "\(t["qb"]["change"].bool == true ? "NEW · " : "")\(t["qb"]["name"].string ?? "—")" }
            func r(_ label: String, _ f: (JSON) -> String, _ key: String? = nil) -> TapeRow {
                TapeRow(label: label, left: f(a), right: f(h), leftRank: key.flatMap { a[$0]["rank"].int }, rightRank: key.flatMap { h[$0]["rank"].int })
            }
            let rows = [TapeRow(label: "Starting QB", left: qb(a), right: qb(h)),
                        r("Plays", { Stat.fixed($0["plays"].double, 0) }), r("Seconds a play", { Stat.fixed($0["sec_per_play"].double, 1) }),
                        r("Pass rate", { Fmt.pct($0["pass_rate"].double) }), r("Dropbacks", { Stat.fixed($0["dropbacks"].double, 0) }),
                        r("Runs", { Stat.fixed($0["rushes"].double, 0) }),
                        r("Pass offense EPA", { Stat.epa($0["pass_off"]["value"].double) }, "pass_off"),
                        r("Run offense EPA", { Stat.epa($0["rush_off"]["value"].double) }, "rush_off"),
                        r("Pass defense EPA", { Stat.epa($0["pass_def"]["value"].double) }, "pass_def"),
                        r("Run defense EPA", { Stat.epa($0["rush_def"]["value"].double) }, "rush_def"),
                        r("Pressure allowed", { Fmt.pct($0["protection"]["value"].double) }, "protection"),
                        r("Pass rush", { Fmt.pct($0["pass_rush"]["value"].double) }, "pass_rush"),
                        r("Red-zone TDs", { Fmt.pct($0["red_zone"]["value"].double) }, "red_zone")]
            out.append(fold("tape", "Tale of the tape and matchups") {
                TapeView(left: a["name"].string ?? "", right: h["name"].string ?? "", rows: rows)
                edgesView(g)
            })
        }
        if let h = hurt(g, names: names) {
            out.append(fold("hurt", "Who's hurt", n: h.n) {
                h.view
                AboutView(text: "Regulars only (35%+ of snaps in the last three games) and any QB. Game status comes out Friday for Sunday games; before that it's the practice report. Missing line starters, a top target, a top pass rusher or defensive backs move the projection (tested on 2016–25).")
            })
        }
        let notes = g["matchup_notes"].array
        if !notes.isEmpty {
            out.append(fold("notes", "Matchup notes (unconfirmed)", n: notes.count) {
                ForEach(notes.indices, id: \.self) { i in
                    let n = notes[i]
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(Fmt.label(n["label"].string)) \(Fmt.am(n["price"].double))").font(.footnote.weight(.semibold))
                        Text("\(n["why"].string ?? "") · market \(Fmt.pct(n["p_market"].double)) · with matchup \(Fmt.pct(n["p_matchup"].double))")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                AboutView(text: "Receivers facing defenses that give up a lot (or very little) to their position, and deep threats against defenses that do or don't allow the deep ball. Promising on 2025 lines but not proven, so every one is tracked before it counts.")
            })
        }
        let reads = (fun?["reads"].array ?? []).map { r in (r, (r["p_model"].double ?? 0) - (r["p_market"].double ?? 0)) }
            .sorted { abs($0.1) > abs($1.1) }
        if !reads.isEmpty {
            out.append(fold("reads", "Our model vs. the market", n: reads.count) {
                StatTable(head: ["Player", "Stat", "Line", "Market over", "Our model", "Gap"],
                          rows: reads.map { r, gap in
                              [TCell(text: r["player"].string ?? ""), TCell(text: nflStat[r["stat"].string ?? ""] ?? r["stat"].string ?? ""),
                               TCell(text: r["line"].string ?? "—"), TCell(text: Fmt.pct(r["p_market"].double)), TCell(text: Fmt.pct(r["p_model"].double)),
                               TCell(text: Stat.pts(gap), color: gap >= 0 ? .green : .red)] },
                          highlight: Set(reads.indices.filter { abs(reads[$0].1) >= 0.12 }), leading: [0, 1])
                AboutView(text: "Our model's view of each over (usage, efficiency, game script, injuries) next to the market's no-vig chance. It has no weight in prices: it earns one only by beating real prop lines. Highlighted rows disagree by 12+ points; the market usually knows why.")
            })
        }
        return out + weatherAndNotes(g)
    }

    // MARK: - College football

    private static let cfbUnits = [("epa", "EPA / play"), ("success", "Success rate"), ("pass_epa", "Pass EPA"), ("rush_epa", "Run EPA"),
                                   ("line_yards", "Line yards"), ("stuff_rate", "Stuff rate"), ("explosiveness", "Explosiveness")]

    static func ncaafTop(_ g: JSON) -> [AnalysisFold] {
        if let blocked = g["ny_blocked"].string {
            return [fold("ny", "New York rules") { Text("\(blocked): analysis only (New York rules).").font(.footnote).foregroundStyle(.red) }]
        }
        let reads = g["read"].object.sorted { $0.key < $1.key }
        guard !reads.isEmpty else { return [] }
        return [fold("early", "Early read") {
            ForEach(reads, id: \.key) { k, r in
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        TagView(text: "\(k) read", color: .blue)
                        Text(Fmt.label(r["label"].string)).font(.subheadline.weight(.semibold))
                        Spacer()
                        if let p = r["price"].double { Text(Fmt.am(p)).font(.subheadline.monospacedDigit()) }
                    }
                    Text("**\(Stat.fixed(r["strength"].double))** SD · \(Stat.fixed(r["edge_pts"].double)) pts").font(.caption).foregroundStyle(.secondary)
                    let drivers = r["drivers"].array.compactMap(\.string)
                    if !drivers.isEmpty { Text(drivers.joined(separator: " · ")).font(.caption2).foregroundStyle(.secondary) }
                }
            }
            AboutView(text: "The efficiency read beat opening lines in 2022–25 (not closing lines), so it's strongest early in the week. Tracked, never priced, until this season's record agrees.")
        }]
    }

    static func ncaafFolds(_ g: JSON) -> [AnalysisFold] {
        var out: [AnalysisFold] = []
        let teams = g["teams"].array
        if let a = teams[safe: 0], let h = teams[safe: 1] {
            let at = a["team"].string ?? "", ht = h["team"].string ?? ""
            let cell = { (u: JSON) -> TCell in TCell(text: u["rank"].int.map(String.init) ?? "—") }
            out.append(fold("units", "Units and where it's decided") {
                StatTable(head: ["FBS rank (1 = best)", "\(at) O", "\(ht) D", "\(ht) O", "\(at) D"],
                          rows: cfbUnits.map { k, l in [TCell(text: l), cell(a["off_" + k]), cell(h["def_" + k]), cell(h["off_" + k]), cell(a["def_" + k])] })
                edgesView(g)
            })
        }
        if let w = g["weather"]["text"].string { out.append(fold("weather", "Weather") { prose(w) }) }
        return out
    }

    // MARK: - NHL

    private static let goalieStatus = ["confirmed": "Confirmed", "expected": "Expected", "probable": "Probable", "our guess": "Our guess"]

    static func nhlTop(_ g: JSON) -> [AnalysisFold] {
        var out: [AnalysisFold] = []
        let r = g["read"]
        if !r.isNull {
            out.append(fold("read", "Our read (tracked, not a pick)") {
                prose("\(Fmt.label(r["label"].string)) at \(Fmt.am(r["price"].double)): our model \(Fmt.pct(r["p_model"].double)), market no-vig \(Fmt.pct(r["p_market"].double)).")
            })
        }
        let fd = g["fanduel"].array
        if !fd.isEmpty {
            out.append(fold("books", "Your books vs. the sharp book") {
                StatTable(head: ["Side"] + Stat.myBooks + ["Sharp no-vig"],
                          rows: fd.map { o in [TCell(text: Fmt.label(o["label"].string))] + Stat.bookCells(o) + [TCell(text: Fmt.pct(o["p_market"].double))] })
                AboutView(text: "From today's odds pull (\(fd[0]["source"].string ?? "")). Each book's price with its EV under it. This is where the NHL card's picks come from: a book lagging the sharp price by 3%+ EV; a bet goes to the better book.")
            })
        }
        return out
    }

    static func nhlFolds(_ g: JSON) -> [AnalysisFold] {
        var out: [AnalysisFold] = []
        let teams = g["teams"].array
        let L = g["line"], Mo = g["model"]
        if let s = g["script"].string { out.append(fold("story", "How the game goes") { prose(s) }) }
        if let a = teams[safe: 0], let h = teams[safe: 1] {
            let at = a["team"].string ?? "", ht = h["team"].string ?? ""
            let goalie = { (t: JSON) in "\(t["goalie"].string ?? "—") (\(goalieStatus[t["goalie_status"].string ?? ""] ?? t["goalie_status"].string ?? ""))" }
            var rows = [TapeRow(label: "Record", left: a["record"].string ?? "—", right: h["record"].string ?? "—"),
                        TapeRow(label: "Goalie", left: goalie(a), right: goalie(h)),
                        TapeRow(label: "Save %", left: Fmt.pct(a["goalie_sv"].double, 1), right: Fmt.pct(h["goalie_sv"].double, 1)),
                        TapeRow(label: "Shots expected", left: Stat.fixed(a["shots"].double), right: Stat.fixed(h["shots"].double),
                                leftRank: a["ranks"]["off_shots"].int, rightRank: h["ranks"]["off_shots"].int),
                        TapeRow(label: "Goals expected", left: Stat.fixed(a["xg"].double, 2), right: Stat.fixed(h["xg"].double, 2))]
            let sa = g["special"][at], sh = g["special"][ht]
            if !sa.isNull {
                rows.append(TapeRow(label: "Power play", left: Fmt.pct(sa["pp_pct"].double), right: Fmt.pct(sh["pp_pct"].double),
                                    leftRank: sa["pp_rank"].int, rightRank: sh["pp_rank"].int))
                rows.append(TapeRow(label: "Penalty kill", left: Fmt.pct(sa["pk_pct"].double), right: Fmt.pct(sh["pk_pct"].double),
                                    leftRank: sa["pk_rank"].int, rightRank: sh["pk_rank"].int))
            }
            out.append(fold("tape", "Tale of the tape and matchups") {
                TapeView(left: at, right: ht, rows: rows)
                edgesView(g)
            })
            let gap = { (m: Double?, k: Double?) -> String in
                guard let m, let k else { return "—" }
                return abs(m - k) < 0.005 ? "0 pts" : Stat.pts(m - k)
            }
            let inv = { (x: Double?) in x.map { 1 - $0 } }
            let row = { (lab: String, mkt: Double?, mod: Double?, price: Double?) -> [TCell] in
                [TCell(text: lab), TCell(text: Fmt.am(price)), TCell(text: Fmt.pct(mkt)), TCell(text: Fmt.pct(mod)), TCell(text: gap(mod, mkt))]
            }
            var lineRows = [row("\(ht) ML", L["p_home"].double, Mo["p_home"].double, L["ml_home"].double),
                            row("\(at) ML", inv(L["p_home"].double), inv(Mo["p_home"].double), L["ml_away"].double)]
            if let t = L["total"].string {
                lineRows.append(row("Over \(t)", L["p_over"].double, Mo["p_over"].double, L["over"].double))
                lineRows.append(row("Under \(t)", inv(L["p_over"].double), inv(Mo["p_over"].double), L["under"].double))
            }
            let book = Stat.bookName(g["book"].string)
            out.append(fold("lines", "The lines and our model") {
                StatTable(head: [book.isEmpty ? "DraftKings" : book, "Price", "Market", "Our model", "Gap"], rows: lineRows)
                AboutView(text: (g["book"].string == "FanDuel" ? "FanDuel's prices; Market is Pinnacle's no-vig chance." : "DraftKings' prices from ESPN's free feed; Market is DraftKings' no-vig chance.")
                          + " Our model: expected shots and goals from each team's recent play against tonight's goalies. Our totals lose to the market's (2025-26), so trust its total over ours.")
            })
        }
        let props = g["props"].array
        if !props.isEmpty {
            let statName = ["shots": "shots", "points": "points", "saves": "saves"]
            out.append(fold("props", "Player props", n: props.count) {
                StatTable(head: ["Player", "FanDuel line", "Over / under", "Novig", "Market over", "Our model", "Best EV"],
                          rows: props.map { x in
                              let best = x["ev_over"].double.map { max($0, x["ev_under"].double ?? -1) }
                              return [TCell(text: "\(x["player"].string ?? "") \(x["team"].string ?? "")"),
                                      TCell(text: "\(statName[x["stat"].string ?? ""] ?? x["stat"].string ?? "") \(x["line"].string ?? "")"),
                                      TCell(text: "\(Fmt.am(x["fd_over"].double)) / \(x["fd_under"].double.map { Fmt.am($0) } ?? "—")"),
                                      Self.novigOu(x),
                                      TCell(text: Fmt.pct(x["p_market"].double)), TCell(text: Fmt.pct(x["p_model"].double)),
                                      TCell(text: best.map { Fmt.signed($0) } ?? "—", color: tone(best))] },
                          highlight: Set(props.indices.filter { !props[$0]["read"].isNull && props[$0]["read"].bool != false }), leading: [0, 1])
                AboutView(text: "Market over is the other books' no-vig chance at FanDuel's number. Our model is the machine-learning model (ice time, shot rates, lineup, tonight's game read); it has no weight in prices yet. Highlighted rows fit our game read. Every line is logged to train the model.")
            })
        }
        if let h = hurt(g) { out.append(fold("hurt", "Who's hurt", n: h.n) { h.view }) }
        return out
    }

    // MARK: - Soccer

    static func soccerTop(_ g: JSON) -> [AnalysisFold] {
        let lines = g["lines"].array
        guard !lines.isEmpty else { return [] }
        let moved = { (o: JSON) -> String in
            guard let f = o["first_price"].double, f != o["price"].double else { return "—" }
            return "\(Fmt.am(f)) → \(Fmt.am(o["price"].double))"
        }
        let src = Stat.bookName(lines[0]["source"].string)
        return [fold("books", "Your books vs. the sharp book") {
            StatTable(head: ["3-way"] + Stat.myBooks + ["Sharp no-vig", "FanDuel moved"],
                      rows: lines.map { o in
                          let side = o["side"].string ?? ""
                          return [TCell(text: side == "Draw" ? "Draw" : "\(side) win")] + Stat.bookCells(o)
                              + [TCell(text: Fmt.pct(o["p_market"].double)), TCell(text: moved(o))] })
            AboutView(text: "Regulation time (90 minutes plus stoppage). Each book's price, with its EV under it, against \(src.isEmpty ? "the sharp book" : src)'s no-vig chance at our latest pull. Soccer is market-only: our ratings lost to the close in every league, so a pick needs FanDuel to lag the sharp price by 3%+ EV. Every line is logged to test whether FanDuel lags at all.")
        }]
    }

    /// The 3-way in one place (analysis_soccer.moneyline; the web's moneylineRead): market now vs first look, the
    /// better book with its EV, and the lineup read when there is one.
    static func moneylineRead(_ an: JSON) -> [AnalysisFold] {
        let ml = an["moneyline"], sides = ml["sides"].array
        guard !sides.isEmpty else { return [] }
        let lineup = sides.contains { $0["p_lineup"].double != nil }
        let best = { (s: JSON) -> TCell in
            guard let price = s["best_price"].double else { return "—" }
            let ev = s["best_ev"].double
            return TCell(text: "\(Fmt.am(price)) \(Stat.bookName(s["best_book"].string))", sub: ev.map { Fmt.signed($0) },
                         subColor: (ev ?? 0) > 0 ? .green : nil)
        }
        let rows: [[TCell]] = sides.map { s in
            let side = s["side"].string ?? ""
            var row: [TCell] = [TCell(text: side == "Draw" ? "Draw" : "\(side) win"), TCell(text: Fmt.pct(s["p_market"].double)),
                                TCell(text: Fmt.pct(s["p_first"].double)), TCell(text: Stat.pts(s["move"].double)), best(s)]
            if lineup { row.append(TCell(text: Fmt.pct(s["p_lineup"].double))) }
            return row
        }
        let rec = ml["lineup_record"]
        var about = "Market: the sharp book's no-vig chances (regulation time) now and at our first look at this match; a move of 2+ points is the sharp money's direction. Best price: the better of FanDuel and DraftKings for each side (ties to FanDuel) with its EV against those chances; a pick needs 3%+. European games within 4 days either side come from the cup matches we price."
        if lineup {
            about += " Lineup read: the starters' expected goals on a score grid (\(ml["lineup"].string == "confirmed" ? "confirmed lineups" : "each team's last XI until the lineups are out")). It has no weight"
            if let n = rec["n"].int, n > 0 {
                about += ": on \(n) graded matches its log loss is \(Stat.fixed(rec["log_loss"].double, 3)) vs the market's \(Stat.fixed(rec["log_loss_mkt"].double, 3)) (lower is better)"
            }
            about += "."
        }
        return [fold("moneyline", "Moneyline read") {
            if let s = ml["summary"].string, !s.isEmpty { prose(s) }
            StatTable(head: ["3-way", "Market now", "First look", "Move", "Best price"] + (lineup ? ["Lineup read"] : []), rows: rows)
            AboutView(text: about)
        }]
    }

    static func soccerFolds(_ g: JSON) -> [AnalysisFold] {
        let an = g["analysis"]
        guard !an.isNull else { return [] }
        let teams = an["teams"].array
        if teams.isEmpty { return moneylineRead(an) }               // a match with only the moneyline read (no ESPN match yet)
        var out: [AnalysisFold] = []
        let confirmed = an["lineup"].string == "confirmed"
        if let s = an["script"].string { out.append(fold("story", "How the game goes") { prose(s) }) }
        out += moneylineRead(an)
        if let h = teams[safe: 0], let a = teams[safe: 1] {
            let rot = { (t: JSON) -> String in
                let r = t["rotation"]
                if r.isNull { return "—" }
                let c = r["changes"].int ?? 0, missing = r["missing"].array.compactMap(\.string)
                return "\(c) change\(c == 1 ? "" : "s")" + (missing.isEmpty ? "" : ", without \(missing.joined(separator: ", "))")
            }
            let days = { (x: Double?) in x.map { "\(Stat.fixed($0, 0)) days" } ?? "—" }
            var rows = [TapeRow(label: "Goals expected (market)", left: Stat.fixed(h["xg"].double, 2), right: Stat.fixed(a["xg"].double, 2))]
            if h["goals_model"].double != nil {
                rows.append(TapeRow(label: "Goals expected (lineup read)", left: Stat.fixed(h["goals_model"].double, 2), right: Stat.fixed(a["goals_model"].double, 2)))
            }
            rows += [TapeRow(label: "Shots projected", left: Stat.fixed(h["shots"].double), right: Stat.fixed(a["shots"].double)),
                     TapeRow(label: "On target projected", left: Stat.fixed(h["sot"].double), right: Stat.fixed(a["sot"].double)),
                     TapeRow(label: "Shots a game (last 10)", left: Stat.fixed(h["shots_for"].double), right: Stat.fixed(a["shots_for"].double),
                             leftRank: h["rank_for"].int, rightRank: a["rank_for"].int),
                     TapeRow(label: "Shots allowed (last 10)", left: Stat.fixed(h["shots_against"].double), right: Stat.fixed(a["shots_against"].double),
                             leftRank: h["rank_against"].int, rightRank: a["rank_against"].int),
                     TapeRow(label: "Rest", left: days(h["rest_days"].double), right: days(a["rest_days"].double))]
            if confirmed { rows.append(TapeRow(label: "Lineup", left: rot(h), right: rot(a))) }
            out.append(fold("tape", "Tale of the tape") {
                TapeView(left: h["team"].string ?? "", right: a["team"].string ?? "", sep: "vs", rows: rows)
                AboutView(text: "Goals expected: the sharp 1X2 and goals line fit to a score grid. Shots projected: our shots model on \(confirmed ? "tonight's lineups" : "each team's last XI (lineups come out about an hour before kickoff)"), plus substitutes. Ranks: this season in the league (1st = most shots, fewest allowed).")
            })
        }
        let r = an["goals_read"]
        if !r.isNull {
            let row = { (lab: String, mine: Double?, mkt: Double?) -> [TCell] in
                [TCell(text: lab), TCell(text: Fmt.pct(mkt)), TCell(text: Fmt.pct(mine)), TCell(text: mine != nil && mkt != nil ? Stat.pts(mine! - mkt!) : "—")]
            }
            out.append(fold("goals", "Goals read") {
                StatTable(head: ["", "Market", "Lineup read", "Gap"],
                          rows: [row("Over 2.5 goals", r["p_over25"].double, r["p_over25_mkt"].double),
                                 row("Both teams to score", r["p_btts"].double, r["p_btts_mkt"].double)])
                AboutView(text: "The lineup read starts from the market's expected goals and adjusts for who actually starts (each starter's expected goals from the shots model). \(confirmed ? "Lineups are confirmed." : "Lineups aren't out yet, so it uses each team's last XI.") It has no weight: every confirmed-lineup read is logged and checked against the market's log loss.")
            })
        }
        let shooters = an["shooters"].array
        if !shooters.isEmpty {
            let rung = { (s: JSON) -> JSON? in let r = s["fd_shots"].array; return r.first { $0["line"].double == 1.5 } ?? r.first }
            out.append(fold("shooters", "Likeliest shooters", n: shooters.count) {
                StatTable(head: ["Player", "Shots", "On target", "1+ shot", "FanDuel", "FanDuel fair", "Our model"],
                          rows: shooters.map { s in
                              let r = rung(s)
                              return [TCell(text: "\(s["player"].string ?? "") \(s["team"].string ?? "")"), TCell(text: Stat.fixed(s["shots"].double)),
                                      TCell(text: Stat.fixed(s["sot"].double)), TCell(text: Fmt.pct(s["p_shot"].double)),
                                      TCell(text: r.map { "\(Stat.fixed(($0["line"].double ?? 0) + 0.5, 0))+ shots \(Fmt.am($0["fd_price"].double))" } ?? "not posted",
                                            color: r == nil ? .secondary : nil),
                                      TCell(text: r.map { Fmt.pct($0["p_fd_fair"].double) } ?? "—"), TCell(text: r.map { Fmt.pct($0["p_model"].double) } ?? "—")] },
                          leading: [0, 4])
                AboutView(text: "Expected shots from our machine-learning model (each player's shot rate, minutes, role, his team's and the opponent's shot form, the market's expected goals). FanDuel fair: FanDuel's own shot ladder with its margin (about 16%) taken off. The model has no weight in prices yet: every FanDuel rung is logged and graded to test it.")
            })
            if shooters.contains(where: { $0["p_ga"].double != nil }) {
                let fdPrice = { (x: JSON) -> TCell in x.isNull ? TCell(text: "not posted", color: .secondary) : TCell(text: Fmt.am(x["fd_price"].double)) }
                out.append(fold("scorers", "Score or assist") {
                    StatTable(head: ["Player", "Score", "Assist", "Score or assist", "FanDuel score or assist", "FanDuel to score", "Pinnacle fair"],
                              rows: shooters.map { s in
                                  [TCell(text: "\(s["player"].string ?? "") \(s["team"].string ?? "")"), TCell(text: Stat.pctOdds(s["p_goal"].double)),
                                   TCell(text: Stat.pctOdds(s["p_assist"].double)), TCell(text: Stat.pctOdds(s["p_ga"].double)),
                                   fdPrice(s["fd_ga"]), fdPrice(s["fd_scorer"]), TCell(text: s["pin_scorer"].double.map { Stat.pctOdds($0) } ?? "—")] })
                    AboutView(text: "Our model's chances (fair odds in brackets): goals and assists per 90 minutes, role and minutes, both teams' form and the market's expected goals. A FanDuel price longer than our fair odds pays more than the model thinks it should (FanDuel has no sharp book to check it against here, and the model has no weight yet). Pinnacle fair: its no-vig scorer chance, the sharp price our scorer picks use.")
                })
            }
        }
        return out
    }

    // MARK: - NBA

    static func nbaTop(_ g: JSON) -> [AnalysisFold] {
        let m = g["model"]
        guard !m.isNull, let sp = g["spread_home"].double, let margin = m["margin"].double else { return [] }
        let home = g["home"].string ?? "", away = g["away"].string ?? ""
        let side = { (x: Double) in "\(x >= 0 ? home : away) by \(String(format: "%g", (abs(x) * 10).rounded() / 10))" }
        let gap = { (x: Double) in abs(x) < 0.05 ? "0 pts" : Stat.pts(x, 1, scale: 1) }
        var rows: [[TCell]] = [[TCell(text: "Margin"), TCell(text: side(sp)), TCell(text: side(margin)),
                                TCell(text: "\(gap(margin - sp)) \(margin - sp >= 0 ? home : away)")]]
        if let tot = g["total"].double, let mt = m["total"].double {
            rows.append([TCell(text: "Total"), TCell(text: String(format: "%g", tot)), TCell(text: String(format: "%g", (mt * 10).rounded() / 10)), TCell(text: gap(mt - tot))])
        }
        let outs = { (xs: [JSON]) in xs.map { "\($0["name"].string ?? "") (\(Int(($0["minutes"].double ?? 0).rounded())) min)" }.joined(separator: ", ") }
        let oa = m["out"]["away"].array, oh = m["out"]["home"].array
        return [fold("read", "Our read") {
            StatTable(head: ["", "Market", "Our model", "Gap"], rows: rows)
            AboutView(text: "Our team model: each team's offense and defense per 100 possessions, adjusted for opponents, and pace, from the last 400 days with recent games counting most, plus rest. It has no weight in prices: there were no past NBA lines to test it on, so every read is logged and graded against the closing line and the result." + (m["early"].bool == true ? " Early season: the ratings are mostly last season's, and rosters changed, so expect big gaps that mean little." : ""))
            if !oa.isEmpty || !oh.isEmpty {
                ReadLines(title: "Out tonight, and the read doesn't adjust for it",
                          lines: (oa.isEmpty ? [] : ["\(away): \(outs(oa))"]) + (oh.isEmpty ? [] : ["\(home): \(outs(oh))"])
                              + ["Our ratings come from the season so far; the market already prices these absences. Reads with key players out are tracked separately."])
            }
        }]
    }

    static func nbaFolds(_ g: JSON) -> [AnalysisFold] {
        var out: [AnalysisFold] = []
        let m = g["model"], home = g["home"].string ?? "", away = g["away"].string ?? ""
        let a = m["ranks"][away], h = m["ranks"][home]
        if !a.isNull && !h.isNull {
            let rest = { (t: String) in m["rest"][t].int.map { "\($0)d" } ?? "—" }
            out.append(fold("tape", "Tale of the tape") {
                TapeView(left: away, right: home, rows: [
                    TapeRow(label: "Points expected", left: Stat.fixed(m["away_points"].double), right: Stat.fixed(m["home_points"].double)),
                    TapeRow(label: "Offense", left: "", right: "", leftRank: a["off_ortg"].int, rightRank: h["off_ortg"].int),
                    TapeRow(label: "Defense", left: "", right: "", leftRank: a["def_ortg"].int, rightRank: h["def_ortg"].int),
                    TapeRow(label: "Pace", left: "", right: "", leftRank: a["pace"].int, rightRank: h["pace"].int),
                    TapeRow(label: "Rest", left: rest(away), right: rest(home))])
            })
        }
        let lines = g["lines"].array.sorted { abs($0["gap"].double ?? 0) > abs($1["gap"].double ?? 0) }
        if lines.isEmpty {
            out.append(fold("lines", "Player lines") {
                prose("FanDuel's player lines are priced 15 to 45 minutes before tip, once the starting lineups are out. They show up here then, with any lean, and the night's parlay tickets.")
            })
        } else {
            out.append(fold("lines", "Player lines", n: lines.count) {
                StatTable(head: ["Player", "FanDuel line", "Over / under", "Novig", "Market over", "Our model", "Gap", "Minutes"],
                          rows: lines.map { x in
                              let gap = x["gap"].double
                              return [TCell(text: "\(x["player"].string ?? "") \(x["team"].string ?? "")\(x["day_to_day"].bool == true ? " · day-to-day" : "")"),
                                      TCell(text: "\(x["label"].string ?? x["stat"].string ?? "") \(x["line"].string ?? "")"),
                                      TCell(text: "\(Fmt.am(x["fd_over"].double)) / \(x["fd_under"].double.map { Fmt.am($0) } ?? "—")"),
                                      Self.novigOu(x),
                                      TCell(text: Fmt.pct(x["p_market"].double)), TCell(text: Fmt.pct(x["p_model"].double)),
                                      TCell(text: Stat.pts(gap), color: tone(gap)),
                                      TCell(text: x["minutes"].double.map { String(Int($0.rounded())) } ?? "—")] },
                          leading: [0, 1])
                AboutView(text: "Market over is the no-vig chance at FanDuel's number, and it sets the price. Our model (minutes and per-minute rates from recent games, tonight's lineup) is shown for learning: it has no weight until it beats the market on logged lines. Sorted by the biggest gap.")
            })
        }
        return out
    }

    // MARK: UFC (Oct 23; web ufcMeta / ufcTop / ufcFolds, cards/analysis_ufc.py)

    private static let ufcMethod = [("ko", "KO/TKO"), ("sub", "Submission"), ("dec", "Decision")]

    /// Each of Mike's books against the sharp no-vig moneyline, then how DraftKings prices the way it ends.
    static func ufcTop(_ g: JSON) -> [AnalysisFold] {
        var out: [AnalysisFold] = []
        let rows = g["books"].array, dk = g["dk"], f = g["fighters"].array
        if !rows.isEmpty {
            out.append(fold("books", "The moneyline at your books vs. the sharp book") {
                StatTable(head: ["Fighter"] + Stat.myBooks + ["Sharp no-vig"],
                          rows: rows.map { o in [TCell(text: Fmt.label(o["label"].string))] + Stat.bookCells(o, ufc: true)
                                                 + [TCell(text: Fmt.pct(o["p_market"].double))] })
                AboutView(text: "From the latest pull (\(rows[0]["source"].string ?? "")). Each book's price with its EV under it. The card's UFC bets come from here: a book lagging the sharp price, at the best of your books. A draw or no contest voids the moneyline.")
            })
        }
        let m = dk["method"]
        if !m.isNull && !m.object.isEmpty, let a = f[safe: 0], let b = f[safe: 1] {
            var cells: [[TCell]] = ufcMethod.map { k, lab in
                [TCell(text: lab)] + ["a", "b"].map { s in
                    let c = m["\(s)_\(k)"]
                    return TCell(text: Fmt.pct(c["p"].double), sub: Fmt.am(c["price"].double))
                }
            }
            let d = dk["distance"], t = dk["total"]
            if !d.object.isEmpty {
                cells.append([TCell(text: "Goes the distance"), TCell(text: Fmt.pct(d["p_yes"].double),
                              sub: "yes \(Fmt.am(d["yes"].double)) / no \(Fmt.am(d["no"].double))"), ""])
            }
            if !t.object.isEmpty {
                cells.append([TCell(text: "Over \(t["line"].string ?? "") rounds"), TCell(text: Fmt.pct(t["p_over"].double),
                              sub: "over \(Fmt.am(t["over"].double)) / under \(Fmt.am(t["under"].double))"), ""])
            }
            out.append(fold("method", "How it ends (DraftKings)") {
                StatTable(head: ["Result", a["name"].string ?? "", b["name"].string ?? ""], rows: cells)
                AboutView(text: "DraftKings' prices from ESPN, as chances with the margin taken out. The six method outcomes carry about \(Fmt.pct(dk["method_margin"].double)) of margin together (a moneyline about 4%), which is why we don't bet them: no edge showed on the fights we could check (Oct 23).")
            })
        }
        return out
    }

    /// "x KO · y sub · z dec", or "—" with no UFC fights since 2021.
    private static func ufcBy(_ form: JSON, _ key: String) -> String {
        guard (form["fights"].int ?? 0) != 0 else { return "—" }
        let w = form[key]
        return "\(w["ko"].int ?? 0) KO · \(w["sub"].int ?? 0) sub · \(w["dec"].int ?? 0) dec"
    }

    static func ufcFolds(_ g: JSON) -> [AnalysisFold] {
        let f = g["fighters"].array
        guard let a = f[safe: 0], let b = f[safe: 1] else { return [] }
        let an = a["name"].string ?? "", bn = b["name"].string ?? ""
        var out: [AnalysisFold] = []
        if let story = g["story"].string, !story.isEmpty { out.append(fold("story", "How the fight goes") { prose(story) }) }
        let mo = g["model"], dk = g["dk"]
        if !mo.isNull && !mo.object.isEmpty {
            let debut = [mo["debut_a"].bool == true ? an : nil, mo["debut_b"].bool == true ? bn : nil].compactMap { $0 }
            let pa = mo["p_a"].double, dpa = dk["ml"]["p_a"].double
            out.append(fold("model", "Our model (tracked, no weight)") {
                StatTable(head: ["", "Our model", "DraftKings no-vig"], rows: [
                    [TCell(text: "\(an) wins"), TCell(text: Fmt.pct(pa)), TCell(text: Fmt.pct(dpa))],
                    [TCell(text: "\(bn) wins"), TCell(text: Fmt.pct(pa.map { 1 - $0 })), TCell(text: Fmt.pct(dpa.map { 1 - $0 }))],
                    [TCell(text: "Goes the distance"), TCell(text: Fmt.pct(mo["p_dist"].double)), TCell(text: Fmt.pct(dk["distance"]["p_yes"].double))]])
                if !debut.isEmpty {
                    Text("\(debut.joined(separator: " and ")): no UFC fights since 2021, so the model sees an average fighter. The market knows more.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                AboutView(text: "Ratings and fight stats from ESPN's UFC results since 2021, fit on every earlier fight. Out of sample it beats a coin flip and Elo, but on the fights where we have DraftKings' prices the market beat it clearly (log loss 0.642 vs 0.721, Oct 23), so it never moves a price or a pick. It's logged every card to keep score.")
            })
        }
        let sf = g["same_fight"].array
        if !sf.isEmpty {
            out.append(fold("sgp", "Same-fight parlays", n: sf.count) {
                StatTable(head: ["Parlay", "Fair chance", "Fair odds", "Legs multiplied", "DraftKings single"],
                          rows: sf.map { c in [TCell(text: c["label"].string ?? ""), TCell(text: Fmt.pct(c["p"].double)),
                                               TCell(text: c["fair_price"].double.map { Fmt.am($0) } ?? "—"),
                                               TCell(text: c["naive"].double.map { Fmt.pct($0) } ?? "—"),
                                               c["dk_price"].double == nil ? "—" : Stat.bookCell(c["dk_price"].double, c["dk_ev"].double)] })
                AboutView(text: "Who wins is the sharp moneyline; how each fighter wins (finish or decision) is DraftKings' method market with its margin taken out; when a finish comes is set so the parlays agree with the sharp total-rounds line (or, without one, every UFC finish since 2021 at this length). A same-game parlay is only worth it when the book pays more than the fair odds: type its quote into the Build tab. \"Legs multiplied\" is what you'd get treating the legs as unrelated: the gap is why books price these themselves. A win by decision is the same bet as DraftKings' points prop, priced next to it.")
            })
        }
        let v = { (x: JSON, k: String) in x[k].string ?? "—" }
        let tape: [(String, (JSON) -> String)] = [
            ("Record", { v($0, "record") }), ("Age", { v($0, "age") }), ("Height", { v($0, "height") }),
            ("Reach", { v($0, "reach") }), ("Stance", { v($0, "stance") }), ("From", { v($0, "country") }),
            ("UFC fights since 2021", { String($0["form"]["fights"].int ?? 0) }),
            ("Wins by", { ufcBy($0["form"], "wins") }), ("Losses by", { ufcBy($0["form"], "losses") }),
            ("Went the distance", { Fmt.pct($0["form"]["distance"].double) })]
        out.append(fold("tape", "Tale of the tape") {
            TapeView(left: an, right: bn, sep: "vs", rows: tape.map { TapeRow(label: $0.0, left: $0.1(a), right: $0.1(b)) })
        })
        out.append(fold("last", "Last five fights") {
            UfcLastFights(fighter: a)
            UfcLastFights(fighter: b)
        })
        let cr = g["class_rates"]
        if !cr.isNull && !cr.object.isEmpty {
            let wc = g["weight_class"].string ?? "", rounds = g["rounds"].string ?? ""
            out.append(fold("class", "\(wc) \(rounds)-rounders") {
                prose("Since 2021, \(cr["n"].string ?? "") UFC \(wc.lowercased()) fights scheduled for \(rounds) rounds: \(Fmt.pct(cr["distance"].double)) went to the judges, \(Fmt.pct(cr["ko"].double)) ended by KO/TKO and \(Fmt.pct(cr["sub"].double)) by submission.")
                AboutView(text: "ESPN's results for every UFC card since 2021. A base rate, not a prediction: who is fighting matters more than the class.")
            })
        }
        return out
    }
}

/// One fighter's last UFC fights, newest first: W green, L red, a draw or no contest faint (web ufcFolds `last`).
struct UfcLastFights: View {
    let fighter: JSON
    var body: some View {
        let last = fighter["form"]["last"].array
        VStack(alignment: .leading, spacing: 4) {
            Text(fighter["name"].string ?? "").font(.subheadline.bold())
            if last.isEmpty {
                Text("No UFC fights since 2021: a debut or a long layoff.").font(.footnote).foregroundStyle(.secondary)
            }
            ForEach(last.indices, id: \.self) { i in
                let f = last[i], r = f["result"].string ?? ""
                (Text(r).foregroundColor(r == "W" ? .green : r == "L" ? .red : .secondary) + Text(" \(f["opponent"].string ?? "")")
                 + Text(" · \(f["method"].string ?? "")\(f["round"].int.flatMap { $0 != 0 ? ", round \($0)" : nil } ?? "") · \(f["date"].string ?? "")").foregroundColor(.secondary))
                    .font(.footnote)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

extension Array { subscript(safe i: Int) -> Element? { indices.contains(i) ? self[i] : nil } }

/// A matchup edge with its size: a bar right of center for the offense, left for the defense (SDs, capped at 2.5).
struct EdgeRow: View {
    let text: String
    let size: Double?
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(text).font(.footnote)
            if let s = size {
                GeometryReader { geo in
                    let half = geo.size.width / 2, w = min(abs(s) / 2.5, 1) * half
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.secondary.opacity(0.12))
                        Rectangle().fill(s > 0 ? Color.green : Color.blue).frame(width: w).offset(x: s > 0 ? half : half - w)
                    }
                }
                .frame(height: 5)
                .accessibilityLabel("\(s > 0 ? "Offense" : "Defense") edge, \(String(format: "%.1f", abs(s))) SD")
            }
        }
    }
}

struct HurtList: View {
    let teams: [(String, [JSON])]
    let effects: [String]
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !effects.isEmpty {
                Text("What it does to the numbers").font(.caption.weight(.semibold))
                ForEach(effects, id: \.self) { Text($0).font(.footnote) }
            }
            ForEach(teams, id: \.0) { team, list in
                Text(team).font(.footnote.weight(.semibold))
                ForEach(Array(list.enumerated()), id: \.offset) { _, p in
                    let st = p["status"].string ?? ""
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(st).font(.caption2.weight(.semibold))
                            .foregroundStyle(st == "Out" || st == "Doubtful" ? .red : st == "Questionable" ? .orange : .secondary)
                        Text(p["name"].string ?? p["player"].string ?? "").font(.footnote)
                        Text(detail(p)).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }
    private func detail(_ p: JSON) -> String {
        var parts: [String] = []
        if let pos = p["position"].string ?? p["pos"].string { parts.append(pos) }
        if let s = p["snap_share"].double { parts.append("\(Int((s * 100).rounded()))% of snaps") }
        if let m = p["toi_min"].string { parts.append("\(m) min · \(Fmt.pct(p["shot_share"].double)) of shots") }
        if let i = p["injury"].string { parts.append(i.lowercased()) }
        return parts.joined(separator: " · ")
    }
}
