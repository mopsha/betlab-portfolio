import SwiftUI

// Game day (Mike's W27 and W7, Oct 24), from web/lib/gameday.ts, lib/locks.ts, components/today/GameDay.tsx and Wall.tsx:
// the rules behind Today's live cards and lock countdowns (drawn in HomeView and TodayCards since the overhaul, Nov 4),
// and the wall (every game you have money on, one tile each, your legs on it; reached from Live). The live states are
// the Live tab's (Live.swift).
// GameDayTests runs web/tests/gameday.test.mjs and locks.test.mjs. **Change both together.**

enum GameDay {
    /// "1h 04m 09s", "12m 30s", "0m 05s" to a time; "now" once it's passed. Units, so it never reads as a clock time
    /// (Mike, Oct 24: "1:04" looked like a time).
    static func countdown(_ at: Date, now: Date = Date()) -> String {
        let s = Int((at.timeIntervalSince(now)).rounded(.down))
        guard s > 0 else { return "now" }
        let h = s / 3600, m = (s % 3600) / 60, sec = s % 60
        return h > 0 ? String(format: "%dh %02dm %02ds", h, m, sec) : String(format: "%dm %02ds", m, sec)
    }

    /// When a slice's parlays lock: the first 15-minute tick within 25 minutes of its first kickoff (the worker's
    /// sgp_plus.lock_due); earlier once the news is in for every game.
    /// College basketball locks with its first tip's pull, the first tick within 45 minutes of it (pregame.FIRST_TIP_ONLY).
    static func lockTime(_ kickoff: Date, sport: String = "") -> Date {
        let tick = 15.0 * 60, lead = (sport == "ncaab" ? 45.0 : 25.0) * 60
        return Date(timeIntervalSince1970: ((kickoff.timeIntervalSince1970 - lead) / tick).rounded(.up) * tick)
    }

    struct Lock: Equatable { let slate: String; let title: String; let at: Date }

    /// The slices with a parlay still to lock (not locked, first kickoff ahead, with an SGP+ or TD ticket), soonest first.
    /// `games`: the NBA's and college basketball's slices are built only once their lines are pulled, so until then they come
    /// from the schedule (Mike, Oct 24: "i don't see that lock coming up on home").
    /// `watched`: the watched games' own locks (Watch.locks: by each game, never its slice, Nov 7).
    static func upcomingLocks(_ slates: [Slate], now: Date = Date(), games: [Game] = [], watched: [Lock] = []) -> [Lock] {
        let built = slates.compactMap { s -> Lock? in
            guard s.lockedAt == nil, let k = Models.date(s.kickoff), k > now,
                  (s.ticketIds ?? []).contains(where: { $0.hasPrefix("plus-") || $0.hasPrefix("td-") })
            else { return nil }
            return Lock(slate: s.slate, title: s.title ?? s.label ?? s.slate, at: lockTime(k, sport: s.sport))
        }
        let known = Set(slates.map(\.slate))
        return (built + scheduledSlices(games, now: now).filter { !known.contains($0.slate) } + watched.filter { $0.at > now })
            .sorted { $0.at < $1.at }
    }

    /// The slices still to be built, from the schedule: one per slice with a game still ahead, locking at the first tip's
    /// lock time (the worker's sgp_plus.slice_of and slice_names; web lib/locks.ts scheduledSlices). The least games: a
    /// ticket needs two; since Nov 7 a lone NBA game's slips show only when watched.
    private static let scheduled = ["nba": 2, "ncaab": 2]
    static func scheduledSlices(_ games: [Game], now: Date = Date()) -> [Lock] {
        var order: [String] = [], by: [String: (sport: String, name: String, first: Date, n: Int)] = [:]
        for g in games where scheduled[g.league] != nil {
            guard let c = g.commenceTime, let t = Models.date(c), t > now, let (day, name) = Slices.sliceOf(g.league, c) else { continue }
            let k = "\(day)-\(g.league)-\(name)"
            if let cur = by[k] { by[k] = (g.league, name, min(cur.first, t), cur.n + 1) } else { order.append(k); by[k] = (g.league, name, t, 1) }
        }
        return order.compactMap { k in
            let s = by[k]!
            guard s.n >= scheduled[s.sport]! else { return nil }
            let word = Slices.word(s.sport, s.name, first: s.first)
            return Lock(slate: k, title: "\(Slices.sportName[s.sport] ?? s.sport) \(word) game\(s.n == 1 ? "" : "s")", at: lockTime(s.first, sport: s.sport))
        }
    }

    static func isGameDay(_ openBets: Int, _ locksToday: Int) -> Bool { openBets > 0 || locksToday > 0 }

    /// What to call an open bet on a small card: "4-leg parlay +940", or a single's leg; its matchup when it has neither.
    static func name(_ b: MyBet) -> String {
        let n = Stats.betName(legs: b.legs, label: b.label, price: b.price)
        return n.hasPrefix("Bet") ? b.matchup ?? n : n
    }

    struct TileLeg { let leg: LegLive; let bet: String }
    struct Tile: Identifiable { let game: GameLive; var legs: [TileLeg]; var id: String { game.key } }

    /// The wall's tiles: one per game across the bets still alive, each with every leg on it (named by its bet); the
    /// biggest first, then live games, then upcoming by start, finished last. A bet that's over (won, or lost on a leg) leaves the wall, and a
    /// game with no live bet left goes with it (Mike, Oct 24: "if a bet is over that tracker should disappear"; web b5aab204).
    static func wallTiles(_ bets: [(id: String, live: BetLive)], names: [String: String]) -> [Tile] {
        var order: [String] = [], tiles: [String: Tile] = [:]
        // bet-id order, so a tile's legs keep their order poll to poll (they followed the dictionary's order, Oct 25)
        for (id, b) in bets.sorted(by: { $0.id < $1.id }) where b.status != "won" && b.status != "lost" {
            for l in b.legs {
                guard let k = l.gameKey, let g = b.games.first(where: { $0.key == k }) else { continue }
                if tiles[k] == nil { order.append(k); tiles[k] = Tile(game: g, legs: []) }
                tiles[k]!.legs.append(TileLeg(leg: l, bet: names[id] ?? "Bet"))
            }
        }
        let rank = { (g: GameLive) in g.state == "in" ? 0 : g.state == "pre" ? 1 : 2 }
        // the biggest first (most legs: Mike, Oct 25, "sorting in size order on wall looks best"), then live, then start
        return order.compactMap { tiles[$0] }.sorted { a, b in
            let (x, y) = (a.game, b.game)
            return a.legs.count != b.legs.count ? a.legs.count > b.legs.count
                : rank(x) != rank(y) ? rank(x) < rank(y) : x.start != y.start ? x.start < y.start : x.key < y.key
        }
    }
}

/// The wall (W7): every game you have money on, one tile each, live, with your legs on it, grouped by their bet.
struct WallView: View {
    let open: [MyBet]
    @ObservedObject var live: LiveModel
    @Environment(\.theme) private var theme
    @EnvironmentObject private var store: BetStore
    @Environment(\.scenePhase) private var phase

    var body: some View {
        let names = Dictionary(open.map { ($0.betId, GameDay.name($0)) }, uniquingKeysWith: { a, _ in a })
        let tiles = GameDay.wallTiles(open.compactMap { b in live.bets[b.betId].map { (b.betId, $0) } }, names: names)
        let liveN = tiles.filter { $0.game.state == "in" }.count
        ScrollView {
            if tiles.isEmpty {
                VStack(spacing: 4) {
                    Text("No games on").bold()
                    Text("Your open bets have no game today.").font(.footnote).foregroundStyle(.secondary)
                }
                .padding(.top, 40)
            } else {
                HStack(spacing: 8) {
                    if liveN > 0 { LiveCountPill(n: liveN) }
                    Text("\(tiles.count) game\(tiles.count == 1 ? "" : "s") with your money on them").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                }
                .padding(.horizontal).padding(.top, 8)
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 340), spacing: 14, alignment: .top)], spacing: 14) {
                ForEach(tiles) { WallTile(t: $0) }
            }
            .padding(.horizontal).padding(.bottom, 24)
        }
        .background(theme.page ?? Color(.systemGroupedBackground))
        .navigationTitle("The wall")
        .navigationBarTitleDisplayMode(.inline)
        // the wall polls for itself: Home's loop is a .task on Home, which SwiftUI cancels once the wall is pushed over
        // it (Oct 27: "when you are actively on the wall it doesn't update"). Same pace: 20 s while a game is on, else 5 min.
        .task(id: "\(phase == .active)|\(open.map(\.betId).sorted().joined(separator: ","))") {
            guard phase == .active else { return }
            while !Task.isCancelled {
                await live.refresh(store.api, open: Set(open.map(\.betId)))
                try? await Task.sleep(for: live.soon ? LiveModel.fast : LiveModel.slow)
            }
        }
    }
}

extension View {
    /// The scoreboard's band: the away team's color to the home team's, darkened toward the bottom (the game page's
    /// header until it is rebuilt; the rebuilt screens use GlowCard and ScoreHead).
    func teamBand(_ away: Color, _ home: Color) -> some View {
        background(LinearGradient(colors: [away.opacity(0.85), home.opacity(0.85)], startPoint: .leading, endPoint: .trailing))
            .overlay(LinearGradient(colors: [.black.opacity(0.05), .black.opacity(0.35)], startPoint: .top, endPoint: .bottom)
                .allowsHitTesting(false))   // the shade passes taps to the logos (their cards, Oct 25)
    }
}

/// One game: its score between the two logos, the teams' colors a soft glow behind it (the overhaul, Nov 4), then the
/// legs on it under each bet's name.
private struct WallTile: View {
    let t: GameDay.Tile

    var body: some View {
        let g = t.game
        let byBet = t.legs.reduce(into: [(bet: String, legs: [LegLive])]()) { acc, x in
            if let i = acc.firstIndex(where: { $0.bet == x.bet }) { acc[i].legs.append(x.leg) } else { acc.append((x.bet, [x.leg])) }
        }
        GlowCard(left: Color(hex: g.reading.away.color), right: Color(hex: g.reading.home.color)) {
            VStack(alignment: .leading, spacing: 14) {
                ScoreHead(g: g)
                ForEach(Array(byBet.enumerated()), id: \.offset) { _, b in
                    Hairline()
                    Text(b.bet).font(.footnote.weight(.bold)).foregroundStyle(.secondary)
                    ForEach(Array(b.legs.enumerated()), id: \.offset) { _, l in LiveLegRow(l: l) }
                }
            }
        }
        .opacity(g.state == "post" ? 0.75 : 1)
    }
}

/// Away and home, each a large logo, abbreviation and score; LIVE / FINAL / the start and the clock in the middle.
/// `compact`: the smaller one inside My bets' trackers.
struct Scoreboard: View {
    let g: GameLive
    var compact = false
    private static let time: DateFormatter = { let f = DateFormatter(); f.timeZone = Fmt.et; f.dateFormat = "h:mm a"; return f }()
    private static let dayTime: DateFormatter = { let f = DateFormatter(); f.timeZone = Fmt.et; f.dateFormat = "EEE h:mm a"; return f }()
    /// The start: "9:30 PM" today, "Sun 9:30 AM" another day.
    private func start(_ d: Date) -> String {
        BetMath.etDay(d) == BetMath.etDay(Date()) ? Self.time.string(from: d) : Self.dayTime.string(from: d)
    }

    var body: some View {
        let g = g.reading                       // soccer: home first (Nov 5)
        let ufc = g.sport == "ufc", scored = !ufc && g.state != "pre"
        let a = g.away.score ?? 0, h = g.home.score ?? 0
        HStack(alignment: .center) {
            side(g.away, score: scored ? a : nil, lead: scored && a > h, ufc: ufc, ball: g.ball == "away")
            Spacer(minLength: 4)
            VStack(spacing: 4) {
                VStack(spacing: 3) {
                    if g.state == "in" { HStack(spacing: 5) { LiveDot(); Text(g.redZone ? "RED ZONE" : "LIVE") }.font(.caption2.weight(.heavy)) }
                    else { Text(g.state == "post" ? "FINAL" : (Models.date(g.start).map(start) ?? "")).font(.caption2.weight(.heavy)) }
                    if g.state != "pre" { Text(g.detail).font(.caption.monospacedDigit()).lineLimit(1) }
                }
                .padding(.horizontal, 8).padding(.vertical, 5)
                .background(g.redZone ? AnyShapeStyle(Color.red.opacity(0.75)) : AnyShapeStyle(Color.black.opacity(0.28)), in: Capsule())
                // the down and distance on its own line under the pill (Oct 25: three lines in it "looks wrong")
                if g.state == "in", let down = g.down {
                    Text(down).font(.caption2.weight(.semibold).monospaced()).lineLimit(1).opacity(0.85)
                }
            }
            .foregroundStyle(.white)
            Spacer(minLength: 4)
            side(g.home, score: scored ? h : nil, lead: scored && h > a, ufc: ufc, trailing: true, ball: g.ball == "home")
        }
    }

    private func side(_ s: LiveSide, score: Double?, lead: Bool, ufc: Bool, trailing: Bool = false, ball: Bool = false) -> some View {
        let d: CGFloat = compact ? 26 : 40
        let logo = CardTap(ref: ufc ? nil : CardRef(kind: .team, name: s.name, abbr: s.abbr)) {
            LiveImage(url: s.logo, size: d, round: ufc) { Circle().fill(.white.opacity(0.25)).frame(width: d, height: d) }
                .padding(compact ? 3 : 4).background(.white.opacity(0.9), in: Circle())
        }
        let text = VStack(alignment: trailing ? .trailing : .leading, spacing: 0) {
            if let score { Text(Live.js(score)).font(.system(size: compact ? 21 : 30, weight: .heavy, design: .rounded)).monospacedDigit() }
            HStack(spacing: 4) {
                Text(s.abbr.isEmpty ? s.name : s.abbr).font(.caption.weight(.bold)).lineLimit(1)
                if ball { Image(systemName: "football.fill").font(.caption2) }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(ball ? "\(s.abbr), has the ball" : s.abbr)
        }
        return HStack(spacing: 8) {
            if trailing { text; logo } else { logo; text }
        }
        .foregroundStyle(.white)
        .opacity(score == nil || lead ? 1 : 0.72)
    }
}
