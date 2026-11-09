import Foundation

/// The signed-in user's own bets, typed prices and settings, shared by Home (Mark as mine) and My bets.
/// Writes go through here as the user (row-level security), then everything reloads.
@MainActor
final class BetStore: ObservableObject {
    @Published private(set) var bets: [MyBet] = [] { didSet { WidgetFeed.write(bets, realMode: isReal) } }
    @Published private(set) var quotes: [Quote] = []       // typed FanDuel / DraftKings prices
    @Published private(set) var customs: [Quote] = []      // parlays built and saved, with grade and result
    @Published private(set) var realFrom: String?
    @Published private(set) var funBucket: Double = 10
    @Published private(set) var book = "FanDuel"
    /// user_settings.notify (jsonb): {"legs": false} turns leg push alerts off for the account (Oct 24).
    @Published private(set) var notify: [String: JSON] = [:]
    var legAlerts: Bool { notify["legs"]?.bool != false }
    /// user_settings.bans: players and teams BetLab gives no bets on (Bans.swift, Oct 25).
    @Published private(set) var bans: [Ban] = []
    /// user_settings.books_off: the books turned off for everything (0043, Nov 6; BooksOff.swift).
    @Published private(set) var booksOff: [String] = []
    var myBooks: [String] { BooksOff.on(booksOff) }
    /// user_settings.watching: the games you'll watch, by game id (0045, Nov 7; Watch.swift): their own parlays join Today.
    @Published private(set) var watching: [String] = []
    /// user_settings.share_bets: friends see your bets (0024, Oct 27; on by default).
    @Published private(set) var shareBets = true
    /// user_settings.unit_dollars: dollars per unit on the account (0029, Oct 30; web unitOf): nil until set, $5 then.
    @Published private(set) var unitDollars: Double?
    /// A new account that hasn't seen the first-run welcome (Nov 5); only ever true after a good read.
    @Published var needsWelcome = false
    var unit: Double { unitDollars.flatMap { $0 > 0 ? $0 : nil } ?? 5 }
    /// Friends' reactions on your bets from the last two weeks (0042): the bubble on Live's cards.
    @Published private(set) var reactions: [Reaction] = []
    func reacting(_ b: MyBet) -> Reacting? {
        let l = reactions.filter { $0.betId == b.betId }
        return l.isEmpty ? nil : Reacting(list: l, me: "")
    }
    /// Ladder challenges (Ladder.swift, Oct 26), newest first.
    @Published private(set) var ladders: [Ladder] = []
    @Published private(set) var error: String?
    @Published private(set) var loaded = false
    /// Goes up each time the app reloads on its own (back in the foreground, every 5 minutes): a screen with its own data
    /// keys its `.task(id:)` on this, so nothing needs the app closed to catch up (Mike, Nov 1, 2026).
    @Published private(set) var refreshTick = 0
    private var reloadedAt = Date.distantPast
    private var pulseWait: Task<Void, Never>?
    let api: SupabaseClient

    init(api: SupabaseClient) { self.api = api }

    /// The parlays' fun-ticket bodies (their games), for team cards (Cards.swift); loaded by Stats and the card sheet.
    @Published private(set) var cardTickets: [String: JSON]?
    func loadCardTickets() async { cardTickets = await Cards.tickets(api, bets) }

    var marks: [String: MyBet] { Dictionary(bets.compactMap { b in b.key.map { ($0, b) } }, uniquingKeysWith: { a, _ in a }) }
    /// Build's marks: open bets only (Nov 9; web openMarks), so the same legs built for another game aren't the old
    /// settled bet.
    var openMarks: [String: MyBet] { Dictionary(bets.filter(\.isOpen).compactMap { b in b.key.map { ($0, b) } }, uniquingKeysWith: { a, _ in a }) }
    var isReal: Bool { Marking.isReal(realFrom: realFrom) }
    /// Open bets with a game in progress, for the Live tab's badge (LiveBadgeWatch).
    @Published var liveCount = 0

    private struct Settings: Decodable { let realFrom: String?; let funBucketMonthly: Double?; let book: String?; let notify: JSON?; let bans: JSON?
                                         let shareBets: Bool?; let unitDollars: Double?; let onboardedAt: String?; let booksOff: [String]?
                                         let watching: [String]? }

    /// Bets and settings again, then every screen's own data; a no-op right after the last one (a glance at Control Center).
    func reload(every gap: TimeInterval = 30) async {
        guard Date().timeIntervalSince(reloadedAt) >= gap else { return }
        reloadedAt = Date()
        let had = loaded
        await load()
        if had { refreshTick += 1 }             // the first load: the screens are loading for themselves already
    }

    /// Something changed in the database (LivePulse): read it soon, once for a burst of changes. A change right after a
    /// reload waits for the gap instead of being dropped.
    func pulsed() {
        pulseWait?.cancel()
        let wait = max(2, 5 - Date().timeIntervalSince(reloadedAt))
        pulseWait = Task {
            try? await Task.sleep(for: .seconds(wait))
            guard !Task.isCancelled else { return }
            await reload(every: 0)
        }
    }

    func load() async {
        if !loaded { await read(api.saved, quiet: true) }     // your bets from last time, at once (Nov 4)
        await read(api, quiet: false)
    }

    /// Each read's number: loads overlap (the 5-minute reload, a pulse, a write's own load, pull to refresh), and an
    /// older read that finishes last must not put back bets from before a newer one (Nov 9: a just-placed bet vanished).
    private var generation = 0

    private func read(_ api: SupabaseClient, quiet: Bool) async {
        generation += 1
        let mine = generation
        do {
            async let b: [MyBet] = api.rows("my_bets")
            async let q: [Quote] = api.rows("quotes")
            async let c: [Quote] = api.rows("custom_parlays")
            async let s: [Settings] = api.rows("user_settings")
            let (bets, quotes, customs, settings) = try await (b, q, c, s)
            // A parlay marked before its price was typed takes the price typed later (web myBetsData).
            let typed = Dictionary((quotes + customs).compactMap { q in q.price.map { (q.sgpId, $0) } }, uniquingKeysWith: { a, _ in a })
            // live CLV on open bets (bet_clv, Oct 28): the worker's value at the last publish
            struct Clv: Decodable { let betId: String; let clv: Double }
            let clvs: [Clv] = (try? await api.rows("bet_clv")) ?? []
            let now = Dictionary(clvs.map { ($0.betId, $0.clv) }, uniquingKeysWith: { a, _ in a })
            struct SlipP: Decodable { let betId: String; let p: Double }
            let slipRows: [SlipP] = (try? await api.rows("slip_prices")) ?? []
            let slipPs = Dictionary(slipRows.map { ($0.betId, $0.p) }, uniquingKeysWith: { a, _ in a })
            // A Build slip marked before Nov 1 was saved without its games: its saved slip has them (web myBetsData).
            let slipGames = Dictionary(customs.compactMap { c in c.games?.array.isEmpty == false ? (c.sgpId, c.games!) : nil },
                                       uniquingKeysWith: { a, _ in a })
            let filled = await Self.withStarts(bets.map { x in
                var x = x
                if x.price == nil, let id = x.sgpId, let p = typed[id] { x.price = p }
                if x.games?.array.isEmpty ?? true, let id = x.sgpId, let g = slipGames[id] { x.games = g }
                x.clvNow = now[x.betId]
                x.slipP = slipPs[x.betId]
                return x
            }, api: api)
            // reactions only reach recent bets: a friend reacts in the feed, which shows the newest 60
            let recent = filled.filter { (Models.date($0.placedAt).map { Date().timeIntervalSince($0) } ?? .infinity) < 14 * 86400 }
            let reacts = await ReactionStore.read(api, recent.map(\.betId))
            // a missing ladders table (before migration 0020) must not stop My bets loading
            let ladderRows = ((try? await api.rows("ladders") as [Ladder]) ?? []).sorted { $0.createdAt > $1.createdAt }
            guard mine == generation else { return }      // a newer read started meanwhile: its answer stands
            self.bets = filled
            self.quotes = quotes
            self.customs = customs
            realFrom = settings.first?.realFrom
            funBucket = settings.first?.funBucketMonthly ?? 10
            book = settings.first?.book ?? "FanDuel"
            notify = settings.first?.notify?.object ?? [:]
            bans = Bans.clean(settings.first?.bans)
            shareBets = settings.first?.shareBets != false
            unitDollars = settings.first?.unitDollars
            // and no bets: a saved copy of the row from before migration 0041 must not greet an old account
            needsWelcome = settings.first?.onboardedAt == nil && bets.isEmpty
            Bans.current = bans
            booksOff = (settings.first?.booksOff ?? []).filter { Marking.books.contains($0) }
            BooksOff.current = booksOff
            watching = settings.first?.watching ?? []
            Watch.current = watching
            reactions = reacts
            ladders = ladderRows
            error = nil
            loaded = true
        } catch {
            if !quiet && mine == generation { self.error = error.localizedDescription }
        }
    }

    /// A bet with no start of its own (entered by hand or from a slip) sorts, files and closes (Tail) by its first
    /// game's kickoff (web withStarts).
    static func withStarts(_ bets: [MyBet], api: SupabaseClient) async -> [MyBet] {
        let need = bets.filter { $0.pickCommenceTime == nil && $0.ticketCommenceTime == nil && !($0.games?.array.isEmpty ?? true) }
        let ids = Array(Set(need.flatMap { b in (b.games?.array ?? []).compactMap { g -> String? in
            let r = g["game_ref"].string ?? g["gameRef"].string
            return BetMath.refTime(r) == nil ? BetMath.refGameId(r) : nil
        } }))
        struct Start: Decodable { let gameId: String; let commenceTime: String? }
        let rows: [Start] = ids.isEmpty ? [] : (try? await api.rows("games", .init(select: "game_id,commence_time", inList: ("game_id", ids)))) ?? []
        let starts = Dictionary(rows.compactMap { r in r.commenceTime.map { (r.gameId, $0) } }, uniquingKeysWith: { a, _ in a })
        return bets.map { x in
            var x = x
            if x.pickCommenceTime == nil && x.ticketCommenceTime == nil { x.gameStart = BetMath.gameStart(x, starts: starts) }
            return x
        }
    }

    func input(for t: Ticket) -> MarkInput {
        let q = Dictionary(quotes.compactMap { x in x.price.map { (x.sgpId, $0) } }, uniquingKeysWith: { a, _ in a })
        return .ticket(t, quote: q[t.sgpId], dkQuote: q[t.sgpId + "~dk"])
    }

    /// Leg push alerts on or off for this account (user_settings.notify.legs; the worker's leg_alerts.py skips an
    /// account set to false). Other notify keys are kept (web setLegAlerts).
    func setLegAlerts(_ on: Bool) async -> String? {
        var n = notify
        n["legs"] = .bool(on)
        do {
            try await api.upsert("user_settings", ["notify": JSON.object(n).any, "updated_at": ISO8601DateFormatter().string(from: Date())],
                                 onConflict: "user_id")
            notify = n
            return nil
        } catch { return (error as? AuthError)?.message ?? "Couldn't save that." }
    }

    /// Alert settings (web setNotify, Nov 2): any notify keys, the rest kept; the worker's alert_prefs.py reads them.
    func setNotify(_ patch: [String: JSON]) async -> String? {
        var n = notify
        for (k, v) in patch { n[k] = v }
        do {
            try await api.upsert("user_settings", ["notify": JSON.object(n).any, "updated_at": ISO8601DateFormatter().string(from: Date())],
                                 onConflict: "user_id")
            notify = n
            return nil
        } catch { return (error as? AuthError)?.message ?? "Couldn't save that." }
    }

    /// Dollars per unit on the account (web setUnitDollars, Oct 30): the slip reader and promo placements use it.
    func setUnitDollars(_ dollars: Double) async -> String? {
        guard dollars > 0, dollars <= 100000 else { return "A unit is a dollar amount above 0." }
        do {
            let d = (dollars * 100).rounded() / 100
            try await api.upsert("user_settings", ["unit_dollars": d, "updated_at": ISO8601DateFormatter().string(from: Date())], onConflict: "user_id")
            unitDollars = d
            return nil
        } catch { return (error as? AuthError)?.message ?? "Couldn't save that." }
    }

    /// The books turned off for everything (web setBooksOff, 0043): never all three.
    func setBooksOff(_ off: [String]) async -> String? {
        let next = Marking.books.filter { off.contains($0) }
        guard next.count < Marking.books.count else { return "Keep at least one book on." }
        do {
            try await api.upsert("user_settings", ["books_off": next, "updated_at": ISO8601DateFormatter().string(from: Date())], onConflict: "user_id")
            booksOff = next
            BooksOff.current = next
            await load()
            return nil
        } catch { return (error as? AuthError)?.message ?? "Couldn't save that." }
    }

    /// Watch a game or stop (web setWatching, 0045): its own parlays join Today when its slice locks, with the lock alert.
    func setWatching(_ gameId: String, _ on: Bool) async -> String? {
        let next = Watch.toggled(watching, gameId, on: on)
        do {
            try await api.upsert("user_settings", ["watching": next, "updated_at": ISO8601DateFormatter().string(from: Date())], onConflict: "user_id")
            watching = next
            Watch.current = next
            return nil
        } catch { return (error as? AuthError)?.message ?? "Couldn't save that." }
    }

    /// Whether friends see your bets (web setShareBets).
    func setShareBets(_ on: Bool) async -> String? {
        do {
            try await api.upsert("user_settings", ["share_bets": on, "updated_at": ISO8601DateFormatter().string(from: Date())], onConflict: "user_id")
            shareBets = on
            return nil
        } catch { return (error as? AuthError)?.message ?? "Couldn't save that." }
    }

    /// Save the whole ban list (web setBans); at most 200 entries.
    func setBans(_ list: [Ban]) async -> String? {
        let next = Array(list.prefix(200))
        do {
            try await api.upsert("user_settings", ["bans": next.map(\.row), "updated_at": ISO8601DateFormatter().string(from: Date())],
                                 onConflict: "user_id")
            bans = next
            Bans.current = next
            return nil
        } catch { return (error as? AuthError)?.message ?? "Couldn't save that." }
    }

    /// The theme this device shows, on the account (user_settings.theme, Oct 25): the worker's leg alerts speak "diva"
    /// to an account on Pink (leg_alerts.py). Best effort: a failed save leaves the alerts as they were.
    /// The welcome's last step: the account's unit, and that it's seen the welcome. An error's words, or nil.
    func finishWelcome(unit d: Double) async -> String? {
        let now = ISO8601DateFormatter().string(from: Date())
        do {
            try await api.upsert("user_settings", ["unit_dollars": d, "onboarded_at": now, "updated_at": now], onConflict: "user_id")
            unitDollars = d
            needsWelcome = false
            return nil
        } catch { return (error as? AuthError)?.message ?? "Couldn't save that." }
    }

    func saveTheme(_ id: String) async {
        _ = try? await api.upsert("user_settings", ["theme": id, "updated_at": ISO8601DateFormatter().string(from: Date())],
                                  onConflict: "user_id")
    }

    /// A promo placement (the finder, Oct 30; web placePromo): the slips first, then the bet (and a lock's hedge). Nov 9: refused
    /// before anything is written when a bet on the same slip at that book exists (bets' unique user_id, sgp_id: the insert failed
    /// only after the earlier bet's saved slip was overwritten and a bonus split), and the token is claimed first (`claimToken`),
    /// given back if the bet then fails to save.
    func placePromo(customs: [[String: Any?]], bets: [[String: Any?]], token: String? = nil, dollars: Double? = nil) async -> String? {
        let ids = bets.compactMap { $0["sgp_id"] as? String }
        struct Had: Decodable { let sgpId: String? }
        let had: [Had] = (try? await api.rows("bets", .init(select: "sgp_id", limit: 1, inList: ("sgp_id", ids)))) ?? []
        if !had.isEmpty || ids.contains(where: { marks[$0] != nil }) { return Self.alreadyBet }
        var undo: (() async -> Void)? = nil
        if let token {
            switch await claimToken(token, wager: dollars) {
            case .failure(let e): return e.message
            case .success(let u): undo = u
            }
        }
        let e = await write { api in
            for c in customs { try await api.upsert("custom_parlays", c, onConflict: "user_id,sgp_id") }
            for b in bets { try await api.insert("bets", b) }
        }
        if e != nil, let undo { await undo(); await load() }
        return e
    }
    static let alreadyBet = "You already have a bet on this slip at this book: pick another, or undo that bet first."

    /// I placed this with a wallet token (Build, Nov 9; web Builder's place through placePromo): the mark with the token's id, its
    /// bonus or boost and the boost's cap in units, the units typed (the token's dollars by default), the token claimed first.
    func placeWithToken(_ m: MarkInput, token: PromoRow, stake: String, price: String, book: String) async -> String? {
        let boost = token.kind == "boost" ? token.pct.map { String(format: "%g", $0) } ?? "" : ""
        switch Marking.edit(stake: stake, price: price, book: book, bonus: token.kind == "bonus", boost: boost) {
        case .failure(let e): return e.message
        case .success(let change):
            var row = Marking.row(m, real: true)       // the sheet that asks is for real bets only, as `place`
            for (k, v) in change { row[k] = v }
            let units = Double(stake.trimmingCharacters(in: .whitespaces)) ?? 1
            row["stake"] = (units * 1000).rounded() / 1000
            row["promo_id"] = token.promoId
            if token.kind == "boost", let c = token.maxExtraDollars, c > 0 { row["boost_cap"] = (c / unit * 1000).rounded() / 1000 }
            var dollars = (units * unit * 100).rounded() / 100
            if let face = token.amountDollars, abs(dollars - face) < 0.05 { dollars = face }    // the unit's rounding, not a bigger bet
            let undo: () async -> Void
            switch await claimToken(token.promoId, wager: dollars) {
            case .failure(let e): return e.message
            case .success(let u): undo = u
            }
            let e = await write { try await $0.insert("bets", row) }
            if e != nil { await undo(); await load() }
            return e
        }
    }

    /// Take a wallet token for a bet of `wager` dollars, before the bet is written (Nov 9; web claimToken): it must still be open
    /// (Promos.usable: a used one could go on a second bet), the wager at most its dollars (unless `overMax`, for I used it on a bet
    /// already placed), and a bonus bet used for less than its face (Nov 3) is split, the rest becoming its own open token on the
    /// same terms. The split is one conditional update, made only while the token is open at the face just read, so two placements
    /// can't both split it. Gives back an undo for when the bet then fails to save.
    func claimToken(_ id: String, wager: Double?, overMax: Bool = false) async -> Result<() async -> Void, AuthError> {
        let rows: [PromoRow]
        do { rows = try await api.rows("promos", .init(eq: [("promo_id", id)])) }
        catch { return .failure(AuthError(message: (error as? AuthError)?.message ?? "Couldn't check that promo.")) }
        let p = rows.first
        if let bad = Promos.usable(p) { return .failure(AuthError(message: bad)) }
        guard let p else { return .failure(AuthError(message: "That promo is gone.")) }
        if !overMax, let w = wager, let face = p.amountDollars, w > face + 0.004 {
            return .failure(AuthError(message: "This \(p.kind == "bonus" ? "bonus bet" : "boost's max wager") is \(PromoFinder.money(face))."))
        }
        let left = p.kind == "bonus" ? wager.map { Promos.bonusLeft(p.amountDollars, $0) } ?? 0 : 0
        guard left > 0, let wager, let face = p.amountDollars else { return .success({}) }
        do {
            let n = try await api.updateCount("promos", eq: [("promo_id", id), ("status", "open"), ("amount_dollars", "\(face)")], ["amount_dollars": wager])
            guard n > 0 else { return .failure(AuthError(message: "That promo just changed: reload and try again.")) }
        } catch { return .failure(AuthError(message: (error as? AuthError)?.message ?? "Couldn't save that.")) }
        let restId = UUID().uuidString.lowercased()
        var rest = p.row
        rest["amount_dollars"] = left; rest["promo_id"] = restId; rest["status"] = "open"
        let api = self.api
        let back = { _ = try? await api.update("promos", eq: [("promo_id", id)], ["amount_dollars": face]) }
        do { try await api.insert("promos", rest) }
        catch { await back(); return .failure(AuthError(message: (error as? AuthError)?.message ?? "Couldn't save that.")) }
        return .success({ _ = try? await api.delete("promos", eq: [("promo_id", restId)]); await back() })
    }

    /// Undo a promo placement: the bet, and its lock's hedge with it (web undoPromo); the token goes back to the wallet.
    func undoPromo(_ b: MyBet) async -> String? {
        await write { try await $0.delete("bets", eq: [b.lockId != nil ? ("lock_id", b.lockId!) : ("sgp_id", b.sgpId ?? "")]) }
    }

    /// A bets row built elsewhere (a slip read from a screenshot, Slip.row).
    func addRow(_ row: [String: Any?]) async -> String? { await write { try await $0.insert("bets", row) } }

    /// Each returns the message to show, or nil when it worked.
    func mark(_ m: MarkInput) async -> String? {
        await write { try await $0.insert("bets", Marking.row(m, real: self.isReal)) }
    }

    /// A real bet marked with what was placed, in one step (Mike, Oct 24: units, price, book, bonus bet or boost typed
    /// at the mark instead of in Edit after): the mark's row with the typed fields over it.
    func place(_ m: MarkInput, stake: String, price: String, book: String, bonus: Bool, boost: String) async -> String? {
        switch Marking.edit(stake: stake, price: price, book: book, bonus: bonus, boost: boost) {
        case .failure(let e): return e.message
        case .success(let change):
            var row = Marking.row(m, real: true)
            for (k, v) in change { row[k] = v }
            return await write { try await $0.insert("bets", row) }
        }
    }

    /// A typed book price for a slip (web PriceBox / saveQuote): DraftKings' under "<sgp_id>~dk". It grades the slip
    /// and teaches that book's quote model.
    func saveQuote(_ t: Ticket, price: Double, book: String, legs: [String]) async -> String? {
        let dk = book == "DraftKings"
        let row: [String: Any?] = ["sgp_id": t.sgpId + (dk ? "~dk" : ""), "price": price, "fair_price": t.fairPrice,
                                   "naive_price": dk ? t.body.dk?.naivePrice : t.naivePrice, "p_fair": t.pFair, "legs": legs,
                                   "n_legs": legs.count, "matchup": t.matchup, "odds_event_id": t.body.eventId, "sport": t.sport,
                                   "book": book, "quoted_at": ISO8601DateFormatter().string(from: Date())]
        return await write { try await $0.upsert("quotes", row, onConflict: "user_id,sgp_id") }
    }

    /// The price typed for a slip at a book, if any.
    func quote(_ t: Ticket, book: String) -> Double? {
        let id = t.sgpId + (book == "DraftKings" ? "~dk" : "")
        return quotes.first { $0.sgpId == id }?.price
    }

    func undo(key m: MarkInput) async -> String? {
        await write { try await $0.delete("bets", eq: [m.pickId != nil ? ("pick_id", m.pickId!) : ("sgp_id", m.sgpId ?? "")]) }
    }

    func undo(_ b: MyBet) async -> String? {
        await undo(key: MarkInput(kind: b.kind, pickId: b.pickId, sgpId: b.sgpId))
    }

    func edit(_ bet: MyBet, stake: String, price: String, book: String, bonus: Bool, cashout: String, boost: String,
              protect: Bool? = nil, reset: Bool? = nil) async -> String? {
        switch Marking.edit(stake: stake, price: price, book: book, bonus: bonus, cashout: cashout, boost: boost, protect: protect, reset: reset,
                            current: bet.stake, ladder: bet.ladderId != nil) {
        case .failure(let e): return e.message
        case .success(let change): return await write { try await $0.update("bets", eq: [("bet_id", bet.betId)], change) }
        }
    }

    // MARK: - ladders (Oct 26; web lib/actions.ts startLadder, stopLadder, ladderStep)

    /// What BetLab could suggest as a step: the card's live picks and leans for the next two days, off the ban list.
    func ladderOffers() async -> [Offer] {
        let now = Date()
        let offers: [Offer] = (try? await api.rows("offers", .init(from: ("commence_time", now),
                                                                    to: ("commence_time", now.addingTimeInterval(48 * 3600)), active: true))) ?? []
        return BooksOff.mine(offers).filter { $0.tier != .check && !Bans.banned(bans, $0.label, league: $0.league, player: $0.player) }
    }

    /// Every game still to start today (ET), priced or not: the step chooser lists them all (web ladderData).
    func ladderGames() async -> [Game] {
        let now = Date()
        let games: [Game] = (try? await api.rows("games", .init(from: ("commence_time", now), to: ("commence_time", LadderMath.endOfDay(now))))) ?? []
        return games.sorted { ($0.commenceTime ?? "") < ($1.commenceTime ?? "") }
    }

    /// Change a ladder (web changeLadder): `skip` turns an offer down (a locked step is unlocked so the worker picks the
    /// next), `unskip` brings them all back, `game` keeps the next step to one game ("" for any game today; a new choice
    /// unlocks a locked step and clears a notice). Saved on the ladder, so both apps and the worker see it.
    func changeLadder(_ l: Ladder, skip: String? = nil, unskip: Bool = false, game: String?? = nil) async -> String? {
        var change: [String: Any?] = [:]
        if let skip {
            change["skipped"] = Array(Set((l.skipped ?? []) + [skip]))
            if l.locked?.offerId == skip { change["locked"] = nil as Any?; change["locked_at"] = nil as Any? }
        }
        if unskip { change["skipped"] = [String]() }
        if let game {
            change["game_id"] = game.flatMap { $0.isEmpty ? nil : $0 } as Any?
            change["notice"] = nil as Any?; change["locked"] = nil as Any?; change["locked_at"] = nil as Any?
        }
        return await write { try await $0.update("ladders", eq: [("ladder_id", l.ladderId)], change) }
    }

    /// Start a ladder from `start` units to `target`. One active ladder at a time.
    func startLadder(start: Double, target: Double, book: String = "FanDuel") async -> String? {
        guard start > 0, start <= 100 else { return "Start with some units, like 1." }
        guard target > start, target <= 100_000 else { return "The target has to be above the start." }
        // a ladder its steps already ended (busted or climbed) is closed here rather than blocking a new one (web
        // startLadder, Nov 6: Mike's busted ladder stayed "active"); it still reads as busted
        let active = ladders.filter { $0.status == "active" }
        let over = active.filter { [.busted, .climbed].contains(LadderMath.state($0, bets).phase) }
        for l in over {
            if let e = await write({ try await $0.update("ladders", eq: [("ladder_id", l.ladderId)],
                                                         ["status": "stopped", "ended_at": ISO8601DateFormatter().string(from: Date()),
                                                          "locked": nil, "locked_at": nil]) }) { return e }
        }
        if active.count > over.count { return "Finish or stop the ladder you're on first." }
        return await write { try await $0.insert("ladders", ["start_units": start, "target_units": target, "book": Marking.bookOf(book)]) }
    }

    /// Stop a ladder; its bets stay, graded as normal. A ladder that never had a step is deleted instead, so a tryout
    /// leaves nothing under Past ladders (Mike, Oct 26; web stopLadder).
    func stopLadder(_ l: Ladder) async -> String? {
        if !bets.contains(where: { $0.ladderId == l.ladderId }) {
            return await write { try await $0.delete("ladders", eq: [("ladder_id", l.ladderId)]) }
        }
        return await write { try await $0.update("ladders", eq: [("ladder_id", l.ladderId)],
                                                 ["status": "stopped", "ended_at": ISO8601DateFormatter().string(from: Date())]) }
    }

    /// Make a bet the ladder's next step at `stake` units (the whole stack): BetLab's suggestion (saved like Place; a
    /// pick already marked is the same bet), or one of your open bets. A real bet, outside the 5u-a-day rule.
    func ladderStep(_ l: Ladder, stake: Double, offer: Offer? = nil, bet: MyBet? = nil) async -> String? {
        let units = (stake * 100).rounded() / 100
        if let o = offer, marks[o.offerId] == nil {
            var row = Marking.row(.offer(o), real: true)
            row["stake"] = units
            row["ladder_id"] = l.ladderId
            return await write {
                try await $0.insert("bets", row)
                try await $0.update("ladders", eq: [("ladder_id", l.ladderId)], ["locked": nil, "locked_at": nil, "notice": nil])
            }
        }
        guard let id = bet?.betId ?? offer.flatMap({ marks[$0.offerId]?.betId }) else { return "Pick a bet for this step." }
        return await write {
            try await $0.update("bets", eq: [("bet_id", id)], ["ladder_id": l.ladderId, "stake": units, "mode": "real"])
            try await $0.update("ladders", eq: [("ladder_id", l.ladderId)], ["locked": nil, "locked_at": nil, "notice": nil])
        }
    }

    /// The worker's locked step, placed: saved as its pick or lean at the whole stack (a pick already marked is that bet).
    func ladderStep(_ l: Ladder, stake: Double, locked k: LockedStep) async -> String? {
        let m = MarkInput(kind: k.tier == "pick" ? "pick" : "lean", pickId: k.offerId, price: k.price, label: k.label,
                          matchup: k.matchup, book: Marking.bookOf(k.book))
        let units = (stake * 100).rounded() / 100
        if let had = marks[k.offerId] { return await ladderStep(l, stake: stake, bet: had) }
        var row = Marking.row(m, real: true)
        row["stake"] = units
        row["ladder_id"] = l.ladderId
        return await write {
            try await $0.insert("bets", row)
            try await $0.update("ladders", eq: [("ladder_id", l.ladderId)], ["locked": nil, "locked_at": nil, "notice": nil])
        }
    }

    private func write(_ op: (SupabaseClient) async throws -> Void) async -> String? {
        do { try await op(api) } catch { return (error as? AuthError)?.message ?? Marking.friendly("") }
        await load()
        return nil
    }
}
