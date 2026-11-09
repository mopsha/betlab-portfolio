import Foundation

/// The demo mode (the overhaul's Phase 1a, Nov 6): launched with `-demo <path to a fixture>`, the app reads every table
/// from that file instead of Supabase, signs in as no one, and writes nothing, so simulator checks never touch a real
/// account. The fixture is the web preview's own (`python scripts/sample_fixture.py` writes web/fixtures/today.json;
/// sample bets go in its `my_bets`, a function's answer under the function's name, e.g. `friend_bets`). The simulator
/// reads the Mac's files, so the path is the Mac's. Normal launches never set it.
enum Demo {
    static let path = UserDefaults.standard.string(forKey: "demo")
    static var on: Bool { path?.isEmpty == false }
    static let userId = "00000000-0000-4000-8000-00000000de70"

    /// A session that never expires and is never saved; its token carries only the demo user's id.
    static var session: Session {
        let claims = Data(#"{"sub":"\#(userId)"}"#.utf8).base64EncodedString()
            .replacingOccurrences(of: "=", with: "").replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
        return Session(accessToken: "demo.\(claims).demo", refreshToken: "", expiresAt: .distantFuture, email: "demo@betlab.local")
    }

    private static let tables: [String: [[String: Any]]] = {
        guard let path, let d = FileManager.default.contents(atPath: path),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
        var out: [String: [[String: Any]]] = [:]
        for (k, v) in o { if let rows = v as? [[String: Any]] { out[k] = rows } }
        // the web fixture keeps the account's bets as my_bets; the bets table is the same rows
        if out["bets"] == nil { out["bets"] = out["my_bets"] }
        return out
    }()

    /// A table's rows as the REST API would answer `f` (every column; `select` is ignored).
    static func rows(_ table: String, _ f: SupabaseClient.Filter) throws -> Data {
        var rows = (tables[table] ?? []).filter { r in
            f.eq.allSatisfy { k, v in text(r[k]) == v }
                && (f.inList.map { k, vs in vs.contains(text(r[k]) ?? "\u{0}") } ?? true)
                && (f.from.map { k, d in date(r[k]).map { $0 >= d } ?? false } ?? true)
                && (f.to.map { k, d in date(r[k]).map { $0 < d } ?? false } ?? true)
                && (f.gt.map { k, d in date(r[k]).map { $0 > d } ?? false } ?? true)
                && (f.active.map { (r["active"] as? Bool) == $0 } ?? true)
        }
        if let (col, asc) = f.order {
            rows.sort { a, b in
                let x = text(a[col]) ?? "", y = text(b[col]) ?? ""
                if let p = Double(x), let q = Double(y) { return asc ? p < q : p > q }
                return asc ? x < y : x > y
            }
        }
        // computed columns the app asks for ("matchup:body->>matchup", "part:body->>part"): PostgREST reads them out of a
        // JSON column; without them Build's game cards came back with no names in demo mode
        let picks: [(alias: String, col: String, key: String)] = f.select.split(separator: ",").compactMap { item in
            let t = item.trimmingCharacters(in: .whitespaces)
            guard let arrow = t.range(of: "->>") else { return nil }
            let lhs = String(t[..<arrow.lowerBound]), key = String(t[arrow.upperBound...])
            let parts = lhs.split(separator: ":", maxSplits: 1).map(String.init)
            return parts.count == 2 ? (parts[0], parts[1], key) : (key, parts[0], key)
        }
        if !picks.isEmpty {
            rows = rows.map { r in
                var x = r
                for p in picks { x[p.alias] = (r[p.col] as? [String: Any])?[p.key].map { text($0) ?? "\($0)" } ?? NSNull() }
                return x
            }
        }
        return try JSONSerialization.data(withJSONObject: Array(rows.prefix(f.limit)))
    }

    /// A function's answer: the fixture's rows under its name, else none.
    static func rpc(_ fn: String) throws -> Data {
        try JSONSerialization.data(withJSONObject: tables[fn] ?? [])
    }

    private static func text(_ v: Any?) -> String? {
        if let s = v as? String { return s }
        guard let n = v as? NSNumber else { return nil }
        if CFGetTypeID(n) == CFBooleanGetTypeID() { return String(n.boolValue) }     // JSON's true, not the number 1
        return n.doubleValue == n.doubleValue.rounded() ? String(n.intValue) : n.stringValue
    }

    private static func date(_ v: Any?) -> Date? { (v as? String).flatMap(Models.date) }
}
