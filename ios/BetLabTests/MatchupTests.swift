import XCTest
@testable import BetLab

/// Soccer reads home team first (Fmt.matchup, GameLive.reading): the shared cases (tests/fixtures/soccer_matchups.json)
/// that web/lib/format.ts runs too.
final class MatchupTests: XCTestCase {
    func testTheSharedCases() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/soccer_matchups.json")
        let fix = try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
        XCTAssertGreaterThan(fix["cases"].array.count, 5)
        for c in fix["cases"].array {
            XCTAssertEqual(Fmt.matchup(c["text"].string, sport: c["sport"].string), c["out"].string!, c["text"].string!)
        }
    }

    func testASoccerGameReadsHomeFirst() {
        let side = { (n: String, s: Double) in LiveSide(name: n, abbr: "", score: s) }
        let g = GameLive(key: "k", sport: "soccer", espnId: "1", state: "in", detail: "60'", start: "",
                         home: side("Getafe", 1), away: side("Brighton", 0), winner: "home")
        XCTAssertEqual(g.reading.away.name, "Getafe")
        XCTAssertEqual(g.reading.home.name, "Brighton")
        XCTAssertEqual(g.reading.winner, "away")
        XCTAssertEqual(g.reading.between, "vs")
        var nba = g; nba.sport = "nba"
        XCTAssertEqual(nba.reading.away.name, "Brighton")
        XCTAssertEqual(nba.reading.between, "@")
    }
}
