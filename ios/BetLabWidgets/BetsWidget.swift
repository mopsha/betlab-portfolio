import SwiftUI
import WidgetKit

/// Today's and the week's units and your open bets, from what the app last saw (WidgetSnapshot). Home screen: small and
/// medium; lock screen: a line and a small block.
struct BetsWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "BetsWidget", provider: Provider()) { e in
            BetsWidgetView(entry: e).containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("My bets")
        .description("Today's units, the week, and your open bets.")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryRectangular, .accessoryInline])
    }

    struct Entry: TimelineEntry {
        let date: Date
        let snap: WidgetSnapshot?
    }

    struct Provider: TimelineProvider {
        func placeholder(in context: Context) -> Entry { Entry(date: Date(), snap: .sample) }
        func getSnapshot(in context: Context, completion: @escaping (Entry) -> Void) {
            completion(Entry(date: Date(), snap: context.isPreview ? (WidgetSnapshot.load() ?? .sample) : WidgetSnapshot.load()))
        }
        /// The app redraws the widget when your bets change; this only keeps "next up" times honest.
        func getTimeline(in context: Context, completion: @escaping (Timeline<Entry>) -> Void) {
            completion(Timeline(entries: [Entry(date: Date(), snap: WidgetSnapshot.load())], policy: .after(Date().addingTimeInterval(30 * 60))))
        }
    }
}

struct BetsWidgetView: View {
    let entry: BetsWidget.Entry
    @Environment(\.widgetFamily) private var family

    private func tint(_ u: Double) -> Color { u > 0.004 ? .green : u < -0.004 ? .red : .primary }

    var body: some View {
        if let s = entry.snap {
            switch family {
            case .accessoryInline:
                Text("\(unitsText(s.today)) today · \(s.openCount) open")
            case .accessoryRectangular:
                VStack(alignment: .leading, spacing: 1) {
                    Text("BetLab").font(.caption2.weight(.semibold))
                    Text("\(unitsText(s.today)) today").font(.system(size: 20, weight: .heavy).monospacedDigit())
                    Text(next(s)).font(.caption2).lineLimit(1)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            case .systemMedium:
                HStack(alignment: .top, spacing: 12) {
                    totals(s).frame(width: 110, alignment: .leading)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(s.openCount == 0 ? "No open bets" : "Open · \(s.openCount)").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        ForEach(Array(s.open.prefix(3).enumerated()), id: \.offset) { _, b in
                            VStack(alignment: .leading, spacing: 0) {
                                HStack {
                                    Text(b.title).font(.caption.weight(.medium)).lineLimit(1)
                                    Spacer(minLength: 4)
                                    Text(b.price).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                                }
                                if let t = b.start { Text(when(t)).font(.caption2).foregroundStyle(.secondary) }
                            }
                        }
                        Spacer(minLength: 0)
                    }
                }
            default:
                totals(s)
            }
        } else {
            VStack(alignment: .leading, spacing: 4) {
                Text("BetLab").font(.caption.weight(.semibold))
                Text("Open the app once to fill this in.").font(.caption2).foregroundStyle(.secondary)
            }
        }
    }

    private func totals(_ s: WidgetSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(s.real ? "TODAY" : "TODAY · PAPER").font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
            // the day's units lead, as Today's hero does (the overhaul: big numbers lead)
            Text(unitsText(s.today)).font(.system(size: 34, weight: .heavy).monospacedDigit()).kerning(-1).foregroundStyle(tint(s.today))
                .minimumScaleFactor(0.5).lineLimit(1)
            Text(s.settledToday == 1 ? "1 settled" : "\(s.settledToday) settled").font(.caption2).foregroundStyle(.secondary)
            Spacer(minLength: 2)
            Text("Week \(unitsText(s.week))").font(.caption.weight(.bold).monospacedDigit()).foregroundStyle(tint(s.week))
            Text("\(s.openCount) open").font(.caption2).foregroundStyle(.secondary)
        }
    }

    private func next(_ s: WidgetSnapshot) -> String {
        guard let b = s.open.first else { return "No open bets" }
        return "\(s.openCount) open" + (b.start.map { " · next \(when($0))" } ?? "")
    }

    private func when(_ d: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = Calendar.current.isDateInToday(d) ? "h:mm a" : "EEE h:mm a"
        return f.string(from: d)
    }
}
