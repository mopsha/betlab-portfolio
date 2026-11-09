import SwiftUI
import UIKit

// The live tracker (Oct 23), as web/components/live/LiveBets.tsx, in the style of FanDuel's and DraftKings' open-bet
// cards: a score per game with team logos, each leg as a ring that fills toward its target around the player's headshot
// (or the team's logo) with the number so far as a badge (the overhaul, Nov 4; Design/KitLive.swift), a parlay's legs as dots. Numbers count when they change, a leg glows when it
// hits, and a bet that cashes gets confetti and its winnings counting up (Mike, Oct 23: "woah + cool"); Reduce Motion
// turns the motion off. One refresh feeds every card: every 20 s while a game is in progress (or starts within 20 minutes),
// otherwise every 5 minutes so a game that starts is picked up; only while My bets is on screen and the app is in the
// foreground. ESPN doesn't push, so this is polling by design. The logic is Live.swift.

@MainActor
final class LiveModel: ObservableObject {
    @Published private(set) var bets: [String: BetLive] = [:]
    @Published private(set) var live = false
    /// Open bets the live state settled (won or lost), kept once moved so each moves to Settled once (web LiveProvider
    /// `moved`); the worker's grade replaces them (Live.markLiveSettled skips graded bets).
    @Published private(set) var settled: [String: String] = [:]
    /// Bets cashing right now: a win seen while My bets is on screen (not on first load), shown 4.5 s on Open with
    /// confetti before it moves to Settled.
    @Published private(set) var cashing: Set<String> = []
    private var openIds: Set<String> = []
    private var seen: [String: BetLive] = [:]       // each bet's last state, to spot what changed
    private var celebrated = false
    /// No haptics or cash animation (settles are still recorded): the tab badge's watch (LiveBadgeWatch), Me and the game page.
    var quiet = false

    static let celebrate: Duration = .milliseconds(4500)

    static let fast: Duration = .seconds(20), slow: Duration = .seconds(300)

    /// Poll again soon: a game is in progress, or one starts within 20 minutes.
    var soon: Bool {
        live || bets.values.contains { $0.games.contains { g in g.state == "pre" && (Models.date(g.start)?.timeIntervalSinceNow ?? .infinity) < 20 * 60 } }
    }
    /// Open bets with a game in progress (the "n live" pill).
    var liveCount: Int { bets.filter { openIds.contains($0.key) && $0.value.games.contains { $0.state == "in" } }.count }

    /// The bets' rows as stored (`games` keeps its own keys), their fun tickets' bodies, then ESPN: `open` bets from
    /// yesterday's and today's boards, `done` (recent settled) bets from their own game days.
    /// `friends`: track friends' shared bets instead ("all", or one friend's user id), read through friend_bets (Friends,
    /// Oct 27; web /api/live?friends=).
    func refresh(_ api: SupabaseClient, open: Set<String>, done: Set<String> = [], friends: String? = nil) async {
        openIds = open
        guard !open.isEmpty || !done.isEmpty else { live = false; return }
        let select = "bet_id,kind,sgp_id,label,legs,matchup,league,sport,games,pick_commence_time,ticket_commence_time,placed_at"
        let read: [LiveBetRow]?
        if let friends {
            read = try? await api.rpc("friend_bets", friends == "all" ? [:] : ["friend": friends], plain: true)
        } else {
            read = try? await api.rows("my_bets", .init(select: select), plain: true)
        }
        guard let rows = read else { return }
        var mine = rows.filter { open.contains($0.bet_id) || done.contains($0.bet_id) }
        // A Build slip marked before Nov 1 was saved without its games: its saved slip has them (web myBetsData). A friend
        // can't read your custom_parlays; migration 0046 copied those games onto the bets.
        let bare = mine.filter { $0.kind == "custom" && ($0.games?.array.isEmpty ?? true) }.compactMap(\.sgp_id)
        if friends == nil, !bare.isEmpty,
           let cs: [JSON] = try? await api.rows("custom_parlays", .init(select: "sgp_id,games", inList: ("sgp_id", bare)), plain: true) {
            let by = Dictionary(cs.compactMap { c in c["sgp_id"].string.map { ($0, c["games"]) } }.filter { !$0.1.array.isEmpty },
                                uniquingKeysWith: { a, _ in a })
            mine = mine.map { b in var b = b; if b.kind == "custom", b.games?.array.isEmpty ?? true, let g = b.sgp_id.flatMap({ by[$0] }) { b.games = g }; return b }
        }
        mine = await Self.withStarts(mine, api)
        let ids = mine.filter { $0.kind == "parlay" }.compactMap(\.sgp_id)
        var tickets: [String: JSON] = [:]
        if !ids.isEmpty, let t: [JSON] = try? await api.rows("fun_tickets", .init(select: "sgp_id,sport,matchup,commence_time,body", inList: ("sgp_id", ids)), plain: true) {
            for r in t {
                guard let id = r["sgp_id"].string else { continue }
                var body = r["body"].object
                body["_sport"] = r["sport"]; body["_matchup"] = r["matchup"]; body["_start"] = r["commence_time"]
                tickets[id] = .object(body)
            }
        }
        let out = await Live.liveBets(mine, tickets: tickets, settled: done)
        // a leg that hits while you watch: a light tap; a bet that cashes: a success buzz and the cash animation
        var hit = false, cashed: [String] = []
        for (id, b) in out.bets {
            guard let before = seen[id] else { continue }
            if zip(before.legs, b.legs).contains(where: { $0.status != .won && $1.status == .won }) { hit = true }
            if open.contains(id) && b.settle == "won" && before.settle != "won" && settled[id] == nil { cashed.append(id) }
        }
        seen.merge(out.bets) { _, new in new }
        bets.merge(out.bets) { _, new in new }
        live = out.bets.contains { open.contains($0.key) && $0.value.games.contains { $0.state == "in" } }
        // a quiet tracker (Me, the game page, the tab badge) settles bets but plays nothing
        if !quiet {
            // testing hook (web betlab:celebrate): `-celebrate <bet_id>` plays the cash animation once on that bet, which stays put
            if let id = UserDefaults.standard.string(forKey: "celebrate"), !celebrated, out.bets[id] != nil {
                celebrated = true
                cashing.insert(id)
                Task { try? await Task.sleep(for: Self.celebrate); cashing.remove(id) }
            }
            if !cashed.isEmpty { UINotificationFeedbackGenerator().notificationOccurred(.success) }
            else if hit { UIImpactFeedbackGenerator(style: .light).impactOccurred() }
        }
        // an open bet the live state settles moves to Settled, once (Mike, Oct 23); a win cashes on Open first
        for (id, b) in out.bets where open.contains(id) && settled[id] == nil && !cashing.contains(id) {
            guard let s = b.settle else { continue }
            if cashed.contains(id) && !quiet {
                cashing.insert(id)
                Task {
                    try? await Task.sleep(for: Self.celebrate)
                    cashing.remove(id)
                    settled[id] = s
                }
            } else {
                settled[id] = s
            }
        }
    }
}

extension LiveModel {
    /// Each slip's games' kickoffs from the games table, for refs that carry no time (BetStore.withStarts, web withStarts):
    /// the tracker looks for each game on its own days (Live.searchDays), so a bet a few days old, or one for tomorrow,
    /// still finds its game (Nov 9).
    static func withStarts(_ rows: [LiveBetRow], _ api: SupabaseClient) async -> [LiveBetRow] {
        let refs = { (b: LiveBetRow) in (b.games?.array ?? []).map { $0["game_ref"].string } }
        let ids = Array(Set(rows.flatMap { b in refs(b).compactMap { r in BetMath.refTime(r) == nil ? BetMath.refGameId(r) : nil } }))
        struct Start: Decodable { let gameId: String; let commenceTime: String? }
        let got: [Start] = ids.isEmpty ? [] : (try? await api.rows("games", .init(select: "game_id,commence_time", inList: ("game_id", ids)))) ?? []
        let starts = Dictionary(got.compactMap { r in r.commenceTime.map { (r.gameId, $0) } }, uniquingKeysWith: { a, _ in a })
        return rows.map { b in
            var b = b
            let own = refs(b).compactMap { r in BetMath.refGameId(r).flatMap { id in starts[id].map { (id, $0) } } }
            b.game_starts = Dictionary(own, uniquingKeysWith: { a, _ in a })
            b.game_start = refs(b).compactMap { r in BetMath.refTime(r) ?? BetMath.refGameId(r).flatMap { starts[$0] } }
                .compactMap { Models.date($0) }.min().map { ISO8601DateFormatter().string(from: $0) }
            return b
        }
    }
}

/// The Live tab's badge: open bets with a game in progress right now, not every open bet (Mike, Nov 5). The screens'
/// trackers stop when their tab is hidden, so the badge has its own, at the same pace (20 s while a game is on, else
/// 5 minutes) and only in the foreground; ESPN's cache shares its reads with whichever screen is tracking too.
struct LiveBadgeWatch: ViewModifier {
    @ObservedObject var store: BetStore
    @Environment(\.scenePhase) private var phase
    @StateObject private var live: LiveModel = { let m = LiveModel(); m.quiet = true; return m }()

    func body(content: Content) -> some View {
        let open = Set(store.bets.filter(\.isOpen).map(\.betId))
        content.task(id: "\(phase == .active)|\(store.refreshTick)|\(open.sorted().joined(separator: ","))") {
            guard phase == .active else { return }
            guard !open.isEmpty else { store.liveCount = 0; return }
            while !Task.isCancelled {
                await live.refresh(store.api, open: open)
                store.liveCount = live.liveCount
                try? await Task.sleep(for: live.soon ? LiveModel.fast : LiveModel.slow)
            }
        }
    }
}

/// A pulsing red dot (LIVE); still under Reduce Motion.
struct LiveDot: View {
    @Environment(\.accessibilityReduceMotion) private var calm
    @State private var dim = false
    var body: some View {
        Circle().fill(.red).frame(width: 7, height: 7).opacity(dim ? 0.35 : 1)
            .onAppear { if !calm { withAnimation(.easeInOut(duration: 0.7).repeatForever(autoreverses: true)) { dim = true } } }
    }
}

/// "3 live": how many open bets have a game in progress.
struct LiveCountPill: View {
    let n: Int
    var body: some View {
        HStack(spacing: 6) { LiveDot(); Text("\(n) live").font(.caption.weight(.semibold)) }
            .foregroundStyle(.red)
            .padding(.horizontal, 10).padding(.vertical, 3)
            .background(Color.red.opacity(0.12), in: Capsule())
    }
}

/// A number that counts from its old value to its new one when animated (600 ms, eased by the caller).
struct CountingText: View, Animatable {
    var value: Double
    var digits = 0
    var animatableData: Double { get { value } set { value = newValue } }
    var body: some View { Text(digits == 0 ? String(Int(value.rounded())) : String(format: "%.\(digits)f", value)) }
}

/// An ESPN logo or headshot, or nothing (the caller's fallback) when there's none or it fails.
struct LiveImage<Fallback: View>: View {
    let url: String?
    var size: CGFloat
    var round = false
    @ViewBuilder var fallback: () -> Fallback

    var body: some View {
        if let url, let u = URL(string: url) {
            AsyncImage(url: u) { phase in
                switch phase {
                case .success(let img): img.resizable().aspectRatio(contentMode: round ? .fill : .fit)
                case .failure: fallback()
                default: Color.clear
                }
            }
            .frame(width: size, height: size)
            .clipShape(round ? AnyShape(Circle()) : AnyShape(Rectangle()))
        } else {
            fallback()
        }
    }
}

extension Color {
    /// "#rrggbb"
    init?(hex: String?) {
        guard let hex, hex.count == 7, let v = Int(hex.dropFirst(), radix: 16) else { return nil }
        self.init(red: Double((v >> 16) & 0xff) / 255, green: Double((v >> 8) & 0xff) / 255, blue: Double(v & 0xff) / 255)
    }
}

/// One bet's tracker (open or settled); nothing when none of its games was found. Since the overhaul (Nov 4) each leg is a
/// ring around its picture. `head: false`: the card above already shows the one game's score, so only the legs follow.
/// A bet across games reads game by game (a score line, then its legs) under its dots, which fold the legs away on a
/// long slip. `folded` (the Settled tab, Mike, Oct 23) starts it collapsed under a one-line summary.
struct LiveBetView: View {
    let b: BetLive
    var folded = false
    var head = true
    @State private var open = false
    @State private var legsShown: Bool?

    /// A long slip across games starts as its dots; tap them for the legs.
    private var expanded: Bool { legsShown ?? (b.legs.count <= 6) }

    var body: some View {
        if folded {
            // one line: the two teams' logos (one game), the leg segments and the result, "NE 24 @ CHI 30 · Hit",
            // "5 games · 5 of 8 hit" (web ltrack-fold)
            DisclosureGroup(isExpanded: $open) { sections.padding(.vertical, 6) } label: {
                HStack(spacing: 10) {
                    if b.games.count == 1, let g = b.games.first?.reading {
                        HStack(spacing: 2) {
                            LiveImage(url: g.away.logo, size: 16) { EmptyView() }
                            LiveImage(url: g.home.logo, size: 16) { EmptyView() }
                        }
                    }
                    bars.frame(minWidth: 40, maxWidth: 140)
                    Text(foldText).font(.caption.monospaced().weight(.medium)).lineLimit(1).layoutPriority(1)
                        .foregroundStyle(b.status == "won" ? .green : b.status == "lost" ? .red : .secondary)
                }
            }
            .font(.caption)
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(Color.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
        } else if !head && b.games.count == 1 {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(Array(b.legs.enumerated()), id: \.offset) { LiveLegRow(l: $0.element) }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            VStack(alignment: .leading, spacing: 12) {
                if b.legs.count > 1 {
                    Button { withAnimation(.easeInOut(duration: 0.2)) { legsShown = !expanded } } label: {
                        HStack(spacing: 8) {
                            LegDots(legs: b.legs)
                            Spacer(minLength: 6)
                            Text(b.status == "lost" ? "Lost" : b.status == "won" ? "Won" : "\(b.hit) of \(b.total) in")
                                .font(.footnote.weight(.semibold))
                                .foregroundStyle(b.status == "won" ? .green : b.status == "lost" ? .red : .secondary)
                            Image(systemName: "chevron.down").font(.caption2.weight(.bold)).foregroundStyle(.tertiary)
                                .rotationEffect(.degrees(expanded ? 180 : 0))
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(expanded ? "Hide the legs" : "Show the legs")
                }
                if expanded || b.legs.count <= 1 { sections }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// One section per game, its legs under its score line (an SGP+ reads game by game, as FanDuel shows it); legs
    /// whose game isn't on today come last.
    private var sections: some View {
        let sections = b.games.map { g in (g, b.legs.filter { $0.gameKey == g.key }) }
        let elsewhere = b.legs.filter { l in l.gameKey == nil || !b.games.contains { $0.key == l.gameKey } }
        return VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(sections.enumerated()), id: \.element.0.key) { i, s in
                if i > 0 { Hairline() }
                LiveScoreStrip(g: s.0)
                ForEach(Array(s.1.enumerated()), id: \.offset) { LiveLegRow(l: $0.element) }
            }
            if !elsewhere.isEmpty {
                if !sections.isEmpty { Hairline() }
                HStack(spacing: 10) {
                    Text("LATER").font(.caption2.weight(.semibold)).tracking(0.6).foregroundStyle(.secondary).frame(minWidth: 54, alignment: .leading)
                    Text("Not on today").font(.caption.monospaced()).foregroundStyle(.secondary)
                }
                ForEach(Array(elsewhere.enumerated()), id: \.offset) { LiveLegRow(l: $0.element) }
            }
        }
    }

    private var foldText: String {
        let g = b.games.first?.reading, ufc = g?.sport == "ufc"
        let sc = { (x: Double?) in ufc ? "" : " \(x.map(Live.js) ?? "")" }
        let head = b.games.count == 1 && g != nil ? "\(g!.away.abbr.isEmpty ? g!.away.name : g!.away.abbr)\(sc(g!.away.score)) \(g!.between) \(g!.home.abbr.isEmpty ? g!.home.name : g!.home.abbr)\(sc(g!.home.score)) · "
            : "\(b.games.count) games · "
        return head + (b.legs.count > 1 ? "\(b.hit) of \(b.total) hit" : b.legs.first?.text ?? "")
    }

    /// One thin segment per leg: green won, red lost, grey void or open.
    private var bars: some View {
        HStack(spacing: 3) {
            ForEach(Array(b.legs.enumerated()), id: \.offset) { _, l in
                Capsule().fill(l.status == .won ? Color.green : l.status == .lost ? .red : l.status == .void ? .secondary : Color(.systemGray4))
                    .frame(height: 4)
            }
        }
    }
}

/// Confetti and "CASHED +11.50u" counting up, over the tracker (Mike, Oct 23: the cash animation). Under Reduce Motion
/// only the badge shows.
struct CashOverlay: View {
    let win: Double?
    @Environment(\.accessibilityReduceMotion) private var calm
    @State private var fall = false
    @State private var pop = false
    @State private var shown = 0.0

    private struct Piece { let x, delay, dur, rot, drift, w: Double; let color: Color; let round: Bool }
    private static let colors: [Color] = [.green, .blue, Color(red: 0.96, green: 0.77, blue: 0.27), Color(red: 1, green: 0.44, blue: 0.69),
                                          Color(red: 0.35, green: 0.82, blue: 1), .white]
    @State private var pieces: [Piece] = (0..<46).map { i in
        Piece(x: .random(in: 0...1), delay: .random(in: 0...0.35), dur: .random(in: 1.6...2.8), rot: .random(in: -360...360),
              drift: .random(in: -30...30), w: .random(in: 5...10), color: colors[i % colors.count], round: i % 3 == 0)
    }

    var body: some View {
        GeometryReader { geo in
            ZStack {
                if !calm {
                    ForEach(pieces.indices, id: \.self) { i in
                        let p = pieces[i]
                        RoundedRectangle(cornerRadius: p.round ? p.w / 2 : 2)
                            .fill(p.color)
                            .frame(width: p.w, height: p.round ? p.w : p.w * 1.8)
                            .rotationEffect(.degrees(fall ? p.rot : 0))
                            .position(x: p.x * geo.size.width + (fall ? p.drift : 0), y: fall ? 520 : -12)
                            .animation(.linear(duration: p.dur).delay(p.delay), value: fall)
                    }
                }
                VStack(spacing: 2) {
                    Text("CASHED").font(.caption2.monospaced().weight(.bold)).tracking(1.5)
                    if win != nil {
                        HStack(spacing: 0) { Text("+"); CountingText(value: shown, digits: 2); Text("u") }
                            .font(.system(size: 26, weight: .heavy, design: .monospaced))
                    }
                }
                .foregroundStyle(.green)
                .padding(.horizontal, 18).padding(.vertical, 10)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
                .shadow(radius: 8)
                .scaleEffect(pop || calm ? 1 : 0.6)
                .position(x: geo.size.width / 2, y: geo.size.height * 0.42)
            }
        }
        .allowsHitTesting(false)
        .onAppear {
            fall = true
            if calm { shown = win ?? 0; return }
            withAnimation(.spring(response: 0.5, dampingFraction: 0.55)) { pop = true }
            withAnimation(.easeOut(duration: 0.6)) { shown = win ?? 0 }
        }
    }
}

/// LIVE (or FINAL, or the start in ET), each team as logo, abbreviation and score over a team-color underline (the
/// leader brighter; UFC: fighter photos, "vs", no score), then the clock. A changed score pops 1.45x in green.
struct LiveScoreStrip: View {
    let g: GameLive

    var body: some View {
        let g = g.reading                       // soccer: home first (Nov 5)
        let ufc = g.sport == "ufc", scored = !ufc && g.state != "pre"
        let a = g.away.score ?? 0, h = g.home.score ?? 0
        HStack(spacing: 10) {
            Group {
                if g.state == "in" { HStack(spacing: 5) { LiveDot(); Text("LIVE") }.foregroundStyle(.red) }
                else if g.state == "post" { Text("FINAL").foregroundStyle(.secondary) }
                else { Text(Models.date(g.start).map { Self.time.string(from: $0) } ?? "").foregroundStyle(.secondary) }
            }
            .font(.caption2.weight(.semibold)).tracking(0.6).frame(minWidth: 54, alignment: .leading)
            HStack(spacing: 8) {
                LiveTeam(s: g.away, score: scored ? a : nil, lead: scored && a > h, ufc: ufc, ball: g.ball == "away")
                Text(g.between).foregroundStyle(.tertiary).fontWeight(.regular)
                LiveTeam(s: g.home, score: scored ? h : nil, lead: scored && h > a, ufc: ufc, ball: g.ball == "home")
            }
            .lineLimit(1)
            Spacer(minLength: 0)
            if g.redZone { Text("RED ZONE").font(.caption2.weight(.heavy)).foregroundStyle(.white)
                .padding(.horizontal, 6).padding(.vertical, 2).background(.red, in: Capsule()) }
            if g.state != "pre" { Text(g.detail + (g.down.map { " · \($0)" } ?? "")).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
        }
        .font(.footnote.monospaced().weight(.semibold))
    }

    private static let time: DateFormatter = {
        let f = DateFormatter()
        f.timeZone = Fmt.et
        f.dateFormat = "h:mm a"
        return f
    }()
}

struct LiveTeam: View {
    let s: LiveSide
    let score: Double?
    let lead: Bool
    let ufc: Bool
    var ball = false               // football: this side has the ball (Oct 25)
    @Environment(\.accessibilityReduceMotion) private var calm
    @State private var shown: Double = 0
    @State private var bump = false

    var body: some View {
        HStack(spacing: 6) {
            CardTap(ref: ufc || s.logo == nil ? nil : CardRef(kind: .team, name: s.name, abbr: s.abbr)) {
                LiveImage(url: s.logo, size: 18, round: ufc) { EmptyView() }
            }
            Text(s.abbr.isEmpty ? s.name : s.abbr)
            if ball { Image(systemName: "football.fill").font(.caption2).accessibilityLabel("has the ball") }
            if score != nil {
                CountingText(value: shown).fontWeight(.bold)
                    .scaleEffect(bump ? 1.45 : 1)
                    .foregroundStyle(bump ? Color.green : (lead ? .primary : .secondary))
            }
        }
        .foregroundStyle(lead ? .primary : .secondary)
        .padding(.bottom, 2)
        .overlay(alignment: .bottom) { if let c = Color(hex: s.color) { Rectangle().fill(c.opacity(0.7)).frame(height: 2) } }
        .onAppear { shown = score ?? 0 }
        .onChange(of: score) { old, new in
            guard let new else { return }
            if calm { shown = new; return }
            withAnimation(.easeOut(duration: 0.6)) { shown = new }
            guard old != nil, old != new else { return }
            withAnimation(.easeOut(duration: 0.18)) { bump = true }
            withAnimation(.easeOut(duration: 1.0).delay(0.2)) { bump = false }
        }
    }
}

/// One leg: its ring (LegRing: the picture, the number so far as a badge, on-court dot, lost and void looks), the
/// label, where it stands in words ("8 to go", "In · he has 2"), and "current/target unit" counting when it moves. A leg
/// that turns won glows green.
struct LiveLegRow: View {
    let l: LegLive
    @Environment(\.accessibilityReduceMotion) private var calm
    @State private var shown: Double = 0
    @State private var glow = false

    var body: some View {
        let ring = LegRing(l: l)
        let look = ring.look
        HStack(alignment: .center, spacing: 14) {
            ring
            VStack(alignment: .leading, spacing: 2) {
                Text(l.label).font(.subheadline.weight(.semibold)).strikethrough(look == .lost, color: .red.opacity(0.6))
                    .foregroundStyle(look == .lost || look == .void ? .secondary : .primary)
                    .fixedSize(horizontal: false, vertical: true)
                if !l.text.isEmpty {
                    Text(l.text).font(.footnote)
                        .foregroundStyle(look == .won ? .green : look == .lost ? .red : look == .behind ? .orange : .secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 6)
            if l.current != nil, let t = l.target {
                HStack(spacing: 0) {
                    CountingText(value: shown).bold().foregroundStyle(.primary)
                    Text("/\(Live.js(t))\(!l.unit.isEmpty && l.unit != "total" ? " \(l.unit)" : "")")
                }
                .font(.footnote.monospaced()).foregroundStyle(.secondary).fixedSize()
            }
        }
        .padding(6)
        .background(RoundedRectangle(cornerRadius: Kit.inner).fill(Color.green.opacity(glow ? 0.12 : 0)))
        .overlay(RoundedRectangle(cornerRadius: Kit.inner).strokeBorder(Color.green.opacity(glow ? 0.35 : 0), lineWidth: 3))
        .padding(-6)
        .onAppear { shown = l.current ?? 0 }
        .onChange(of: l.current) { _, new in
            if calm { shown = new ?? 0 } else { withAnimation(.easeOut(duration: 0.6)) { shown = new ?? 0 } }
        }
        .onChange(of: l.status) { old, new in
            guard !calm, old != .won, new == .won else { return }
            withAnimation(.easeOut(duration: 0.4)) { glow = true }
            withAnimation(.easeOut(duration: 1.2).delay(0.4)) { glow = false }
        }
    }
}
