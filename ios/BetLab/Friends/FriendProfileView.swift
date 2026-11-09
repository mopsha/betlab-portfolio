import SwiftUI

/// A friend's profile (web app/friends/[handle]; rebuilt in the overhaul's look, Nov 5): their units won as the number
/// that leads, the record, open bets (Tail while their game hasn't started), recent settled bets, badges, and the
/// players and teams they bet most as pictures. Only for accepted friends; units at the prices they took, never money.
struct FriendProfileView: View {
    let friend: Profile
    @EnvironmentObject private var store: BetStore
    @EnvironmentObject private var auth: AuthStore
    @Environment(\.theme) private var theme
    @StateObject private var live = LiveModel()
    @StateObject private var rx = ReactionStore()
    @State private var bets: [MyBet] = []
    @State private var teams: [PlayerCard] = []
    @State private var loaded = false
    @State private var gone = false
    private static let recent = 15

    var body: some View {
        // their record counts as their own Live does: real bets once they have any
        let counted = BetMath.recordBets(bets, realMode: false).counted
        let open = counted.filter(\.isOpen).sorted { (BetMath.start($0) ?? $0.placedAt) < (BetMath.start($1) ?? $1.placedAt) }
        let recent = Array(counted.filter { !$0.isOpen }.sorted { $0.placedAt > $1.placedAt }.prefix(Self.recent))
        let have = Set(store.bets.map(Social.betKey))
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                hero(counted)
                if !open.isEmpty {
                    SectionTitle("Open", note: "\(open.count)").padding(.top, 8)
                    ForEach(open) {
                        BetCardView(b: $0, live: live.bets[$0.betId], friend: true, tailed: have.contains(Social.betKey($0)), carded: true,
                                    rx: rx.on($0.betId, me: me, api: store.api))
                    }
                }
                if !recent.isEmpty {
                    SectionTitle("Recent").padding(.top, 8)
                    ForEach(recent) { BetCardView(b: $0, live: live.bets[$0.betId], friend: true, carded: true, rx: rx.on($0.betId, me: me, api: store.api)) }
                }
                badges(counted)
                shelves(counted)
                foot
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 28)
        }
        .background(theme.pageColor.ignoresSafeArea())
        .navigationTitle(friend.name)
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task(id: store.refreshTick) { await load() }
        .task(id: bets.map(\.betId).joined(separator: ",")) {
            guard !bets.isEmpty else { return }
            while !Task.isCancelled {
                await live.refresh(store.api, open: Set(open.map(\.betId)), done: Set(recent.map(\.betId)), friends: friend.userId)
                try? await Task.sleep(for: live.soon ? LiveModel.fast : LiveModel.slow)
            }
        }
    }

    // MARK: who, and the number that leads

    @ViewBuilder private func hero(_ counted: [MyBet]) -> some View {
        let t = BetMath.record(counted).total
        let run = Stats.streaks(counted)
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 14) {
                AvatarView(p: friend, size: 64)
                VStack(alignment: .leading, spacing: 2) {
                    Text(friend.name).font(.title2.weight(.heavy)).lineLimit(1).minimumScaleFactor(0.7)
                    Text("@\(friend.handle)").font(.subheadline).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            if t.bets > 0 {
                VStack(alignment: .leading, spacing: 2) {
                    HeroNumber(text: BetMath.signedUnits(t.units), color: tone(t.units) ?? .primary)
                        .accessibilityLabel("\(BetMath.signedUnits(t.units)) units")
                    Text("units won, at the prices \(friend.name) took").font(.footnote).foregroundStyle(.secondary)
                }
                HStack(spacing: 10) {
                    stat("Record", "\(t.won)-\(t.lost)\(t.push > 0 ? "-\(t.push)" : "")")
                    stat("ROI", Fmt.signed(t.roi), tone(t.roi))
                    if let k = run.kind { stat("Streak", "\(run.n)\(k == "won" ? "W" : "L")", k == "won" ? .green : .red) }
                }
            } else if loaded && counted.isEmpty {
                GlowCard {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("No bets shared yet").font(.headline)
                        Text("\(friend.name) may have sharing off in Settings.").font(.footnote).foregroundStyle(.secondary)
                    }
                }
            } else if !loaded {
                ProgressView().frame(maxWidth: .infinity).padding(.top, 30)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(alignment: .top) { PageGlow(left: AvatarView.color(friend.handle), right: nil) }
    }

    private func stat(_ title: String, _ value: String, _ color: Color? = nil) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased()).font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
            Text(value).font(.system(size: 20, weight: .heavy)).monospacedDigit().foregroundStyle(color ?? .primary)
                .lineLimit(1).minimumScaleFactor(0.7)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    // MARK: badges

    @ViewBuilder private func badges(_ counted: [MyBet]) -> some View {
        let got = Achievements.all(counted).filter { $0.earned != nil }
        if !got.isEmpty {
            SectionTitle("Badges", note: "\(got.count)").padding(.top, 8)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 10) {
                    ForEach(got) { b in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(b.icon).font(.title)
                            Text(b.title).font(.subheadline.weight(.bold)).lineLimit(1)
                            Text(b.how).font(.caption).foregroundStyle(.secondary).lineLimit(3).fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 0)
                            Text(Fmt.shortDay(Models.date((b.earned ?? "") + "T16:00:00Z") ?? Date()))
                                .font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
                        }
                        .padding(14)
                        .frame(width: 156, height: 150, alignment: .topLeading)
                        .background(theme.cardColor, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                        .accessibilityElement(children: .combine)
                    }
                }
            }
            .scrollClipDisabled()
        }
    }

    // MARK: players and teams

    @ViewBuilder private func shelves(_ counted: [MyBet]) -> some View {
        let players = Players.all(counted)
        if !players.isEmpty {
            SectionTitle("Players", note: "most bet").padding(.top, 8)
            PictureShelf(cards: players, kind: .player)
        }
        if !teams.isEmpty {
            SectionTitle("Teams", note: "most bet").padding(.top, 8)
            PictureShelf(cards: teams, kind: .team)
        }
        if !players.isEmpty || !teams.isEmpty {
            Text("The ring is the share of graded legs that hit; the badge is won-lost. Tap a picture for every leg.")
                .font(.footnote).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private var foot: some View {
        VStack(alignment: .leading, spacing: 10) {
            if gone { Text("Removed.").font(.footnote).foregroundStyle(.secondary) }
            else {
                HStack { ActButton("Remove friend", kind: .quiet, wide: false, confirm: "Yes, remove") { await end() }; Spacer() }
            }
        }
        .padding(.top, 16)
    }

    private func load() async {
        bets = await BetStore.withStarts((try? await store.api.rpc("friend_bets", ["friend": friend.userId]) as [MyBet]) ?? [], api: store.api)
        loaded = true
        let counted0 = BetMath.recordBets(bets, realMode: false).counted
        await rx.load(store.api, counted0.filter(\.isOpen).map(\.betId)
                        + counted0.filter { !$0.isOpen }.sorted { $0.placedAt > $1.placedAt }.prefix(Self.recent).map(\.betId))
        // their parlays' games (the shared tickets), for the team pictures
        let counted = BetMath.recordBets(bets, realMode: false).counted
        teams = Cards.teams(counted, tickets: await Cards.tickets(store.api, counted))
    }

    private func end() async -> String? {
        do {
            try await store.api.delete("friendships", eq: [("requester", friend.userId)])     // row-level security: only your pair
            try await store.api.delete("friendships", eq: [("addressee", friend.userId)])
            gone = true
            return nil
        } catch { return (error as? AuthError)?.message ?? "Couldn't do that." }
    }

    private var me: String { auth.session?.userId ?? "" }

    private func tone(_ x: Double?) -> Color? { guard let x else { return nil }; return x > 0 ? .green : x < 0 ? .red : nil }
}
