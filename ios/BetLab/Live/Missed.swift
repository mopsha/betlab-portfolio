import SwiftUI

/// Missed bets (Mike's #41, Nov 2; web lib/missed.ts): the picks you skipped and how they did, at 1 unit each, beside the picks
/// you took on the same terms. A pick counts from the account's real-money start. Shared cases: tests/fixtures/missed.json.
enum Missed {
    struct Result {
        var picks: [PaperPick] = []
        var won = 0, lost = 0, push = 0
        var units = 0.0
        var clv: Double? = nil
        var tookN = 0
        var tookUnits = 0.0
    }

    static func bets(_ all: [PaperPick], taken: Set<String>, since: Date) -> Result {
        let settled = all.filter { p in p.settled && (Models.date(p.commenceTime).map { $0 >= since } ?? false) }
        let skipped = settled.filter { !taken.contains($0.pickId) }
            .sorted { (Models.date($0.commenceTime) ?? .distantPast) > (Models.date($1.commenceTime) ?? .distantPast) }
        let took = settled.filter { taken.contains($0.pickId) }
        let clvs = skipped.compactMap(\.clvOf)
        return Result(picks: skipped, won: skipped.filter { $0.status == "won" }.count, lost: skipped.filter { $0.status == "lost" }.count,
                      push: skipped.filter { $0.status == "push" }.count, units: skipped.reduce(0) { $0 + ($1.profitFlat ?? 0) },
                      clv: clvs.isEmpty ? nil : clvs.reduce(0, +) / Double(clvs.count), tookN: took.count,
                      tookUnits: took.reduce(0) { $0 + ($1.profitFlat ?? 0) })
    }
}

/// My bets > Record > Missed bets.
struct MissedSection: View {
    @EnvironmentObject private var store: BetStore
    let picks: [PaperPick]

    private var result: Missed.Result {
        let shown = picks.filter { !Bans.banned(store.bans, $0.label ?? "", league: $0.league) }
        return Missed.bets(shown, taken: Set(store.bets.compactMap(\.pickId)), since: Models.date(store.realFrom) ?? Marking.realStart)
    }

    var body: some View {
        let r = result
        if !r.picks.isEmpty {
                Section("Missed bets") {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("You skipped **\(r.picks.count)** pick\(r.picks.count == 1 ? "" : "s"): \(r.won)-\(r.lost)\(r.push > 0 ? "-\(r.push)" : ""), **\(BetMath.signedUnits(r.units))** at 1u each")
                            + (r.clv.map { Text(" · CLV ") + Text(String(format: "%+.1f%%", $0 * 100)).bold() } ?? Text(""))
                            + Text(".")
                        if r.tookN > 0 {
                            Text("The \(r.tookN) you took: \(BetMath.signedUnits(r.tookUnits)) at 1u each.").font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                    DisclosureGroup("See them") {
                        ForEach(r.picks.prefix(50)) { p in
                            VStack(alignment: .leading, spacing: 2) {
                                Text("**\(p.label ?? "")** \(Fmt.am(p.price)) · \(p.status == "push" ? "push" : BetMath.signedUnits(p.profitFlat ?? 0))")
                                Text(p.matchup ?? "").font(.footnote).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
    }
}
