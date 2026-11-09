import Link from "next/link";
import { FriendBet, PersonHero } from "@/components/friends/Friends";
import { EndFriend } from "@/components/friends/FriendsUi";
import { LiveProvider } from "@/components/live/LiveBets";
import { PlayerCards } from "@/components/games/PlayerCards";
import { BackLink } from "@/components/ui/BackLink";
import { SectionTitle, SubHead } from "@/components/ui/Kit";
import { achievements } from "@/lib/achievements";
import { record } from "@/lib/bets";
import { friendBets, myBetsData, reactionsFor, socialData } from "@/lib/data";
import { longDay, signed } from "@/lib/format";
import { betKey, circle, PROFILE_RECENT as RECENT, profileBets } from "@/lib/social";
import { streaks } from "@/lib/stats";

export const dynamic = "force-dynamic";

/** A friend's profile (Oct 27; the overhaul's look, Nov 5): who they are with units won as the big number and a record
 *  line, then their open bets (Tail while the game hasn't started), recent settled bets, badges and player cards.
 *  Only for accepted friends; never money. */
export default async function FriendPage({ params }: { params: Promise<{ handle: string }> }) {
  const { handle } = await params;
  const [s, mine] = await Promise.all([socialData(), myBetsData()]);
  if (s.profile?.handle === handle) {
    return <main className="rail friends"><SubHead title="That's you" back="/friends" backLabel="Friends" />
      <div className="card empty"><span>Your own numbers are in <Link href="/more/stats">Me › Stats</Link>.</span></div></main>;
  }
  const p = circle(s.me, s.friendships, s.profiles).friends.find((f) => f.handle === handle);
  if (!p) {
    return <main className="rail friends"><SubHead title="Not friends" back="/friends" backLabel="Friends" />
      <div className="card empty"><span>You see a profile once you&apos;re friends: add them in Friends by their @handle.</span></div></main>;
  }
  // their record counts as their My bets does: real bets once they have any
  // the same open and recent bets /api/live tracks for this profile (social.profileBets)
  const { counted, open, recent } = profileBets(await friendBets(p.user_id).catch(() => []));
  const t = record(counted).total, roi = t.staked ? t.units / t.staked : null;
  const run = streaks(counted), badges = achievements(counted).filter((b) => b.earned);
  const have = new Set(mine.bets.map(betKey));
  const reactions = await reactionsFor([...open, ...recent].map((b) => b.bet_id)).catch(() => []);
  const line = t.bets > 0 ? (
    <>
      {t.won}-{t.lost}{t.push ? `-${t.push}` : ""}
      {roi !== null && <>{" · ROI "}<span className={roi > 0 ? "pos" : roi < 0 ? "neg" : ""}>{signed(roi)}</span></>}
      {run.current.kind && <>{" · "}<span className={run.current.kind === "won" ? "pos" : "neg"}>{run.current.n} {run.current.kind === "won" ? (run.current.n === 1 ? "win" : "wins") : (run.current.n === 1 ? "loss" : "losses")} in a row</span></>}
    </>
  ) : counted.length ? "No settled bets yet" : `No bets shared yet. ${p.name} may have sharing off in Settings.`;
  return (
    <main className="rail friends">
      <BackLink fallback="/friends" label="Friends" />
      <div className="fx-layout profile">
        <div className="fx-top">
          <PersonHero p={p} big units={t.bets > 0 ? t.units : null} line={line} />
        </div>

        <div className="fx-feed">
          <LiveProvider src={`/api/live?friends=${p.user_id}&view=settled`}>
            {open.length > 0 && (
              <section>
                <SectionTitle note={open.length}>Open</SectionTitle>
                <div className="fx-list">{open.map((b) => <FriendBet key={b.bet_id} b={b} who={p} mine={have} showWho={false} reactions={reactions} me={s.me} />)}</div>
              </section>
            )}
            {recent.length > 0 && (
              <section>
                <SectionTitle note={recent.length === RECENT ? `last ${RECENT}` : recent.length}>Recent</SectionTitle>
                <div className="fx-list">{recent.map((b) => <FriendBet key={b.bet_id} b={b} who={p} mine={have} showWho={false} reactions={reactions} me={s.me} />)}</div>
              </section>
            )}
          </LiveProvider>
          {!open.length && !recent.length && counted.length === 0 && (
            <section className="fx-empty">
              <span className="fx-empty-faces" aria-hidden><i /><i /><i /></span>
              <h2>Nothing to show yet</h2>
              <p className="sub">{p.name}&apos;s bets show here once they enter one and share it.</p>
            </section>
          )}
        </div>

        <div className="fx-foot">
          {badges.length > 0 && (
            <section>
              <SectionTitle note={badges.length}>Badges</SectionTitle>
              <div className="fx-badges">
                {badges.map((x) => (
                  <div key={x.id} className="fx-badge" title={x.how}>
                    <span className="fx-badge-icon" aria-hidden>{x.icon}</span>
                    <span><b>{x.title}</b><span className="sub">{x.how}</span><span className="cap">{longDay(x.earned!)}</span></span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {counted.length > 0 && <div className="fx-cards"><PlayerCards bets={counted} whose={p.name} /></div>}

          <div className="fx-end"><EndFriend other={p.user_id} label="Remove friend" /></div>
          <p className="sub fx-note">Units at the price {p.name} took; never money.</p>
        </div>
      </div>
    </main>
  );
}
