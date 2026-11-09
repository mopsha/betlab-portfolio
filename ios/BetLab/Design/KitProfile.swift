import SwiftUI

// The overhaul's pieces for Me as reorganized (Nov 5, docs/OVERHAUL.md), beside KitMe.swift: a small range chip with a
// full-size tap area, a two-line row, a chip that is a link, a stack of your players' and teams' pictures, a badge as
// a circle, and a friend's face with today's bet count.

/// A small chip to pick a range beside a big number: the capsule is short, the tap area is 44pt tall.
struct RangeChip: View {
    let text: String
    let on: Bool
    let action: () -> Void
    @Environment(\.theme) private var theme

    var body: some View {
        Button(action: action) {
            Text(text).font(.footnote.weight(.semibold)).lineLimit(1)
                .padding(.horizontal, 11).padding(.vertical, 7)
                .background(on ? Color.primary : theme.cardColor, in: Capsule())
                .foregroundStyle(on ? Color(.systemBackground) : .secondary)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// A row inside a card: its name, a quiet line under it, something leading (pictures) or trailing (a count), a chevron.
struct ProfileRow<Leading: View, Trailing: View>: View {
    let title: String
    let sub: String
    @ViewBuilder var leading: () -> Leading
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        HStack(spacing: 12) {
            leading()
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body.weight(.semibold)).foregroundStyle(.primary)
                Text(sub).font(.footnote).foregroundStyle(.secondary).lineLimit(2).multilineTextAlignment(.leading)
            }
            Spacer(minLength: 6)
            trailing()
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
        }
        .padding(.vertical, 13)
        .frame(minHeight: 44)
        .contentShape(Rectangle())
    }
}

extension ProfileRow where Leading == EmptyView, Trailing == EmptyView {
    init(_ title: String, sub: String) { self.init(title: title, sub: sub) { EmptyView() } trailing: { EmptyView() } }
}

/// A chip that opens a screen (Me's Extras).
struct LinkChip<Destination: View>: View {
    let text: String
    @ViewBuilder var destination: () -> Destination
    @Environment(\.theme) private var theme

    var body: some View {
        NavigationLink { destination() } label: {
            Text(text).font(.subheadline.weight(.semibold)).lineLimit(1)
                .padding(.horizontal, 15).frame(minHeight: 44)
                .background(theme.cardColor, in: Capsule())
                .foregroundStyle(.primary)
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}

/// A few of your players and teams as overlapping pictures (their photos and logos from ESPN, initials until they load).
struct FaceStack: View {
    struct Item: Identifiable, Equatable {
        let kind: CardRef.Kind
        let name: String
        let sport: String
        var id: String { (kind == .team ? "t:" : "p:") + name }
    }
    let items: [Item]
    var size: CGFloat = 34
    @State private var urls: [String: String] = [:]
    @Environment(\.theme) private var theme

    var body: some View {
        HStack(spacing: -9) {
            ForEach(items) { it in
                ZStack {
                    Color(.tertiarySystemFill)
                    if it.kind == .team {
                        LiveImage(url: urls[it.id], size: size * 0.64) { Monogram(name: it.name, size: size * 0.64) }
                    } else {
                        LiveImage(url: urls[it.id], size: size, round: true) { Monogram(name: it.name, size: size) }
                    }
                }
                .frame(width: size, height: size)
                .clipShape(Circle())
                .overlay(Circle().strokeBorder(theme.cardColor, lineWidth: 2))
            }
        }
        .accessibilityHidden(true)
        .task(id: items.map(\.id).joined(separator: ",")) {
            for it in items where urls[it.id] == nil {
                if let u = await Cards.look(it.kind, it.name, sport: it.sport).url { urls[it.id] = u }
            }
        }
    }
}

/// A badge as a circle with its own art: in color once earned, dimmed while locked.
struct BadgeDot: View {
    let badge: Badge
    var size: CGFloat = 52
    @Environment(\.theme) private var theme

    var body: some View {
        let got = badge.earned != nil
        Text(badge.icon).font(.system(size: size * 0.46))
            .grayscale(got ? 0 : 1).opacity(got ? 1 : 0.45)
            .frame(width: size, height: size)
            .background(theme.cardColor, in: Circle())
            .accessibilityLabel("\(badge.title), \(got ? "earned" : "locked")")
    }
}

/// A friend's face: a ring in the accent and a count when they bet today (as Friends draws its row).
struct FriendFace: View {
    let p: Profile
    let today: Int
    @Environment(\.theme) private var theme

    var body: some View {
        VStack(spacing: 6) {
            AvatarView(p: p, size: 52)
                .padding(4)
                .overlay(Circle().strokeBorder(today > 0 ? theme.accent : Color(.systemFill), lineWidth: 2.5))
                .overlay(alignment: .topTrailing) {
                    if today > 0 {
                        Text("\(today)").font(.system(size: 11, weight: .bold, design: .monospaced))
                            .padding(.horizontal, 5).frame(minWidth: 22, minHeight: 20)
                            .foregroundStyle(Color(.systemBackground)).background(Color.primary, in: Capsule())
                            .overlay(Capsule().strokeBorder(theme.pageColor, lineWidth: 2))
                            .offset(x: 4, y: -2)
                    }
                }
            Text(p.name).font(.caption.weight(.semibold)).lineLimit(1)
        }
        .frame(width: 70)
    }
}
