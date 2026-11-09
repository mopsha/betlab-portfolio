import XCTest
@testable import BetLab

/// FanDuel's College Football Pick'em (Nov 7): tests/fixtures/pickem.json, the worker's and the web's cases too.
final class PickemTests: XCTestCase {
    private func fixture() throws -> JSON {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/pickem.json")
        return try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
    }

    private func rows(_ fx: JSON) throws -> [PickemRow] {
        guard case .array(let list) = fx["rows"] else { return [] }
        return try list.map { j in
            var o = j.object.mapValues(\.any)
            o["week"] = "2026-11-07"
            return try Models.decoder.decode(PickemRow.self, from: JSONSerialization.data(withJSONObject: o))
        }
    }

    func testScoreFlipsAndLabelsMatchTheFixture() throws {
        let fx = try fixture()
        let rs = try rows(fx)
        XCTAssertEqual(rs.count, 5)
        let s = Pickem.score(rs), want = fx["score"]
        XCTAssertEqual(Double(s.games), want["games"].double)
        XCTAssertEqual(Double(s.picked), want["picked"].double)
        XCTAssertEqual(Double(s.graded), want["graded"].double)
        XCTAssertEqual(Double(s.yours), want["yours"].double)
        XCTAssertEqual(Double(s.ours), want["ours"].double)
        let f = Pickem.flips(rs)
        guard case .array(let flips) = fx["flips"], case .array(let unpicked) = fx["unpicked"] else { return XCTFail("fixture") }
        XCTAssertEqual(f.toFlip.map { Pickem.sideLabel($0, $0.ours ?? "") }, flips.compactMap(\.string))
        XCTAssertEqual(f.unpicked.map { Double($0.n) }, unpicked.compactMap(\.double))
        for (key, label) in fx["labels"].object {
            let parts = key.split(separator: ":")
            guard parts.count == 2, let n = Int(parts[0]), let r = rs.first(where: { $0.n == n }) else { return XCTFail(key) }
            XCTAssertEqual(Pickem.sideLabel(r, String(parts[1])), label.string, key)
        }
    }

    func testTheWeekIsTheComingSaturday() {
        XCTAssertEqual(Pickem.weekOf("2026-11-07"), "2026-11-07")
        XCTAssertEqual(Pickem.weekOf("2026-11-08"), "2026-11-14")
        XCTAssertEqual(Pickem.weekOf("2026-11-11"), "2026-11-14")
    }
}
