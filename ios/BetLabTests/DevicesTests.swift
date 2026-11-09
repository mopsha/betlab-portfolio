import XCTest
@testable import BetLab

final class DevicesTests: XCTestCase {
    func testASessionsNameFromItsUserAgent() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("tests/fixtures/devices.json")
        let f = try JSON.plainDecoder.decode(JSON.self, from: Data(contentsOf: url))
        for c in f["cases"].array { XCTAssertEqual(DeviceSession.name(c[0].string), c[1].string, c[0].string ?? "") }
    }

    func testTheLockAsksOnLaunchAndAfterFiveMinutesAwayOnlyWhenOn() {
        let now = Date()
        XCTAssertFalse(AppLock.needsUnlock(enabled: false, leftAt: nil, now: now))
        XCTAssertTrue(AppLock.needsUnlock(enabled: true, leftAt: nil, now: now))
        XCTAssertFalse(AppLock.needsUnlock(enabled: true, leftAt: now.addingTimeInterval(-299), now: now))
        XCTAssertTrue(AppLock.needsUnlock(enabled: true, leftAt: now.addingTimeInterval(-300), now: now))
    }
}
