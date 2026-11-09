import SwiftUI

/// Friends (web app/friends, Oct 27): your friends' bets as a feed, newest first, with Tail on the open ones (W16);
/// requests to answer; adding a friend by @handle or email; your own name and @handle. Friends see bets, never money.
/// Each bet is Live's own card with the live tracker. The logic is Social.swift; the views are below (rebuilt in the
/// overhaul's look, Nov 5).
@MainActor
final class FriendsModel: ObservableObject {
    @Published var me = ""
    @Published var profile: Profile?
    @Published var profiles: [Profile] = []
    @Published var friendships: [Friendship] = []
    @Published var bets: [MyBet] = []
    @Published var loaded = false
    @Published var error: String?

    var circle: Social.Circle { Social.circle(me, friendships, profiles) }

    func load(_ api: SupabaseClient, me: String) async {
        self.me = me
        do {
            async let p: [Profile] = api.rows("profiles")
            async let f: [Friendship] = api.rows("friendships")
            (profiles, friendships) = try await (p, f)
            profile = profiles.first { $0.userId == me }
            bets = circle.friends.isEmpty ? [] : await BetStore.withStarts((try? await api.rpc("friend_bets") as [MyBet]) ?? [], api: api)
            error = nil
        } catch { self.error = (error as? AuthError)?.message ?? error.localizedDescription }
        loaded = true
    }

    /// Your name and @handle (web saveProfile).
    func saveProfile(_ api: SupabaseClient, name: String, handle text: String) async -> String? {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty, n.count <= 40 else { return "Your name: 1 to 40 characters." }
        guard let h = Social.cleanHandle(text) else { return "Your @handle: 3 to 20 letters, digits or _." }
        do { try await api.upsert("profiles", ["user_id": me, "name": n, "handle": h], onConflict: "user_id") } catch {
            let m = (error as? AuthError)?.message ?? ""
            return m.range(of: "duplicate key|unique", options: [.regularExpression, .caseInsensitive]) != nil ? "@\(h) is taken: try another." : m
        }
        await load(api, me: me)
        return nil
    }

    /// Ask someone to be friends, found by their exact @handle or email (find_person: no browsing).
    func request(_ api: SupabaseClient, _ q: String) async -> String? {
        guard profile != nil else { return "Set your name and @handle first." }
        guard let found = (try? await api.rpc("find_person", ["q": q]) as [Profile])?.first else {
            return "No one with that @handle or email. Check the spelling, or ask them for their @handle."
        }
        if friendships.contains(where: { ($0.requester == found.userId && $0.addressee == me) || ($0.addressee == found.userId && $0.requester == me) }) {
            return "You and \(found.name) are already friends, or a request is waiting."
        }
        do { try await api.insert("friendships", ["addressee": found.userId]) } catch { return (error as? AuthError)?.message ?? "Couldn't send that." }
        await load(api, me: me)
        return nil
    }

    /// Accept or decline a request someone sent you.
    func answer(_ api: SupabaseClient, from: String, accept: Bool) async -> String? {
        do {
            if accept { _ = try await api.rpc("accept_friend", ["from_user": from]) as [Bool] }
            else { try await api.delete("friendships", eq: [("requester", from), ("addressee", me)]) }
        } catch { return (error as? AuthError)?.message ?? "Couldn't do that." }
        await load(api, me: me)
        return nil
    }

    /// End a friendship, or take back a request you sent.
    func end(_ api: SupabaseClient, _ other: String) async -> String? {
        do {
            try await api.delete("friendships", eq: [("requester", me), ("addressee", other)])
            try await api.delete("friendships", eq: [("requester", other), ("addressee", me)])
        } catch { return (error as? AuthError)?.message ?? "Couldn't do that." }
        await load(api, me: me)
        return nil
    }
}


struct FriendsView: View {
    @EnvironmentObject private var store: BetStore
    @EnvironmentObject private var auth: AuthStore
    @StateObject private var m = FriendsModel()
    @StateObject private var live = LiveModel()
    @StateObject private var rx = ReactionStore()
    @Environment(\.scenePhase) private var phase
    @Environment(\.theme) private var theme
    @State private var adding = false
    @State private var editing = false

    var body: some View {
        let c = m.circle
        let items = Social.feed(m.bets, c.friends)
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                if !m.loaded {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 80)
                } else if let e = m.error {
                    GlowCard { Label(e, systemImage: "exclamationmark.triangle").font(.subheadline).foregroundStyle(.red) }
                } else if m.profile == nil {
                    setup
                } else {
                    requests(c.incoming)
                    hero
                    waiting(c.outgoing)
                    row(c.friends)
                    feed(items, friends: c.friends)
                }
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 28)
        }
        .background(theme.pageColor.ignoresSafeArea())
        .navigationTitle("Friends")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $adding) { AddFriendSheet(m: m) }
        .sheet(isPresented: $editing) { if let p = m.profile { ProfileSheet(m: m, name: p.name, handle: p.handle) } }
        .refreshable { await reload() }
        .task(id: store.refreshTick) { await reload() }
        .task(id: "\(phase == .active)|\(m.bets.map(\.betId).joined(separator: ","))") {
            guard phase == .active, !m.bets.isEmpty else { return }
            while !Task.isCancelled {
                let shown = items.map(\.bet)
                await live.refresh(store.api, open: Set(shown.filter(\.isOpen).map(\.betId)),
                                   done: Set(shown.filter { !$0.isOpen }.map(\.betId)), friends: "all")
                try? await Task.sleep(for: live.soon ? LiveModel.fast : LiveModel.slow)
            }
        }
    }

    private func reload() async {
        await m.load(store.api, me: auth.session?.userId ?? "")
        await rx.load(store.api, Social.feed(m.bets, m.circle.friends).map(\.bet.betId))
    }

    // MARK: no profile yet

    private var setup: some View {
        GlowCard(left: theme.accent) {
            VStack(alignment: .leading, spacing: 12) {
                Text("Set up your profile").font(.title3.weight(.heavy))
                Text("Pick the name friends see and an @handle they can find you by. Friends see your bets, results and units, never money.")
                    .font(.footnote).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                ProfileForm(m: m, name: "", handle: Social.suggestHandle(auth.session?.email ?? ""), fresh: true, onCard: true)
            }
        }
    }

    // MARK: requests to answer

    @ViewBuilder private func requests(_ list: [Social.Request]) -> some View {
        if !list.isEmpty {
            SectionTitle("Requests", note: "\(list.count) to answer")
            ForEach(list) { r in
                GlowCard(left: r.other.map { AvatarView.color($0.handle) }) {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 12) {
                            if let p = r.other { AvatarView(p: p, size: 48) }
                            VStack(alignment: .leading, spacing: 2) {
                                Text(r.other?.name ?? "Someone").font(.headline.weight(.bold)).lineLimit(1)
                                Text("\(r.other.map { "@\($0.handle) " } ?? "")wants to be friends").font(.footnote).foregroundStyle(.secondary).lineLimit(1)
                            }
                        }
                        HStack(alignment: .top, spacing: 10) {
                            ActButton("Accept") { await m.answer(store.api, from: r.otherId, accept: true) }
                            ActButton("Decline", kind: .quiet) { await m.answer(store.api, from: r.otherId, accept: false) }
                        }
                    }
                }
            }
        }
    }

    // MARK: you

    /// Your own profile, small: who you are, your units and record, whether friends see your bets, and Add a friend.
    @ViewBuilder private var hero: some View {
        if let p = m.profile {
            let t = BetMath.record(BetMath.recordBets(store.bets, realMode: store.isReal).counted).total
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    AvatarView(p: p, size: 56)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(p.name).font(.title3.weight(.heavy)).lineLimit(1).minimumScaleFactor(0.8)
                        Text("@\(p.handle)").font(.footnote).foregroundStyle(.secondary).lineLimit(1)
                    }
                    Spacer(minLength: 8)
                    if t.bets > 0 {
                        VStack(alignment: .trailing, spacing: 0) {
                            HeroNumber(text: BetMath.signedUnits(t.units), color: t.units > 0 ? .green : t.units < 0 ? .red : .primary, size: 30)
                            Text("\(t.won)-\(t.lost)").font(.footnote.weight(.semibold)).monospacedDigit().foregroundStyle(.secondary)
                        }
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel("\(BetMath.signedUnits(t.units)) units, \(t.won) won, \(t.lost) lost")
                    }
                }
                HStack(spacing: 10) {
                    Button { adding = true } label: { Label("Add a friend", systemImage: "person.badge.plus") }.buttonStyle(KitButton())
                    Button { editing = true } label: { Image(systemName: "pencil") }.buttonStyle(KitButton(kind: .quiet, wide: false))
                        .accessibilityLabel("Change your name or @handle")
                }
                HStack(spacing: 7) {
                    Circle().fill(store.shareBets ? Color.green : Color(.systemGray2)).frame(width: 7, height: 7)
                    Text(store.shareBets ? "Friends see my bets: units, never money" : "Friends can't see my bets: sharing is off in Settings")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .padding(.bottom, 4)
        }
    }

    /// Requests you sent, still waiting: one quiet card.
    @ViewBuilder private func waiting(_ list: [Social.Request]) -> some View {
        if !list.isEmpty {
            GlowCard(padding: 14) {
                VStack(spacing: 12) {
                    ForEach(list) { r in
                        HStack(spacing: 10) {
                            if let p = r.other { AvatarView(p: p, size: 34) }
                            VStack(alignment: .leading, spacing: 1) {
                                Text(r.other?.name ?? "Someone").font(.subheadline.weight(.semibold)).lineLimit(1)
                                Text("Waiting for them to accept").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 6)
                            ActButton("Cancel", kind: .quiet, wide: false, confirm: "Cancel request") { await m.end(store.api, r.otherId) }
                        }
                    }
                }
            }
        }
    }

    // MARK: friends

    /// Your friends as a row of faces, each with how many bets they placed today.
    @ViewBuilder private func row(_ friends: [Profile]) -> some View {
        if !friends.isEmpty {
            let today = BetMath.etDay(Date())
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 14) {
                    ForEach(friends) { f in
                        let n = m.bets.filter { $0.userId == f.userId && Models.date($0.placedAt).map(BetMath.etDay) == today }.count
                        NavigationLink { FriendProfileView(friend: f) } label: { face(f, today: n) }.buttonStyle(.plain)
                            .accessibilityLabel(n > 0 ? "\(f.name), \(n) bet\(n == 1 ? "" : "s") today" : f.name)
                    }
                }
                .padding(.vertical, 4)
            }
            .scrollClipDisabled()
        }
    }

    private func face(_ f: Profile, today n: Int) -> some View {
        VStack(spacing: 6) {
            AvatarView(p: f, size: 58)
                .padding(4)
                .overlay(Circle().strokeBorder(n > 0 ? theme.accent : Color(.systemFill), lineWidth: 2.5))
                .overlay(alignment: .topTrailing) {
                    if n > 0 {
                        Text("\(n)").font(.system(size: 11, weight: .bold, design: .monospaced))
                            .padding(.horizontal, 5).frame(minWidth: 22, minHeight: 20)
                            .foregroundStyle(Color(.systemBackground)).background(Color.primary, in: Capsule())
                            .overlay(Capsule().strokeBorder(theme.pageColor, lineWidth: 2))
                            .offset(x: 4, y: -2)
                    }
                }
            Text(f.name).font(.caption.weight(.semibold)).lineLimit(1)
        }
        .frame(width: 74)
    }

    // MARK: the feed

    @ViewBuilder private func feed(_ items: [(bet: MyBet, who: Profile)], friends: [Profile]) -> some View {
        if items.isEmpty {
            GlowCard {
                VStack(alignment: .leading, spacing: 8) {
                    Image(systemName: friends.isEmpty ? "person.2.fill" : "tray").font(.title2).foregroundStyle(theme.accent)
                    Text(friends.isEmpty ? "No friends yet" : "No bets yet").font(.headline)
                    Text(friends.isEmpty
                         ? "Add someone by their exact @handle or email. Once they accept, their bets show here in units, and you can tail the open ones."
                         : "Your friends' bets show here as they enter them, with Tail on the ones still open.")
                        .font(.footnote).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    if friends.isEmpty, let p = m.profile {
                        Text("They can find you as @\(p.handle).").font(.footnote.weight(.semibold))
                    }
                }
            }
        } else {
            let have = Set(store.bets.map(Social.betKey))
            let day = { (b: MyBet) in Models.date(b.placedAt).map(BetMath.etDay) ?? String(b.placedAt.prefix(10)) }
            let days = items.reduce(into: [String]()) { if $0.last != day($1.bet) { $0.append(day($1.bet)) } }
            ForEach(days, id: \.self) { d in
                let rows = items.filter { day($0.bet) == d }
                SectionTitle(KitSocial.dayTitle(d), note: "\(rows.count) bet\(rows.count == 1 ? "" : "s")").padding(.top, 8)
                ForEach(rows, id: \.bet.betId) { x in
                    BetCardView(b: x.bet, live: live.bets[x.bet.betId], friend: true, who: x.who,
                                tailed: have.contains(Social.betKey(x.bet)), carded: true,
                                rx: rx.on(x.bet.betId, me: m.me, api: store.api))
                }
            }
        }
    }
}

/// A person's initial on a steady color from their handle.
struct AvatarView: View {
    let p: Profile
    var size: CGFloat = 36

    /// The person's color: the avatar's fill, and the soft light on their card.
    static func color(_ handle: String) -> Color { Color(hue: Double(Social.hue(handle)) / 360, saturation: 0.55, brightness: 0.62) }

    var body: some View {
        Text(p.name.trimmingCharacters(in: .whitespaces).first.map { String($0).uppercased() } ?? "?")
            .font(.system(size: size * 0.45, weight: .bold)).foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(Self.color(p.handle), in: Circle())
            .accessibilityHidden(true)
    }
}

/// A button that runs a write and shows its error; `confirm` asks a second tap first (Remove, Cancel request).
struct ActButton: View {
    let title: String
    var kind: KitButton.Kind = .solid
    var wide = true
    var confirm: String? = nil
    let run: () async -> String?
    @State private var busy = false
    @State private var sure = false
    @State private var msg: String?

    init(_ title: String, kind: KitButton.Kind = .solid, wide: Bool = true, confirm: String? = nil, run: @escaping () async -> String?) {
        (self.title, self.kind, self.wide, self.confirm, self.run) = (title, kind, wide, confirm, run)
    }

    var body: some View {
        VStack(alignment: .trailing, spacing: 4) {
            HStack(spacing: 8) {
                if let c = confirm, sure {
                    Button(c) { go() }.buttonStyle(KitButton(kind: .danger, wide: wide, height: wide ? 44 : 36))
                    Button("Keep") { sure = false }.buttonStyle(KitButton(kind: .quiet, wide: wide, height: wide ? 44 : 36))
                } else {
                    Button(busy ? "\(title)…" : title) { if confirm != nil { sure = true } else { go() } }
                        .buttonStyle(KitButton(kind: kind, wide: wide, height: wide ? 44 : 36))
                }
            }
            .disabled(busy)
            if let msg { Text(msg).font(.caption2).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
        }
    }

    private func go() { busy = true; msg = nil; Task { msg = await run(); busy = false; sure = false } }
}

/// Your name and @handle: on the first visit's card, and in the sheet behind the pencil.
private struct ProfileForm: View {
    @ObservedObject var m: FriendsModel
    @EnvironmentObject private var store: BetStore
    @State var name: String
    @State var handle: String
    let fresh: Bool
    var onCard = false
    var saved: () -> Void = {}
    @State private var busy = false
    @State private var msg: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            TextField("Name", text: $name).textContentType(.name).kitField(onCard: onCard)
            TextField("@handle", text: $handle).textInputAutocapitalization(.never).autocorrectionDisabled().kitField(onCard: onCard)
                .onChange(of: handle) { _, h in if h != h.lowercased() { handle = h.lowercased() } }
            Button(busy ? "Saving…" : fresh ? "Save" : "Update") {
                busy = true; msg = nil
                Task {
                    msg = await m.saveProfile(store.api, name: name, handle: handle)
                    busy = false
                    if msg == nil { saved() }
                }
            }
            .buttonStyle(KitButton()).disabled(busy)
            if let msg { Text(msg).font(.footnote).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
        }
    }
}

/// The sheet behind the pencil: change your name or @handle.
private struct ProfileSheet: View {
    @ObservedObject var m: FriendsModel
    let name: String
    let handle: String
    @Environment(\.dismiss) private var dismiss
    @Environment(\.theme) private var theme

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Your profile").font(.title2.weight(.heavy))
            Text("The name friends see, and the @handle they find you by.").font(.footnote).foregroundStyle(.secondary)
            ProfileForm(m: m, name: name, handle: handle, fresh: false) { dismiss() }
            Spacer(minLength: 0)
        }
        .padding(20).padding(.top, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(theme.pageColor.ignoresSafeArea())
        .presentationDetents([.medium])
    }
}

/// Add a friend: their exact @handle or email (find_person: nobody can browse who uses BetLab).
private struct AddFriendSheet: View {
    @ObservedObject var m: FriendsModel
    @EnvironmentObject private var store: BetStore
    @Environment(\.theme) private var theme
    @State private var q = ""
    @State private var busy = false
    @State private var msg: String?
    @State private var sent = false
    @FocusState private var typing: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Add a friend").font(.title2.weight(.heavy))
            TextField("Their @handle or email", text: $q).textInputAutocapitalization(.never).autocorrectionDisabled()
                .keyboardType(.emailAddress).focused($typing).kitField()
            Button(busy ? "Sending…" : "Send request") {
                busy = true; msg = nil; sent = false
                Task {
                    let e = await m.request(store.api, q)
                    if e == nil { q = ""; sent = true }
                    msg = e ?? "Request sent. You'll see each other's bets once they accept."
                    busy = false
                }
            }
            .buttonStyle(KitButton()).disabled(busy || q.trimmingCharacters(in: .whitespaces).count < 3)
            if let msg {
                Text(msg).font(.footnote).foregroundStyle(sent ? Color.secondary : .red).fixedSize(horizontal: false, vertical: true)
            }
            Text("Exact matches only: nobody can browse who uses BetLab. They accept before either of you sees the other's bets.")
                .font(.footnote).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(20).padding(.top, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(theme.pageColor.ignoresSafeArea())
        .presentationDetents([.medium])
        .onAppear { typing = true }
    }
}

/// Tail (W16): copy a friend's open bet into your bets, at the odds you got (theirs to start) and your book. The main
/// button of a friend's open bet.
struct TailButton: View {
    let b: MyBet
    @State var done: Bool
    @EnvironmentObject private var store: BetStore
    @State private var open = false
    @State private var odds = ""
    @State private var book = "FanDuel"
    @State private var busy = false
    @State private var msg: String?

    init(b: MyBet, done: Bool) { self.b = b; _done = State(initialValue: done) }

    var body: some View {
        if done {
            Label("Tailed: it's in your bets", systemImage: "checkmark.circle.fill").font(.footnote.weight(.semibold)).foregroundStyle(.green)
                .frame(maxWidth: .infinity, minHeight: 46, alignment: .leading)
        } else if !open {
            Button("Tail") {
                odds = b.price.map { Fmt.am($0) } ?? ""
                book = BooksOff.mine.contains(BetMath.book(b)) ? BetMath.book(b) : BooksOff.mine[0]     // your books (Nov 6)
                open = true
            }
            .buttonStyle(KitButton())
        } else {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    TextField("Your odds", text: $odds).keyboardType(.numbersAndPunctuation)
                        .font(.body.monospacedDigit().weight(.semibold)).kitField(onCard: true)
                    Picker("Book", selection: $book) { ForEach(BooksOff.mine, id: \.self) { Text($0) } }.labelsHidden()
                        .frame(minHeight: 46).padding(.horizontal, 4)
                        .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: Kit.inner, style: .continuous))
                }
                HStack(spacing: 10) {
                    Button(busy ? "Adding…" : "Add to my bets") { Task { await tail() } }.buttonStyle(KitButton()).disabled(busy)
                    Button("Cancel") { open = false }.buttonStyle(KitButton(kind: .quiet, wide: false))
                }
                if let msg { Text(msg).font(.caption).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
            }
        }
    }

    private func tail() async {
        guard Social.canTail(b) else { msg = "Too late: its game has started or it's settled."; return }
        guard let price = Marking.parseOdds(odds) else { msg = "Enter the odds you got, like +450 or -110."; return }
        busy = true; msg = nil
        do {
            try await store.api.insert("bets", Social.tailRow(b, price: price, book: book, real: store.isReal))
            await store.load()
            done = true
        } catch {
            let m = (error as? AuthError)?.message ?? ""
            msg = m.range(of: "duplicate key", options: .caseInsensitive) != nil ? "Already in your bets." : m.isEmpty ? "Couldn't add that." : m
        }
        busy = false
    }
}
