import SwiftUI

// Ask BetLab (Mike's W22, Oct 24), as web components/me/Chat.tsx: chat with Claude over your bets, today's board and the
// games. The web's /api/chat answers (lib/chat.ts: four read-only tools under the user's own row-level security); the
// app sends its Supabase access token as a bearer token. The conversation stays on the device for this session only.
// The look (the overhaul, Nov 5): your messages as accent bubbles, BetLab's answers as plain text under its mark, the
// games an answer links to as cards (ChatCards.swift), and a field that floats over the page.

/// The chat's answers as display pieces (web lib/chat-format.ts): paragraphs and "- " lists, with **bold** and
/// [links](/path) inside. Only app paths and https links become links; anything else stays text.
enum ChatFormat {
    struct Span: Equatable { var text: String; var bold = false; var href: String? = nil }
    struct Block: Equatable { let kind: String; let spans: [Span] }     // p, li

    private static let inline = try! NSRegularExpression(pattern: #"\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\)"#)
    static func safeHref(_ h: String) -> String? { (h.hasPrefix("/") && !h.hasPrefix("//")) || h.hasPrefix("https://") ? h : nil }

    static func spans(_ line: String) -> [Span] {
        var out: [Span] = [], last = line.startIndex
        for m in inline.matches(in: line, range: NSRange(line.startIndex..., in: line)) {
            let r = Range(m.range, in: line)!
            if r.lowerBound > last { out.append(Span(text: String(line[last..<r.lowerBound]))) }
            if let b = Range(m.range(at: 1), in: line) { out.append(Span(text: String(line[b]), bold: true)) }
            else {
                let text = String(line[Range(m.range(at: 2), in: line)!]), href = safeHref(String(line[Range(m.range(at: 3), in: line)!]))
                out.append(href != nil ? Span(text: text, href: href) : Span(text: String(line[r])))
            }
            last = r.upperBound
        }
        if last < line.endIndex { out.append(Span(text: String(line[last...]))) }
        return out
    }

    static func blocks(_ text: String) -> [Block] {
        text.components(separatedBy: "\n").compactMap { raw in
            let line = raw.replacingOccurrences(of: #"\s+$"#, with: "", options: .regularExpression)
            guard !line.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
            if let r = line.range(of: #"^\s*(?:[-*•]|\d+\.)\s+"#, options: .regularExpression) {
                return Block(kind: "li", spans: spans(String(line[r.upperBound...])))
            }
            return Block(kind: "p", spans: spans(line.replacingOccurrences(of: #"^#+\s*"#, with: "", options: .regularExpression)))
        }
    }

    /// A block as text: bold kept, links tappable (an app path as betlab:/games/..., opened in the app).
    static func attributed(_ spans: [Span]) -> AttributedString {
        spans.reduce(into: AttributedString()) { out, s in
            var a = AttributedString(s.text)
            if s.bold { a.inlinePresentationIntent = .stronglyEmphasized }
            if let h = s.href { a.link = h.hasPrefix("/") ? URL(string: "betlab:" + h) : URL(string: h) }
            out += a
        }
    }
}

/// The conversation, kept in memory for this run of the app (leaving the screen and coming back keeps it).
@MainActor
final class ChatModel: ObservableObject {
    static let shared = ChatModel()
    struct Turn: Equatable, Identifiable { let role: String; let content: String; let id = UUID() }
    @Published var turns: [Turn] = []
    @Published var busy = false
    @Published var error: String?
    @Published var waiting = false       // 503: the web service has no ANTHROPIC_API_KEY yet

    func ask(_ q: String, token: () async throws -> String) async {
        let text = q.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !busy else { return }
        turns.append(Turn(role: "user", content: text))
        busy = true; error = nil
        defer { busy = false }
        do {
            var req = URLRequest(url: Config.webURL.appendingPathComponent("api/chat"))
            req.httpMethod = "POST"
            req.timeoutInterval = 130
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue("Bearer \(try await token())", forHTTPHeaderField: "Authorization")
            req.httpBody = try JSONSerialization.data(withJSONObject: ["messages": turns.map { ["role": $0.role, "content": $0.content] }])
            let (data, resp) = try await URLSession.shared.data(for: req)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            let j = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            if code == 200, let a = j?["answer"] as? String, !a.isEmpty {
                turns.append(Turn(role: "assistant", content: a)); waiting = false
            } else {
                waiting = code == 503
                error = (j?["error"] as? String) ?? (code == 401 ? "Sign in again." : "No answer came back: try again.")
            }
        } catch {
            self.error = "You look offline: try again."
        }
    }

    func clear() { turns = []; error = nil }
}

struct ChatView: View {
    @EnvironmentObject private var auth: AuthStore
    @EnvironmentObject private var store: BetStore
    @ObservedObject private var model = ChatModel.shared
    @StateObject private var games = ChatGames()
    @State private var draft = ""
    @State private var openGame: String?
    @FocusState private var typing: Bool
    @Environment(\.theme) private var theme
    @Environment(\.colorScheme) private var scheme

    /// What the chat can already answer, as chips: the board, your bets, your record, a parlay, and a game you have a bet on.
    private var ideas: [(text: String, icon: String)] {
        var out = [("What's on tonight's board?", "list.bullet.rectangle"), ("What's the best bet tonight?", "star"),
                   ("How are my open bets doing?", "waveform.path.ecg"), ("How am I doing this week?", "chart.line.uptrend.xyaxis")]
        if let game = store.bets.first(where: { $0.isOpen && Stats.legsOf($0) <= 1 && $0.matchup != nil })?.matchup {
            out.append(("Tell me about \(game)", "sportscourt"))
        }
        out.append(("Build me a 3-leg parlay from today's board", "plus.square"))
        return out
    }

    /// The games the answers link to, for their cards.
    private var linked: [String] {
        model.turns.filter { $0.role != "user" }.flatMap { ChatLayout.games(in: $0.content).map(\.id) }
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if model.waiting {
                        Text("Chat is waiting for its key: add ANTHROPIC_API_KEY to the web service in Railway.")
                            .font(.footnote).padding(12).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.orange.opacity(0.15), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
                    }
                    if model.turns.isEmpty { welcome }
                    ForEach(model.turns) { t in
                        if t.role == "user" { mine(t) } else { ChatAnswer(text: t.content, games: games) { openGame = $0 } }
                    }
                    if model.busy {
                        VStack(alignment: .leading, spacing: 10) {
                            ChatMark()
                            TypingDots().padding(.horizontal, 14).padding(.vertical, 12).background(theme.cardColor, in: Capsule())
                                .accessibilityLabel("BetLab is answering")
                        }
                    }
                    if let e = model.error, !model.waiting {     // the banner says it already
                        Label(e, systemImage: "exclamationmark.circle").font(.footnote.weight(.semibold)).foregroundStyle(.red)
                    }
                    Color.clear.frame(height: 1).id("end")
                }
                .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 8)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: model.turns.count) { _, _ in withAnimation { proxy.scrollTo("end", anchor: .bottom) } }
            .onChange(of: model.busy) { _, _ in withAnimation { proxy.scrollTo("end", anchor: .bottom) } }
            .onChange(of: typing) { _, on in
                guard on else { return }
                Task { try? await Task.sleep(for: .milliseconds(350)); withAnimation { proxy.scrollTo("end", anchor: .bottom) } }
            }
            .onAppear { proxy.scrollTo("end", anchor: .bottom) }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .background(theme.pageColor.ignoresSafeArea())
        .navigationTitle("Ask BetLab")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if !model.turns.isEmpty {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { model.clear() } label: { Image(systemName: "square.and.pencil") }.accessibilityLabel("New chat")
                }
            }
        }
        .task(id: linked.joined(separator: ",")) { await games.find(linked, api: store.api) }
        .navigationDestination(item: $openGame) { GameView(gameId: $0, title: nil) }
    }

    private func send(_ q: String) {
        draft = ""
        Task { await model.ask(q) { try await auth.accessToken() } }
    }

    // MARK: nothing asked yet

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 14) {
            ChatMark(size: 44, named: false)
            Text("What do you want to know?").font(.system(size: 28, weight: .heavy)).kerning(-0.5)
            Text("I read your bets, today's board and any game's page. I only read: I never place or change a bet.")
                .font(.subheadline).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Flow(spacing: 8) {
                ForEach(ideas, id: \.text) { idea in
                    Button { send(idea.text) } label: {
                        HStack(spacing: 7) {
                            Image(systemName: idea.icon).font(.footnote.weight(.semibold)).foregroundStyle(theme.accent)
                            Text(idea.text).font(.subheadline.weight(.semibold)).multilineTextAlignment(.leading)
                        }
                        .padding(.horizontal, 14).padding(.vertical, 10)
                        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    }
                    .buttonStyle(.plain).disabled(model.busy)
                }
            }
            .padding(.top, 4)
        }
        .padding(.top, 28)
    }

    // MARK: your message

    private func mine(_ t: ChatModel.Turn) -> some View {
        Text(t.content)
            .padding(.horizontal, 14).padding(.vertical, 10)
            .foregroundStyle(theme.onAccent(scheme))
            .background(theme.accent, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .contextMenu { Button { UIPasteboard.general.string = t.content } label: { Label("Copy", systemImage: "doc.on.doc") } }
            .padding(.leading, 48)
            .frame(maxWidth: .infinity, alignment: .trailing)
    }

    // MARK: the field

    private var composer: some View {
        let can = !model.busy && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return HStack(alignment: .bottom, spacing: 8) {
            TextField("Ask about your bets, the board, a game", text: $draft, axis: .vertical)
                .lineLimit(1...5).focused($typing).padding(.vertical, 8).onSubmit { if can { send(draft) } }
            Button { send(draft) } label: {
                Image(systemName: "arrow.up").font(.system(size: 15, weight: .bold))
                    .foregroundStyle(can ? theme.onAccent(scheme) : Color.secondary)
                    .frame(width: 36, height: 36)
                    .background(can ? theme.accent : Color(.tertiarySystemFill), in: Circle())
            }
            .buttonStyle(.plain).disabled(!can).accessibilityLabel("Send")
        }
        .padding(.leading, 18).padding(.trailing, 6).padding(.vertical, 5)
        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .shadow(color: .black.opacity(scheme == .dark ? 0.4 : 0.12), radius: 14, y: 4)
        .padding(.horizontal, 12).padding(.top, 10).padding(.bottom, 8)
        .background(LinearGradient(colors: [theme.pageColor.opacity(0), theme.pageColor], startPoint: .top, endPoint: .center))
        .animation(.easeOut(duration: 0.15), value: can)
    }
}

/// Three dots pulsing while Claude answers (still under Reduce Motion).
private struct TypingDots: View {
    @Environment(\.accessibilityReduceMotion) private var calm
    @State private var on = false
    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<3) { i in
                Circle().fill(.secondary).frame(width: 7, height: 7).opacity(on ? 1 : 0.3)
                    .animation(calm ? nil : .easeInOut(duration: 0.6).repeatForever().delay(Double(i) * 0.2), value: on)
            }
        }
        .onAppear { on = true }
    }
}
