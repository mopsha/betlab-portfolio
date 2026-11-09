import SwiftUI
import UniformTypeIdentifiers

/// A bet as a 1080x1350 picture to send (Mike's W13, Oct 24), drawn as web/app/api/share/[id] draws it: that route signs
/// in by the web's cookie, so the app renders the same card itself (ShareCard in Stats.swift is the content).
struct ShareCardView: View {
    let c: ShareCard

    private static func hex(_ v: Int) -> Color { Color(red: Double((v >> 16) & 0xff) / 255, green: Double((v >> 8) & 0xff) / 255, blue: Double(v & 0xff) / 255) }
    private static let tones: [String: Color] = ["win": hex(0x2fd286), "loss": hex(0xff6b6b), "even": hex(0xa2abb8), "open": hex(0x8ea2ff)]
    private static let dots: [String: Color] = ["won": hex(0x2fd286), "lost": hex(0xff6b6b), "void": hex(0x6f7886), "open": hex(0x3a424e)]
    private static let ink = hex(0xe9ecf1), faint = hex(0xa2abb8)

    var body: some View {
        let tone = Self.tones[c.tone] ?? Self.faint
        let legSize: CGFloat = c.legs.count > 7 ? 30 : 36
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                (Text("Bet").foregroundColor(Self.ink) + Text("Lab").foregroundColor(Self.hex(0x8ea2ff)))
                Spacer()
                Text("\(c.book) · \(c.when)")
            }
            .font(.system(size: 34)).foregroundStyle(Self.faint)
            Text(c.status).font(.system(size: c.status.count > 8 ? 88 : 120, weight: .regular)).tracking(-2).foregroundStyle(tone)
                .lineLimit(1).minimumScaleFactor(0.5).padding(.top, 56)
            HStack(alignment: .firstTextBaseline) {
                Text(c.title).font(.system(size: 44)).lineLimit(2)
                Spacer(minLength: 20)
                Text(c.price).font(.system(size: 48))
            }
            .foregroundStyle(Self.ink).padding(.top, 28)
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(c.legs.enumerated()), id: \.offset) { i, l in
                    if i > 0 { Rectangle().fill(Self.hex(0x262c35)).frame(height: 1) }
                    HStack(spacing: 22) {
                        Circle().fill(Self.dots[l.result] ?? Self.faint).frame(width: 26, height: 26)
                        Text(l.label).foregroundStyle(l.result == "lost" ? Self.hex(0xff9b9b) : Self.ink).lineLimit(1)
                        Spacer(minLength: 16)
                        if let v = l.value { Text(v).foregroundStyle(Self.faint) }
                    }
                    .font(.system(size: legSize)).padding(.vertical, 12)
                }
                if c.more > 0 { Text("+\(c.more) more legs").font(.system(size: 28)).foregroundStyle(Self.faint).padding(.top, 12) }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 32).padding(.vertical, 28)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(Self.hex(0x161a20), in: RoundedRectangle(cornerRadius: 28))
            .overlay(RoundedRectangle(cornerRadius: 28).strokeBorder(tone.opacity(0.25), lineWidth: 2))
            .padding(.top, 36)
            HStack(alignment: .firstTextBaseline) {
                Text(c.headline).font(.system(size: 76)).tracking(-1).foregroundStyle(tone)
                Spacer(minLength: 16)
                Text(c.detail).font(.system(size: 30)).foregroundStyle(Self.faint).lineLimit(1).minimumScaleFactor(0.6)
            }
            .padding(.top, 40)
        }
        .padding(.top, 72).padding(.horizontal, 72).padding(.bottom, 60)
        .frame(width: 1080, height: 1350, alignment: .topLeading)
        .background(Self.hex(0x0d0f13))
        .environment(\.colorScheme, .dark)
    }

    /// The PNG, drawn at 1080x1350.
    @MainActor static func png(_ c: ShareCard) -> Data? {
        let r = ImageRenderer(content: ShareCardView(c: c))
        r.scale = 1
        return r.uiImage?.pngData()
    }
}

/// The picture handed to the share sheet, drawn only when it's shared.
struct ShareCardImage: Transferable {
    let card: ShareCard
    static var transferRepresentation: some TransferRepresentation {
        DataRepresentation(exportedContentType: .png) { item in await MainActor.run { ShareCardView.png(item.card) } ?? Data() }
            .suggestedFileName("BetLab bet.png")
    }
}

/// "Share" on a bet card: the picture through the system share sheet.
struct ShareBetButton: View {
    let b: MyBet
    var body: some View {
        let c = ShareCard.of(b)
        ShareLink(item: ShareCardImage(card: c), preview: SharePreview("\(c.status): \(c.title)", image: Image(systemName: "photo"))) {
            Label("Share", systemImage: "square.and.arrow.up")
        }
    }
}
