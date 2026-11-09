import Foundation

// "Open in FanDuel" (web/lib/fanduel.ts): links go to the New York host so FanDuel skips "pick your state",
// and FanDuel's app scheme puts the bet in its betslip (Mike's iPhone tests, Oct 6). Bets are only added
// to the betslip; Mike reviews and places them in FanDuel.
enum FanDuel {
    static let host = "https://ny.sportsbook.fanduel.com"

    static func nyLink(_ u: String) -> String {
        u.replacingOccurrences(of: #"^https?://(?:[a-z]{2}\.)?sportsbook\.fanduel\.com"#, with: host, options: .regularExpression)
    }

    /// The web app's hand-off page for parlays (web/public/fd.html).
    static let handoffPage = "https://betlab.example.app/fd.html"

    /// A parlay goes through the hand-off page (Oct 15): FanDuel wants marketId[0]=..&selectionId[0]=.., its app needs
    /// the brackets as they are, and iOS percent-encodes them in any URL (marketId%5B0%5D: FanDuel opened with an empty
    /// betslip). Safari keeps them, so the page gets each leg as m=..&s=.. and opens FanDuel's app from there.
    static func handoff(_ link: String) -> URL? {
        guard link.contains("marketId["),
              let re = try? NSRegularExpression(pattern: #"marketId\[(\d+)\]=([^&]*)&selectionId\[\d+\]=([^&]*)"#) else { return nil }
        var items: [URLQueryItem] = []
        for m in re.matches(in: link, range: NSRange(link.startIndex..., in: link)) {
            let part = { (i: Int) in Range(m.range(at: i), in: link).map { String(link[$0]).removingPercentEncoding ?? "" } ?? "" }
            items += [URLQueryItem(name: "m", value: part(2)), URLQueryItem(name: "s", value: part(3))]
        }
        guard !items.isEmpty, var c = URLComponents(string: handoffPage) else { return nil }
        c.queryItems = items
        return c.url
    }

    /// The app link and the web link to fall back on.
    static func links(_ raw: String?) -> (app: URL, web: URL)? {
        guard let raw, !raw.isEmpty else { return nil }
        let web = nyLink(raw)
        if let page = handoff(web) { return (page, page) }
        let app = web.replacingOccurrences(of: #"^https?://"#, with: "fanduelsportsbook://", options: .regularExpression)
        guard let a = URL(string: app), let w = URL(string: web) else { return nil }
        return (a, w)
    }
}
