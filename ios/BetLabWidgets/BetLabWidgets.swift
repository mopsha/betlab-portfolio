import SwiftUI
import WidgetKit

// The widget extension (Mike's #3, Oct 27): the home-screen and lock-screen widgets (BetsWidget) and the Live Activity
// for a real bet in play (BetLiveActivity). Its data: ios/Shared (WidgetSnapshot from the app; the activity's state
// from the worker's pushes).
@main
struct BetLabWidgets: WidgetBundle {
    var body: some Widget {
        BetsWidget()
        BetLiveActivity()
    }
}

/// A leg's status as a color and symbol, as My bets' tracker draws it (LiveLegRow).
enum LegLook {
    static func tint(_ status: String) -> Color {
        switch status {
        case "won": .green
        case "lost": .red
        case "void": .secondary
        case "losing": .orange
        case "pending", "unknown": .gray
        default: .blue
        }
    }
    static func symbol(_ status: String) -> String {
        switch status {
        case "won": "checkmark.circle.fill"
        case "lost": "xmark.circle.fill"
        case "void": "minus.circle.fill"
        case "pending", "unknown": "circle"
        default: "circle.inset.filled"
        }
    }
}
