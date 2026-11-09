import PhotosUI
import SwiftUI

// Me > Promos, the wallet (web app/more/promos, components/promos/PromoWallet.tsx; rules in Promos.swift): the bonus bets
// and profit boosts you hold as tokens, soonest to end first. What they are worth leads; Add a promo (typed, or read
// off a screenshot of the book's promos screen by the web's /api/promos) is a button, not an open form; Use it opens
// the finder with that token, and the bet you place with it marks it used. Used and expired fold at the bottom.

struct PromosView: View {
    @EnvironmentObject private var store: BetStore
    @EnvironmentObject private var auth: AuthStore
    @Environment(\.theme) private var theme
    @State private var rows: [PromoRow] = []
    @State private var editing: PromoRow?
    @State private var drafts: [PromoRow] = []
    @State private var picks: [PhotosPickerItem] = []
    @State private var picking = false
    @State private var busy = false
    @State private var msg: String?
    @State private var using: PromoRow?         // I used it: which bet the token went on

    var body: some View {
        let now = Date()
        let w = Promos.wallet(rows, now: now)
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                hero(w.open, now: now)
                if !drafts.isEmpty {
                    SectionTitle("Found on the screenshot", note: "\(drafts.count) to check").padding(.top, 6)
                    ForEach(drafts) { d in
                        TokenCard(p: d, now: now) {
                            VStack(alignment: .leading, spacing: 8) {
                                if let pr = d.problem { Text("\(pr) Fix it first.").font(.footnote).foregroundStyle(.orange) }
                                HStack(spacing: 8) {
                                    if d.problem == nil {
                                        Button { Task { await keep(d) } } label: { Text("Keep it").frame(maxWidth: .infinity) }
                                            .buttonStyle(SolidButton()).disabled(busy)
                                        Button("Fix first") { editing = d; drafts.removeAll { $0.promoId == d.promoId } }.buttonStyle(SoftButton())
                                    } else {
                                        Button { editing = d; drafts.removeAll { $0.promoId == d.promoId } } label: { Text("Fix it").frame(maxWidth: .infinity) }
                                            .buttonStyle(SolidButton())
                                    }
                                    Button("Skip") { drafts.removeAll { $0.promoId == d.promoId } }.buttonStyle(SoftButton())
                                }
                            }
                        }
                    }
                }
                if !w.open.isEmpty {
                    SectionTitle("Waiting", note: drafts.isEmpty ? nil : "\(w.open.count)").padding(.top, 6)
                    ForEach(w.open) { p in
                        TokenCard(p: p, now: now) { actions(p) }
                    }
                }
                if !w.done.isEmpty {
                    FoldCard(title: "Used and expired", note: "\(w.done.count)") {
                        VStack(spacing: 0) {
                            ForEach(Array(w.done.enumerated()), id: \.element.id) { i, p in
                                if i > 0 { Hairline() }
                                doneRow(p, now: now)
                            }
                        }
                    }
                    .padding(.top, 6)
                }
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 28)
        }
        .background(theme.pageColor.ignoresSafeArea())
        .navigationTitle("Promos")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: store.refreshTick) { await load() }
        .refreshable { await load() }
        .photosPicker(isPresented: $picking, selection: $picks, maxSelectionCount: Self.maxShots, matching: .images)
        .onChange(of: picks) { _, its in Task { await read(its) } }
        .sheet(item: $editing) { p in PromoEditView(start: p) { await load() } }
        .confirmationDialog("Which bet did it go on?", isPresented: Binding(get: { using != nil }, set: { if !$0 { using = nil } }),
                            titleVisibility: .visible, presenting: using) { p in
            ForEach(Promos.usedOnChoices(p, store.bets)) { b in
                Button(Self.betText(b)) { Task { await usedOn(p, b) } }
            }
            Button("A bet not in BetLab") { Task { await set(p, "used") } }
        } message: { p in
            Text(Promos.usedOnChoices(p, store.bets).isEmpty ? "No bet\(p.book.map { " at \($0)" } ?? "") in the last week to tie it to." : "It takes the token, and its bonus or boost.")
        }
    }

    /// Up to 20 screenshots at once (Nov 9; web MAX_SHOTS, lib/promo-read.ts MAX_IMAGES): the server reads each on its own.
    static let maxShots = 20

    // MARK: what the wallet is worth

    private func hero(_ open: [PromoRow], now: Date) -> some View {
        let bonus = open.filter { $0.kind == "bonus" }.reduce(0) { $0 + ($1.amountDollars ?? 0) }
        let boosts = open.filter { $0.kind == "boost" }.count
        let day = BetMath.etDay(now)
        let today = open.filter { p in Promos.date(p.expiresAt).map { BetMath.etDay($0) == day } ?? false }.count
        let n = open.count
        return VStack(alignment: .leading, spacing: 6) {
            if open.isEmpty {
                Text("No promos waiting").font(.title2.weight(.heavy))
                Text("Add the bonus bets and boosts your books give you, and BetLab finds the best bet for each.")
                    .font(.footnote).foregroundStyle(.secondary)
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    HeroNumber(text: bonus > 0 ? Promos.dollars(bonus) : "\(n)", size: 56)
                    Text(bonus > 0 ? "in bonus bets" : "waiting").font(.headline).foregroundStyle(.secondary)
                }
                .accessibilityElement(children: .combine)
                let line = [bonus > 0 ? "\(n) waiting" : "", boosts > 0 ? "\(boosts) profit boost\(boosts == 1 ? "" : "s")" : ""].filter { !$0.isEmpty }
                HStack(spacing: 6) {
                    if !line.isEmpty { Text(line.joined(separator: " · ")).foregroundStyle(.secondary) }
                    if today > 0 {
                        if !line.isEmpty { Text("·").foregroundStyle(.secondary) }
                        Text("\(today) end\(today == 1 ? "s" : "") today").fontWeight(.semibold).foregroundStyle(.orange)
                    }
                }
                .font(.footnote)
            }
            // Nov 9 (Mike: "it needs to be easier to enter promos with a screenshot"): the screenshot leads, typing is second
            HStack(spacing: 8) {
                Button { picking = true } label: {
                    HStack(spacing: 6) {
                        if busy { ProgressView().controlSize(.small) } else { Image(systemName: "camera.viewfinder") }
                        Text(busy ? "Reading…" : "From a screenshot")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(SolidButton()).disabled(busy)
                Button { editing = PromoRow() } label: { Label("Type one", systemImage: "plus") }
                    .buttonStyle(SoftButton())
            }
            .padding(.top, 8)
            if busy {
                Text("Reading your screenshots: this takes up to a minute.").font(.footnote).foregroundStyle(.secondary).padding(.top, 2)
            } else if let msg {
                Text(msg).font(.footnote).foregroundStyle(.secondary).padding(.top, 2)
            } else if drafts.isEmpty {
                Text("A picture of the book's promos or bonus bets screen: BetLab reads every one on it, and you check each before it's kept.")
                    .font(.footnote).foregroundStyle(.secondary).padding(.top, 2)
            }
        }
    }

    // MARK: a token's actions

    private func actions(_ p: PromoRow) -> some View {
        HStack(spacing: 8) {
            NavigationLink { PromoFinderView(promoId: p.promoId) } label: { Text("Use it").frame(maxWidth: .infinity) }
                .buttonStyle(SolidButton())
            Button("I used it") { using = p }.buttonStyle(SoftButton())
            Button("Edit") { editing = p }.buttonStyle(SoftButton())
            Menu {
                Button("Won't use") { Task { await set(p, "void") } }
            } label: {
                Image(systemName: "ellipsis").font(.subheadline.weight(.bold)).foregroundStyle(.secondary)
                    .frame(width: 34, height: 46).contentShape(Rectangle())
            }
            .accessibilityLabel("More for this promo")
        }
    }

    /// A used, expired or set-aside token, small: what it was, what became of it, and what can still be done.
    private func doneRow(_ p: PromoRow, now: Date) -> some View {
        let st = Promos.state(p, now: now)
        let back = st == "void" || (st == "used" && !store.bets.contains(where: { $0.promoId == p.promoId }))
        return HStack(spacing: 10) {
            BookIcon(book: p.book, size: 24).grayscale(0.6).opacity(0.8)
            Text(Promos.title(p)).font(.subheadline.weight(.semibold)).lineLimit(1)
            Spacer(minLength: 6)
            Text(st == "used" ? "used" : st == "void" ? "not used" : Promos.expires(p, now: now)).font(.caption).foregroundStyle(.secondary)
            if back || st != "used" {
                Menu {
                    if back { Button("Bring back") { Task { await set(p, "open", from: st == "used" ? "used" : nil) } } }
                    if st != "used" { Button("Remove", role: .destructive) { Task { await remove(p) } } }
                } label: {
                    Image(systemName: "ellipsis").font(.footnote.weight(.bold)).foregroundStyle(.tertiary)
                        .frame(width: 30, height: 30).contentShape(Rectangle())
                }
                .accessibilityLabel("More for this promo")
            }
        }
        .padding(.vertical, 9)
    }

    // MARK: reads and writes (unchanged by the new look)

    private func load() async {
        rows = (try? await store.api.rows("promos", .init(order: ("created_at", ascending: false)))) ?? rows
    }

    private func set(_ p: PromoRow, _ status: String, from: String? = nil) async {
        do { try await store.api.update("promos", eq: [("promo_id", p.promoId)] + (from.map { [("status", $0)] } ?? []), ["status": status]); await load() }
        catch { msg = "Couldn't save that." }
    }

    private static func betText(_ b: MyBet) -> String {
        let parts: [String] = [b.label ?? b.matchup ?? "A bet", b.price == nil ? "" : Fmt.am(b.price), Marking.units(b.stake), b.book ?? ""]
        return parts.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    /// The token went on a bet saved without it (web usedPromo): the bet takes it and its bonus or boost; the database
    /// marks it used.
    private func usedOn(_ p: PromoRow, _ b: MyBet) async {
        let change: [String: Any?] = p.kind == "bonus" ? ["promo_id": p.promoId, "bonus": true]
            : ["promo_id": p.promoId, "boost": p.pct, "boost_cap": (p.maxExtraDollars ?? 0) > 0 ? ((p.maxExtraDollars! / store.unit) * 1000).rounded() / 1000 : nil]
        // the token must still be open (Nov 9), and a bonus used for less than its face splits
        let undo: () async -> Void
        switch await store.claimToken(p.promoId, wager: b.stake.map { ($0 * store.unit * 100).rounded() / 100 }, overMax: true) {
        case .failure(let e): msg = e.message; await load(); return
        case .success(let u): undo = u
        }
        do { try await store.api.update("bets", eq: [("bet_id", b.betId)], change); await store.load(); await load() }
        catch { await undo(); msg = "Couldn't save that." }
    }

    /// Keep a draft as read (web saveDraft): cleaned as the web cleans it, then saved; one that can't be opens to fix.
    private func keep(_ d: PromoRow) async {
        let c = Promos.clean(d)
        guard var row = c.row else { msg = c.error; editing = d; drafts.removeAll { $0.promoId == d.promoId }; return }
        row.source = "screenshot"
        do {
            try await store.api.insert("promos", row.row)
            drafts.removeAll { $0.promoId == d.promoId }
            msg = nil
            await load()
        } catch { msg = (error as? AuthError)?.message ?? "Couldn't save that." }
    }

    private func remove(_ p: PromoRow) async {
        do { try await store.api.delete("promos", eq: [("promo_id", p.promoId)]); await load() }
        catch { msg = "Couldn't remove that." }
    }

    private func read(_ its: [PhotosPickerItem]) async {
        guard !its.isEmpty else { return }
        busy = true; msg = nil
        defer { busy = false; picks = [] }
        var images: [String] = []
        for it in its {
            if let d = try? await it.loadTransferable(type: Data.self), let s = Slip.shrink(d) { images.append(s) }
        }
        guard !images.isEmpty else { msg = "Those aren't images this phone can open."; return }
        do {
            var req = URLRequest(url: Config.webURL.appendingPathComponent("api/promos"))
            // the server reads each screenshot (45 s and one retry, 6 at once: web lib/promo-read.ts), with room for the upload
            req.httpMethod = "POST"; req.timeoutInterval = 200
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue("Bearer \(try await auth.accessToken())", forHTTPHeaderField: "Authorization")
            req.httpBody = try JSONSerialization.data(withJSONObject: ["images": images])
            let (data, resp) = try await URLSession.shared.data(for: req)
            let http = resp as? HTTPURLResponse
            struct Answer: Decodable { let promos: [PromoRow]?; let error: String?; let read: Int?; let failed: Int? }
            let a = try? Models.decoder.decode(Answer.self, from: data)
            if http?.statusCode == 200, let found = a?.promos {
                drafts = found.enumerated().map { i, p in var p = p; p.promoId = "draft-\(i)-\(UUID().uuidString.prefix(4))"; p.source = "screenshot"; return p }
                msg = found.isEmpty ? "No bonus bets or boosts found on those screenshots."
                    : Self.failedText(read: a?.read, failed: a?.failed) ?? "Found \(found.count): check \(found.count == 1 ? "it" : "each") and save."
            } else {
                msg = Self.readError(status: http?.statusCode, said: a?.error, html: http?.value(forHTTPHeaderField: "Content-Type")?.contains("html") == true)
            }
        } catch {
            msg = Self.readError(error)
        }
    }

    /// Some screenshots didn't read (Nov 9; web PromoWallet read): how many, so they can go again. Nil when all did.
    static func failedText(read: Int?, failed: Int?) -> String? {
        guard let failed, failed > 0, let read else { return nil }
        return "Read \(read - failed) of \(read) screenshots: send the other \(failed == 1 ? "one" : String(failed)) again."
    }

    /// Why a read failed, in words (Nov 9: a timeout said "You look offline", and the login page's HTML "Couldn't read").
    static func readError(status: Int?, said: String?, html: Bool) -> String {
        if let said, !said.isEmpty { return said }
        if html || status == 401 { return "Sign in again, then try once more." }
        if status == 504 { return "Reading took too long: try again in a moment." }
        return "Couldn't read those screenshots (\(status.map(String.init) ?? "no answer")): try again."
    }
    static func readError(_ error: Error) -> String {
        if let u = error as? URLError {
            if u.code == .timedOut { return "Reading took too long: try again in a moment." }
            if SupabaseClient.isOffline(u) { return "You look offline: try again." }
        }
        return (error as? AuthError)?.message ?? "Couldn't read those screenshots: try again."
    }
}

/// Add or edit a token (web PromoForm in PromoWallet.tsx): what it is first, then its limits, then when it ends.
struct PromoEditView: View {
    @EnvironmentObject private var store: BetStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.theme) private var theme
    @State var p: PromoRow
    let saved: () async -> Void
    @State private var hasExpiry: Bool
    @State private var expiry: Date
    @State private var err: String?
    @State private var busy = false
    @State private var teamsText: String
    @State private var schedule: [ScheduleGame] = []

    init(start: PromoRow, saved: @escaping () async -> Void) {
        _teamsText = State(initialValue: (start.teams ?? []).joined(separator: ", "))
        var seeded = start; seeded.sports = Promos.sports(start)
        _p = State(initialValue: seeded)
        self.saved = saved
        let d = Promos.date(start.expiresAt)
        _hasExpiry = State(initialValue: d != nil)
        _expiry = State(initialValue: d ?? Calendar.current.date(byAdding: .day, value: 7, to: Date())!)
    }

    private func num(_ v: Binding<Double?>) -> Binding<String> {
        Binding(get: { v.wrappedValue.map { String(format: "%g", $0) } ?? "" },
                set: { v.wrappedValue = Double($0.replacingOccurrences(of: Fmt.minus, with: "-").filter { "0123456789.-+".contains($0) }) })
    }
    private var legs: Binding<String> {
        Binding(get: { p.minLegs.map(String.init) ?? "" }, set: { p.minLegs = Int($0) })
    }
    private var isNew: Bool { p.promoId.isEmpty || p.promoId.hasPrefix("draft-") }

    var body: some View {
        NavigationStack {
            Form { Group {
                Section {
                    Picker("Kind", selection: $p.kind) { Text("Bonus bet").tag("bonus"); Text("Profit boost").tag("boost") }.pickerStyle(.segmented)
                    HStack(spacing: 10) {
                        bookChoice(nil)
                        ForEach(Marking.books.filter { BooksOff.mine.contains($0) || $0 == p.book }, id: \.self) { bookChoice($0) }
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 2)
                    if p.kind == "boost" { field("Boost %", num($p.pct), "30") }
                    field(p.kind == "boost" ? "Max wager $" : "Bonus $", num($p.amountDollars), p.kind == "boost" ? "25" : "10")
                    if p.kind == "boost" { field("Max extra winnings $", num($p.maxExtraDollars), "none") }
                } header: { Text("The promo") } footer: { Text(p.book.map { "From \($0)." } ?? "From any book.") }
                Section {
                    ChipFlow(spacing: 8) {
                        ForEach(Promos.sportChoices, id: \.0) { k, label in
                            let on = p.sports?.contains(k) ?? false
                            Button {
                                var x = p.sports ?? []
                                if on { x.removeAll { $0 == k }; p.games?.removeAll { $0.sport == k } } else { x.append(k) }
                                p.sports = x.isEmpty ? nil : x
                            } label: {
                                HStack(spacing: 5) {
                                    LeagueMark(league: k, size: 15)
                                    Text(label).font(.subheadline.weight(.semibold))
                                }
                                .padding(.horizontal, 12).padding(.vertical, 7)
                                .background(on ? theme.accent.opacity(0.2) : Color(.tertiarySystemFill), in: Capsule())
                                .overlay(Capsule().strokeBorder(theme.accent, lineWidth: on ? 1.5 : 0))
                                .foregroundStyle(on ? theme.accent : Color.primary)
                            }
                            .buttonStyle(.borderless)
                            .accessibilityAddTraits(on ? .isSelected : [])
                        }
                    }
                    .padding(.vertical, 4)
                    if !(p.sports ?? []).isEmpty || !(p.games ?? []).isEmpty {
                        ForEach(p.games ?? [], id: \.eventId) { g in
                            HStack {
                                Text(g.matchup).lineLimit(1).minimumScaleFactor(0.8)
                                Spacer()
                                Button { p.games?.removeAll { $0.eventId == g.eventId } } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary) }
                                    .buttonStyle(.borderless)
                                    .accessibilityLabel("Remove \(g.matchup)")
                            }
                        }
                        Menu {
                            ForEach(gameDays, id: \.self) { day in
                                Section(day) {
                                    ForEach(gameChoices.filter { Promos.gameDay($0.start) == day }) { g in
                                        Button("\(g.matchup) · \(Promos.clock(g.start))") {
                                            p.games = (p.games ?? []) + [PromoGame(eventId: g.id, matchup: g.matchup, commenceTime: g.start, sport: g.sport)]
                                        }
                                    }
                                }
                            }
                        } label: {
                            LabeledContent("Games") {
                                Text(!(p.games ?? []).isEmpty ? "Add another" : gameChoices.isEmpty ? "No games this week" : "Any game · pick one")
                            }
                        }
                        .disabled(gameChoices.isEmpty)
                    }
                } header: { Text("Sport and games") } footer: { Text((p.sports ?? []).isEmpty ? "None picked: any sport." : "Pick a game only if the promo is for certain games.") }
                Section {
                    field("Min legs", legs, "1")
                    field("Min odds", num($p.minOdds), "-200")
                    field("Max odds", num($p.maxOdds), "none")
                    Picker("Bet type", selection: Binding(get: { p.market ?? "" }, set: { p.market = $0.isEmpty ? nil : $0 })) {
                        Text("Any bet").tag("")
                        ForEach(Build.marketChoices, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    .pickerStyle(.menu)
                    // a token for certain kinds of leg (Nov 9, web PromoForm's "Only these legs"): every leg must be one; none is any
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Only these legs").font(.subheadline)
                        ChipFlow(spacing: 8) {
                            ForEach(Promos.legChoices, id: \.0) { k, label in
                                let on = p.legKinds?.contains(k) ?? false
                                Button {
                                    var x = p.legKinds ?? []
                                    if on { x.removeAll { $0 == k } } else { x.append(k) }
                                    p.legKinds = x.isEmpty ? nil : x
                                } label: {
                                    Text(label).font(.subheadline.weight(.semibold))
                                        .padding(.horizontal, 12).padding(.vertical, 7)
                                        .background(on ? theme.accent.opacity(0.2) : Color(.tertiarySystemFill), in: Capsule())
                                        .overlay(Capsule().strokeBorder(theme.accent, lineWidth: on ? 1.5 : 0))
                                        .foregroundStyle(on ? theme.accent : Color.primary)
                                }
                                .buttonStyle(.borderless)
                                .accessibilityAddTraits(on ? .isSelected : [])
                            }
                        }
                    }
                    .padding(.vertical, 4)
                    TextField("Teams, for a game not posted yet", text: $teamsText)
                } header: { Text("Its limits") } footer: { Text((p.legKinds ?? []).isEmpty ? "No legs picked: any leg." : "Every leg of the bet must be one of these.") }
                Section {
                    Toggle("Expires", isOn: $hasExpiry)
                    if hasExpiry { DatePicker("On", selection: $expiry) }
                    TextField("Note (NFL only, SGP only…)", text: Binding(get: { p.note ?? "" }, set: { p.note = $0.isEmpty ? nil : $0 }))
                    if let err { Text(err).foregroundStyle(.red) }
                }
            }.themedRows() }
            .themedList()
            .task {
                let now = Date()
                let rows: [ScheduleGame] = (try? await store.api.rows("schedule_games", .init(from: ("start", now), to: ("start", now.addingTimeInterval(8 * 86400))))) ?? []
                schedule = rows.sorted { $0.start < $1.start }
            }
            .navigationTitle(isNew ? "Add a promo" : "Edit promo")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button(busy ? "Saving…" : "Save") { Task { await save() } }.disabled(busy) }
            }
        }
    }

    /// One book to pick, as its own picture; a ticket for any book.
    /// The schedule's games in the chosen sports, not yet picked, soonest first (Nov 5: sport first, then its games; the odds
    /// packs only know a game about an hour out).
    private var gameChoices: [ScheduleGame] {
        schedule.filter { g in (p.sports ?? []).contains(g.sport) && !(p.games ?? []).contains { $0.eventId == g.id } }
    }
    private var gameDays: [String] { gameChoices.reduce(into: [String]()) { let d = Promos.gameDay($1.start); if !$0.contains(d) { $0.append(d) } } }

    private func bookChoice(_ b: String?) -> some View {
        let on = p.book == b
        return Button { p.book = b } label: {
            BookIcon(book: b, size: 38)
                .padding(4)
                .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous).strokeBorder(theme.accent, lineWidth: on ? 2 : 0))
                .opacity(on ? 1 : 0.55)
        }
        .buttonStyle(.borderless)
        .accessibilityLabel(b ?? "Any book")
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func field(_ label: String, _ text: Binding<String>, _ ph: String) -> some View {
        LabeledContent(label) { TextField(ph, text: text).keyboardType(.numbersAndPunctuation).multilineTextAlignment(.trailing).frame(maxWidth: 110) }
    }

    private func save() async {
        p.expiresAt = hasExpiry ? ISO8601DateFormatter().string(from: expiry) : nil
        p.teams = Promos.splitTeams([teamsText])
        // web cleanPromo (Nov 9): a 0 cap or legs outside 1 to 20 went to the database, which refused them as "Couldn't save that."
        let c = Promos.clean(p)
        guard let row = c.row else { err = c.error; return }
        p = row
        busy = true
        defer { busy = false }
        do {
            if isNew { try await store.api.insert("promos", row.row) }
            else {
                var change = row.row; change.removeValue(forKey: "source")
                try await store.api.update("promos", eq: [("promo_id", p.promoId)], change)
            }
            await saved()
            dismiss()
        } catch { err = (error as? AuthError)?.message ?? "Couldn't save that." }
    }
}
