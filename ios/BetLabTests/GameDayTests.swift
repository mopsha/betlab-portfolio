import XCTest
@testable import BetLab

/// web/tests/gameday.test.mjs and locks.test.mjs, case for case.
final class GameDayTests: XCTestCase {
    func d(_ s: String) -> Date { Models.date(s)! }

    func testBetNames() throws {
        // the shared cases (tests/fixtures/bet_names.json), which web/tests/gameday.test.mjs runs too
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/bet_names.json")
        let fix = try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
        for c in fix["cases"].array {
            let legs: [String]? = c["legs"].isNull ? nil : c["legs"].array.compactMap(\.string)
            XCTAssertEqual(Stats.betName(legs: legs, label: c["label"].string, price: c["price"].double, n: c["n"].int), c["name"].string, "\(legs ?? [])")
        }
    }

    func testCountdownsTickToTheSecondAndSayNowOncePassed() {
        let now = d("2026-10-24T17:00:00Z")
        XCTAssertEqual(GameDay.countdown(d("2026-10-24T18:04:09Z"), now: now), "1h 04m 09s")
        XCTAssertEqual(GameDay.countdown(d("2026-10-24T17:12:30Z"), now: now), "12m 30s")
        XCTAssertEqual(GameDay.countdown(d("2026-10-24T16:59:00Z"), now: now), "now")
    }

    func testTheWallHasOneTilePerGameWithEveryBetsLegsLiveGamesFirst() {
        let g = { (key: String, state: String, start: String) in
            GameLive(key: key, sport: "ncaaf", espnId: key, state: state, detail: "", start: start,
                     home: LiveSide(name: "H", abbr: "H", score: 0), away: LiveSide(name: "A", abbr: "A", score: 0)) }
        let leg = { (label: String, key: String) in LegLive(label: label, status: .live, gameKey: key) }
        let live = g("ncaaf:1", "in", "2026-10-24T16:00:00Z"), later = g("ncaaf:2", "pre", "2026-10-24T17:00:00Z")
        let bets: [(id: String, live: BetLive)] = [
            ("b1", BetLive(games: [later, live], legs: [leg("Akron +2.5", "ncaaf:2"), leg("TCU -10.5", "ncaaf:1")], status: "live", hit: 0, total: 2)),
            ("b2", BetLive(games: [live], legs: [leg("TCU ML", "ncaaf:1")], status: "live", hit: 0, total: 1)),
        ]
        let tiles = GameDay.wallTiles(bets, names: ["b1": "2-leg parlay +260", "b2": "TCU ML -400"])
        XCTAssertEqual(tiles.map(\.game.key), ["ncaaf:1", "ncaaf:2"])
        XCTAssertEqual(tiles[0].legs.map(\.leg.label), ["TCU -10.5", "TCU ML"])
        XCTAssertEqual(tiles[0].legs.map(\.bet), ["2-leg parlay +260", "TCU ML -400"])
    }

    func testAGameDayIsAnyOpenBetOrALockStillToCome() {
        XCTAssertFalse(GameDay.isGameDay(0, 0)); XCTAssertTrue(GameDay.isGameDay(2, 0)); XCTAssertTrue(GameDay.isGameDay(0, 3))
    }

    func testLockTimesAndTheNextLocks() {
        let iso = ISO8601DateFormatter()
        XCTAssertEqual(iso.string(from: GameDay.lockTime(d("2026-10-10T22:10:00Z"))), "2026-10-10T21:45:00Z")   // 6:10 PM -> 5:45
        XCTAssertEqual(iso.string(from: GameDay.lockTime(d("2026-10-10T23:30:00Z"))), "2026-10-10T23:15:00Z")
        XCTAssertEqual(iso.string(from: GameDay.lockTime(d("2026-10-10T23:07:00Z"))), "2026-10-10T22:45:00Z")
        let s = { (slate: String, kickoff: String, locked: String?, tickets: [String]) in
            Slate(slate: slate, sport: "nhl", kickoff: kickoff, nGames: 2, title: slate, lockedAt: locked, label: slate, ticketIds: tickets) }
        let out = GameDay.upcomingLocks([
            s("soccer evening", "2026-10-10T23:30:00Z", nil, ["plus-x"]), s("nhl evening", "2026-10-10T22:10:00Z", nil, ["plus-x"]),
            s("nhl late", "2026-10-11T02:10:00Z", nil, []),                 // no ticket: nothing to lock
            s("noon", "2026-10-10T16:00:00Z", nil, ["plus-x"]),             // started
            s("afternoon", "2026-10-10T21:30:00Z", "t", ["plus-x"]),        // already locked
        ], now: d("2026-10-10T20:52:00Z"))
        XCTAssertEqual(out.map(\.slate), ["nhl evening", "soccer evening"])
    }

    func testTheNbasSlicesComeFromTheScheduleUntilTheirPullBuildsThem() {       // Oct 24
        let now = d("2026-10-24T21:00:00Z")
        let g = { (league: String, t: String) in Game(gameId: "\(league):\(t)", league: league, home: nil, away: nil, matchup: "x", commenceTime: t, state: nil) }
        let games = [g("nba", "2026-10-24T22:10:00Z"), g("nba", "2026-10-24T22:40:00Z"), g("nba", "2026-10-24T23:40:00Z"),
                     g("nba", "2026-10-25T00:10:00Z"), g("nba", "2026-10-25T01:10:00Z"), g("nba", "2026-10-25T02:10:00Z"),
                     g("nhl", "2026-10-24T23:00:00Z")]
        let iso = ISO8601DateFormatter()
        let s = GameDay.scheduledSlices(games, now: now)              // Nov 7: 5-6:30 PM tips are their own "dusk" slice
        XCTAssertEqual(s.map(\.slate), ["2026-10-24-nba-dusk", "2026-10-24-nba-early", "2026-10-24-nba-late"])
        XCTAssertEqual(s.map(\.title), ["NBA 6:10 PM games", "NBA early games", "NBA late games"])
        XCTAssertEqual(s.map { iso.string(from: $0.at) }, ["2026-10-24T21:45:00Z", "2026-10-24T23:15:00Z", "2026-10-25T00:45:00Z"])
        let built = Slate(slate: "2026-10-24-nba-dusk", sport: "nba", kickoff: "2026-10-24T22:10:00Z", nGames: 6, title: "NBA 6:10 PM games",
                          lockedAt: nil, label: "x", ticketIds: ["plus-y"])
        XCTAssertEqual(GameDay.upcomingLocks([built], now: now, games: games).map(\.slate),
                       ["2026-10-24-nba-dusk", "2026-10-24-nba-early", "2026-10-24-nba-late"])
    }

    func testCollegeBasketballsSlicesComeFromTheScheduleOnceTheyHaveTwoGames() {      // Nov 2
        let now = d("2026-11-02T14:15:00Z")
        let g = { (t: String) in Game(gameId: "ncaab:\(t)", league: "ncaab", home: nil, away: nil, matchup: "x", commenceTime: t, state: nil) }
        let s = GameDay.scheduledSlices([g("2026-11-02T14:00:00Z"), g("2026-11-02T15:00:00Z"), g("2026-11-02T23:00:00Z"),
                                         g("2026-11-02T23:30:00Z"), g("2026-11-03T02:30:00Z")], now: now)
        XCTAssertEqual(s.map(\.slate), ["2026-11-02-ncaab-evening"])
        XCTAssertEqual(s.map(\.title), ["College basketball evening games"])
        XCTAssertEqual(s.map { ISO8601DateFormatter().string(from: $0.at) }, ["2026-11-02T22:15:00Z"])
    }

    func testABetThatsOverLeavesTheWallAndAGameWithNoLiveBetLeftGoesWithIt() {     // web b5aab204
        let g = { (key: String, state: String) in
            GameLive(key: key, sport: "nba", espnId: key, state: state, detail: "", start: "2026-10-24T23:00:00Z",
                     home: LiveSide(name: "H", abbr: "H", score: 0), away: LiveSide(name: "A", abbr: "A", score: 0)) }
        let leg = { (label: String, key: String, s: LegStatus) in LegLive(label: label, status: s, gameKey: key) }
        let a = g("nba:1", "in"), b = g("nba:2", "post")
        let bets: [(id: String, live: BetLive)] = [
            ("dead", BetLive(games: [a, b], legs: [leg("X", "nba:2", .lost), leg("Y", "nba:1", .live)], status: "lost", hit: 0, total: 2)),
            ("won", BetLive(games: [b], legs: [leg("Z", "nba:2", .won)], status: "won", hit: 1, total: 1)),
            ("alive", BetLive(games: [a], legs: [leg("W", "nba:1", .live)], status: "live", hit: 0, total: 1)),
        ]
        let tiles = GameDay.wallTiles(bets, names: ["dead": "d", "won": "w", "alive": "a"])
        XCTAssertEqual(tiles.map(\.game.key), ["nba:1"])
        XCTAssertEqual(tiles[0].legs.map(\.bet), ["a"])
    }
}
