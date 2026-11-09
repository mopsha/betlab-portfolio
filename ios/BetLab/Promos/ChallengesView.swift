import PhotosUI
import SwiftUI

// More > Novig challenges (web app/more/challenges and components/promos/Challenges.tsx, Oct 28): add the screenshot of
// Novig's Points > Challenges in the morning (the web's /api/challenges reads it); the worker finds each challenge's best
// Novig bet and alerts you when it's ripe (src/betlab/challenges.py); open it in Novig, then tap I placed it.

struct ChallengeBet: Decodable, Hashable {
    struct Leg: Decodable, Hashable { let label: String; let game: String; let start: String; let price: Double; let p: Double }
    let label: String
    let legs: [Leg]
    let price: Double
    let dec: Double
    let p: Double
    let ev: Double
    let link: String
    let stake: Double
}

struct Challenge: Decodable, Identifiable, Hashable {
    let challengeId: String
    let day: String
    let text: String
    let points: Int?
    let status: String
    let pick: ChallengeBet?
    let best: ChallengeBet?
    let notice: String?
    var id: String { challengeId }

    /// Where it stands (web challengeState): the tag, the bet to show and a note.
    var state: (tag: String, good: Bool, bet: ChallengeBet?, note: String?) {
        switch status {
        case "done": return ("Placed", true, pick, nil)
        case "skipped": return ("Skipped", false, nil, nil)
        case "ready" where pick != nil: return ("Ready", true, pick, nil)
        default:
            let missed = notice.flatMap { $0.hasPrefix("missed: ") ? "\($0.dropFirst(8)) started before it was placed; finding another." : nil }
            let note = missed ?? (notice.map { $0.hasPrefix("missed") ? nil : $0 } ?? nil)
                ?? (best != nil ? "The best so far. You'll get an alert when it's ripe (its game's news is in and the price is right)."
                                : "Looking for a Novig price. You'll get an alert when a bet is ripe.")
            return (best != nil ? "Watching" : "Waiting", false, best, note)
        }
    }
}

/// History (web lib/challenges.ts challengeHistory, Oct 28): points by day (each placed challenge's points, 100 more for a
/// day's 3+ all placed) and how each placed straight did, from the Novig sync's `novig-<outcome>` bet.
enum ChallengeHistory {
    struct Item: Hashable { let text: String; let status: String; let label: String?; let result: String?; let profit: Double? }
    struct Day: Hashable { let day: String; let done: Int; let total: Int; let points: Int; let bonus: Bool; let items: [Item] }
    struct Month: Hashable { let key: String; let points: Int; let done: Int; let total: Int; let sweeps: Int; let settled: Int; let won: Int; let units: Double }
    struct Bet { let sgpId: String?; let status: String?; let profit: Double? }

    static func outcome(_ link: String?) -> String? {
        guard let link, let r = link.range(of: #"(?<=novig\.com/events/)[^/?#]+"#, options: .regularExpression) else { return nil }
        let id = String(link[r])
        return id.contains(",") ? nil : id
    }

    static func build(_ rows: [Challenge], bets: [Bet], today: String) -> (days: [Day], month: Month) {
        let bySgp = Dictionary(bets.compactMap { b in b.sgpId.map { ($0, b) } }, uniquingKeysWith: { a, _ in a })
        let days: [Day] = Dictionary(grouping: rows, by: \.day).sorted { $0.key > $1.key }.map { day, cs in
            let done = cs.filter { $0.status == "done" }.count
            let bonus = cs.count >= 3 && done == cs.count
            let pts = cs.filter { $0.status == "done" }.reduce(0) { $0 + ($1.points ?? 50) } + (bonus ? 100 : 0)
            let items = cs.map { c -> Item in
                let o = c.status == "done" ? outcome(c.pick?.link) : nil
                let b = o.flatMap { bySgp["novig-\($0)"] }
                let st = b?.status
                let result = st != nil && st != "open" ? st : c.status == "done" ? (b != nil ? "open" : nil) : nil
                return Item(text: c.text, status: c.status, label: c.pick?.label, result: result, profit: b?.profit)
            }
            return Day(day: day, done: done, total: cs.count, points: pts, bonus: bonus, items: items)
        }
        let key = String(today.prefix(7))
        let inMonth = days.filter { $0.day.hasPrefix(key) }
        let placed = inMonth.flatMap(\.items).filter { $0.result != nil && $0.result != "open" }
        return (days, Month(key: key, points: inMonth.reduce(0) { $0 + $1.points }, done: inMonth.reduce(0) { $0 + $1.done },
                            total: inMonth.reduce(0) { $0 + $1.total }, sweeps: inMonth.filter(\.bonus).count, settled: placed.count,
                            won: placed.filter { $0.result == "won" }.count, units: placed.reduce(0) { $0 + ($1.profit ?? 0) }))
    }
}

struct ChallengesView: View {
    @EnvironmentObject private var store: BetStore
    @EnvironmentObject private var auth: AuthStore
    @State private var items: [Challenge] = []
    @State private var past: [Challenge] = []
    @State private var picks: [PhotosPickerItem] = []
    @State private var busy = false
    @State private var msg: String?

    private var done: Int { items.filter { $0.status == "done" }.count }
    private var each: Int { items.first { $0.points != nil }?.points ?? 50 }
    private var sorted: [Challenge] {
        let order = ["ready": 0, "open": 1, "done": 2, "skipped": 3]
        return items.sorted { (order[$0.status] ?? 9) < (order[$1.status] ?? 9) }
    }

    var body: some View {
        List { Group {
            Section { hero }
            DisclosureGroup("How it works") {
                Text("Each morning, screenshot Novig's Points › Challenges and add it here. BetLab finds the best Novig bet for each and alerts you when it's ripe: its game's news is in and the price beats the sharp line (+1.5% before 5 PM, fair until 10 PM, then the best there is). Place it in Novig, then tap I placed it.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            if items.isEmpty {
                Text("No challenges yet today. Add the screenshot of Novig's Challenges to start.").foregroundStyle(.secondary)
            }
            ForEach(sorted) { c in card(c) }
            history
        }.themedRows() }.themedList()
        .navigationTitle("Novig challenges")
        .refreshable { await load() }
        .task(id: store.refreshTick) { await load() }
        .onChange(of: picks) { _, its in Task { await add(its) } }
    }

    /// The Daily Drop: a ring of how many are placed, the points, and Add.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 14) {
                ZStack {
                    Circle().stroke(Color.secondary.opacity(0.25), lineWidth: 5)
                    Circle().trim(from: 0, to: items.isEmpty ? 0 : CGFloat(done) / CGFloat(items.count))
                        .stroke(Color.green, style: StrokeStyle(lineWidth: 5, lineCap: .round)).rotationEffect(.degrees(-90))
                    Text("\(done)/\(max(items.count, 3))").font(.subheadline.weight(.semibold).monospacedDigit())
                }
                .frame(width: 52, height: 52)
                VStack(alignment: .leading, spacing: 2) {
                    Text("The Daily Drop").font(.headline)
                    let earned = done * each + (items.count >= 3 && done == items.count ? 100 : 0)
                    (Text("\(each) points each, 100 more for all \(max(items.count, 3))")
                     + Text(earned > 0 ? " · \(earned) earned today" : "").foregroundColor(.green))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            PhotosPicker(selection: $picks, maxSelectionCount: 4, matching: .images) {
                Text(busy ? "Reading…" : items.isEmpty ? "Add today's challenges" : "Add more").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered).disabled(busy)
            if let msg { Text(msg).font(.footnote).foregroundStyle(.secondary) }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder private func card(_ c: Challenge) -> some View {
        let s = c.state
        let settled = c.status == "done" || c.status == "skipped"
        let tint: Color = c.status == "done" || c.status == "ready" ? .green : s.tag == "Watching" ? .orange : .secondary
        Section {
            HStack(alignment: .top, spacing: 10) {
                ZStack {
                    if c.status == "done" { Circle().fill(Color.green); Image(systemName: "checkmark").font(.caption2.bold()).foregroundStyle(.white) }
                    else { Circle().strokeBorder(tint, style: StrokeStyle(lineWidth: 2, dash: c.status == "ready" ? [] : [3, 3])) }
                }
                .frame(width: 22, height: 22)
                Text(c.text.replacingOccurrences(of: #"^Place an? "#, with: "", options: .regularExpression).capitalizedFirst)
                    .font(.subheadline.weight(.semibold))
                Spacer(minLength: 4)
                Text(s.tag.uppercased()).font(.caption2.weight(.semibold).monospaced())
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(tint.opacity(0.15), in: Capsule()).foregroundStyle(tint == .secondary ? Color.secondary : tint)
            }
            .opacity(c.status == "skipped" ? 0.6 : 1)
            if let b = s.bet, !settled {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(b.legs, id: \.self) { l in
                        HStack {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(Fmt.label(l.label)).font(.subheadline.weight(.semibold))
                                Text("\(l.game.replacingOccurrences(of: " @ ", with: " at ")) · \(Fmt.dayTime(l.start))")
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if b.legs.count > 1 { Text(Fmt.am(l.price)).font(.footnote.monospacedDigit()).foregroundStyle(.secondary) }
                        }
                        Divider()
                    }
                    HStack(alignment: .lastTextBaseline) {
                        VStack(alignment: .leading, spacing: 0) {
                            Text(Fmt.am(b.price)).font(.title.weight(.bold).monospacedDigit())
                            Text("Novig" + (b.legs.count > 1 ? String(format: " · %.2fx", b.dec) : "") + " · $\(Int(b.stake))")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text("\(Fmt.pct(b.p, 0)) to hit").font(.caption.monospacedDigit())
                        Text("EV \(Fmt.signed(b.ev))").font(.caption.monospacedDigit()).foregroundStyle(b.ev >= 0 ? .green : .red)
                    }
                }
                .padding(12)
                .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: 10))
                .listRowSeparator(.hidden)
            }
            if let b = s.bet, c.status == "done" {
                (Text(b.label).bold() + Text(" \(Fmt.am(b.price)) at Novig")).font(.footnote).foregroundStyle(.secondary)
            }
            if let n = s.note, !settled { Text(n).font(.caption).foregroundStyle(.secondary) }
            HStack(spacing: 10) {
                Spacer()
                if c.status == "open" || c.status == "ready" {
                    Button("Skip") { Task { await set(c, "skipped") } }.buttonStyle(.bordered).tint(.secondary)
                    if let b = s.bet { BookButton(book: "Novig", link: b.link) }
                    if c.status == "ready" { Button("I placed it") { Task { await set(c, "done") } }.buttonStyle(.borderedProminent) }
                }
                if settled { Button("Undo") { Task { await set(c, "open") } }.buttonStyle(.bordered).controlSize(.small).tint(.secondary) }
            }
        }
    }

    private func load() async {
        items = (try? await store.api.rows("challenges", .init(eq: [("day", BetMath.etDay(Date()))], order: ("created_at", true)))) ?? items
        past = (try? await store.api.rows("challenges", .init(order: ("created_at", true), gt: ("created_at", Date().addingTimeInterval(-42 * 86_400))))) ?? past
    }

    @ViewBuilder private var history: some View {
        let today = BetMath.etDay(Date())
        let bets = store.bets.filter { ($0.sgpId ?? "").hasPrefix("novig-") }
            .map { ChallengeHistory.Bet(sgpId: $0.sgpId, status: BetMath.status($0), profit: BetMath.profit($0)) }
        let h = ChallengeHistory.build(past, bets: bets, today: today)
        if !h.days.isEmpty {
            let m = h.month
            Section("History") {
                Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 10) {
                    GridRow {
                        stat("\(m.points)", "points in \(monthName(m.key))")
                        stat("\(m.done)/\(m.total)", "placed")
                    }
                    GridRow {
                        stat("\(m.sweeps)", "3-for-3 days")
                        stat(m.settled > 0 ? "\(m.units >= 0 ? "+" : "−")\(String(format: "%.2f", abs(m.units)))u" : "—",
                             m.settled > 0 ? "\(m.won) of \(m.settled) won" : "no results yet", color: m.settled > 0 ? (m.units >= 0 ? .green : .red) : nil)
                    }
                }
                .padding(.vertical, 4)
                ForEach(h.days.filter { $0.day != today }.prefix(14), id: \.day) { d in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(dayName(d.day)).font(.subheadline.weight(.semibold))
                            Text("\(d.done)/\(d.total)\(d.bonus ? " · +100" : "")").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                            Spacer()
                            Text("\(d.points) pts").font(.caption.weight(.semibold).monospacedDigit()).foregroundStyle(.green)
                        }
                        ForEach(Array(d.items.enumerated()), id: \.offset) { _, i in
                            HStack {
                                Text(i.status == "done" ? (i.label ?? i.text) : i.text).font(.caption).lineLimit(1)
                                    .foregroundStyle(i.status == "done" ? .primary : .secondary)
                                Spacer()
                                Text(resultText(i)).font(.caption2.monospacedDigit())
                                    .foregroundStyle(i.result == "won" ? .green : i.result == "lost" ? .red : .secondary)
                            }
                        }
                    }
                    .padding(.vertical, 2)
                }
                Text("Results come from the Novig sync (straight bets). A parlay placed for a challenge shows as placed.")
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
    }

    private func stat(_ v: String, _ label: String, color: Color? = nil) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(v).font(.title3.weight(.bold).monospacedDigit()).foregroundStyle(color ?? .primary)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
    }

    private func resultText(_ i: ChallengeHistory.Item) -> String {
        if i.status != "done" { return i.status == "skipped" ? "skipped" : "missed" }
        if i.result == "won" || i.result == "lost" {
            return i.result! + (i.profit.map { " \($0 >= 0 ? "+" : "−")\(String(format: "%.2f", abs($0)))u" } ?? "")
        }
        return i.result ?? "placed"
    }

    private func monthName(_ key: String) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM"
        let out = DateFormatter(); out.dateFormat = "LLLL"
        return f.date(from: key).map { out.string(from: $0) } ?? key
    }

    private func dayName(_ day: String) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        let out = DateFormatter(); out.dateFormat = "EEE, MMM d"
        return f.date(from: day).map { out.string(from: $0) } ?? day
    }

    private func set(_ c: Challenge, _ status: String) async {
        do {
            try await store.api.update("challenges", eq: [("challenge_id", c.challengeId)],
                                       status == "open" ? ["status": status, "pick": nil] : ["status": status])
            await load()
        } catch { msg = "Couldn't save that. Try again." }
    }

    private func add(_ its: [PhotosPickerItem]) async {
        guard !its.isEmpty else { return }
        busy = true; msg = nil
        defer { busy = false; picks = [] }
        var images: [String] = []
        for it in its {
            if let d = try? await it.loadTransferable(type: Data.self), let s = Slip.shrink(d) { images.append(s) }
        }
        guard !images.isEmpty else { msg = "Those aren't images this phone can open."; return }
        do {
            var req = URLRequest(url: Config.webURL.appendingPathComponent("api/challenges"))
            req.httpMethod = "POST"; req.timeoutInterval = 65
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue("Bearer \(try await auth.accessToken())", forHTTPHeaderField: "Authorization")
            req.httpBody = try JSONSerialization.data(withJSONObject: ["images": images])
            let (data, resp) = try await URLSession.shared.data(for: req)
            struct Answer: Decodable { let added: Int?; let error: String? }
            let a = try? JSONDecoder().decode(Answer.self, from: data)
            if (resp as? HTTPURLResponse)?.statusCode == 200, let n = a?.added {
                msg = "\(n) challenge\(n == 1 ? "" : "s") added. BetLab is finding the bets now."
                await load()
            } else {
                msg = a?.error ?? "Couldn't read those screenshots."
            }
        } catch { msg = "You look offline: try again." }
    }
}

private extension String {
    var capitalizedFirst: String { prefix(1).uppercased() + dropFirst() }
}
