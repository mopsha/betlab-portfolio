import XCTest
@testable import BetLab

/// web/tests/bets.test.mjs, case for case: My bets must count exactly as the web app does.
final class MyBetsTests: XCTestCase {
    func bet(_ f: (inout MyBet) -> Void = { _ in }) -> MyBet {
        var b = MyBet(betId: UUID().uuidString, kind: "pick", mode: "real", price: 120, stake: 2, placedAt: "2026-10-14T16:00:00Z",
                      pickStatus: "won", profitFlat: 1.2, clv: 0.1, league: "nfl", market: "spreads", pickKind: "game",
                      loggedPrice: 120, closePush: 0)
        f(&b)
        return b
    }
    func near(_ a: Double?, _ e: Double, file: StaticString = #filePath, line: UInt = #line) {
        guard let a else { return XCTFail("nil != \(e)", file: file, line: line) }
        XCTAssertEqual(a, e, accuracy: 1e-10, file: file, line: line)
    }

    /// tests/fixtures/promo_profit.json: the profit every port computes (web bets.test.mjs, Python test_promo_profit).
    func testPromoProfitSharedFixture() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/promo_profit.json")
        let fix = try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
        var bets: [MyBet] = []
        for c in fix["cases"].array {
            let f = c["bet"]
            let b = bet {
                $0.kind = "custom"; $0.pickStatus = nil; $0.profitFlat = nil
                $0.stake = f["stake"].double; $0.price = f["price"].double; $0.ticketStatus = f["ticket_status"].string
                $0.profit1u = f["profit_1u"].double; $0.bonus = f["bonus"].bool; $0.protect = f["protect"].bool
                $0.boost = f["boost"].double; $0.boostCap = f["boost_cap"].double; $0.cashout = f["cashout"].double
            }
            bets.append(b)
            XCTAssertEqual(BetMath.profit(b) ?? .nan, c["profit"].double!, accuracy: 1e-10, c["name"].string ?? "")
        }
        // a boosted bonus bet counts once, as a bonus (Oct 30)
        let boost = BetMath.boostSummary(bets)
        XCTAssertEqual(boost.bets, 4)
        XCTAssertEqual(BetMath.bonusSummary(bets).bets, 5)
        near(boost.fromBoost, 1 + 0.5 + 0.3)
    }

    func testWinningsUseYourPriceAndStake() {
        near(BetMath.profit(bet { $0.price = 150; $0.stake = 3 }), 4.5)
        near(BetMath.profit(bet { $0.price = -125; $0.stake = 3 }), 2.4)
    }

    func testMissingPriceScalesFallbackProfit() {
        near(BetMath.profit(bet { $0.price = nil }), 2.4)
        near(BetMath.profit(bet { $0.price = nil; $0.kind = "custom"; $0.profitFlat = nil; $0.profit1u = 1.5 }), 3)
        near(BetMath.profit(bet { $0.price = nil; $0.stake = 3 }), 3.6)
        XCTAssertNil(BetMath.profit(bet { $0.price = nil; $0.profitFlat = nil }))
    }

    func testNovigCountsAVoidLegAtItsFairValue() {
        let legs = { (r: [String]) in r.enumerated().map { LegResult(leg: "L\($0.offset)", result: $0.element, p: $0.element == "void" ? 0.4 : nil) } }
        near(BetMath.profit(bet { $0.book = "Novig"; $0.price = 100; $0.legResults = legs(["won", "void"]) }), 2 * (2 * 0.4 - 1))
        near(BetMath.profit(bet { $0.book = "Novig"; $0.price = 500; $0.pickStatus = "void"; $0.legResults = legs(["void", "void"]) }), 2 * (6 * 0.16 - 1))
        near(BetMath.profit(bet { $0.book = "FanDuel"; $0.price = 100; $0.legResults = legs(["won", "void"]) }), 0)
        near(BetMath.profit(bet { $0.book = "Novig"; $0.price = 150; $0.stake = 3 }), 4.5)
    }

    func testLossesPushesVoidsOpenAndPaper() {
        XCTAssertEqual(BetMath.profit(bet { $0.pickStatus = "lost" }), -2)
        XCTAssertEqual(BetMath.profit(bet { $0.pickStatus = "push" }), 0)
        XCTAssertEqual(BetMath.profit(bet { $0.pickStatus = "void" }), 0)
        XCTAssertNil(BetMath.profit(bet { $0.pickStatus = "open" }))
        near(BetMath.profit(bet { $0.mode = "paper"; $0.stake = nil; $0.price = nil }), 1.2)
    }

    func testPersonalPriceChangesClvAndBeatClose() {
        let worse = bet { $0.price = -125 }
        near(BetMath.personalClv(worse), -0.1)
        near(BetMath.personalClv(bet { $0.price = 150 }), 0.25)
        let r = BetMath.record([worse, bet { $0.price = 150 }])
        XCTAssertEqual(r.total.clvN, 2)
        XCTAssertEqual(r.total.beat, 1)
        near(r.total.clvSum, 0.15)
    }

    func testFootballClvKeepsClosingPushes() {
        near(BetMath.personalClv(bet { $0.clv = 0.09; $0.closePush = 0.1; $0.price = 150 }), 0.225)
    }

    func testPropsUseTheRawClose() {
        near(BetMath.personalClv(bet { $0.pickKind = "prop"; $0.clv = 0.3; $0.clvRaw = 0.1; $0.price = 150 }), 0.25)
        XCTAssertNil(BetMath.personalClv(bet { $0.pickKind = "prop"; $0.clv = 0.3; $0.clvRaw = nil }))
        XCTAssertNil(BetMath.personalClv(bet { $0.pickKind = nil; $0.market = "player_receptions"; $0.clv = 0.3; $0.clvRaw = nil }))
    }

    func testMissingClosingDataIsExcluded() {
        XCTAssertNil(BetMath.personalClv(bet { $0.closePush = nil; $0.price = 150 }))
        XCTAssertNil(BetMath.personalClv(bet { $0.loggedPrice = nil }))
        XCTAssertNil(BetMath.personalClv(bet { $0.clv = nil }))
        near(BetMath.personalClv(bet { $0.closePush = nil }), 0.1)
        near(BetMath.personalClv(bet { $0.price = nil; $0.closePush = nil }), 0.1)
        XCTAssertEqual(BetMath.record([bet { $0.price = 150; $0.closePush = nil }]).total.clvN, 0)
    }

    func testParlaysAndBadDataHaveNoClv() {
        XCTAssertNil(BetMath.personalClv(bet { $0.kind = "parlay" }))
        XCTAssertNil(BetMath.personalClv(bet { $0.kind = "custom" }))
        XCTAssertNil(BetMath.personalClv(bet { $0.price = 0 }))
        XCTAssertNil(BetMath.personalClv(bet { $0.price = 150; $0.closePush = 2 }))
    }

    func testVoidLegPaysWithoutThatLeg() {
        let legs = [LegResult(leg: "A", result: "won"), LegResult(leg: "B", result: "void", p: 0.5), LegResult(leg: "C", result: "won")]
        near(BetMath.profit(bet { $0.kind = "parlay"; $0.pickStatus = nil; $0.ticketStatus = "won"; $0.price = 500; $0.stake = 1; $0.legResults = legs }),
             6 * 0.5 - 1)
        let short = bet { $0.kind = "parlay"; $0.pickStatus = nil; $0.ticketStatus = "won"; $0.price = -150; $0.stake = 1
            $0.legResults = [LegResult(leg: "A", result: "won"), LegResult(leg: "B", result: "void", p: 0.3)] }
        near(BetMath.profit(short), 0)
    }

    func testFunBucketAndDailyCapCountUnits() {
        let now = Models.date("2026-10-20T16:00:00Z")!
        let parlays = [MyBet(kind: "parlay", mode: "real", stake: 0.5, placedAt: "2026-10-19T16:00:00Z"),
                       MyBet(kind: "custom", mode: "paper", stake: nil, placedAt: "2026-10-02T16:00:00Z"),
                       MyBet(kind: "parlay", mode: "real", stake: 2, placedAt: "2026-09-30T16:00:00Z"),
                       MyBet(kind: "pick", mode: "real", stake: 1, placedAt: "2026-10-19T16:00:00Z")]
        near(BetMath.bucketUsed(parlays, now: now), 1.5)
        let day = [bet { $0.pickStatus = "open"; $0.stake = 2; $0.placedAt = "2026-10-20T15:00:00Z" },
                   bet { $0.pickStatus = "open"; $0.stake = nil; $0.placedAt = "2026-10-20T15:00:00Z" },
                   bet { $0.pickStatus = "open"; $0.mode = "paper"; $0.stake = 1; $0.placedAt = "2026-10-20T15:00:00Z" }]
        near(BetMath.atRisk(day, day: "2026-10-20"), 3)
    }

    func testRecordByBook() {
        let rows = [bet { $0.price = 150; $0.book = "DraftKings" }, bet { $0.price = 120; $0.book = "FanDuel" }, bet { $0.price = 110 }]
        let r = BetMath.record(rows, by: BetMath.book)
        XCTAssertEqual(Dictionary(uniqueKeysWithValues: r.lines.map { ($0.group, $0.bets) }), ["FanDuel": 2, "DraftKings": 1])
        XCTAssertEqual(r.total.bets, 3)
    }

    func testNovigBetsGetTheirOwnRowAndGradeLikeAnyCustomBet() {     // the Novig sync's bets (Oct 23)
        let nv = bet { $0.kind = "custom"; $0.book = "Novig"; $0.price = 105; $0.stake = 0.5; $0.pickStatus = nil
                       $0.ticketStatus = "won"; $0.sgpId = "novig-abc"; $0.label = "Rangers ML · Novig $2.50 (auto)" }
        XCTAssertEqual(BetMath.profit(nv)!, 0.525, accuracy: 1e-10)
        let r = BetMath.record([nv, bet { $0.book = "FanDuel" }], by: BetMath.book)
        XCTAssertEqual(Dictionary(uniqueKeysWithValues: r.lines.map { ($0.group, $0.bets) }), ["FanDuel": 1, "Novig": 1])
    }

    func testFromOct18TheRecordCountsRealBetsOnlyFromZero() {
        let paperWin = MyBet(betId: "1", kind: "pick", mode: "paper", price: 100, placedAt: "2026-10-12T15:00:00Z", pickStatus: "won")
        let paperParlay = MyBet(betId: "2", kind: "parlay", mode: "paper", price: 500, stake: 2, placedAt: "2026-10-12T15:00:00Z", ticketStatus: "lost")
        var r = BetMath.recordBets([paperWin, paperParlay], realMode: false)               // before real money: everything counts
        XCTAssertFalse(r.useReal)
        XCTAssertEqual(BetMath.record(r.counted).total.won, 1)
        r = BetMath.recordBets([paperWin, paperParlay], realMode: true)                     // Oct 18, nothing real yet: a clear record
        XCTAssertTrue(r.useReal)
        XCTAssertEqual(BetMath.record(r.counted).total.bets, 0)
        XCTAssertEqual(BetMath.bucketUsed(r.counted, now: Models.date("2026-10-18T16:00:00Z")!), 0)
        XCTAssertEqual(r.paper.count, 2)
        let realLoss = MyBet(betId: "3", kind: "pick", mode: "real", price: -110, stake: 1, placedAt: "2026-10-18T16:00:00Z", pickStatus: "lost")
        r = BetMath.recordBets([paperWin, paperParlay, realLoss], realMode: true)            // the first real bet counts alone
        XCTAssertEqual([BetMath.record(r.counted).total.won, BetMath.record(r.counted).total.lost], [0, 1])
    }

    func testDecodesTheMyBetsView() throws {
        let json = #"""
        [{"bet_id":"b1","kind":"parlay","pick_id":null,"sgp_id":"s1","mode":"paper","price":null,"stake":null,
          "placed_at":"2026-10-12T16:00:00.123+00:00","ticket_status":"won","profit_1u":4.2,"ticket_kind":"sgp_plus",
          "leg_results":[{"leg":"A","result":"won","value":3},{"leg":"B","result":"void","p":0.4,"value":"DNP"}],
          "extra_column":true}]
        """#
        let b = try Models.decoder.decode([MyBet].self, from: Data(json.utf8))[0]
        XCTAssertEqual(b.profit1u, 4.2)
        XCTAssertEqual(b.legResults?[1].p, 0.4)
        XCTAssertNil(b.legResults?[1].value)
        XCTAssertEqual(BetMath.group(b), "SGP+ tickets")
        near(BetMath.profit(b), 4.2)
    }

    // Oct 19: promo credits (web/tests/bets.test.mjs's three bonus cases)
    func testBonusBetPaysProfitOnlyAndALossCostsNothing() {
        let b = { (status: String) in self.bet { $0.bonus = true; $0.kind = "custom"; $0.pickStatus = nil; $0.ticketStatus = status; $0.stake = 2; $0.price = 400 } }
        near(BetMath.profit(b("won")), 8)                              // 2u at +400: the 8u profit, no stake back
        XCTAssertEqual(BetMath.profit(b("lost")), 0)
        XCTAssertEqual(BetMath.profit(b("void")), 0)
        near(BetMath.profit(bet { $0.pickStatus = "lost"; $0.stake = 2 }), -2)   // cash bets unchanged
    }

    func testBonusBetsStayOutOfStakedCapAndBucketButWinningsCount() {
        let now = ISO8601DateFormatter().string(from: Date())
        let cash = bet { $0.kind = "custom"; $0.pickStatus = nil; $0.ticketStatus = "lost"; $0.stake = 1; $0.price = 300; $0.placedAt = now }
        let won = bet { $0.kind = "custom"; $0.pickStatus = nil; $0.ticketStatus = "won"; $0.stake = 2; $0.price = 400; $0.bonus = true; $0.placedAt = now }
        let total = BetMath.record([cash, won]).total
        near(total.staked, 1)
        near(total.units, 7)                                            // -1 cash, +8 from the bonus win
        let open = { (bonus: Bool) in self.bet { $0.kind = "custom"; $0.pickStatus = nil; $0.ticketStatus = nil; $0.stake = 3; $0.price = 300
                                                 $0.placedAt = now; $0.ticketCommenceTime = now; $0.bonus = bonus } }
        near(BetMath.atRisk([open(false), open(true)], day: BetMath.etDay(Date())), 3)
        near(BetMath.bucketUsed([open(false), open(true)]), 3)
    }

    func testBonusLineFaceConvertedAndRate() {
        let b = { (status: String?, stake: Double) in self.bet { $0.bonus = true; $0.kind = "custom"; $0.pickStatus = nil; $0.price = 400
                                                                 $0.ticketStatus = status; $0.stake = stake } }
        let s = BetMath.bonusSummary([b("won", 1), b("lost", 3), b("void", 5), b(nil, 2), bet()])
        XCTAssertEqual([s.bets, s.settled, s.won], [4, 2, 1])
        near(s.face, 4)
        near(s.converted, 4)
        near(s.rate, 1)
        XCTAssertNil(BetMath.bonusSummary([bet()]).rate)
    }

    func testEditSavesTheBonusFlag() {
        guard case .success(let on) = Marking.edit(stake: "1.94", price: "+150", book: "FanDuel", bonus: true) else { return XCTFail() }
        XCTAssertEqual(on["bonus"] as? Bool, true)
        guard case .success(let none) = Marking.edit(stake: "1", price: "", book: "FanDuel") else { return XCTFail() }
        XCTAssertFalse(none.keys.contains("bonus"))
    }

    func testACashOutSettlesTheBetAtWhatTheBookPaidBack() {      // Oct 22
        let cashed = bet { $0.kind = "parlay"; $0.stake = 1; $0.price = 1398; $0.pickStatus = nil; $0.ticketStatus = "lost"; $0.cashout = 1.058 }
        XCTAssertEqual(BetMath.status(cashed), "cashout")
        XCTAssertEqual(BetMath.statusName("cashout"), "cashed out")
        near(BetMath.profit(cashed), 0.058)                                          // $5.29 back on $5
        near(BetMath.profit(bet { $0 = cashed; $0.ticketStatus = nil }), 0.058)      // before the ticket grades too
        near(BetMath.profit(bet { $0 = cashed; $0.bonus = true }), 1.058)            // a bonus bet's cash-out is all profit
    }

    func testAProfitBoostMultipliesAWinsProfit() {      // Oct 22: the price stays the book's own
        let kmet = bet { $0.kind = "custom"; $0.stake = 2; $0.price = 178; $0.pickStatus = nil; $0.ticketStatus = "won"; $0.boost = 100 }
        near(BetMath.profit(kmet), 2 * 1.78 * 2)                                     // +7.12u: $10 paid $45.60
        near(BetMath.profit(bet { $0 = kmet; $0.ticketStatus = "lost" }), -2)
        let s = BetMath.boostSummary([kmet, bet { $0.kind = "custom"; $0.stake = 1; $0.price = 325; $0.pickStatus = nil
                                                  $0.ticketStatus = "lost"; $0.boost = 30 }])
        near(s.units, 7.12 - 1); near(s.fromBoost, 3.56); XCTAssertEqual(s.won, 1); near(s.staked, 3)
    }

    func testEditSavesABoostOrClearsIt() {
        guard case .success(let b) = Marking.edit(stake: "1", price: "", book: "FanDuel", boost: "50%") else { return XCTFail() }
        XCTAssertEqual(b["boost"] as? Double, 50)
        guard case .success(let blank) = Marking.edit(stake: "1", price: "", book: "FanDuel", boost: "") else { return XCTFail() }
        XCTAssertNil(blank["boost"]!)
        guard case .failure(let e) = Marking.edit(stake: "1", price: "", book: "FanDuel", boost: "0") else { return XCTFail() }
        XCTAssertEqual(e.message, "Enter the profit boost in percent, like 50.")
    }

    func testAMarkFromPromoModeSavesItsBoostOrBonus() {
        let r = Marking.row(MarkInput(kind: "custom", sgpId: "x", boost: 100, bonus: false), real: true)
        XCTAssertEqual(r["boost"] as? Double, 100)
        XCTAssertEqual(r["bonus"] as? Bool, false)
        XCTAssertFalse(Marking.row(MarkInput(kind: "pick", pickId: "p"), real: true).keys.contains("boost"))
    }

    func testEditSavesACashOutOrClearsIt() {
        guard case .success(let c) = Marking.edit(stake: "1", price: "", book: "FanDuel", cashout: "1.0584") else { return XCTFail() }
        XCTAssertEqual(c["cashout"] as? Double, 1.058)
        guard case .success(let blank) = Marking.edit(stake: "1", price: "", book: "FanDuel", cashout: " ") else { return XCTFail() }
        XCTAssertTrue(blank.keys.contains("cashout"))
        XCTAssertNil(blank["cashout"]!)
        guard case .failure(let e) = Marking.edit(stake: "1", price: "", book: "FanDuel", cashout: "abc") else { return XCTFail() }
        XCTAssertEqual(e.message, "Enter what the cash-out paid back in units, like 1.06.")
        guard case .success(let none) = Marking.edit(stake: "1", price: "", book: "FanDuel") else { return XCTFail() }
        XCTAssertFalse(none.keys.contains("cashout"))
    }
    /// Mike, Oct 26: a push counts as a loss in the record, a cash-out as its bet settled (web bets.test.mjs, same bets).
    /// Oct 26 (web bets.test.mjs): Bet Protect+ takes 3% of the stake off every settled bet but a void.
    func testBetProtectTakesItsFeeOffEverySettledBetButAVoid() {
        func c(_ status: String, bonus: Bool = false, protect: Bool = true) -> MyBet {
            bet { $0.kind = "custom"; $0.pickStatus = nil; $0.ticketStatus = status; $0.price = 911; $0.stake = 2; $0.bonus = bonus; $0.protect = protect }
        }
        XCTAssertEqual(BetMath.profit(c("won", bonus: true))!, 2 * 9.11 - 0.06, accuracy: 1e-9)
        XCTAssertEqual(BetMath.profit(c("lost"))!, -2.06, accuracy: 1e-9)
        XCTAssertEqual(BetMath.profit(c("lost", bonus: true))!, -0.06, accuracy: 1e-9)
        XCTAssertEqual(BetMath.profit(c("void"))!, 0, accuracy: 1e-9)
        XCTAssertEqual(BetMath.profit(c("won", protect: false))!, 18.22, accuracy: 1e-9)
    }

    func testTheRecordCountsAPushAsALossAndACashOutAsItsBetSettled() {
        func c(_ status: String, cashout: Double? = nil) -> MyBet {
            bet { $0.kind = "custom"; $0.pickStatus = nil; $0.ticketStatus = status; $0.price = 200; $0.stake = 1; $0.cashout = cashout }
        }
        let r = BetMath.record([c("won"), c("push"), c("lost", cashout: 1.5), c("open", cashout: 0.4), c("void")]).total
        XCTAssertEqual([r.bets, r.won, r.lost, r.push], [5, 1, 2, 1])
        XCTAssertEqual(r.units, 2 + 0 + 0.5 - 0.6 + 0, accuracy: 1e-9)
    }
}

final class BetStartTests: XCTestCase {
    /// Web tests/bets.test.mjs: a bet without a start of its own files by its first game's kickoff (Oct 25).
    func testAHandEnteredBetFilesByItsFirstKickoff() throws {
        let games = try JSON.plainDecoder.decode(JSON.self, from: Data(#"[{"matchup":"GB @ DET","gameRef":"2026_07_GB_DET","legs":[]},{"matchup":"x","gameRef":"nba|CHI|WSH|2026-10-24T23:10:00+00:00","legs":[]}]"#.utf8))
        var b = MyBet(betId: "x", kind: "custom", placedAt: "2026-10-24T12:00:00Z")
        b.games = games
        let starts = ["nfl:2026_07_GB_DET": "2026-10-25T20:25:00+00:00"]
        XCTAssertEqual(BetMath.gameStart(b, starts: starts), "2026-10-24T23:10:00.000Z")
        b.gameStart = BetMath.gameStart(b, starts: starts)
        XCTAssertEqual(BetMath.start(b), "2026-10-24T23:10:00.000Z")
        XCTAssertEqual(BetMath.refGameId("2026_07_PIT_NO"), "nfl:2026_07_PIT_NO")
        XCTAssertNil(BetMath.refGameId("ufc:600:1"))
    }

}
