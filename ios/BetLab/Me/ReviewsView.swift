import SwiftUI

// MARK: - Reviews

struct Review: Decodable, Identifiable { let id: String; let title: String; let body: String; let createdAt: String }

/// The Tuesday weekly reviews, newest open, older ones folded.
struct ReviewsView: View {
    @EnvironmentObject private var store: BetStore
    @State private var list: [Review] = []
    @State private var loaded = false

    var body: some View {
        List { Group {
            if loaded && list.isEmpty { Text("No reviews yet.").foregroundStyle(.secondary) }
            ForEach(Array(list.enumerated()), id: \.element.id) { i, r in
                Section { ReviewItem(r: r, open: i == 0) }
            }
        }.themedRows() }.themedList()
        .navigationTitle("Reviews")
        .subtitle("every Tuesday")
        .overlay { if !loaded { ProgressView() } }
        .task {
            list = ((try? await store.api.rows("reviews") as [Review]) ?? []).sorted { $0.createdAt > $1.createdAt }
            loaded = true
        }
    }
}

private struct ReviewItem: View {
    let r: Review
    @State var open: Bool
    var body: some View {
        DisclosureGroup(isExpanded: $open) {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(blocks.enumerated()), id: \.offset) { _, b in b }
            }
            .padding(.vertical, 4)
        } label: {
            VStack(alignment: .leading, spacing: 2) {
                Text(Models.date(r.createdAt).map { Fmt.longDay($0) } ?? "").font(.caption).foregroundStyle(.secondary)
                Text(r.title).font(.headline)
            }
        }
    }

    /// Paragraphs, "- " bullet blocks, and one-line headings (a short line with no end punctuation), as the web draws them.
    private var blocks: [AnyView] {
        r.body.components(separatedBy: "\n\n").map { b in
            let lines = b.split(separator: "\n").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
            if !lines.isEmpty && lines.allSatisfy({ $0.hasPrefix("- ") }) {
                return AnyView(VStack(alignment: .leading, spacing: 4) { ForEach(lines, id: \.self) { Text("• " + $0.dropFirst(2)).font(.footnote) } })
            }
            if lines.count == 1, lines[0].count < 60, !".:!?".contains(lines[0].last ?? ".") {
                return AnyView(Text(lines[0]).font(.subheadline.weight(.semibold)).padding(.top, 4))
            }
            return AnyView(Text(b).font(.footnote))
        }
    }
}
