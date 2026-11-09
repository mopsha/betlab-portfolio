import type { GameRefs } from "@/components/chat/Answer";
import { Chat, type Idea, type Turn } from "@/components/me/Chat";
import { gameArt } from "@/lib/art";
import { chatReady } from "@/lib/chat";
import { allGames } from "@/lib/data";
import { dayTime } from "@/lib/format";
import { fixtureMode } from "@/lib/mode";

export const dynamic = "force-dynamic";

const AHEAD_MS = 36 * 3600_000, MOST = 60;   // the games an answer is likely to link: the next day and a half
const soon = <T,>(p: Promise<T>, fallback: T, ms = 3000) => Promise.race([p.catch(() => fallback), new Promise<T>((r) => setTimeout(() => r(fallback), ms))]);

/** The coming games' pictures, keyed by their page's path, so a game link in an answer is drawn as a card with both
 *  logos; and the next game as a question to start from. The chat works without any of it. */
async function comingGames(): Promise<{ games: GameRefs; game: Idea | null }> {
  const until = Date.now() + AHEAD_MS;
  const list = (await allGames(null)).games.filter((g) => g.commence_time && Date.parse(g.commence_time) < until && g.home && g.away).slice(0, MOST);
  const art = await gameArt(list);
  const games: GameRefs = {};
  for (const g of list) {
    const a = art[g.game_id];
    games[`/games/${g.league}/${g.game_id}`] = {
      title: `${g.away} @ ${g.home}`, when: dayTime(g.commence_time),
      away: { src: a?.away.logo, name: g.away!, abbr: a?.away.abbr, color: a?.away.color },
      home: { src: a?.home.logo, name: g.home!, abbr: a?.home.abbr, color: a?.home.color },
    };
  }
  const first = list.find((g) => art[g.game_id]?.away.logo && art[g.game_id]?.home.logo) ?? list[0];
  const ref = first ? games[`/games/${first.league}/${first.game_id}`] : null;
  return { games, game: ref ? { cap: "A game", q: `Break down ${ref.title}`, art: [ref.away, ref.home] } : null };
}

/** The local preview's made-up conversation (/chat?sample=1, fixture mode only): the chat needs a key and sign-in, so
 *  this is how its look is checked. Its game links are the fixture's own next games. */
function sampleTurns(games: GameRefs): Turn[] {
  const [a, b] = Object.entries(games);
  const link = (e?: [string, { title: string }]) => (e ? `[${e[1].title}](${e[0]})` : "tonight's first game");
  return [
    { role: "user", content: "What's the best bet tonight?" },
    { role: "assistant", content: `**One pick clears the bar tonight**, and one lean is close.\n\n- ${link(a)}: the home side at -108, fair -121, **+2.9% EV**\n- ${link(b)}: over 224.5 at -105, a lean at +1.1%\n\nThe first is the book lagging the sharp price by about 3 points of chance: -108 implies 51.9%, the sharp no-vig price says 54.8%.` },
    { role: "user", content: "And how are my open bets doing?" },
    { role: "assistant", content: `You have **2 open bets**, both live.\n\n1. The 4-leg parlay on ${link(a)} has 1 of 4 legs in and needs 4 more points from its first leg.\n2. Your moneyline is up 6 at the half.\n\nNothing is lost yet. I can't change or cash out a bet; the game page has the links.` },
  ];
}

/** Chat with BetLab (Mike's W22, Oct 24): Claude over your bets, the board and the games. */
export default async function ChatPage({ searchParams }: { searchParams: Promise<{ sample?: string }> }) {
  const sp = await searchParams;
  const { games, game } = await soon(comingGames(), { games: {}, game: null });
  const sample = fixtureMode() && sp.sample !== undefined ? sampleTurns(games) : null;
  return (
    <main className="rail chatpage">
      <Chat ready={chatReady()} games={games} game={game} sample={sample} />
    </main>
  );
}
