import SwiftUI

/// The first-run welcome (Nov 5, idea #60; web components/me/WelcomeSteps.tsx, the same words in web lib/welcome.ts). A new account
/// sees it once; Me > Extras > Intro shows it again.
struct WelcomeView: View {
    @EnvironmentObject private var store: BetStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.theme) private var theme
    @State private var step = 0
    @State private var dollars = ""
    @State private var err: String?
    @State private var busy = false

    private static let pages: [(title: String, lines: [String])] = [
        ("BetLab finds the prices that lag",
         ["It compares each book's price with the sharp market's no-vig price. When your book is behind, that's a pick.",
          "Picks are suggestions. You decide, and you place every bet yourself."]),
        ("Three words you'll see",
         ["EV: what a price is worth against the fair chance. Above zero is good.",
          "Units: a bet is 1u, and 5u a day at most. The apps count units, never money.",
          "CLV: did you beat the closing price? Over time it's the best sign you're betting well."]),
        ("Where things are",
         ["Today: the picks and parlays.", "Live: your open bets, updating as they play.",
          "Build: your own parlay, a slip to check, or a promo to use.", "Games: every game and its page.", "Me: your record, friends and settings."]),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("\(step + 1) of \(Self.pages.count + 1)").font(.caption).foregroundStyle(.secondary)
            if step < Self.pages.count {
                Text(Self.pages[step].title).font(.title.weight(.bold)).fixedSize(horizontal: false, vertical: true)
                ForEach(Self.pages[step].lines, id: \.self) { Text($0).fixedSize(horizontal: false, vertical: true) }
            } else {
                Text("What's one unit to you?").font(.title.weight(.bold))
                Text("Pick an amount you could lose every day and not mind. You can change it in Settings.").fixedSize(horizontal: false, vertical: true)
                LabeledContent("Dollars per unit") {
                    TextField("5", text: $dollars).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(maxWidth: 110)
                }
                Text("If betting stops being fun, help is free and private: 1-877-8-HOPENY.").font(.footnote).foregroundStyle(.secondary)
                if let err { Text(err).font(.footnote).foregroundStyle(.red) }
            }
            Spacer()
            HStack {
                if step > 0 { Button("Back") { step -= 1 }.buttonStyle(.bordered) }
                Spacer()
                if step < Self.pages.count {
                    Button("Next") { step += 1 }.buttonStyle(.borderedProminent)
                } else {
                    Button(busy ? "Saving…" : "Start") { Task { await finish() } }
                        .buttonStyle(.borderedProminent).disabled(busy || (Double(dollars) ?? 0) <= 0)
                }
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background((theme.page ?? Color(.systemBackground)).ignoresSafeArea())
        .tint(theme.accent)
        .onAppear { if dollars.isEmpty { dollars = String(format: "%g", store.unit) } }
    }

    private func finish() async {
        busy = true
        defer { busy = false }
        if let e = await store.finishWelcome(unit: Double(dollars) ?? store.unit) { err = e } else { dismiss() }
    }
}
