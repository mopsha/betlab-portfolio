import XCTest
@testable import BetLab

/// The ban list (Bans.swift): the shared cases (tests/fixtures/bans.json) that src/betlab/bans.py and web/lib/bans.ts run too.
final class BansTests: XCTestCase {
    func testTheSharedCases() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/bans.json")
        let fix = try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
        let cases = fix["cases"].array
        XCTAssertGreaterThan(cases.count, 20)
        for c in cases {
            let got = Bans.banned(Bans.clean(c["bans"]), c["label"].string!, league: c["league"].string, player: c["player"].string)
            XCTAssertEqual(got, c["hit"].bool!, "\(c["label"].string!) with \(c["bans"])")
        }
    }

    func testTheTeamTableLoads() {
        XCTAssertEqual(Bans.teams["nfl"]?.count, 32)
        XCTAssertEqual(Bans.teams["nhl"]?.count, 32)
        XCTAssertEqual(Bans.teams["nba"]?.count, 30)
    }

    func testBadEntriesAreDropped() throws {
        let raw = try JSON.plainDecoder.decode(JSON.self, from: Data(#"[{"kind":"team","name":" "},{"kind":"coach","name":"X"},"Jets",{"kind":"player","name":"Josh Allen"}]"#.utf8))
        XCTAssertEqual(Bans.clean(raw), [Ban(kind: "player", name: "Josh Allen")])
    }
}
