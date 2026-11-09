import SwiftUI

// The overhaul's shared pieces (Nov 4, docs/OVERHAUL.md): what every rebuilt screen is made of, so the screens stop
// hand-rolling cards, chips and headers. The look's rules: cards without outlines, big numbers lead, team color as a
// soft glow behind a score (never a painted band), a leg is a ring that fills toward its target around the player's
// or team's picture, section titles are real headings. The web's twin is web/app/look.css and components/ui.

enum Kit {
    static let radius: CGFloat = 24        // a card
    static let inner: CGFloat = 14         // a button or a cell inside a card
    static let pad: CGFloat = 18
}

/// A card with team color as light: a soft glow in each top corner (a live score's two teams, a pick's team).
/// With no colors it is the plain card every screen uses.
struct GlowCard<Content: View>: View {
    var left: Color? = nil
    var right: Color? = nil
    var padding: CGFloat = Kit.pad
    @ViewBuilder var content: () -> Content
    @Environment(\.theme) private var theme
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        content()
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                ZStack {
                    theme.card ?? Color(.secondarySystemGroupedBackground)
                    GeometryReader { g in
                        if let left { glow(left).position(x: 30, y: -20) }
                        if let right { glow(right).position(x: g.size.width - 30, y: -20) }
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
    }

    private func glow(_ c: Color) -> some View {
        Circle().fill(c).frame(width: 220, height: 220).blur(radius: 46).opacity(scheme == .dark ? 0.42 : 0.24)
    }
}

/// A leg as a ring: it fills toward the target around the player's photo or the team's logo, with the current number
/// as a badge. `done` closes the ring in green.
struct RingArt<Art: View>: View {
    var progress: Double?                  // 0...1; nil draws the empty track
    var tint: Color = .accentColor
    var badge: String? = nil
    var done = false
    var size: CGFloat = 46
    @ViewBuilder var art: () -> Art
    @Environment(\.theme) private var theme

    var body: some View {
        ZStack {
            Circle().stroke(Color(.systemFill), lineWidth: 3.5)
            Circle().trim(from: 0, to: done ? 1 : max(0, min(1, progress ?? 0)))
                .stroke(done ? Color.green : tint, style: StrokeStyle(lineWidth: 3.5, lineCap: .round))
                .rotationEffect(.degrees(-90))
            art().frame(width: size - 10, height: size - 10).clipShape(Circle())
        }
        .frame(width: size, height: size)
        .overlay(alignment: .bottomTrailing) {
            if let badge {
                Text(badge).font(.system(size: 10, weight: .bold, design: .monospaced))
                    .padding(.horizontal, 4).frame(minWidth: 20, minHeight: 18)
                    .foregroundStyle(done ? Color.black : Color(.systemBackground))
                    .background(done ? Color.green : Color.primary, in: Capsule())
                    .overlay(Capsule().strokeBorder(theme.card ?? Color(.secondarySystemGroupedBackground), lineWidth: 2))
                    .offset(x: 6, y: 4)
            }
        }
        .animation(.easeOut(duration: 0.5), value: progress)
    }
}

/// A section's title as a real heading, with a quiet note beside it ("Parlays  2 · next locks in 0:42").
struct SectionTitle<Trailing: View>: View {
    let title: String
    var note: String? = nil
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(title).font(.title3.weight(.bold))
            if let note { Text(note).font(.footnote.weight(.semibold)).foregroundStyle(.secondary) }
            Spacer(minLength: 4)
            trailing()
        }
        .textCase(nil)
    }
}

extension SectionTitle where Trailing == EmptyView {
    init(_ title: String, note: String? = nil) { self.init(title: title, note: note) { EmptyView() } }
}

/// The number a screen leads with: the day's units, a record.
struct HeroNumber: View {
    let text: String
    var color: Color = .primary
    var size: CGFloat = 52
    var body: some View {
        Text(text).font(.system(size: size, weight: .heavy)).monospacedDigit().kerning(-1.5)
            .foregroundStyle(color).lineLimit(1).minimumScaleFactor(0.6)
    }
}

/// A row of small overlapping pictures: what is in a parlay, at a glance.
struct ArtStack: View {
    let urls: [String]
    var size: CGFloat = 30
    @Environment(\.theme) private var theme

    var body: some View {
        HStack(spacing: -8) {
            ForEach(Array(urls.prefix(5).enumerated()), id: \.offset) { _, u in
                LiveImage(url: u, size: size - 4, round: false) { Color(.systemFill) }
                    .frame(width: size, height: size)
                    .background(Color(.tertiarySystemFill), in: Circle())
                    .clipShape(Circle())
                    .overlay(Circle().strokeBorder(theme.card ?? Color(.secondarySystemGroupedBackground), lineWidth: 2))
            }
        }
    }
}

/// A live clock as a red pill ("Q3 4:12").
struct LivePill: View {
    let text: String
    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(.red).frame(width: 6, height: 6)
            Text(text).font(.caption2.weight(.bold))
        }
        .foregroundStyle(.red)
        .padding(.horizontal, 9).padding(.vertical, 5)
        .background(Color.red.opacity(0.14), in: Capsule())
    }
}

/// A small trend line (units over time).
struct Spark: View {
    let values: [Double]
    var color: Color = .green
    var fill = false

    var body: some View {
        GeometryReader { g in
            let lo = values.min() ?? 0, hi = values.max() ?? 1, span = max(hi - lo, 0.0001)
            let pts = values.enumerated().map { i, v in
                CGPoint(x: values.count > 1 ? g.size.width * CGFloat(i) / CGFloat(values.count - 1) : 0,
                        y: g.size.height * (1 - CGFloat((v - lo) / span)) * 0.9 + g.size.height * 0.05)
            }
            ZStack {
                if fill, let first = pts.first, let last = pts.last {
                    Path { p in
                        p.move(to: CGPoint(x: first.x, y: g.size.height)); pts.forEach { p.addLine(to: $0) }
                        p.addLine(to: CGPoint(x: last.x, y: g.size.height)); p.closeSubpath()
                    }
                    .fill(LinearGradient(colors: [color.opacity(0.28), color.opacity(0)], startPoint: .top, endPoint: .bottom))
                }
                Path { p in
                    guard let first = pts.first else { return }
                    p.move(to: first); pts.dropFirst().forEach { p.addLine(to: $0) }
                }
                .stroke(color, style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
            }
        }
        .accessibilityHidden(true)
    }
}

/// A hard top edge where a screen scrolls under the floating header (Nov 6): iOS 26's soft edge let Today's hero number and
/// its line show through and collide with the header's own text. Before iOS 26 there is no soft edge, so nothing changes.
struct HardTopEdge: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) { content.scrollEdgeEffectStyle(.hard, for: .top) } else { content }
    }
}
