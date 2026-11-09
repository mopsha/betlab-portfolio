import Foundation

/// Reads tables through Supabase's REST API as the signed-in user, so row-level security applies
/// (the same reads as web/lib/data.ts).
struct SupabaseClient {
    let token: () async throws -> String
    /// Reads only what's saved on this phone (ResponseCache): `saved` opens a screen at once, before the real read.
    var savedOnly = false
    var saved: SupabaseClient { var c = self; c.savedOnly = true; return c }

    static func isOffline(_ error: Error) -> Bool {
        guard let u = error as? URLError else { return false }
        return [.notConnectedToInternet, .networkConnectionLost, .timedOut, .cannotFindHost, .cannotConnectToHost, .dataNotAllowed,
                .internationalRoamingOff].contains(u.code)
    }

    struct Filter {
        var eq: [(String, String)] = []
        var from: (String, Date)? = nil      // column >= date
        var to: (String, Date)? = nil        // column < date
        var active: Bool? = nil
        var select = "*"
        var order: (String, ascending: Bool)? = nil
        var gt: (String, Date)? = nil        // column > date
        var limit = 5000
        var inList: (String, [String])? = nil    // column in (values)
    }

    /// `plain` keeps the JSON's own keys (for free-form bodies); otherwise snake_case becomes camelCase.
    func rows<T: Decodable>(_ table: String, _ f: Filter = Filter(), as: T.Type = T.self, plain: Bool = false) async throws -> [T] {
        if Demo.on { return try (plain ? JSON.plainDecoder : Models.decoder).decode([T].self, from: Demo.rows(table, f)) }
        guard let base = Config.supabaseURL,
              var comps = URLComponents(url: base.appendingPathComponent("rest/v1/\(table)"), resolvingAgainstBaseURL: false)
        else { throw AuthError(message: "The app isn't set up") }
        var q = [URLQueryItem(name: "select", value: f.select), URLQueryItem(name: "limit", value: String(f.limit))]
        if let (col, asc) = f.order { q.append(URLQueryItem(name: "order", value: "\(col).\(asc ? "asc" : "desc")")) }
        for (k, v) in f.eq { q.append(URLQueryItem(name: k, value: "eq.\(v)")) }
        if let (k, d) = f.from { q.append(URLQueryItem(name: k, value: "gte.\(Self.iso(d))")) }
        if let (k, d) = f.to { q.append(URLQueryItem(name: k, value: "lt.\(Self.iso(d))")) }
        if let (k, d) = f.gt { q.append(URLQueryItem(name: k, value: "gt.\(Self.iso(d))")) }
        if let a = f.active { q.append(URLQueryItem(name: "active", value: "eq.\(a)")) }
        if let (k, vs) = f.inList { q.append(URLQueryItem(name: k, value: "in.(" + vs.map { "\"\($0)\"" }.joined(separator: ",") + ")")) }
        comps.queryItems = q
        let url = comps.url!
        let decode = { (d: Data) throws -> [T] in try (plain ? JSON.plainDecoder : Models.decoder).decode([T].self, from: d) }
        if savedOnly {
            guard let d = ResponseCache.read(url) else { throw AuthError(message: "\(table): nothing saved") }
            return try decode(d)
        }
        let data: Data
        do {
            var req = URLRequest(url: url)
            req.cachePolicy = .reloadIgnoringLocalCacheData      // every read is the database as it is now
            req.setValue(Config.anonKey, forHTTPHeaderField: "apikey")
            req.setValue("Bearer \(try await token())", forHTTPHeaderField: "Authorization")
            let (got, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                let body = (try? JSONSerialization.jsonObject(with: got)) as? [String: Any]
                throw AuthError(message: "\(table): \((body?["message"] as? String) ?? "request failed")")
            }
            data = got
        } catch where Self.isOffline(error) {
            guard let d = ResponseCache.read(url) else { throw error }     // no signal: what this screen last showed
            return try decode(d)
        }
        ResponseCache.write(url, data)
        return try decode(data)
    }

    /// Call a database function (Postgres RPC) as the user; its rows come back like a table's (`plain`: keys as sent).
    func rpc<T: Decodable>(_ fn: String, _ args: [String: Any?] = [:], as: T.Type = T.self, plain: Bool = false) async throws -> [T] {
        if Demo.on { return try (plain ? JSON.plainDecoder : Models.decoder).decode([T].self, from: Demo.rpc(fn)) }
        guard let base = Config.supabaseURL else { throw AuthError(message: "The app isn't set up") }
        var req = URLRequest(url: base.appendingPathComponent("rest/v1/rpc/\(fn)"))
        req.httpMethod = "POST"
        req.setValue(Config.anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(try await token())", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: args.mapValues { $0 ?? NSNull() })
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let msg = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])?["message"] as? String ?? ""
            throw AuthError(message: Marking.friendly(msg))
        }
        let dec = plain ? JSON.plainDecoder : Models.decoder
        if data.first != UInt8(ascii: "[") {    // a scalar answer (accept_friend: true or null)
            return (try? dec.decode(T.self, from: data)).map { [$0] } ?? []
        }
        return try dec.decode([T].self, from: data)
    }

    /// Insert one row (as the signed-in user: `user_id` defaults to auth.uid()).
    func insert(_ table: String, _ row: [String: Any?]) async throws {
        try await send("POST", table, [], body: row)
    }

    /// Insert or replace one row on a unique key (as the user), e.g. `user_id,sgp_id`.
    func upsert(_ table: String, _ row: [String: Any?], onConflict: String) async throws {
        try await send("POST", table, [], body: row, query: [URLQueryItem(name: "on_conflict", value: onConflict)],
                       prefer: "resolution=merge-duplicates,return=minimal")
    }

    /// Update the rows matching `eq` with `change`.
    func update(_ table: String, eq: [(String, String)], _ change: [String: Any?]) async throws {
        try await send("PATCH", table, eq, body: change)
    }

    /// Update the rows matching `eq` with `change`, and say how many it changed: a conditional update (Nov 9: a promo's split
    /// happens only while it is still open at the amount read) checks the count, not just the absence of an error.
    @discardableResult
    func updateCount(_ table: String, eq: [(String, String)], _ change: [String: Any?]) async throws -> Int {
        if Demo.on { return 1 }
        guard let base = Config.supabaseURL,
              var comps = URLComponents(url: base.appendingPathComponent("rest/v1/\(table)"), resolvingAgainstBaseURL: false)
        else { throw AuthError(message: "The app isn't set up") }
        comps.queryItems = eq.map { URLQueryItem(name: $0.0, value: "eq.\($0.1)") } + [URLQueryItem(name: "select", value: "*")]
        var req = URLRequest(url: comps.url!)
        req.cachePolicy = .reloadIgnoringLocalCacheData
        req.httpMethod = "PATCH"
        req.setValue(Config.anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(try await token())", forHTTPHeaderField: "Authorization")
        req.setValue("return=representation", forHTTPHeaderField: "Prefer")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: change.mapValues { $0 ?? NSNull() })
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let msg = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])?["message"] as? String ?? ""
            throw AuthError(message: Marking.friendly(msg))
        }
        return ((try? JSONSerialization.jsonObject(with: data)) as? [Any])?.count ?? 0
    }

    /// Delete the rows matching `eq` (row-level security limits it to the user's own rows).
    func delete(_ table: String, eq: [(String, String)]) async throws {
        try await send("DELETE", table, eq, body: nil)
    }

    private func send(_ method: String, _ table: String, _ eq: [(String, String)], body: [String: Any?]?,
                      query: [URLQueryItem] = [], prefer: String = "return=minimal") async throws {
        if Demo.on { return }      // the demo mode writes nothing
        guard let base = Config.supabaseURL,
              var comps = URLComponents(url: base.appendingPathComponent("rest/v1/\(table)"), resolvingAgainstBaseURL: false)
        else { throw AuthError(message: "The app isn't set up") }
        let items = eq.map { URLQueryItem(name: $0.0, value: "eq.\($0.1)") } + query
        if !items.isEmpty { comps.queryItems = items }
        var req = URLRequest(url: comps.url!)
        req.cachePolicy = .reloadIgnoringLocalCacheData      // every read is the database as it is now
        req.httpMethod = method
        req.setValue(Config.anonKey, forHTTPHeaderField: "apikey")
        req.setValue("Bearer \(try await token())", forHTTPHeaderField: "Authorization")
        req.setValue(prefer, forHTTPHeaderField: "Prefer")
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body.mapValues { $0 ?? NSNull() }, options: [.fragmentsAllowed])
        }
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let msg = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])?["message"] as? String ?? ""
            throw AuthError(message: Marking.friendly(msg))
        }
    }

    /// One document from the `docs` table (collection + doc_id), its body only. Free-form `JSON` bodies keep their own keys.
    func doc<T: Decodable>(_ collection: String, _ id: String, as: T.Type = T.self) async throws -> T? {
        let r: [DocRow<T>] = try await rows("docs", Filter(eq: [("collection", collection), ("doc_id", id)], select: "body"), plain: T.self == JSON.self)
        return r.first?.body
    }

    private static func iso(_ d: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: d)
    }
}

private struct DocRow<T: Decodable>: Decodable { let body: T }
