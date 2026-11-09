// Player cards (Mike's W21, Oct 24) and team cards (Oct 25): trading cards for the players and teams you bet on most,
// with your record on them, in rows you swipe through like the iPhone's; a tap opens every leg (components/games/Cards.tsx).
import { teams } from "@/lib/cards";
import { ticketBodies, type MyBet } from "@/lib/data";
import { look } from "@/lib/headshots";
import { groups } from "@/lib/live-bets";
import { players, type Player } from "@/lib/players";
import { CardShelf, type Face } from "@/components/games/Cards";

const SHOWN = 20;

async function faces(list: Player[], kind: "player" | "team"): Promise<Face[]> {
  const looks = await Promise.all(list.map((p) => look(kind, p.name, p.sport)));
  return list.map((p, i) => ({ ref: { kind, name: p.name }, card: p, look: looks[i] }));
}

/** `whose`: a friend's name on their profile ("Sam's players"); yours otherwise. */
export async function PlayerCards({ bets, whose }: { bets: MyBet[]; whose?: string }) {
  const tickets = await ticketBodies(bets.filter((b) => b.kind === "parlay" && b.sgp_id).map((b) => b.sgp_id!)).catch(() => ({}));
  const [ps, ts] = await Promise.all([faces(players(bets).slice(0, SHOWN), "player"),
                                      faces(teams(bets, (b) => groups(b, tickets)).slice(0, SHOWN), "team")]);
  const foot = "Gold: 70%+ of 3 or more graded legs hit; silver 50%+; bronze below. Tap a card for every leg.";
  return (
    <>
      <CardShelf title={whose ? `${whose}'s players` : "Your players"} faces={ps} foot={foot} />
      <CardShelf title={whose ? `${whose}'s teams` : "Your teams"} faces={ts} foot="A team's moneylines and spreads, and its games' totals and both-teams-to-score legs." />
    </>
  );
}
