import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

// + Add a bet from a screenshot (Mike, Oct 24): pick a sportsbook slip, the web's /api/slip reads it (Claude Haiku 5.5)
// and matches each leg to the app's games, you check the draft, and it's saved as a real bet that tracks, alerts and
// grades like the rest. The image is shrunk on the phone (a screenshot is several MB) and never stored. The saved row is
// web/lib/slip.ts betRow, ported (`Slip.row`). **Change both together.** Several at once (Mike, Oct 25: "multiple pics
// in case it doesn't fit on one screen or multiple bets at once", and "add from clipboard"): up to 6 photos or pastes;
// one slip across screens comes back as one bet, different bets one each, and you check and save them in turn. A draft
// whose odds sit well above its legs' own prices multiplied is flagged before saving (Oct 27: four misread slips paid
// 2-4.6x that, impossible): /api/slip attaches each leg's prices, `Slip.priceCheck` is web lib/slip.ts priceCheck.

/// What /api/slip answers: the slip read and matched (web lib/slip.ts Draft).
struct SlipDraft: Codable, Equatable {
    struct Leg: Codable, Equatable {
        var label: String; var matchup: String; var sport: String; var game_ref: String?; var start: String?; var matched: Bool
        var prices: [String: Double]? = nil     // the leg's own price at FanDuel / DraftKings, from its game's Build pack
    }
    var book: String
    var price: Double
    var boost_pct: Double?
    var stake_dollars: Double
    var bonus: Bool
    var protect: Bool? = nil       // FanDuel Bet Protect+ (web SlipRead.protect, Oct 26)
    var reset: Bool? = nil         // a bet reset token (web SlipRead.reset, Nov 1)
    var placed_at: String?
    var legs: [Leg]
    var fair: SlipFair? = nil      // what its legs are worth (web SlipFair, Nov 4); an edited leg drops it (Slip.fairOf)
    /// The slip's day's games, for a leg the reader couldn't match (web GameChoice, Nov 9): only sent when one is unmatched.
    var choices: [Choice]? = nil
    struct Choice: Codable, Equatable, Hashable { var matchup: String; var sport: String; var game_ref: String?; var start: String; var event_id: String? }
}

struct SlipFair: Codable, Equatable { var p: Double?; var labels: [String]; var missing: [String] }

enum Slip {
    static let maxSide: CGFloat = 1600

    /// The draft's fair chance, if its legs are still the ones it was worked out on (web fairOf).
    static func fairOf(_ d: SlipDraft) -> Double? {
        guard let f = d.fair, let p = f.p, d.legs.map(\.label) == f.labels else { return nil }
        return p
    }

    enum Verdict: String { case plus, even, minus }
    /// What a slip is worth per dollar at its price: a boost pays extra on the profit; a bonus bet's stake isn't yours (web slipEv).
    static func ev(p: Double, price: Double, boost: Double?, bonus: Bool) -> (ev: Double, fair: Double, verdict: Verdict) {
        let dec = price > 0 ? 1 + price / 100 : 1 + 100 / -price
        let profit = (dec - 1) * (1 + (boost ?? 0) / 100)
        let ev = bonus ? p * profit : p * (profit + 1) - 1
        let d = 1 / p
        let fair = (d >= 2 ? (d - 1) * 100 : -100 / (d - 1)).rounded()
        return (ev, fair, ev > 0.01 ? .plus : ev < -0.01 ? .minus : .even)
    }

    /// A leg put on the game the user chose (web chooseGame): its matchup, sport, start and ref; its old prices were for no game.
    static func choose(_ leg: SlipDraft.Leg, _ c: SlipDraft.Choice) -> SlipDraft.Leg {
        var l = leg
        l.matchup = c.matchup; l.sport = c.sport; l.game_ref = c.game_ref; l.start = c.start; l.matched = true; l.prices = nil
        return l
    }

    /// A picked image as a JPEG data URL, at most 1600px on its long side.
    static func shrink(_ data: Data) -> String? {
        guard let img = UIImage(data: data) else { return nil }
        let k = min(1, maxSide / max(img.size.width, img.size.height))
        let size = CGSize(width: (img.size.width * k).rounded(), height: (img.size.height * k).rounded())
        let fmt = UIGraphicsImageRendererFormat(); fmt.scale = 1
        let out = UIGraphicsImageRenderer(size: size, format: fmt).image { _ in img.draw(in: CGRect(origin: .zero, size: size)) }
        return out.jpegData(compressionQuality: 0.85).map { "data:image/jpeg;base64," + $0.base64EncodedString() }
    }

    /// The bets row for a confirmed draft (kind custom, like the bets Claude enters by hand): units from the unit size,
    /// the label in the usual words, the games with their refs (web betRow).
    static func row(_ d: SlipDraft, unitDollars: Double, placedAt: String, id: String) -> [String: Any?] {
        let units = (d.stake_dollars / unitDollars * 1000).rounded() / 1000
        let js = Live.js
        // the boosted price: the profit grows, and an odds-on price can stay odds-on (-200 with 30% is -154; Nov 9)
        let boosted = d.boost_pct.flatMap { b -> Double? in
            guard b != 0 else { return nil }
            return Odds.am(1 + (Odds.dec(d.price) - 1) * (1 + b / 100)).rounded()
        }
        let money = d.bonus ? "Bonus bet $\(js(d.stake_dollars))" : "$\(js(d.stake_dollars)) cash"
        let label = boosted != nil ? "\(money), \(js(d.boost_pct!))% profit boost (\(d.price > 0 ? "+" : "")\(js(d.price)) -> \(boosted! > 0 ? "+" : "")\(js(boosted!)))" : money
        var order: [String] = [], byGame: [String: [String: Any]] = [:]
        for l in d.legs {
            let k = l.game_ref ?? l.matchup
            if byGame[k] == nil {
                order.append(k)
                // the sport too: a game with no ref (college or NHL on the Odds API's id) grades by it (Nov 9)
                var g: [String: Any] = ["matchup": l.matchup, "sport": l.sport, "legs": [String]()]
                if let r = l.game_ref { g["game_ref"] = r }
                byGame[k] = g
            }
            byGame[k]!["legs"] = (byGame[k]!["legs"] as! [String]) + [l.label]
        }
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US"); f.timeZone = Fmt.et; f.dateFormat = "EEE, MMM d"
        let day = Models.date(placedAt).map(f.string) ?? ""
        let tag = d.book == "DraftKings" ? "dk" : d.book == "Novig" ? "nv" : "fd"
        return ["kind": "custom", "sgp_id": "custom-\(tag)-snap-\(id)", "mode": "real", "price": d.price, "stake": units,
                "book": d.book == "Other" ? "FanDuel" : d.book, "label": label,
                "matchup": d.legs.count == 1 ? d.legs[0].matchup : "Parlay \(day) · \(d.legs.count) legs",
                "legs": d.legs.map(\.label), "games": order.map { byGame[$0]! }, "placed_at": placedAt, "bonus": d.bonus, "protect": d.protect == true, "reset": d.reset == true,
                "boost": d.boost_pct.flatMap { $0 != 0 ? $0 : nil }]
    }

    /// How far a read price can sit above the legs' own prices multiplied. A parlay pays at most about that product
    /// (Oct 25-26: cross-game slips 1.00-1.04x of it, same-game ones 0.6-0.9x); four misread slips came in at 2-4.6x.
    static let priceCheckRatio = 1.5
    struct PriceCheck: Equatable { let legsPrice: Double; let ratio: Double; let flag: Bool }
    /// The slip's price against its legs' own prices at its book, multiplied; nil unless every leg has one there.
    static func priceCheck(_ legs: [SlipDraft.Leg], book: String, price: Double?) -> PriceCheck? {
        guard book == "FanDuel" || book == "DraftKings", let price, !legs.isEmpty else { return nil }
        var dec = 1.0
        for l in legs {
            guard let p = l.prices?[book] else { return nil }
            dec *= Odds.dec(p)
        }
        let ratio = Odds.dec(price) / dec
        return PriceCheck(legsPrice: Odds.am(dec).rounded(), ratio: ratio, flag: ratio > priceCheckRatio)
    }

    /// "2026-10-24T13:06:00" (Eastern wall time) as an instant, "2026-10-24T17:06:00.000Z" (web easternIso).
    static func easternIso(_ local: String?, now: Date = Date()) -> String {
        let out = ISO8601DateFormatter(); out.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = Fmt.et; f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        guard let local, let d = f.date(from: local) else { return out.string(from: now) }
        return out.string(from: d)
    }
}

/// The screen: pick or paste, read, check, save each (web components/build/SlipUpload.tsx).
struct SlipAddView: View {
    @EnvironmentObject private var store: BetStore
    @EnvironmentObject private var auth: AuthStore
    @Environment(\.dismiss) private var dismiss
    @AppStorage("betlab-unit-dollars") private var unit = "5"   // seeded from the account's unit (store.unit) on appear
    @State private var items: [PhotosPickerItem] = []
    @State private var images: [String] = []
    @State private var previews: [UIImage] = []
    @State private var queue: [(draft: SlipDraft, placed: String?)] = []   // the bets read, the first on screen
    @State private var total = 0
    @State private var draft: SlipDraft?
    @State private var priceText = ""
    @State private var wager = ""
    @State private var boost = ""
    @State private var placed = Date()
    @State private var busy = false
    @State private var error: String?
    @State private var waiting = false
    @State private var tokens: [PromoRow] = []      // the wallet's open tokens, for a bonus or boosted slip (Nov 9)
    @State private var tokenId: String?             // the one picked; until touched, the only one that fits
    @State private var tokenTouched = false
    private static let maxImages = 6

    /// The wallet tokens this draft may have used (web slipTokens), and the one it's saved with.
    private func draftTokens(_ d: SlipDraft) -> (fits: [PromoRow], chosen: String?) {
        let fits = Promos.slipTokens(book: d.book, bonus: d.bonus, boost: Double(boost.replacingOccurrences(of: "%", with: "")),
                                     stake: Double(wager) ?? d.stake_dollars, price: Marking.parseOdds(priceText), legs: d.legs.count, tokens)
        let chosen = tokenTouched ? fits.first { $0.promoId == tokenId }?.promoId : (fits.count == 1 ? fits[0].promoId : nil)
        return (fits, chosen)
    }

    var body: some View {
        NavigationStack {
            Form { Group {
                if waiting {
                    Text("Reading slips is waiting for its key: add ANTHROPIC_API_KEY to the web service in Railway.").font(.footnote)
                }
                if draft == nil {
                    Section {
                        if !previews.isEmpty {
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 8) {
                                    ForEach(Array(previews.enumerated()), id: \.offset) { i, img in
                                        Image(uiImage: img).resizable().scaledToFill().frame(width: 90, height: 150)
                                            .clipShape(RoundedRectangle(cornerRadius: 10))
                                            .overlay(alignment: .topTrailing) {
                                                Button { previews.remove(at: i); images.remove(at: i) } label: {
                                                    Image(systemName: "xmark.circle.fill").font(.title3).symbolRenderingMode(.palette)
                                                        .foregroundStyle(.white, .black.opacity(0.55))
                                                }
                                                .buttonStyle(.plain).padding(4).accessibilityLabel("Remove screenshot \(i + 1)")
                                            }
                                    }
                                }
                            }
                        }
                        if images.count < Self.maxImages {
                            PhotosPicker(selection: $items, maxSelectionCount: Self.maxImages - images.count, matching: .images) {
                                Label(images.isEmpty ? "Choose screenshots of your slips" : "Add another screenshot", systemImage: "photo.on.rectangle")
                                    .frame(maxWidth: .infinity, minHeight: images.isEmpty ? 60 : 36)
                            }
                            PasteButton(supportedContentTypes: [.image]) { providers in Task { await paste(providers) } }
                                .frame(maxWidth: .infinity)
                        }
                        if !images.isEmpty {
                            Button(busy ? "Reading…" : images.count > 1 ? "Read \(images.count) screenshots" : "Read slip") { Task { await read() } }
                                .disabled(busy).frame(maxWidth: .infinity)
                        }
                    } footer: {
                        Text("One slip across several screens comes back as one bet; different bets come back one each.")
                    }
                }
                if let e = error { Text(e).foregroundStyle(.red).font(.footnote) }
                if let d = draft { form(d) }
            }.themedRows() }.themedList()
            .navigationTitle(total > 1 && draft != nil ? "Bet \(total - queue.count) of \(total)" : "Add a bet")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                if draft != nil {
                    ToolbarItem(placement: .confirmationAction) { Button(busy ? "Saving…" : "Save") { Task { await save() } }.disabled(busy || draft?.legs.isEmpty != false) }
                }
            }
            .onChange(of: items) { _, its in Task { await load(its) } }
            .onAppear { if let u = store.unitDollars { unit = String(format: "%g", u) } }   // the account's unit (Oct 30)
            .task { tokens = Promos.wallet((try? await store.api.rows("promos")) ?? []).open }
        }
    }

    @ViewBuilder private func form(_ d: SlipDraft) -> some View {
        Section {
            Picker("Book", selection: Binding(get: { draft?.book ?? "FanDuel" }, set: { draft?.book = $0 })) {
                ForEach(["FanDuel", "DraftKings", "Novig"], id: \.self) { Text($0) }
            }
            field("Odds (before boost)", $priceText, "+978")
            field("Wager $", $wager, "5")
            field("Your unit $", $unit, "5")
            field("Profit boost %", $boost, "none")
            Toggle("Bonus bet", isOn: Binding(get: { draft?.bonus ?? false }, set: { draft?.bonus = $0 }))
            Toggle("Bet Protect+", isOn: Binding(get: { draft?.protect ?? false }, set: { draft?.protect = $0 }))
            Toggle("Bet reset", isOn: Binding(get: { draft?.reset ?? false }, set: { draft?.reset = $0 }))
            DatePicker("Placed (ET)", selection: $placed)
                .environment(\.timeZone, Fmt.et)
        } header: {
            Text("Check it against your slip")
        }
        let tk = draftTokens(d)
        if !tk.fits.isEmpty {
            Section {
                Picker("From your wallet", selection: Binding(get: { tk.chosen ?? "" }, set: { tokenId = $0.isEmpty ? nil : $0; tokenTouched = true })) {
                    Text(tk.fits.count == 1 ? "Not this one" : "Pick the token it used").tag("")
                    ForEach(tk.fits) { p in
                        Text([Promos.title(p), p.book ?? "", Promos.expires(p)].filter { !$0.isEmpty }.joined(separator: " · ")).tag(p.promoId)
                    }
                }
                .pickerStyle(.menu)
            } footer: {
                Text(tk.chosen != nil ? "Saved with this token: it leaves your wallet." : "None: the wallet keeps every token.")
            }
        }
        Section {
            ForEach(Array(d.legs.enumerated()), id: \.offset) { i, l in
                VStack(alignment: .leading, spacing: 3) {
                    TextField("Leg \(i + 1)", text: Binding(get: { draft?.legs[safe: i]?.label ?? "" },
                                                             set: { draft?.legs[i].label = $0; draft?.legs[i].prices = nil }))
                        .font(.subheadline.weight(.semibold))
                    Text(l.matched ? l.matchup + (l.game_ref == nil ? " · no grading ref" : "") : "\(l.matchup) · no game found: tracks by name")
                        .font(.caption).foregroundStyle(l.matched ? Color.secondary : Color.orange)
                    // no game found: pick it from the slip's day's games, so it tracks live and grades (Nov 9)
                    if !l.matched, let choices = d.choices, !choices.isEmpty {
                        Menu {
                            ForEach(choices, id: \.self) { c in
                                Button("\(c.sport.uppercased()) · \(c.matchup) · \(Fmt.dayTime(c.start))") {
                                    if let leg = draft?.legs[safe: i] { draft?.legs[i] = Slip.choose(leg, c) }
                                }
                            }
                        } label: { Label("Pick its game", systemImage: "sportscourt").font(.caption.weight(.semibold)) }
                    }
                }
                .swipeActions { Button("Remove", role: .destructive) { draft?.legs.remove(at: i) } }
            }
            slipValue(d)
            if let c = Slip.priceCheck(d.legs, book: d.book, price: Marking.parseOdds(priceText)), c.flag {
                Label("These odds don't fit these legs: at \(d.book) the \(d.legs.count == 1 ? "leg pays" : "\(d.legs.count) legs multiplied pay") \(Fmt.am(c.legsPrice)), and a parlay never pays much more than that (\(String(format: "%.1f", c.ratio))x here). Check the odds and each leg against your slip.",
                      systemImage: "exclamationmark.triangle.fill")
                    .font(.footnote).foregroundStyle(.orange)
            }
        } header: {
            Text("Legs · \(d.legs.count)")
        } footer: {
            Text("The wording is what the tracker and the grading read. Swipe a leg to remove it.")
        }
        if total > 1 {
            Section { Button("Skip this one", role: .destructive) { next() } }
        }
    }

    private func field(_ title: String, _ text: Binding<String>, _ hint: String) -> some View {
        LabeledContent(title) { TextField(hint, text: text).keyboardType(.numbersAndPunctuation).multilineTextAlignment(.trailing) }
    }

    private func load(_ its: [PhotosPickerItem]) async {
        guard !its.isEmpty else { return }
        error = nil
        for it in its {
            guard images.count < Self.maxImages, let data = try? await it.loadTransferable(type: Data.self) else { continue }
            add(data)
        }
        items = []
    }

    /// What's on the clipboard (PasteButton: no paste prompt), as screenshots.
    private func paste(_ providers: [NSItemProvider]) async {
        error = nil
        var got = 0
        for p in providers where images.count < Self.maxImages {
            let data: Data? = await withCheckedContinuation { c in
                _ = p.loadDataRepresentation(for: .image) { d, _ in c.resume(returning: d) }
            }
            if let data { add(data); got += 1 }
        }
        if got == 0 { error = "No image on the clipboard: copy a screenshot first." }
    }

    private func add(_ data: Data) {
        guard let s = Slip.shrink(data), let img = UIImage(data: data) else { error = "That isn't an image this phone can open."; return }
        images.append(s); previews.append(img)
    }

    private func read() async {
        guard !images.isEmpty else { return }
        busy = true; error = nil
        defer { busy = false }
        do {
            var req = URLRequest(url: Config.webURL.appendingPathComponent("api/slip"))
            req.httpMethod = "POST"; req.timeoutInterval = 95
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue("Bearer \(try await auth.accessToken())", forHTTPHeaderField: "Authorization")
            req.httpBody = try JSONSerialization.data(withJSONObject: ["images": images])
            let (data, resp) = try await URLSession.shared.data(for: req)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            struct One: Decodable { let draft: SlipDraft; let placed_at: String? }
            struct Answer: Decodable { let drafts: [One]?; let draft: SlipDraft?; let placed_at: String?; let error: String? }
            let a = try? JSONDecoder().decode(Answer.self, from: data)
            waiting = code == 503
            let all = a?.drafts?.map { ($0.draft, $0.placed_at) } ?? a?.draft.map { [($0, a?.placed_at)] } ?? []
            guard code == 200, !all.isEmpty else {
                error = a?.error ?? (code == 422 ? "Couldn't read that slip." : code == 401 ? "Sign in again." : "No answer came back: try again.")
                return
            }
            queue = all.map { (draft: $0.0, placed: $0.1) }
            total = all.count
            next()
        } catch {
            self.error = "You look offline: try again."
        }
    }

    /// The next bet read onto the screen, or done when there's none left.
    private func next() {
        guard !queue.isEmpty else { dismiss(); return }
        let (d, at) = queue.removeFirst()
        draft = d
        priceText = "\(d.price > 0 ? "+" : "")\(Live.js(d.price))"
        wager = Live.js(d.stake_dollars)
        boost = d.boost_pct.map(Live.js) ?? ""
        placed = Models.date(at) ?? Date()
        tokenId = nil; tokenTouched = false
        error = nil
    }

    /// Is this parlay +EV? The slip's fair price from its games' simulated draws, against what it pays with any boost or bonus (web
    /// SlipValueLine). Our market-anchored estimate, not a promise; it goes once a leg is edited.
    @ViewBuilder private func slipValue(_ d: SlipDraft) -> some View {
        let price = Marking.parseOdds(priceText)
        let b = Double(boost.replacingOccurrences(of: "%", with: "")).flatMap { $0 > 0 ? $0 : nil }
        if let p = Slip.fairOf(d), let price {
            let v = Slip.ev(p: p, price: price, boost: b, bonus: d.bonus)
            Section {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(v.verdict == .plus ? "+EV" : v.verdict == .minus ? "\u{2212}EV" : "About even").font(.headline)
                        Text("Fair \(Fmt.am(v.fair)), this pays \(Fmt.am(price))\(b.map { " with a \(Int($0))% boost" } ?? "")\(d.bonus ? " as a bonus bet" : "")").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(Fmt.signed(v.ev)).font(.headline.monospacedDigit()).foregroundStyle(v.verdict == .plus ? .green : v.verdict == .minus ? .red : .primary)
                }
            }
        } else if let m = d.fair?.missing, !m.isEmpty {
            Section { Text("No fair price: \(m.joined(separator: ", ")) \(m.count == 1 ? "isn't" : "aren't") in our prices (a game that's started is gone).").font(.caption).foregroundStyle(.secondary) }
        }
    }

    private func save() async {
        guard var d = draft else { return }
        guard let price = Marking.parseOdds(priceText) else { error = "Enter the book's odds, like +978 or -110."; return }
        guard let w = Double(wager), w > 0, let u = Double(unit), u > 0 else { error = "Enter the wager and your unit size."; return }
        guard !d.legs.isEmpty, !d.legs.contains(where: { $0.label.trimmingCharacters(in: .whitespaces).isEmpty }) else {
            error = "Every leg needs its wording."; return
        }
        d.price = price; d.stake_dollars = w
        d.boost_pct = Double(boost.replacingOccurrences(of: "%", with: "")).flatMap { $0 > 0 ? $0 : nil }
        let out = ISO8601DateFormatter(); out.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var row = Slip.row(d, unitDollars: u, placedAt: out.string(from: placed), id: String(UUID().uuidString.prefix(8)).lowercased())
        let betId = UUID().uuidString.lowercased()
        row["bet_id"] = betId
        // the wallet token it used (Nov 9; web addSlipBet): claimed first, its id and bonus or boost on the bet, given back on a failure
        let chosen = draftTokens(d).chosen.flatMap { id in tokens.first { $0.promoId == id } }
        if let t = chosen, (t.kind == "bonus") != d.bonus {
            error = "That token is a \(t.kind == "bonus" ? "bonus bet" : "profit boost"): set the slip to match, or pick none."; return
        }
        busy = true
        defer { busy = false }
        if u != store.unitDollars { _ = await store.setUnitDollars(u) }    // the unit typed is the account's (Oct 30)
        var undo: (() async -> Void)? = nil
        if let t = chosen {
            switch await store.claimToken(t.promoId, wager: w) {
            case .failure(let e): error = e.message; return
            case .success(let back): undo = back
            }
            row["promo_id"] = t.promoId
            if t.kind == "boost" {
                if let pct = t.pct { row["boost"] = pct }
                row["boost_cap"] = (t.maxExtraDollars ?? 0) > 0 ? ((t.maxExtraDollars! / u) * 1000).rounded() / 1000 : nil
            }
        }
        error = await store.addRow(row)
        if error != nil, let undo { await undo() }
        // apart from the bet: a price that fails to save must not lose the bet (migration 0038)
        if error == nil, let p = Slip.fairOf(d) { try? await store.api.insert("slip_prices", ["bet_id": betId, "p": p]) }
        if error == nil {
            if chosen != nil { tokens = Promos.wallet((try? await store.api.rows("promos")) ?? tokens).open }
            next()
        }
    }
}
