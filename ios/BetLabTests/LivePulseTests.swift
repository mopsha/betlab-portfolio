import XCTest
@testable import BetLab

final class LivePulseTests: XCTestCase {
    func testTheSocketURLIsRealtimes() {
        let u = LivePulse.url(base: URL(string: "https://x.supabase.co"), key: "k")?.absoluteString
        XCTAssertEqual(u, "wss://x.supabase.co/realtime/v1/websocket?apikey=k&vsn=1.0.0")
    }

    func testJoiningAsksForThePulseTableWithTheToken() throws {
        let o = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(LivePulse.join(token: "jwt").utf8)) as? [String: Any])
        XCTAssertEqual(o["topic"] as? String, LivePulse.topic)
        XCTAssertEqual(o["event"] as? String, "phx_join")
        let payload = try XCTUnwrap(o["payload"] as? [String: Any])
        XCTAssertEqual(payload["access_token"] as? String, "jwt")
        let changes = (payload["config"] as? [String: Any])?["postgres_changes"] as? [[String: Any]]
        XCTAssertEqual(changes?.first?["table"] as? String, "app_pulse")
    }

    func testWhatTheServerSaysMeans() {
        XCTAssertEqual(LivePulse.read(#"{"event":"postgres_changes","payload":{}}"#), .change)
        XCTAssertEqual(LivePulse.read(#"{"event":"phx_close","payload":{}}"#), .closed)
        XCTAssertEqual(LivePulse.read(#"{"event":"phx_reply","payload":{"status":"error"}}"#), .closed)
        XCTAssertEqual(LivePulse.read(#"{"event":"system","payload":{"status":"error"}}"#), .closed)
        XCTAssertEqual(LivePulse.read(#"{"event":"phx_reply","payload":{"status":"ok"}}"#), .other)
        XCTAssertEqual(LivePulse.read("not json"), .other)
    }
}
