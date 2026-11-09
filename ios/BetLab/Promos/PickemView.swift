import PhotosUI
import SwiftUI

/// Me › Extras › CFB Pick'em (Nov 7): this week's FanDuel College Football Pick'em entry. Add screenshots of the
/// Questions screens; the worker prices each frozen line against the sharp market and names the side to take; edit the
/// picks in FanDuel before the Saturday noon lock (Claude never enters picks), then tap the side you kept here. Once
/// graded, the score and what BetLab's side would have scored.
struct PickemView: View {
    @EnvironmentObject private var store: BetStore
    @EnvironmentObject private var auth: AuthStore
    @Environment(\.theme) private var theme
    @State private var rows: [PickemRow] = []
    @State private var past: [PickemRow] = []
    @State private var weeks: [PickemWeek] = []
    @State private var picks: [PhotosPickerItem] = []
    @State private var busy = false
    @State private var msg: String?
    @State private var partner = ""
    @State private var reward = ""

    private var week: String { Pickem.weekOf(BetMath.etDay(Date())) }
    private var score: Pickem.Score { Pickem.score(rows) }
    private var locked: Bool {
        rows.contains { Models.date($0.start).map { $0 <= Date() } ?? false } || Date() >= (Models.date("\(week)T17:00:00Z") ?? .distantFuture)
    }

    var body: some View {
        List { Group {
            Section { hero }
            DisclosureGroup("How it works") {
                Text("FanDuel freezes the pick'em lines Wednesday morning and settles on those numbers. By Saturday the sharp market has moved, so BetLab prices each frozen line against Pinnacle every 15 minutes and names the side that covers more often. Screenshot the Questions screens any day after Wednesday; Saturday at 10 AM you get one alert with the picks to flip, and one at 11:45 to submit. Edit them in FanDuel before noon, then tap the side you kept here so the score is right. Games with a New York college get no pick from BetLab.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            if rows.isEmpty {
                Text("No entry this week. Screenshot FanDuel's Pick'em Questions (Rewards › College Football Pick'em › Play Free) and add them.")
                    .foregroundStyle(.secondary)
            }
            ForEach(rows) { r in game(r) }
            if !rows.isEmpty && locked { outcome }
            history
        }.themedRows() }.themedList()
        .navigationTitle("CFB Pick'em")
        .refreshable { await load() }
        .task(id: store.refreshTick) { await load() }
        .onChange(of: picks) { _, its in Task { await add(its) } }
    }

    /// The score, the week and Add.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 16) {
                stat(rows.isEmpty ? "—" : "\(score.yours)/\(score.graded > 0 ? score.graded : rows.count)", "your picks")
                stat(rows.isEmpty ? "—" : "\(score.ours)/\(score.graded > 0 ? score.graded : rows.count)", "BetLab's")
                VStack(alignment: .leading, spacing: 2) {
                    Text("Week of \(dayName(week))").font(.headline)
                    Text(subtitle).font(.caption).foregroundStyle(.secondary)
                }
            }
            PhotosPicker(selection: $picks, maxSelectionCount: 6, matching: .images) {
                Text(busy ? "Reading…" : rows.isEmpty ? "Add screenshots" : "Add again").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered).disabled(busy)
            if let msg { Text(msg).font(.footnote).foregroundStyle(.secondary) }
        }
        .padding(.vertical, 4)
    }

    private var subtitle: String {
        guard !rows.isEmpty else { return "Add the Questions screenshots to start" }
        let f = Pickem.flips(rows)
        let state = score.graded == rows.count ? "Graded" : locked ? "Locked" : !f.toFlip.isEmpty ? "\(f.toFlip.count) to flip"
            : !f.unpicked.isEmpty ? "\(f.unpicked.count) unpicked" : "Set"
        return "\(rows.count) games · \(state)" + (locked ? "" : " · locks Saturday noon")
    }

    private func stat(_ big: String, _ small: String) -> some View {
        VStack(spacing: 2) {
            Text(big).font(.system(size: 26, weight: .bold, design: .rounded).monospacedDigit())
            Text(small.uppercased()).font(.caption2.monospaced()).foregroundStyle(.secondary)
        }
    }

    /// One game: logos and names, the time or final, the two sides as buttons.
    @ViewBuilder private func game(_ r: PickemRow) -> some View {
        let done = r.graded
        let won = done && r.pick != nil && (r.result == r.pick || r.result == "push")
        Section {
            HStack(spacing: 8) {
                HStack(spacing: -8) {
                    TeamArt(s: LiveSide(name: r.away, abbr: String(r.away.prefix(3)), score: nil, logo: r.awayLogo), size: 26)
                    TeamArt(s: LiveSide(name: r.home, abbr: String(r.home.prefix(3)), score: nil, logo: r.homeLogo), size: 26)
                }
                Text("\(r.away) at \(r.home)").font(.subheadline.weight(.semibold)).lineLimit(1)
                Spacer(minLength: 4)
                Text(done ? "\(r.awayPts ?? 0)-\(r.homePts ?? 0)" : Fmt.dayTime(r.start))
                    .font(.caption.monospacedDigit().weight(done && r.pick != nil ? .semibold : .regular))
                    .foregroundStyle(done && r.pick != nil ? (won ? Color.green : Color.red) : Color.secondary)
            }
            HStack(spacing: 8) {
                side(r, "away")
                side(r, "home")
            }
            .listRowSeparator(.hidden)
            if let n = r.notice, !done { Text(n).font(.caption).foregroundStyle(.secondary) }
            if !done, let fl = r.fairLine {
                Text("Market now \(r.home) \(fl > 0 ? "+" : "")\(Pickem.num(fl))").font(.caption).foregroundStyle(.tertiary)
            }
        }
    }

    private func side(_ r: PickemRow, _ s: String) -> some View {
        let mine = r.pick == s, ours = r.ours == s, done = r.graded
        let hit = done && (r.result == s || r.result == "push")
        let p = Pickem.chance(r, s)
        return Button {
            Task { await set(r, mine ? nil : s) }
        } label: {
            HStack(alignment: .center, spacing: 8) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(Pickem.sideLabel(r, s)).font(.subheadline.weight(.semibold)).lineLimit(2).multilineTextAlignment(.leading)
                    Text(mine && ours ? "you · BetLab" : mine ? "you" : ours ? "BetLab" : " ")
                        .font(.caption2).foregroundStyle(mine ? Color.secondary : Color(.tertiaryLabel))
                }
                Spacer(minLength: 2)
                Text(p.map { "\(Int(($0 * 100).rounded()))%" } ?? "—")
                    .font(.callout.monospacedDigit().weight(ours ? .semibold : .regular))
                    .foregroundStyle(ours || hit ? Color.green : Color.secondary)
            }
            .padding(.horizontal, 12).padding(.vertical, 10)
            .frame(maxWidth: .infinity, minHeight: 56)
            .background(hit ? Color.green.opacity(0.16) : Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(theme.accent, lineWidth: mine ? 2 : 0))
            .opacity(done && !hit ? 0.55 : 1)
            .foregroundStyle(.primary)
        }
        .buttonStyle(.plain)
        .disabled(done)
    }

    /// After FanDuel grades it: the partners' best score and what it paid.
    private var outcome: some View {
        Section("After FanDuel grades it (Sunday)") {
            HStack {
                Text("Partners' best").font(.subheadline)
                Spacer()
                TextField("6", text: $partner).keyboardType(.numberPad).multilineTextAlignment(.trailing).frame(width: 60)
            }
            HStack {
                Text("What it paid").font(.subheadline)
                Spacer()
                TextField("25% boost, bonus bets, nothing", text: $reward).multilineTextAlignment(.trailing)
            }
            Button("Save") { Task { await saveWeek() } }.buttonStyle(.bordered).tint(.secondary)
        }
    }

    @ViewBuilder private var history: some View {
        let byWeek = Dictionary(grouping: past, by: \.week)
        if !byWeek.isEmpty {
            Section("Past weeks") {
                ForEach(byWeek.keys.sorted(by: >), id: \.self) { w in
                    let s = Pickem.score(byWeek[w] ?? [])
                    let info = weeks.first { $0.week == w }
                    HStack(spacing: 12) {
                        Text(dayName(w)).font(.subheadline.weight(.semibold))
                        Text("you \(s.yours)/\(s.graded)").font(.footnote.monospacedDigit())
                        Text("BetLab \(s.ours)/\(s.graded)").font(.footnote.monospacedDigit())
                        Spacer()
                        if let b = info?.partnerBest { Text("partners \(b)").font(.footnote.monospacedDigit()).foregroundStyle(.secondary) }
                        if let r = info?.reward, !r.isEmpty { Text(r).font(.footnote).foregroundStyle(.secondary).lineLimit(1) }
                    }
                }
            }
        }
    }

    private static let day: DateFormatter = { let f = DateFormatter(); f.timeZone = TimeZone(identifier: "UTC"); f.dateFormat = "MMM d"; return f }()
    private func dayName(_ w: String) -> String { Models.date("\(w)T12:00:00Z").map { Self.day.string(from: $0) } ?? w }

    private func load() async {
        rows = (try? await store.api.rows("pickem", .init(eq: [("week", week)], order: ("n", true)))) ?? rows
        past = ((try? await store.api.rows("pickem", .init(order: ("n", true)))) ?? past).filter { $0.week != week }
        weeks = (try? await store.api.rows("pickem_weeks", .init(order: ("week", false)))) ?? weeks
        if let w = weeks.first(where: { $0.week == week }) {
            partner = w.partnerBest.map(String.init) ?? partner
            reward = w.reward ?? reward
        }
    }

    private func set(_ r: PickemRow, _ pick: String?) async {
        guard let id = r.pickId else { return }
        do {
            try await store.api.update("pickem", eq: [("pick_id", id)], ["pick": pick])
            await load()
        } catch { msg = "Couldn't save that. Try again." }
    }

    private func saveWeek() async {
        do {
            try await store.api.upsert("pickem_weeks", ["week": week, "partner_best": Int(partner), "reward": reward.isEmpty ? nil : reward],
                                       onConflict: "user_id,week")
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
            var req = URLRequest(url: Config.webURL.appendingPathComponent("api/pickem"))
            req.httpMethod = "POST"; req.timeoutInterval = 65
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue("Bearer \(try await auth.accessToken())", forHTTPHeaderField: "Authorization")
            req.httpBody = try JSONSerialization.data(withJSONObject: ["images": images])
            let (data, resp) = try await URLSession.shared.data(for: req)
            struct Answer: Decodable { let added: Int?; let updated: Int?; let error: String? }
            let a = try? JSONDecoder().decode(Answer.self, from: data)
            if (resp as? HTTPURLResponse)?.statusCode == 200, let n = a?.added {
                let u = a?.updated ?? 0
                msg = "\(n) game\(n == 1 ? "" : "s") added" + (u > 0 ? ", \(u) pick\(u == 1 ? "" : "s") updated" : "") + ". BetLab is pricing the lines now."
                await load()
            } else {
                msg = a?.error ?? "Couldn't read those screenshots."
            }
        } catch { msg = "You look offline: try again." }
    }
}
