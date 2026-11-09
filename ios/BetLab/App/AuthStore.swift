import Foundation

struct Session: Codable, Equatable {
    var accessToken: String
    var refreshToken: String
    var expiresAt: Date
    var email: String?

    /// The account's id, read from the access token (a JWT's `sub`).
    var userId: String? {
        let parts = accessToken.split(separator: ".")
        guard parts.count > 1 else { return nil }
        var b64 = String(parts[1]).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        while b64.count % 4 != 0 { b64 += "=" }
        guard let d = Data(base64Encoded: b64), let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return nil }
        return o["sub"] as? String
    }
}

/// Mike's account: Plan and Reviews are his work with Claude, so other accounts don't see them (web lib/owner.ts).
let ownerUserId = "00000000-0000-4000-8000-000000000001"

struct AuthError: LocalizedError {
    let message: String
    /// Supabase Auth's answer, when it gave one: the HTTP status and its error code ("refresh_token_not_found").
    var status: Int? = nil
    var code: String? = nil
    var errorDescription: String? { message }

    /// The refresh token itself is no good (used, revoked, unknown): only this signs the account out.
    static let deadCodes: Set<String> = ["invalid_grant", "refresh_token_not_found", "refresh_token_already_used",
                                         "session_not_found", "session_expired"]
    var deadRefresh: Bool { (status == 400 || status == 401) && code.map(Self.deadCodes.contains) == true }
}

/// Supabase sign-in, as on the web app's login page: email and password, or a 6-digit code sent by email
/// (sign-ups are off, so only the invited account works). Talks to Supabase Auth's REST API directly.
@MainActor
final class AuthStore: ObservableObject {
    /// The app's one sign-in, shared with what runs without a screen (Live Activities' tokens).
    static let shared = AuthStore()
    @Published private(set) var session: Session?
    private let account = "session"
    private var refreshing: Task<Session, Error>?

    init() {
        if Demo.on { session = Demo.session; return }       // never the saved account (Demo.swift)
        if let data = Keychain.load(account: account), let s = try? JSONDecoder().decode(Session.self, from: data) {
            session = s
        }
    }

    func signIn(email: String, password: String) async throws {
        let body = try await post("token?grant_type=password", ["email": email, "password": password])
        try store(body, email: email)
    }

    func sendCode(email: String) async throws {
        _ = try await post("otp", ["email": email, "create_user": false])
    }

    func verify(email: String, code: String) async throws {
        let body = try await post("verify", ["email": email, "token": code, "type": "email"])
        try store(body, email: email)
    }

    func signOut() {
        if Demo.on { return }        // the real account's saved session stays untouched
        session = nil
        Keychain.delete(account: account)
        ResponseCache.clear()                // one account's bets must not open for the next
        // nor its widget, or the filters its settings set until the next account's first load (Nov 9)
        WidgetFeed.clear()
        Bans.current = []
        BooksOff.current = []
        Watch.current = []
    }

    /// A token that's good for at least another minute, refreshed when needed (one refresh at a time).
    func accessToken() async throws -> String {
        guard let s = session else { throw AuthError(message: "Signed out") }
        if s.expiresAt.timeIntervalSinceNow > 60 { return s.accessToken }
        if let task = refreshing { return try await task.value.accessToken }
        let task = Task { () throws -> Session in
            defer { refreshing = nil }
            do {
                let body = try await post("token?grant_type=refresh_token", ["refresh_token": s.refreshToken])
                try store(body, email: s.email)
            } catch let e as AuthError where e.deadRefresh {
                signOut()       // a refresh token that's been used or revoked can't come back
                throw e
            }
            // anything else (a 5xx, a 429, the network, an odd body) keeps the session: the next call tries again
            // (Nov 9: one 502 from Supabase Auth signed the account out and cleared its saved data)
            return session!
        }
        refreshing = task
        return try await task.value.accessToken
    }

    // MARK: - plumbing

    private func store(_ body: [String: Any], email: String?) throws {
        guard let access = body["access_token"] as? String, let refresh = body["refresh_token"] as? String else {
            throw AuthError(message: "Supabase didn't return a session")
        }
        let expiresIn = (body["expires_in"] as? Double) ?? 3600
        let s = Session(accessToken: access, refreshToken: refresh,
                        expiresAt: Date().addingTimeInterval(expiresIn), email: email)
        session = s
        if let data = try? JSONEncoder().encode(s) { Keychain.save(data, account: account) }
    }

    private func post(_ path: String, _ json: [String: Any]) async throws -> [String: Any] {
        guard let base = Config.supabaseURL, let url = URL(string: "auth/v1/" + path, relativeTo: base) else {
            throw AuthError(message: "The app isn't set up")
        }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(Config.anonKey, forHTTPHeaderField: "apikey")
        req.httpBody = try JSONSerialization.data(withJSONObject: json)
        let (data, resp) = try await URLSession.shared.data(for: req)
        let body = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let msg = body["error_description"] ?? body["msg"] ?? body["message"] ?? body["error"]
            throw AuthError(message: (msg as? String) ?? "Sign-in failed", status: (resp as? HTTPURLResponse)?.statusCode,
                            code: (body["error_code"] as? String) ?? (body["error"] as? String))
        }
        return body
    }
}
