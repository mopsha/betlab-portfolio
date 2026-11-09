import SwiftUI

/// The Notebook on an NFL game page (Mike, Nov 6; web components/games/Notebook.tsx): the story, what changed, each
/// defense's recent pattern in plain counts, then the bet. The worker writes the words (src/betlab/cards/notebook_nfl.py);
/// the bet is the game's best pick or lean, our prices deciding it, named here and shown once, as its own row under "Bets on
/// this game" (no duplicate cards). The words set no price.
struct NotebookView: View {
    let nb: JSON
    let bet: Offer?
    @Environment(\.theme) private var theme

    static func has(_ nb: JSON?) -> Bool {
        guard let nb else { return false }
        return !(nb["story"].string ?? "").isEmpty || !nb["changes"].array.isEmpty || !nb["patterns"].array.isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("The notebook").font(.title3.weight(.bold))
            if let s = nb["story"].string, !s.isEmpty { part("The story") { Text(s) } }
            let changes = nb["changes"].array.compactMap(\.string)
            if !changes.isEmpty { part("What changed") { bullets(changes) } }
            let patterns = nb["patterns"].array.compactMap { $0["text"].string }
            if !patterns.isEmpty { part("The pattern") { bullets(patterns) } }
            part("The bet") {
                if let b = bet {
                    (Text("\(b.label) \(Fmt.am(b.price))").bold().foregroundColor(.accentColor)
                     + Text("\(b.book.map { " at \($0)" } ?? "") · \(b.tier == .pick ? "a pick" : "a lean")\(b.ev.map { ", \(Fmt.pct($0)) EV" } ?? ""). It's the first row under Bets on this game."))
                } else {
                    Text("Nothing worth betting in this game. Most games are priced right.")
                }
            }
            Text("The notes explain the game; they don't set prices. The bet is whatever our prices like best here.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .font(.subheadline)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 4).padding(.leading, 8)
        .overlay(alignment: .leading) { Rectangle().fill(Color.accentColor.opacity(0.35)).frame(width: 2) }   // a page's margin
    }

    private func part<C: View>(_ title: String, @ViewBuilder _ c: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased()).font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
            c().fixedSize(horizontal: false, vertical: true)
        }
    }

    private func bullets(_ xs: [String]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(xs, id: \.self) { x in
                HStack(alignment: .firstTextBaseline, spacing: 6) { Text("•").foregroundStyle(.secondary); Text(x) }
            }
        }
    }
}
