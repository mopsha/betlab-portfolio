import XCTest
@testable import BetLab

/// web/tests/social.test.mjs, case for case: Friends must read as the web does.
final class SocialTests: XCTestCase {
    let me = "me", g = "sam-id", c = "cal-id"
    lazy var profiles = [Profile(userId: me, name: "Mike", handle: "mike"), Profile(userId: g, name: "Sam", handle: "sam"),
                         Profile(userId: c, name: "Cal", handle: "cal")]
    func games(_ s: String) -> JSON { try! JSON.plainDecoder.decode(JSON.self, from: Data(s.utf8)) }
    func bet(_ f: (inout MyBet) -> Void = { _ in }) -> MyBet {
        var b = MyBet(betId: "b1", kind: "custom", sgpId: "custom-fd-snap-1", mode: "real", price: 450, stake: 0.8, book: "DraftKings", bonus: true,
                      cashout: nil, boost: 30, ladderId: "l1", protect: true, matchup: "x", placedAt: "2026-10-27T15:00:00Z", fairPrice: 400,
                      legs: ["A ML", "B 3+ receptions"])
        b.games = games(#"[{"matchup": "x", "legs": ["A ML"]}]"#); b.pFair = 0.2; b.userId = g; b.gameStart = "2026-10-27T17:00:00Z"
        f(&b)
        return b
    }

    func testHandlesCleanedCheckedAndSuggestedFromAnEmail() {
        XCTAssertEqual(Social.cleanHandle(" @Mike_B "), "mike_b")
        XCTAssertNil(Social.cleanHandle("ab"))
        XCTAssertNil(Social.cleanHandle("has space"))
        XCTAssertEqual(Social.suggestHandle("owner@example.com"), "owner")
        XCTAssertEqual(Social.suggestHandle("al@x.com"), "al_bets")
    }

    func testTheCircleFriendsRequestsToAnswerAndRequestsWaiting() {
        let list = [Friendship(requester: g, addressee: me, status: "accepted"), Friendship(requester: c, addressee: me, status: "pending"),
                    Friendship(requester: me, addressee: "dana-id", status: "pending")]
        let x = Social.circle(me, list, profiles)
        XCTAssertEqual(x.friends.map(\.handle), ["sam"])
        XCTAssertEqual(x.incoming.map(\.otherId), [c])
        XCTAssertEqual(x.outgoing.map(\.otherId), ["dana-id"]); XCTAssertNil(x.outgoing[0].other)
    }

    func testTailIsOpenUntilTheGameStartsNeverOnceSettledNoGameClosesAfter6Hours() {
        let now = Models.date("2026-10-27T16:00:00Z")!
        XCTAssertTrue(Social.canTail(bet(), now: now))
        XCTAssertFalse(Social.canTail(bet { $0.gameStart = "2026-10-27T15:30:00Z" }, now: now))
        XCTAssertFalse(Social.canTail(bet { $0.ticketStatus = "lost" }, now: now))
        XCTAssertFalse(Social.canTail(bet { $0.liveSettled = "lost" }, now: now))
        XCTAssertTrue(Social.canTail(bet { $0.gameStart = nil }, now: now))                                   // entered an hour ago
        XCTAssertFalse(Social.canTail(bet { $0.gameStart = nil; $0.placedAt = "2026-10-27T08:00:00Z" }, now: now))
    }

    func testATailCopiesTheBetNotTheFriendsSlip() {
        let r = Social.tailRow(bet(), price: 425, book: "FanDuel", real: true)
        XCTAssertEqual(r["kind"] as? String, "custom"); XCTAssertEqual(r["sgp_id"] as? String, "custom-fd-snap-1")
        XCTAssertNil(r["pick_id"]!); XCTAssertEqual(r["price"] as? Double, 425); XCTAssertEqual(r["book"] as? String, "FanDuel")
        XCTAssertEqual(r["stake"] as? Double, 1); XCTAssertEqual(r["mode"] as? String, "real")
        XCTAssertEqual(r["legs"] as? [String], ["A ML", "B 3+ receptions"])
        XCTAssertEqual((r["games"] as? [[String: Any]])?.first?["matchup"] as? String, "x")
        for k in ["bonus", "boost", "protect", "cashout", "ladder_id", "user_id", "bet_id", "boost_cap", "promo_id", "lock_id", "promo_ev"] { XCTAssertNil(r[k], k) }
        let pick = Social.tailRow(bet { $0.kind = "pick"; $0.pickId = "p9"; $0.sgpId = nil }, price: -110, book: "DraftKings", real: false)
        XCTAssertEqual(pick["pick_id"] as? String, "p9"); XCTAssertNil(pick["sgp_id"]!)
        XCTAssertEqual(pick["mode"] as? String, "paper"); XCTAssertNil(pick["stake"]!)
        XCTAssertEqual(Social.betKey(bet { $0.kind = "pick"; $0.pickId = "p9"; $0.sgpId = nil }), "p:p9")
    }

    func testTheFeedFriendsBetsOnlyNewestFirstWithWhoPlacedIt() {
        let f = Social.feed([bet { $0.betId = "old"; $0.placedAt = "2026-10-25T10:00:00Z" }, bet { $0.betId = "new" }, bet { $0.betId = "x"; $0.userId = self.c }],
                            profiles.filter { $0.userId == g })
        XCTAssertEqual(f.map { "\($0.bet.betId) \($0.who.name)" }, ["new Sam", "old Sam"])
    }

    func testFriendBetsDecodeWhoseBetItIs() throws {
        let b = try Models.decoder.decode(MyBet.self, from: Data(#"{"bet_id": "b", "kind": "custom", "user_id": "u1", "p_fair": 0.4, "odds_event_id": "ev", "placed_at": "2026-10-27T15:00:00Z"}"#.utf8))
        XCTAssertEqual(b.userId, "u1"); XCTAssertEqual(b.pFair, 0.4); XCTAssertEqual(b.oddsEventId, "ev")
    }

    // MARK: reactions (tests/fixtures/reactions.json, the web's cases too; Nov 6)

    private func reactionsFixture() throws -> JSON {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/reactions.json")
        return try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
    }

    func testReactionsTallyATapAndWho() throws {
        let fx = try reactionsFixture(), me = fx["me"].string ?? ""
        for c in fx["tally"].array {
            let list = c["reactions"].array.map { r in
                Reaction(betId: r["bet_id"].string ?? "", userId: r["user_id"].string ?? "", name: r["name"].string,
                         reaction: r["reaction"].string ?? "", createdAt: r["created_at"].string)
            }
            let got = Social.tally(list, me: me)
            let want = c["want"].array
            XCTAssertEqual(got.count, want.count, c["case"].string ?? "")
            for (g, w) in zip(got, want) {
                XCTAssertEqual(g.reaction, w["reaction"].string); XCTAssertEqual(g.emoji, w["emoji"].string)
                XCTAssertEqual(Double(g.count), w["count"].double); XCTAssertEqual(g.mine, w["mine"].bool)
                XCTAssertEqual(g.names, w["names"].array.compactMap(\.string))
            }
        }
        for c in fx["next"].array {
            XCTAssertEqual(Social.nextReaction(c["current"].string, c["tapped"].string ?? ""), c["want"].string)
        }
        for c in fx["who"].array { XCTAssertEqual(Social.whoText(c["names"].array.compactMap(\.string)), c["want"].string) }
        XCTAssertEqual(Social.reactions.map(\.key), ["fire", "money", "sweat", "skull", "pray", "goat"])     // migration 0042's check
    }

    func testReactionsDecodeFromTheDatabase() throws {
        let r = try Models.decoder.decode(Reaction.self, from: Data(#"{"bet_id": "b", "user_id": "u", "name": null, "reaction": "goat", "created_at": "2026-11-06T20:00:00Z"}"#.utf8))
        XCTAssertEqual(r.betId, "b"); XCTAssertNil(r.name); XCTAssertEqual(r.reaction, "goat")
    }
}
