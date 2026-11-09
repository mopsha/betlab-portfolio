// Friends (Mike, Oct 27): a feed of your friends' bets, their profiles, and Tail (W16) to copy one into your own bets.
// Friends come from accepted requests (supabase 0024: profiles, friendships, friend_bets); friends see bets, never
// money (units only). Pure, so the tests run it; lib/data.ts loads, lib/actions.ts writes.
import { isSettled, recordBets, startOf } from "./bets";
import type { MyBet } from "./data";
import { bookOf } from "./books";

export type Profile = { user_id: string; name: string; handle: string };
export type Friendship = { requester: string; addressee: string; status: "pending" | "accepted"; created_at: string; accepted_at: string | null };

/** "@Mike_B " -> "mike_b"; null unless 3-20 letters, digits or underscores. */
export function cleanHandle(s: string): string | null {
  const h = s.trim().replace(/^@/, "").toLowerCase();
  return /^[a-z0-9_]{3,20}$/.test(h) ? h : null;
}

/** A starting handle from a name or an email: "Sam" -> "sam", "owner@example.com" -> "owner". */
export function suggestHandle(from: string): string {
  const h = from.split("@")[0].toLowerCase().replace(/[^a-z0-9_]/g, "").slice(0, 20);
  return h.length >= 3 ? h : `${h}_bets`.slice(0, 20);
}

/** Who's who for the signed-in user: friends, requests to answer, requests waiting on someone else. */
export function circle(me: string, list: Friendship[], profiles: Profile[]) {
  const who = (id: string) => profiles.find((p) => p.user_id === id) ?? null;
  const other = (f: Friendship) => (f.requester === me ? f.addressee : f.requester);
  const pick = (f: (x: Friendship) => boolean) => list.filter(f).map((x) => ({ ...x, other: who(other(x)), otherId: other(x) }));
  return {
    friends: pick((f) => f.status === "accepted").filter((x) => x.other).map((x) => x.other!).sort((a, b) => a.name.localeCompare(b.name)),
    incoming: pick((f) => f.status === "pending" && f.addressee === me),
    outgoing: pick((f) => f.status === "pending" && f.requester === me),
  };
}

/** How long a bet with no known game stays tailable after it was entered. */
export const NO_GAME_HOURS = 6;

/** A friend's bet you can still copy: not settled, and its game (the first, for a parlay) hasn't started; with no game
 *  known, for NO_GAME_HOURS after it was entered. */
export function canTail(b: MyBet, now = new Date()): boolean {
  if (isSettled(b) || b.live_settled) return false;
  const start = startOf(b);
  return start ? Date.parse(start) > now.getTime() : now.getTime() - Date.parse(b.placed_at) < NO_GAME_HOURS * 3600_000;
}

/** The key that makes a bet the same bet in two accounts: the pick, or the parlay. */
export const betKey = (b: Pick<MyBet, "pick_id" | "sgp_id">) => (b.pick_id ? `p:${b.pick_id}` : `s:${b.sgp_id}`);

/** The row a tail inserts into your bets: the same pick or parlay (so it grades the same way), at the price you got
 *  and your book, 1u once your real money has started (paper before, like marking). Never the friend's bonus, boost,
 *  Bet Protect+, bet reset, cash-out or ladder: those were their slip's, not the bet. */
export function tailRow(b: MyBet, o: { price: number; book: string; real: boolean }) {
  return {
    kind: b.kind, pick_id: b.pick_id ?? null, sgp_id: b.pick_id ? null : b.sgp_id,
    mode: o.real ? ("real" as const) : ("paper" as const), stake: o.real ? 1 : null,
    price: o.price, book: bookOf(o.book), label: b.label, matchup: b.matchup, fair_price: b.fair_price, p_fair: b.p_fair,
    legs: b.legs, games: b.games ?? null, odds_event_id: b.odds_event_id,
  };
}

/** The feed: friends' bets, newest first (placed, or settled for a graded one), each with who placed it. */
export function feed(bets: MyBet[], profiles: Profile[], limit = 60): { bet: MyBet; who: Profile }[] {
  const who = new Map(profiles.map((p) => [p.user_id, p]));
  return bets.filter((b) => who.has(String(b.user_id)))
    .sort((a, b) => b.placed_at.localeCompare(a.placed_at))
    .slice(0, limit)
    .map((bet) => ({ bet, who: who.get(String(bet.user_id))! }));
}

/** How many settled bets a friend's profile shows under Recent. */
export const PROFILE_RECENT = 15;

/** A friend's profile: the bets their record counts (real once they have any, as their My bets), the open ones by start
 *  and the PROFILE_RECENT most recent settled ones by when they were placed. The page draws these and /api/live tracks
 *  exactly these (Nov 9: the tracker took its own 40 by start, so some cards had none). */
export function profileBets(bets: MyBet[]): { counted: MyBet[]; open: MyBet[]; recent: MyBet[] } {
  const { counted } = recordBets(bets, false);
  const open = counted.filter((b) => !isSettled(b)).sort((a, b) => String(startOf(a) ?? a.placed_at).localeCompare(String(startOf(b) ?? b.placed_at)));
  const recent = counted.filter(isSettled).sort((a, b) => b.placed_at.localeCompare(a.placed_at)).slice(0, PROFILE_RECENT);
  return { counted, open, recent };
}

/** A steady color for a person's initial, from their handle. */
export function hue(handle: string): number {
  let h = 0;
  for (const c of handle) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

/** Reactions (Nov 6, supabase 0042): one per friend per bet, drawn as its emoji. The order is the picker's. */
export const REACTIONS = [
  { key: "fire", emoji: "🔥", say: "Fire" }, { key: "money", emoji: "💰", say: "Money" }, { key: "sweat", emoji: "😬", say: "Sweating" },
  { key: "skull", emoji: "💀", say: "Dead" }, { key: "pray", emoji: "🙏", say: "Praying" }, { key: "goat", emoji: "🐐", say: "GOAT" },
] as const;
export type ReactionKey = (typeof REACTIONS)[number]["key"];
export type Reaction = { bet_id: string; user_id: string; name: string | null; reaction: string; created_at: string };
export const emojiOf = (k: string) => REACTIONS.find((r) => r.key === k)?.emoji ?? "";

/** One bet's reactions as chips: each kind with its count and who, yours marked; most first, then the first reacted.
 *  You are "You"; a name the database didn't give (a friend's friend) is "Someone". */
export function tally(list: Reaction[], me: string) {
  const out: { reaction: string; emoji: string; count: number; mine: boolean; names: string[] }[] = [];
  for (const r of list) {
    if (!emojiOf(r.reaction)) continue;
    let c = out.find((x) => x.reaction === r.reaction);
    if (!c) out.push(c = { reaction: r.reaction, emoji: emojiOf(r.reaction), count: 0, mine: false, names: [] });
    c.count++;
    if (r.user_id === me) { c.mine = true; c.names.unshift("You"); } else c.names.push(r.name ?? "Someone");
  }
  return out.sort((a, b) => b.count - a.count);       // a stable sort keeps the first reacted first among equals
}

/** What a tap does: the reaction you have again takes it back (null); another replaces it. */
export const nextReaction = (current: string | null, tapped: string): string | null => (current === tapped ? null : tapped);

/** Who reacted, for a chip's label: "You", "Sam and Cal", "You, Sam and 2 more". */
export function whoText(names: string[]): string {
  if (names.length <= 2) return names.join(" and ");
  return `${names[0]}, ${names[1]} and ${names.length - 2} more`;
}
