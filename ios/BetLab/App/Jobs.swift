import SwiftUI

// Refresh (Home) and Grade now (My bets): queue the worker's guarded `reprice` or `grade` job through
// `job_requests`, as the user (web/lib/jobs.ts, refresh.ts, refresh-actions.ts). The worker enforces its own
// cooldown, lock and allow-list too; the app only asks.

enum AppJob: String { case reprice, grade }

struct JobRequest: Decodable, Equatable {
    let id: Int
    let status: String          // queued, running, done, refused, failed
    let requestedAt: String
    let finishedAt: String?
}

struct JobState: Equatable {
    var mode = "unknown"        // active, shadow, unknown
    var request: JobRequest?

    static let cooldown: TimeInterval = 30 * 60

    var pending: Bool { request?.status == "queued" || request?.status == "running" }
    func wait(now: Date = Date()) -> TimeInterval {
        guard let at = request.flatMap({ Models.date($0.requestedAt) }) else { return 0 }
        return max(0, at.addingTimeInterval(Self.cooldown).timeIntervalSince(now))
    }
    var canAsk: Bool { mode == "active" && !pending && wait() == 0 }

    static func mode(fromStep step: String?) -> String {
        step == "started" ? "active" : step == "started (shadow)" ? "shadow" : "unknown"
    }

    func message(_ job: AppJob) -> String {
        if job == .grade && mode == "active" {
            switch request?.status {
            case "queued": return "Grading queued. You can keep browsing."
            case "running": return "Grading finished games…"
            case "done": return "Grading finished. Results are up to date."
            case "refused": return "Grading could not start. The worker may be busy or cooling down."
            case "failed": return "Grading failed. The morning run grades again."
            default: return "Grade finished games now instead of at the 9:55 AM run. Once every 30 minutes."
            }
        }
        if mode == "shadow" { return "On-demand refresh is not enabled yet. Scheduled updates continue." }
        if mode != "active" { return "Refresh is unavailable right now. Pull down to reload." }
        switch request?.status {
        case "queued": return "Refresh queued. You can keep browsing."
        case "running": return "Refreshing prices and picks…"
        case "done": return "Refresh finished. The priced time is under the title."
        case "refused": return "Refresh could not start. The worker may be busy or cooling down."
        case "failed": return "Refresh failed. Scheduled updates continue."
        default: return "Refresh prices and picks. Limited to once every 30 minutes."
        }
    }
}

enum Jobs {
    private struct Run: Decodable { let step: String? }

    static func state(_ api: SupabaseClient, _ job: AppJob) async -> JobState {
        do {
            async let w: [Run] = api.rows("runs", .init(eq: [("job", "worker")], select: "step", order: ("started_at", false), limit: 1))
            async let r: [JobRequest] = api.rows("job_requests", .init(eq: [("job", job.rawValue)], select: "id,status,requested_at,finished_at",
                                                                        order: ("requested_at", false), limit: 1))
            let (worker, req) = try await (w, r)
            return JobState(mode: JobState.mode(fromStep: worker.first?.step), request: req.first)
        } catch {
            return JobState()
        }
    }

    /// Queue the job unless one is pending or the 30-minute cooldown hasn't passed. Returns an error message or nil.
    static func request(_ api: SupabaseClient, _ job: AppJob) async -> String? {
        let s = await state(api, job)
        guard s.canAsk else { return nil }
        do {
            try await api.insert("job_requests", ["job": job.rawValue, "status": "queued"])
            return nil
        } catch {
            return job == .grade ? "Couldn't queue grading. Try again in a moment." : "Couldn't queue a refresh. Try again in a moment."
        }
    }
}

/// A small toolbar icon for Refresh / Grade now. Tapping opens a menu with the job's status and the action, so a
/// stray tap never queues anything (Refresh spends odds credits). Polls every 5 seconds while a request is
/// pending, spinning in place of the icon, then calls `onDone`.
struct JobButton: View {
    let job: AppJob
    let api: SupabaseClient
    var onDone: () async -> Void = {}
    @State private var state = JobState()
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        Menu {
            Section(error ?? status) {
                Button(job == .grade ? "Grade now" : "Refresh now",
                       systemImage: job == .grade ? "checkmark.seal" : "arrow.clockwise") {
                    busy = true
                    Task {
                        error = await Jobs.request(api, job)
                        state = await Jobs.state(api, job)
                        busy = false
                    }
                }
                .disabled(busy || !state.canAsk)
            }
        } label: {
            if busy || state.pending {
                ProgressView().controlSize(.small)
            } else {
                Image(systemName: job == .grade ? "checkmark.seal" : "arrow.clockwise")
            }
        }
        .accessibilityLabel(job == .grade ? "Grade now" : "Refresh")
        .task(id: state.pending) {
            if state.request == nil { state = await Jobs.state(api, job) }
            while state.pending {
                try? await Task.sleep(for: .seconds(5))
                if Task.isCancelled { return }
                let next = await Jobs.state(api, job)
                let finished = !next.pending && state.pending
                state = next
                if finished { await onDone() }
            }
        }
        .onAppear { Task { state = await Jobs.state(api, job) } }
    }

    private var status: String {
        let wait = state.wait()
        let base = state.message(job)
        return !state.pending && wait > 0 && state.mode == "active" ? "\(base) Next one in \(Int(wait / 60) + 1) min." : base
    }
}

extension View {
    /// The small line under a large title (iOS 26); older systems skip it.
    @ViewBuilder func subtitle(_ text: String?) -> some View {
        if #available(iOS 26.0, *), let text { self.navigationSubtitle(text) } else { self }
    }

    /// A row that sits on the page's background instead of in a card.
    func bareRow() -> some View {
        listRowBackground(Color.clear).listRowSeparator(.hidden).listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
    }
}
