import XCTest
@testable import BetLab

/// Books on and off (Nov 6, 0043): tests/fixtures/books_off.json, the worker's and the web's cases too.
final class BooksOffTests: XCTestCase {
    private func fixture() throws -> JSON {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/books_off.json")
        return try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
    }

    private func offer(_ j: JSON) throws -> Offer {
        try Models.decoder.decode(Offer.self, from: JSONSerialization.data(withJSONObject: j.any))
    }

    private func check(_ o: Offer, _ off: [String], _ want: JSON, _ name: String) {
        let got = BooksOff.atBooks(o, off: off.map { $0 })
        guard case .object(let w) = want else { XCTAssertNil(got, name); return }
        guard let got else { return XCTFail("\(name): hidden") }
        let have: [String: Any?] = ["tier": got.tier.rawValue, "book": got.book, "price": got.price, "ev": got.ev, "fd_url": got.fdUrl,
                                    "bet_limit": got.betLimit, "other_book": got.otherBook, "other_price": got.otherPrice, "other_ev": got.otherEv]
        for (k, v) in w where have.keys.contains(k) {
            let h = have[k] ?? nil
            switch v {
            case .null: XCTAssertNil(h, "\(name): \(k)")
            case .string(let s): XCTAssertEqual(h as? String, s, "\(name): \(k)")
            default: XCTAssertEqual(h as? Double, v.double, "\(name): \(k)")
            }
        }
    }

    func testACardBetAtTheBooksAnAccountHasOn() throws {
        let fx = try fixture()
        let o = try offer(fx["offer"])
        for c in fx["cases"].array { check(o, c["off"].array.compactMap(\.string), c["want"], c["case"].string ?? "") }
        check(try offer(fx["lean"]["offer"]), fx["lean"]["off"].array.compactMap(\.string), fx["lean"]["want"], "lean")
        let old = try offer(fx["old"]["offer"])
        for c in fx["old"]["cases"].array { check(old, c["off"].array.compactMap(\.string), c["want"], "old") }
        for c in fx["on"].array { XCTAssertEqual(BooksOff.on(c["off"].array.compactMap(\.string)), c["want"].array.compactMap(\.string)) }
    }

    func testAHedgeNeedsASecondBookOn() {
        XCTAssertEqual(FinderModel.hedge(.fanduel, on: [.fanduel, .draftkings, .novig]), .draftkings)
        XCTAssertEqual(FinderModel.hedge(.fanduel, on: [.fanduel, .novig]), .novig)
        XCTAssertEqual(FinderModel.hedge(.draftkings, on: [.fanduel, .draftkings]), .fanduel)
        XCTAssertNil(FinderModel.hedge(.novig, on: [.novig]))
    }
}
