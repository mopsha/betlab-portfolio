import Foundation

// "Open in Novig" (web/lib/novig.ts, Oct 28): novig.com has no universal links, so iOS kept the order-slip link in a
// browser. Novig's app answers to novigapp:// and reads the same events/<outcome ids>/<partner>/<amount> path into its
// order slip; the web link is the fallback when the app isn't installed.
enum Novig {
    static let scheme = "novigapp://"

    /// novig.com/events/<ids>/oddsapi/5 -> novigapp://events/<ids>/oddsapi/5, with the web link to fall back on.
    static func links(_ raw: String?) -> (app: URL, web: URL)? {
        guard let raw, let web = URL(string: raw),
              let r = raw.range(of: #"^https?://(?:www\.)?novig\.com/(events/[^?#]+)"#, options: .regularExpression),
              let app = URL(string: scheme + raw[r].replacingOccurrences(of: #"^https?://(?:www\.)?novig\.com/"#, with: "",
                                                                            options: .regularExpression)) else { return nil }
        return (app, web)
    }
}

/// Novig's exact parlay price (web lib/novig.ts and api/novig, worker novig_parlays.py): its free parlay pricer answers
/// 2-20 outcome ids with one price, the parlay's chance. Oct 30: it moved to /rfq/v2/quote/unauthenticated ({outcomeIds}
/// in, {price, expiresAt} out; the Oct 28 route was gone by Oct 29) and no longer says the largest payout. 400: won't
/// combine; 404: no price right now (both final); a 429 or a failure is asked again (3 tries).
struct NovigQuote: Hashable {
    let price: Double
    let p: Double
    let stakeMax: Double?

    static let pricer = URL(string: "https://api.novig.com/rfq/v2/quote/unauthenticated")!

    /// The pricer's answer as American odds; nil when it priced nothing.
    static func parse(_ data: Data) -> NovigQuote? {
        guard let q = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let p = Double("\(q["price"] ?? "")"), p > 0, p < 1 else { return nil }
        let price = (p >= 0.5 ? -100 * p / (1 - p) : 100 * (1 - p) / p).rounded()
        return NovigQuote(price: price, p: p, stakeMax: nil)
    }

    static func fetch(_ ids: [String]) async -> NovigQuote? {
        guard ids.count >= 2 else { return nil }
        var req = URLRequest(url: pricer)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["outcomeIds": ids])
        for i in 0..<3 {
            var wait: UInt64 = 800_000_000
            if let (data, resp) = try? await URLSession.shared.data(for: req), let http = resp as? HTTPURLResponse {
                if http.statusCode < 300, let q = parse(data) { return q }
                let msg = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])?["message"] as? String ?? ""
                if http.statusCode == 400 || (http.statusCode == 404 && !msg.hasPrefix("Cannot ")) { return nil }
                if http.statusCode == 429 {
                    wait = UInt64(min(Double(http.value(forHTTPHeaderField: "Retry-After") ?? "") ?? 1, 5) * 1_000_000_000)
                }
            }
            if i < 2 { try? await Task.sleep(nanoseconds: wait) }
        }
        return nil
    }
}
