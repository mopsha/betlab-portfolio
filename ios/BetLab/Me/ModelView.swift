import SwiftUI
import Charts

struct PaperPick: Decodable, Identifiable {
    let pickId: String
    var league: String? = nil
    var matchup: String? = nil
    var label: String? = nil
    var price: Double? = nil
    var commenceTime: String? = nil
    var status: String? = nil
    var profitFlat: Double? = nil
    var unitsFlat: Double? = nil
    var clv: Double? = nil
    var clvRaw: Double? = nil
    var id: String { pickId }
    var clvOf: Double? { clvRaw ?? clv }
    var settled: Bool { ["won", "lost", "push"].contains(status ?? "") }
}

/// More > Model (web app/more/model): is the model earning trust? Closing line value first, the record second.
struct ModelView: View {
    @EnvironmentObject private var store: BetStore
    @State private var results: JSON = .null
    @State private var golive: JSON = .null
    @State private var syncedAt: String?
    @State private var picks: [PaperPick] = []
    @State private var loaded = false
    @State private var show = "all"
    @State private var error: String?

    private static func scoreName(_ m: String) -> String {
        m.replacingOccurrences(of: #"^NCAAF\b"#, with: "College football", options: .regularExpression)
            .replacingOccurrences(of: #"^NCAAB\b"#, with: "College basketball", options: .regularExpression)
            .replacingOccurrences(of: #"^MLS\b"#, with: "Soccer (MLS)", options: .regularExpression)
    }
    private func u(_ v: Double?) -> String { BetMath.signedUnits(v) }
    private func clv(_ v: Double?) -> String { v.map { Fmt.signed($0) } ?? "—" }

    var body: some View {
        let o = results["overall"]
        List { Group {
            Section {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        pill("Record", o["record"].string ?? "—")
                        pill("Units", u(o["units"].double), tone(o["units"].double))
                        pill("Avg CLV", clv(o["avg_clv"].double) + "  goal +1%")
                        pill("Beat close", (o["beat_close_pct"].double.map { Fmt.pct($0) } ?? "—") + "  goal 55%")
                    }
                }
                .bareRow()
                Text(lede).font(.footnote).bareRow()
            }
            if let e = error { Section { Text(e).font(.caption).foregroundStyle(.red) } }
            if !golive.isNull { scorecard }
            chartSection
            byMarket
            paperRecord
        }.themedRows() }.themedList()
        .navigationTitle("Model")
        .subtitle(syncedAt.map { "updated \(Fmt.dayTime($0))" })
        .overlay { if !loaded { ProgressView() } }
        .refreshable { await load() }
        .task(id: store.refreshTick) { await load() }
    }

    private func load() async {
        let api = store.api
        async let r: JSON? = api.doc("app", "results")
        async let g: JSON? = api.doc("app", "golive")
        async let m: JSON? = api.doc("app", "meta")
        async let p: [PaperPick] = api.rows("paper_picks", .init(eq: [("tier", "pick"), ("current_rule", "true")]))
        do {
            results = try await r ?? .null
            golive = try await g ?? .null
            syncedAt = try await m?["synced_at"].string
            picks = try await p
            error = nil
        } catch { self.error = String(describing: error) }
        loaded = true
    }

    private var lede: String {
        let markets = golive["markets"].array
        let strong = markets.filter { $0["status"].string == "pass" }.compactMap { $0["market"].string }.map(Self.scoreName)
        let best = markets.max { ($0["progress"].double ?? 0) < ($1["progress"].double ?? 0) }
        let ap = golive["all_markets"]["picks"]
        var s: String
        if !strong.isEmpty { s = "Strong now: \(strong.joined(separator: ", ")). " }
        else if let b = best, let n = b["picks"]["with_clv"].int, n > 0 {
            s = "No market is proven yet; furthest along is \(Self.scoreName(b["market"].string ?? "")) with \(n) of \(golive["rules"]["min_picks"].int ?? 0) picks measured. "
        } else { s = "No market has measured picks yet. " }
        if let n = ap["with_clv"].int, n > 0 { s += "\(n) pick\(n == 1 ? "" : "s") measured against the close, \(Fmt.pct(ap["sure_positive"].double)) sure the edge is real." }
        return s
    }

    @ViewBuilder private var scorecard: some View {
        let rules = golive["rules"]
        let minPicks = rules["min_picks"].int ?? 0
        let markets = golive["markets"].array.sorted {
            ($0["picks"]["with_clv"].int ?? 0, $0["leans"]["with_clv"].int ?? 0) > ($1["picks"]["with_clv"].int ?? 0, $1["leans"]["with_clv"].int ?? 0)
        }
        Section("Strengths and weak spots · each market against the close") {
            ForEach(markets.indices, id: \.self) { i in
                let m = markets[i], st = m["status"].string ?? ""
                let (word, color): (String, Color) = st == "pass" ? ("strong", .green) : st == "failing" ? ("weak spot", .red) : ("building", .secondary)
                let n = m["picks"]["with_clv"].int ?? 0
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(Self.scoreName(m["market"].string ?? "")).font(.subheadline.weight(.semibold))
                        TagView(text: word, color: color)
                        Spacer()
                        ProgressView(value: min(1, m["progress"].double ?? 0)).frame(width: 60)
                        Text("\(n)/\(minPicks)").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }
                    HStack(spacing: 6) {
                        let avg = m["picks"]["avg_clv"].double
                        Text("CLV **\(clv(avg))**").foregroundStyle((avg ?? -1) >= (rules["min_avg_clv"].double ?? 0) ? .green : .secondary)
                        Text("· beat close **\(m["picks"]["beat_close"].double.map { Fmt.pct($0) } ?? "—")**")
                        if let ln = m["leans"]["with_clv"].int, ln > 0 { Text("· leans \(ln) · \(clv(m["leans"]["avg_clv"].double))") }
                    }
                    .font(.caption).foregroundStyle(.secondary)
                }
            }
            DisclosureGroup("How markets are scored") {
                Text("A market is **strong** once it has \(minPicks)+ picks with measured closing line value, average CLV of \(Fmt.signed(rules["min_avg_clv"].double, 0)) or better, and beats the close \(Fmt.pct(rules["min_beat_close"].double)) of the time. With \(minPicks)+ picks and a missed bar, it's a **weak spot** to fix. Leans are the same signal at smaller edges: supporting evidence, not a substitute. Real bets are your call either way.")
                    .font(.footnote)
            }
            .font(.caption)
        }
        let books = golive["by_book"].array
        if !books.isEmpty {
            Section {
                StatTable(head: ["Book", "Picks", "CLV", "Beat close", "Leans", "CLV"], rows: books.map { b in
                    let p = b["picks"], l = b["leans"]
                    return [TCell(text: b["book"].string ?? ""), TCell(text: "\(p["with_clv"].int ?? 0)/\(p["logged"].int ?? 0)"),
                            TCell(text: clv(p["avg_clv"].double)), TCell(text: p["beat_close"].double.map { Fmt.pct($0) } ?? "—"),
                            TCell(text: "\(l["with_clv"].int ?? 0)/\(l["logged"].int ?? 0)"), TCell(text: clv(l["avg_clv"].double))]
                })
            } header: { Text("By book · picks and leans against the close") }
              footer: { Text("Measured / logged. DraftKings is priced from Oct 12; everything before is FanDuel's.") }
        }
    }

    private struct Point: Identifiable { let i: Int; let v: Double; let series: String; var id: String { "\(series)\(i)" } }

    @ViewBuilder private var chartSection: some View {
        let settled = picks.filter(\.settled).sorted { ($0.commenceTime ?? "") < ($1.commenceTime ?? "") }
        Section {
            if settled.count >= 2 {
                let pts: [Point] = {
                    var won = 0.0, exp = 0.0, out: [Point] = []
                    for (i, p) in settled.enumerated() {
                        won += p.profitFlat ?? 0; exp += (p.clvOf ?? 0) * (p.unitsFlat ?? 1)
                        out += [Point(i: i + 1, v: won, series: "Units won"), Point(i: i + 1, v: exp, series: "What CLV predicts")]
                    }
                    return out
                }()
                Chart(pts) { p in
                    LineMark(x: .value("Pick", p.i), y: .value("Units", p.v))
                        .foregroundStyle(by: .value("Series", p.series))
                        .lineStyle(StrokeStyle(lineWidth: 2, dash: p.series == "Units won" ? [] : [5, 4]))
                }
                .chartForegroundStyleScale(["Units won": Color.primary, "What CLV predicts": Color.accentColor])
                .chartXAxisLabel("pick")
                .frame(height: 200)
                Text("Solid: units won. Dashed: what closing line value says we should have won. The gap between them is luck.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                Text("The chart starts after two graded picks under the current rules.").foregroundStyle(.secondary)
            }
        } header: { Text("Units won vs what CLV predicts") }
    }

    @ViewBuilder private var byMarket: some View {
        let bm = results["by_market"].object.sorted { $0.key < $1.key }
        if !bm.isEmpty {
            Section("By market") {
                StatTable(head: ["Market", "Bets", "Record", "Units", "Return", "CLV", "Beat"], rows: bm.map { k, m in
                    [TCell(text: Self.scoreName(k)), TCell(text: "\(m["bets"].int ?? 0)"), TCell(text: m["record"].string ?? "—"),
                     TCell(text: u(m["units"].double), color: tone(m["units"].double)), TCell(text: m["roi"].double.map { Fmt.signed($0) } ?? "—"),
                     TCell(text: clv(m["avg_clv"].double)), TCell(text: m["beat_close_pct"].double.map { Fmt.pct($0) } ?? "—")]
                })
            }
        }
    }

    @ViewBuilder private var paperRecord: some View {
        let marked = Set(store.bets.compactMap(\.pickId))
        let list = picks.filter { p in
            switch show {
            case "mine": return marked.contains(p.pickId)
            case "open": return !p.settled && p.status != "void"
            case "all": return true
            default: return p.status == show
            }
        }.sorted { ($0.commenceTime ?? "") > ($1.commenceTime ?? "") }
        Section("Paper record · current rules") {
            Picker("Show", selection: $show) {
                Text("All").tag("all"); Text("Won").tag("won"); Text("Lost").tag("lost"); Text("Open").tag("open"); Text("Yours").tag("mine")
            }
            .pickerStyle(.segmented)
            if list.isEmpty { Text("No picks here yet. Every paper pick lands in this list with its result and CLV the morning after the game.").font(.footnote).foregroundStyle(.secondary) }
            ForEach(list.prefix(100)) { p in
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(Fmt.label(p.label) + (marked.contains(p.pickId) ? " ✓" : "")).font(.subheadline.weight(.semibold))
                        Spacer()
                        Text(Fmt.am(p.price)).font(.subheadline.monospacedDigit())
                    }
                    HStack(spacing: 6) {
                        Text("\(Fmt.sportShort[p.league ?? ""] ?? p.league ?? "") · \(p.matchup ?? "") · \(Fmt.dayTime(p.commenceTime))").lineLimit(1)
                        Spacer()
                        let st = p.settled || p.status == "void" ? p.status ?? "" : "open"
                        TagView(text: st, color: st == "won" ? .green : st == "lost" ? .red : .secondary)
                    }
                    .font(.caption).foregroundStyle(.secondary)
                    HStack(spacing: 8) {
                        if let pf = p.profitFlat { Text(u(pf)).bold().foregroundStyle(pf >= 0 ? .green : .red) }
                        if let c = p.clvOf { Text("CLV \(Fmt.signed(c))").foregroundStyle(c >= 0 ? .green : .red) }
                    }
                    .font(.caption)
                }
            }
        }
    }

    private func pill(_ title: String, _ value: String, _ color: Color? = nil) -> some View {
        HStack(spacing: 4) { Text(title).foregroundStyle(.secondary); Text(value).bold().foregroundStyle(color ?? .primary) }
            .font(.caption).padding(.horizontal, 10).padding(.vertical, 5)
            .background(Color.secondary.opacity(0.12), in: Capsule())
    }
}
