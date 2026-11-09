import SwiftUI

/// A game on the calendar: every game ESPN lists for the next 10 weeks (calendar_sync.py, Nov 4).
struct ScheduleGame: Decodable, Identifiable, Hashable {
    let id: String
    let sport: String
    let start: String
    let home: String?
    let away: String?
    let matchup: String
    let gameId: String?

    /// As the Games tab's card reads a game.
    var asGame: Game { Game(gameId: gameId ?? id, league: sport, home: home, away: away, matchup: matchup, commenceTime: start, state: nil) }
}

private struct CalendarDay: Decodable { let day: String; let sport: String; let games: Int }

/// The month grid (web lib/calendar.ts, one fixture tests/fixtures/calendar.json): plain "YYYY-MM-DD" Eastern days, never instants,
/// so a clock change can't move a cell.
enum CalendarGrid {
    private static let utc: Calendar = { var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(identifier: "UTC")!; return c }()
    private static func date(_ day: String) -> Date? {
        let p = day.split(separator: "-").compactMap { Int($0) }
        guard p.count == 3 else { return nil }
        return utc.date(from: DateComponents(year: p[0], month: p[1], day: p[2], hour: 12))
    }
    private static func str(_ d: Date) -> String {
        let c = utc.dateComponents([.year, .month, .day], from: d)
        return String(format: "%04d-%02d-%02d", c.year!, c.month!, c.day!)
    }

    static func shift(_ month: String, _ n: Int) -> String {
        let p = month.split(separator: "-").compactMap { Int($0) }
        let i = p[0] * 12 + (p[1] - 1) + n
        let (y, m) = i >= 0 ? (i / 12, i % 12) : ((i - 11) / 12, ((i % 12) + 12) % 12)
        return String(format: "%04d-%02d", y, m + 1)
    }

    /// Every day of the weeks (Sunday first) that hold a day of this month ("2026-11").
    static func grid(_ month: String) -> [String] {
        guard let start = date("\(month)-01"), let next = date("\(shift(month, 1))-01"),
              let last = utc.date(byAdding: .day, value: -1, to: next) else { return [] }
        let before = utc.component(.weekday, from: start) - 1, after = 7 - utc.component(.weekday, from: last)
        guard let first = utc.date(byAdding: .day, value: -before, to: start), let end = utc.date(byAdding: .day, value: after, to: last)
        else { return [] }
        var out: [String] = [], d = first
        while d <= end { out.append(str(d)); d = utc.date(byAdding: .day, value: 1, to: d)! }
        return out
    }

    static func monthName(_ month: String) -> String {
        guard let d = date("\(month)-15") else { return month }
        let f = DateFormatter(); f.timeZone = TimeZone(identifier: "UTC"); f.dateFormat = "MMMM yyyy"
        return f.string(from: d)
    }
}

@MainActor final class CalendarModel: ObservableObject {
    @Published var month = String(BetMath.etDay(Date()).prefix(7))
    @Published var day = BetMath.etDay(Date())
    @Published var sport: String?
    @Published private(set) var counts: [String: [String: Int]] = [:]    // day -> sport -> games
    @Published private(set) var games: [ScheduleGame] = []
    @Published private(set) var art: [String: GameLive] = [:]    // logos and colors from ESPN (Live.art)
    @Published private(set) var slates: [Slate] = []
    @Published private(set) var error: String?
    @Published private(set) var loaded = false

    var sports: [String] { Array(Set(counts.values.flatMap(\.keys))).sorted() }
    func count(_ d: String) -> Int {
        guard let day = counts[d] else { return 0 }
        if let sport { return day[sport] ?? 0 }
        return day.values.reduce(0, +)
    }
    var shown: [ScheduleGame] { games.filter { sport == nil || $0.sport == sport }.sorted { ($0.start, $0.matchup) < ($1.start, $1.matchup) } }

    func load(_ api: SupabaseClient) async {
        do {
            async let c: [CalendarDay] = api.rows("calendar_days", .init(inList: ("day", CalendarGrid.grid(month))))
            async let g: [ScheduleGame] = dayGames(api)
            async let s: SlatesDoc? = api.doc("fun", "slates")
            let (cs, gs, doc) = try await (c, g, s)
            var by: [String: [String: Int]] = [:]
            for x in cs { by[x.day, default: [:]][x.sport] = x.games }
            (counts, games, slates, error, loaded) = (by, gs, doc?.slates ?? [], nil, true)
            art = await Live.art(for: gs.map(\.asGame), ttl: ESPN.doneTTL)
        } catch is CancellationError {
        } catch { self.error = error.localizedDescription; loaded = true }
    }

    func loadDay(_ api: SupabaseClient) async {
        if let g = try? await dayGames(api) {
            games = g
            art = await Live.art(for: g.map(\.asGame), ttl: ESPN.doneTTL)
        }
    }

    private func dayGames(_ api: SupabaseClient) async throws -> [ScheduleGame] {
        guard let start = Self.etMidnight(day) else { return [] }
        return try await api.rows("schedule_games", .init(from: ("start", start), to: ("start", BetMath.etShift(start, days: 1))))
    }

    private static func etMidnight(_ day: String) -> Date? {
        let p = day.split(separator: "-").compactMap { Int($0) }
        guard p.count == 3 else { return nil }
        var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(identifier: "America/New_York")!
        return c.date(from: DateComponents(year: p[0], month: p[1], day: p[2]))
    }
}

/// The calendar: a clean month, a dot on the days with your bets or a lock; below it the day: your bets, its locks, and its games as the Games
/// tab's cards, by sport. A sport with more games than `openUpTo` starts folded (college basketball's 100 a night).
struct CalendarView: View {
    @EnvironmentObject private var store: BetStore
    @StateObject private var model = CalendarModel()
    private static let openUpTo = 12
    @State private var opened: [String: Bool] = [:]

    private var locks: [GameDay.Lock] {
        GameDay.upcomingLocks(model.slates.filter { model.sport == nil || $0.sport == model.sport }, games: model.shown.map(\.asGame))
    }
    private var dayLocks: [GameDay.Lock] { locks.filter { BetMath.etDay($0.at) == model.day } }
    private var today: String { BetMath.etDay(Date()) }
    private func betCount(_ d: String) -> Int { store.bets.filter { BetMath.day($0) == d }.count }
    private func clock(_ d: Date) -> String { Fmt.time(ISO8601DateFormatter().string(from: d)) }

    var body: some View {
        List {
            Section {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        chip("All", model.sport == nil) { model.sport = nil }
                        ForEach(model.sports, id: \.self) { s in chip(Fmt.sports[s] ?? s, model.sport == s) { model.sport = s } }
                    }
                }
                VStack(spacing: 10) {
                    HStack {
                        Text(CalendarGrid.monthName(model.month)).font(.headline)
                        Spacer()
                        Button { move(-1) } label: { Label("Previous month", systemImage: "chevron.left").labelStyle(.iconOnly).frame(width: 36, height: 32) }
                        Button { move(1) } label: { Label("Next month", systemImage: "chevron.right").labelStyle(.iconOnly).frame(width: 36, height: 32) }
                    }.buttonStyle(.borderless)
                    grid
                    HStack(spacing: 12) {
                        legend(.accentColor, "your bets")
                        legend(.orange, "a lock")
                        Spacer()
                    }.accessibilityHidden(true)
                }.padding(.vertical, 4)
            }
            if let e = model.error { Section { Label(e, systemImage: "exclamationmark.triangle").foregroundStyle(.orange) } }
            Section(Fmt.longDay(Models.date("\(model.day)T16:00:00Z") ?? Date())) {
                ForEach(store.bets.filter { BetMath.day($0) == model.day }) { b in
                    HStack(spacing: 8) { TagView(text: "Your bet", color: .accentColor); Text(b.label ?? b.matchup ?? "").font(.subheadline).lineLimit(2) }
                }
                if let first = dayLocks.first {
                    DisclosureGroup {
                        ForEach(dayLocks, id: \.slate) { l in
                            LabeledContent(l.title) { Text("by \(clock(l.at))") }.font(.subheadline)
                        }
                    } label: {
                        HStack { Text("\(dayLocks.count) lock\(dayLocks.count == 1 ? "" : "s")").bold(); Text("next by \(clock(first.at))").foregroundStyle(.secondary) }.font(.subheadline)
                    }
                }
                if model.loaded && model.shown.isEmpty && betCount(model.day) == 0 && dayLocks.isEmpty {
                    Text("No games listed for this day yet.").foregroundStyle(.secondary)
                }
            }
            ForEach(Array(Set(model.shown.map(\.sport))).sorted(), id: \.self) { s in
                let games = model.shown.filter { $0.sport == s }
                Section {
                    DisclosureGroup(isExpanded: Binding(get: { opened[s] ?? (games.count <= Self.openUpTo || model.sport != nil) }, set: { opened[s] = $0 })) {
                        ForEach(games) { g in card(g) }
                    } label: {
                        HStack { Text(Fmt.sports[s] ?? s).bold(); Text("\(games.count) game\(games.count == 1 ? "" : "s")").foregroundStyle(.secondary) }.font(.subheadline)
                    }
                }
            }
        }
        .themedRows().themedList()
        .navigationTitle("Calendar")
        .overlay { if !model.loaded { ProgressView() } }
        .refreshable { await model.load(store.api) }
        .task(id: "\(model.month)|\(store.refreshTick)") { await model.load(store.api) }
        .task(id: model.day) { opened = [:]; await model.loadDay(store.api) }
    }

    @ViewBuilder private func card(_ g: ScheduleGame) -> some View {
        let row = GameCardRow(g: g.asGame, art: model.art[g.gameId ?? g.id], count: nil, chevron: g.gameId != nil)
        Group {
            if let id = g.gameId { NavigationLink { GameView(gameId: id) } label: { EmptyView() }.opacity(0).background(row) } else { row }
        }
        .listRowInsets(EdgeInsets(top: 4, leading: 10, bottom: 4, trailing: 12))
    }

    private func legend(_ c: Color, _ t: String) -> some View {
        HStack(spacing: 4) { Circle().fill(c).frame(width: 6, height: 6); Text(t).font(.caption2).foregroundStyle(.secondary) }
    }

    private func move(_ n: Int) {
        model.month = CalendarGrid.shift(model.month, n)
        if !model.day.hasPrefix(model.month) { model.day = "\(model.month)-01" }
    }

    /// Plain weeks, not a lazy grid: a LazyVGrid in a self-sizing list row kept changing its height, and UIKit stopped the app after 84
    /// layout passes (Nov 4).
    private var grid: some View {
        let days = CalendarGrid.grid(model.month), letters = ["S", "M", "T", "W", "T", "F", "S"]
        return VStack(spacing: 2) {
            HStack(spacing: 0) {
                ForEach(letters.indices, id: \.self) { i in
                    Text(letters[i]).font(.caption2.bold()).foregroundStyle(.secondary).frame(maxWidth: .infinity).accessibilityHidden(true)
                }
            }
            ForEach(Array(stride(from: 0, to: days.count, by: 7)), id: \.self) { w in
                HStack(spacing: 0) { ForEach(days[w..<min(w + 7, days.count)], id: \.self) { d in cell(d) } }
            }
        }
    }

    private func cell(_ d: String) -> some View {
        let n = model.count(d), bets = betCount(d), selected = d == model.day, isToday = d == today
        let lock = locks.contains { BetMath.etDay($0.at) == d }
        return Button { model.day = d; model.month = String(d.prefix(7)) } label: {
            VStack(spacing: 3) {
                Text("\(Int(d.suffix(2)) ?? 0)")
                    .font(.subheadline.weight(selected || isToday ? .bold : n > 0 || bets > 0 ? .medium : .regular))
                    .foregroundStyle(selected ? Color.white : isToday ? Color.accentColor : n > 0 || bets > 0 ? Color.primary : Color.secondary)
                    .frame(width: 34, height: 34)
                    .background(selected ? Color.accentColor : Color.clear, in: Circle())
                HStack(spacing: 3) {
                    if bets > 0 { Circle().fill(Color.accentColor).frame(width: 5, height: 5) }
                    if lock { Circle().fill(Color.orange).frame(width: 5, height: 5) }
                }.frame(height: 5)
            }
            .frame(maxWidth: .infinity)
            .contentShape(Rectangle())
            .opacity(d.hasPrefix(model.month) ? 1 : 0.4)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(Fmt.longDay(Models.date("\(d)T16:00:00Z") ?? Date())): \(n) games\(bets > 0 ? ", \(bets) of your bets" : "")\(lock ? ", a lock" : "")")
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private func chip(_ title: String, _ selected: Bool, _ action: @escaping () -> Void) -> some View {
        Button(title, action: action).buttonStyle(.bordered).tint(selected ? .accentColor : .secondary).controlSize(.small)
    }
}
