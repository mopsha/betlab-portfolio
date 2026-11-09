import SwiftUI

// The overhaul's live pieces (Nov 4, docs/OVERHAUL.md), built on Kit.swift: a game's score as the head of a card (both
// logos, the big score, the clock as a pill), and a leg as a ring around its player's photo or team's logo. Today and
// Live both draw their bets from these, so a bet looks the same on both.

extension View {
    /// A card as a list row: on the page's background, no separator, a little air above and below.
    func cardRow() -> some View {
        listRowBackground(Color.clear).listRowSeparator(.hidden)
            .listRowInsets(EdgeInsets(top: 6, leading: 0, bottom: 6, trailing: 0))
    }
}

/// A thin line inside a card.
struct Hairline: View {
    var body: some View { Rectangle().fill(Color.primary.opacity(0.08)).frame(height: 1) }
}

/// A score that counts to its new value and pops green when it changes (still under Reduce Motion).
struct BigScore: View {
    let score: Double
    var size: CGFloat = 34
    var lead = true
    @Environment(\.accessibilityReduceMotion) private var calm
    @State private var shown: Double = 0
    @State private var bump = false

    var body: some View {
        CountingText(value: shown)
            .font(.system(size: size, weight: .heavy)).monospacedDigit().kerning(-1)
            .lineLimit(1).minimumScaleFactor(0.55)          // a 3-digit score shrinks, never wraps ("11 / 3", Nov 6)
            .foregroundStyle(bump ? Color.green : .primary)
            .opacity(lead || bump ? 1 : 0.62)
            .scaleEffect(bump ? 1.18 : 1)
            .onAppear { shown = score }
            .onChange(of: score) { old, new in
                if calm { shown = new; return }
                withAnimation(.easeOut(duration: 0.6)) { shown = new }
                guard old != new else { return }
                withAnimation(.easeOut(duration: 0.18)) { bump = true }
                withAnimation(.easeOut(duration: 1.0).delay(0.2)) { bump = false }
            }
    }
}

/// A team's logo (a fighter's photo in UFC), opening its card; its abbreviation in a circle when ESPN has no art.
struct TeamArt: View {
    let s: LiveSide
    var size: CGFloat = 38
    var ufc = false

    var body: some View {
        CardTap(ref: ufc || s.logo == nil ? nil : CardRef(kind: .team, name: s.name, abbr: s.abbr)) {
            LiveImage(url: s.logo, size: size, round: ufc) { monogram }
        }
        .accessibilityLabel(s.name)
    }

    private var monogram: some View {
        Text(String((s.abbr.isEmpty ? s.name : s.abbr).prefix(3)).uppercased())
            .font(.system(size: size * 0.3, weight: .heavy)).foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(Color(hex: s.color) ?? Color(.systemGray2), in: Circle())
    }
}

/// One game as the head of a card: logo and score on each side, the clock between them. Before the start, the two
/// teams and the time; UFC has no score.
struct ScoreHead: View {
    let g: GameLive
    private static let time: DateFormatter = { let f = DateFormatter(); f.timeZone = Fmt.et; f.dateFormat = "h:mm a"; return f }()
    private static let dayTime: DateFormatter = { let f = DateFormatter(); f.timeZone = Fmt.et; f.dateFormat = "EEE h:mm a"; return f }()

    var body: some View {
        let g = g.reading                       // soccer: home first (Nov 5)
        let ufc = g.sport == "ufc", scored = !ufc && g.state != "pre"
        let a = g.away.score ?? 0, h = g.home.score ?? 0
        HStack(alignment: .center, spacing: 6) {
            side(g.away, score: scored ? a : nil, lead: a >= h, ufc: ufc, ball: g.ball == "away")
            Spacer(minLength: 4)
            middle
            Spacer(minLength: 4)
            side(g.home, score: scored ? h : nil, lead: h >= a, ufc: ufc, trailing: true, ball: g.ball == "home")
        }
    }

    @ViewBuilder private var middle: some View {
        VStack(spacing: 4) {
            if g.state == "in" {
                if g.redZone { Text("RED ZONE").font(.caption2.weight(.heavy)).foregroundStyle(.red) }
                LivePill(text: g.detail.isEmpty ? "Live" : g.detail)
                // the down and distance on its own line under the clock
                if let down = g.down { Text(down).font(.caption2.weight(.semibold)).foregroundStyle(.secondary).lineLimit(1) }
            } else if g.state == "post" {
                Text(g.detail.isEmpty ? "Final" : g.detail).font(.caption2.weight(.bold)).foregroundStyle(.secondary)
                    .padding(.horizontal, 9).padding(.vertical, 5).background(Color.primary.opacity(0.08), in: Capsule())
            } else {
                Text(Models.date(g.start).map(start) ?? "").font(.caption.weight(.bold)).foregroundStyle(.secondary)
            }
        }
        .lineLimit(1)
        .fixedSize()            // the clock keeps its words ("22.9 - 4th"); the scores shrink instead (Nov 6)
    }

    /// The start: "9:30 PM" today, "Sun 9:30 AM" another day.
    private func start(_ d: Date) -> String {
        BetMath.etDay(d) == BetMath.etDay(Date()) ? Self.time.string(from: d) : Self.dayTime.string(from: d)
    }

    @ViewBuilder
    private func side(_ s: LiveSide, score: Double?, lead: Bool, ufc: Bool, trailing: Bool = false, ball: Bool = false) -> some View {
        let logo = TeamArt(s: s, size: 38, ufc: ufc)
        let name = Text(s.abbr.isEmpty ? s.name : s.abbr).font(.subheadline.weight(.bold)).lineLimit(1).minimumScaleFactor(0.7)
        let number = VStack(alignment: trailing ? .trailing : .leading, spacing: 0) {   // the score before the spacers give way
            if let score { BigScore(score: score, lead: lead) } else { name }
            // football: this side has the ball
            if ball {
                Image(systemName: "football.fill").font(.caption2).foregroundStyle(.secondary)
                    .accessibilityLabel("\(s.abbr.isEmpty ? s.name : s.abbr) has the ball")
            }
        }
        HStack(spacing: 10) {
            if trailing { number; logo } else { logo; number }
        }
        .layoutPriority(1)
    }
}

/// A leg as a ring (Kit's RingArt) around its player's photo or its team's logo. The ring fills toward the target and
/// the badge is the number so far; won closes it in green, lost turns it red. A leg with no number to count (a team to
/// win) shows where it stands as a part ring: mostly full when ahead, a quarter when behind.
struct LegRing: View {
    let l: LegLive
    var size: CGFloat = 46
    var tap = true

    enum Look { case won, lost, void, pending, live, ahead, behind }
    var look: Look {
        switch l.status {
        case .won: .won
        case .lost: .lost
        case .void: .void
        case .pending: .pending
        case .losing: .behind
        case .winning: .ahead
        default: .live
        }
    }
    var tint: Color {
        switch look {
        case .won, .ahead: .green
        case .lost: .red
        case .behind: .orange
        case .live: .accentColor
        case .void, .pending: Color(.systemGray3)
        }
    }

    private var progress: Double? {
        if look == .lost || look == .void { return 1 }
        if let c = l.current, let t = l.target, t > 0 { return max(0, min(1, c / t)) }
        switch look {
        case .ahead: return 0.75
        case .behind: return 0.25
        case .live: return 0.5
        default: return nil
        }
    }

    var body: some View {
        let dim = look == .lost || l.onCourt == false
        CardTap(ref: tap && l.img != nil ? l.card : nil) {
            RingArt(progress: progress, tint: tint, badge: l.current.map(Live.js), done: look == .won, size: size) {
                art.grayscale(look == .lost ? 0.85 : l.onCourt == false ? 0.6 : 0).opacity(dim ? 0.6 : 1)
            }
            .overlay(alignment: .bottomTrailing) { if l.current == nil { mark.offset(x: 4, y: 3) } }
            .overlay(alignment: .topLeading) {       // basketball: on the floor now
                if l.onCourt == true {
                    Circle().fill(.green).frame(width: 11, height: 11)
                        .overlay(Circle().strokeBorder(Color(.systemBackground), lineWidth: 2))
                        .accessibilityLabel("on the court")
                }
            }
        }
    }

    /// The picture: a headshot fills the ring, a team's logo sits inside it; the leg's initials when there is none.
    @ViewBuilder private var art: some View {
        let d = size - 10
        if l.card?.kind == .team {
            ZStack {
                Color(.tertiarySystemFill)
                LiveImage(url: l.img, size: d * 0.7) { initials }
            }
            .frame(width: d, height: d)
        } else {
            LiveImage(url: l.img, size: d, round: true) { initials.frame(width: d, height: d).background(Color(.tertiarySystemFill)) }
                .background(Color(.tertiarySystemFill))
        }
    }

    /// A leg that's on no one shows its market (web marketMark): O, U, BTS, X; else the leg's initials.
    static func marketMark(_ label: String) -> String? {
        let l = label.lowercased()
        return l.hasPrefix("over") ? "O" : l.hasPrefix("under") ? "U" : l.hasPrefix("both teams") ? "BTS" : l.hasPrefix("draw") ? "X" : nil
    }

    private var initials: some View {
        let words = (l.card == nil ? Self.marketMark(l.label) : nil)
            ?? l.label.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined().uppercased()
        return Text(words).font(.system(size: size * 0.28, weight: .heavy)).foregroundStyle(.secondary)
    }

    /// Without a number: a green check, a red cross, a grey dash; nothing while the leg is in play or to come.
    @ViewBuilder private var mark: some View {
        if look == .won || look == .lost || look == .void {
            Image(systemName: look == .won ? "checkmark" : look == .lost ? "xmark" : "minus")
                .font(.system(size: 8, weight: .heavy)).foregroundStyle(look == .won ? .black : .white)
                .frame(width: 18, height: 18)
                .background(look == .void ? Color(.systemGray2) : tint, in: Circle())
        }
    }
}

/// A parlay's legs as dots: filled green in, red lost, grey void, an open ring in play, a faint dot to come.
struct LegDots: View {
    let legs: [LegLive]
    var size: CGFloat = 11

    var body: some View {
        HStack(spacing: 5) {
            ForEach(Array(legs.enumerated()), id: \.offset) { _, l in
                switch l.status {
                case .won: Circle().fill(.green).frame(width: size, height: size)
                case .lost: Circle().fill(.red).frame(width: size, height: size)
                case .void: Circle().fill(Color(.systemGray2)).frame(width: size, height: size)
                case .pending, .unknown: Circle().fill(Color(.systemFill)).frame(width: size, height: size)
                default: Circle().strokeBorder(l.status == .losing ? Color.orange : .accentColor, lineWidth: 2.5).frame(width: size, height: size)
                }
            }
        }
        .accessibilityHidden(true)
    }
}

enum KitLive {
    /// Units as the big numbers say them: "+1.3u", "−0.25u", "5u" (two decimals at most, none it doesn't need).
    static func units(_ u: Double, signed: Bool = false) -> String {
        let r = (abs(u) * 100).rounded() / 100
        let n = r == r.rounded() ? String(Int(r)) : String(format: "%g", r)
        return (signed ? (u < 0 && r > 0 ? Fmt.minus : "+") : "") + n + "u"
    }

    /// The logos of a live bet's games, away then home, each once: the stack on a parlay across games.
    static func logos(_ b: BetLive) -> [String] {
        var seen = Set<String>()
        return b.games.flatMap { [$0.away.logo, $0.home.logo] }.compactMap { $0 }.filter { seen.insert($0).inserted }
    }
}
