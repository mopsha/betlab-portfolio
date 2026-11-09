import SwiftUI

// Today's pieces (the overhaul, Nov 4; mockup V3-Today): the day's units as the number the screen leads with, one card
// per open bet with its game's score and its legs as rings, parlays as cards that scroll sideways, and a game in the feed
// with its two logos. The live states are the Live tab's (Live.swift); nothing here decides what shows (Feed.swift does).

/// The day so far: what today's settled bets made, in units, and what is still riding.
struct TodayUnits: Equatable {
    var settled = 0          // bets settled today
    var net = 0.0            // what they made
    var inPlay = 0.0         // units on today's open bets (a bonus bet's stake isn't yours)
    var series: [Double] = []   // the day's running total after each settled bet, from 0

    /// Your record's bets (real only once real money started) whose game is today, in start order.
    static func of(_ bets: [MyBet], realMode: Bool, now: Date = Date()) -> TodayUnits {
        let day = BetMath.etDay(now)
        let mine = BetMath.recordBets(bets, realMode: realMode).counted.filter { BetMath.day($0) == day }
        let done = mine.filter(BetMath.isSettled).sorted { (BetMath.start($0) ?? $0.placedAt) < (BetMath.start($1) ?? $1.placedAt) }
        var out = TodayUnits(settled: done.count)
        var run = 0.0
        out.series = [0] + done.map { run += BetMath.profit($0) ?? 0; return run }
        out.net = run
        out.inPlay = mine.filter { $0.isOpen && !$0.isBonus }.reduce(0) { $0 + BetMath.stake($1) }
        return out
    }
}

/// The top of Today: the date, then the day's units large (green or red) with what is still in play, and the day's line
/// once two bets have settled. A day with no bet yet says so quietly instead of showing a zero.
struct TodayHero: View {
    let date: String
    let u: TodayUnits?       // nil: another day (Tomorrow, This week) shows the date alone

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(date).font(.footnote.weight(.semibold)).foregroundStyle(.secondary)
            if let u {
                if u.settled == 0 && u.inPlay == 0 {
                    Text("No bets today yet.").font(.title3.weight(.semibold)).foregroundStyle(.secondary)
                } else {
                    HStack(alignment: .bottom) {
                        VStack(alignment: .leading, spacing: 4) {
                            if u.settled > 0 {
                                HeroNumber(text: KitLive.units(u.net, signed: true), color: u.net > 0 ? .green : u.net < 0 ? .red : .primary)
                                Text(u.inPlay > 0 ? "today · \(KitLive.units(u.inPlay)) still in play" : "today")
                                    .font(.footnote).foregroundStyle(.secondary)
                            } else {
                                HeroNumber(text: KitLive.units(u.inPlay))
                                Text("in play today · nothing settled yet").font(.footnote).foregroundStyle(.secondary)
                            }
                        }
                        Spacer(minLength: 12)
                        if u.series.count > 2 {
                            Spark(values: u.series, color: u.net >= 0 ? .green : .red).frame(width: 120, height: 44).padding(.bottom, 20)
                        }
                    }
                }
            }
        }
        .padding(.horizontal, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

/// One game on Today, once: its score between the two logos, then every open bet on it as a row (Mike, Nov 4: "it
/// shouldn't have two cards for the same game"). A bet across several games gets a card of its own, headed by its
/// logos. Each row opens its bet.
struct TodayGameCard: View {
    let bets: [(MyBet, BetLive)]
    var open: (String) -> Void

    var body: some View {
        let first = bets[0].1
        let one = first.games.count == 1 ? first.games.first : nil
        let lit = one ?? first.games.first { $0.state == "in" } ?? first.games.first
        GlowCard(left: one.flatMap { Color(hex: $0.reading.away.color) }, right: Color(hex: lit?.reading.home.color)) {
            VStack(alignment: .leading, spacing: 14) {
                if let one {
                    ScoreHead(g: one)
                } else {
                    let on = first.games.filter { $0.state == "in" }.count
                    HStack {
                        ArtStack(urls: KitLive.logos(first))
                        Spacer()
                        if on > 0 { LivePill(text: "\(on) of \(first.games.count) live") }
                        else if let next = first.games.filter({ $0.state == "pre" }).map(\.start).min() {
                            Text(Fmt.time(next)).font(.caption.weight(.bold)).foregroundStyle(.secondary)
                        }
                    }
                }
                ForEach(bets, id: \.0.betId) { bet, b in
                    Hairline()
                    Button { open(bet.betId) } label: { TodayBetLine(bet: bet, b: b).contentShape(Rectangle()) }
                        .buttonStyle(.plain)
                }
            }
        }
    }

    /// Bets grouped by game: the ones on a single game share that game's card, in the order given.
    static func groups(_ cards: [(MyBet, BetLive)]) -> [[(MyBet, BetLive)]] {
        var out: [[(MyBet, BetLive)]] = []
        var at: [String: Int] = [:]
        for c in cards {
            if c.1.games.count == 1, let key = c.1.games.first?.key {
                if let i = at[key] { out[i].append(c) } else { at[key] = out.count; out.append([c]) }
            } else {
                out.append([c])
            }
        }
        return out
    }
}

/// One bet inside a game's card: its name, where it stands, and its legs as rings (dots past four legs).
struct TodayBetLine: View {
    let bet: MyBet
    let b: BetLive

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(name).font(.headline).lineLimit(1).minimumScaleFactor(0.75)
                Text(standing).font(.footnote).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.8)
            }
            Spacer(minLength: 6)
            if b.legs.count <= 4 {
                HStack(spacing: 8) { ForEach(Array(b.legs.enumerated()), id: \.offset) { LegRing(l: $0.element, tap: false) } }
                    .padding(.trailing, 4).padding(.bottom, 3)       // the badges hang past the rings
            } else {
                LegDots(legs: b.legs)
            }
        }
    }

    private var name: String { b.legs.count > 1 ? Stats.betName(legs: bet.legs, label: nil, price: nil, n: max(b.legs.count, Stats.legsOf(bet))) : BetMath.what(bet) }

    /// "1 of 4 in · +333"; a single: where its leg stands.
    private var standing: String {
        let price = bet.price.map { Fmt.am($0) }
        let state = b.status == "won" ? "Won" : b.legs.count > 1 ? "\(b.hit) of \(b.total) in" : b.legs.first?.text ?? ""
        return [state.isEmpty ? nil : state, price].compactMap { $0 }.joined(separator: " · ")
    }
}

/// Today's locks still to come, each with its countdown (the first one bold).
struct LocksCard: View {
    let locks: [GameDay.Lock]
    let now: Date
    private static let shown = 4      // locks listed; the rest are counted

    var body: some View {
        let ahead = locks.filter { $0.at > now.addingTimeInterval(-60) }
        GlowCard(padding: 14) {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(ahead.prefix(Self.shown).enumerated()), id: \.element.slate) { i, l in
                    HStack {
                        Text(l.title).font(.footnote.weight(i == 0 ? .semibold : .regular)).lineLimit(1)
                        Spacer()
                        Text(GameDay.countdown(l.at, now: now)).font(.footnote.monospacedDigit().weight(i == 0 ? .bold : .regular))
                            .foregroundStyle(i == 0 ? Color.accentColor : .secondary)
                    }
                }
                if ahead.count > Self.shown { Text("+\(ahead.count - Self.shown) more later today").font(.caption).foregroundStyle(.secondary) }
            }
        }
    }
}

/// A parlay as a small card: its league and start in a chip, the logos of its games, the price large, the legs in a line.
struct TicketCard: View {
    let t: Ticket
    let title: String
    let logos: [String]
    let today: Bool
    @EnvironmentObject private var store: BetStore
    @Environment(\.theme) private var theme

    var body: some View {
        let legs = SlipBooks.legs(t)
        GlowCard(padding: 16) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 6) {
                    Text(t.kind == "sgp" ? Watch.nicks(t.matchup)      // a watched game's own parlay (Nov 7)
                         : "\(Fmt.sportShort[t.sport] ?? Fmt.sportName(t.sport)) · \(today ? Fmt.time(t.commenceTime) : Fmt.dayTime(t.commenceTime))")
                        .font(.caption2.weight(.semibold)).lineLimit(1)
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(Color.primary.opacity(0.08), in: Capsule())
                    Spacer(minLength: 2)
                    if store.marks[t.sgpId] != nil {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).font(.footnote).accessibilityLabel("Placed")
                    }
                    if !logos.isEmpty { ArtStack(urls: Array(logos.prefix(3)), size: 26) }
                }
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(Fmt.am(t.price ?? t.fairPrice)).font(.system(size: 26, weight: .bold, design: .monospaced))
                    if t.price == nil { Text("FAIR").font(.caption2.weight(.semibold)).foregroundStyle(.tertiary) }
                }
                Text(t.kind == "td" ? "Anytime TD ticket" : t.body.style == "single" ? "Best single" : "\(legs.count) legs" + ((t.body.games?.count ?? 0) > 1 ? " · \(t.body.games!.count) games" : ""))
                    .font(.caption.weight(.semibold))
                Text(legs.prefix(3).map { Fmt.label($0.label) }.joined(separator: " · "))
                    .font(.footnote).foregroundStyle(.secondary).lineLimit(2, reservesSpace: true)
            }
        }
        .frame(width: 216)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title), \(Fmt.am(t.price ?? t.fairPrice))")
    }
}

/// A parlay in full, in a sheet: its story, its legs game by game with their prices, each book's price box and betslip
/// link, and I placed this (what the feed's fold-out row held).
struct TicketSheet: View {
    let t: Ticket
    let title: String
    @EnvironmentObject private var store: BetStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List { Group {
                Section {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(title).font(.headline)
                        Text("\(Fmt.dayTime(t.commenceTime)) · fair \(Fmt.am(t.fairPrice))").font(.footnote).foregroundStyle(.secondary)
                        if let s = t.body.story ?? t.body.why { Text(s).font(.footnote).foregroundStyle(.secondary).padding(.top, 2) }
                    }
                }
                // a multi-game ticket carries its legs twice (per game and flat), so the flat list only when there are no games
                if let games = t.body.games, !games.isEmpty {
                    ForEach(Array(games.enumerated()), id: \.offset) { _, g in
                        Section("\(Fmt.matchup(g.matchup, sport: t.sport)) · \(Fmt.time(g.commenceTime))") {
                            ForEach(Array(g.legs.enumerated()), id: \.offset) { _, l in legRow(l) }
                        }
                    }
                } else {
                    Section("Legs") { ForEach(Array((t.body.legs ?? []).enumerated()), id: \.offset) { _, l in legRow(l) } }
                }
                Section {
                    VStack(alignment: .leading, spacing: 10) {
                        if t.kind == "over" {
                            HStack(spacing: 10) {
                                MarkControl(input: store.input(for: t))
                                if let link = t.body.link { BookButton(book: "FanDuel", link: link) }
                            }
                            if t.body.link != nil, t.body.linkMain == true, let main = Build.mainLineText([true]) {
                                Text(main).font(.caption2).foregroundStyle(.secondary)
                            }
                        } else {
                            SlipBooks(t: t)
                            MarkControl(input: store.input(for: t))
                        }
                    }
                    .padding(.vertical, 4)
                }
            }.themedRows() }.themedList()
            .navigationTitle("Parlay")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .presentationDetents([.medium, .large])
    }

    private func legRow(_ l: Leg) -> some View {
        HStack {
            Text(Fmt.label(l.label)).font(.footnote)
            Spacer()
            Text(Fmt.am(l.price ?? l.fairPrice) + (l.dkPrice.map { " · DK \(Fmt.am($0))" } ?? "") + (l.nvPrice.map { " · NV \(Fmt.am($0))" } ?? ""))
                .font(.footnote.monospacedDigit()).foregroundStyle(.secondary)
        }
    }
}

/// A game in the feed: its two logos, then when, who, and its one or two best things to look at (GameRowView).
struct FeedGameCard: View {
    let g: FeedGame
    let art: GameLive?

    var body: some View {
        let art = art?.reading                  // soccer: home first (Nov 5)
        GlowCard(left: Color(hex: art?.away.color), right: Color(hex: art?.home.color), padding: 14) {
            HStack(alignment: .top, spacing: 12) {
                if let art {
                    VStack(spacing: 6) {
                        TeamArt(s: art.away, size: 26, ufc: art.sport == "ufc")
                        TeamArt(s: art.home, size: 26, ufc: art.sport == "ufc")
                    }
                }
                GameRowView(g: g)
                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(.tertiary).padding(.top, 4)
            }
        }
    }
}

/// A sport chip, with the league's own logo where ESPN has one.
struct SportChip: View {
    let title: String
    var league: String? = nil
    let selected: Bool
    let action: () -> Void
    @Environment(\.theme) private var theme
    private static let logos: Set<String> = ["nfl", "nba", "nhl", "mlb", "wnba"]

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let league, Self.logos.contains(league) {
                    LiveImage(url: "https://a.espncdn.com/i/teamlogos/leagues/500/\(league).png", size: 16) { EmptyView() }
                }
                Text(title).font(.subheadline.weight(.semibold))
            }
            .padding(.horizontal, 13).padding(.vertical, 7)
            .background(selected ? AnyShapeStyle(Color.primary) : AnyShapeStyle(theme.card ?? Color(.secondarySystemGroupedBackground)), in: Capsule())
            .foregroundStyle(selected ? Color(.systemBackground) : .primary)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}
