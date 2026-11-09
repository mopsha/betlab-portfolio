import ActivityKit
import SwiftUI
import WidgetKit

/// A real bet in play on the lock screen and in the Dynamic Island: its games' scores and each leg as My bets' tracker
/// shows it (status, count against the target, progress), "3 of 5 hit", and the latest event. The worker sends every
/// change (src/betlab/live_activity.py).
struct BetLiveActivity: Widget {
    typealias State = BetActivityAttributes.ContentState

    var body: some WidgetConfiguration {
        ActivityConfiguration(for: BetActivityAttributes.self) { ctx in
            LockScreenBet(name: ctx.attributes.name, toWin: ctx.attributes.toWin, s: ctx.state)
                .padding(.horizontal, 12).padding(.vertical, 10)
                .activityBackgroundTint(Color(red: 0.07, green: 0.08, blue: 0.11).opacity(0.92))
                .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { ctx in
            let s = ctx.state
            return DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text(ctx.attributes.name).font(.caption.weight(.semibold)).lineLimit(1)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    StatusPill(s: s)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(s.games.prefix(2).enumerated()), id: \.offset) { _, g in GameLine(g: g) }
                        ForEach(Array(s.legs.prefix(3).enumerated()), id: \.offset) { _, l in LegLine(l: l) }
                    }
                }
            } compactLeading: {
                Text("\(s.hit)/\(s.total)").font(.caption.weight(.bold).monospacedDigit())
                    .foregroundStyle(s.status == "lost" ? .red : s.status == "won" ? .green : .white)
            } compactTrailing: {
                if let g = s.games.first, g.awayScore != nil {
                    Text("\(g.awayScore ?? "")-\(g.homeScore ?? "")").font(.caption.monospacedDigit())
                } else {
                    Image(systemName: s.over ? LegLook.symbol(s.status) : "dot.radiowaves.left.and.right")
                }
            } minimal: {
                Text("\(s.hit)/\(s.total)").font(.caption2.weight(.bold).monospacedDigit())
            }
        }
    }
}

/// The lock screen as My bets' live tracker shows a bet (LiveBetView): the leg segments and "x of y hit", then each
/// game as a scoreboard band in its teams' colors (logos, scores, the LIVE pill and clock in the middle) with its legs
/// under it. Smaller than in the app: Apple gives a Live Activity about 160 points.
struct LockScreenBet: View {
    let name: String
    var toWin: String? = nil
    let s: BetActivityAttributes.ContentState
    typealias Leg = BetActivityAttributes.Leg

    /// The legs that matter most (a dead one, the live ones, then those to come and those in), at most 2 under two
    /// games or 3 under one, grouped under their games in the bet's order; legs with no game come last.
    static func fit(_ s: BetActivityAttributes.ContentState) -> (sections: [(game: Int?, legs: [Leg])], more: Int) {
        let rank = ["lost": 0, "losing": 1, "tied": 1, "winning": 1, "live": 1, "pending": 2, "unknown": 3, "won": 4, "void": 5]
        let order = s.legs.indices.sorted { (rank[s.legs[$0].status] ?? 3, $0) < (rank[s.legs[$1].status] ?? 3, $1) }
        var keep: [Int] = [], games: [Int] = []
        for i in order {
            let g = s.legs[i].game.flatMap { $0 < s.games.count ? $0 : nil }
            let new = g.map { !games.contains($0) } ?? false
            if new && games.count == 2 { continue }                  // two scoreboards at most
            if keep.count >= (games.count + (new ? 1 : 0) > 1 ? 2 : 3) { continue }
            if new, let g { games.append(g) }
            keep.append(i)
        }
        var sections: [(game: Int?, legs: [Leg])] = games.sorted().map { g in
            (g, keep.sorted().filter { s.legs[$0].game == g }.map { s.legs[$0] })
        }
        let loose = keep.sorted().filter { i in s.legs[i].game.map { !games.contains($0) } ?? true }.map { s.legs[$0] }
        if !loose.isEmpty { sections.append((nil, loose)) }
        if !sections.isEmpty, s.legs.allSatisfy({ $0.game == nil }), !s.games.isEmpty { sections[0].game = 0 }  // older worker
        return (sections, s.more + s.legs.count - keep.count)
    }

    var body: some View {
        let f = Self.fit(s)
        VStack(alignment: .leading, spacing: 3) {
            // the name gets the row (a parlay is named by who's in it, Nov 6); the count sits on the strip it describes
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(name).font(.footnote.weight(.bold)).lineLimit(1).minimumScaleFactor(0.85).layoutPriority(1)
                Spacer(minLength: 4)
                if let toWin {
                    Text("to win \(toWin)").font(.caption2.monospaced().weight(.semibold)).lineLimit(1)
                        .foregroundStyle(s.status == "won" ? .green : s.status == "lost" ? .red : .white.opacity(0.7))
                }
            }
            if s.total > 1 {                                          // every leg, so the ones not listed still show
                HStack(spacing: 8) {
                    LegStrip(s: s)
                    Text(s.status == "lost" ? "Lost" : s.status == "won" ? "Won" : "\(s.hit) of \(s.total) hit")
                        .font(.caption2.monospaced().weight(.semibold)).lineLimit(1).fixedSize()
                        .foregroundStyle(s.status == "won" ? .green : s.status == "lost" ? .red : .white.opacity(0.7))
                }
                .padding(.bottom, 2)
            }
            ForEach(Array(f.sections.enumerated()), id: \.offset) { _, sec in
                if let g = sec.game { TrackerBand(g: s.games[g]) }
                ForEach(Array(sec.legs.enumerated()), id: \.offset) { _, l in LegLine(l: l) }
            }
        }
        .foregroundStyle(.white)
    }
}

/// One segment per leg: green won, red lost, blue under way, grey to come (the tracker's bars).
struct LegStrip: View {
    let s: BetActivityAttributes.ContentState
    var body: some View {
        let shown = s.legs.map(\.status) + Array(repeating: "unknown", count: s.more)
        HStack(spacing: 3) {
            ForEach(Array(shown.enumerated()), id: \.offset) { _, st in
                Capsule().fill(st == "won" ? Color.green : st == "lost" ? .red : st == "pending" || st == "unknown" || st == "void"
                               ? .white.opacity(0.25) : LegLook.tint(st))
                    .frame(height: 4)
            }
        }
    }
}

/// The tracker's scoreboard (GameDay.Scoreboard, compact): each team's logo in a white circle, score and abbreviation,
/// the leader brighter; LIVE and the clock (or FINAL, or the start) in a pill in the middle. The overhaul's look (Nov 6):
/// a dark card with each team's color as a soft light on its own side, never a painted band.
struct TrackerBand: View {
    let g: BetActivityAttributes.Game

    var body: some View {
        let scored = g.state != "pre" && g.awayScore != nil && g.homeScore != nil
        let a = Double(g.awayScore ?? "") ?? 0, h = Double(g.homeScore ?? "") ?? 0
        HStack(alignment: .center) {
            side(g.away, logo: g.awayLogo, score: scored ? g.awayScore : nil, lead: scored && a > h)
            Spacer(minLength: 4)
            VStack(spacing: 1) {
                if g.state == "in" {
                    HStack(spacing: 4) { Circle().fill(.red).frame(width: 5, height: 5); Text("LIVE") }.font(.system(size: 9, weight: .heavy))
                    Text(g.detail).font(.system(size: 10, weight: .semibold).monospacedDigit()).lineLimit(1)
                } else {
                    Text(g.state == "post" ? "FINAL" : g.detail).font(.system(size: 10, weight: .heavy)).lineLimit(1)
                }
            }
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(.black.opacity(0.35), in: Capsule())
            Spacer(minLength: 4)
            side(g.home, logo: g.homeLogo, score: scored ? g.homeScore : nil, lead: scored && h > a, trailing: true)
        }
        .padding(.horizontal, 6).padding(.vertical, 4)
        .background {
            ZStack {
                Color.white.opacity(0.07)
                RadialGradient(colors: [(Self.color(g.awayColor) ?? .gray).opacity(0.55), .clear], center: .leading, startRadius: 0, endRadius: 120)
                RadialGradient(colors: [(Self.color(g.homeColor) ?? .gray).opacity(0.55), .clear], center: .trailing, startRadius: 0, endRadius: 120)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 11))
    }

    private func side(_ abbr: String, logo: String?, score: String?, lead: Bool, trailing: Bool = false) -> some View {
        let pic = Group {
            if let img = LogoStore.image(logo) { Image(uiImage: img).resizable().scaledToFit() }
            else { Text(String(abbr.prefix(3))).font(.system(size: 7, weight: .heavy)).foregroundStyle(.black.opacity(0.6)) }
        }
        .frame(width: 16, height: 16).padding(2).background(.white.opacity(0.9), in: Circle())
        let text = HStack(alignment: .firstTextBaseline, spacing: 4) {
            if trailing, let score { Text(score).font(.system(size: 18, weight: .heavy)).monospacedDigit() }
            Text(abbr).font(.caption2.weight(.bold)).lineLimit(1)
            if !trailing, let score { Text(score).font(.system(size: 18, weight: .heavy)).monospacedDigit() }
        }
        return HStack(spacing: 6) { if trailing { text; pic } else { pic; text } }
            .opacity(score == nil || lead ? 1 : 0.75)
    }

    static func color(_ hex: String?) -> Color? {
        guard let hex, hex.count == 7, let v = Int(hex.dropFirst(), radix: 16) else { return nil }
        return Color(red: Double(v >> 16 & 255) / 255, green: Double(v >> 8 & 255) / 255, blue: Double(v & 255) / 255)
    }
}

/// LIVE / WON / LOST / FINAL and "3 of 5 hit".
struct StatusPill: View {
    let s: BetActivityAttributes.ContentState
    var count = true            // "3 of 5 hit" (the lock screen's leg strip says it already)
    var body: some View {
        let (word, color): (String, Color) = switch s.status {
        case "won": ("WON", .green)
        case "lost": ("LOST", .red)
        case "final": ("FINAL", .gray)
        case "pending": ("SOON", .gray)
        default: ("LIVE", .red)
        }
        HStack(spacing: 5) {
            Text(count && s.total > 1 ? "\(s.hit) of \(s.total) hit" : "").font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
            Text(word).font(.caption2.weight(.heavy)).padding(.horizontal, 6).padding(.vertical, 2)
                .background(color.opacity(0.9), in: Capsule()).foregroundStyle(.white)
        }
    }
}

struct GameLine: View {
    let g: BetActivityAttributes.Game
    var body: some View {
        HStack(spacing: 6) {
            Text(g.away).font(.caption.weight(.semibold))
            if g.state != "pre", let a = g.awayScore, let h = g.homeScore {
                Text("\(a)–\(h)").font(.caption.weight(.heavy).monospacedDigit())
            } else {
                Text("@").font(.caption2).foregroundStyle(.secondary)
            }
            Text(g.home).font(.caption.weight(.semibold))
            Spacer(minLength: 4)
            Text(g.detail).font(.caption2.monospacedDigit()).foregroundStyle(g.state == "in" ? .red : .secondary).lineLimit(1)
        }
    }
}

/// A leg as the app's tracker draws it, small: a ring that fills toward the target (closed green when won, red when lost),
/// its name, and the count so far.
struct LegLine: View {
    let l: BetActivityAttributes.Leg
    var body: some View {
        HStack(spacing: 7) {
            MiniRing(l: l)
            Text(l.label).font(.caption).lineLimit(1).opacity(l.status == "lost" ? 0.55 : 1)
                .strikethrough(l.status == "lost", color: .white.opacity(0.5))
            Spacer(minLength: 4)
            if let v = l.value {
                Text(v).font(.caption.weight(l.status == "pending" ? .regular : .semibold).monospacedDigit())
                    .foregroundStyle(l.status == "pending" ? .white.opacity(0.5) : LegLook.tint(l.status) == .blue ? .white : LegLook.tint(l.status))
            }
        }
    }
}


/// The tracker's leg ring at lock-screen size: a track, the part done in the leg's color, a check or a cross once settled.
struct MiniRing: View {
    let l: BetActivityAttributes.Leg
    var size: CGFloat = 15
    var body: some View {
        let done = l.status == "won" || l.status == "lost"
        let p = done ? 1 : l.status == "pending" || l.status == "void" ? 0 : min(1, max(0.08, l.progress ?? 0.5))
        ZStack {
            Circle().stroke(.white.opacity(0.2), lineWidth: 2.5)
            Circle().trim(from: 0, to: p).stroke(LegLook.tint(l.status), style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                .rotationEffect(.degrees(-90))
            if done {
                Image(systemName: l.status == "won" ? "checkmark" : "xmark").font(.system(size: 7, weight: .black))
                    .foregroundStyle(LegLook.tint(l.status))
            }
        }
        .frame(width: size, height: size)
    }
}
