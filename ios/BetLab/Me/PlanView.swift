import SwiftUI

struct Todo: Decodable, Identifiable, Hashable {
    let id: String
    let owner: String
    var title: String = ""
    var detail: String? = nil
    var due: String? = nil
    var status: String = "open"
    var doneAt: String? = nil
    var ord: Double? = nil
}

/// The to-do list Mike and Claude share (web More > Plan): tick items, add your own or a request for Claude
/// (read at the start of every Claude session).
struct PlanView: View {
    @EnvironmentObject private var store: BetStore
    @State private var todos: [Todo] = []
    @State private var loaded = false
    @State private var title = ""
    @State private var forClaude = false
    @State private var hasDue = false
    @State private var due = Date()
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        List { Group {
            Section {
                TextField("Add a to-do or ask Claude for something", text: $title, axis: .vertical)
                Picker("For", selection: $forClaude) { Text("For me").tag(false); Text("For Claude").tag(true) }.pickerStyle(.segmented)
                Toggle("Due date", isOn: $hasDue)
                if hasDue { DatePicker("Due", selection: $due, displayedComponents: .date) }
                Button(busy ? "Adding…" : "Add") { add() }.disabled(busy || title.trimmingCharacters(in: .whitespaces).isEmpty)
                if let error { Text(error).foregroundStyle(.red) }
            }
            column("For you", "you")
            column("For Claude", "claude")
        }.themedRows() }.themedList()
        .navigationTitle("Plan")
        .subtitle("what each of us owes next")
        .overlay { if !loaded { ProgressView() } }
        .refreshable { await load() }
        .task(id: store.refreshTick) { await load() }
    }

    @ViewBuilder private func column(_ name: String, _ owner: String) -> some View {
        let items = todos.filter { $0.owner == owner }
        let open = items.filter { $0.status != "done" }.sorted { ($0.due ?? "9999", $0.ord ?? 0) < ($1.due ?? "9999", $1.ord ?? 0) }
        let done = items.filter { $0.status == "done" }.sorted { ($0.doneAt ?? "") > ($1.doneAt ?? "") }
        Section("\(name) · \(open.count) open") {
            if open.isEmpty { Text("Nothing open.").foregroundStyle(.secondary) }
            ForEach(open) { TodoRow(t: $0) { await set($0, done: $1) } }
            if !done.isEmpty {
                DisclosureGroup("Done (\(done.count))") { ForEach(done.prefix(40)) { TodoRow(t: $0) { await set($0, done: $1) } } }
            }
        }
    }

    private func load() async {
        todos = (try? await store.api.rows("todos")) ?? todos
        loaded = true
    }

    private func add() {
        busy = true
        let d = Calendar.current.dateComponents([.year, .month, .day], from: due)
        let row: [String: Any?] = ["owner": forClaude ? "claude" : "you", "title": String(title.trimmingCharacters(in: .whitespaces).prefix(300)),
                                   "due": hasDue ? String(format: "%04d-%02d-%02d", d.year!, d.month!, d.day!) : nil,
                                   "added_by": "app", "ord": Int(Date().timeIntervalSince1970 * 1000)]
        Task {
            do { try await store.api.insert("todos", row); title = ""; hasDue = false; error = nil; await load() }
            catch { self.error = (error as? AuthError)?.message ?? "Couldn't add that." }
            busy = false
        }
    }

    private func set(_ t: Todo, done: Bool) async {
        try? await store.api.update("todos", eq: [("id", t.id)],
                                    ["status": done ? "done" : "open", "done_at": done ? ISO8601DateFormatter().string(from: Date()) : nil])
        await load()
    }
}

private struct TodoRow: View {
    let t: Todo
    let toggle: (Todo, Bool) async -> Void
    @State private var busy = false

    var body: some View {
        let done = t.status == "done"
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Button {
                    busy = true
                    Task { await toggle(t, !done); busy = false }
                } label: {
                    Image(systemName: done ? "checkmark.circle.fill" : "circle").foregroundStyle(done ? Color.green : Color.secondary)
                }
                .buttonStyle(.plain).disabled(busy)
                Text(t.title).strikethrough(done).foregroundStyle(done ? .secondary : .primary)
                Spacer()
                if !done, let due = t.due { dueTag(due) }
            }
            if let d = t.detail, !d.isEmpty {
                DisclosureGroup("More") { Text(d).font(.footnote).foregroundStyle(.secondary) }.font(.caption)
            }
        }
    }

    private func dueTag(_ due: String) -> some View {
        let today = BetMath.etDay(Date())
        let days = Int(((Models.date(due + "T12:00:00Z")?.timeIntervalSince(Models.date(today + "T12:00:00Z") ?? Date()) ?? 0) / 86400).rounded())
        let f = DateFormatter(); f.dateFormat = "EEE MMM d"; f.timeZone = TimeZone(identifier: "UTC")
        let text = days < 0 ? "overdue" : days == 0 ? "today" : days == 1 ? "tomorrow" : (Models.date(due + "T12:00:00Z").map { f.string(from: $0) } ?? due)
        return TagView(text: text, color: days < 0 ? .red : days <= 1 ? .orange : .secondary)
    }
}
