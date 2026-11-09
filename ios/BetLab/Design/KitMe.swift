import SwiftUI

// The overhaul's pieces for Build, the game page and Me (Nov 4, docs/OVERHAUL.md), beside Kit.swift: the theme's page
// and card colors as plain values, a chip, a price button, a player's photo by name, a tile and a row for Me.

extension Theme {
    var pageColor: Color { page ?? Color(.systemGroupedBackground) }
    var cardColor: Color { card ?? Color(.secondarySystemGroupedBackground) }
    /// Text that reads on the accent (the slip bar, a filled button): dark on a dark theme's bright accent, white on a light one's.
    func onAccent(_ device: ColorScheme) -> Color { (scheme ?? device) == .dark ? Color(white: 0.05) : .white }
}

/// A pill to pick one of a few (sports, market tabs, a chart's range): the picked one is solid, the rest sit on the card.
struct PickChip: View {
    let text: String
    let on: Bool
    let action: () -> Void
    @Environment(\.theme) private var theme

    var body: some View {
        Button(action: action) {
            Text(text).font(.subheadline.weight(.semibold)).lineLimit(1)
                .padding(.horizontal, 14).padding(.vertical, 7)
                .background(on ? Color.primary : theme.cardColor, in: Capsule())
                .foregroundStyle(on ? Color(.systemBackground) : .secondary)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// A price button's look: a quiet cell; picked, the accent as a tint and a ring.
struct PriceCell: ViewModifier {
    let on: Bool
    var dim = false
    @Environment(\.theme) private var theme

    func body(content: Content) -> some View {
        content
            .frame(maxWidth: .infinity, minHeight: 48)
            .padding(.horizontal, 6)
            .background(on ? theme.accent.opacity(0.18) : Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Kit.inner, style: .continuous).strokeBorder(theme.accent, lineWidth: on ? 1.5 : 0))
            .foregroundStyle(on ? theme.accent : Color.primary)
            .opacity(dim && !on ? 0.45 : 1)
    }
}

extension View {
    func priceCell(on: Bool, dim: Bool = false) -> some View { modifier(PriceCell(on: on, dim: dim)) }
}

/// Initials on a quiet circle: what shows when a team or player has no picture.
struct Monogram: View {
    let name: String
    var size: CGFloat = 40
    var color: Color? = nil

    var body: some View {
        let words = name.split(separator: " ")
        let text = words.count > 1 ? String(words.first!.prefix(1) + words.last!.prefix(1)) : String(name.prefix(2))
        Text(text.uppercased()).font(.system(size: size * 0.36, weight: .bold)).foregroundStyle(.secondary)
            .frame(width: size, height: size)
            .background((color ?? Color.secondary).opacity(0.18), in: Circle())
            .accessibilityHidden(true)
    }
}

/// Headshots found this run, by player name: a row asks once, and the slip bar reads what the rows already found.
@MainActor
final class Faces: ObservableObject {
    static let shared = Faces()
    @Published private(set) var urls: [String: String] = [:]
    private var asked: Set<String> = []

    static func sport(_ s: String) -> String {
        switch s { case "nba": "NBA"; case "nfl": "NFL"; case "nhl": "NHL"; case "wnba": "WNBA"
        case "ncaaf", "ncaab", "ufc": s.uppercased(); default: "Soccer" }
    }

    func find(_ name: String, sport: String) async {
        guard !asked.contains(name) else { return }
        asked.insert(name)
        if let u = await Players.headshot(name, sport: Self.sport(sport)).url { urls[name] = u }
    }
}

/// A player's photo by name (ESPN's search, cached a day), his initials until it loads or when there is none.
struct PlayerFace: View {
    let name: String
    let sport: String
    var size: CGFloat = 40
    @ObservedObject private var faces = Faces.shared

    var body: some View {
        LiveImage(url: faces.urls[name], size: size, round: true) { Monogram(name: name, size: size) }
            .frame(width: size, height: size)
            .background(Color(.tertiarySystemFill), in: Circle())
            .task(id: name) { await faces.find(name, sport: sport) }
    }
}

/// A team's logo, or its initials.
struct TeamLogo: View {
    let url: String?
    let name: String
    var size: CGFloat = 32
    var round = false

    var body: some View {
        LiveImage(url: url, size: size, round: round) { Monogram(name: name, size: size) }
            .frame(width: size, height: size)
    }
}

/// A tile on Me: a small name, then whatever leads (a count, a step, a face).
struct MeTile<Content: View>: View {
    let name: String
    @ViewBuilder var content: () -> Content
    @Environment(\.theme) private var theme

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(name.uppercased()).font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
            content()
            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, minHeight: 104, alignment: .topLeading)
        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
        .contentShape(RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
    }
}

/// A row inside a card on Me: its name, a quiet note or tag, and a chevron.
struct MeRow<Trailing: View>: View {
    let title: String
    var note: String? = nil
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        HStack(spacing: 10) {
            Text(title).font(.body.weight(.semibold)).foregroundStyle(.primary)
            Spacer(minLength: 6)
            if let note { Text(note).font(.footnote).foregroundStyle(.secondary).lineLimit(1) }
            trailing()
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
        }
        .padding(.vertical, 15)
        .contentShape(Rectangle())
    }
}

extension MeRow where Trailing == EmptyView {
    init(_ title: String, note: String? = nil) { self.init(title: title, note: note) { EmptyView() } }
}

/// Two soft lights in a page's top corners: a game's two team colors behind its score.
struct PageGlow: View {
    let left: Color?
    let right: Color?
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        GeometryReader { g in
            if let left { light(left).position(x: 40, y: 20) }
            if let right { light(right).position(x: g.size.width - 40, y: 20) }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func light(_ c: Color) -> some View {
        Circle().fill(c).frame(width: 280, height: 280).blur(radius: 70).opacity(scheme == .dark ? 0.5 : 0.3)
    }
}
