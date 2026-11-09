import { redirect } from "next/navigation";
import Link from "next/link";
import { RefreshControl } from "@/components/app/RefreshControl";
import { refreshData } from "@/lib/refresh";
import { BetRow } from "@/components/today/BetRow";
import { GameRow } from "@/components/today/GameRow";
import { LiveCards, LockList, NextLock, type HubLock, type OpenBet } from "@/components/today/LiveCards";
import { ParlayShelf, type ParlayCard } from "@/components/today/ParlayShelf";
import { TicketCard } from "@/components/today/TicketCard";
import { Art, type ArtOf } from "@/components/ui/Art";
import { IconLink, ScreenHead, SectionTitle } from "@/components/ui/Kit";
import { Spark } from "@/components/ui/Chart";
import { gameArt } from "@/lib/art";
import { dayOf, isBonus, isSettled, profit, recordBets, stakeOf, startOf } from "@/lib/bets";
import { fmtU, isReal } from "@/lib/real";
import { homeData, myBetsData, myMarks, needsWelcome, promosData, type FeedItem, type Game, type Slate, type Ticket } from "@/lib/data";
import { expiringSoon, promoTitle } from "@/lib/promos";
import { betName } from "@/lib/gameday";
import { liveSettled, markLiveSettled } from "@/lib/live-bets";
import type { GameLive } from "@/lib/live";
import { gamePair, offerArt, ticketArt } from "@/lib/pictures";
import { MINUS, SPORTS, SPORT_SHORT, dayTime, fmtAm, longDay, matchupText, time } from "@/lib/format";
import { etDay, type DayKey } from "@/lib/time";

const DAYS: [DayKey, string][] = [["today", "Today"], ["tomorrow", "Tomorrow"], ["week", "This week"]];
const WINDOW: Record<string, string> = { early: "early games", late: "late games", night: "night" };

/** "Saturday noon games · SGP+ · locked": the slice says when (its title comes from sgp_plus.slice_names),
 *  the sport chip already says which sport. Slates from before Oct 10 have no title. */
function ticketTitle(t: Ticket, s: Slate | null): string {
  // a watched game's own parlay (Nov 7): its game, and what kind of slip it is
  if (t.kind === "sgp") return `${matchupText(t.matchup ?? "", t.sport)} · ${t.body.style === "single" ? "best single" : t.body.style === "longshot" || t.body.longshot ? "long shot" : "parlay"} · watching${s?.locked_at ? " · locked" : ""}`;
  const what = (t.body.cup ? `${t.body.cup} ` : "") + (t.kind === "td" ? "anytime TD ticket" : "SGP+") + (s?.locked_at ? " · locked" : "");
  if (s?.title) return `${s.title} · ${what}`;
  const day = new Date(t.commence_time ?? "").toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "long" });
  const w = /-(early|late|night)$/.exec(s?.slate ?? "")?.[1];
  return `${day} ${w ? WINDOW[w] : `· ${s?.n_games ?? t.body.games?.length ?? ""} games`} · ${what}`;
}

/** "Bengals @ Falcons": a matchup by its teams' last words, short enough for a shelf card's chip. */
const nicks = (m?: string | null) => String(m ?? "").split(/ @ | vs\.? /).map((s) => s.trim().split(" ").pop()).join(" @ ");
const units = (u: number, d = 1) => (u >= 0 ? "+" : MINUS) + Math.abs(u).toFixed(d) + "u";
/** Pictures are a nicety: a slow ESPN never holds the page (2.5 s, then the monograms). */
const soon = <T,>(p: Promise<T>, fallback: T, ms = 2500) => Promise.race([p.catch(() => fallback), new Promise<T>((r) => setTimeout(() => r(fallback), ms))]);
const pseudo = (id: string, league: string, matchup: string | null, at: string | null): Game =>
  ({ game_id: id, league, odds_event_id: null, home: null, away: null, matchup, commence_time: at, state: null, home_score: null, away_score: null });

export default async function Home({ searchParams }: { searchParams: Promise<{ day?: string; sport?: string }> }) {
  if (await needsWelcome()) redirect("/welcome");       // a new account's first look (Nov 5)
  const sp = await searchParams;
  const day = (DAYS.some(([k]) => k === sp.day) ? sp.day : "today") as DayKey;
  const sport = sp.sport && SPORTS[sp.sport] ? sp.sport : null;
  // a failed bets read must not read as "nothing in play" and "0 open bets" (Nov 9): say it failed instead
  let betsFailed = false;
  const [d, marks, refresh, mine, wallet] = await Promise.all([homeData(day, sport), myMarks(), refreshData(),
    day === "today" ? myBetsData().catch(() => { betsFailed = true; return null; }) : Promise.resolve(null), promosData().catch(() => [])]);
  const today = etDay(new Date().toISOString());
  // a promo that runs out today (Oct 30): one line, to the finder
  const promoToday = expiringSoon(wallet).filter((p) => p.expires_at && etDay(p.expires_at) === today);
  // today's locks still to come (a ticket joins Parlays once it locks)
  const hubLocks: HubLock[] = day !== "today" ? [] : d.nextLocks.filter((l) => etDay(l.at) === today)
    .map((l) => ({ slate: l.slate, title: l.title, at: l.at }));
  const q = (over: Record<string, string | null>) => {
    const p = new URLSearchParams();
    const next = { day, sport, ...over };
    if (next.day && next.day !== "today") p.set("day", next.day);
    if (next.sport) p.set("sport", next.sport);
    const s = p.toString();
    return s ? `/?${s}` : "/";
  };

  // the day's units (the hero): today's settled bets, counted like Live and Me (real money once it started; a bet the
  // tracker already settled counts), and what's still in play
  const settledLive = mine ? await liveSettled(mine.bets).catch(() => new Map<string, "won" | "lost">()) : new Map<string, "won" | "lost">();
  const bets = mine ? markLiveSettled(mine.bets, settledLive) : [];
  const { counted } = recordBets(bets, isReal(new Date(), mine?.settings.real_from));
  const todays = counted.filter((b) => dayOf(b) === today);
  const done = todays.filter(isSettled).sort((a, b) => String(startOf(a) ?? a.placed_at).localeCompare(String(startOf(b) ?? b.placed_at)));
  let run = 0;
  const trend = [0, ...done.map((b) => (run += profit(b) ?? 0))];
  const inPlay = todays.filter((b) => !isSettled(b) && !isBonus(b)).reduce((s, b) => s + stakeOf(b), 0);
  const openBets: OpenBet[] = bets.filter((b) => !isSettled(b)).map((b) => {
    const n = betName({ ...b, price: null });
    return { id: b.bet_id, name: n.startsWith("Bet") ? b.matchup ?? n : n, price: b.price };
  });

  // pictures: each pick's, game's and parlay's teams from ESPN's boards, its players by search
  const tickets = d.items.flatMap((it) => (it.kind === "ticket" ? [it] : []));
  const feedGames = d.items.flatMap((it) => (it.kind === "game" ? [it.game] : []));
  const ticketGames = tickets.flatMap(({ ticket: t }) => (t.body.games ?? []).map((g) => pseudo(`m:${g.matchup}`, t.sport, g.matchup, g.commence_time)));
  const pickGames = d.picks.filter((o) => o.game_id).map((o) => pseudo(o.game_id!, o.league, o.matchup, o.commence_time));
  const art = await soon(gameArt([...feedGames, ...pickGames, ...ticketGames]), {} as Record<string, GameLive>);
  const byMatchup = new Map(ticketGames.flatMap((g) => (art[g.game_id] ? [[g.matchup!, art[g.game_id]] as const] : [])));
  const [pickArt, ticketArts] = await soon(Promise.all([
    Promise.all(d.picks.map((o) => offerArt(o, o.game_id ? art[o.game_id] : null))),
    Promise.all(tickets.map(({ ticket }) => ticketArt(ticket, byMatchup))),
  ]), [d.picks.map(() => null), tickets.map(() => [])] as [(ArtOf | null)[], ArtOf[][]]);

  const cards: ParlayCard[] = tickets.map(({ ticket: t, slate }, i) => {
    const legs = (t.body.games ?? []).flatMap((g) => g.legs).concat(t.body.games ? [] : t.body.legs ?? []);
    const at = t.body.nv?.price ?? null;
    return {
      id: t.sgp_id, league: t.sport, art: ticketArts[i] ?? [],
      chip: t.kind === "sgp" ? nicks(t.matchup) : `${SPORT_SHORT[t.sport] ?? t.sport} · ${slate?.title ?? time(t.commence_time)}`,
      price: fmtAm(at ?? t.fair_price), cap: at !== null ? "Novig" : "fair price", placed: !!marks[t.sgp_id],
      sub: `${t.kind === "td" ? "Anytime TD · " : ""}${legs.map((l) => (typeof l === "string" ? l : l.label)).slice(0, 4).join(" · ")}${legs.length > 4 ? ` · +${legs.length - 4}` : ""}`,
    };
  });

  let lastDay = "";
  const rows = feedGames.map((g) => {
    const dayKey = g.commence_time ? etDay(g.commence_time) : "";
    const header = day === "week" && dayKey !== lastDay ? <h3 className="day" key={`d-${dayKey}`}>{longDay(dayKey)}</h3> : null;
    lastDay = dayKey;
    return [header, <GameRow key={g.game_id} g={g} art={art[g.game_id]} />];
  });

  const dateLine = new Date().toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "long", month: "short", day: "numeric" });
  const hasDay = day === "today" && todays.length > 0;
  const nothing = !d.picks.length && !cards.length && !rows.length;
  return (
    <main className="rail today">
      {d.fixture && <p className="banner">Local preview: today's snapshot of the database, no sign-in. Marks reset when the preview restarts.</p>}
      <ScreenHead lead={<span className="date">{dateLine}</span>}>
        <RefreshControl initial={refresh} icon />
        <IconLink href="/chat" icon="chat" label="Ask BetLab" />
      </ScreenHead>

      <div className="today-grid">
        <section className="today-hero" aria-label={day === "today" ? "Today" : undefined}>
          {betsFailed ? (
            <div role="alert">
              <h1 className="today-title">Today</h1>
              <p className="sub">Couldn&apos;t load your bets just now, so today&apos;s units aren&apos;t shown. Reload, or open <Link href="/bets">Live</Link>.</p>
            </div>
          ) : hasDay ? (
            <div className="hero-row">
              <div>
                <div className={`hero-num ${run > 0.004 ? "pos" : run < -0.004 ? "neg" : ""}`}>{units(run)}</div>
                <p className="sub">today{inPlay > 0 ? ` · ${inPlay.toFixed(1)}u still in play` : done.length ? ` · ${done.length} settled` : ""}</p>
              </div>
              {trend.length > 2 && <Spark points={trend} label={`Today's units, ${run >= 0 ? "up" : "down"} ${Math.abs(run).toFixed(1)}`} />}
            </div>
          ) : (
            <div>
              <h1 className="today-title">{day === "today" ? "Today" : day === "tomorrow" ? "Tomorrow" : "This week"}</h1>
              <p className="sub">{day !== "today" ? "What's worth a look, by start time"
                : d.picks.length || cards.length ? `Nothing in play yet · ${[d.picks.length ? `${d.picks.length} pick${d.picks.length === 1 ? "" : "s"}` : "", cards.length ? `${cards.length} parlay${cards.length === 1 ? "" : "s"}` : ""].filter(Boolean).join(" and ")} to look at`
                : "Nothing in play yet"}</p>
            </div>
          )}
          <p className="sub today-meta">
            <Link href="/bets">{betsFailed ? "Your bets" : `${openBets.length} open bet${openBets.length === 1 ? "" : "s"}`}</Link> · fun bucket {fmtU(d.bucket.used)} of {fmtU(d.bucket.cap)}
            {d.pricedAt && <> · priced {dayTime(d.pricedAt)} ET</>}
          </p>
          {day === "today" && promoToday.length > 0 && (
            <Link className="card promo-line" href={`/build/promo?promo_id=${promoToday[0].promo_id}`}>
              <span className="grow"><b>Expires today</b><small>{promoToday.map((p) => `${promoTitle(p)}${p.book ? ` at ${p.book}` : ""}`).join(", ")}</small></span>
              <span className="sub">Find the best bet</span><span className="chev" aria-hidden>›</span>
            </Link>
          )}
        </section>

        {day === "today" && openBets.length > 0 && <aside className="today-live"><LiveCards bets={openBets} /></aside>}

        <div className="today-main">
          <div className="controls">
            <nav className="seg" aria-label="Day">
              {DAYS.map(([k, l]) => <Link key={k} href={q({ day: k })} aria-current={k === day}>{l}</Link>)}
            </nav>
            <nav className="chips" aria-label="Sport">
              <Link href={q({ sport: null })} aria-current={!sport}>All</Link>
              {d.sports.map((s) => <Link key={s} href={q({ sport: s })} aria-current={s === sport}><Art kind="league" name={s} size={18} />{SPORTS[s] ?? s}</Link>)}
            </nav>
          </div>

          {d.picks.length > 0 && (
            <>
              <SectionTitle note={d.picks.length}>{day === "today" ? `Today's pick${d.picks.length === 1 ? "" : "s"}` : "Picks"}</SectionTitle>
              <div className="feed">{d.picks.map((o, i) => <BetRow key={o.offer_id} o={o} mine={marks[o.offer_id]} art={pickArt[i]}
                pair={pickArt[i] ? undefined : gamePair(o.game_id ? art[o.game_id] : null)} />)}</div>
            </>
          )}

          {(cards.length > 0 || hubLocks.length > 0) && (
            <>
              <SectionTitle note={<>{cards.length > 0 ? cards.length : null}{cards.length > 0 && hubLocks.length > 0 ? " · " : null}{hubLocks.length > 0 && <NextLock locks={hubLocks} />}</>}>Parlays</SectionTitle>
              {cards.length > 0
                ? <ParlayShelf cards={cards} details={tickets.map(({ ticket: t, slate }) => (
                    <div key={t.sgp_id}><p className="sub pshelf-title">{ticketTitle(t, slate)} · fair {fmtAm(t.fair_price)}</p><TicketCard t={t} mine={marks[t.sgp_id]} /></div>))} />
                : <LockList locks={hubLocks} />}
            </>
          )}
          {day !== "today" && d.nextLocks.length > 0 && !cards.length && (
            <p className="sub" title="A slice locks early once the news is in for every one of its games">Next lock: <b>{d.nextLocks[0].title}</b> by {dayTime(d.nextLocks[0].at)}</p>
          )}

          {rows.length > 0 && (
            <>
              <SectionTitle note={rows.length}>Games</SectionTitle>
              <div className="feed">{rows}</div>
            </>
          )}
          {nothing && (
            <div className="card empty">
              <b>Nothing to act on {day === "today" ? "today" : day === "tomorrow" ? "tomorrow" : "this week"}</b>
              <span>No pick or parlay cleared the bar. Most days the market is priced right; leans are on each game&apos;s page.</span>
            </div>
          )}
          {d.quiet > 0 && <p className="note" style={{ marginTop: 12 }}>{d.quiet} more game{d.quiet === 1 ? "" : "s"} with nothing to act on are on <Link href="/games">Games</Link>.</p>}
        </div>
      </div>
    </main>
  );
}
