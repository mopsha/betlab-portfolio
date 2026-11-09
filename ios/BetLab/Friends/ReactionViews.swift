import SwiftUI

/// Reactions (Nov 6, supabase 0042), iMessage-style like the web (components/friends/Reactions.tsx): a smiley beside Tail
/// opens the six in a floating bubble, and the card wears what friends picked as a stacked bubble on its bottom edge (a tap
/// says who). One per person; your pick again takes it back. Your own bets show the bubble only. The rules are
/// Social.tally / nextReaction, shared with the web through tests/fixtures/reactions.json.
struct Reacting {
    let list: [Reaction]
    let me: String
    /// nil: your own bet (the bubble only). Takes the new reaction (nil takes yours back); returns an error to show.
    var react: ((String?) async -> String?)? = nil

    var mine: String? { list.first { $0.userId == me }?.reaction }
}

/// The smiley in a friend's card (your own pick in its place once you've reacted); the six float above it.
struct ReactButton: View {
    let rx: Reacting
    @State private var open = false
    @State private var error: String?
    @Environment(\.theme) private var theme

    var body: some View {
        Button { open = true } label: {
            Group {
                if let m = rx.mine, let e = Social.emoji(m) {
                    Text(e).font(.system(size: 24))
                } else {
                    Image(systemName: "face.smiling").font(.system(size: 21, weight: .medium)).overlay(alignment: .topTrailing) {
                        Image(systemName: "plus").font(.system(size: 9, weight: .heavy)).offset(x: 5, y: -3)
                    }
                }
            }
            .frame(width: 46, height: 46)
            .background(rx.mine != nil ? theme.accent.opacity(0.22) : Color(.tertiarySystemFill), in: Circle())
            .overlay { if rx.mine != nil { Circle().strokeBorder(theme.accent.opacity(0.6), lineWidth: 1.5) } }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(rx.mine.flatMap { m in Social.reactions.first { $0.key == m }?.say }.map { "Your reaction: \($0). Change it" } ?? "React")
        .popover(isPresented: $open, attachmentAnchor: .point(.top), arrowEdge: .bottom) {
            HStack(spacing: 2) {
                ForEach(Array(Social.reactions.enumerated()), id: \.offset) { i, r in
                    PickEmoji(emoji: r.emoji, say: r.say, mine: r.key == rx.mine, delay: Double(i) * 0.025) {
                        open = false
                        Task { error = await rx.react?(Social.nextReaction(rx.mine, r.key)) }
                    }
                }
            }
            .padding(6)
            .presentationCompactAdaptation(.popover)
        }
        .sensoryFeedback(.impact(weight: .light), trigger: rx.mine)
        .overlay(alignment: .bottomTrailing) {
            if let error { Text(error).font(.caption2).foregroundStyle(.red).fixedSize().offset(y: 18) }
        }
    }
}

/// One of the six, springing up when the bubble opens.
private struct PickEmoji: View {
    let emoji: String, say: String, mine: Bool, delay: Double
    let tap: () -> Void
    @State private var shown = false
    @Environment(\.theme) private var theme

    var body: some View {
        Button(action: tap) {
            Text(emoji).font(.system(size: 30))
                .frame(width: 46, height: 46)
                .background(mine ? theme.accent.opacity(0.25) : .clear, in: Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(say)
        .accessibilityAddTraits(mine ? .isSelected : [])
        .scaleEffect(shown ? 1 : 0.4).opacity(shown ? 1 : 0)
        .onAppear { withAnimation(.spring(response: 0.3, dampingFraction: 0.55).delay(delay)) { shown = true } }
    }
}

/// What friends picked, stacked; hung on the card's bottom-left edge by `.reactionBubble`.
struct ReactionBubble: View {
    let rx: Reacting
    @State private var who = false
    @State private var pop = false

    var body: some View {
        let chips = Social.tally(rx.list, me: rx.me)
        if !chips.isEmpty {
            let total = chips.reduce(0) { $0 + $1.count }
            Button { who = true } label: {
                HStack(spacing: 6) {
                    HStack(spacing: -7) {
                        ForEach(chips.prefix(3), id: \.reaction) { c in
                            Text(c.emoji).font(.system(size: 15))
                                .frame(width: 26, height: 26)
                                .background(Color(.tertiarySystemBackground), in: Circle())
                                .overlay { Circle().strokeBorder(Color(.secondarySystemBackground), lineWidth: 2) }
                        }
                    }
                    if total > 1 { Text("\(total)").font(.system(size: 13, weight: .bold, design: .monospaced)) }
                }
                .padding(.leading, 3).padding(.trailing, total > 1 ? 10 : 3)
                .frame(height: 32)
                .background(Color(.secondarySystemBackground), in: Capsule())
                .overlay { Capsule().strokeBorder(Color(.systemBackground), lineWidth: 3) }
                .shadow(color: .black.opacity(0.25), radius: 6, y: 3)
            }
            .buttonStyle(.plain)
            .scaleEffect(pop ? 1.15 : 1)
            .onChange(of: rx.mine) { _, new in
                guard new != nil else { return }
                withAnimation(.spring(response: 0.2, dampingFraction: 0.4)) { pop = true }
                withAnimation(.spring(response: 0.3, dampingFraction: 0.7).delay(0.18)) { pop = false }
            }
            .accessibilityLabel("Reactions: " + chips.map { "\($0.emoji) \(Social.whoText($0.names))" }.joined(separator: ", "))
            .popover(isPresented: $who, attachmentAnchor: .point(.top), arrowEdge: .bottom) {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(chips, id: \.reaction) { c in
                        HStack(spacing: 8) { Text(c.emoji); Text(Social.whoText(c.names)).font(.subheadline) }
                    }
                }
                .padding(12)
                .presentationCompactAdaptation(.popover)
            }
        }
    }
}

extension View {
    /// Hangs a bet's reactions on its card's bottom-left edge, with room below for them.
    @ViewBuilder func reactionBubble(_ rx: Reacting?) -> some View {
        if let rx, !Social.tally(rx.list, me: rx.me).isEmpty {
            self.overlay(alignment: .bottomLeading) { ReactionBubble(rx: rx).offset(x: 20, y: 15) }.padding(.bottom, 14)
        } else {
            self
        }
    }
}

/// The reactions a screen shows (Friends, a friend's profile): read through bet_reactions_for, written as you (row-level
/// security lets only a friend's shared bet take one). A tap shows at once and goes back if the write fails.
@MainActor
final class ReactionStore: ObservableObject {
    @Published private(set) var list: [Reaction] = []

    static func read(_ api: SupabaseClient, _ ids: [String]) async -> [Reaction] {
        ids.isEmpty ? [] : ((try? await api.rpc("bet_reactions_for", ["bets": ids]) as [Reaction]) ?? [])
    }

    func load(_ api: SupabaseClient, _ ids: [String]) async { list = await Self.read(api, ids) }

    /// A friend's bet, for its card.
    func on(_ betId: String, me: String, api: SupabaseClient) -> Reacting {
        Reacting(list: list.filter { $0.betId == betId }, me: me) { [weak self] next in
            await self?.react(api, me: me, betId: betId, next)
        }
    }

    private func react(_ api: SupabaseClient, me: String, betId: String, _ next: String?) async -> String? {
        let before = list
        list.removeAll { $0.betId == betId && $0.userId == me }
        if let next { list.append(Reaction(betId: betId, userId: me, name: "You", reaction: next)) }
        do {
            if let next {
                try await api.upsert("bet_reactions", ["bet_id": betId, "user_id": me, "reaction": next,
                                                       "created_at": ISO8601DateFormatter().string(from: Date())], onConflict: "bet_id,user_id")
            } else {
                try await api.delete("bet_reactions", eq: [("bet_id", betId), ("user_id", me)])
            }
            return nil
        } catch {
            list = before
            let m = (error as? AuthError)?.message ?? ""
            return m.range(of: "row-level security", options: .caseInsensitive) != nil ? "That bet isn't shared with you any more." : "Couldn't save that."
        }
    }
}
