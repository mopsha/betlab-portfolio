import Link from "next/link";
import { IconLink, ScreenHead } from "@/components/ui/Kit";
import { GameCard } from "@/components/games/GameCard";
import { Art } from "@/components/ui/Art";
import { gameArt } from "@/lib/art";
import { allGames } from "@/lib/data";
import { SPORTS, longDay } from "@/lib/format";
import { etDay } from "@/lib/time";

/** Every game in the next week, by day, filterable by sport. Each opens its own page. */
export default async function Games({ searchParams }: { searchParams: Promise<{ sport?: string }> }) {
  const sp = await searchParams;
  const sport = sp.sport && SPORTS[sp.sport] ? sp.sport : null;
  const { games, sports, counts } = await allGames(sport);
  const art = await gameArt(games).catch(() => ({}) as Awaited<ReturnType<typeof gameArt>>);   // logos and colors; the list works without
  let last = "";
  return (
    <main className="rail">
      <ScreenHead title="Games"><IconLink href="/more/calendar" icon="calendar" label="Calendar" /></ScreenHead>
      <nav className="chips" aria-label="Sport" style={{ marginBottom: 14 }}>
        <Link href="/games" aria-current={!sport}>All</Link>
        {sports.map((s) => <Link key={s} href={`/games?sport=${s}`} aria-current={s === sport}><Art kind="league" name={s} size={18} />{SPORTS[s] ?? s}</Link>)}
      </nav>
      <div className="feed">
        {games.map((g) => {
          const day = g.commence_time ? etDay(g.commence_time) : "";
          const header = day !== last ? <h2 className="day" key={`d-${day}`}>{day ? longDay(day) : "Date to be set"}</h2> : null;
          last = day;
          const c = counts[g.game_id];
          return [header, <GameCard key={g.game_id} g={g} art={art[g.game_id]} count={c} />];
        })}
      </div>
    </main>
  );
}
