import SwiftUI

/// The picked game's markets under one row of tabs (Nov 5): Popular (the main lines, a row per team, then the game's
/// top props as photo rows), Lines (every line and rung), a tab per player stat (a row per player with his photo and
/// his numbers), and Ideas (the themed slips, BuildIdeas.swift). A search that matches no game filters the legs and
/// shows every market's matches.
struct Board: View {
    @ObservedObject var model: BuildModel
    let art: [String: GameLive]
    @Environment(\.theme) private var theme

    static let popular = "popular", lines = "game"

    var body: some View {
        let eid = model.current
        let q = model.query.trimmingCharacters(in: .whitespaces).lowercased()
        let gameHit = !q.isEmpty && model.inSport.contains { $0.matchup.lowercased().contains(q) }
        let legQ = q.isEmpty || gameHit ? "" : q
        VStack(alignment: .leading, spacing: 14) {
            if let pk = model.packs[eid] {
                let all = Array(pk.legs.values)
                let tabs = Build.boardTabs(legQ.isEmpty ? all : all.filter { $0.label.lowercased().contains(legQ) }, matchup: pk.matchup)
                if !legQ.isEmpty {
                    matches(tabs, pk)
                } else {
                    let items = Self.items(tabs)
                    let cur = items.contains { $0.key == model.tab } ? model.tab : Self.popular
                    UnderTabs(items: items, selected: cur) { model.tab = $0 }
                    switch cur {
                    case Self.popular: popular(tabs, pk)
                    case BuildModel.ideasTab: IdeasTab(model: model, art: art)
                    case Self.lines: if let t = tabs.first(where: { $0.key == Self.lines }) { lines(t, eid) }
                    default: if let t = tabs.first(where: { $0.key == cur }) { players(t, pk) }
                    }
                }
            } else {
                Text(model.failed.contains(eid) ? "Couldn't load this game's legs. Pick it again to retry." : "Loading legs…")
                    .font(.footnote).foregroundStyle(.secondary).padding(.horizontal)
            }
        }
    }

    /// Popular, Lines, one per stat the game has, Ideas.
    static func items(_ tabs: [BoardTab]) -> [UnderTabs.Item] {
        var out = [UnderTabs.Item(key: popular, title: "Popular")]
        if tabs.contains(where: { $0.key == lines }) { out.append(.init(key: lines, title: "Lines")) }
        out += tabs.filter { $0.key != lines }.map { .init(key: $0.key, title: $0.title) }
        out.append(.init(key: BuildModel.ideasTab, title: "Ideas"))
        return out
    }

    // MARK: Popular

    /// The main lines (a three-way game: its result), then the top props.
    @ViewBuilder private func popular(_ tabs: [BoardTab], _ pk: Pack) -> some View {
        let eid = model.current
        let game = tabs.first { $0.key == Self.lines }
        if let main = MainLines.rows(pk, art: art[eid]) {
            MainLinesCard(model: model, eid: eid, rows: main, ufc: pk.sport == "ufc")
        } else if let s = game?.sections.first {
            card {
                Text(s.title.uppercased()).font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
                buttons(s, eid)
            }
        }
        let props = Popular.props(pk, eid: eid, pricer: model.pricer, bans: Bans.current)
        if !props.isEmpty {
            VStack(spacing: 0) {
                ForEach(Array(props.enumerated()), id: \.element.label) { i, l in
                    if i > 0 { Hairline() }
                    HStack(spacing: 12) {
                        PlayerFace(name: l.player ?? "", sport: pk.sport, size: 40)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(l.player ?? "").font(.body.weight(.semibold)).lineLimit(1)
                            Text("\(Popular.what(l)) · \(Fmt.pct(l.p)) chance").font(.footnote).foregroundStyle(.secondary).lineLimit(2)
                        }
                        Spacer(minLength: 4)
                        LegButton(model: model, eid: eid, leg: l, short: "", chance: false).frame(width: 84)
                    }
                    .padding(.vertical, 10)
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 6)
            .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
            .padding(.horizontal)
        } else if game == nil {
            Text("No lines for this game yet.").font(.footnote).foregroundStyle(.secondary).padding(.horizontal)
        }
    }

    // MARK: Lines and the stat tabs

    /// Every line and rung, a card per market.
    private func lines(_ t: BoardTab, _ eid: String) -> some View {
        ForEach(t.sections) { s in
            card {
                Text(s.title.uppercased()).font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
                buttons(s, eid)
            }
        }
    }

    /// One card of players, each a row: his photo, his name and team, then his numbers.
    private func players(_ t: BoardTab, _ pk: Pack) -> some View {
        LazyVStack(alignment: .leading, spacing: 0) {
            ForEach(Array(t.sections.enumerated()), id: \.element.id) { i, s in
                if i > 0 { Hairline() }
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 12) {
                        PlayerFace(name: s.title, sport: pk.sport, size: 40)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(s.title).font(.body.weight(.semibold)).lineLimit(1)
                            if let sub = s.sub { Text(sub).font(.footnote).foregroundStyle(.secondary).lineLimit(1) }
                        }
                    }
                    buttons(s, model.current)
                }
                .padding(.vertical, 12)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 2)
        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
        .padding(.horizontal)
    }

    /// A search's matches: every market that has one, under its name.
    @ViewBuilder private func matches(_ tabs: [BoardTab], _ pk: Pack) -> some View {
        if tabs.isEmpty {
            Text("No leg matches “\(model.query)”.").font(.footnote).foregroundStyle(.secondary).padding(.horizontal)
        }
        ForEach(tabs) { t in
            SectionTitle(t.key == Self.lines ? "Lines" : t.title).padding(.horizontal)
            if t.key == Self.lines { lines(t, model.current) } else { players(t, pk) }
        }
    }

    private func card<C: View>(@ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 10) { content() }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
            .padding(.horizontal)
    }

    /// A section's price buttons, three to a line, one rung after another.
    @ViewBuilder private func buttons(_ s: BoardSection, _ eid: String) -> some View {
        ForEach(s.rows) { r in
            let cols = min(r.legs.count, 3)
            ForEach(Array(stride(from: 0, to: r.legs.count, by: 3)), id: \.self) { i in
                HStack(spacing: 8) {
                    ForEach(r.legs[i..<min(i + 3, r.legs.count)], id: \.label) { l in LegButton(model: model, eid: eid, leg: l) }
                    ForEach(0..<max(0, cols - (min(i + 3, r.legs.count) - i)), id: \.self) { _ in Color.clear.frame(maxWidth: .infinity) }
                }
            }
        }
    }
}

/// Popular's props: one leg per player, the one nearest a 65% chance among his overs and yes legs in Mike's 55–80%
/// range that this book posts; the players with the most markets first (the game's stars), eight at most. Players on
/// the ban list are left out (the stat tabs still list everyone).
enum Popular {
    static func props(_ pk: Pack, eid: String, pricer: Pricer, bans: [Ban], limit: Int = 8) -> [PackLeg] {
        let all = pk.legs.values.filter { !($0.player ?? "").isEmpty }
        let markets = Dictionary(grouping: all) { $0.player! }.mapValues(\.count)
        var best: [String: PackLeg] = [:]
        for l in all where l.side != "under" && l.side != "no" && l.p >= 0.55 && l.p <= 0.8 {
            guard let x = pricer.leg(eid, l.label), !x.unavailable, x.price.isFinite else { continue }
            if Bans.banned(bans, l.label, league: pk.sport, player: l.player) { continue }
            let who = l.player!
            if let b = best[who] {
                let (d, e) = (abs(l.p - 0.65), abs(b.p - 0.65))
                if d > e || (d == e && l.label >= b.label) { continue }
            }
            best[who] = l
        }
        return best.values.sorted { a, b in
            let (x, y) = (markets[a.player!] ?? 0, markets[b.player!] ?? 0)
            return x != y ? x > y : a.player! < b.player!
        }.prefix(limit).map { $0 }
    }

    /// What the leg is, without the player's name: "25+ points", "Over 24.5 points", "Anytime TD".
    static func what(_ l: PackLeg) -> String {
        let short = Fmt.label(Build.shortLeg(l))
        if l.side == "over" || l.side == "under", l.point != nil { return short + " " + Build.statTitle(l.stat).lowercased() }
        return short
    }
}

/// A game's main lines, a row per team: the spread and the total at the number nearest even money, and to win.
/// Nil for a three-way game (soccer), a matchup that isn't "Away @ Home", or when none of the three is there.
enum MainLines {
    struct Row: Identifiable {
        let name: String, short: String, logo: String?
        let spread: PackLeg?, total: PackLeg?, win: PackLeg?
        var id: String { name }
    }

    static func rows(_ pk: Pack, art: GameLive?) -> [Row]? {
        let parts = pk.matchup.components(separatedBy: " @ ")
        let game = pk.legs.values.filter { ($0.player ?? "").isEmpty }
        guard parts.count == 2, !game.contains(where: { $0.stat == "draw" }) else { return nil }
        func away(_ l: PackLeg) -> Bool? {
            guard let t = l.team, !t.isEmpty else { return nil }
            return parts[0].contains(t) ? true : parts[1].contains(t) ? false : nil
        }
        /// The two-sided rung nearest even money.
        func main(_ ls: [PackLeg], _ key: (PackLeg) -> Double) -> [PackLeg] {
            let off = { (pair: [PackLeg]) in pair.reduce(0) { $0 + abs($1.p - 0.5) } }
            return Dictionary(grouping: ls, by: key).filter { $0.value.count == 2 }.sorted { $0.key < $1.key }.map(\.value)
                .min { off($0) < off($1) } ?? []
        }
        let spread = main(game.filter { ($0.stat == "spread" || $0.stat == "puck line") && away($0) != nil && $0.point != nil }) {
            (away($0) == true ? 1 : -1) * ($0.point ?? 0) + 0
        }
        let total = main(game.filter { ($0.stat == "total" || $0.stat == "goals") && $0.point != nil && ($0.side == "over" || $0.side == "under") }) { $0.point ?? 0 }
        let win = game.filter { $0.stat == "moneyline" }
        let rows = [true, false].map { isAway in
            let side = isAway ? art?.away : art?.home
            return Row(name: parts[isAway ? 0 : 1], short: side.flatMap { $0.abbr.isEmpty ? nil : $0.abbr } ?? parts[isAway ? 0 : 1], logo: side?.logo,
                       spread: spread.first { away($0) == isAway }, total: total.first { $0.side == (isAway ? "over" : "under") },
                       win: win.first { away($0) == isAway })
        }
        return rows.contains { $0.spread != nil || $0.total != nil || $0.win != nil } ? rows : nil
    }
}

struct MainLinesCard: View {
    @ObservedObject var model: BuildModel
    let eid: String
    let rows: [MainLines.Row]
    let ufc: Bool
    @Environment(\.theme) private var theme
    private static let name: CGFloat = 104

    var body: some View {
        // only the columns this game has (a fight has no spread)
        let spread = rows.contains { $0.spread != nil }, total = rows.contains { $0.total != nil }, win = rows.contains { $0.win != nil }
        let heads = [spread ? "SPREAD" : nil, total ? "TOTAL" : nil, win ? "TO WIN" : nil].compactMap { $0 }
        VStack(spacing: 10) {
            HStack(spacing: 8) {
                Color.clear.frame(width: Self.name, height: 1)
                ForEach(heads, id: \.self) {
                    Text($0).font(.caption2.weight(.semibold)).foregroundStyle(.tertiary).frame(maxWidth: .infinity)
                }
            }
            ForEach(rows) { r in
                HStack(spacing: 8) {
                    HStack(spacing: 8) {
                        TeamLogo(url: r.logo, name: r.name, size: 32, round: ufc)
                        Text(r.short).font(.callout.weight(.bold)).lineLimit(2).minimumScaleFactor(0.7)
                    }
                    .frame(width: Self.name, alignment: .leading)
                    .accessibilityElement(children: .ignore).accessibilityLabel(r.name)
                    if spread { cell(r.spread, r.spread?.point.map { ($0 > 0 ? "+" : "") + String(format: "%g", $0) }) }
                    if total { cell(r.total, r.total.flatMap { l in l.point.map { (l.side == "over" ? "O " : "U ") + String(format: "%g", $0) } }) }
                    if win { cell(r.win, nil) }
                }
            }
        }
        .padding(16)
        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
        .padding(.horizontal)
    }

    @ViewBuilder private func cell(_ leg: PackLeg?, _ short: String?) -> some View {
        if let leg { LegButton(model: model, eid: eid, leg: leg, short: short ?? "", chance: false) }
        else { Text("—").foregroundStyle(.tertiary).frame(maxWidth: .infinity, minHeight: 48) }
    }
}

/// A price button: the short leg ("Over 2.5", "CLE +2.5", "Anytime TD"), then the book's price and the fair chance.
/// On the slip it takes the accent as a tint and a ring; dimmed with "—" when this book doesn't post it.
/// `short` replaces the leg's own short name (the main lines' "+7.5", "O 228.5"; empty for none).
struct LegButton: View {
    @ObservedObject var model: BuildModel
    let eid: String
    let leg: PackLeg
    var short: String? = nil
    var chance = true

    var body: some View {
        let x = model.pricer.leg(eid, leg.label)
        let on = model.has(eid, leg.label)
        let off = x == nil || x!.unavailable
        let name = short ?? Build.shortLeg(leg)
        Button { model.toggle(eid, leg.label) } label: {
            VStack(spacing: 2) {
                if !name.isEmpty {
                    Text(Fmt.label(name)).font(.caption).lineLimit(1).minimumScaleFactor(0.75).foregroundStyle(.secondary)
                }
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text(off ? "—" : Fmt.am(x!.price)).font(.system(.subheadline, design: .monospaced).weight(.bold))
                    if chance { Text(Fmt.pct(leg.p)).font(.caption2.monospacedDigit()).foregroundStyle(.secondary) }
                }
            }
            .priceCell(on: on, dim: off)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(Fmt.label(leg.label)) \(off ? "not at \(model.book.rawValue)" : Fmt.am(x!.price))\(on ? ", on your slip" : "")")
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}
