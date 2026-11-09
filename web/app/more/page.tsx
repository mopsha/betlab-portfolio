import Link from "next/link";
import { InstallApp } from "@/components/app/InstallApp";
import { MeBadges } from "@/components/me/MeBadges";
import { MeFriends } from "@/components/me/MeFriends";
import { MeNumbers } from "@/components/me/MeNumbers";
import { ArtStack, type ArtOf } from "@/components/ui/Art";
import { IconLink, SectionTitle } from "@/components/ui/Kit";
import { achievements } from "@/lib/achievements";
import { friendBets, ladderData, promosData, socialData, todosData } from "@/lib/data";
import { headshot } from "@/lib/headshots";
import { ladderState, stepsToTarget } from "@/lib/ladder";
import { meNumbers, rangeOf, walletLine } from "@/lib/me-view";
import { isOwner } from "@/lib/owner";
import { players } from "@/lib/players";
import { expiringSoon, wallet } from "@/lib/promos";
import { fmtU, realStart } from "@/lib/real";
import { circle } from "@/lib/social";
import { etDay } from "@/lib/time";
import { rungs } from "@/lib/wallet-view";
import { betsView } from "@/app/bets/load";

const soon = <T,>(p: Promise<T>, fallback: T, ms = 2500) => Promise.race([p.catch(() => fallback), new Promise<T>((r) => setTimeout(() => r(fallback), ms))]);
const HEAD_SPORT: Record<string, string> = { nba: "NBA", nfl: "NFL", nhl: "NHL", wnba: "WNBA", ncaaf: "NCAAF", ncaab: "NCAAB", soccer: "Soccer" };
const EXTRAS = [["/more/learn", "Learn"], ["/wrapped", "Wrapped"], ["/more/challenges", "Novig challenges"], ["/more/pickem", "CFB Pick'em"], ["/more/prices", "Prices"],
  ["/more/calendar", "Calendar"], ["/more/dfs", "DFS lineups"], ["/ticker", "Desktop ticker"], ["/welcome?again=1", "Intro"], ["/more/markets", "Markets"]] as const;

/** Me (the overhaul, Nov 4; reorganized Nov 5: "all the right functionality exists, it can just be organized so much
 *  better"). About you, in one order, each place with one way in: who you are; your number for the week, the month or
 *  all time with its chart and four stats; your betting (promos, ladder, record and stats); badges; friends; BetLab's
 *  own pages; extras as chips. Settings is the round button in the header. */
export default async function Me({ searchParams }: { searchParams: Promise<{ range?: string }> }) {
  const range = rangeOf((await searchParams).range);
  const [{ d, hasReal, counted }, todos, owner, social, promos] = await Promise.all([
    betsView(), todosData().catch(() => []), isOwner(), socialData().catch(() => null), promosData().catch(() => [])]);
  const today = etDay(new Date().toISOString());
  const numbers = meNumbers(counted, range, today);
  const start = realStart(d.settings.real_from).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
  const since = hasReal ? `since ${start}` : "paper";

  const open = wallet(promos).open, held = walletLine(open);
  const ending = expiringSoon(promos).filter((p) => p.expires_at && etDay(p.expires_at) === today).length;
  const ladders = await ladderData(d.settings.bans ?? []).then((l) => l.ladders).catch(() => []);
  const active = ladders.find((l) => l.status === "active");
  const ladder = active ? ladderState(active, d.bets) : null;
  const target = active ? Number(active.target_units) : 0;
  const track = ladder ? rungs(ladder.won, stepsToTarget(ladder.stack, target, 100), null, 8) : [];

  const me = social?.profile ?? null;
  const friends = social ? circle(social.me, social.friendships, social.profiles) : null;
  const theirs = friends?.friends.length ? await friendBets().catch(() => []) : [];
  const betToday: Record<string, number> = {};
  for (const b of theirs) if (b.user_id && etDay(b.placed_at) === today) betToday[b.user_id] = (betToday[b.user_id] ?? 0) + 1;
  const name = me?.name ?? (social?.email ? social.email.split("@")[0] : "You");

  // the players you bet on most, for the Record and stats row (their photos by search, cached a day)
  const top = players(counted).slice(0, 3);
  const faces: ArtOf[] = await soon(Promise.all(top.map(async (p) => ({ src: (await headshot(p.name, HEAD_SPORT[p.sport.toLowerCase()] ?? p.sport)).url, name: p.name, kind: "player" as const }))), []);
  const forYou = todos.filter((t) => t.owner === "you" && t.status === "open").length;

  return (
    <main className="rail me">
      {d.fixture && <p className="banner">Local preview: sample bets, no sign-in.</p>}
      <div className="shead">
        <div className="me-who">
          <span className="me-avatar" aria-hidden>{name.slice(0, 1).toUpperCase()}</span>
          <span><b>{name}</b><span className="sub">{me?.handle ? `@${me.handle} · ` : ""}{since}</span></span>
        </div>
        <span className="shead-tools"><IconLink href="/more/settings" icon="settings" label="Settings" /><IconLink href="/search" icon="search" label="Search" /></span>
      </div>

      <div className="me-dash">
        <MeNumbers n={numbers} range={range} />

        <div className="me-main">
          <section>
            <SectionTitle>Your betting</SectionTitle>
            <div className="tiles">
              <Link className="tile" href="/more/promos">
                <span className="cap">Promos</span>
                {held.dollars > 0 ? <span className="tile-big">${Math.round(held.dollars)}{held.boosts > 0 && <small> + {held.boosts} boost{held.boosts === 1 ? "" : "s"}</small>}</span>
                  : held.boosts > 0 ? <span className="tile-big">{held.boosts} <small>boost{held.boosts === 1 ? "" : "s"}</small></span>
                  : <span className="tile-big">None <small>waiting</small></span>}
                <span className={`sub${ending ? " warn" : ""}`}>{ending ? `${ending} end${ending === 1 ? "s" : ""} today` : open.length ? "The wallet and the finder" : "Add a bonus bet or boost"}</span>
              </Link>
              <Link className="tile" href="/more/ladder">
                <span className="cap">Ladder</span>
                {ladder ? <>
                  <span className="tile-big">{fmtU(ladder.stack)} <small>of {fmtU(target)}</small></span>
                  <span className="me-rungs" aria-hidden>{track.map((r, i) => <i key={i} className={r} />)}</span>
                  <span className="sr-only">{ladder.won} step{ladder.won === 1 ? "" : "s"} won</span>
                </> : <>
                  <span className="tile-big">Start one</span>
                  <span className="sub">Roll one stack toward a target</span>
                </>}
              </Link>
            </div>
            <Link className="card rowx me-record" href="/more/record">
              {faces.length > 0 && <ArtStack items={faces} size={30} />}
              <span className="grow">Record and stats<small>By sport, book and price · your players</small></span>
              <span className="chev" aria-hidden>›</span>
            </Link>
          </section>

          <MeBadges badges={achievements(counted)} />
        </div>

        <div className="me-side">
          <MeFriends friends={friends?.friends ?? []} today={betToday} requests={friends?.incoming.length ?? 0} />

          <section>
            <SectionTitle>BetLab</SectionTitle>
            <div className="card rows">
              <Link className="rowx" href="/chat"><span className="grow">Ask BetLab<small>Your bets, tonight&apos;s board, any game</small></span><span className="chev" aria-hidden>›</span></Link>
              <Link className="rowx" href="/more/model"><span className="grow">How the model is doing<small>Strengths and weak spots by market</small></span><span className="chev" aria-hidden>›</span></Link>
              {/* Reviews and Plan are the owner's work with Claude: other accounts don't see them (Oct 10). One row, two
                  places: the row opens the reviews, its pill the plan. */}
              {owner && (
                <div className="rowx me-two">
                  <Link className="grow" href="/more/reviews">Reviews and plan<small>The Tuesday reviews</small></Link>
                  <Link className={`mk${forYou ? " for-you" : ""}`} href="/more/plan" aria-label={forYou ? `Plan: ${forYou} for you` : "Plan"}>{forYou ? `${forYou} for you` : "Plan"}</Link>
                </div>
              )}
            </div>
          </section>

          <section>
            <SectionTitle>Extras</SectionTitle>
            <nav className="me-extras" aria-label="Extras">
              {EXTRAS.filter(([href]) => href !== "/more/challenges" || !(d.settings.books_off ?? []).includes("Novig"))
                .map(([href, l]) => <Link key={href} className="mk" href={href}>{l}</Link>)}
            </nav>
          </section>
          <InstallApp />
        </div>
      </div>
    </main>
  );
}
