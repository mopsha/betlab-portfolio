import XCTest
@testable import BetLab

/// web/tests/wrapped.test.mjs, case for case: Wrapped must read as the web does.
final class WrappedTests: XCTestCase {
    private var n = 0
    func on(_ day: String, _ f: (inout MyBet) -> Void = { _ in }) -> MyBet {
        n += 1
        var b = MyBet(betId: "b\(n)", kind: "custom", mode: "real", price: 100, stake: 1, book: "FanDuel", bonus: false, matchup: "x",
                      placedAt: day + "T18:00:00Z", ticketStatus: "won", legs: ["A ML"])
        f(&b)
        return b
    }
    let oct27 = Models.date("2026-10-27T12:00:00Z")!
    func results(_ s: String) -> [LegResult] { try! Models.decoder.decode([LegResult].self, from: Data(s.utf8)) }

    func testMonthsWithASettledBetNewestFirstAndTheSeason() {
        XCTAssertEqual(Wrapped.periods([on("2026-10-19"), on("2026-10-25"), on("2026-11-02"), on("2026-11-03") { $0.ticketStatus = nil }]),
                       ["2026-11", "2026-10", "season"])
        XCTAssertEqual(Wrapped.periods([on("2026-10-19")]), ["2026-10"])
        XCTAssertEqual(Wrapped.periodName("2026-10", now: oct27), "October")
        XCTAssertEqual(Wrapped.periodName("2025-12", now: oct27), "December 2025")
        XCTAssertEqual(Wrapped.periodName("season"), "Your season")
    }

    func testAMonthsStoryItsOwnBetsTheBottomLineBiggestHitBestDayAndBook() throws {
        let bets = [
            on("2026-09-28") { $0.price = 900 },                                     // September: not in October's story
            on("2026-10-19") { $0.price = 389; $0.boost = 30 },                      // +5.06u
            on("2026-10-19") { $0.ticketStatus = "lost" },
            on("2026-10-25") { $0.price = 150; $0.book = "DraftKings" },
            on("2026-10-26") { $0.ticketStatus = "lost"; $0.book = "DraftKings" },
            on("2026-10-27") { $0.ticketStatus = nil },                              // open: not counted
        ]
        let w = try XCTUnwrap(Wrapped.story(bets, "2026-10", now: oct27))
        XCTAssertEqual(w.name, "October")
        XCTAssertEqual(w.total.bets, 4)
        XCTAssertEqual([w.total.won, w.total.lost], [2, 2])
        XCTAssertEqual(w.total.units, 3.89 * 1.3 - 1 + 1.5 - 1, accuracy: 1e-9)
        XCTAssertEqual(w.best?.price, "+389 → +506")
        XCTAssertEqual(w.bestDay?.day, "2026-10-19")
        XCTAssertEqual(w.busiest?.day, "2026-10-19")
        XCTAssertEqual(w.book?.group, "FanDuel")                                    // +4.06u vs DraftKings +0.50u
        XCTAssertEqual(w.days, 3)
        XCTAssertNil(Wrapped.story(bets, "2026-08"))
        XCTAssertEqual(Wrapped.story(bets, "season")?.total.bets, 5)
    }

    func testTheHeartbreakerIsTheLongestParlayThatLostByOneLegAndNamesIt() throws {
        let legs = ["A 50+ receiving yds", "B 3+ receptions", "C ML"]
        let res = { (lost: Int) in self.results("[" + legs.enumerated().map { #"{"leg": "\#($0.element)", "result": "\#($0.offset == lost ? "lost" : "won")", "value": \#($0.offset == lost ? 44 : 1)}"# }.joined(separator: ",") + "]") }
        let bets = [
            on("2026-10-25") { $0.price = 600; $0.legs = legs; $0.ticketStatus = "lost"; $0.legResults = res(0) },
            on("2026-10-25") { $0.price = 3038; $0.legs = legs; $0.ticketStatus = "lost"; $0.legResults = res(2) },
            on("2026-10-25") { $0.price = 9000; $0.legs = legs; $0.ticketStatus = "lost"                       // two+ lost
                $0.legResults = self.results("[" + legs.map { #"{"leg": "\#($0)", "result": "lost"}"# }.joined(separator: ",") + "]") },
        ]
        let h = try XCTUnwrap(Wrapped.heartbreak(bets))
        XCTAssertEqual(h.leg.label, "C ML")
        XCTAssertEqual(h.bet.price, "+3038")
        XCTAssertEqual(h.hit, 2)
        XCTAssertNil(Wrapped.heartbreak([on("2026-10-25")]))
    }

    func testTheBettingTypeTheFirstThatFitsWithEnoughBets() {
        let many = { (k: Int, f: @escaping (inout MyBet) -> Void) in (0..<k).map { _ in self.on("2026-10-25", f) } }
        XCTAssertEqual(Wrapped.persona(many(6) { $0.kind = "pick"; $0.pickStatus = "won"; $0.ticketStatus = nil; $0.clv = 0.03; $0.loggedPrice = 100 }).name, "The Sharp")
        XCTAssertEqual(Wrapped.persona(many(6) { $0.legs = Array(repeating: "x", count: 6) }).name, "The Parlay Architect")
        XCTAssertEqual(Wrapped.persona(many(6) { $0.bonus = true }).name, "The Bonus Hunter")
        XCTAssertEqual(Wrapped.persona(many(6) { $0.price = 1200 }).name, "The Long-Shot Dreamer")
        XCTAssertEqual(Wrapped.persona(many(6) { $0.kind = "pick"; $0.league = "nba" }).name, "The NBA Loyalist")
        XCTAssertEqual(Wrapped.persona(many(2) { _ in }).name, "The All-Rounder")      // two bets: too few for a type
    }

    func testBadgesShowInTheMonthWhoseBetEarnedThem() {
        let bets = [on("2026-09-28"), on("2026-10-20") { $0.price = 1200 }]
        let oct = Wrapped.story(bets, "2026-10")!.badges.map(\.title)
        XCTAssertTrue(oct.contains("Four figures"))
        XCTAssertFalse(oct.contains("On the board"))                                 // earned in September
    }

    @MainActor func testTheSharePictureRendersAt1080x1350() throws {
        let w = try XCTUnwrap(Wrapped.story([on("2026-10-19") { $0.price = 389 }, on("2026-10-20") { $0.ticketStatus = "lost"; $0.book = "DraftKings" }], "2026-10"))
        let img = try XCTUnwrap(UIImage(data: try XCTUnwrap(WrappedCardView.png(w))))
        XCTAssertEqual(img.size.width * img.scale, 1080); XCTAssertEqual(img.size.height * img.scale, 1350)
    }
}
