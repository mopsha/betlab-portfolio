import { notFound } from "next/navigation";
import { nbaFolds, nbaMeta, nbaTop, ncaafFolds, ncaafMeta, ncaafTop, nflFolds, nflMeta, nflTop, nhlFolds, nhlMeta, nhlTop, soccerBadges, soccerFolds, soccerMeta, soccerTop, ufcFolds, ufcMeta, ufcTop, type Fold } from "@/components/games/Analysis";
import { BetRow } from "@/components/today/BetRow";
import { OverRow, TicketCard } from "@/components/today/TicketCard";
import { onBooks } from "@/lib/books";
import { booksOff, gameData, myBetsData, settingsData } from "@/lib/data";
import { WatchButton } from "@/components/games/WatchButton";
import { dayTime, matchupText, num, sportName } from "@/lib/format";
import { BackLink } from "@/components/ui/BackLink";
import { GameBets } from "@/components/games/GameBets";
import { Notebook, notebookOf } from "@/components/games/Notebook";
import { GameHero, type WinChance } from "@/components/games/GameHero";
import type { ArtOf } from "@/components/ui/Art";
import { IconLink, SectionTitle } from "@/components/ui/Kit";
import { gameArt } from "@/lib/art";
import { isSettled } from "@/lib/bets";
import { betName } from "@/lib/gameday";
import { sideOf } from "@/lib/live";
import { gamePair, offerArt } from "@/lib/pictures";

/** Pictures are a nicety: a slow ESPN never holds the page (2.5 s, then the monograms). */
const soon = <T,>(p: Promise<T>, fallback: T, ms = 2500) => Promise.race([p.catch(() => fallback), new Promise<T>((r) => setTimeout(() => r(fallback), ms))]);

/** One page per game (docs/APP_PLAN.md): its bets, its parlays, then the analysis folded below. */
export default async function GamePage({ params }: { params: Promise<{ league: string; id: string }> }) {
  const { league, id } = await params;
  const d = await gameData(`${league}:${decodeURIComponent(id)}`);
  if (!d) notFound();
  const { game: g, offers, tickets, analysis: an, mine, quotes } = d;
  // the wall's scoreboard on top (Oct 24, from the iPhone's game page): logos, colors, and the live score once it starts
  const art = (await gameArt([g], 15_000).catch(() => ({}) as Record<string, never>))[g.game_id];

  // the price tables show the account's books only (Nov 6, Analysis.colsOf); watched games (Nov 7)
  const [off, settings] = await Promise.all([booksOff(), settingsData().catch(() => null)]);
  const on = onBooks(off);
  const watching = (settings?.watching ?? []).includes(g.game_id);
  const ahead = !!g.commence_time && Date.parse(g.commence_time) > Date.now();
  const withOn = <T,>(x: T): T => (x ? { ...x, books_on: on } : x);
  const nfl = withOn(an.nfl_preview), cfb = withOn(an.ncaaf_preview), nhl = withOn(an.nhl), soc = withOn(an.soccer), nba = withOn(an.nba), ufc = withOn(an.ufc);
  const meta = nfl ? nflMeta(nfl) : cfb ? ncaafMeta(cfb) : nhl ? nhlMeta(nhl) : soc ? soccerMeta(soc) : nba ? nbaMeta(nba) : ufc ? ufcMeta(ufc) : [];
  const top = nfl ? nflTop(nfl) : cfb ? ncaafTop(cfb) : nhl ? nhlTop(nhl) : soc ? soccerTop(soc) : nba ? nbaTop(nba) : ufc ? ufcTop(ufc) : null;
  const folds: Fold[] = nfl ? nflFolds(nfl, an.nfl_fun) : cfb ? ncaafFolds(cfb) : nhl ? nhlFolds(nhl) : soc ? soccerFolds(soc) : nba ? nbaFolds(nba) : ufc ? ufcFolds(ufc) : [];
  const badges: string[] = soc ? soccerBadges(soc) : [];
  for (const t of nfl?.teams ?? []) if (t.qb?.change) badges.push(`New QB: ${t.qb.name}`);
  for (const t of nhl?.teams ?? []) if (t.goalie_status && t.goalie_status !== "confirmed") badges.push(`${t.team} goalie ${t.goalie_status}`);
  for (const t of nhl?.teams ?? []) if (t.b2b) badges.push(`${t.team} on a back-to-back`);

  const bets = offers.filter((o) => o.tier !== "check");
  const checks = offers.filter((o) => o.tier === "check");
  const sgps = tickets.filter((t) => t.kind === "sgp");
  const overs = tickets.filter((t) => t.kind === "over");
  if (checks.length) folds.unshift({ key: "check", title: "Check the news", n: checks.length,
    body: <div className="feed">{checks.map((o) => <BetRow key={o.offer_id} o={o} showGame={false} />)}</div> });

  // pictures for the bets (a prop's player by search, a side's logo), your open bets for "Your bet", the chance to win
  const [arts, mineOpen] = await Promise.all([
    soon(Promise.all(bets.slice(0, 16).map((o) => offerArt(o, art))), [] as (ArtOf | null)[]),
    myBetsData().then(({ bets: all }) => all.filter((b) => !isSettled(b)).map((b) => { const n = betName({ ...b, price: null });
      return { id: b.bet_id, name: n.startsWith("Bet") ? b.matchup ?? n : n, price: b.price }; })).catch(() => []),
  ]);
  const pHome = num(nhl?.line?.p_home ?? nhl?.model?.p_home);
  const pA = num(ufc?.dk?.ml?.p_a ?? ufc?.model?.p_a), first = ufc?.fighters?.[0]?.name as string | undefined;
  const ufcSide = art && first ? sideOf(first, art) : null;
  const chance: WinChance | null = !art || art.state === "post" ? null
    : pHome !== null ? { home: pHome, away: 1 - pHome, label: nhl?.line?.p_home != null ? "Market's chance to win" : "Our model's chance to win" }
    : pA !== null && ufcSide ? { home: ufcSide === "home" ? pA : 1 - pA, away: ufcSide === "away" ? pA : 1 - pA, label: "Chance to win" } : null;
  const count = [bets.length ? `${bets.length} bet${bets.length === 1 ? "" : "s"}` : "", sgps.length ? `${sgps.length} parlay${sgps.length === 1 ? "" : "s"}` : "",
    overs.length ? `${overs.length} to root for` : ""].filter(Boolean).join(" · ");

  return (
    <main className="wide gpage">
      <div className="gp-main">
        <div className="gp-top"><BackLink /><span className="sub">{sportName(g.league)} · {dayTime(g.commence_time)} ET</span>
          <span className="gp-tools">{ahead && <WatchButton gameId={g.game_id} on={watching} />}<IconLink href="/search" icon="search" label="Search" /></span></div>
        <GameHero g={art} title={matchupText(g.matchup, g.league)} when={dayTime(g.commence_time)} chance={chance}>
          {(meta.length > 0 || badges.length > 0) && (
            <div className="gh-meta">
              {meta.map((m) => <span key={m}>{m}</span>)}
              {badges.map((b) => <span className="tag warn" key={b}>{b}</span>)}
            </div>
          )}
        </GameHero>
        {art && <GameBets bets={mineOpen} espnId={art.espnId} teams={[art.away.name, art.home.name]} />}
        <Notebook nb={notebookOf(nfl)} bet={bets[0]} />

        {count && <SectionTitle note={count}>Bets on this game</SectionTitle>}
        {bets.length > 0 && <div className="feed">{bets.map((o, i) => <BetRow key={o.offer_id} o={o} mine={mine[o.offer_id]} showGame={false} art={arts[i]}
          pair={arts[i] ? undefined : gamePair(art)} />)}</div>}
        {sgps.length > 0 && (
          <section className="sec"><h3 className="cap">Parlays</h3>
            {ahead && <p className="sub watchnote">{watching ? "You're watching: these join Today's Parlays when the slice locks, with an alert."
              : "Tap Watch to get these on Today when the slice locks, with an alert."}</p>}
            <div className="grid-tickets">{sgps.map((t) => <TicketCard key={t.sgp_id} t={t} mine={mine[t.sgp_id]} quote={quotes[t.sgp_id]} dkQuote={quotes[`${t.sgp_id}~dk`]} />)}</div>
          </section>
        )}
        {overs.length > 0 && (
          <section className="sec"><h3 className="cap">To root for</h3>
            <div className="grid-tickets">{overs.map((t) => <OverRow key={t.sgp_id} t={t} mine={mine[t.sgp_id]} />)}</div>
          </section>
        )}
        {!bets.length && !sgps.length && !overs.length && !notebookOf(nfl) && (
          <div className="card empty" style={{ marginTop: 18 }}><b>Nothing to act on in this game</b><span>No pick, lean or parlay cleared the bar.{folds.length > 0 || top ? " The analysis is below." : ""}</span></div>
        )}
      </div>
      {(top || folds.length > 0) && (
        <div className="gp-side">
          <SectionTitle>Analysis</SectionTitle>
          {top}
          {folds.length > 0 && (
            <div className="card folds">
              {folds.map((f) => (
                <details className="fold" key={f.key}>
                  <summary><span>{f.title}</span>{f.n ? <span className="n">{f.n}</span> : null}</summary>
                  <div className="fb">{f.body}</div>
                </details>
              ))}
            </div>
          )}
        </div>
      )}
    </main>
  );
}
