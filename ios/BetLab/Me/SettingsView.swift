import SwiftUI
import UserNotifications

// MARK: - Settings

/// Alerts on this iPhone (PushSection's rows, so Settings has one Alerts section).
struct PushRows: View {
    @ObservedObject private var push = Push.shared
    var body: some View {
        switch push.status {
        case .authorized, .provisional, .ephemeral:
            Label(push.saved ? "On for this iPhone" : "On", systemImage: "bell.badge.fill").foregroundStyle(.green)
        case .denied:
            Text("Off. Turn them on in the iPhone's Settings > Notifications > BetLab.").foregroundStyle(.secondary)
        default:
            Button("Turn on pick alerts") { Task { await push.turnOn() } }
        }
        if let m = push.message { Text(m).font(.footnote).foregroundStyle(.secondary) }
    }
}

/// Settings > Alerts (Mike's #47, Nov 2; web AlertSettings): user_settings.notify, read by the worker's alert_prefs.py.
struct AlertSettingsRows: View {
    @EnvironmentObject private var store: BetStore
    @State private var msg: String?
    @State private var busy = false
    @State private var minEV = ""
    private static let sports = [("nfl", "NFL"), ("ncaaf", "College football"), ("nba", "NBA"), ("ncaab", "College basketball"),
                                 ("nhl", "NHL"), ("soccer", "Soccer"), ("ufc", "UFC")]

    private func save(_ patch: [String: JSON]) {
        msg = nil; busy = true
        Task {
            if let e = await store.setNotify(patch) { msg = e }
            busy = false
        }
    }

    private func flag(_ key: String, _ title: String, on dflt: Bool) -> some View {
        Toggle(title, isOn: Binding(get: { store.notify[key]?.bool ?? dflt }, set: { save([key: .bool($0)]) })).disabled(busy)
    }

    private var quiet: [String: JSON]? { store.notify["quiet"].flatMap { $0.object.isEmpty ? nil : $0.object } }

    private func time(_ key: String, _ title: String) -> some View {
        DatePicker(title, selection: Binding(get: {
            let parts = (quiet?[key]?.string ?? "23:00").split(separator: ":").compactMap { Int($0) }
            return Calendar.current.date(from: DateComponents(hour: parts.first ?? 0, minute: parts.last ?? 0)) ?? Date()
        }, set: { d in
            let c = Calendar.current.dateComponents([.hour, .minute], from: d)
            var q = quiet ?? [:]
            q[key] = .string(String(format: "%02d:%02d", c.hour ?? 0, c.minute ?? 0))
            save(["quiet": .object(q)])
        }), displayedComponents: .hourAndMinute).disabled(busy)
    }

    private func row(_ key: String, _ title: String, _ sub: String, on dflt: Bool) -> some View {
        Toggle(isOn: Binding(get: { store.notify[key]?.bool ?? dflt }, set: { save([key: .bool($0)]) })) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                if !sub.isEmpty { Text(sub).font(.caption).foregroundStyle(.secondary) }
            }
        }
        .disabled(busy)
    }

    var body: some View {
        Section("Send me") {
            row("picks", "New picks", "The moment one is found", on: true)
            row("leans", "Leans too", "A lot more alerts", on: false)
            row("locks", "Parlay locks", "Each slice's tickets, 15 minutes out", on: true)
            row("legs", "My legs", "A leg hits, one is left, it loses, the bet wins", on: true)
            row("news", "A player on my bet goes out", "With the book's rule for it", on: true)
            row("reactions", "A friend reacts to my bet", "", on: true)
            HStack {
                Text("Minimum EV (%)")
                Spacer()
                TextField("Any", text: $minEV).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 70)
                    .onSubmit { saveMinEV() }
                    .onChange(of: minEV) { _, v in if v.isEmpty || Double(v) != nil { saveMinEVSoon() } }
            }
            .onAppear { minEV = store.notify["min_ev"]?.double.map { String(format: "%g", $0) } ?? "" }
            if let msg { Text(msg).foregroundStyle(.red) }
        }
        Section {
            SportChips(on: { store.notify["sports"]?[$0].bool != false }, sports: Self.sports) { key in
                var s = store.notify["sports"]?.object ?? [:]
                s[key] = .bool(store.notify["sports"]?[key].bool == false)
                save(["sports": .object(s)])
            }
            .disabled(busy)
        } header: { Text("Sports") } footer: { Text("For picks, leans and locks.") }
        Section {
            Toggle("Quiet hours", isOn: Binding(get: { quiet != nil }, set: { on in
                save(["quiet": on ? .object(["from": .string("23:00"), "to": .string("08:00")]) : .null])
            })).disabled(busy)
            if quiet != nil {
                time("from", "From")
                time("to", "To")
            }
        } header: { Text("Quiet hours") } footer: {
            Text("Eastern time. What's found in quiet hours arrives when they end, unless the game has started by then; leg alerts are skipped.")
        }
    }

    @State private var pendingSave: Task<Void, Never>?
    private func saveMinEVSoon() {
        pendingSave?.cancel()
        pendingSave = Task {
            try? await Task.sleep(for: .seconds(1))
            if !Task.isCancelled { saveMinEV() }
        }
    }

    private func saveMinEV() {
        let v = Double(minEV)
        if v == store.notify["min_ev"]?.double { return }
        if let v, !(0...50).contains(v) { msg = "Minimum EV is 0 to 50."; return }
        save(["min_ev": v.map(JSON.number) ?? .null])
    }
}

/// Settings > Your books (user_settings.books_off, 0043, Nov 6; web BookSwitches): one switch per book for everything.
struct BooksSection: View {
    @EnvironmentObject private var store: BetStore
    @State private var off: [String] = []
    @State private var msg: String?
    @State private var busy = false
    private static let what = ["FanDuel": "Picks, parlays and links", "DraftKings": "Picks, parlays and links",
                               "Novig": "Game lines, parlay prices, challenges"]

    var body: some View {
        Section {
            ForEach(Marking.books, id: \.self) { b in
                Toggle(isOn: Binding(get: { !off.contains(b) }, set: { on in flip(b, on) })) {
                    HStack(spacing: 12) {
                        BookIcon(book: b, size: 32)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(b)
                            Text(Self.what[b] ?? "").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                .disabled(busy)
            }
            if let msg { Text(msg).foregroundStyle(.red) }
        } footer: {
            Text("A book that's off is gone everywhere: a pick shows at your next best book (or not at all, if no book you have on makes it a bet), parlays, Build and promos price at your books only, and alerts follow.")
        }
        .onAppear { off = store.booksOff }
        .onChange(of: store.booksOff) { _, v in off = v }
    }

    private func flip(_ b: String, _ on: Bool) {
        let next = on ? off.filter { $0 != b } : off + [b]
        guard next.count < Marking.books.count else { msg = "Keep at least one book on."; return }
        let before = off
        off = next; msg = nil; busy = true
        Task {
            if let e = await store.setBooksOff(next) { off = before; msg = e }
            busy = false
        }
    }
}

/// Settings > Friends see my bets (user_settings.share_bets, 0024, Oct 27; web ShareRow): on by default.
struct ShareBetsRow: View {
    @EnvironmentObject private var store: BetStore
    @State private var on = true
    @State private var msg: String?
    @State private var busy = false

    var body: some View {
        Toggle(isOn: Binding(get: { on }, set: { next in
            on = next; msg = nil; busy = true
            Task {
                if let e = await store.setShareBets(next) { on = !next; msg = e }
                busy = false
            }
        })) {
            SettingRow(icon: "person.2.fill", tint: .purple, title: "Friends see my bets") { EmptyView() }
        }
        .disabled(busy)
        .onAppear { on = store.shareBets }
        .onChange(of: store.shareBets) { _, v in on = v }
        if let msg { Text(msg).foregroundStyle(.red) }
    }
}

/// Me > Settings: who you are, then a row per setting with a screen of its own.
struct SettingsView: View {
    @AppStorage(AppLock.key) private var appLock = false
    @EnvironmentObject private var store: BetStore
    @EnvironmentObject private var auth: AuthStore

    var body: some View {
        // reorganized Nov 6 (Mike: "it's pretty ah rn"): who you are, then short rows like the iPhone's own Settings, each
        // with what it's set to and a screen of its own (web app/more/settings)
        let on = store.myBooks
        let n = store.notify
        let sends = [n["picks"]?.bool != false ? "Picks" : nil, n["leans"]?.bool == true ? "leans" : nil,
                     n["locks"]?.bool != false ? "locks" : nil, n["legs"]?.bool != false ? "legs" : nil].compactMap { $0 }
        Form { Group {
            Section {
                HStack(spacing: 14) {
                    Image(systemName: "person.crop.circle.fill").font(.system(size: 48)).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Your account").font(.headline)
                        Text(auth.session?.email ?? "Signed in").font(.footnote).foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 4)
            }
            Section("Betting") {
                NavigationLink { BooksScreen() } label: {
                    SettingRow(icon: "ticket.fill", tint: .blue, title: "Your books") {
                        HStack(spacing: -6) { ForEach(on, id: \.self) { BookIcon(book: $0, size: 22) } }
                    }
                }
                NavigationLink { MoneyScreen() } label: {
                    SettingRow(icon: "dollarsign", tint: .green, title: "Units and money") { Text("$\(Live.js(store.unit)) a unit") }
                }
                NavigationLink { BanListView() } label: {
                    SettingRow(icon: "nosign", tint: .red, title: "Ban list") { Text(store.bans.isEmpty ? "Nobody" : "\(store.bans.count)") }
                }
            }
            Section("Alerts") {
                NavigationLink { AlertsScreen() } label: {
                    SettingRow(icon: "bell.fill", tint: .orange, title: "Notifications") {
                        Text(n["quiet"]?.object.isEmpty == false ? "Quiet hours" : sends.isEmpty ? "Off" : sends.joined(separator: ", "))
                    }
                }
            }
            Section("Friends and privacy") {
                ShareBetsRow()
                NavigationLink { DevicesView() } label: { SettingRow(icon: "iphone", tint: .gray, title: "Signed-in devices") { EmptyView() } }
                Toggle(isOn: $appLock) { SettingRow(icon: "faceid", tint: .indigo, title: "Lock with Face ID") { EmptyView() } }
            }
            Section("Look") {
                NavigationLink { LookScreen() } label: {
                    SettingRow(icon: "paintpalette.fill", tint: .pink, title: "Theme and icon") { EmptyView() }
                }
            }
            Section { Button("Sign out", role: .destructive) { auth.signOut() }.frame(maxWidth: .infinity) }
        }.themedRows() }.themedList()
        .navigationTitle("Settings")
    }
}

/// A Settings row: a colored square with a white symbol, the title, and what it's set to (the iPhone's own Settings).
struct SettingRow<Value: View>: View {
    let icon: String
    let tint: Color
    let title: String
    @ViewBuilder let value: () -> Value

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon).font(.system(size: 15, weight: .semibold)).foregroundStyle(.white)
                .frame(width: 30, height: 30).background(tint, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            Text(title)
            Spacer(minLength: 8)
            value().foregroundStyle(.secondary).lineLimit(1)
        }
    }
}

/// Sports as chips that wrap (Settings > Notifications).
struct SportChips: View {
    let on: (String) -> Bool
    let sports: [(String, String)]
    let tap: (String) -> Void

    var body: some View {
        FlowRow(spacing: 8) {
            ForEach(sports, id: \.0) { key, title in
                let isOn = on(key)
                Button { tap(key) } label: {
                    Text(title).font(.subheadline.weight(.semibold)).padding(.horizontal, 14).frame(height: 36)
                        .foregroundStyle(isOn ? Color.primary : Color.secondary)
                        .background(isOn ? Color.green.opacity(0.16) : Color(.tertiarySystemFill), in: Capsule())
                        .overlay { if isOn { Capsule().strokeBorder(Color.green, lineWidth: 1.5) } }
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(isOn ? .isSelected : [])
            }
        }
        .padding(.vertical, 4)
    }
}

/// A row of views that wraps onto the next line.
struct FlowRow: Layout {
    var spacing: CGFloat = 8
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let w = proposal.width ?? 320
        var x: CGFloat = 0, y: CGFloat = 0, line: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > 0 && x + s.width > w { x = 0; y += line + spacing; line = 0 }
            x += s.width + spacing; line = max(line, s.height)
        }
        return CGSize(width: w, height: y + line)
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, line: CGFloat = 0
        for v in subviews {
            let s = v.sizeThatFits(.unspecified)
            if x > bounds.minX && x + s.width > bounds.maxX { x = bounds.minX; y += line + spacing; line = 0 }
            v.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(s))
            x += s.width + spacing; line = max(line, s.height)
        }
    }
}

/// Settings > Your books.
struct BooksScreen: View {
    var body: some View { Form { BooksSection() }.themedList().navigationTitle("Your books") }
}

/// Settings > Notifications: this iPhone's push, then what to send and when.
struct AlertsScreen: View {
    var body: some View {
        Form { Group {
            Section("This iPhone") { PushRows() }
            AlertSettingsRows()
        }.themedRows() }.themedList().navigationTitle("Notifications")
    }
}

/// Settings > Theme and icon (kept on this phone).
struct LookScreen: View {
    @AppStorage("appearance") private var appearance = "system"
    var body: some View {
        Form { Group {
            Section { ThemePicker(selection: $appearance) } header: { Text("Theme") } footer: { Text("Device follows your phone's light or dark mode.") }
            Section("App icon") { AppIconRow() }
        }.themedRows() }.themedList().navigationTitle("Theme and icon")
    }
}

/// Settings > Units and money: the unit's dollars, parlay units a month, the real-money date.
struct MoneyScreen: View {
    @EnvironmentObject private var store: BetStore
    @State private var fun = ""
    @State private var unitText = ""
    @State private var useDate = false
    @State private var realFrom = Date()
    @State private var msg: String?
    @State private var busy = false

    private static let et: Calendar = { var c = Calendar(identifier: .gregorian); c.timeZone = Fmt.et; return c }()

    var body: some View {
        let f = Double(fun.trimmingCharacters(in: .whitespaces))
        let valid = f != nil && f! >= 0 && f! <= 1000
        Form { Group {
            Section {
                LabeledContent("One unit is") {
                    TextField("5", text: $unitText).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(maxWidth: 80)
                }
                LabeledContent("Parlays a month") {
                    TextField("10", text: $fun).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(maxWidth: 80)
                }
            } header: { Text("Units") } footer: {
                Text("A unit is your standard bet, in dollars; everything counts in units, 5u a day at most. Keep it the same size for a month at a time, never bigger after a win or a loss.")
            }
            Section {
                Toggle("My own real-money date", isOn: $useDate)
                if useDate { DatePicker("Real money from", selection: $realFrom, displayedComponents: .date) }
            } header: { Text("Real money") } footer: {
                Text("From this date, I placed this records a real bet (1 unit at the price shown, both editable); before it, bets are paper. Off means Oct 18. You must be 21 to bet in New York.")
            }
            Section {
                Button(busy ? "Saving…" : "Save") { save(f ?? 0) }.disabled(busy || !valid)
                if let msg { Text(msg).foregroundStyle(msg == "Saved" ? .green : .red) }
            }
        }.themedRows() }.themedList()
        .navigationTitle("Units and money")
        .onAppear {
            fun = String(format: "%g", store.funBucket)
            unitText = String(format: "%g", store.unit)
            if let r = store.realFrom, let d = Models.date(r) { useDate = true; realFrom = d }
        }
    }

    private func save(_ units: Double) {
        busy = true
        // just after midnight Eastern on the chosen day (05:00 UTC is after midnight in summer and winter time)
        let day = Self.et.dateComponents([.year, .month, .day], from: realFrom)
        let iso = useDate ? String(format: "%04d-%02d-%02dT05:00:00Z", day.year!, day.month!, day.day!) : nil
        Task {
            do {
                try await store.api.upsert("user_settings", ["fun_bucket_monthly": units, "book": store.book, "real_from": iso,
                                                             "updated_at": ISO8601DateFormatter().string(from: Date())], onConflict: "user_id")
                if let u = Double(unitText), u != store.unitDollars, let e = await store.setUnitDollars(u) { msg = e; busy = false; return }
                await store.load()
                msg = "Saved"
            } catch { msg = (error as? AuthError)?.message ?? "Couldn't save that." }
            busy = false
        }
    }
}
