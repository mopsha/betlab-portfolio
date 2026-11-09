import XCTest
@testable import BetLab

/// Ladder challenges (Ladder.swift): the shared cases (tests/fixtures/ladder.json) that web/tests/ladder.test.mjs runs too.
final class LadderTests: XCTestCase {
    private func fixture() throws -> JSON {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/ladder.json")
        return try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
    }

    private func bet(_ s: JSON, _ i: Int) -> MyBet {
        var b = MyBet()
        b.betId = "b\(i)"; b.ladderId = "L"; b.kind = "custom"; b.mode = "real"
        b.stake = s["stake"].double; b.price = s["price"].double; b.bonus = s["bonus"].bool
        b.boost = s["boost"].double; b.cashout = s["cashout"].double
        b.placedAt = "2026-10-2\(i)T12:00:00Z"; b.ticketStatus = s["status"].string
        return b
    }

    func testTheSharedStates() throws {
        let cases = try fixture()["states"].array
        XCTAssertGreaterThan(cases.count, 8)
        for c in cases {
            let name = c["name"].string!
            let l = Ladder(ladderId: "L", startUnits: c["ladder"]["start"].double!, targetUnits: c["ladder"]["target"].double!,
                           status: c["ladder"]["status"].string ?? "active", createdAt: "2026-10-20T00:00:00Z")
            let s = LadderMath.state(l, c["steps"].array.enumerated().map { bet($1, $0) })
            XCTAssertEqual(s.phase.rawValue, c["expect"]["phase"].string!, name)
            XCTAssertEqual(s.stack, c["expect"]["stack"].double!, accuracy: 1e-4, name)
            XCTAssertEqual(s.won, Int(c["expect"]["won"].double!), name)
            if let want = c["expect"]["next_stake"].double { XCTAssertEqual(s.nextStake ?? -1, want, accuracy: 1e-4, name) }
            else { XCTAssertNil(s.nextStake, name) }
            if let want = c["expect"]["to_win"].double { XCTAssertEqual(s.toWin ?? -1, want, accuracy: 1e-4, name) }
        }
    }

    func testTheSharedSuggestions() throws {
        for c in try fixture()["suggest"].array {
            let offers: [Offer] = try c["offers"].array.map { o in
                var row: [String: Any] = ["offer_id": o["offer_id"].string!, "tier": o["tier"].string!, "league": "nfl",
                                          "label": o["offer_id"].string!, "game_id": o["game_id"].string!, "price": o["price"].double!,
                                          "ev": o["ev"].double!, "commence_time": o["commence_time"].string!]
                for k in ["book", "other_book"] { if let v = o[k].string { row[k] = v } }
                for k in ["point", "other_point", "other_price", "other_ev"] { if let v = o[k].double { row[k] = v } }
                return try Models.decoder.decode(Offer.self, from: JSONSerialization.data(withJSONObject: row))
            }
            let got = LadderMath.suggest(offers, now: Models.date(c["now"].string)!, skipped: c["skipped"].array.compactMap(\.string),
                                         game: c["game"].string, before: Models.date(c["before"].string), book: c["book"].string)
            if let want = c["expect_price"].double { XCTAssertEqual(got?.price, want, c["name"].string!) }
            XCTAssertEqual(got?.offerId, c["expect"].string, c["name"].string!)
        }
    }

    func testWinsInARowToTheTarget() throws {
        for c in try fixture()["steps_to_target"].array {
            XCTAssertEqual(LadderMath.stepsToTarget(c["stack"].double!, c["target"].double!, price: c["price"].double!), Int(c["expect"].double!))
        }
    }

    func testALadderRowWithALockedStepDecodes() throws {
        let row = #"[{"ladder_id":"L","start_units":1,"target_units":100,"status":"active","created_at":"2026-10-27T13:00:00Z","game_id":null,"skipped":["x"],"locked":{"offer_id":"o1","tier":"pick","label":"Knicks -2.5","price":-105.0,"book":"FanDuel","matchup":"BOS @ NY","commence_time":"2026-10-27T23:30:00Z","ev":0.035,"game_id":"nba:1","league":"nba","player":null,"stake":1.95,"step":2},"locked_at":"2026-10-27T22:40:00Z","notice":null}]"#
        let l = try Models.decoder.decode([Ladder].self, from: Data(row.utf8))[0]
        XCTAssertEqual(l.locked?.offerId, "o1")
        XCTAssertEqual(l.locked?.stake, 1.95)
        XCTAssertEqual(l.locked?.step, 2)
        XCTAssertEqual(l.skipped, ["x"])
    }

    func testAStepReadsAsItsLegsAndALadderNeverShowsLessThanNothing() throws {
        for c in try fixture()["step_names"].array {
            let legs: [String]? = c["legs"].isNull ? nil : c["legs"].array.compactMap(\.string)
            XCTAssertEqual(LadderMath.stepName(legs: legs, label: c["label"].string, matchup: c["matchup"].string), c["expect"].string)
        }
        for c in try fixture()["ended_stack"].array { XCTAssertEqual(LadderMath.shownStack(c["stack"].double!), c["expect"].double!) }
    }

    func testALockMissingItsStakeStillDecodes() throws {
        let row = #"{"ladder_id":"L","start_units":1,"target_units":100,"status":"active","created_at":"2026-11-06T12:00:00Z","locked":{"offer_id":"o","tier":"lean","label":"Buffalo Sabres ML","price":-120,"commence_time":"2026-11-07T00:00:00Z"}}"#
        let l = try Models.decoder.decode(Ladder.self, from: Data(row.utf8))
        XCTAssertEqual(l.locked?.label, "Buffalo Sabres ML")
        XCTAssertNil(l.locked?.stake)
    }

    func testATappedLadderAlertOpensTheLadderOnMe() {
        XCTAssertTrue(Push.destination("/bets?view=ladder") == ("more", true))       // the worker's link (ladders.py)
        XCTAssertTrue(Push.destination("/more/ladder") == ("more", true))
        XCTAssertTrue(Push.destination("/bets") == ("bets", false))
        XCTAssertTrue(Push.destination("/games/nfl/2026_10_DAL_IND") == ("games", false))
        XCTAssertTrue(Push.destination("/") == ("home", false))
    }
}
