import SwiftUI

/// Model and Markets as one place: the model's strengths and weak spots, and what each sport has.
struct ModelMarketsView: View {
    @State private var show = "model"

    var body: some View {
        Group {
            if show == "model" { ModelView() } else { MarketsView() }
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                Picker("Show", selection: $show) { Text("Model").tag("model"); Text("Markets").tag("markets") }
                    .pickerStyle(.segmented).frame(width: 200)
            }
        }
    }
}

// MARK: - Markets

/// What each sport has, side by side (docs app/coverage; docs/COVERAGE.md).
struct MarketsView: View {
    @EnvironmentObject private var store: BetStore
    @State private var doc: JSON?
    @State private var loaded = false

    var body: some View {
        List { Group {
            if let c = doc {
                let cols = c["columns"].array.compactMap(\.string)
                let rows = c["rows"].array.map { $0.array.compactMap(\.string) }
                Section {
                    StatTable(head: cols, rows: rows.map { r in r.enumerated().map { i, v in
                        TCell(text: v, color: i == 0 ? nil : v.hasPrefix("✓") ? .green : v.hasPrefix("✗") ? .red : v.lowercased().hasPrefix("planned") ? .orange : nil, bold: i == 0)
                    } }, leading: Set(0..<cols.count))
                }
                let key = c["key"].array.compactMap(\.string), notes = c["notes"].array.compactMap(\.string)
                if !key.isEmpty || !notes.isEmpty {
                    Section {
                        DisclosureGroup("What the columns mean") {
                            ForEach(key, id: \.self) { Text("• " + $0).font(.footnote) }
                            ForEach(notes, id: \.self) { Text($0).font(.footnote).foregroundStyle(.secondary) }
                        }
                    }
                }
            } else if loaded {
                Text("The table appears after the next cloud run.").foregroundStyle(.secondary)
            }
        }.themedRows() }.themedList()
        .navigationTitle("Markets")
        .subtitle(doc?["updated"].string.map { "updated \($0)" })
        .overlay { if !loaded { ProgressView() } }
        .task { doc = try? await store.api.doc("app", "coverage", as: JSON.self); loaded = true }
    }
}
