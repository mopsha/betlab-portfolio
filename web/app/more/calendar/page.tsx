import Link from "next/link";
import { GameCard } from "@/components/games/GameCard";
import { gameArt } from "@/lib/art";
import { calendarData, type Game } from "@/lib/data";
import { monthGrid, monthName, shiftMonth } from "@/lib/calendar";
import { SPORTS, longDay } from "@/lib/format";
import { etDay } from "@/lib/time";

export const dynamic = "force-dynamic";

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
const DOW = ["S", "M", "T", "W", "T", "F", "S"];
const OPEN_UP_TO = 12;       // a sport with more games than this starts folded (college basketball's 100 a night)

/** The calendar (Nov 4): a clean month, a dot on the days with your bets or a lock; below it the day: your bets, its locks, and its games
 *  as the Games tab's cards, by sport. Every game ESPN lists for the next 10 weeks, read once a day (calendar_sync.py). */
export default async function Calendar({ searchParams }: { searchParams: Promise<{ day?: string; month?: string; sport?: string }> }) {
  const sp = await searchParams;
  const today = etDay(new Date());
  const day = /^\d{4}-\d{2}-\d{2}$/.test(sp.day ?? "") ? sp.day! : today;
  const month = /^\d{4}-\d{2}$/.test(sp.month ?? "") ? sp.month! : day.slice(0, 7);
  const sport = sp.sport && SPORTS[sp.sport] ? sp.sport : null;
  const cells = monthGrid(month);
  const d = await calendarData(cells, day, sport);
  const lockDays = new Set(d.allLocks.map((l) => etDay(l.at)));
  const q = (o: { day?: string; month?: string; sport?: string | null }) => {
    const p = new URLSearchParams({ month: o.month ?? month, day: o.day ?? day });
    const s = o.sport === undefined ? sport : o.sport;
    if (s) p.set("sport", s);
    return `/more/calendar?${p}`;
  };
  const asGame = (g: (typeof d.games)[number]) => ({ game_id: g.game_id ?? g.id, league: g.sport, home: g.home, away: g.away, matchup: g.matchup, commence_time: g.start }) as Game;
  const art = await gameArt(d.games.map(asGame)).catch(() => ({}) as Awaited<ReturnType<typeof gameArt>>);
  const sports = [...new Set(d.games.map((g) => g.sport))];
  return (
    <main className="rail">
      <div className="head"><h1>Calendar</h1></div>
      <nav className="chips" aria-label="Sport" style={{ marginBottom: 14 }}>
        <Link href={q({ sport: null })} aria-current={!sport}>All</Link>
        {d.sports.map((s) => <Link key={s} href={q({ sport: s })} aria-current={s === sport}>{SPORTS[s] ?? s}</Link>)}
      </nav>
      <section className="card calmonth">
        <div className="calhead">
          <h2>{monthName(month)}</h2>
          <span className="calarrows">
            <Link href={q({ month: shiftMonth(month, -1) })} aria-label="Previous month">‹</Link>
            <Link href={q({ month: shiftMonth(month, 1) })} aria-label="Next month">›</Link>
          </span>
        </div>
        <div className="calgrid" role="grid" aria-label={monthName(month)}>
          {DOW.map((w, i) => <div key={i} className="dow" aria-hidden="true">{w}</div>)}
          {cells.map((c) => {
            const n = d.count[c] ?? 0, bets = d.betDays[c] ?? 0, lock = lockDays.has(c);
            const label = `${longDay(c)}: ${n} games${bets ? `, ${bets} of your bets` : ""}${lock ? ", a lock" : ""}`;
            return (
              <Link key={c} href={q({ day: c, month: c.slice(0, 7) })} aria-label={label} aria-current={c === day ? "date" : undefined}
                    className={`calday${c.slice(0, 7) === month ? "" : " out"}${c === today ? " today" : ""}${n || bets ? "" : " quiet"}`}>
                <b>{Number(c.slice(8))}</b>
                <span className="caldots" aria-hidden="true">{bets > 0 && <i className="cal-bet" />}{lock && <i className="cal-lock" />}</span>
              </Link>
            );
          })}
        </div>
        <p className="callegend" aria-hidden="true"><i className="cal-bet" /> your bets <i className="cal-lock" /> a lock</p>
      </section>
      <h2 className="day">{longDay(day)}{day === today ? " · today" : ""}</h2>
      <div className="feed">
        {d.bets.map((b) => (
          <Link key={b.bet_id} className="card calrow" href="/bets"><span><span className="tag lean">Your bet</span> {b.label ?? b.matchup}</span></Link>
        ))}
        {d.locks.length > 0 && (
          <details className="card calfold">
            <summary><b>{d.locks.length} lock{d.locks.length > 1 ? "s" : ""}</b> <span className="faint">next by {time(d.locks[0].at)}</span></summary>
            {d.locks.map((l) => <div key={l.slate} className="calrow"><span>{l.title}</span><span className="faint">by {time(l.at)}</span></div>)}
          </details>
        )}
        {sports.map((s) => {
          const games = d.games.filter((g) => g.sport === s);
          return (
            <details key={s} className="calsport" open={games.length <= OPEN_UP_TO || !!sport}>
              <summary><b>{SPORTS[s] ?? s}</b> <span className="faint">{games.length} game{games.length > 1 ? "s" : ""}</span></summary>
              <div className="feed">
                {games.map((g) => <GameCard key={g.id} g={asGame(g)} art={art[g.game_id ?? g.id]} linked={!!g.game_id} />)}
              </div>
            </details>
          );
        })}
        {!d.games.length && !d.bets.length && !d.locks.length && <p className="faint">No games listed for this day yet.</p>}
      </div>
    </main>
  );
}
