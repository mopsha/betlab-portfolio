import AppIntents

// Siri (Mike's W11, Oct 25): "How's my parlay?" asks Ask BetLab, the chat over your bets (ChatView, the web's /api/chat
// with the app's bearer token), and speaks its answer. App Shortcuts need no setup: the phrases work once the app is
// installed. Until ANTHROPIC_API_KEY is on the web service the chat answers 503 and Siri says so.

struct HowsMyParlayIntent: AppIntent {
    static let title: LocalizedStringResource = "How's my parlay?"
    static let description = IntentDescription("Ask BetLab how your open bets are doing right now.")
    static let openAppWhenRun = false

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let answer = await Ask.once("How are my open bets doing right now? Answer in two or three short spoken sentences: which legs are live, which hit, which are behind.")
        return .result(dialog: IntentDialog(stringLiteral: answer))
    }
}

struct AskBetLabIntent: AppIntent {
    static let title: LocalizedStringResource = "Ask BetLab"
    static let description = IntentDescription("Ask BetLab a question about your bets, today's board or a game.")
    static let openAppWhenRun = false

    @Parameter(title: "Question") var question: String

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        .result(dialog: IntentDialog(stringLiteral: await Ask.once(question + " (Answer briefly, to be read aloud.)")))
    }
}

struct BetLabShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: HowsMyParlayIntent(), phrases: ["How's my parlay in \(.applicationName)", "How are my bets doing in \(.applicationName)",
                                                           "Check my parlay with \(.applicationName)"],
                    shortTitle: "How's my parlay?", systemImageName: "chart.line.uptrend.xyaxis")
        AppShortcut(intent: AskBetLabIntent(), phrases: ["Ask \(.applicationName)"], shortTitle: "Ask BetLab", systemImageName: "bubble.left")
    }
}

/// One question to the chat, its answer as plain words for Siri (markdown bold, list dashes and links dropped).
enum Ask {
    @MainActor
    static func once(_ question: String) async -> String {
        let auth = AuthStore()
        guard auth.session != nil else { return "Open BetLab and sign in first." }
        do {
            var req = URLRequest(url: Config.webURL.appendingPathComponent("api/chat"))
            req.httpMethod = "POST"; req.timeoutInterval = 60
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue("Bearer \(try await auth.accessToken())", forHTTPHeaderField: "Authorization")
            req.httpBody = try JSONSerialization.data(withJSONObject: ["messages": [["role": "user", "content": question]]])
            let (data, resp) = try await URLSession.shared.data(for: req)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            let j = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            if code == 503 { return "BetLab's chat is waiting for its key. Add it on the web service, then ask again." }
            guard code == 200, let a = j?["answer"] as? String else { return (j?["error"] as? String) ?? "BetLab didn't answer. Try again in a minute." }
            return spoken(a)
        } catch {
            return "I couldn't reach BetLab. Check your connection."
        }
    }

    /// Markdown as speech: **bold** and [links](/x) to their text, list markers and headings off, lines joined.
    static func spoken(_ s: String) -> String {
        ChatFormat.blocks(s).map { b in b.spans.map(\.text).joined() }.joined(separator: " ")
    }
}
