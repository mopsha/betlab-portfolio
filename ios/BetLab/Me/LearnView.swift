import SwiftUI
import Charts

// More > Learn (web app/more/learn, components/me/Calculators.tsx): Betting 101, each lesson folded with its calculator.
// The calculators keep the web's math.

enum Calc {
    static func ev(_ p: Double, _ a: Double) -> Double { p * (Odds.dec(a) - 1) - (1 - p) }
    static func kelly(_ p: Double, _ a: Double) -> Double { let b = Odds.dec(a) - 1; return max(0, (b * p - (1 - p)) / b) }
    static func implied(_ a: Double) -> Double { 1 / Odds.dec(a) }

    /// No-vig chances by the power method (more of the vig off the underdog), as BetLab prices.
    static func devigPower(_ prices: [Double]) -> [Double] {
        let imp = prices.map(implied), tot = imp.reduce(0, +)
        if abs(tot - 1) < 1e-9 { return imp }
        let f = { (k: Double) in imp.reduce(0) { $0 + pow($1, k) } - 1 }
        var lo = 0.01, hi = 50.0
        for _ in 0..<80 { let m = (lo + hi) / 2; if f(lo) * f(m) <= 0 { hi = m } else { lo = m } }
        let k = (lo + hi) / 2
        return imp.map { pow($0, k) }
    }

    static func num(_ s: String) -> Double? { Double(s.replacingOccurrences(of: Fmt.minus, with: "-").trimmingCharacters(in: .whitespaces)) }
    static func usd(_ v: Double) -> String { (v < 0 ? Fmt.minus : "") + String(format: "$%.2f", abs(v)) }

    /// The web's seeded generator (mulberry32), so a seed gives the same 40 bettors as on the web.
    struct Mulberry32 {
        var seed: UInt32
        mutating func next() -> Double {
            seed = seed &+ 0x6d2b79f5
            var t = (seed ^ (seed >> 15)) &* (1 | seed)
            t = (t &+ ((t ^ (t >> 7)) &* (61 | t))) ^ t
            return Double(t ^ (t >> 14)) / 4294967296
        }
    }
}

/// A calculator: labeled fields, then results; recomputed as you type.
struct CalcView: View {
    typealias Out = [(String, String, Color?)]
    let title: String
    let fields: [(key: String, label: String, value: String)]
    let run: ([String: String]) -> Out
    var say: (([String: String]) -> String)? = nil
    @State private var v: [String: String] = [:]

    var body: some View {
        let vals = fields.reduce(into: [String: String]()) { $0[$1.key] = v[$1.key] ?? $1.value }
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            ForEach(fields, id: \.key) { f in
                LabeledContent(f.label) {
                    TextField(f.value, text: Binding(get: { v[f.key] ?? f.value }, set: { v[f.key] = $0 }))
                        .keyboardType(.numbersAndPunctuation).multilineTextAlignment(.trailing).frame(maxWidth: 110)
                }
                .font(.footnote)
            }
            Divider()
            ForEach(run(vals), id: \.0) { k, val, c in
                HStack { Text(k).foregroundStyle(.secondary); Spacer(); Text(val).bold().monospacedDigit().foregroundStyle(c ?? .primary) }.font(.footnote)
            }
            if let say { Text(say(vals)).font(.caption).foregroundStyle(.secondary) }
        }
        .padding(12)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
    }
}

enum Calculators {
    static var odds: CalcView {
        CalcView(title: "Odds converter", fields: [("a", "American odds", "-110")], run: { v in
            guard let a = Marking.parseOdds(v["a"]!) else { return [("Enter odds", "like −110 or +150", nil)] }
            let d = Odds.dec(a)
            return [("Decimal", String(format: "%.3f", d), nil), ("Break-even", Fmt.pct(1 / d, 1), nil), ("Profit on $10", Calc.usd(10 * (d - 1)), nil)]
        }, say: { v in
            guard let a = Marking.parseOdds(v["a"]!) else { return "" }
            let be = Fmt.pct(1 / Odds.dec(a), 1)
            return a < 0 ? "Risk $\(Int(abs(a))) to win $100. You need to win \(be) of these bets to break even."
                : "Risk $100 to win $\(Int(a)). You need to win \(be) of these bets to break even."
        })
    }
    static var vig: CalcView {
        CalcView(title: "No-vig calculator", fields: [("a", "Side A", "-110"), ("b", "Side B", "-110"), ("c", "Draw (soccer)", "")], run: { v in
            let ps = ["a", "b", "c"].map { Marking.parseOdds(v[$0]!) }
            let used = ps[2] == nil ? Array(ps.prefix(2)) : ps
            guard used.allSatisfy({ $0 != nil }) else { return [("Enter prices", "like −110", nil)] }
            let pr = used.map { $0! }, tot = pr.map(Calc.implied).reduce(0, +), fair = Calc.devigPower(pr), names = ["A", "B", "Draw"]
            return [("Implied total", Fmt.pct(tot, 1), nil), ("Book's hold", Fmt.pct(1 - 1 / tot, 2), nil)]
                + fair.enumerated().map { ("Fair \(names[$0])", "\(Fmt.pct($1, 1)) · \(Fmt.am(Odds.am(1 / $1)))", nil) }
        })
    }
    static var ev: CalcView {
        CalcView(title: "EV calculator", fields: [("p", "Win chance %", "55"), ("a", "Price", "-110")], run: { v in
            guard let pp = Calc.num(v["p"]!), pp > 0, pp < 100, let a = Marking.parseOdds(v["a"]!) else { return [("Enter", "a chance and a price", nil)] }
            let p = pp / 100, e = Calc.ev(p, a)
            return [("EV per $1", Fmt.signed(e), e >= 0 ? .green : .red), ("Break-even", Fmt.pct(Calc.implied(a), 1), nil),
                    ("Fair price", Fmt.am(Odds.am(1 / p)), nil), ("Per $100 staked", (e >= 0 ? "+" : "") + Calc.usd(e * 100), nil)]
        })
    }
    static var units: CalcView {
        CalcView(title: "Stake sizing", fields: [("p", "Win chance %", "54"), ("a", "Price", "-110")], run: { v in
            guard let pp = Calc.num(v["p"]!), pp > 0, pp < 100, let a = Marking.parseOdds(v["a"]!) else { return [("Enter", "a chance and a price", nil)] }
            let k = Calc.kelly(pp / 100, a), qk = min(2, k / 4 / 0.01)
            return [("Edge", k > 0 ? "yes" : "none: skip it", k > 0 ? .green : .red), ("¼-Kelly (cap 2u)", String(format: "%.2fu", qk), nil),
                    ("Flat bet", "1u", nil), ("Daily cap", "5u", nil)]
        })
    }
    static var clv: CalcView {
        CalcView(title: "CLV calculator", fields: [("bet", "Price you got", "-105"), ("a", "Close, your side", "-125"), ("b", "Close, other side", "+105")], run: { v in
            let xs = ["bet", "a", "b"].map { Marking.parseOdds(v[$0]!) }
            guard xs.allSatisfy({ $0 != nil }) else { return [("Enter", "three prices", nil)] }
            let fair = Calc.devigPower([xs[1]!, xs[2]!])[0], c = Calc.ev(fair, xs[0]!)
            return [("Fair close (your side)", Fmt.pct(fair, 1), nil), ("Fair close price", Fmt.am(Odds.am(1 / fair)), nil), ("Your CLV", Fmt.signed(c), c >= 0 ? .green : .red)]
        })
    }
    static var parlay: CalcView {
        CalcView(title: "Parlay math (up to 4 legs)", fields: [("1", "Leg 1", "-110"), ("2", "Leg 2", "-110"), ("3", "Leg 3", "-110"), ("4", "Leg 4", "-110")], run: { v in
            let legs = ["1", "2", "3", "4"].compactMap { Marking.parseOdds(v[$0]!) }
            guard legs.count >= 2 else { return [("Enter", "at least two legs", nil)] }
            let dec = legs.reduce(1) { $0 * Odds.dec($1) }, fairP = legs.reduce(1) { $0 * Calc.implied($1) / 1.0476 }, e = fairP * dec - 1
            return [("Parlay pays", Fmt.am(Odds.am(dec)), nil), ("Fair price", Fmt.am(Odds.am(1 / fairP)), nil),
                    ("Chance to hit", Fmt.pct(fairP, 1), nil), ("Book's edge", Fmt.signed(-e), .red)]
        }, say: { _ in "Assumes each leg is a standard −110/−110 market with the vig removed, and that legs are independent." })
    }
    static var bonus: CalcView {
        CalcView(title: "Bonus bet value", fields: [("amt", "Bonus bet $", "10"), ("a", "Price", "+300"), ("p", "Fair win %", "24")], run: { v in
            guard let amt = Calc.num(v["amt"]!), amt > 0, let a = Marking.parseOdds(v["a"]!), let pp = Calc.num(v["p"]!), pp > 0, pp < 100 else {
                return [("Enter", "all three fields", nil)]
            }
            let val = amt * pp / 100 * (Odds.dec(a) - 1)
            return [("Cash value", Calc.usd(val), nil), ("Kept", "\(Fmt.pct(val / amt)) of face value", nil), ("If it wins", Calc.usd(amt * (Odds.dec(a) - 1)), nil)]
        })
    }
}

/// 40 bettors with the same true edge: how many are still behind after N bets. Seeded, so the first view is stable.
struct VarianceSim: View {
    @State private var p = "55"
    @State private var a = "-110"
    @State private var n = "300"
    @State private var seed: UInt32 = 7

    private struct Pt: Identifiable { let run: Int; let i: Int; let u: Double; let behind: Bool; var id: Int { run * 100_000 + i } }

    var body: some View {
        let res = simulate()
        VStack(alignment: .leading, spacing: 8) {
            Text("Simulate 40 bettors with the same edge").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            HStack {
                field("True win %", $p); field("Price", $a); field("Bets each", $n)
            }
            if let res {
                Chart {
                    ForEach(res.pts) { pt in
                        LineMark(x: .value("Bet", pt.i), y: .value("Units", pt.u), series: .value("Run", pt.run))
                            .foregroundStyle(pt.behind ? Color.red.opacity(0.45) : Color.secondary.opacity(0.45))
                            .lineStyle(StrokeStyle(lineWidth: 1))
                    }
                    LineMark(x: .value("Bet", 0), y: .value("Units", 0), series: .value("Run", -1)).foregroundStyle(Color.accentColor)
                    LineMark(x: .value("Bet", res.n), y: .value("Units", res.e1 * Double(res.n)), series: .value("Run", -1))
                        .foregroundStyle(Color.accentColor).lineStyle(StrokeStyle(lineWidth: 2.5, dash: [6, 4]))
                }
                .frame(height: 200)
                Text("Expected: \(BetMath.signedUnits(res.e1 * Double(res.n)).replacingOccurrences(of: ".00u", with: "u")) after \(res.n) bets (dashed). \(res.behind) of 40 bettors with exactly this edge were still behind (red).\(res.e1 < 0 ? " With no edge, the vig wins in the long run." : "")")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Button("Run again") { seed &+= 1 }.font(.footnote)
        }
        .padding(12)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
    }

    private func field(_ label: String, _ v: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            TextField(label, text: v).keyboardType(.numbersAndPunctuation).textFieldStyle(.roundedBorder).font(.footnote)
        }
    }

    private func simulate() -> (pts: [Pt], n: Int, e1: Double, behind: Int)? {
        guard let pp = Calc.num(p), pp > 0, pp < 100, let aa = Marking.parseOdds(a), let nb = Calc.num(n) else { return nil }
        let N = min(3000, max(10, Int(nb.rounded())))
        var rnd = Calc.Mulberry32(seed: seed)
        let win = Odds.dec(aa) - 1, every = max(1, N / 200)
        var pts: [Pt] = [], behind = 0
        for r in 0..<40 {
            var u = 0.0, path = [0.0]
            for _ in 0..<N { u += rnd.next() < pp / 100 ? win : -1; path.append(u) }
            let lost = path[N] < 0
            if lost { behind += 1 }
            for i in stride(from: 0, through: N, by: every) { pts.append(Pt(run: r, i: i, u: path[i], behind: lost)) }
        }
        return (pts, N, pp / 100 * win - (1 - pp / 100), behind)
    }
}

struct LearnView: View {
    private struct Lesson: Identifiable { let id: String; let title: String; let text: [String]; var calc: AnyView? = nil }

    private let lessons: [Lesson] = [
        Lesson(id: "odds", title: "Reading odds", text: [
            "American odds are built around $100. A minus number is what you risk to win $100; a plus number is what you win when you risk $100. `−150` means risk $150 to win $100. `+150` means risk $100 to win $150.",
            "Every price is also a probability: the win rate you need to break even. That's the number the model compares against. Implied probability = 1 ÷ decimal odds."],
               calc: AnyView(Calculators.odds)),
        Lesson(id: "vig", title: "The vig (the book's cut)", text: [
            "A fair coin flip would be `+100` on both sides. FanDuel usually prices it `−110 / −110`. Add the two break-even rates and you get 104.8%, not 100%. That extra is the vig.",
            "Remove it and you get the market's fair chances: that's \"no-vig\" in the app. Books shade long shots more than favorites, so BetLab uses the *power* method, which takes more of the vig off the underdog."],
               calc: AnyView(Calculators.vig)),
        Lesson(id: "ev", title: "Expected value", text: [
            "Expected value (EV) is what a bet earns on average per $1 staked, if your chance is right: `EV = p × (decimal − 1) − (1 − p)`. A 55% shot at −110 has EV of +5%.",
            "A bet is a pick only when its EV clears 3% on game lines, 5% on props and 10% on prop unders, within 36 hours of the start. Smaller edges show as leans. The buffers exist because our chances are estimates."],
               calc: AnyView(Calculators.ev)),
        Lesson(id: "units", title: "Units", text: [
            "A **unit** is your standard bet, whatever size you choose. BetLab counts everything in units, never dollars: a 1u bet at `+120` that wins is `+1.20u`, and \"+6 units\" means the same whatever your unit is. Only bet money you could lose completely without it touching rent, bills or school.",
            "• Bet flat at first: every pick 1 unit.\n• Keep your unit the same size for a month at a time, never bigger after a win or a loss.\n• At most 5 units at risk on one day. The one exception is a ladder challenge's steps (My bets › Ladder), which roll the whole stack by design.\n• Never chase. Doubling up to get even is how losing streaks get worse.",
            "The **Kelly criterion** gives the stake that grows your money fastest *if your chances are exactly right*. They never are, so BetLab tracks quarter-Kelly, capped at 2 units, for comparison only (taking a unit as about 1% of what you set aside)."],
               calc: AnyView(Calculators.units)),
        Lesson(id: "variance", title: "Variance: why 100 bets prove almost nothing", text: [
            "Someone who truly wins 55% of −110 bets (a big edge) is still behind after 100 bets about 3 times in 10. After 1,000 bets that drops to about 1 in 20. That's why the scorecard is closing line value, not the record."],
               calc: AnyView(VarianceSim())),
        Lesson(id: "clv", title: "Closing line value (CLV)", text: [
            "The closing line, the last price before the start, is the sharpest number the market produces. Consistently beating it means you're very likely a winning bettor, even through losing stretches. CLV becomes meaningful in weeks, where records take years.",
            "CLV here is your bet's EV if the no-vig closing price were the truth."],
               calc: AnyView(Calculators.clv)),
        Lesson(id: "shop", title: "Line shopping", text: [
            "Books disagree, and the difference is pure edge. The same bet at −105 instead of −115 moves your break-even from 53.5% to 51.2%. Winning 52.5% of bets is EV −1.9% at −115 (a slow loser) and +2.5% at −105 (a winner).",
            "That's why the plan is FanDuel plus one or two other books."]),
        Lesson(id: "parlays", title: "Parlays and same-game parlays", text: [
            "A parlay multiplies the legs' odds, and the book's edge too. One −110 coin flip costs about 4.5%; four of them pay `+1228` against a fair `+1500`, about 17%. Same-game parlays price the correlation with extra margin.",
            "Picks are straight bets. Parlays live in the fun bucket (the parlay units a month you set in Settings), so they never blur the real record. The Build grade compares FanDuel's price with what its parlays that size usually pay."],
               calc: AnyView(Calculators.parlay)),
        Lesson(id: "bonus", title: "Bonus bets and boosts", text: [
            "**Bonus bets** pay the profit but never the stake, so long odds keep more of their value: a $10 bonus bet on a fair +300 is worth about $7.50 in cash on average; on a −110 coin flip, about $4.50.",
            "**Profit boosts** raise the payout on one bet; many turn a slightly negative bet positive. Run the boosted price through the EV calculator with the no-vig chance."],
               calc: AnyView(Calculators.bonus)),
        Lesson(id: "props", title: "Player props", text: [
            "Props are priced from projections of playing time and usage. Books post hundreds per game, so they're less sharp than spreads, but they carry more vig, lower limits, and move with game script.",
            "New York bans college player props, and BetLab never offers them."]),
        Lesson(id: "soccer", title: "Soccer markets", text: [
            "• **Moneyline is three-way:** home, draw or away, settled on 90 minutes plus stoppage time.\n• **Draw no bet:** your stake comes back on a draw.\n• **Double chance:** two of the three outcomes.\n• **Totals and spreads:** usually half-goal lines, so no pushes.\n• **Both teams to score:** yes/no on each side scoring."]),
        Lesson(id: "taxes", title: "Taxes in New York", text: [
            "Gambling winnings are income for federal and New York taxes (and New York City tax if you live there), with or without a tax form. Losses are deductible only if you itemize, and from 2026 returns a federal law limits that to 90% of losses. Keep your records (My bets). Check with a tax professional; this isn't tax advice."]),
        Lesson(id: "control", title: "Staying in control", text: [
            "• Before your first deposit, set a monthly deposit limit in FanDuel equal to what you set aside for betting (Account → Responsible Gaming).\n• At most 5 units at risk per day.\n• If betting stops being fun, or you catch yourself chasing, take a break. FanDuel's limits can lock the account for a set time.",
            "**New York HOPEline**, free, confidential, 24/7: call `1-877-846-7369` (1-877-8-HOPENY) or text `467369` (HOPENY)."]),
    ]

    var body: some View {
        List { Group {
            Section {
                ForEach(lessons) { l in
                    DisclosureGroup(l.title) {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(l.text, id: \.self) { Text(.init($0)).font(.footnote) }
                            if let c = l.calc { c }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }.themedRows() }.themedList()
        .navigationTitle("Learn")
        .subtitle("every number in the app, explained")
    }
}
