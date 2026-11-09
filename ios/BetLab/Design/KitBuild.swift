import SwiftUI

// The overhaul's pieces for Build as reorganized (Nov 5, docs/OVERHAUL.md), beside Kit.swift: a row of underlined
// tabs (the modes, a game's markets), a round icon button for a header, the
// grade as a round badge, and a quiet cell with a hairline between numbers.

/// A row of words, the picked one underlined in the accent (Build · Check a slip · Use a promo; a game's markets).
/// It scrolls sideways when the words run past the screen, and keeps the picked one in view.
struct UnderTabs: View {
    struct Item: Identifiable, Equatable { let key: String; let title: String; var id: String { key } }
    let items: [Item]
    let selected: String
    var spacing: CGFloat = 20
    var font: Font = .subheadline.weight(.semibold)
    let pick: (String) -> Void
    @Environment(\.theme) private var theme

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: spacing) {
                    ForEach(items) { t in
                        let on = t.key == selected
                        Button { pick(t.key) } label: {
                            VStack(spacing: 6) {
                                Text(t.title).font(font).foregroundStyle(on ? Color.primary : .secondary)
                                Capsule().fill(on ? theme.accent : Color.clear).frame(height: 3)
                            }
                            .fixedSize()
                            .frame(minHeight: 44, alignment: .bottom)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(on ? .isSelected : [])
                        .id(t.key)
                    }
                }
                .padding(.horizontal)
            }
            .onChange(of: selected) { _, key in withAnimation { proxy.scrollTo(key, anchor: .center) } }
        }
    }
}

/// A header's round button: an icon on the card's color, 40 points across inside a 44-point target.
struct IconDisc: View {
    let systemName: String
    var onCard = false
    @Environment(\.theme) private var theme

    var body: some View {
        Image(systemName: systemName).font(.system(size: 16, weight: .semibold)).foregroundStyle(.primary)
            .frame(width: 40, height: 40)
            .background(onCard ? Color(.tertiarySystemFill) : theme.cardColor, in: Circle())
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
    }
}

/// A slip's grade as a round badge: green for A−/B+ and up, orange for B to C, red below (web gradeClass).
struct GradeBadge: View {
    let grade: String
    let idx: Int
    var size: CGFloat = 44

    static func color(_ idx: Int) -> Color { idx <= 3 ? .green : idx <= 6 ? .orange : .red }

    var body: some View {
        let c = Self.color(idx)
        Text(grade).font(.system(size: size * 0.42, weight: .heavy)).foregroundStyle(c)
            .frame(width: size, height: size)
            .background(c.opacity(0.18), in: Circle())
            .accessibilityLabel("Grade \(grade)")
    }
}

/// Numbers side by side under small names, a hairline between each (chance, fair price, edge).
struct CellRow: View {
    struct Cell: Identifiable { let name: String; let value: String; var color: Color = .primary; var id: String { name } }
    let cells: [Cell]

    var body: some View {
        HStack(spacing: 14) {
            ForEach(Array(cells.enumerated()), id: \.element.id) { i, c in
                if i > 0 { Rectangle().fill(Color.primary.opacity(0.08)).frame(width: 1, height: 34) }
                StatCell(name: c.name, value: c.value, color: c.color)
            }
        }
    }
}
