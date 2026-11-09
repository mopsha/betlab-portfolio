import XCTest
@testable import BetLab

/// Build must price, grade and save exactly as web/lib/builder.ts does.
final class BuildTests: XCTestCase {
    // the host app signs in and loads the account's books off (BooksOff.current); every case here starts with all three on
    override func setUp() { super.setUp(); BooksOff.current = [] }

    func testSaveIdMatchesTheWebApp() {
        // computed with web/lib/builder.ts buildId under Node (Oct 14)
        let s1 = ["Josh Allen Over 1.5 TDs", "Bills -3.5", "Stefon Diggs Over 64.5 receiving yds"].map { SlipLeg(eventId: "e", label: $0) }
        XCTAssertEqual(Build.id(s1), "custom-f99ddc4d")
        XCTAssertEqual(Build.id([SlipLeg(eventId: "e", label: "Brunson Over 25.5 pts")], book: .draftkings), "custom-30328f27~dk")
        XCTAssertEqual(Build.id(["Bodø/Glimt to win", "Draw"].map { SlipLeg(eventId: "e", label: $0) }), "custom-3ea81a0d")
        // with the slip's game day (Nov 9): the same legs another day are another slip (web builder.test.mjs)
        XCTAssertEqual(Build.id([SlipLeg(eventId: "e", label: "Brunson Over 25.5 pts")], day: "2026-11-09"), "custom-276a704")
    }

    /// 16 draws as 2 bytes: A hits in draws 0-11, B in 4-15, C is "not A".
    func pack(pA: Double = 0.75, pB: Double = 0.75, priceA: Double = -300, priceB: Double = -300) -> Pack {
        let a = Data([0xFF, 0x0F]).base64EncodedString(), b = Data([0xF0, 0xFF]).base64EncodedString()
        return Pack(eventId: "g1", matchup: "A @ B", commenceTime: "2026-10-18T17:00:00Z", gameRef: nil, sport: "nfl", draws: 16, legs: [
            "A": PackLeg(label: "A", player: "P1", side: "over", price: priceA, p: pA, pPack: 0.75, bits: a, link: "https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=11"),
            "B": PackLeg(label: "B", player: "P2", side: "over", price: priceB, p: pB, pPack: 0.75, bits: b, link: "https://sportsbook.fanduel.com/addToBetslip?marketId=2&selectionId=22"),
            "C": PackLeg(label: "C", player: "P3", side: "over", price: 200, p: 0.25, pPack: 0.25, not: "A")])
    }

    func testJointCountsDrawsAndScalesByShrink() {
        let pr = Pricer(["g1": pack()])
        XCTAssertEqual(pr.joint("g1", ["A", "B"])!, 0.5, accuracy: 1e-12)          // draws 4-11
        XCTAssertEqual(pr.joint("g1", ["A", "C"])!, 0, accuracy: 1e-12)            // C is not-A
        let shrunk = Pricer(["g1": pack(pA: 0.6)])
        XCTAssertEqual(shrunk.joint("g1", ["A", "B"])!, 0.5 * 0.6 / 0.75, accuracy: 1e-12)
    }

    func testGradeWithATypedPrice() {
        let pr = Pricer(["g1": pack()])
        let slip = [SlipLeg(eventId: "g1", label: "A"), SlipLeg(eventId: "g1", label: "B")]
        // p = 0.5 (fair +100); typed +100 pays 100% of fair vs the 78% band: rel 1.28 -> A+, then +1 for p >= 25% (already top)
        let e = Build.evaluate(pr, slip, priceText: "+100")!
        XCTAssertEqual(e.p, 0.5, accuracy: 1e-12)
        XCTAssertEqual(e.fair, 100, accuracy: 1e-9)
        XCTAssertEqual(e.grade, "A+")
        XCTAssertFalse(e.provisional)
        XCTAssertEqual(e.lift, 0.5 / 0.5625, accuracy: 1e-12)
        XCTAssertEqual(e.fights.count, 1)                                         // 0.89x together
        // no price typed: provisional from the legs' own prices (0.75 * 1.333 = 1.0 of fair -> A−), +1 likely, −1 the fight
        let p = Build.evaluate(pr, slip, priceText: "")!
        XCTAssertTrue(p.provisional)
        XCTAssertEqual(p.grade, "A\u{2212}")
    }

    func testRulesFlagLegsOutsideMikesRange() {
        let pr = Pricer(["g1": pack(pA: 0.9, pB: 0.5)])
        let e = Build.evaluate(pr, [SlipLeg(eventId: "g1", label: "A"), SlipLeg(eventId: "g1", label: "B")], priceText: "")!
        XCTAssertEqual(e.rules.count, 2)
    }

    func testGameLinesWithNoPlayerAreNotTheSamePlayer() {
        var pk = pack()
        for k in ["A", "B"] { pk = Pack(eventId: pk.eventId, matchup: pk.matchup, commenceTime: pk.commenceTime, gameRef: nil, sport: pk.sport,
                                         draws: pk.draws, legs: pk.legs.mapValues { var l = $0; l.player = ""; return l }) ; _ = k }
        let e = Build.evaluate(Pricer(["g1": pk]), [SlipLeg(eventId: "g1", label: "A"), SlipLeg(eventId: "g1", label: "B")], priceText: "")!
        XCTAssertFalse(e.rules.contains { $0.hasPrefix("two legs on") })
    }

    func testDraftKingsMarksLegsItDoesNotPost() {
        let pr = Pricer(["g1": pack()], book: .draftkings)
        XCTAssertTrue(pr.leg("g1", "A")!.unavailable)
        XCTAssertNil(Build.evaluate(pr, [SlipLeg(eventId: "g1", label: "A")], priceText: ""))
    }

    func testLinksCombineLegs() {
        XCTAssertEqual(Build.link(book: .fanduel, ["https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=11",
                                                   "https://sportsbook.fanduel.com/addToBetslip?marketId=2&selectionId=22"]),
                       "https://ny.sportsbook.fanduel.com/addToBetslip?marketId[0]=1&selectionId[0]=11&marketId[1]=2&selectionId[1]=22")
        XCTAssertEqual(Build.link(book: .draftkings, ["https://sportsbook.draftkings.com/?outcomes=0ML1_3", "https://sportsbook.draftkings.com/?outcomes=0ML2_1"]),
                       "https://sportsbook.draftkings.com/?outcomes=0ML1_3%2B0ML2_1")
        XCTAssertNil(Build.link(book: .draftkings, ["https://sportsbook.draftkings.com/?outcomes=0ML1_3", nil]))
        // one linked leg of a parlay would open as a single bet (Nov 5)
        XCTAssertNil(Build.link(book: .fanduel, [nil, "https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=11", nil]))
        XCTAssertEqual(Build.link(book: .fanduel, ["https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=11"]),
                       "https://ny.sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=11")
    }

    func testRecordByGrade() {
        let rows = [Quote(sgpId: "1", price: 300, pFair: 0.25, grade: "A", status: "won", profit1u: 3),
                    Quote(sgpId: "2", price: 300, pFair: 0.25, grade: "A", status: "lost", profit1u: -1),
                    Quote(sgpId: "3", price: 900, pFair: 0.1, grade: "C", status: "lost", profit1u: -1),
                    Quote(sgpId: "4", price: 900, pFair: 0.1, grade: "C", status: nil)]
        let r = Build.recordByGrade(rows)
        XCTAssertEqual(r.map(\.grade), ["A", "C"])
        XCTAssertEqual(r[0].units, 2)
        XCTAssertEqual(r[1].graded, 1)
    }

    // MARK: the leg board and the promo finder (every case of web/tests/builder.test.mjs)

    func leg(_ label: String, player: String? = "", team: String? = nil, stat: String, side: String, point: Double? = nil,
             price: Double = -110, p: Double = 0.5, bits: String? = nil) -> PackLeg {
        PackLeg(label: label, player: player, team: team, stat: stat, side: side, point: point, price: price, p: p, pPack: p, bits: bits)
    }

    func testGameLinesPutAwayDrawHomeInOneRowAndPairTotalsByNumber() {
        let legs = [
            leg("Juventus to win", team: "Juventus", stat: "moneyline", side: "yes"),
            leg("Draw", stat: "draw", side: "yes"),
            leg("Rennes to win", team: "Rennes", stat: "moneyline", side: "yes"),
            leg("Under 2.5 goals", stat: "goals", side: "under", point: 2.5),
            leg("Over 1.5 goals", stat: "goals", side: "over", point: 1.5),
            leg("Over 2.5 goals", stat: "goals", side: "over", point: 2.5),
        ]
        let t = Build.boardTabs(legs, matchup: "Rennes @ Juventus")[0]
        XCTAssertEqual(t.title, "Game lines")
        XCTAssertEqual(t.sections.map(\.title), ["Result", "Total goals"])
        // soccer reads home team first (Nov 5): Juventus (home), Draw, Rennes
        XCTAssertEqual(t.sections[0].rows[0].legs.map(\.label), ["Juventus to win", "Draw", "Rennes to win"])
        XCTAssertEqual(t.sections[1].rows.map { $0.legs.map(Build.shortLeg) }, [["Over 1.5"], ["Over 2.5", "Under 2.5"]])
    }

    func testASpreadRungPairsTheAwaySideWithTheHomeSidesOppositeNumber() {
        let legs = [
            leg("CBJ -1.5", team: "CBJ", stat: "puck line", side: "yes", point: -1.5),
            leg("CBJ +1.5", team: "CBJ", stat: "puck line", side: "yes", point: 1.5),
            leg("BUF -1.5", team: "BUF", stat: "puck line", side: "yes", point: -1.5),
            leg("BUF +1.5", team: "BUF", stat: "puck line", side: "yes", point: 1.5),
        ]
        let rows = Build.boardTabs(legs, matchup: "BUF @ CBJ")[0].sections[0].rows.map { $0.legs.map(\.label) }
        XCTAssertEqual(rows, [["BUF -1.5", "CBJ +1.5"], ["BUF +1.5", "CBJ -1.5"]])
    }

    func testPlayerPropsGetATabPerStatASectionPerPlayerAndShortButtons() {
        func p(_ label: String, _ player: String, _ stat: String, _ side: String, _ point: Double) -> PackLeg {
            leg(label, player: player, team: "PIT", stat: stat, side: side, point: point)
        }
        let legs = [
            p("DK Metcalf over 3.5 receptions", "DK Metcalf", "receptions", "over", 3.5),
            p("DK Metcalf under 3.5 receptions", "DK Metcalf", "receptions", "under", 3.5),
            p("Jaylen Warren anytime TD", "Jaylen Warren", "tds", "yes", 0.5),
        ]
        let tabs = Build.boardTabs(legs, matchup: "Pittsburgh Steelers @ Cleveland Browns")
        XCTAssertEqual(tabs.map(\.title), ["Receptions", "Touchdowns"])
        XCTAssertEqual(tabs[0].sections[0].title, "DK Metcalf")
        XCTAssertEqual(tabs[0].sections[0].rows[0].legs.map(Build.shortLeg), ["Over 3.5", "Under 3.5"])
        XCTAssertEqual(Build.shortLeg(tabs[1].sections[0].rows[0].legs[0]), "Anytime TD")
    }

    func testPromoValueBonusKeepsOnlyTheProfitBoostMultipliesIt() {
        XCTAssertEqual(Build.promoEv(0.25, 4, .bonus), 0.75)
        XCTAssertEqual(Build.promoEv(0.25, 4, .none), 0)
        XCTAssertEqual(Build.promoEv(0.25, 4, .boost(50)), 0.375, accuracy: 1e-12)
        // a $10 stake at +900 with a 100% boost would add $90; a $25 cap on extra winnings keeps $25 of it
        var capped = Promo.boost(100); capped.stake = 10; capped.maxExtra = 25
        XCTAssertEqual(Build.promoEv(0.1, 10, capped), 0.25, accuracy: 1e-12)
        XCTAssertEqual(Build.promoEv(0.1, 10, .boost(100)), 0.9, accuracy: 1e-12)
        XCTAssertEqual(Promo(stored: capped.stored), capped)
        XCTAssertTrue((0..<20).allSatisfy { _ in capped.stored == capped.stored })      // the finder's task id: stable
        XCTAssertEqual(Promo(stored: "boost:30"), .boost(30))
        XCTAssertEqual(Promo(stored: "bonus"), .bonus)
        XCTAssertEqual(Promo(stored: nil), .none)
    }

    /// 100 bytes of draws (800), each byte all-hit or all-miss.
    func bits(_ on: (Int) -> Bool) -> String { Data((0..<100).map { on($0) ? 255 : 0 }).base64EncodedString() }

    func testTheFinderSkipsTwoLegsOfOneMarketAndRanksByThePromosValue() {
        let legs = [
            leg("Over 1.5 goals", stat: "goals", side: "over", point: 1, price: -300, p: 0.8, bits: bits { $0 < 80 }),
            leg("Over 2.5 goals", stat: "goals", side: "over", point: 1, price: 100, p: 0.5, bits: bits { $0 < 50 }),
            leg("A to win", stat: "moneyline", side: "yes", point: 1, price: 110, p: 0.5, bits: bits { $0 % 2 == 0 }),
        ]
        let pr = Pricer(["g": Pack(eventId: "g", matchup: "A @ B", commenceTime: "", gameRef: nil, sport: "soccer", draws: 800,
                                   legs: Dictionary(uniqueKeysWithValues: legs.map { ($0.label, $0) }))])
        let out = Build.findPromo(pr, ["g"], .bonus)
        XCTAssertGreaterThanOrEqual(out.count, 1)
        XCTAssertTrue(out.allSatisfy { f in !(f.legs.contains { $0.label == "Over 1.5 goals" } && f.legs.contains { $0.label == "Over 2.5 goals" }) })
        XCTAssertEqual(out.map(\.ev), out.map(\.ev).sorted(by: >))
    }

    func testTheFinderSkipsFairPriceLegsAtFanDuelNestedLegsAndLongShots() {
        var fair = leg("Over 2.5 goals", stat: "goals", side: "over", point: 2.5, price: 100, p: 0.5, bits: bits { $0 < 50 })
        fair.source = "fair price (FanDuel has no soccer totals)"
        let legs = [
            fair,
            leg("A to win", team: "A", stat: "moneyline", side: "yes", price: 110, p: 0.5, bits: bits { $0 % 2 == 0 }),
            leg("A or draw", stat: "double chance", side: "yes", price: -300, p: 0.75, bits: bits { $0 % 2 == 0 || $0 % 4 == 1 }),
            leg("B to win", team: "B", stat: "moneyline2", side: "yes", price: 2000, p: 0.06, bits: bits { $0 % 4 == 3 && $0 < 24 }),
        ]
        let pr = Pricer(["g": Pack(eventId: "g", matchup: "A @ B", commenceTime: "", gameRef: nil, sport: "soccer", draws: 800,
                                   legs: Dictionary(uniqueKeysWithValues: legs.map { ($0.label, $0) }))])
        let out = Build.findPromo(pr, ["g"], .boost(50))
        XCTAssertFalse(out.contains { f in f.legs.contains { $0.label == "Over 2.5 goals" } })             // FanDuel doesn't post it
        XCTAssertFalse(out.contains { f in Set(f.legs.map(\.label)).isSuperset(of: ["A to win", "A or draw"]) })   // nested
        XCTAssertTrue(out.allSatisfy { 1 / $0.p - 1 <= 15 })                                             // +1500 or shorter
        // one leg per game is a plain parlay: it pays exactly the legs' product
        let two = Pack(eventId: "h", matchup: "C @ D", commenceTime: "", gameRef: nil, sport: "soccer", draws: 800,
                       legs: ["C to win": { var c = leg("C to win", team: "C", stat: "moneyline", side: "yes", price: 120, p: 0.45, bits: bits { $0 < 45 })
                                     c.source = "pinnacle"; return c }()])
        var g = pr.pack("g")!
        g = Pack(eventId: g.eventId, matchup: g.matchup, commenceTime: "", gameRef: nil, sport: g.sport, draws: g.draws,
                 legs: g.legs.mapValues { var l = $0; if l.source == nil { l.source = "pinnacle (market)" }; return l })
        let cross = Build.findPromo(Pricer(["g": g, "h": two]), ["g", "h"], .bonus).filter { $0.games == 2 }
        XCTAssertFalse(cross.isEmpty)
        for f in cross {
            let naive = f.legs.map { Odds.dec(pr.pack($0.eventId)?.legs[$0.label]?.price ?? 120) }.reduce(1, *)
            XCTAssertEqual(f.dec, naive, accuracy: 1e-9)
        }
    }

    /// Mike, Oct 26: a one-game boost with a leg minimum gave no options (web builder.test.mjs, same legs).
    func testAOneGameTokenWithALegMinimumGetsSlipsOfThatManyLegs() {
        func L(_ player: String, _ p: Double, _ price: Double, _ on: @escaping (Int) -> Bool) -> PackLeg {
            var l = leg("\(player) over 0.5 yds", player: player, stat: "yds", side: "over", point: 0.5, price: price, p: p, bits: bits(on))
            l.source = "pinnacle"; return l
        }
        let legs = [L("Long One", 0.1, 950) { $0 < 10 }, L("Long Two", 0.1, 950) { $0 >= 90 }, L("Long Three", 0.1, 950) { $0 % 10 == 3 },
                    L("Likely A", 0.6, -140) { $0 < 60 }, L("Likely B", 0.6, -140) { $0 >= 40 }, L("Likely C", 0.8, -380) { $0 % 5 != 0 },
                    L("Likely D", 0.5, 105) { $0 % 2 == 0 }]
        let pr = Pricer(["g": Pack(eventId: "g", matchup: "A @ B", commenceTime: "", gameRef: nil, sport: "nfl", draws: 800,
                                   legs: Dictionary(uniqueKeysWithValues: legs.map { ($0.label, $0) }))])
        for n in [3, 4] {
            var promo = Promo.boost(50); promo.minLegs = n
            let out = Build.findPromo(pr, ["g"], promo)
            XCTAssertFalse(out.isEmpty, "\(n)+ legs: some options")
            XCTAssertTrue(out.allSatisfy { $0.legs.count >= n && $0.legs.count <= n + 1 && 1 / $0.p <= 16 }, "\(n)+ legs, under the cap")
        }
    }

    func testATokensTermsFewestLegsAndShortestOdds() {
        var legs3 = Promo.boost(50); legs3.minLegs = 3
        XCTAssertFalse(Build.promoFits(legs3, legs: 2, dec: 5))
        XCTAssertTrue(Build.promoFits(legs3, legs: 3, dec: 5))
        var odds = Promo.bonus; odds.minOdds = 300
        XCTAssertFalse(Build.promoFits(odds, legs: 2, dec: 3.5))
        XCTAssertTrue(Build.promoFits(odds, legs: 2, dec: 4))
        // switching type keeps the terms; a boost keeps its cap only as a boost
        var b = Promo.boost(30); b.stake = 10; b.maxExtra = 25; b.minLegs = 3
        let bonus = b.switched(to: .bonus)
        XCTAssertEqual(bonus.stake, 10); XCTAssertEqual(bonus.minLegs, 3); XCTAssertNil(bonus.maxExtra)
        XCTAssertEqual(bonus.switched(to: .boost).stake, 10)
    }

    func moneyline(_ label: String, team: String, p: Double, price: Double, on: (Int) -> Bool, source: String?) -> PackLeg {
        var l = leg(label, team: team, stat: "moneyline", side: "yes", price: price, p: p, bits: bits(on)); l.source = source; return l
    }
    func game(_ id: String, _ legs: [PackLeg]) -> Pack {
        Pack(eventId: id, matchup: id, commenceTime: "", gameRef: nil, sport: "nba", draws: 800,
             legs: Dictionary(uniqueKeysWithValues: legs.map { ($0.label, $0) }))
    }

    func testSameGameSlipsRankAtACautiousQuotePlainParlaysAtTheirExactPrice() {
        let pr = Pricer([
            "g1": game("g1", [moneyline("A ML", team: "A", p: 0.5, price: 110, on: { $0 % 2 == 0 }, source: "pinnacle (market)")]),
            "g2": game("g2", [moneyline("C ML", team: "C", p: 0.5, price: 105, on: { $0 < 50 }, source: "pinnacle (market)")]),
            "g3": game("g3", [moneyline("E ML", team: "E", p: 0.5, price: 120, on: { $0 % 2 == 1 }, source: "fanatics, williamhill_us")]),
        ])
        let all = Build.findPromo(pr, ["g1", "g2", "g3"], .bonus)
        XCTAssertEqual(all.filter { $0.legs.count == 1 }.count, 2)        // each sharp-priced leg alone (Oct 22), never E
        let out = all.filter { $0.legs.count > 1 }
        XCTAssertEqual(out.count, 1)                                         // only the two sharp-priced legs make a plain parlay
        XCTAssertTrue(out[0].plain && out[0].dec == out[0].low)
        XCTAssertEqual(out[0].dec, 2.1 * 2.05, accuracy: 1e-9)
        XCTAssertEqual(out[0].ev, 0.25 * (2.1 * 2.05 - 1), accuracy: 1e-9)
        var three = Promo.bonus; three.minLegs = 3
        XCTAssertEqual(Build.findPromo(pr, ["g1", "g2", "g3"], three).count, 0)   // no 3-leg slip here
        let sgp = Pricer(["g": game("g", [moneyline("A ML", team: "A", p: 0.5, price: 110, on: { $0 % 2 == 0 }, source: nil),
                                          leg("Over 210.5", stat: "total", side: "over", point: 210.5, price: -110, p: 0.5, bits: bits { $0 < 50 })])])
        let s = Build.findPromo(sgp, ["g"], .bonus)[0]
        XCTAssertFalse(s.plain)
        XCTAssertLessThan(s.low, s.dec)
        XCTAssertEqual(s.low / s.dec, exp(-0.12), accuracy: 1e-9)
    }

    func testASinglePricedOffASharpBookIsAPromoPickAtItsExactPrice() {     // Oct 22: the Kmet boost
        var kmet = leg("Cole Kmet over 1.5 receptions", player: "Cole Kmet", stat: "receptions", side: "over", point: 1.5,
                       price: 178, p: 0.332, bits: bits { $0 < 33 })
        kmet.pPack = 0.33
        kmet.source = "pinnacle"
        let pr = Pricer(["g": Pack(eventId: "g", matchup: "NE @ CHI", commenceTime: "", gameRef: nil, sport: "nfl", draws: 800,
                                   legs: [kmet.label: kmet])])
        let out = Build.findPromo(pr, ["g"], .boost(100))
        guard let k = out.first else { return XCTFail() }
        XCTAssertTrue(k.legs.count == 1 && k.plain)
        XCTAssertEqual(k.dec, 2.78, accuracy: 1e-9)
        XCTAssertEqual(k.ev, 0.332 * (2.78 + 1.78) - 1, accuracy: 1e-9)          // +51%
        var two = Promo.boost(100); two.minLegs = 2
        XCTAssertEqual(Build.findPromo(pr, ["g"], two).count, 0)
    }

    func testTheTwoBookLockPaysTheSameEitherWay() {
        // a $10 bonus on +400 hedged at -450: $32.73 on the other side, $7.27 either way
        let v = Build.lockValue(5, 1 + 100 / 450, .bonus)!
        XCTAssertEqual(v.hedge * 10, 32.727, accuracy: 0.01)
        XCTAssertEqual(v.locked * 10, 7.273, accuracy: 0.01)
        XCTAssertEqual(4 - v.hedge, v.hedge * (100 / 450), accuracy: 1e-12)            // a wins = b wins
        // a 100% boost on a $10 cash stake at +150, hedged at -160: equal either way, and the cap shrinks it
        let dB = 1 + 100.0 / 160, b = Build.lockValue(2.5, dB, .boost(100))!
        XCTAssertEqual(3 - b.hedge, b.hedge * (dB - 1) - 1, accuracy: 1e-12)
        XCTAssertGreaterThan(b.locked, 0)
        var capped = Promo.boost(100); capped.stake = 10; capped.maxExtra = 5
        XCTAssertLessThan(Build.lockValue(2.5, dB, capped)!.locked, b.locked)
        XCTAssertNil(Build.lockValue(2, 2, .none))
    }

    func testLocksPairOppositesAtTheOtherBookAndSkipMismatchedRungs() {
        func L(_ label: String, stat: String, team: String? = nil, side: String, point: Double? = nil, p: Double = 0.5,
               price: Double, dk: Double, not: String? = nil, source: String? = nil) -> PackLeg {
            var l = PackLeg(label: label, team: team, stat: stat, side: side, point: point, price: price, p: p, pPack: p, source: source, bits: "", not: not)
            l.dkPrice = dk; return l
        }
        let legs = [
            L("ANA to win", stat: "moneyline", team: "ANA", side: "yes", p: 0.35, price: 164, dk: 175, not: "NJD to win"),
            L("NJD to win", stat: "moneyline", team: "NJD", side: "yes", p: 0.65, price: -200, dk: -190),
            L("Over 6.5 goals", stat: "goals", side: "over", point: 6.5, price: -110, dk: -105),
            L("Under 6.5 goals", stat: "goals", side: "under", point: 6.5, price: -110, dk: -115),
            // FanDuel's price here is a stand-in and DraftKings' rung doesn't match: never a lock
            L("NJD +1.5", stat: "puck line", team: "NJD", side: "yes", point: 1.5, p: 0.8, price: -410, dk: -148, source: "fair price (FanDuel's isn't in the feed)"),
            L("ANA -1.5", stat: "puck line", team: "ANA", side: "yes", point: -1.5, p: 0.2, price: 410, dk: 124, not: "NJD +1.5"),
        ]
        let pk = Pack(eventId: "g", matchup: "ANA @ NJD", commenceTime: "", gameRef: nil, sport: "nhl", draws: 8,
                      legs: Dictionary(uniqueKeysWithValues: legs.map { ($0.label, $0) }))
        XCTAssertEqual(Build.opposite(pk, pk.legs["NJD to win"]!)?.label, "ANA to win")
        XCTAssertEqual(Build.opposite(pk, pk.legs["Over 6.5 goals"]!)?.label, "Under 6.5 goals")
        let fd = Pricer(["g": pk], book: .fanduel), dk = Pricer(["g": pk], book: .draftkings)
        let out = Build.findLocks(fd, dk, ["g"], .bonus)
        XCTAssertEqual(out.first?.promoLeg, "ANA to win")                              // the longest real price locks the most
        XCTAssertEqual(out.first?.hedgeLeg, "NJD to win")
        XCTAssertEqual(out.first?.locked ?? 0, 1.64 * (1 - 1 / (1 + 100.0 / 190)), accuracy: 1e-9)
        XCTAssertTrue(out.allSatisfy { !$0.promoLeg.contains("1.5") && !$0.hedgeLeg.contains("1.5") })
        var three = Promo.boost(50); three.minLegs = 3
        XCTAssertEqual(Build.findLocks(fd, dk, ["g"], three).count, 0)                 // a 3-leg token can't lock a single
    }
}

extension BuildTests {
    func testMaxOddsKeepLongSlipsOut() {      // web: "its max odds keep long slips out" (Oct 24)
        var capped = Promo.boost(50); capped.maxOdds = 300
        XCTAssertTrue(Build.promoFits(capped, legs: 1, dec: 3.5))      // +250
        XCTAssertFalse(Build.promoFits(capped, legs: 1, dec: 5))       // +400 is over +300
        var minned = Promo.boost(50); minned.minOdds = -200
        XCTAssertFalse(Build.promoFits(minned, legs: 1, dec: 1.4))     // -250 is shorter than -200
        var t = Promo.boost(50); t.maxOdds = 200000
        XCTAssertEqual(t.switched(to: .bonus).maxOdds, 200000)
    }

    // MARK: the promo finder (tests/fixtures/promo_finder.json, slices.json, promos.json: web, Python and iPhone alike)

    private func fixture(_ name: String) throws -> JSON {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/\(name)")
        return try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
    }

    func testPromoFinderRanksAsTheWeb() throws {
        let fix = try fixture("promo_finder.json")
        func pickRows(_ rows: [JSON]) -> [PromoPick] { rows.map { k in
            let n = Int(k["legs"].double!), id = k["id"].string!, plain = k["plain"].bool!
            return PromoPick(legs: (0..<n).map { SlipLeg(eventId: "g-\(id)-\($0)", label: "\(id) leg \($0)") }, p: k["p"].double!,
                             games: plain ? n : 1, plain: plain, dec: k["dec"].double!, low: k["low"].double!, ev: 0)
        } }
        func lockRows(_ rows: [JSON]) -> [LockPick] { rows.map { l in
            let id = l["id"].string!
            return LockPick(eventId: "g-\(id)", promoLeg: "\(id) leg 0", hedgeLeg: "\(id) other", promoPrice: l["promoPrice"].double!,
                            hedgePrice: l["hedgePrice"].double!, promoLink: nil, hedgeLink: nil, locked: l["locked"].double!, hedge: l["hedge"].double!)
        } }
        for c in fix["cases"].array {
            // a case may bring its own candidates (a boost that only takes 3-leg parlays)
            let picks = pickRows(c["picks"].isNull ? fix["picks"].array : c["picks"].array)
            let locks = lockRows(c["locks"].isNull ? fix["locks"].array : c["locks"].array)
            let pj = c["promo"]
            var promo = pj["kind"].string == "boost" ? Promo.boost(pj["pct"].double!) : Promo.bonus
            promo.stake = pj["stake"].double; promo.maxExtra = pj["maxExtra"].double
            let out = PromoFinder.rank(picks, locks, promo, PromoFinder.Mode(rawValue: c["mode"].string!)!)
            let ids = out.map { String($0.legs[0].label.split(separator: " ")[0]) }
            XCTAssertEqual(ids, c["order"].array.compactMap(\.string), c["mode"].string ?? "")
            for (id, v) in c["values"].object { XCTAssertEqual(out.first { $0.legs[0].label.hasPrefix(id + " ") }!.value, v.double!, accuracy: 1e-9, id) }
            for (id, v) in c["adds"].object { XCTAssertEqual(out.first { $0.legs[0].label.hasPrefix(id + " ") }!.boostAdds, v.double!, accuracy: 1e-9, id) }
            for (id, t) in c["text"].object { XCTAssertEqual(out.first { $0.legs[0].label.hasPrefix(id + " ") }!.text, t.string!) }
        }
    }

    func testPromoFinderKeepsItsListVaried() throws {
        for c in try fixture("promo_finder.json")["variety"]["cases"].array {
            let rows = c["picks"].array
            let picks = rows.map { k in
                let ls = k["labels"].array.compactMap(\.string)
                return PromoPick(legs: ls.map { SlipLeg(eventId: "g", label: $0) }, p: k["p"].double!, games: ls.count,
                                 plain: k["plain"].bool!, dec: k["dec"].double!, low: k["low"].double!, ev: 0)
            }
            var promo = Promo.bonus
            promo.stake = c["promo"]["stake"].double
            let out = PromoFinder.rank(picks, [], promo, PromoFinder.Mode(rawValue: c["mode"].string!)!,
                                       top: Int(c["top"].double!))
            let ids = out.map { r in rows.first { $0["labels"].array.compactMap(\.string) == r.legs.map(\.label) }!["id"].string! }
            XCTAssertEqual(ids, c["order"].array.compactMap(\.string))
        }
    }

    func testSlicesMatchTheWorker() throws {
        for c in try fixture("slices.json")["cases"].array {
            let a = c.array.compactMap(\.string)
            let got = Slices.sliceOf(a[0], a[1])
            XCTAssertEqual(got?.0, a[2], "\(a[0]) \(a[1])"); XCTAssertEqual(got?.1, a[3], "\(a[0]) \(a[1])")
        }
    }

    func testTokenMarketAndGamesMatchTheWeb() throws {
        let fix = try fixture("promos.json")
        for c in fix["market_fits"].array {
            let kinds = c["kinds"].array.compactMap(\.string)   // a token for certain kinds of leg (Nov 9)
            XCTAssertEqual(Build.marketFits(c["market"].string, stat: c["stat"].string, player: c["player"].string, kinds: kinds.isEmpty ? nil : kinds),
                           c["want"].bool, "\(c)")
        }
        for c in fix["fits_game"].array {
            let teams = c["teams"].isNull ? nil : c["teams"].array.compactMap(\.string)
            let games = c["games"].isNull ? nil : c["games"].array.map { PromoGame(eventId: $0["event_id"].string!, matchup: $0["matchup"].string!, commenceTime: $0["commence_time"].string!) }
            XCTAssertEqual(Promos.fitsGame(teams: teams, games: games, eventId: c["event"].string!, matchup: c["matchup"].string!, start: c["start"].string ?? ""), c["want"].bool, "\(c)")
        }
    }

    /// A token's leg kinds are cleaned as the web cleans them, read and saved with the token, and named in its terms (Nov 9,
    /// migration 0047; web cleanKinds, tests/fixtures/promos.json `clean_kinds`).
    func testPromoDollarsGoOutToTheCent() throws {
        var p = PromoRow(); p.kind = "bonus"; p.amountDollars = 10.61
        let json = try JSONSerialization.data(withJSONObject: p.row.mapValues { $0 ?? NSNull() })
        XCTAssertTrue(String(decoding: json, as: UTF8.self).contains("\"amount_dollars\":10.61"), String(decoding: json, as: UTF8.self))
    }

    func testLegKindsMatchTheWeb() throws {
        let fix = try fixture("promos.json")
        for c in fix["clean_kinds"].array {
            let want: [String]? = c["want"].isNull ? nil : c["want"].array.compactMap(\.string)
            XCTAssertEqual(Promos.cleanKinds(c["in"].array.compactMap(\.string)), want, "\(c)")
        }
        let p = try Models.decoder.decode(PromoRow.self, from: Data(#"{"kind":"boost","pct":50,"leg_kinds":["tds","first_td"]}"#.utf8))
        XCTAssertEqual(p.legKinds, ["tds", "first_td"])
        XCTAssertEqual(Promos.unpricedKinds(p), ["first_td"])
        XCTAssertEqual(Promos.terms(p), "Anytime TD or First TD only")
        XCTAssertEqual(Promos.asPromo(p).kinds, ["tds", "first_td"])
        XCTAssertEqual((Promos.clean(p).row?.row["leg_kinds"] ?? nil) as? [String], ["tds", "first_td"])
        XCTAssertNil(Promos.clean(PromoRow(kind: "boost", pct: 50, legKinds: [])).row?.row["leg_kinds"] ?? nil)
        XCTAssertEqual(PromosView.failedText(read: 5, failed: 2), "Read 3 of 5 screenshots: send the other 2 again.")
        XCTAssertEqual(PromosView.failedText(read: 3, failed: 1), "Read 2 of 3 screenshots: send the other one again.")
        XCTAssertNil(PromosView.failedText(read: 3, failed: 0))
    }

    func testPromoWalletMatchesTheWeb() throws {
        let fix = try fixture("promos.json")
        let now = Models.date(fix["now"].string)!
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/promos.json")
        let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        let data = try JSONSerialization.data(withJSONObject: raw["promos"]!)
        let rows = try Models.decoder.decode([PromoRow].self, from: data)
        let byId = Dictionary(uniqueKeysWithValues: rows.map { ($0.promoId, $0) })
        let w = Promos.wallet(rows, now: now), e = fix["expect"]
        XCTAssertEqual(w.open.map(\.promoId), e["open"].array.compactMap(\.string))
        XCTAssertEqual(w.done.map(\.promoId), e["done"].array.compactMap(\.string))
        XCTAssertEqual(Promos.expiringSoon(rows, now: now).map(\.promoId), e["soon"].array.compactMap(\.string))
        for (id, s) in e["state"].object { XCTAssertEqual(Promos.state(byId[id]!, now: now), s.string, id) }
        for (id, s) in e["title"].object { XCTAssertEqual(Promos.title(byId[id]!), s.string, id) }
        for (id, s) in e["terms"].object { XCTAssertEqual(Promos.terms(byId[id]!), s.string, id) }
        for (id, s) in e["expires"].object { XCTAssertEqual(Promos.expires(byId[id]!, now: now), s.string, id) }
        for c in e["note_sports"].array {
            let note = c[0].string!, want = c[1].array.compactMap(\.string)
            XCTAssertEqual(Promos.sports(PromoRow(note: note)) ?? [], want, note)
        }
    }

    /// Legs linked to a main market say to check the number (Oct 30, Brunson 1.5 -> 2.5; web fanduel.test.mjs)
    func testMainLineLinksSayToCheckTheNumber() {
        XCTAssertNil(Build.mainLineText([false, false]))
        XCTAssertEqual(Build.mainLineText([true]), "Check the number on FanDuel's slip: this link follows FanDuel's main line, which can move.")
        XCTAssertEqual(Build.mainLineText([true, false, true], book: "DraftKings"),
                       "Check the number on 2 of these legs on DraftKings' slip: their links follow DraftKings' main line, which can move.")
    }

    /// A token's wager, and what a bonus bet leaves (Nov 3): the cases web promos.test.mjs runs.
    func testWagerAndBonusLeft() throws {
        let fix = try fixture("promos.json")
        for c in fix["wager"].array { XCTAssertEqual(Promos.wager(c["typed"].string ?? "", max: c["max"].double), c["want"].double, "\(c)") }
        for c in fix["bonus_left"].array { XCTAssertEqual(Promos.bonusLeft(c["face"].double, c["dollars"].double!), c["want"].double!, "\(c)") }
    }

    /// A token for some games: its teams, split and matched to a game's side (Oct 31; tests/fixtures/promos.json)
    func testPromoTeamsMatchTheWeb() throws {
        let e = try fixture("promos.json")["expect"]
        for c in e["split_teams"].array {
            XCTAssertEqual(Promos.splitTeams([c[0].string!]), c[1].array.isEmpty ? nil : c[1].array.compactMap(\.string), c[0].string!)
        }
        for c in e["team_fits"].array {
            let teams = c[0].array.compactMap(\.string)
            XCTAssertEqual(Promos.teamFits(teams.isEmpty ? nil : teams, c[1].string!), c[2].bool!, c[1].string!)
        }
    }

    /// What /api/promos answers decodes (Nov 9: PromoRow required promo_id and status, so every screenshot read failed on the
    /// iPhone), even with no id or status at all; and a token is cleaned as the web cleans it (tests/fixtures/promos.json).
    func testPromoReadDecodesAndCleansAsTheWeb() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/promos.json")
        let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        struct Answer: Decodable { let promos: [PromoRow]? }
        let answer = try Models.decoder.decode(Answer.self, from: JSONSerialization.data(withJSONObject: raw["draft_answer"]!))
        XCTAssertEqual(answer.promos?.count, 2)
        XCTAssertEqual(answer.promos?[0].pct, 30); XCTAssertEqual(answer.promos?[0].minLegs, 3); XCTAssertEqual(answer.promos?[0].status, "open")
        XCTAssertNil(answer.promos?[0].problem); XCTAssertEqual(answer.promos?[1].problem, "A boost needs its size, 1 to 500%.")
        let bare = try Models.decoder.decode(Answer.self, from: Data(#"{"promos":[{"kind":"boost","amount_dollars":25,"source":"screenshot"}]}"#.utf8))
        XCTAssertEqual(bare.promos?.first?.promoId, ""); XCTAssertEqual(bare.promos?.first?.amountDollars, 25)

        let clean = (raw["clean"] as! [String: Any])["cases"] as! [[String: Any]]
        for c in clean {
            let p = try Models.decoder.decode(PromoRow.self, from: JSONSerialization.data(withJSONObject: c["in"]!))
            let got = Promos.clean(p)
            if let e = c["error"] as? String { XCTAssertNil(got.row, "\(c)"); XCTAssertEqual(got.error, e); continue }
            let row = try XCTUnwrap(got.row, "\(c)").row
            func json(_ x: Any) throws -> String {
                String(decoding: try JSONSerialization.data(withJSONObject: ["v": x], options: [.sortedKeys]), as: UTF8.self)
            }
            for (k, v) in c["want"] as! [String: Any] {
                let mine: Any = (row[k] ?? nil) ?? NSNull()
                XCTAssertEqual(try json(mine), try json(v), "\(k) of \(c)")
            }
        }
    }

    /// A token placed must still be open, and a slip read from a screenshot offers the tokens it may have used (Nov 9; web promos.test.mjs).
    func testTokenUsableAndSlipTokensMatchTheWeb() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/promos.json")
        let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        let fix = try fixture("promos.json")
        let now = Models.date(fix["now"].string)!
        let st = raw["slip_tokens"] as! [String: Any]
        let rows = try Models.decoder.decode([PromoRow].self, from: JSONSerialization.data(withJSONObject: raw["promos"]!))
            + Models.decoder.decode([PromoRow].self, from: JSONSerialization.data(withJSONObject: st["tokens"]!))
        for c in fix["usable"]["cases"].array {
            let id = c[0].string!
            XCTAssertEqual(Promos.usable(rows.first { $0.promoId == id }, now: now), c[1].string, id)
        }
        for c in fix["slip_tokens"]["cases"].array {
            let s = c["slip"]
            let got = Promos.slipTokens(book: s["book"].string!, bonus: s["bonus"].bool!, boost: s["boost_pct"].double, stake: s["stake_dollars"].double!,
                                        price: s["price"].double, legs: s["legs"].double.map { Int($0) }, rows, now: now)
            XCTAssertEqual(got.map(\.promoId), c["want"].array.compactMap(\.string), "\(s)")
        }
    }

    func testIUsedItOffersTheTokensLikelyBets() throws {
        let fix = try fixture("promos.json"), u = fix["used_on"]
        let now = Models.date(fix["now"].string)!
        let bets: [MyBet] = u["bets"].array.map { j in
            var b = MyBet(); b.betId = j["bet_id"].string!; b.mode = j["mode"].string; b.book = j["book"].string
            b.bonus = j["bonus"].bool; b.boost = j["boost"].double; b.promoId = j["promo_id"].string; b.placedAt = j["placed_at"].string!
            return b
        }
        for c in u["cases"].array {
            var p = PromoRow(); p.kind = c["promo"]["kind"].string!; p.book = c["promo"]["book"].string
            XCTAssertEqual(Promos.usedOnChoices(p, bets, now: now).map(\.betId), c["want"].array.compactMap(\.string), p.kind + (p.book ?? ""))
        }
    }
}
