import XCTest
@testable import BetLab

/// Learn's calculators keep the web's math (components/me/Calculators.tsx); reference values computed with Node.
final class MoreTests: XCTestCase {
    func testSeededGeneratorMatchesTheWeb() {
        var r = Calc.Mulberry32(seed: 7)
        XCTAssertEqual(r.next(), 0.011704753153, accuracy: 1e-12)
        XCTAssertEqual(r.next(), 0.061958257575, accuracy: 1e-12)
        XCTAssertEqual(r.next(), 0.976907632779, accuracy: 1e-12)
    }

    func testPowerDevig() {
        let f = Calc.devigPower([-150, 130])
        XCTAssertEqual(f[0], 0.583982635036, accuracy: 1e-9)
        XCTAssertEqual(f[1], 0.416017364964, accuracy: 1e-9)
        XCTAssertEqual(Calc.devigPower([-110, -110])[0], 0.5, accuracy: 1e-9)
    }

    func testEvAndKelly() {
        XCTAssertEqual(Calc.ev(0.55, -110), 0.55 * (100.0 / 110) - 0.45, accuracy: 1e-12)
        XCTAssertEqual(Calc.kelly(0.5, -110), 0)
        XCTAssertGreaterThan(Calc.kelly(0.55, -110), 0)
    }

    @MainActor func testPushEndpointMatchesTheDatabaseRule() {
        // migration 0011: ^apns:(sandbox|production):[0-9a-f]{32,200}$ (test builds are Debug, so sandbox)
        let e = Push.endpoint(Data([0xAB, 0x01, 0xFF] + Array(repeating: 0x10, count: 29)))
        XCTAssertTrue(e.hasPrefix("apns:sandbox:ab01ff"))
        XCTAssertNotNil(e.range(of: "^apns:(sandbox|production):[0-9a-f]{32,200}$", options: .regularExpression))
    }

    func testOwnerIdComesFromTheToken() {
        // header.payload.signature with payload {"sub":"abc"}
        let payload = Data(#"{"sub":"abc"}"#.utf8).base64EncodedString().replacingOccurrences(of: "=", with: "")
        let s = Session(accessToken: "x.\(payload).y", refreshToken: "r", expiresAt: Date(), email: nil)
        XCTAssertEqual(s.userId, "abc")
    }
}
