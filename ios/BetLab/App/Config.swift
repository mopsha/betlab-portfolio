import Foundation

/// The Supabase address and public (anon) key, from Info.plist, which takes them from Secrets.xcconfig
/// (ios/scripts/make_secrets.sh). The anon key is public by design: row-level security guards the data.
enum Config {
    static let supabaseURL: URL? = {
        guard let s = Bundle.main.object(forInfoDictionaryKey: "SUPABASE_URL") as? String,
              s.hasPrefix("http"), let url = URL(string: s) else { return nil }
        return url
    }()
    /// The web app: Ask BetLab's /api/chat (the app signs in with its Supabase access token).
    static let webURL = URL(string: "https://betlab.example.app")!
    static let anonKey: String = (Bundle.main.object(forInfoDictionaryKey: "SUPABASE_ANON_KEY") as? String) ?? ""
    static var isConfigured: Bool { supabaseURL != nil && !anonKey.isEmpty && !anonKey.hasPrefix("$(") }
}
