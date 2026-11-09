import SwiftUI

// The overhaul's pieces for Friends and Ask BetLab (Nov 5, docs/OVERHAUL.md), beside Kit.swift: a button in the look
// (the accent filled, or quiet on the card), chips that wrap onto lines, a day as people say it, and a row of players
// or teams as rings around their pictures.

/// A button in the look: the accent filled (a card's main button), quiet on a fill, or red to confirm a removal.
struct KitButton: ButtonStyle {
    enum Kind { case solid, quiet, danger }
    var kind: Kind = .solid
    var wide = true
    var height: CGFloat = 44
    @Environment(\.theme) private var theme
    @Environment(\.colorScheme) private var scheme
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.bold)).lineLimit(1)
            .padding(.horizontal, 16)
            .frame(maxWidth: wide ? .infinity : nil, minHeight: height)
            .background(fill, in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
            .foregroundStyle(text)
            .opacity(configuration.isPressed ? 0.7 : enabled ? 1 : 0.45)
            .contentShape(RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
    }

    private var fill: Color {
        switch kind { case .solid: theme.accent; case .quiet: Color(.tertiarySystemFill); case .danger: .red }
    }
    private var text: Color {
        switch kind { case .solid: theme.onAccent(scheme); case .quiet: .primary; case .danger: .white }
    }
}

/// A text field in the look: a quiet cell on a card or a sheet.
struct KitField: ViewModifier {
    @Environment(\.theme) private var theme
    var onCard = false
    func body(content: Content) -> some View {
        content.padding(.horizontal, 14).frame(minHeight: 46)
            .background(onCard ? Color(.tertiarySystemFill) : theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
    }
}

extension View {
    func kitField(onCard: Bool = false) -> some View { modifier(KitField(onCard: onCard)) }
}

/// Children left to right, wrapping onto new lines (suggestion chips).
struct Flow: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(proposal.width ?? .infinity, subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let a = arrange(bounds.width, subviews)
        for (i, p) in a.points.enumerated() {
            subviews[i].place(at: CGPoint(x: bounds.minX + p.x, y: bounds.minY + p.y), anchor: .topLeading,
                              proposal: ProposedViewSize(width: min(a.sizes[i].width, bounds.width), height: a.sizes[i].height))
        }
    }

    private func arrange(_ width: CGFloat, _ subviews: Subviews) -> (points: [CGPoint], sizes: [CGSize], size: CGSize) {
        var points: [CGPoint] = [], sizes: [CGSize] = []
        var x: CGFloat = 0, y: CGFloat = 0, line: CGFloat = 0, widest: CGFloat = 0
        for s in subviews {
            let size = s.sizeThatFits(ProposedViewSize(width: width.isFinite ? width : nil, height: nil))
            if x > 0, x + size.width > width { x = 0; y += line + spacing; line = 0 }
            points.append(CGPoint(x: x, y: y)); sizes.append(size)
            x += size.width + spacing
            line = max(line, size.height)
            widest = max(widest, x - spacing)
        }
        return (points, sizes, CGSize(width: width.isFinite ? width : widest, height: y + line))
    }
}

enum KitSocial {
    /// An Eastern day ("2026-11-04") as people say it: Today, Yesterday, else "Monday, Nov 2".
    static func dayTitle(_ day: String, now: Date = Date()) -> String {
        if day == BetMath.etDay(now) { return "Today" }
        if day == BetMath.etDay(BetMath.etShift(now, days: -1)) { return "Yesterday" }
        return Models.date(day + "T16:00:00Z").map(Fmt.longDay) ?? day
    }
}

/// Players or teams as a row of rings around their pictures: the ring is the share of graded legs that hit, the badge
/// the won-lost. A tap opens the card's whole history (CardDetail), from the cards passed in, so a friend's shelf shows
/// the friend's legs.
struct PictureShelf: View {
    let cards: [PlayerCard]
    let kind: CardRef.Kind
    @State private var shots: [String: Players.Headshot] = [:]
    @State private var open: PlayerCard?
    private static let shown = 12

    var body: some View {
        let list = Array(cards.prefix(Self.shown))
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: 14) {
                ForEach(list) { p in
                    Button { open = p } label: { cell(p) }.buttonStyle(.plain)
                        .accessibilityLabel("\(p.name), \(p.won) won, \(p.lost) lost")
                }
            }
            .padding(.vertical, 6)
        }
        .scrollClipDisabled()
        .task(id: list.map(\.key).joined(separator: ",")) {
            await withTaskGroup(of: (String, Players.Headshot).self) { g in
                for p in list where shots[p.key] == nil { g.addTask { (p.key, await Cards.look(kind, p.name, sport: p.sport)) } }
                for await (k, h) in g { shots[k] = h }
            }
        }
        .sheet(item: $open) { p in CardDetail(kind: kind, name: p.name, p: p, shot: shots[p.key]) }
    }

    private func cell(_ p: PlayerCard) -> some View {
        let size: CGFloat = 62, d = size - 10
        let graded = p.won + p.lost > 0
        return VStack(spacing: 7) {
            RingArt(progress: p.hitRate, tint: (p.hitRate ?? 0) >= 0.5 ? .green : .orange,
                    badge: graded ? "\(p.won)-\(p.lost)" : nil, size: size) {
                if kind == .team {
                    ZStack {
                        Color(.tertiarySystemFill)
                        LiveImage(url: shots[p.key]?.url, size: d * 0.68) { Monogram(name: p.name, size: d * 0.68) }
                    }
                } else {
                    LiveImage(url: shots[p.key]?.url, size: d, round: true) { Monogram(name: p.name, size: d) }
                        .background(Color(.tertiarySystemFill))
                }
            }
            Text(kind == .team ? p.name : p.name.split(separator: " ").last.map(String.init) ?? p.name)
                .font(.caption.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.8)
        }
        .frame(width: 78)
    }
}
