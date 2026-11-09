import XCTest
@testable import BetLab

/// Watched games (Nov 7, 0045): tests/fixtures/watch.json, the web's cases too.
final class WatchTests: XCTestCase {
    private func fixture() throws -> JSON {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/watch.json")
        return try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
    }

    private func decode<T: Decodable>(_ j: JSON, _ extra: [String: Any] = [:]) throws -> T {
        var o = j.object.mapValues(\.any)
        for (k, v) in extra where o[k] == nil { o[k] = v }
        return try Models.decoder.decode(T.self, from: JSONSerialization.data(withJSONObject: o))
    }

    func testTodayShowsAWatchedGamesSlipsAtItsOwnLockNeverItsSlices() throws {
        let fx = try fixture()
        guard case .array(let w) = fx["watching"], case .array(let cases) = fx["cases"],
              case .array(let lt) = fx["locks"]["tickets"], case .array(let want) = fx["locks"]["want"],
              let now = Models.date(fx["now"].string) else { return XCTFail("fixture") }
        let watching = Set(w.compactMap(\.string))
        for c in cases {
            let t: Ticket = try decode(c["ticket"], ["sgp_id": "s", "sport": "nfl", "body": [String: Any]()])
            XCTAssertEqual(Watch.shows(t, watching: watching, now: now), c["show"].bool, c["name"].string ?? "")
        }
        let tickets: [Ticket] = try lt.map { try decode($0, ["sgp_id": "s", "body": [String: Any]()]) }
        let got = Watch.locks(tickets, watching: watching, now: now)
        XCTAssertEqual(got.map(\.slate), want.compactMap { $0["key"].string })
        XCTAssertEqual(got.map(\.title), want.compactMap { $0["title"].string })
        XCTAssertEqual(got.map(\.at), want.compactMap { Models.date($0["at"].string) })
    }

    func testWatchingAGameTurnsOnOnceAndOffCleanly() {
        XCTAssertEqual(Watch.toggled(["a"], "b", on: true), ["a", "b"])
        XCTAssertEqual(Watch.toggled(["a", "b"], "b", on: true), ["a", "b"])
        XCTAssertEqual(Watch.toggled(["a", "b"], "a", on: false), ["b"])
        XCTAssertEqual(Watch.nicks("Cincinnati Bengals @ Atlanta Falcons"), "Bengals @ Falcons")
    }
}
