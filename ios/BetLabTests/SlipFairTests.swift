import XCTest
@testable import BetLab

final class SlipFairTests: XCTestCase {
    private func fixture(_ name: String) throws -> Data {
        try Data(contentsOf: URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/\(name).json"))
    }

    func testAPricedSlipsValue() throws {
        for c in try JSON.plainDecoder.decode(JSON.self, from: fixture("slip_ev"))["cases"].array {
            let v = Slip.ev(p: c["p"].double ?? 0, price: c["price"].double ?? 0, boost: c["boost"].double, bonus: c["bonus"].bool ?? false)
            XCTAssertEqual(v.ev, c["ev"].double ?? 9, accuracy: 1e-9, "\(c)")
            XCTAssertEqual(v.fair, c["fair"].double)
            XCTAssertEqual(v.verdict.rawValue, c["verdict"].string)
        }
    }

    func testTheFairPriceOnlyCountsForTheLegsItWasWorkedOutOn() {
        let leg = { (l: String) in SlipDraft.Leg(label: l, matchup: "x", sport: "nhl", game_ref: nil, start: nil, matched: true) }
        var d = SlipDraft(book: "FanDuel", price: 300, boost_pct: nil, stake_dollars: 5, bonus: false, placed_at: nil, legs: [leg("A ML"), leg("B ML")],
                          fair: SlipFair(p: 0.3, labels: ["A ML", "B ML"], missing: []))
        XCTAssertEqual(Slip.fairOf(d), 0.3)
        d.legs[1].label = "C ML"
        XCTAssertNil(Slip.fairOf(d))
    }

    func testThemedSlips() throws {
        struct Case: Decodable { let theme: String; let legs: [String]?; let p: Double? }
        let raw = try XCTUnwrap(JSONSerialization.jsonObject(with: fixture("themes")) as? [String: Any])
        var packs: [String: Pack] = [:]
        for (eid, v) in try XCTUnwrap(raw["packs"] as? [String: [String: Any]]) {
            var body = v
            body["legs"] = Array((v["legs"] as? [String: Any] ?? [:]).values)      // a pack's body lists its legs; the fixture keys them, as web's Pack does
            let one = try Models.decoder.decode(PackPart.self, from: JSONSerialization.data(withJSONObject: body))
            packs[eid] = try XCTUnwrap(Pack.merge([one]))
        }
        let cases = try Models.decoder.decode([Case].self, from: JSONSerialization.data(withJSONObject: try XCTUnwrap(raw["cases"])))
        let pr = Pricer(packs, book: .fanduel)
        for c in cases {
            let s = Build.themedSlip(pr, packs.keys.sorted(), Build.SlipTheme(rawValue: c.theme)!)
            XCTAssertEqual(s?.legs.map(\.label), c.legs, c.theme)
            if let p = c.p { XCTAssertEqual(s?.p ?? 0, p, accuracy: 1e-6, c.theme) }
        }
    }
}
