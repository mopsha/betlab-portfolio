import XCTest
@testable import BetLab

final class CalendarTests: XCTestCase {
    private func fixture() throws -> JSON {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/calendar.json")
        return try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
    }

    func testTheMonthGridRunsSundayToSaturdayAroundTheMonth() throws {
        for g in try fixture()["grids"].array {
            let days = CalendarGrid.grid(g["month"].string ?? "")
            XCTAssertEqual(days.first, g["first"].string)
            XCTAssertEqual(days.last, g["last"].string)
            XCTAssertEqual(days.count, Int(g["weeks"].double ?? 0) * 7)
        }
    }

    func testMonthsShiftAcrossYears() throws {
        for s in try fixture()["shift"].array {
            XCTAssertEqual(CalendarGrid.shift(s[0].string ?? "", Int(s[1].double ?? 0)), s[2].string)
        }
    }
}
