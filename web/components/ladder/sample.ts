// Invented ladders for the local fixture preview only (lib/mode.ts fixtureMode: never on in a production build): one
// mid-climb with its next step locked, one that busted. The fixture file can't carry ladders (lib/data.ts keeps them in
// memory), so the Ladder page adds these there, to see the screen. Not real bets.
import type { MyBet } from "@/lib/data";
import type { Ladder } from "@/lib/ladder";

const ago = (now: number, h: number) => new Date(now - h * 3600_000).toISOString();
const step = (now: number, ladder: string, n: number, hours: number, label: string, matchup: string, league: string, price: number, stake: number, status: string): MyBet => ({
  bet_id: `sample-${ladder}-${n}`, kind: "pick", pick_id: null, sgp_id: null, mode: "real", price, stake, label, matchup, book: "FanDuel",
  ladder_id: ladder, placed_at: ago(now, hours), pick_status: status, ticket_status: null, league, pick_commence_time: ago(now, hours - 2),
} as unknown as MyBet);

export function sampleLadder(now = Date.now(), next?: { offer_id: string; label: string; price: number; matchup: string | null; commence_time: string | null;
  ev: number | null; game_id: string | null; league: string; tier: string }): { ladders: Ladder[]; bets: MyBet[] } {
  const stack = Math.round(1 * 1.91 * 1.87 * 2.05 * 100) / 100;
  const live: Ladder = { ladder_id: "sample-live", start_units: 1, target_units: 50, status: "active", created_at: ago(now, 80), book: "FanDuel",
    locked: next ? { offer_id: next.offer_id, tier: next.tier, label: next.label, price: next.price, book: "FanDuel", matchup: next.matchup,
      commence_time: next.commence_time ?? ago(now, -3), ev: next.ev, game_id: next.game_id, league: next.league, stake: stack, step: 4 } : null,
    locked_at: next ? ago(now, 0.4) : null };
  const bust: Ladder = { ladder_id: "sample-bust", start_units: 1, target_units: 100, status: "active", created_at: ago(now, 300) };
  return { ladders: [live, bust], bets: [
    step(now, "sample-live", 1, 76, "New York Knicks -4.5", "Chicago Bulls @ New York Knicks", "nba", -110, 1, "won"),
    step(now, "sample-live", 2, 52, "Buffalo Bills ML", "Buffalo Bills @ New York Jets", "nfl", -115, 1.91, "won"),
    step(now, "sample-live", 3, 28, "Boston Bruins ML", "Boston Bruins @ Toronto Maple Leafs", "nhl", 105, 3.57, "won"),
    step(now, "sample-bust", 1, 296, "Denver Nuggets -3.5", "Denver Nuggets @ Utah Jazz", "nba", -108, 1, "won"),
    step(now, "sample-bust", 2, 272, "Dallas Cowboys +3", "Dallas Cowboys @ Philadelphia Eagles", "nfl", -110, 1.93, "lost"),
  ] };
}
