import SwiftUI

// Color themes (Mike, Oct 24: "as many color themes as possible, more than the web app"). The web has Device, Light,
// Dark, Pink, Gold, Purple and Rose (web/lib/looks.ts, globals.css); the iPhone has those and more. A theme sets the
// light or dark scheme, the accent (buttons, links, chips), the page and the cards. Kept on the phone (AppStorage
// "appearance", the old Appearance picker's key: "system", "light" and "dark" still mean what they did).

struct Theme: Identifiable, Equatable {
    let id: String
    let name: String
    let scheme: ColorScheme?
    let accent: Color
    let page: Color?        // the screen behind the cards; nil: the system's
    let card: Color?        // a card (list row, tracker, tile); nil: the system's

    private static func c(_ hex: String) -> Color { Color(hex: "#" + hex) ?? .gray }
    private static let green = Color(red: 0.13, green: 0.68, blue: 0.38)

    static let all: [Theme] = [
        Theme(id: "system", name: "Device", scheme: nil, accent: green, page: nil, card: nil),
        Theme(id: "light", name: "Light", scheme: .light, accent: green, page: nil, card: nil),
        Theme(id: "dark", name: "Dark", scheme: .dark, accent: green, page: nil, card: nil),
        // the web's themes
        Theme(id: "midnight", name: "Midnight", scheme: .dark, accent: c("8ea2ff"), page: c("0d0f13"), card: c("161a20")),
        Theme(id: "pink", name: "Pink", scheme: .dark, accent: c("ff5fa8"), page: c("0c0a0c"), card: c("1a1218")),
        Theme(id: "gold", name: "Gold", scheme: .dark, accent: c("e2b84a"), page: c("0b0a08"), card: c("1a1710")),
        Theme(id: "purple", name: "Purple", scheme: .dark, accent: c("b18cff"), page: c("0d0b12"), card: c("19152a")),
        Theme(id: "rose", name: "Rose", scheme: .light, accent: c("d6337f"), page: c("fbf1f5"), card: c("ffffff")),
        // the iPhone's own
        Theme(id: "ocean", name: "Ocean", scheme: .dark, accent: c("38bdf8"), page: c("06131f"), card: c("0d2233")),
        Theme(id: "forest", name: "Forest", scheme: .dark, accent: c("4ade80"), page: c("07120b"), card: c("102018")),
        Theme(id: "crimson", name: "Crimson", scheme: .dark, accent: c("f43f5e"), page: c("120608"), card: c("220d12")),
        Theme(id: "sunset", name: "Sunset", scheme: .dark, accent: c("fb923c"), page: c("140a06"), card: c("26150d")),
        Theme(id: "neon", name: "Neon", scheme: .dark, accent: c("39ff14"), page: c("050505"), card: c("111411")),
        Theme(id: "cyber", name: "Cyber", scheme: .dark, accent: c("f0abfc"), page: c("0a0614"), card: c("170f2b")),
        Theme(id: "slate", name: "Slate", scheme: .dark, accent: c("94a3b8"), page: c("0f1115"), card: c("1b1f26")),
        Theme(id: "coffee", name: "Coffee", scheme: .dark, accent: c("d4a373"), page: c("120d09"), card: c("221912")),
        Theme(id: "mint", name: "Mint", scheme: .light, accent: c("0f9d78"), page: c("eefaf5"), card: c("ffffff")),
        Theme(id: "sky", name: "Sky", scheme: .light, accent: c("2563eb"), page: c("eef4ff"), card: c("ffffff")),
        Theme(id: "lavender", name: "Lavender", scheme: .light, accent: c("7c3aed"), page: c("f4f0ff"), card: c("ffffff")),
        Theme(id: "peach", name: "Peach", scheme: .light, accent: c("ea580c"), page: c("fff4ec"), card: c("ffffff")),
        Theme(id: "lemon", name: "Lemon", scheme: .light, accent: c("ca8a04"), page: c("fffbe6"), card: c("ffffff")),
        Theme(id: "paper", name: "Paper", scheme: .light, accent: c("111827"), page: c("f5f3ee"), card: c("fffdf8")),
    ]

    static func named(_ id: String) -> Theme { all.first { $0.id == id } ?? all[0] }
}

private struct ThemeKey: EnvironmentKey { static let defaultValue = Theme.all[0] }
extension EnvironmentValues {
    var theme: Theme { get { self[ThemeKey.self] } set { self[ThemeKey.self] = newValue } }
}

extension View {
    /// A list's page and cards in the theme's colors (the system's when the theme has none). Put it on the List.
    func themedList() -> some View { modifier(ThemedList()) }
    /// A card's background: the theme's card color, else `fallback`.
    func themedCard(_ fallback: Color = Color(.secondarySystemGroupedBackground), radius: CGFloat = 12) -> some View {
        modifier(ThemedCard(fallback: fallback, radius: radius))
    }
}

extension View {
    /// Every row of a list on the theme's card color. Put it on a Group around the list's sections.
    func themedRows() -> some View { modifier(ThemedRows()) }
}

private struct ThemedRows: ViewModifier {
    @Environment(\.theme) private var theme
    func body(content: Content) -> some View { content.listRowBackground(theme.card) }
}

private struct ThemedList: ViewModifier {
    @Environment(\.theme) private var theme
    func body(content: Content) -> some View {
        if let page = theme.page {
            content.scrollContentBackground(.hidden).background(page)
        } else {
            content
        }
    }
}

private struct ThemedCard: ViewModifier {
    @Environment(\.theme) private var theme
    let fallback: Color
    let radius: CGFloat
    func body(content: Content) -> some View {
        content.background(theme.card ?? fallback, in: RoundedRectangle(cornerRadius: radius))
    }
}

/// The picker in Settings: every theme as a swatch.
struct ThemePicker: View {
    @Binding var selection: String

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 92), spacing: 10)], spacing: 10) {
            ForEach(Theme.all) { t in
                Button { selection = t.id } label: {
                    VStack(spacing: 6) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 12).fill(t.page ?? (t.scheme == .dark ? Color.black : Color(.systemGray6)))
                            VStack(spacing: 4) {
                                RoundedRectangle(cornerRadius: 4).fill(t.card ?? (t.scheme == .dark ? Color(white: 0.15) : .white)).frame(height: 14)
                                RoundedRectangle(cornerRadius: 4).fill(t.accent).frame(width: 30, height: 8)
                            }
                            .padding(8)
                        }
                        .frame(height: 50)
                        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(selection == t.id ? t.accent : Color.secondary.opacity(0.25),
                                                                                lineWidth: selection == t.id ? 2.5 : 1))
                        Text(t.name).font(.caption.weight(selection == t.id ? .bold : .regular)).foregroundStyle(.primary)
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 4)
    }
}
