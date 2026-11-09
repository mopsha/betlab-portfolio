import Foundation
import UIKit

// Team logos for the lock screen (Oct 27): a Live Activity can't download images, so the app saves each logo the
// worker names (BetActivityAttributes.Game.awayLogo/homeLogo, ESPN's) small into the App Group, and the widget reads
// it from there. A logo not saved yet shows as the team's initials.
enum LogoStore {
    static let group = "group.com.mopsha.betlab"

    /// Where a logo lives: logos/<its URL's path, flattened>.png in the App Group.
    static func file(_ url: String) -> URL? {
        guard let u = URL(string: url), !u.path.isEmpty,
              let dir = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group)?
                .appendingPathComponent("logos", isDirectory: true) else { return nil }
        let name = u.path.split(separator: "/").joined(separator: "-")
        return dir.appendingPathComponent(name.hasSuffix(".png") ? name : name + ".png")
    }

    static func image(_ url: String?) -> UIImage? {
        guard let url, let f = file(url) else { return nil }
        return UIImage(contentsOfFile: f.path)
    }

    /// Download the logos not saved yet, each scaled to 96 pt-ish pixels (the widget's memory is small).
    static func fetch(_ urls: [String?]) async {
        for url in Set(urls.compactMap { $0 }) {
            guard let f = file(url), !FileManager.default.fileExists(atPath: f.path), let u = URL(string: url),
                  let (data, _) = try? await URLSession.shared.data(from: u), let img = UIImage(data: data) else { continue }
            let side: CGFloat = 96
            let small = UIGraphicsImageRenderer(size: CGSize(width: side, height: side)).image { _ in
                let s = min(side / img.size.width, side / img.size.height)
                let w = img.size.width * s, h = img.size.height * s
                img.draw(in: CGRect(x: (side - w) / 2, y: (side - h) / 2, width: w, height: h))
            }
            try? FileManager.default.createDirectory(at: f.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? small.pngData()?.write(to: f, options: .atomic)
        }
    }
}
