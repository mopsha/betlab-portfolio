import SwiftUI

// The building blocks of the game page's analysis: a two-team tape, a stat table that scrolls sideways,
// and the "About these numbers" fold (web/components/games/Analysis.tsx and its CSS).

/// One table cell: its text, an optional second line (a book's EV under its price), and colors.
struct TCell {
    var text: String
    var sub: String? = nil
    var color: Color? = nil
    var subColor: Color? = nil
    var bold = false
}

extension TCell: ExpressibleByStringLiteral {
    init(stringLiteral value: String) { self.init(text: value) }
}

/// Green for a gain, red for a loss.
func tone(_ x: Double?) -> Color? { guard let x else { return nil }; return x > 0 ? .green : x < 0 ? .red : nil }

struct StatTable: View {
    let head: [String]
    let rows: [[TCell]]
    var highlight: Set<Int> = []
    var leading: Set<Int> = [0]          // text columns; the rest are numbers, right-aligned

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 7) {
                GridRow {
                    ForEach(head.indices, id: \.self) { i in
                        Text(head[i]).gridColumnAlignment(leading.contains(i) ? .leading : .trailing)
                    }
                }
                .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                ForEach(rows.indices, id: \.self) { r in
                    GridRow {
                        ForEach(rows[r].indices, id: \.self) { i in
                            let c = rows[r][i]
                            VStack(alignment: leading.contains(i) ? .leading : .trailing, spacing: 1) {
                                Text(c.text).fontWeight(c.bold ? .semibold : .regular).foregroundStyle(c.color ?? .primary)
                                if let s = c.sub { Text(s).font(.caption2).foregroundStyle(c.subColor ?? .secondary) }
                            }
                        }
                    }
                    .padding(.vertical, highlight.contains(r) ? 2 : 0)
                    .background(highlight.contains(r) ? Color.yellow.opacity(0.18) : Color.clear)
                }
            }
            .font(.caption.monospacedDigit())
            .padding(.vertical, 2)
        }
    }
}

/// One row of a tale of the tape: a label and each team's value, with an optional rank (lower is better; the
/// better side is bold, as on the web).
struct TapeRow {
    let label: String
    let left: String
    let right: String
    var leftRank: Int? = nil
    var rightRank: Int? = nil
    var of: Int? = nil
}

struct TapeView: View {
    let left: String
    let right: String
    var sep = "at"
    let rows: [TapeRow]

    var body: some View {
        Grid(horizontalSpacing: 10, verticalSpacing: 7) {
            GridRow {
                Text(left).font(.caption.weight(.semibold)).gridColumnAlignment(.leading)
                Text(sep).font(.caption2).foregroundStyle(.secondary)
                Text(right).font(.caption.weight(.semibold)).gridColumnAlignment(.trailing)
            }
            ForEach(rows.indices, id: \.self) { i in
                let r = rows[i]
                GridRow {
                    side(r.left, r.leftRank, better(r.leftRank, r.rightRank), r.of)
                    Text(r.label).font(.caption2).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    side(r.right, r.rightRank, better(r.rightRank, r.leftRank), r.of)
                }
            }
        }
        .font(.caption.monospacedDigit())
    }

    private func better(_ a: Int?, _ b: Int?) -> Bool { a != nil && b != nil && a! < b! }

    private func side(_ v: String, _ rank: Int?, _ best: Bool, _ of: Int?) -> some View {
        HStack(spacing: 3) {
            Text(v).fontWeight(best ? .bold : .regular)
            if let rank { Text(Stat.ord(rank) + (of.map { " of \($0)" } ?? "")).font(.caption2).foregroundStyle(.secondary) }
        }
    }
}

struct AboutView: View {
    let text: String
    var body: some View {
        DisclosureGroup("About these numbers") {
            Text(text).font(.footnote).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
        }
        .font(.caption)
    }
}

/// Short lines of reasoning, one under another (the web's `.read` block).
struct ReadLines: View {
    var title: String? = nil
    let lines: [String]
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let title { Text(title).font(.caption.weight(.semibold)) }
            ForEach(lines, id: \.self) { Text($0).font(.footnote) }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }
}

/// Number formats from web/components/games/Analysis.tsx.
enum Stat {
    static func ord(_ n: Int?) -> String {
        guard let n else { return "—" }
        let t = n % 100, suffix = (11...13).contains(t) ? "th" : [1: "st", 2: "nd", 3: "rd"][n % 10] ?? "th"
        return "\(n)\(suffix)"
    }
    static func fixed(_ x: Double?, _ d: Int = 1) -> String {
        guard let x else { return "—" }
        return String(format: "%.\(d)f", x).replacingOccurrences(of: "-", with: Fmt.minus)
    }
    /// EPA a play: +0.12 / −0.05
    static func epa(_ x: Double?) -> String {
        guard let x else { return "—" }
        return (x >= 0 ? "+" : Fmt.minus) + String(format: "%.2f", abs(x))
    }
    /// A difference of two chances, in points: "+6 pts". `scale` 1 for a difference already in points.
    static func pts(_ x: Double?, _ d: Int = 0, scale: Double = 100) -> String {
        guard let x, x.isFinite else { return "—" }
        return (x >= 0 ? "+" : Fmt.minus) + String(format: "%.\(d)f", abs(x * scale)) + " pts"
    }
    /// "41% (+144)": a chance with its fair American odds.
    static func pctOdds(_ p: Double?) -> String {
        guard let v = p, v > 0, v < 1 else { return "—" }
        return "\(Fmt.pct(v)) (\(Fmt.am(v >= 0.5 ? -100 * v / (1 - v) : 100 * (1 - v) / v)))"
    }
    static func bookName(_ b: String?) -> String {
        ["fanduel": "FanDuel", "draftkings": "DraftKings", "draft kings": "DraftKings", "pinnacle": "Pinnacle"][(b ?? "").lowercased()] ?? (b ?? "")
    }
    /// A book's price with its EV under it; "—" where the book doesn't post that side.
    static func bookCell(_ price: Double?, _ ev: Double?) -> TCell {
        guard let price else { return "—" }
        return TCell(text: Fmt.am(price), sub: ev.map { Fmt.signed($0) }, subColor: ev.map { $0 >= 0 ? .green : .red })
    }
    /// The price tables' book columns: the account's books only (Nov 6, web Analysis colsOf).
    static var myBooks: [String] { BooksOff.mine }
    /// A row's cells at the account's books: FanDuel's `price`/`ev`, `dk_`/`nv_` for the others (a UFC row nests each book).
    static func bookCells(_ o: JSON, ufc: Bool = false) -> [TCell] {
        myBooks.map { b in
            if ufc { let k = b.lowercased(); return bookCell(o[k]["price"].double, o[k]["ev"].double) }
            let pre = ["FanDuel": "", "DraftKings": "dk_", "Novig": "nv_"][b] ?? ""
            return bookCell(o[pre + "price"].double, o[pre + "ev"].double)
        }
    }
}
