import XCTest
@testable import BetLab

/// Home's feed must match the web app's rules (web/lib/data.ts homeData).
final class FeedTests: XCTestCase {
    // the host app signs in and loads the account's books off (BooksOff.current); every case here starts with all three on
    override func setUp() { super.setUp(); BooksOff.current = [] }

    let now = Models.date("2026-10-14T16:00:00Z")!          // noon ET
    func iso(_ hoursFromNow: Double) -> String {
        let f = ISO8601DateFormatter()
        return f.string(from: now.addingTimeInterval(hoursFromNow * 3600))
    }

    func game(_ id: String, _ league: String = "nfl", at h: Double) -> Game {
        Game(gameId: id, league: league, home: nil, away: nil, matchup: id, commenceTime: iso(h), state: nil)
    }
    func offer(_ id: String, game: String, tier: Tier, market: String = "spreads", ev: Double = 0.05, at h: Double, league: String = "nfl") -> Offer {
        Offer(offerId: id, tier: tier, league: league, gameId: game, commenceTime: iso(h), matchup: game, market: market, kind: nil,
              player: nil, label: "Bills -3.5", point: -3.5, price: -110, book: "FanDuel", pModel: nil, pMarket: nil, pFinal: 0.55,
              ev: ev, unitsFlat: 1, marketSource: nil, why: nil, context: nil, fdUrl: nil, otherBook: nil, otherPoint: nil, otherPrice: nil)
    }
    func ticket(_ id: String, kind: String, game: String?, slate: String? = nil, at h: Double) -> Ticket {
        Ticket(sgpId: id, kind: kind, sport: "nfl", gameId: game, slate: slate, matchup: nil, commenceTime: iso(h),
               fairPrice: 400, pFair: 0.2, price: nil, body: TicketBody())
    }

    func testStartedGamesDropAndPicksComeFirst() {
        let f = FeedLogic.build(games: [game("A", at: 5), game("B", at: -1)],
                                offers: [offer("o1", game: "A", tier: .pick, ev: 0.02, at: 5), offer("o2", game: "A", tier: .pick, ev: 0.03, at: 5),
                                         offer("o3", game: "B", tier: .pick, at: -1)],
                                tickets: [], slates: [], sport: nil, now: now)
        XCTAssertEqual(f.picks.map(\.offerId), ["o2", "o1"])     // best EV first
        XCTAssertEqual(f.items.map(\.id), [])                  // picks aren't repeated in their game's row (Oct 28)
        XCTAssertEqual(f.quiet, 0)                              // and a game with a pick isn't "nothing to act on"
    }

    func testHomeShowsNoLeans() {      // Oct 22: leans stay on each game's page and Games
        let f = FeedLogic.build(games: [game("A", at: 5), game("B", at: 6)],
                                offers: [offer("pick", game: "A", tier: .pick, at: 5), offer("lean", game: "A", tier: .lean, at: 5),
                                         offer("prop", game: "B", tier: .lean, market: "player_pass_yds", at: 6)],
                                tickets: [], slates: [], sport: nil, now: now)
        XCTAssertEqual(f.picks.map(\.offerId), ["pick"])
        XCTAssertEqual(f.items.map(\.id), [])
        XCTAssertEqual(f.quiet, 1)
    }

    func testQuietGamesAndCheckFlagsStayOffHome() {
        let f = FeedLogic.build(games: [game("A", at: 5), game("B", at: 6)],
                                offers: [offer("c", game: "A", tier: .check, at: 5)], tickets: [], slates: [],
                                sport: nil, now: now)
        XCTAssertTrue(f.items.isEmpty)
        XCTAssertEqual(f.quiet, 2)
    }

    func testAWatchedGamesSlipsJoinTheParlaysByItsOwnLock() {
        // Nov 7 (Mike): a game's own slips show for the games you watch, next to the slice's SGP+ once it locks; until
        // then an SGP+ hid its window's slips (Oct 12) and a lone game showed its own
        let games = [game("A", at: 0.3), game("B", at: 0.3)]
        let slips = [ticket("a1", kind: "sgp", game: "A", slate: "s1", at: 0.3), ticket("b1", kind: "sgp", game: "B", slate: "s1", at: 0.3)]
        let plus = ticket("plus", kind: "sgp_plus", game: nil, slate: "s1", at: 0.3)
        let slate = Slate(slate: "s1", sport: "nfl", kickoff: iso(0.3), nGames: 2, title: "Sunday early", lockedAt: iso(-0.1))
        let none = FeedLogic.build(games: games, offers: [], tickets: slips + [plus], slates: [slate], sport: nil, watching: [], now: now)
        XCTAssertEqual(none.items.map(\.id), ["t-plus"])
        let watched = FeedLogic.build(games: games, offers: [], tickets: slips + [plus], slates: [slate], sport: nil, watching: ["A"], now: now)
        XCTAssertEqual(Set(watched.items.map(\.id)), ["t-plus", "t-a1"])
        XCTAssertEqual(FeedLogic.ticketTitle(plus, slate), "Sunday early · SGP+ · locked")
        // by its own game's lock, never the slice's (Nov 7): a later game in a locked slice waits for its own
        let late = [game("A", at: 3)], lateSlip = [ticket("a1", kind: "sgp", game: "A", slate: "s1", at: 3)]
        XCTAssertTrue(FeedLogic.build(games: late, offers: [], tickets: lateSlip, slates: [slate], sport: nil, watching: ["A"], now: now).items.isEmpty)
        let open = Slate(slate: "s1", sport: "nfl", kickoff: iso(0.3), nGames: 2, title: nil, lockedAt: nil)
        XCTAssertEqual(FeedLogic.build(games: games, offers: [], tickets: slips, slates: [open], sport: nil, watching: ["A"], now: now)
                        .items.map(\.id), ["t-a1"])
    }

    func testUnlockedSgpPlusWaits() {
        let plus = ticket("plus", kind: "sgp_plus", game: nil, slate: "s1", at: 3)
        let slate = Slate(slate: "s1", sport: "nfl", kickoff: iso(3), nGames: 3, title: nil, lockedAt: nil)
        let f = FeedLogic.build(games: [], offers: [], tickets: [plus], slates: [slate], sport: nil, now: now)
        XCTAssertTrue(f.items.isEmpty)
    }

    func testSportFilter() {
        let f = FeedLogic.build(games: [game("A", at: 5), game("H", "nhl", at: 6)],
                                offers: [offer("o1", game: "A", tier: .pick, at: 5), offer("o2", game: "H", tier: .pick, at: 6, league: "nhl")],
                                tickets: [], slates: [], sport: "nhl", now: now)
        XCTAssertEqual(f.picks.map(\.offerId), ["o2"])
        XCTAssertEqual(f.sports, ["nfl", "nhl"])
    }

    func testTodayWindowIsEastern() {
        // 1 AM ET Oct 15 (05:00Z): today runs to midnight ET Oct 16, tomorrow is all of Oct 16 ET
        let late = Models.date("2026-10-15T05:00:00Z")!
        XCTAssertEqual(FeedLogic.window(.today, now: late).to, Models.date("2026-10-16T04:00:00Z"))
        XCTAssertEqual(FeedLogic.window(.tomorrow, now: late).from, Models.date("2026-10-16T04:00:00Z"))
        XCTAssertEqual(FeedLogic.window(.today, now: late).from, Models.date("2026-10-15T04:00:00Z"))
    }

    func testFormatting() {
        XCTAssertEqual(Fmt.am(150), "+150")
        XCTAssertEqual(Fmt.am(-110), "\u{2212}110")
        XCTAssertEqual(Fmt.label("Bills -3.5"), "Bills \u{2212}3.5")
        XCTAssertEqual(Fmt.signed(0.042), "+4.2%")
        XCTAssertEqual(Fmt.implied(-110), 110.0 / 210.0, accuracy: 1e-9)
        XCTAssertEqual(Fmt.sportName("ufc"), "UFC")             // not Soccer, the fallback (Oct 23)
        XCTAssertEqual(Fmt.sportShort["ufc"], "UFC")
        XCTAssertEqual(FanDuel.links("https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=2")?.app.absoluteString,
                       "fanduelsportsbook://ny.sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=2")
        let novig = Novig.links("https://novig.com/events/01a17ead-b7b2-7a71-aa1a-68515b461ab7/oddsapi/5")
        XCTAssertEqual(novig?.app.absoluteString, "novigapp://events/01a17ead-b7b2-7a71-aa1a-68515b461ab7/oddsapi/5")
        XCTAssertEqual(novig?.web.absoluteString, "https://novig.com/events/01a17ead-b7b2-7a71-aa1a-68515b461ab7/oddsapi/5")
        XCTAssertNil(Novig.links("https://novig.com/"))
        // Novig's whole slip (Oct 28): every leg's id in one order-slip link, and the pricer's answer as American odds
        XCTAssertEqual(Build.link(book: .novig, ["https://novig.com/events/a/oddsapi/5", "https://novig.com/events/b/oddsapi/5"]),
                       "https://novig.com/events/a,b/oddsapi/5")
        XCTAssertNil(Build.link(book: .novig, ["https://novig.com/events/a/oddsapi/5", nil]))
        let q = NovigQuote.parse(#"{"price":"0.333","expiresAt":1793381399956,"serverNow":1793381369957}"#.data(using: .utf8)!)
        XCTAssertEqual(q?.price, 200)
        XCTAssertNil(q?.stakeMax)
        XCTAssertNil(NovigQuote.parse(#"[{"price":"0.5"}]"#.data(using: .utf8)!))   // the old route's array (gone Oct 29)
        XCTAssertNil(NovigQuote.parse(#"{"statusCode":400}"#.data(using: .utf8)!))
        let nv = Pricer(["g": Pack(eventId: "g", matchup: "A @ B", commenceTime: "", gameRef: nil, sport: "nba", draws: 8, legs: [
            "A ML": PackLeg(label: "A ML", price: 110, p: 0.5, pPack: 0.5, nvId: "id-a", nvPrice: 102),
            "X over 9.5 points": PackLeg(label: "X over 9.5 points", price: -140, p: 0.6, pPack: 0.6, nvId: "id-x"),
            "Y over 4.5 rebounds": PackLeg(label: "Y over 4.5 rebounds", price: -120, p: 0.55, pPack: 0.55)])], book: .novig)
        XCTAssertEqual(nv.leg("g", "A ML")?.price, 102)
        XCTAssertEqual(nv.leg("g", "X over 9.5 points")?.price, -150)
        XCTAssertEqual(nv.leg("g", "Y over 4.5 rebounds")?.unavailable, true)
        XCTAssertEqual(nv.novigIds([SlipLeg(eventId: "g", label: "A ML"), SlipLeg(eventId: "g", label: "X over 9.5 points")]), ["id-a", "id-x"])
        XCTAssertTrue(Build.id([SlipLeg(eventId: "g", label: "A ML")], book: .novig).hasSuffix("~nv"))
    }

    /// Novig challenges (Oct 28; web tests/challenges.test.mjs): a row decodes and says where it stands.
    func testChallengeStates() throws {
        let json = #"""
        [{"challenge_id":"c","day":"2026-10-28","text":"Place a straight trade on CFB (Min. $5)","points":50,"status":"open",
          "pick":null,"notice":null,"best":{"label":"Tulane Green Wave -10.5","legs":[{"label":"Tulane Green Wave -10.5",
          "game":"Tulane Green Wave @ Charlotte 49ers","start":"2026-10-30T23:00:00Z","price":111,"p":0.49}],"price":111,
          "dec":2.11,"p":0.49,"ev":0.035,"link":"https://novig.com/events/x/oddsapi/5","stake":5,"stake_max":null,
          "matchup":"Tulane Green Wave @ Charlotte 49ers","commence_time":"2026-10-30T23:00:00Z"}}]
        """#
        let c = try Models.decoder.decode([Challenge].self, from: json.data(using: .utf8)!)[0]
        XCTAssertEqual(c.state.tag, "Watching")
        XCTAssertEqual(c.state.bet?.legs.first?.game, "Tulane Green Wave @ Charlotte 49ers")
        XCTAssertTrue(c.state.note?.contains("alert when it's ripe") == true)
        let missed = Challenge(challengeId: "c", day: "d", text: "t", points: nil, status: "open", pick: nil, best: nil, notice: "missed: Tulane -10.5")
        XCTAssertEqual(missed.state.note, "Tulane -10.5 started before it was placed; finding another.")
        XCTAssertEqual(Challenge(challengeId: "c", day: "d", text: "t", points: nil, status: "skipped", pick: nil, best: nil, notice: nil).state.tag, "Skipped")
    }

    /// web tests/challenges.test.mjs "challenge history", case for case.
    func testChallengeHistory() {
        let pick = { (id: String) in ChallengeBet(label: "bet \(id)", legs: [], price: 100, dec: 2, p: 0.5, ev: 0, link: "https://novig.com/events/\(id)/oddsapi/5", stake: 5) }
        let ch = { (id: String, day: String, status: String, p: ChallengeBet?) in
            Challenge(challengeId: id, day: day, text: "t", points: 50, status: status, pick: p, best: nil, notice: nil) }
        let rows = [ch("a", "2026-10-27", "done", pick("o1")), ch("b", "2026-10-27", "done", pick("o2")),
                    ch("c", "2026-10-27", "done", ChallengeBet(label: "parlay", legs: [], price: 300, dec: 4, p: 0.24, ev: 0, link: "https://novig.com/events/x,y/oddsapi/5", stake: 5)),
                    ch("d", "2026-10-28", "done", pick("o3")), ch("e", "2026-10-28", "skipped", nil), ch("f", "2026-09-30", "done", pick("o9"))]
        let bets = [ChallengeHistory.Bet(sgpId: "novig-o1", status: "won", profit: 1.1), ChallengeHistory.Bet(sgpId: "novig-o2", status: "lost", profit: -1),
                    ChallengeHistory.Bet(sgpId: "novig-o3", status: "open", profit: nil)]
        let h = ChallengeHistory.build(rows, bets: bets, today: "2026-10-28")
        XCTAssertEqual(h.days.map { "\($0.day) \($0.done)/\($0.total) \($0.points) \($0.bonus)" },
                       ["2026-10-28 1/2 50 false", "2026-10-27 3/3 250 true", "2026-09-30 1/1 50 false"])
        XCTAssertEqual(h.days[1].items.map(\.result), ["won", "lost", nil])
        XCTAssertEqual(h.days[0].items[0].result, "open")
        XCTAssertEqual(h.month.points, 300); XCTAssertEqual(h.month.done, 4); XCTAssertEqual(h.month.total, 5)
        XCTAssertEqual(h.month.sweeps, 1); XCTAssertEqual(h.month.settled, 2); XCTAssertEqual(h.month.won, 1)
        XCTAssertEqual(h.month.units, 0.1, accuracy: 1e-9)
    }

    func testDecodesSupabaseRows() throws {
        let json = #"""
        [{"sgp_id":"x","kind":"sgp","sport":"nfl","game_id":"nfl:1","slate":null,"matchup":"A @ B",
          "commence_time":"2026-10-14T23:15:00+00:00","fair_price":412.5,"p_fair":0.195,"price":null,
          "body":{"theme":"Shootout","legs":[{"label":"Over 47.5","price":-105}],"weird":{"x":[1,"a"]}}}]
        """#
        let t = try Models.decoder.decode([Ticket].self, from: Data(json.utf8))
        XCTAssertEqual(t[0].body.legs?.first?.price, -105)
        XCTAssertEqual(Fmt.time(t[0].commenceTime), "7:15 PM")
    }

    func testALoneNbaSlipWithLegLabelsShowsItsFullLegs() throws {
        // Oct 20: fun_nba.game_slips lists the game's legs by label only, which failed the whole body (an empty slip)
        let json = #"""
        {"sgp_id":"n1","kind":"sgp","sport":"nba","fair_price":5772,"p_fair":0.017,
         "body":{"theme":"Correlated overs","games":[{"matchup":"BOS @ DET","commence_time":"2026-10-20T19:00:00Z",
           "legs":["Derrick White 6+ assists"]}],
          "legs":[{"label":"Derrick White 6+ assists","price":280,
            "link":"https://ny.sportsbook.fanduel.com/addToBetslip?marketId=42.6&selectionId=2"}]}}
        """#
        let t = try Models.decoder.decode(Ticket.self, from: Data(json.utf8))
        XCTAssertEqual(t.body.theme, "Correlated overs")
        XCTAssertEqual(t.body.games?.first?.legs.first?.price, 280)
        XCTAssertNotNil(SlipBooks.legs(t).first?.link)
        let over = try Models.decoder.decode(Ticket.self, from: Data(#"{"sgp_id":"o1","kind":"over","sport":"nba","body":{"label":"Payton Pritchard 21+ points"}}"#.utf8))
        XCTAssertEqual(over.body.label, "Payton Pritchard 21+ points")
    }

    func testASlipOpensAtBothBooksAndReadsDraftKingsSide() throws {
        let json = #"""
        {"sgp_id":"t1","kind":"sgp_plus","sport":"soccer","fair_price":1696,"p_fair":0.056,"naive_price":"1500",
         "body":{"likely_price":1100,"dk":{"legs":2,"of":2,"naive_price":1450,"likely_price":1050,"stand_in":true},
          "games":[{"matchup":"A @ B","commence_time":"2026-10-15T23:30:00Z","legs":[
            {"label":"B to win","price":-105,"link":"https://sportsbook.fanduel.com/addToBetslip?marketId=1.1&selectionId=11",
             "dk_link":"https://sportsbook.draftkings.com/?outcomes=0ML1_3","dk_price":-110}]},
           {"matchup":"C @ D","commence_time":"2026-10-15T23:30:00Z","legs":[
            {"label":"Over 2.5 goals","price":-168,"link":"https://sportsbook.fanduel.com/addToBetslip?marketId=1.2&selectionId=22",
             "dk_link":"https://sportsbook.draftkings.com/?outcomes=0QL2_1"}]}],
          "legs":[{"label":"B to win","price":-105},{"label":"Over 2.5 goals","price":-168}]}}
        """#
        let t = try Models.decoder.decode(Ticket.self, from: Data(json.utf8))
        XCTAssertEqual(t.naivePrice, 1500)
        XCTAssertEqual(t.body.likelyPrice, 1100)
        XCTAssertEqual(t.body.dk?.standIn, true)
        let legs = SlipBooks.legs(t)
        XCTAssertEqual(legs.map(\.label), ["B to win", "Over 2.5 goals"])        // the per-game legs, once
        XCTAssertEqual(Build.link(book: .draftkings, legs.map(\.dkLink)), "https://sportsbook.draftkings.com/?outcomes=0ML1_3%2B0QL2_1")
        let fd = try XCTUnwrap(Build.link(book: .fanduel, legs.map(\.link)))
        XCTAssertTrue(fd.hasPrefix("https://ny.sportsbook.fanduel.com/addToBetslip?") && fd.contains("11") && fd.contains("22"))
        // a parlay opens through the web app's hand-off page with each leg as m/s (no brackets for iOS to encode)
        let open = try XCTUnwrap(FanDuel.links(fd))
        XCTAssertEqual(open.app.absoluteString, "https://betlab.example.app/fd.html?m=1.1&s=11&m=1.2&s=22")
        // a single bet still goes straight to FanDuel's app
        XCTAssertEqual(FanDuel.links("https://sportsbook.fanduel.com/addToBetslip?marketId=1.1&selectionId=11")?.app.absoluteString,
                       "fanduelsportsbook://ny.sportsbook.fanduel.com/addToBetslip?marketId=1.1&selectionId=11")
        XCTAssertEqual(SlipBooks.line("DraftKings", naive: 1450, likely: 1050, standIn: true), "DraftKings legs +1450 · likely +1050 (FanDuel's pattern)")
        XCTAssertEqual(SlipBooks.line("FanDuel", naive: nil, likely: nil, standIn: false), "")
    }
}

final class DateTests: XCTestCase {
    func testEspnStartsWithoutSecondsParse() {      // Oct 24: the scoreboard pill was empty before kickoff
        XCTAssertEqual(Models.date("2026-10-25T13:30Z"), Models.date("2026-10-25T13:30:00Z"))
        XCTAssertNotNil(Models.date("2026-10-25T13:30:00.000Z"))
    }
}
