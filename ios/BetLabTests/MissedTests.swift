import XCTest
@testable import BetLab

/// Missed bets: the cases web/lib/missed.ts runs too (tests/fixtures/missed.json).
final class MissedTests: XCTestCase {
    func testTheSharedCases() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/missed.json")
        let fix = try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
        for c in fix["cases"].array {
            let picks = c["picks"].array.map { p in
                PaperPick(pickId: p["pick_id"].string!, commenceTime: p["commence_time"].string, status: p["status"].string,
                          profitFlat: p["profit_flat"].double, clv: p["clv"].double, clvRaw: p["clv_raw"].double)
            }
            let r = Missed.bets(picks, taken: Set(c["taken"].array.compactMap(\.string)), since: Models.date(c["since"].string)!)
            let w = c["want"]
            XCTAssertEqual(r.picks.map(\.pickId), w["ids"].array.compactMap(\.string))
            XCTAssertEqual([r.won, r.lost, r.push, r.tookN], [w["won"].double!, w["lost"].double!, w["push"].double!, w["took_n"].double!].map { Int($0) })
            XCTAssertEqual(r.units, w["units"].double!, accuracy: 1e-9)
            XCTAssertEqual(r.tookUnits, w["took_units"].double!, accuracy: 1e-9)
            if let want = w["clv"].double { XCTAssertEqual(r.clv ?? .nan, want, accuracy: 1e-9) } else { XCTAssertNil(r.clv) }
        }
    }
}
