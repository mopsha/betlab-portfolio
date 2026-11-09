import XCTest
@testable import BetLab

final class SearchTests: XCTestCase {
    private func fixture() throws -> JSON {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/search.json")
        return try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
    }

    func testSearchFindsYourBets() throws {
        let f = try fixture()
        let bets: [MyBet] = f["bets"].array.map { b in
            var m = MyBet()
            m.betId = b["bet_id"].string ?? ""
            m.placedAt = b["placed_at"].string ?? ""
            m.label = b["label"].string
            m.matchup = b["matchup"].string
            m.legs = b["legs"].array.compactMap(\.string)
            return m
        }
        for c in f["bet_cases"].array {
            XCTAssertEqual(Search.bets(bets, c[0].string ?? "").map(\.betId), c[1].array.compactMap(\.string), c[0].string ?? "")
        }
    }

    func testSearchFindsTeamsByNameOrCode() throws {
        let f = try fixture()
        let teams: [String: [Bans.TeamRow]] = try JSONDecoder().decode([String: [Bans.TeamRow]].self, from:
            JSONSerialization.data(withJSONObject: ["nba": [["name": "New York Knicks", "abbr": ["NYK", "NY"]], ["name": "Boston Celtics", "abbr": ["BOS"]]],
                                                    "nhl": [["name": "New York Rangers", "abbr": ["NYR"]]]]))
        for c in f["team_cases"].array {
            XCTAssertEqual(Search.teams(teams, c[0].string ?? "").map(\.team.name), c[1].array.compactMap(\.string), c[0].string ?? "")
        }
    }
}
