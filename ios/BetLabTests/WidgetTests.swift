import XCTest
@testable import BetLab

/// The widgets' snapshot (WidgetFeed) and the Live Activity's state as the worker sends it (live_activity.py).
final class WidgetTests: XCTestCase {
    private var n = 0
    func bet(_ placed: String, _ f: (inout MyBet) -> Void = { _ in }) -> MyBet {
        n += 1
        var b = MyBet(betId: "b\(n)", kind: "custom", mode: "real", price: 150, stake: 1, book: "FanDuel", bonus: false, matchup: "x",
                      placedAt: placed, ticketStatus: "won", legs: ["A ML"])
        f(&b)
        return b
    }
    let now = Models.date("2026-10-27T20:00:00Z")!

    func testTodayTheWeekAndOpenBetsSoonestFirst() {
        let bets = [
            bet("2026-10-27T15:00:00Z"),                                                        // +1.50u today
            bet("2026-10-27T16:00:00Z") { $0.ticketStatus = "lost" },                           // -1u today
            bet("2026-10-23T16:00:00Z") { $0.ticketStatus = "lost" },                           // this week
            bet("2026-10-10T16:00:00Z"),                                                        // too old for the week
            bet("2026-10-27T17:00:00Z") { $0.ticketStatus = nil; $0.legs = ["A", "B", "C"]; $0.ticketCommenceTime = "2026-10-28T00:15:00Z" },
            bet("2026-10-27T17:05:00Z") { $0.ticketStatus = nil; $0.price = -110; $0.ticketCommenceTime = "2026-10-27T23:00:00Z" },
            bet("2026-10-27T17:00:00Z") { $0.mode = "paper"; $0.ticketStatus = nil },           // paper: not your record
        ]
        let s = WidgetFeed.snapshot(bets, realMode: true, now: now)
        XCTAssertEqual(s.today, 0.5, accuracy: 1e-9)
        XCTAssertEqual(s.week, -0.5, accuracy: 1e-9)
        XCTAssertEqual(s.settledToday, 2)
        XCTAssertEqual(s.openCount, 2)
        XCTAssertEqual(s.open.map(\.title), ["A ML", "A, B and 1 more"])
        XCTAssertEqual(s.open.map(\.price), ["\(Fmt.minus)110", "+150"])
        XCTAssertTrue(s.real)
        XCTAssertEqual(unitsText(-1.15), "\(Fmt.minus)1.15u")
    }

    func testTheWorkersContentDecodes() throws {
        let json = """
        {"status": "live", "hit": 1, "total": 3, "more": 0, "note": null,
         "games": [{"away": "WVU", "home": "TCU", "awayScore": "27", "homeScore": "30", "state": "in", "detail": "Q4 2:11"}],
         "legs": [{"label": "Josh Allen 250+ passing yds", "status": "live", "value": "180/250 yds", "progress": 0.72},
                  {"label": "Bills ML", "status": "won", "value": null, "progress": null}]}
        """
        let s = try JSONDecoder().decode(BetActivityAttributes.ContentState.self, from: Data(json.utf8))
        XCTAssertEqual(s.legs[0].progress, 0.72)
        XCTAssertEqual(s.games[0].awayScore, "27")
        XCTAssertFalse(s.over)
    }
}
