import SwiftUI

// The overhaul's pieces for Promos and the Ladder (Nov 5, docs/OVERHAUL.md), beside Kit.swift: a token as a thing you
// hold (the book's picture, the value large, its limits as chips, a perforation above its actions), the two buttons
// those screens use, chips that wrap, a card that folds, and a team's logo found by its name.

/// The one main button on a card: the accent, filled.
struct SolidButton: ButtonStyle {
    var tall = true
    func makeBody(configuration: Configuration) -> some View { Face(configuration: configuration, tall: tall) }

    private struct Face: View {
        let configuration: Configuration
        let tall: Bool
        @Environment(\.theme) private var theme
        @Environment(\.colorScheme) private var scheme
        @Environment(\.isEnabled) private var enabled

        var body: some View {
            configuration.label
                .font(.subheadline.weight(.bold)).lineLimit(1).minimumScaleFactor(0.8)
                .padding(.horizontal, 18).frame(minHeight: tall ? 46 : 38)
                .foregroundStyle(theme.onAccent(scheme))
                .background(theme.accent, in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
                .opacity(!enabled ? 0.45 : configuration.isPressed ? 0.75 : 1)
        }
    }
}

/// A quiet button beside the main one: a soft cell, the text in the page's ink (red when it removes something).
struct SoftButton: ButtonStyle {
    var tall = true
    var danger = false
    func makeBody(configuration: Configuration) -> some View { Face(configuration: configuration, tall: tall, danger: danger) }

    private struct Face: View {
        let configuration: Configuration
        let tall: Bool
        let danger: Bool
        @Environment(\.isEnabled) private var enabled

        var body: some View {
            configuration.label
                .font(.subheadline.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.8)
                .padding(.horizontal, 14).frame(minHeight: tall ? 46 : 38)
                .foregroundStyle(danger ? Color.red : Color.primary)
                .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
                .opacity(!enabled ? 0.45 : configuration.isPressed ? 0.6 : 1)
        }
    }
}

/// A sportsbook's own picture (the icons BookButton opens bets with); a ticket when the token names no book.
struct BookIcon: View {
    let book: String?
    var size: CGFloat = 30

    /// The book's color, for a soft light behind what it gave you.
    static func color(_ book: String?) -> Color? {
        switch (book ?? "").lowercased() {
        case "fanduel": Color(hex: "#1b8dff")
        case "draftkings": Color(hex: "#5bb318")
        case "novig": Color(hex: "#7f6bff")
        default: nil
        }
    }

    var body: some View {
        if let book, Marking.books.contains(where: { $0.lowercased() == book.lowercased() }) {
            Image("book-" + book.lowercased()).resizable().interpolation(.high).scaledToFit()
                .frame(width: size, height: size)
                .clipShape(RoundedRectangle(cornerRadius: size * 0.24, style: .continuous))
                .accessibilityLabel(Marking.bookOf(book))
        } else {
            Image(systemName: "ticket.fill").font(.system(size: size * 0.46, weight: .semibold)).foregroundStyle(.secondary)
                .frame(width: size, height: size)
                .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: size * 0.24, style: .continuous))
                .accessibilityLabel(book ?? "Any book")
        }
    }
}

/// Chips that wrap onto as many lines as they need.
struct ChipFlow: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = place(subviews, width: proposal.width ?? .infinity)
        return CGSize(width: proposal.width ?? rows.width, height: rows.height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let rows = place(subviews, width: bounds.width)
        for (i, at) in rows.points.enumerated() {
            subviews[i].place(at: CGPoint(x: bounds.minX + at.x, y: bounds.minY + at.y), proposal: .unspecified)
        }
    }

    private func place(_ subviews: Subviews, width: CGFloat) -> (points: [CGPoint], width: CGFloat, height: CGFloat) {
        var points: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, line: CGFloat = 0, widest: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > 0, x + s.width > width { x = 0; y += line + spacing; line = 0 }
            points.append(CGPoint(x: x, y: y))
            x += s.width + spacing
            line = max(line, s.height)
            widest = max(widest, x - spacing)
        }
        return (points, widest, y + line)
    }
}

/// One limit on a token ("3+ legs", "NBA", "Knicks"), with a small picture when it names a league or a team.
struct TermChip<Art: View>: View {
    let text: String
    var tone: Color? = nil
    @ViewBuilder var art: () -> Art

    var body: some View {
        HStack(spacing: 5) {
            art()
            Text(text).font(.caption.weight(.semibold)).lineLimit(1)
        }
        .padding(.horizontal, 9).padding(.vertical, 5)
        .foregroundStyle(tone ?? Color.secondary)
        .background((tone ?? Color.primary).opacity(tone == nil ? 0.07 : 0.14), in: Capsule())
    }
}

extension TermChip where Art == EmptyView {
    init(_ text: String, tone: Color? = nil) { self.init(text: text, tone: tone) { EmptyView() } }
}

/// Team logos found by name this run (ESPN's team search, cached a day): a token names its teams in words.
@MainActor
final class TeamFaces: ObservableObject {
    static let shared = TeamFaces()
    @Published private(set) var urls: [String: String] = [:]
    private var asked: Set<String> = []

    /// The league a name belongs to when it is one of the NFL, NBA or NHL teams ("Knicks" -> NBA); "" for any other.
    static func league(_ name: String) -> String {
        let n = name.lowercased()
        for (lg, rows) in Bans.teams where rows.contains(where: { $0.name.lowercased().contains(n) || $0.abbr.contains(name.uppercased()) }) {
            return lg.uppercased()
        }
        return ""
    }

    func find(_ name: String, sport: String?) async {
        guard !asked.contains(name) else { return }
        asked.insert(name)
        let lg = Self.league(name)
        let look = await Cards.look(.team, name, sport: lg.isEmpty ? (sport.map(Faces.sport) ?? "") : lg)
        if let u = look.logo ?? look.url { urls[name] = u }
    }
}

/// A team's logo by its name alone; nothing until (or unless) one is found, so a chip stays a plain chip.
struct TeamFace: View {
    let name: String
    var sport: String? = nil
    var size: CGFloat = 16
    @ObservedObject private var faces = TeamFaces.shared

    var body: some View {
        Group {
            if let u = faces.urls[name] { LiveImage(url: u, size: size) { EmptyView() } }
        }
        .task(id: name) { await faces.find(name, sport: sport) }
    }
}

/// A league's own logo where ESPN has one (the sport chips' source); nothing for the rest.
struct LeagueMark: View {
    let league: String
    var size: CGFloat = 16
    private static let logos: Set<String> = ["nfl", "nba", "nhl", "mlb", "wnba"]

    var body: some View {
        if Self.logos.contains(league) {
            LiveImage(url: "https://a.espncdn.com/i/teamlogos/leagues/500/\(league).png", size: size) { EmptyView() }
        }
    }
}

/// A ticket's tear line: dashes across the card, with a notch bitten out of each edge.
struct Perforation: View {
    var inset: CGFloat = Kit.pad
    @Environment(\.theme) private var theme

    var body: some View {
        GeometryReader { g in
            Path { p in p.move(to: CGPoint(x: 0, y: 0.5)); p.addLine(to: CGPoint(x: g.size.width, y: 0.5)) }
                .stroke(Color.primary.opacity(0.16), style: StrokeStyle(lineWidth: 1, dash: [4, 5]))
        }
        .frame(height: 1)
        .overlay(alignment: .leading) { notch.offset(x: -inset - 9) }
        .overlay(alignment: .trailing) { notch.offset(x: inset + 9) }
        .accessibilityHidden(true)
    }

    private var notch: some View { Circle().fill(theme.pageColor).frame(width: 18, height: 18) }
}

/// A token as a thing you hold: the book that gave it, what kind it is, its value large, when it ends, and its limits
/// as chips. The wallet adds its actions under the tear line; the finder shows it small (`compact`).
struct TokenCard<Actions: View>: View {
    let p: PromoRow
    var now = Date()
    var compact = false
    var selected = false
    @ViewBuilder var actions: () -> Actions
    @Environment(\.theme) private var theme

    /// "$10", "50%": the number the token is.
    static func value(_ p: PromoRow) -> String {
        if p.kind == "boost" { return (p.pct.map { String(format: "%g", $0) } ?? "?") + "%" }
        return p.amountDollars.map(Promos.dollars) ?? "$?"
    }
    static func kind(_ p: PromoRow) -> String { p.kind == "boost" ? "Profit boost" : "Bonus bet" }

    /// When it ends, and whether that is soon enough to be orange: today (Eastern), or within 12 hours.
    static func ends(_ p: PromoRow, now: Date) -> (text: String, soon: Bool)? {
        guard let t = Promos.date(p.expiresAt) else { return nil }
        let words = Promos.expires(p, now: now).replacingOccurrences(of: "expires", with: "ends")
        let left = t.timeIntervalSince(now)
        return (words, left > 0 && (left < 12 * 3600 || BetMath.etDay(t) == BetMath.etDay(now)))
    }

    var body: some View {
        GlowCard(right: BookIcon.color(p.book), padding: compact ? 14 : Kit.pad) {
            VStack(alignment: .leading, spacing: compact ? 8 : 14) {
                HStack(alignment: .center, spacing: 10) {
                    BookIcon(book: p.book, size: compact ? 26 : 34)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(Self.kind(p).uppercased()).font(.caption2.weight(.bold)).foregroundStyle(.secondary)
                        if !compact { Text(p.book ?? "Any book").font(.footnote.weight(.semibold)) }
                    }
                    Spacer(minLength: 6)
                    if selected { Image(systemName: "checkmark.circle.fill").foregroundStyle(theme.accent) }
                    else if !compact, let e = Self.ends(p, now: now) { endsLabel(e) }
                }
                HeroNumber(text: Self.value(p), size: compact ? 30 : 46)
                    .accessibilityLabel(Promos.title(p))
                if compact, let e = Self.ends(p, now: now) { endsLabel(e) }
                if !compact {
                    let chips = Self.chips(p)
                    if !chips.isEmpty || p.teams?.isEmpty == false {
                        ChipFlow(spacing: 6) {
                            ForEach(Array(chips.enumerated()), id: \.offset) { _, c in
                                TermChip(text: c.text) { if let lg = c.league { LeagueMark(league: lg, size: 14) } }
                            }
                            ForEach(p.teams ?? [], id: \.self) { t in
                                TermChip(text: t) { TeamFace(name: t, sport: Promos.sports(p)?.first, size: 15) }
                            }
                        }
                    }
                    if let note = p.note, !note.isEmpty { Text(note).font(.footnote).foregroundStyle(.secondary) }
                    if Actions.self != EmptyView.self {
                        Perforation()
                        actions()
                    }
                }
            }
        }
        .overlay {
            if selected { RoundedRectangle(cornerRadius: Kit.radius, style: .continuous).strokeBorder(theme.accent, lineWidth: 1.5) }
        }
    }

    private func endsLabel(_ e: (text: String, soon: Bool)) -> some View {
        Text(e.text).font(.caption.weight(.semibold)).foregroundStyle(e.soon ? Color.orange : Color.secondary)
            .lineLimit(1).minimumScaleFactor(0.8)
    }

    /// The token's limits, one chip each (what Promos.terms says in one line), sports with their league.
    static func chips(_ p: PromoRow) -> [(text: String, league: String?)] {
        var out: [(String, String?)] = []
        if p.kind == "boost", let a = p.amountDollars { out.append(("up to \(Promos.dollars(a))", nil)) }
        if let c = p.maxExtraDollars { out.append(("max \(Promos.dollars(c)) extra", nil)) }
        if let l = p.minLegs, l > 1 { out.append(("\(l)+ legs", nil)) }
        switch (p.minOdds, p.maxOdds) {
        case let (lo?, hi?): out.append(("\(Fmt.am(lo)) to \(Fmt.am(hi))", nil))
        case let (lo?, nil): out.append(("\(Fmt.am(lo)) or longer", nil))
        case let (nil, hi?): out.append(("\(Fmt.am(hi)) or shorter", nil))
        default: break
        }
        for k in Promos.sports(p) ?? [] { out.append((Promos.sportChoices.first { $0.0 == k }?.1 ?? k.uppercased(), k)) }
        if let m = p.market { out.append((Promos.marketName(m), nil)) }
        for g in p.games ?? [] { out.append((g.matchup, nil)) }
        return out
    }
}

extension TokenCard where Actions == EmptyView {
    init(p: PromoRow, now: Date = Date(), compact: Bool = false, selected: Bool = false) {
        self.init(p: p, now: now, compact: compact, selected: selected) { EmptyView() }
    }
}

/// A card that folds: its title and a quiet note, the rest one tap away.
struct FoldCard<Content: View>: View {
    let title: String
    var note: String? = nil
    @State var open = false
    @ViewBuilder var content: () -> Content

    var body: some View {
        GlowCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                Button { withAnimation(.easeOut(duration: 0.2)) { open.toggle() } } label: {
                    HStack(spacing: 8) {
                        Text(title).font(.body.weight(.semibold)).foregroundStyle(.primary)
                        Spacer(minLength: 6)
                        if let note { Text(note).font(.footnote).foregroundStyle(.secondary).lineLimit(1) }
                        Image(systemName: "chevron.down").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
                            .rotationEffect(.degrees(open ? 180 : 0))
                    }
                    .padding(.horizontal, Kit.pad).padding(.vertical, 15)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(.isHeader)
                if open {
                    content().padding(.horizontal, Kit.pad).padding(.bottom, Kit.pad)
                }
            }
        }
    }
}
