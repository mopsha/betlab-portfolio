import SwiftUI

/// Mark as mine / Undo (web MarkButton). Paper until real money starts; from then "I placed this · 1u" records a
/// placed bet at the price shown, and Edit fixes the units, the price the book actually gave, or the book.
struct MarkControl: View {
    let input: MarkInput
    @EnvironmentObject private var store: BetStore
    @State private var busy = false
    @State private var error: String?
    // one sheet for both (two .sheet modifiers on one view present only one)
    private enum Sheet: Identifiable { case edit, place; var id: Self { self } }
    @State private var sheet: Sheet?

    var body: some View {
        let mine = store.marks[input.key]
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                if let mine {
                    Label(summary(mine), systemImage: "checkmark.circle.fill")
                        .font(.caption.weight(.semibold)).foregroundStyle(.green)
                    if mine.isReal && mine.price == nil {
                        Button("Add the price you got") { sheet = .edit }.buttonStyle(.borderedProminent)
                    } else if mine.isReal {
                        Button("Edit") { sheet = .edit }.buttonStyle(.borderless)
                    }
                    // a graded bet is history: Edit stays, Undo would delete it (Nov 9)
                    if mine.isOpen { Button("Undo") { run { await store.undo(key: input) } }.buttonStyle(.borderless) }
                } else {
                    // real money: the units, price, book and any bonus or boost go in before it's saved (Oct 24)
                    Button(store.isReal ? "Place" : "Mark as mine") {
                        if store.isReal { sheet = .place } else { run { await store.mark(input) } }
                    }
                        .buttonStyle(.borderedProminent)
                }
                if busy { ProgressView().controlSize(.small) }
            }
            .font(.caption.weight(.semibold))
            .disabled(busy)
            if let mine, mine.isReal, mine.price == nil {
                Text("No price yet: this bet can't count in your real P/L until you add it.").font(.caption2).foregroundStyle(.red)
            }
            if let error { Text(error).font(.caption2).foregroundStyle(.red) }
        }
        .sheet(item: $sheet) { which in
            switch which {
            case .place: PlaceBetSheet(input: input)
            case .edit: if let mine = store.marks[input.key] { EditBetSheet(bet: mine, parlay: input.kind == "parlay") }
            }
        }
    }

    private func summary(_ b: MyBet) -> String {
        guard b.isReal else { return "Yours" }
        return "Placed \(Marking.units(b.stake))" + (b.isBonus ? " bonus" : "") + (b.protect == true ? " · Bet Protect+" : "") + (b.reset == true ? " · Bet reset" : "") + (b.boost.flatMap { $0 != 0 ? " +\(String(format: "%g", $0))% boost" : nil } ?? "") + (b.price.map { " at \(Fmt.am($0))" } ?? "") + (b.book.map { " · \($0)" } ?? "")
    }

    private func run(_ op: @escaping () async -> String?) {
        busy = true
        Task {
            error = await op()
            busy = false
        }
    }
}

/// "I placed this": what was placed, before it's saved. Units (1 unless typed), the price the book gave (ours to start),
/// the book, and a bonus bet or a profit boost.
struct PlaceBetSheet: View {
    let input: MarkInput
    /// A wallet token on the slip (Build, Nov 9): the bet takes it (its id, bonus or boost and cap), at its dollars to start.
    var token: PromoRow? = nil
    /// Called once it's saved (Build clears its promo).
    var placed: (() -> Void)? = nil
    @EnvironmentObject private var store: BetStore
    @Environment(\.dismiss) private var dismiss
    @State private var stake = "1"
    @State private var price = ""
    @State private var book = "FanDuel"
    @State private var promo = "none"
    @State private var boost = ""
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form { Group {
                Section {
                    Text(input.label.map(Fmt.label) ?? input.matchup ?? "").font(.subheadline.weight(.semibold))
                    LabeledContent("Units") { TextField("1", text: $stake).keyboardType(.decimalPad).multilineTextAlignment(.trailing) }
                    LabeledContent("Price you got") {
                        TextField(input.kind == "parlay" || input.kind == "custom" ? "+1200" : "-110", text: $price)
                            .keyboardType(.numbersAndPunctuation).multilineTextAlignment(.trailing)
                    }
                    Picker("Book", selection: $book) { ForEach(Marking.books.filter { BooksOff.mine.contains($0) || $0 == book }, id: \.self) { Text($0) } }
                } footer: {
                    Text("Units, not dollars: a unit is your usual bet. The price starts at ours; change it to what the book gave you.")
                }
                if let t = token {
                    Section {
                        HStack(spacing: 10) {
                            BookIcon(book: t.book, size: 30)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Uses your \(Promos.title(t))").font(.subheadline.weight(.semibold))
                                let terms = Promos.terms(t)
                                if !terms.isEmpty { Text(terms).font(.caption).foregroundStyle(.secondary) }
                            }
                        }
                    } footer: {
                        Text("It leaves your wallet once this is saved\(t.kind == "bonus" ? "; less than its dollars keeps the rest there as its own bonus bet" : "").")
                    }
                } else {
                    Section {
                        Picker("Promo", selection: $promo) {
                            Text("None").tag("none"); Text("Bonus bet").tag("bonus"); Text("Profit boost").tag("boost")
                        }
                        .pickerStyle(.segmented)
                        if promo == "boost" {
                            LabeledContent("Boost %") { TextField("50", text: $boost).keyboardType(.decimalPad).multilineTextAlignment(.trailing) }
                        }
                    } footer: {
                        Text(promo == "bonus" ? "The book's credit, not cash: a win pays the profit only, a loss costs nothing."
                             : promo == "boost" ? "The price stays the book's own; a win's profit is boosted." : "")
                    }
                }
                if let error { Text(error).foregroundStyle(.red) }
            }.themedRows() }.themedList()
            .navigationTitle("I placed this")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        busy = true
                        Task {
                            if let t = token {
                                error = await store.placeWithToken(input, token: t, stake: stake, price: price, book: book)
                            } else {
                                error = await store.place(input, stake: stake, price: price, book: book, bonus: promo == "bonus",
                                                          boost: promo == "boost" ? boost : "")
                            }
                            busy = false
                            if error == nil { placed?(); dismiss() }
                        }
                    }
                    .disabled(busy)
                }
            }
            .onAppear {
                price = input.price.map { Fmt.am($0).replacingOccurrences(of: Fmt.minus, with: "-") } ?? ""
                book = Marking.bookOf(input.book)
                if input.bonus == true { promo = "bonus" } else if let b = input.boost { promo = "boost"; boost = String(format: "%g", b) }
                if let d = token?.amountDollars, d > 0, store.unit > 0 { stake = String(format: "%g", (d / store.unit * 1000).rounded() / 1000) }
            }
        }
        .presentationDetents([.medium, .large])
    }
}

/// Edit a placed bet: units, the price you got, the book, whether it was a bonus bet (Oct 19), its profit boost and a cash-out (Oct 22).
struct EditBetSheet: View {
    let bet: MyBet
    let parlay: Bool
    @EnvironmentObject private var store: BetStore
    @Environment(\.dismiss) private var dismiss
    @State private var stake = ""
    @State private var price = ""
    @State private var book = "FanDuel"
    @State private var bonus = false
    @State private var protect = false
    @State private var reset = false
    @State private var cashout = ""
    @State private var boost = ""
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form { Group {
                TextField("Units", text: $stake).keyboardType(.decimalPad)
                TextField(parlay ? "Price you got, like +1200" : "Price you got, like -110", text: $price)
                    .keyboardType(.numbersAndPunctuation)
                Picker("Book", selection: $book) { ForEach(Marking.books.filter { BooksOff.mine.contains($0) || $0 == book }, id: \.self) { Text($0) } }
                Section {
                    Toggle("Bonus bet", isOn: $bonus)
                    Toggle("Bet Protect+ (3% fee)", isOn: $protect)
                } footer: {
                    Text("The book's credit, not cash: a win pays the profit only, a loss costs nothing.")
                }
                Section {
                    Toggle("Bet reset", isOn: $reset)
                } footer: {
                    Text("If this loses, the stake comes back as a bonus bet in your wallet. The loss still counts.")
                }
                Section {
                    LabeledContent("Boost %") {
                        TextField("—", text: $boost).keyboardType(.decimalPad).multilineTextAlignment(.trailing)
                    }
                } footer: {
                    Text("A profit boost in percent: the price stays the book's own, a win's profit is boosted")
                }
                Section {
                    LabeledContent("Cashed out (u back)") {
                        TextField("—", text: $cashout).keyboardType(.decimalPad).multilineTextAlignment(.trailing)
                    }
                } footer: {
                    Text("Cashed out early: what the book paid back, in units ($5.29 on a $5 = 1u bet is 1.058). Blank: not cashed out")
                }
                if let error { Text(error).foregroundStyle(.red) }
            }.themedRows() }.themedList()
            .navigationTitle("Edit bet")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        busy = true
                        Task {
                            error = await store.edit(bet, stake: stake, price: price, book: book, bonus: bonus, cashout: cashout, boost: boost, protect: protect, reset: reset)
                            busy = false
                            if error == nil { dismiss() }
                        }
                    }
                    .disabled(busy)
                }
            }
            .onAppear {
                stake = bet.stake.map { String(format: "%g", $0) } ?? "1"
                price = bet.price.map { Fmt.am($0).replacingOccurrences(of: Fmt.minus, with: "-") } ?? ""
                book = Marking.bookOf(bet.book)
                bonus = bet.isBonus
                protect = bet.protect == true
                reset = bet.reset == true
                cashout = bet.cashout.map { String(format: "%g", $0) } ?? ""
                boost = bet.boost.map { String(format: "%g", $0) } ?? ""
            }
        }
        .presentationDetents([.medium, .large])
    }
}
