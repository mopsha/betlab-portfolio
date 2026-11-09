import SwiftUI
import UIKit

/// Settings > App icon (Mike's W12, Nov 2): the home-screen icon, by look, season or team. iPhone only; each is a device's own
/// choice. Colors from ESPN, no logos: scripts/make_app_icons.py lists them (app_icons.json), make_app_icons.swift draws them.
struct AppIconChoice: Decodable, Identifiable, Hashable {
    let id: String, title: String, group: String, bg: String, fg: String, tag: String
    let stripe: String?

    static let all: [AppIconChoice] = {
        guard let url = Bundle.main.url(forResource: "app_icons", withExtension: "json"), let data = try? Data(contentsOf: url) else { return [] }
        return (try? JSONDecoder().decode([AppIconChoice].self, from: data)) ?? []
    }()
    static let groups = ["Looks", "Seasons", "NFL", "NBA", "NHL"]
}

private func hex(_ h: String) -> Color {
    let v = Int(h, radix: 16) ?? 0
    return Color(red: Double((v >> 16) & 255) / 255, green: Double((v >> 8) & 255) / 255, blue: Double(v & 255) / 255)
}

private struct IconPreview: View {
    let bg: String, fg: String, tag: String
    var stripe: String? = nil

    var body: some View {
        ZStack(alignment: .bottom) {
            hex(bg)
            if let stripe { hex(stripe).frame(height: 4) }
            VStack(spacing: 0) {
                Text("B").font(.system(size: tag.isEmpty ? 28 : 22, weight: .bold))
                if !tag.isEmpty { Text(tag).font(.system(size: 8, weight: .bold)) }
            }
            .foregroundStyle(hex(fg))
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(width: 44, height: 44)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

struct AppIconRow: View {
    var body: some View {
        NavigationLink("App icon") { AppIconPicker() }
    }
}

struct AppIconPicker: View {
    @State private var current = UIApplication.shared.alternateIconName
    @State private var search = ""
    @State private var error: String?

    private func set(_ id: String?) {
        error = nil
        UIApplication.shared.setAlternateIconName(id) { e in
            DispatchQueue.main.async {
                if let e { error = e.localizedDescription } else { current = id }
            }
        }
    }

    private func row(title: String, id: String?, preview: IconPreview) -> some View {
        Button { set(id) } label: {
            HStack(spacing: 12) {
                preview
                Text(title).foregroundStyle(.primary)
                Spacer()
                if current == id { Image(systemName: "checkmark").foregroundStyle(.tint) }
            }
        }
    }

    var body: some View {
        List { Group {
            if let error { Text(error).foregroundStyle(.red) }
            if search.isEmpty {
                row(title: "BetLab", id: nil, preview: IconPreview(bg: "2f4fd8", fg: "ffffff", tag: ""))
            }
            ForEach(AppIconChoice.groups, id: \.self) { g in
                let items = AppIconChoice.all.filter { $0.group == g && (search.isEmpty || $0.title.localizedCaseInsensitiveContains(search)) }
                if !items.isEmpty {
                    Section(g) {
                        ForEach(items) { i in
                            row(title: i.title, id: i.id, preview: IconPreview(bg: i.bg, fg: i.fg, tag: i.tag, stripe: i.stripe))
                        }
                    }
                }
            }
        }.themedRows() }.themedList()
        .searchable(text: $search, prompt: "Search teams")
        .navigationTitle("App icon")
        .navigationBarTitleDisplayMode(.inline)
    }
}
