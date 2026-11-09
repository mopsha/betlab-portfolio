import Foundation

/// Live updates (Nov 4; migration 0033): hears from Supabase Realtime that something changed (`app_pulse`, its row-level
/// security decides whose) so the app reads it at once. No SDK in this app, so this speaks Realtime's small protocol over a
/// web socket: join one channel, heartbeat every 25 s, keep the token fresh. Only in the foreground; the 5-minute reload stays as
/// the fallback. Scores aren't here: ESPN has no feed to hear, so the tracker keeps checking every 20 seconds.
enum LivePulse {
    static let topic = "realtime:betlab-pulse"
    private static let beat: Duration = .seconds(25)
    private static let beatsPerToken = 10

    static func url(base: URL?, key: String) -> URL? {
        guard let base, var c = URLComponents(url: base.appendingPathComponent("realtime/v1/websocket"), resolvingAgainstBaseURL: false)
        else { return nil }
        c.scheme = c.scheme == "http" ? "ws" : "wss"
        c.queryItems = [URLQueryItem(name: "apikey", value: key), URLQueryItem(name: "vsn", value: "1.0.0")]
        return c.url
    }

    private static func message(_ topic: String, _ event: String, _ payload: [String: Any], ref: Int) -> String {
        let body: [String: Any] = ["topic": topic, "event": event, "payload": payload, "ref": String(ref)]
        return (try? JSONSerialization.data(withJSONObject: body)).flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
    }

    static func join(token: String) -> String {
        let change: [String: Any] = ["event": "*", "schema": "public", "table": "app_pulse"]
        let config: [String: Any] = ["broadcast": ["ack": false, "self": false], "presence": ["key": ""],
                                     "postgres_changes": [change], "private": false]
        return message(topic, "phx_join", ["config": config, "access_token": token], ref: 1)
    }

    static func heartbeat(ref: Int) -> String { message("phoenix", "heartbeat", [:], ref: ref) }
    static func newToken(_ token: String, ref: Int) -> String { message(topic, "access_token", ["access_token": token], ref: ref) }

    enum Heard: Equatable { case change, closed, other }

    /// What one message from the server means. A refused join or a closed channel means connect again.
    static func read(_ text: String) -> Heard {
        guard let o = (try? JSONSerialization.jsonObject(with: Data(text.utf8))) as? [String: Any], let event = o["event"] as? String
        else { return .other }
        if event == "postgres_changes" { return .change }
        if event == "phx_close" || event == "phx_error" { return .closed }
        if event == "system", (o["payload"] as? [String: Any])?["status"] as? String == "error" { return .closed }
        if event == "phx_reply", (o["payload"] as? [String: Any])?["status"] as? String == "error" { return .closed }
        return .other
    }

    private struct Closed: Error {}

    /// Stays connected until cancelled, connecting again after a failure (5 s, doubling to a minute).
    static func run(token: @escaping @Sendable () async throws -> String, onChange: @escaping @MainActor () -> Void) async {
        guard !Demo.on, let url = url(base: Config.supabaseURL, key: Config.anonKey) else { return }     // the demo has no database
        var wait = 5, again = false
        while !Task.isCancelled {
            let started = Date()
            let socket = URLSession.shared.webSocketTask(with: url)
            socket.resume()
            await withTaskCancellationHandler {
                try? await connection(socket, token: token, again: again, onChange: onChange)
            } onCancel: {
                socket.cancel(with: .goingAway, reason: nil)
            }
            socket.cancel(with: .goingAway, reason: nil)
            again = true
            if Date().timeIntervalSince(started) > 120 { wait = 5 }       // it had been working: not a failing server
            try? await Task.sleep(for: .seconds(wait))
            wait = min(wait * 2, 60)
        }
    }

    private static func connection(_ socket: URLSessionWebSocketTask, token: @escaping @Sendable () async throws -> String,
                                   again: Bool, onChange: @escaping @MainActor () -> Void) async throws {
        try await socket.send(.string(join(token: try await token())))
        if again { await onChange() }       // back after a drop: what changed while it was away was never heard
        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask {
                while true {
                    guard case .string(let text) = try await socket.receive() else { continue }
                    switch read(text) {
                    case .change: await onChange()
                    case .closed: throw Closed()
                    case .other: break
                    }
                }
            }
            group.addTask {
                var ref = 2
                while true {
                    try await Task.sleep(for: beat)
                    try await socket.send(.string(heartbeat(ref: ref)))
                    ref += 1
                    if ref % beatsPerToken == 0 { try await socket.send(.string(newToken(try await token(), ref: ref))); ref += 1 }
                }
            }
            try await group.next()         // either side failing ends the connection
            group.cancelAll()
        }
    }
}
