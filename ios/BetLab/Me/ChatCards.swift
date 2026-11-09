import SwiftUI

// Ask BetLab's answers on screen (the overhaul, Nov 5): the text as headings, paragraphs and lists (ChatFormat reads
// the bold and the links), and each game an answer links to as a card with its logos, opening the game's page. Only
// how an answer is drawn lives here; what is asked and answered is ChatModel (ChatView.swift).

enum ChatLayout {
    enum Kind: Equatable { case heading, para, bullet, number(String) }
    struct Piece: Equatable { let kind: Kind; let spans: [ChatFormat.Span] }

    /// An answer line by line: "# " headings, "- " and "1. " lists, the rest paragraphs; blank lines dropped.
    static func pieces(_ text: String) -> [Piece] {
        text.components(separatedBy: "\n").compactMap { raw in
            let line = raw.replacingOccurrences(of: #"\s+$"#, with: "", options: .regularExpression)
            guard !line.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
            if let r = line.range(of: #"^\s*#+\s*"#, options: .regularExpression) {
                return Piece(kind: .heading, spans: ChatFormat.spans(String(line[r.upperBound...])))
            }
            if let r = line.range(of: #"^\s*\d+\.\s+"#, options: .regularExpression) {
                let n = line[r].trimmingCharacters(in: .whitespaces)
                return Piece(kind: .number(n), spans: ChatFormat.spans(String(line[r.upperBound...])))
            }
            if let r = line.range(of: #"^\s*[-*•]\s+"#, options: .regularExpression) {
                return Piece(kind: .bullet, spans: ChatFormat.spans(String(line[r.upperBound...])))
            }
            return Piece(kind: .para, spans: ChatFormat.spans(line))
        }
    }

    /// "/games/nba/abc123" -> "nba:abc123", a game page's id; nil for any other link.
    static func gameId(_ href: String?) -> String? {
        guard let href, href.hasPrefix("/") else { return nil }
        let parts = href.split(separator: "?")[0].split(separator: "/").map(String.init)
        guard parts.count == 3, parts[0] == "games" else { return nil }
        return "\(parts[1]):\(parts[2].removingPercentEncoding ?? parts[2])"
    }

    /// The games an answer links to, each once, in order, with the words it was linked by.
    static func games(in text: String) -> [(id: String, title: String)] {
        var seen = Set<String>(), out: [(String, String)] = []
        for p in pieces(text) {
            for s in p.spans {
                if let id = gameId(s.href), seen.insert(id).inserted { out.append((id, s.text)) }
            }
        }
        return out
    }

    /// A line as text: bold kept; a link to a website tappable; a game's link as strong words (its card follows the
    /// answer); any other app path plain words.
    static func text(_ spans: [ChatFormat.Span]) -> AttributedString {
        spans.reduce(into: AttributedString()) { out, s in
            var a = AttributedString(s.text)
            if s.bold || gameId(s.href) != nil { a.inlinePresentationIntent = .stronglyEmphasized }
            if let h = s.href, h.hasPrefix("https://"), let u = URL(string: h) { a.link = u }
            out += a
        }
    }

    /// An answer as plain words, for Copy.
    static func plain(_ text: String) -> String {
        pieces(text).map { p in
            let line = p.spans.map(\.text).joined()
            switch p.kind {
            case .bullet: return "- " + line
            case .number(let n): return "\(n) " + line
            default: return line
            }
        }
        .joined(separator: "\n")
    }
}

/// The games answers link to, read once each: the row from `games`, and ESPN's logos and colors for it.
@MainActor
final class ChatGames: ObservableObject {
    @Published private(set) var games: [String: Game] = [:]
    @Published private(set) var art: [String: GameLive] = [:]
    private var asked: Set<String> = []

    func find(_ ids: [String], api: SupabaseClient) async {
        let new = ids.filter { !asked.contains($0) }
        guard !new.isEmpty else { return }
        asked.formUnion(new)
        guard let rows: [Game] = try? await api.rows("games", .init(inList: ("game_id", new))) else {
            asked.subtract(new)        // a failed read may be asked again
            return
        }
        for g in rows { games[g.gameId] = g }
        let found = await Live.art(for: rows, ttl: ESPN.doneTTL)
        art.merge(found) { _, new in new }
    }
}

/// BetLab's mark beside its name: who is talking.
struct ChatMark: View {
    var size: CGFloat = 24
    var named = true
    @Environment(\.theme) private var theme

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "flask.fill").font(.system(size: size * 0.5, weight: .bold)).foregroundStyle(theme.accent)
                .frame(width: size, height: size).background(theme.accent.opacity(0.16), in: Circle())
                .accessibilityHidden(true)
            if named { Text("BetLab").font(.footnote.weight(.bold)).foregroundStyle(.secondary) }
        }
    }
}

/// One answer: the mark, the text in comfortable type (no bubble), then a card for each game it links to. A long
/// press copies the answer.
struct ChatAnswer: View {
    let text: String
    @ObservedObject var games: ChatGames
    let open: (String) -> Void
    @Environment(\.theme) private var theme

    var body: some View {
        let pieces = ChatLayout.pieces(text)
        let linked = ChatLayout.games(in: text)
        VStack(alignment: .leading, spacing: 10) {
            ChatMark()
            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(pieces.enumerated()), id: \.offset) { _, p in line(p) }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .contextMenu {
                Button { UIPasteboard.general.string = ChatLayout.plain(text) } label: { Label("Copy", systemImage: "doc.on.doc") }
            }
            if !linked.isEmpty {
                VStack(spacing: 8) {
                    ForEach(linked, id: \.id) { g in
                        Button { open(g.id) } label: { card(g.id, g.title) }.buttonStyle(.plain)
                            .accessibilityHint("Opens the game's page")
                    }
                }
                .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func line(_ p: ChatLayout.Piece) -> some View {
        let body = Text(ChatLayout.text(p.spans)).lineSpacing(4).fixedSize(horizontal: false, vertical: true)
        switch p.kind {
        case .heading:
            body.font(.headline.weight(.bold)).padding(.top, 4)
        case .para:
            body.font(.body)
        case .bullet:
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text("•").font(.body.weight(.heavy)).foregroundStyle(theme.accent).accessibilityHidden(true)
                body.font(.body)
            }
        case .number(let n):
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(n).font(.body.monospacedDigit().weight(.semibold)).foregroundStyle(.secondary)
                body.font(.body)
            }
        }
    }

    /// The game as the Games list draws it (logos, names, the start); until its row is read, or for a game no longer
    /// listed, the words the answer linked.
    @ViewBuilder private func card(_ id: String, _ title: String) -> some View {
        if let g = games.games[id] {
            GameCardRow(g: g, art: games.art[id], count: nil)
        } else {
            HStack(spacing: 10) {
                Image(systemName: "sportscourt").font(.footnote.weight(.semibold)).foregroundStyle(.secondary)
                    .frame(width: 28, height: 28).background(Color(.tertiarySystemFill), in: Circle())
                Text(title).font(.subheadline.weight(.semibold)).lineLimit(2).multilineTextAlignment(.leading)
                Spacer(minLength: 6)
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
            }
            .padding(.vertical, 12).padding(.horizontal, 14)
            .background(theme.cardColor, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        }
    }
}
