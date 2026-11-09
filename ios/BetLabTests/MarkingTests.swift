import XCTest
@testable import BetLab

/// Marks must save what the web app saves (web/lib/actions.ts markBet, updateBet; web/lib/real.ts).
final class MarkingTests: XCTestCase {
    // the host app signs in and loads the account's books off (BooksOff.current); every case here starts with all three on
    override func setUp() { super.setUp(); BooksOff.current = [] }

    func testRealMoneyStartsOct18EasternOrTheAccountsOwnDate() {
        XCTAssertFalse(Marking.isReal(now: Models.date("2026-10-18T03:59:00Z")!, realFrom: nil))   // 11:59 PM ET Oct 17
        XCTAssertTrue(Marking.isReal(now: Models.date("2026-10-18T04:00:00Z")!, realFrom: nil))
        XCTAssertTrue(Marking.isReal(now: Models.date("2026-10-12T12:00:00Z")!, realFrom: "2026-10-10T00:00:00+00:00"))
    }

    func testPaperAndRealRows() {
        let m = MarkInput(kind: "pick", pickId: "p1", price: 240, label: "Draw", matchup: "A vs B", book: "draftkings")
        let paper = Marking.row(m, real: false)
        XCTAssertEqual(paper["mode"] as? String, "paper")
        XCTAssertNil(paper["stake"]!)
        XCTAssertEqual(paper["book"] as? String, "DraftKings")
        XCTAssertNil(paper["sgp_id"] ?? nil)
        let real = Marking.row(m, real: true)
        XCTAssertEqual(real["mode"] as? String, "real")
        XCTAssertEqual(real["stake"] as? Int, 1)
    }

    func testParlayGoesToTheBetterTypedPrice() {
        var body = TicketBody()
        body.legs = [Leg(label: "Over 47.5", price: -110, fairPrice: nil, note: nil, link: nil),
                     Leg(label: "Bills ML", price: -150, fairPrice: nil, note: nil, link: nil)]
        let t = Ticket(sgpId: "s1", kind: "sgp", sport: "nfl", gameId: "g", slate: nil, matchup: "A @ B", commenceTime: nil,
                       fairPrice: 300, pFair: 0.25, price: 280, body: body)
        XCTAssertEqual(MarkInput.ticket(t, quote: nil, dkQuote: nil).price, 280)
        XCTAssertEqual(MarkInput.ticket(t, quote: 310, dkQuote: nil).book, "FanDuel")
        let dk = MarkInput.ticket(t, quote: 310, dkQuote: 330)
        XCTAssertEqual(dk.book, "DraftKings")
        XCTAssertEqual(dk.price, 330)
        XCTAssertEqual(dk.legs, ["Over 47.5", "Bills ML"])
        let row = Marking.row(dk, real: false)
        XCTAssertEqual(row["sgp_id"] as? String, "s1")
        XCTAssertNil(row["pick_id"] ?? nil)
    }

    /// A Build slip's mark saves its games (Nov 1: an NFL moneyline parlay saved without them didn't track).
    func testBuildMarkSavesItsGames() {
        let m = MarkInput(kind: "custom", sgpId: "custom-1", legs: ["New York Jets ML", "Buffalo Bills ML"],
                          games: [.init(matchup: "Las Vegas Raiders @ New York Jets", gameRef: "2026_08_LV_NYJ", legs: ["New York Jets ML"]),
                                  .init(matchup: "Baltimore Ravens @ Buffalo Bills", gameRef: "2026_08_BAL_BUF", legs: ["Buffalo Bills ML"])])
        let games = Marking.row(m, real: true)["games"] as? [[String: Any?]]
        XCTAssertEqual(games?.count, 2)
        XCTAssertEqual(games?[1]["game_ref"] as? String, "2026_08_BAL_BUF")
        XCTAssertEqual(games?[1]["legs"] as? [String], ["Buffalo Bills ML"])
        XCTAssertFalse(Marking.row(MarkInput(kind: "pick", pickId: "p"), real: true).keys.contains("games"))
    }

    func testEditValidation() {
        XCTAssertEqual(Marking.parseOdds("+150"), 150)
        XCTAssertEqual(Marking.parseOdds("\u{2212}110"), -110)
        XCTAssertNil(Marking.parseOdds("50"))
        guard case .success(let ok) = Marking.edit(stake: "2.555", price: "-115", book: "fanduel") else { return XCTFail() }
        XCTAssertEqual(ok["stake"] as? Double, 2.555)          // 3 decimals, as slips save them (Nov 9)
        XCTAssertEqual(ok["price"] as? Double, -115)
        XCTAssertEqual(ok["book"] as? String, "FanDuel")
        guard case .success(let reset) = Marking.edit(stake: "20", price: "+127", book: "FanDuel", reset: true) else { return XCTFail() }
        XCTAssertEqual(reset["reset"] as? Bool, true)
        guard case .failure(let e) = Marking.edit(stake: "0", price: "", book: "FanDuel") else { return XCTFail() }
        XCTAssertEqual(e.message, "Enter a stake in units, above 0 and at most 100.")
        // an untouched stake isn't written again (0.382u stays 0.382u), and a ladder step's whole stack can be edited
        guard case .success(let kept) = Marking.edit(stake: "0.382", price: "+150", book: "FanDuel", current: 0.382) else { return XCTFail() }
        XCTAssertFalse(kept.keys.contains("stake"))
        guard case .success(let big) = Marking.edit(stake: "150", price: "-110", book: "FanDuel", current: 150, ladder: true) else { return XCTFail() }
        XCTAssertFalse(big.keys.contains("stake"))
        guard case .success(let raised) = Marking.edit(stake: "300", price: "-110", book: "FanDuel", current: 150, ladder: true) else { return XCTFail() }
        XCTAssertEqual(raised["stake"] as? Double, 300)
        guard case .failure = Marking.edit(stake: "150", price: "-110", book: "FanDuel", current: 1) else { return XCTFail() }
        guard case .failure(let p) = Marking.edit(stake: "1", price: "abc", book: "FanDuel") else { return XCTFail() }
        XCTAssertEqual(p.message, "Enter a price like -110 or +150.")
    }

    func testFriendlyErrorsAndUnits() {
        XCTAssertEqual(Marking.friendly("duplicate key value violates unique constraint"), "Already marked.")
        XCTAssertEqual(Marking.friendly("new row violates row-level security policy"), "You can view this but not change it.")
        XCTAssertEqual(Marking.units(nil), "1u")
        XCTAssertEqual(Marking.units(2.5), "2.5u")
    }
}
