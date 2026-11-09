import SwiftUI

/// BetLab Wrapped (web app/wrapped and components/me/WrappedStory.tsx, Oct 27): a month or the season as a story. Tap the
/// right side for the next slide, the left to go back, hold to pause; slides advance every 8 seconds and stop on the
/// last, which has the Share picture (drawn here as web app/api/wrapped draws it). Slides with nothing to say are left
/// out. The logic is Wrapped.swift.
struct WrappedView: View {
    let bets: [MyBet]
    @State private var period: String?

    var body: some View {
        let list = Wrapped.periods(bets)
        let p = period.flatMap { list.contains($0) ? $0 : nil } ?? list.first
        VStack(spacing: 10) {
            if list.count > 1 {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(list, id: \.self) { x in
                            Button(Wrapped.periodName(x)) { period = x }
                                .font(.subheadline.weight(x == p ? .semibold : .regular))
                                .padding(.horizontal, 12).padding(.vertical, 6)
                                .background(x == p ? Color.accentColor.opacity(0.2) : Color.secondary.opacity(0.12), in: Capsule())
                                .foregroundStyle(x == p ? Color.accentColor : .primary)
                        }
                    }
                    .padding(.horizontal)
                }
            }
            if let p, let w = Wrapped.story(bets, p) {
                WrappedStory(w: w).id(p).padding(.horizontal)
            } else {
                ContentUnavailableView("Nothing to wrap yet", systemImage: "gift", description: Text("Your recap starts with your first graded bet."))
            }
        }
        .padding(.bottom, 8)
        .navigationTitle("Wrapped")
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct WrappedStory: View {
    let w: Wrapped.Story
    static let seconds = 8.0
    @State private var i = 0
    @State private var held = false
    @State private var photo: String?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private struct Slide { let key: String; let tone: Color; let body: AnyView }

    var body: some View {
        let list = slides()
        let last = list.count - 1
        let s = list[min(i, last)]
        VStack(spacing: 0) {
            HStack(spacing: 4) {
                ForEach(0..<list.count, id: \.self) { k in
                    Capsule().fill(Color.white.opacity(k <= i ? 0.9 : 0.25)).frame(height: 3)
                }
            }
            .padding(.bottom, 18)
            ScrollView { VStack(alignment: .leading, spacing: 12) { s.body }.frame(maxWidth: .infinity, alignment: .leading) }
                .scrollBounceBehavior(.basedOnSize)
                .id(s.key)
                .transition(.opacity)
            HStack {
                Button("‹ Back") { go(-1, last) }.disabled(i == 0)
                Spacer()
                Text("\(i + 1) / \(list.count)").foregroundStyle(.white.opacity(0.6))
                Spacer()
                Button("Next ›") { go(1, last) }.disabled(i == last)
            }
            .font(.subheadline).tint(.white).padding(.top, 10)
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .foregroundStyle(.white)
        // a dark card with the slide's color glowing from a corner, so green and red numbers stay readable
        .background(RadialGradient(colors: [s.tone.opacity(0.4), .clear], center: .topTrailing, startRadius: 0, endRadius: 520),
                    in: RoundedRectangle(cornerRadius: 22))
        .background(Color(white: 0.07), in: RoundedRectangle(cornerRadius: 22))
        .contentShape(Rectangle())
        .gesture(SpatialTapGesture().onEnded { e in go(e.location.x < 110 ? -1 : 1, last) })
        .onLongPressGesture(minimumDuration: 0.4, perform: {}, onPressingChanged: { held = $0 })
        .animation(.easeInOut(duration: 0.25), value: i)
        .task(id: "\(i)-\(held)") {          // advance on its own, not past the last slide, not while held, never with reduced motion
            guard !held, i < last, !reduceMotion else { return }
            try? await Task.sleep(for: .seconds(Self.seconds))
            if !Task.isCancelled { go(1, last) }
        }
        .task {
            guard let p = w.player else { return }
            photo = await Players.headshot(p.name, sport: p.sport).url
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Wrapped, slide \(i + 1) of \(list.count)")
    }

    private func go(_ d: Int, _ last: Int) { i = max(0, min(last, i + d)) }

    private static let pos = Color(red: 0.18, green: 0.82, blue: 0.53), neg = Color(red: 1, green: 0.42, blue: 0.42)
    private static let accent = Color(red: 0.56, green: 0.64, blue: 1)
    private func tone(_ x: Double) -> Color { x > 0 ? Self.pos : x < 0 ? Self.neg : .white }
    private func kicker(_ s: String) -> some View { Text(s.uppercased()).font(.caption.weight(.semibold)).tracking(1).foregroundStyle(.white.opacity(0.7)) }
    private func huge(_ s: String, _ c: Color = .white) -> some View { Text(s).font(.system(size: 52, weight: .bold)).foregroundStyle(c).minimumScaleFactor(0.5).lineLimit(2) }
    private func big(_ s: String, _ c: Color = .white) -> some View { Text(s).font(.system(size: 36, weight: .bold)).foregroundStyle(c).minimumScaleFactor(0.5).lineLimit(2) }
    private func sub(_ s: String) -> some View { Text(s).font(.subheadline).foregroundStyle(.white.opacity(0.7)) }
    private func day(_ d: String) -> String { Fmt.longDay(Models.date(d + "T16:00:00Z") ?? Date()) }
    private func record(_ t: RecordLine) -> String { "\(t.won)-\(t.lost)\(t.push > 0 ? "-\(t.push)" : "")" }

    private func betBox(_ b: Wrapped.Shown, mark: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack { Text(b.title).bold(); Spacer(); Text(b.price) }
            ForEach(Array(b.legs.enumerated()), id: \.offset) { _, l in
                HStack(spacing: 8) {
                    Circle().fill(l.result == "won" ? Self.pos : l.result == "lost" ? Self.neg : Color.gray).frame(width: 8, height: 8)
                    Text(l.label).fontWeight(l.label == mark ? .bold : .regular).foregroundStyle(l.label == mark ? Self.neg : .white)
                    if let v = l.value { Text("· \(v)").foregroundStyle(.white.opacity(0.6)) }
                }
                .font(.subheadline)
            }
            if b.more > 0 { sub("+\(b.more) more legs") }
            Text("\(b.book) · \(day(b.day))").font(.caption).foregroundStyle(.white.opacity(0.6))
        }
        .padding(12)
        .background(Color.black.opacity(0.3), in: RoundedRectangle(cornerRadius: 14))
    }

    private func slides() -> [Slide] {
        let t = w.total, season = w.period == "season"
        var out: [Slide] = []
        func add(_ key: String, _ tone: Color, @ViewBuilder _ v: () -> some View) { out.append(Slide(key: key, tone: tone, body: AnyView(v()))) }
        add("intro", Self.accent) {
            kicker("BetLab Wrapped")
            huge(season ? "Your season" : "Your \(w.name)")
            Text("**\(t.bets)** bets settled over **\(w.days)** day\(w.days == 1 ? "" : "s"), **\(w.legs)** leg\(w.legs == 1 ? "" : "s")")
                + (w.sports > 1 ? Text(", ") + Text("\(w.sports)").bold() + Text(" sports.") : Text("."))
            sub("Tap to go on")
        }
        add("bottom", t.units >= 0 ? Self.pos : Self.neg) {
            kicker("The bottom line")
            huge(BetMath.signedUnits(t.units), tone(t.units))
            Text(record(t) + (w.roi.map { " · ROI \(Fmt.signed($0))" } ?? ""))
            sub(t.units > 0 ? "Up is up. Plenty of people can't say that." : t.units < 0 ? "Not this time. Every good run starts somewhere." : "Dead even.")
        }
        if let b = w.best {
            add("best", Self.pos) { kicker("Your biggest hit"); big(BetMath.signedUnits(b.units), Self.pos); betBox(b) }
        }
        if let h = w.heartbreak {
            add("heart", Self.neg) {
                kicker("The leg that broke your heart")
                big("\(h.hit) of \(h.hit + 1)")
                Text("One leg from \(h.bet.price): **\(h.leg.label)**\(h.leg.value.map { " (\($0))" } ?? "").")
                betBox(h.bet, mark: h.leg.label)
            }
        }
        if let p = w.player {
            add("player", Self.accent) {
                kicker("Your player")
                if let u = photo.flatMap(URL.init) {
                    AsyncImage(url: u) { $0.resizable().scaledToFit() } placeholder: { Color.clear }.frame(height: 130)
                }
                big(p.name)
                Text("**\(p.legs.count)** legs\(p.topStat.map { ", mostly \($0)" } ?? "").")
                    + (p.won + p.lost > 0 ? Text(" ") + Text("\(p.won) of \(p.won + p.lost)").bold() + Text(" graded legs hit.") : Text(""))
                if p.units != 0 {
                    (Text("Your bets with a \(p.name.split(separator: " ").last.map(String.init) ?? p.name) leg: ") + Text(BetMath.signedUnits(p.units)).bold().foregroundColor(tone(p.units)))
                        .font(.subheadline)
                }
            }
        }
        if let bk = w.book, w.books.count > 1 {
            add("book", Self.accent) {
                kicker("Your best book")
                big(bk.group)
                ForEach(w.books) { l in
                    HStack { Text(l.group); Spacer(); Text("\(l.won)-\(l.lost)").foregroundStyle(.white.opacity(0.6)); Text(BetMath.signedUnits(l.units)).bold().foregroundStyle(tone(l.units)) }
                }
                sub("Shopping more than one book is the easiest edge there is.")
            }
        }
        add("type", Self.accent) { kicker("Your betting type"); big(w.persona.name); Text(w.persona.why) }
        if w.bestDay != nil || w.bestRun > 1 {
            add("days", Self.pos) {
                kicker("Your best moments")
                if let d = w.bestDay {
                    big(BetMath.signedUnits(d.units), Self.pos)
                    Text("on \(day(d.day)), from \(d.bets) bet\(d.bets == 1 ? "" : "s").")
                }
                if w.bestRun > 1 { Text("Longest win streak: **\(w.bestRun) in a row**.") }
                if let b = w.busiest, b.day != w.bestDay?.day { sub("Busiest day: \(day(b.day)), \(b.bets) bets.") }
            }
        }
        if !w.badges.isEmpty {
            add("badges", Self.accent) {
                kicker("Badges you earned")
                big("\(w.badges.count)")
                ForEach(w.badges) { b in
                    HStack(alignment: .top, spacing: 10) {
                        Text(b.icon).font(.title3)
                        VStack(alignment: .leading) { Text(b.title).bold(); Text(b.how).font(.caption).foregroundStyle(.white.opacity(0.7)) }
                    }
                }
            }
        }
        add("end", Color(white: 0.5)) {
            kicker("\(season ? "Your season" : w.name), wrapped")
            Group {
                row("P/L", BetMath.signedUnits(t.units), tone(t.units))
                row("Record", record(t))
                if let b = w.best { row("Biggest hit", b.price) }
                if let p = w.player { row("Your player", p.name) }
                row("Your type", w.persona.name)
            }
            ShareLink(item: WrappedImage(w: w), preview: SharePreview("My \(w.name) Wrapped", image: Image(systemName: "gift"))) {
                Label("Share", systemImage: "square.and.arrow.up").padding(.horizontal, 16).padding(.vertical, 8)
                    .background(Color.white.opacity(0.15), in: Capsule())
            }
            .padding(.top, 8)
        }
        return out
    }

    private func row(_ k: String, _ v: String, _ c: Color = .white) -> some View {
        HStack { Text(k).foregroundStyle(.white.opacity(0.7)); Spacer(); Text(v).bold().foregroundStyle(c) }.padding(.vertical, 4)
    }
}

/// Wrapped as a 1080x1350 picture (web app/api/wrapped): the period's P/L, record, biggest hit, player and type.
struct WrappedCardView: View {
    let w: Wrapped.Story

    private static func hex(_ v: Int) -> Color { Color(red: Double((v >> 16) & 0xff) / 255, green: Double((v >> 8) & 0xff) / 255, blue: Double(v & 0xff) / 255) }
    private static let pos = hex(0x2fd286), neg = hex(0xff6b6b), ink = hex(0xe9ecf1), ink2 = hex(0xa2abb8), accent = hex(0x8ea2ff)
    private static func u(_ x: Double) -> String { "\(x >= 0 ? "+" : Fmt.minus)\(String(format: "%.2f", abs(x)))u" }

    var body: some View {
        let t = w.total, tone = t.units >= 0 ? Self.pos : Self.neg
        var rows: [(String, String, Color?)] = [("Record", "\(t.won)-\(t.lost)\(t.push > 0 ? "-\(t.push)" : "")", nil)]
        if let r = w.roi { rows.append(("ROI", "\(r >= 0 ? "+" : Fmt.minus)\(String(format: "%.1f", abs(r * 100)))%", r >= 0 ? Self.pos : Self.neg)) }
        if let b = w.best { rows.append(("Biggest hit", "\(b.price.components(separatedBy: " ")[0]) · \(Self.u(b.units))", Self.pos)) }
        if let h = w.heartbreak { rows.append(("Heartbreaker", "\(h.hit) of \(h.hit + 1) at \(h.bet.price.components(separatedBy: " ")[0])", nil)) }
        if let p = w.player { rows.append(("Your player", p.name, nil)) }
        if let b = w.book, w.books.count > 1 { rows.append(("Best book", b.group, nil)) }
        if w.bestRun > 1 { rows.append(("Longest streak", "\(w.bestRun) wins", nil)) }
        return VStack(alignment: .leading, spacing: 0) {
            HStack {
                (Text("Bet").foregroundColor(Self.ink) + Text("Lab").foregroundColor(Self.accent) + Text("  Wrapped"))
                Spacer()
                Text("\(t.bets) bets · \(w.days) days")
            }
            .font(.system(size: 34)).foregroundStyle(Self.ink2)
            Text(w.period == "season" ? "My season" : "My \(w.name)").font(.system(size: 64)).foregroundStyle(Self.ink2).padding(.top, 64)
            Text(Self.u(t.units)).font(.system(size: 168)).tracking(-4).foregroundStyle(tone).lineLimit(1).minimumScaleFactor(0.5).padding(.top, 8)
            VStack(spacing: 0) {
                ForEach(Array(rows.enumerated()), id: \.offset) { i, r in
                    if i > 0 { Rectangle().fill(Self.hex(0x262c35)).frame(height: 1) }
                    HStack { Text(r.0).foregroundStyle(Self.ink2); Spacer(); Text(r.1).foregroundStyle(r.2 ?? Self.ink).lineLimit(1) }
                        .font(.system(size: 38)).padding(.vertical, 18)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 36).padding(.vertical, 16)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Self.hex(0x161a20), in: RoundedRectangle(cornerRadius: 28))
            .overlay(RoundedRectangle(cornerRadius: 28).strokeBorder(Self.hex(0x262c35), lineWidth: 2))
            .padding(.top, 48)
            Text("My betting type").font(.system(size: 28)).foregroundStyle(Self.ink2).padding(.top, 40)
            Text(w.persona.name).font(.system(size: 64)).tracking(-1).foregroundStyle(Self.accent).lineLimit(1).minimumScaleFactor(0.6)
        }
        .padding(.top, 72).padding(.horizontal, 72).padding(.bottom, 64)
        .frame(width: 1080, height: 1350, alignment: .topLeading)
        .background(RadialGradient(colors: [tone.opacity(0.2), .clear], center: UnitPoint(x: 0.85, y: 0), startRadius: 0, endRadius: 700))
        .background(Self.hex(0x0d0f13))
        .environment(\.colorScheme, .dark)
    }

    /// The PNG, drawn at 1080x1350.
    @MainActor static func png(_ w: Wrapped.Story) -> Data? {
        let r = ImageRenderer(content: WrappedCardView(w: w))
        r.scale = 1
        return r.uiImage?.pngData()
    }
}

/// The picture handed to the share sheet, drawn only when it's shared.
struct WrappedImage: Transferable {
    let w: Wrapped.Story
    static var transferRepresentation: some TransferRepresentation {
        DataRepresentation(exportedContentType: .png) { item in await MainActor.run { WrappedCardView.png(item.w) } ?? Data() }
            .suggestedFileName("BetLab Wrapped.png")
    }
}
