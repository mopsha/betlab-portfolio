import CryptoKit
import Foundation
import Network
import SwiftUI

/// Every table read saved on this phone (Nov 4, idea #61), so a screen opens at once on what it last showed and still opens with no signal.
/// One file per query; a query's dates count by their day, or today's Home would be a new file on every read. Cleared on sign-out; files
/// not read for two weeks go.
enum ResponseCache {
    private static let keep: TimeInterval = 14 * 86400
    static var directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("rows")

    /// The file's name: the path and query, each date cut to its day.
    static func key(_ url: URL) -> String {
        let c = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let q = (c?.queryItems ?? []).map { i -> String in
            guard let v = i.value, let m = v.range(of: #"^(gte|lt|gt)\.\d{4}-\d{2}-\d{2}"#, options: .regularExpression) else { return "\(i.name)=\(i.value ?? "")" }
            return "\(i.name)=\(v[m])"
        }
        return SHA256.hash(data: Data("\(c?.path ?? "")?\(q.joined(separator: "&"))".utf8)).map { String(format: "%02x", $0) }.joined()
    }

    static func read(_ url: URL) -> Data? {
        try? Data(contentsOf: directory.appendingPathComponent(key(url)))
    }

    static func write(_ url: URL, _ data: Data) {
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try? data.write(to: directory.appendingPathComponent(key(url)), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }

    static func clear() { try? FileManager.default.removeItem(at: directory) }

    static func prune(now: Date = Date()) {
        let fm = FileManager.default
        for f in (try? fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.contentModificationDateKey])) ?? [] {
            let at = (try? f.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate
            if let at, now.timeIntervalSince(at) > keep { try? fm.removeItem(at: f) }
        }
    }
}

/// A line at the top when the phone has no connection, so saved numbers aren't taken for live ones.
struct OfflineBanner: View {
    @StateObject private var net = NetworkWatch()

    var body: some View {
        if !net.online {
            Label("Offline: showing what was last saved", systemImage: "wifi.slash")
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(.thinMaterial, in: Capsule())
                .accessibilityAddTraits(.isStaticText)
        }
    }
}

@MainActor private final class NetworkWatch: ObservableObject {
    @Published var online = true
    private let monitor = NWPathMonitor()

    init() {
        monitor.pathUpdateHandler = { [weak self] path in
            let up = path.status == .satisfied
            Task { @MainActor in self?.online = up }
        }
        monitor.start(queue: DispatchQueue(label: "betlab.network"))
        Task.detached(priority: .background) { ResponseCache.prune() }
    }

    deinit { monitor.cancel() }
}
