import XCTest
@testable import BetLab

final class ResponseCacheTests: XCTestCase {
    private func url(_ q: String) -> URL { URL(string: "https://x.supabase.co/rest/v1/games?select=*&\(q)")! }

    override func setUp() {
        ResponseCache.directory = FileManager.default.temporaryDirectory.appendingPathComponent("rows-\(UUID().uuidString)")
    }

    func testADateCountsByItsDaySoTodaysHomeIsOneFile() {
        XCTAssertEqual(ResponseCache.key(url("start=gte.2026-11-04T10:00:00Z")), ResponseCache.key(url("start=gte.2026-11-04T22:15:30Z")))
        XCTAssertNotEqual(ResponseCache.key(url("start=gte.2026-11-04T10:00:00Z")), ResponseCache.key(url("start=gte.2026-11-05T10:00:00Z")))
        XCTAssertNotEqual(ResponseCache.key(url("sport=eq.nba")), ResponseCache.key(url("sport=eq.nhl")))
    }

    func testWhatsSavedReadsBackAndSignOutClearsIt() {
        let u = url("sport=eq.nba")
        XCTAssertNil(ResponseCache.read(u))
        ResponseCache.write(u, Data("[1]".utf8))
        XCTAssertEqual(ResponseCache.read(u), Data("[1]".utf8))
        ResponseCache.clear()
        XCTAssertNil(ResponseCache.read(u))
    }

    func testOldFilesGo() {
        let u = url("sport=eq.nba")
        ResponseCache.write(u, Data("[1]".utf8))
        ResponseCache.prune(now: Date().addingTimeInterval(13 * 86400))
        XCTAssertNotNil(ResponseCache.read(u))
        ResponseCache.prune(now: Date().addingTimeInterval(15 * 86400))
        XCTAssertNil(ResponseCache.read(u))
    }

    func testOnlyAMissingConnectionCountsAsOffline() {
        XCTAssertTrue(SupabaseClient.isOffline(URLError(.notConnectedToInternet)))
        XCTAssertFalse(SupabaseClient.isOffline(URLError(.badServerResponse)))
        XCTAssertFalse(SupabaseClient.isOffline(AuthError(message: "games: denied")))
    }
}
