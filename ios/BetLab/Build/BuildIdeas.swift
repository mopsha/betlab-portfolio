import SwiftUI

/// Ideas (Nov 5; the themed slips of Nov 4, web Builder's themes): Underdogs, Favorites, Overs only and, in soccer,
/// Both teams score. Each is a card with its legs and what it's worth; a tap loads it into the slip. They are plain
/// parlays of the best-priced legs that fit across the sport's next games, at the header's book, so the price is the
/// legs' own, exact. Players and teams on the ban list are left out (Build.themedSlip).
struct IdeasTab: View {
    @ObservedObject var model: BuildModel
    let art: [String: GameLive]
    @Environment(\.theme) private var theme

    var body: some View {
        let themes = Build.SlipTheme.allCases.filter { $0 != .btts || model.sport == "soccer" }
        let fresh = model.ideasFor == model.ideasKey
        VStack(alignment: .leading, spacing: 12) {
            Text("Parlays of one leg a game from the next \(min(BuildModel.scan, model.inSport.count)) games at \(model.book.rawValue). Tap one to put it on your slip.")
                .font(.footnote).foregroundStyle(.secondary)
            ForEach(themes) { t in
                if let s = model.ideas[t], fresh { idea(t, s) } else { waiting(t, fresh: fresh) }
            }
        }
        .padding(.horizontal)
    }

    private func idea(_ t: Build.SlipTheme, _ s: Build.ThemedSlip) -> some View {
        Button { model.use(s.legs) } label: {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .firstTextBaseline) {
                    Text(t.title).font(.title3.weight(.bold))
                    Spacer(minLength: 8)
                    Text(Fmt.am(Odds.am(s.dec))).font(.system(.title3, design: .monospaced).weight(.bold))
                }
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(s.legs, id: \.self) { l in leg(l) }
                }
                CellRow(cells: [.init(name: "CHANCE", value: Fmt.pct(s.p)),
                                .init(name: "FAIR PRICE", value: Fmt.am(Odds.am(1 / s.p))),
                                .init(name: "VALUE", value: Fmt.signed(s.ev), color: s.ev >= 0 ? .green : .red)])
                Text("Use this slip").font(.subheadline.weight(.bold)).foregroundStyle(theme.accent)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(theme.accent.opacity(0.16), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
            }
            .padding(Kit.pad)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
            .contentShape(RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(t.title): \(s.legs.map { Fmt.label($0.label) }.joined(separator: ", ")). Pays \(Fmt.am(Odds.am(s.dec))), \(Fmt.pct(s.p)) to hit. Use this slip")
    }

    /// A leg with its picture, its game under it.
    private func leg(_ l: SlipLeg) -> some View {
        let pk = model.packs[l.eventId]
        let x = pk?.legs[l.label]
        return HStack(spacing: 10) {
            LegArt(leg: x, sport: pk?.sport ?? model.sport, matchup: pk?.matchup ?? "", art: art[l.eventId], size: 30)
            VStack(alignment: .leading, spacing: 0) {
                Text(Fmt.label(l.label)).font(.subheadline.weight(.semibold)).lineLimit(1)
                if let m = pk?.matchup, !m.isEmpty { Text(m).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
            }
            Spacer(minLength: 6)
            if let x = model.pricer.leg(l.eventId, l.label), !x.unavailable {
                Text(Fmt.am(x.price)).font(.system(.footnote, design: .monospaced).weight(.semibold)).foregroundStyle(.secondary)
            }
        }
    }

    private func waiting(_ t: Build.SlipTheme, fresh: Bool) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(t.title).font(.title3.weight(.bold))
            HStack(spacing: 8) {
                if !fresh || model.ideasLoading { ProgressView().controlSize(.small) }
                Text(!fresh || model.ideasLoading ? "Looking through the next games…" : "Not enough games fit that theme right now.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .padding(Kit.pad)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: Kit.radius, style: .continuous))
    }
}

/// A leg's picture: the player's photo, else its team's logo, else the first letters of what it is.
struct LegArt: View {
    let leg: PackLeg?
    let sport: String
    let matchup: String
    let art: GameLive?
    var size: CGFloat = 40

    var body: some View {
        if let who = leg?.player, !who.isEmpty {
            PlayerFace(name: who, sport: sport, size: size)
        } else {
            let team = leg?.team ?? ""
            TeamLogo(url: BuildArt.logo(team, art, matchup: matchup), name: team.isEmpty ? (leg?.side ?? "?") : team, size: size * 0.72, round: sport == "ufc")
                .frame(width: size, height: size)
                .background(Color(.tertiarySystemFill), in: Circle())
        }
    }
}
