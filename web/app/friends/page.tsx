import Link from "next/link";
import { Avatar, FriendBet, FriendFaces, PersonHero } from "@/components/friends/Friends";
import { Answer, EndFriend, HeroTools, ProfileForm } from "@/components/friends/FriendsUi";
import { LiveProvider } from "@/components/live/LiveBets";
import { SectionTitle, SubHead } from "@/components/ui/Kit";
import { betsView } from "@/app/bets/load";
import { record } from "@/lib/bets";
import { friendBets, reactionsFor, socialData } from "@/lib/data";
import { longDay } from "@/lib/format";
import { betKey, circle, feed, suggestHandle } from "@/lib/social";
import { addDays, etDay } from "@/lib/time";

export const dynamic = "force-dynamic";

/** Friends (Mike, Oct 27; the overhaul's look, Nov 5): a feed, not a settings list. You first (units won, record, Add a
 *  friend), requests to answer, your friends as faces, then their bets day by day as Live draws a bet, with Tail on
 *  the open ones (W16). From 1000px the feed is the main column and you, requests and friends sit at the right.
 *  Friends see bets in units, never money. */
export default async function FriendsPage() {
  const [s, mine] = await Promise.all([socialData(), betsView()]);
  const c = circle(s.me, s.friendships, s.profiles);
  const bets = c.friends.length ? await friendBets().catch(() => []) : [];
  const items = feed(bets, c.friends);
  const reactions = await reactionsFor(items.map((x) => x.bet.bet_id)).catch(() => []);
  const have = new Set(mine.d.bets.map(betKey));
  const today = etDay(new Date().toISOString()), yesterday = addDays(today, -1);
  const placedToday: Record<string, number> = {};
  for (const b of bets) if (etDay(b.placed_at) === today) placedToday[String(b.user_id)] = (placedToday[String(b.user_id)] ?? 0) + 1;
  const days: { day: string; items: typeof items }[] = [];
  for (const it of items) {
    const day = etDay(it.bet.placed_at);
    if (days.at(-1)?.day === day) days.at(-1)!.items.push(it); else days.push({ day, items: [it] });
  }
  const t = record(mine.counted).total;

  if (!s.profile) {
    return (
      <main className="rail friends">
        <SubHead title="Friends" />
        <section className="card fx-setup">
          <h2>Set up your profile</h2>
          <ProfileForm name="" handle={suggestHandle(s.email)} fresh />
          <p className="sub">Friends see your bets, results and units, never money.</p>
        </section>
      </main>
    );
  }
  return (
    <main className="rail friends">
      <SubHead title="Friends" />
      <div className="fx-layout">
        <div className="fx-top">
          <PersonHero p={s.profile} units={t.bets ? t.units : null}
            line={t.bets ? `${t.won}-${t.lost}${t.push ? `-${t.push}` : ""} ${mine.hasReal ? "on real bets" : "on paper"}` : "No settled bets yet"}>
            <HeroTools name={s.profile.name} handle={s.profile.handle} start={c.friends.length || c.incoming.length || c.outgoing.length ? null : "add"} />
          </PersonHero>

          {c.incoming.length > 0 && (
            <section aria-label="Requests">
              <SectionTitle note={c.incoming.length}>Requests</SectionTitle>
              <div className="fx-requests">
                {c.incoming.map((r) => (
                  <div key={r.otherId} className="fx-request">
                    <div className="fx-person">
                      {r.other && <Avatar p={r.other} size={48} />}
                      <span><b>{r.other?.name ?? "Someone"}</b><span className="sub">{r.other ? `@${r.other.handle} ` : ""}wants to be friends</span></span>
                    </div>
                    <Answer from={r.otherId} />
                  </div>
                ))}
              </div>
            </section>
          )}

          {c.friends.length > 0 && (
            <section aria-label="Your friends">
              <SectionTitle note={c.friends.length}>Your friends</SectionTitle>
              <FriendFaces friends={c.friends} today={placedToday} />
            </section>
          )}
        </div>

        <div className="fx-feed">
          {days.length ? (
            <LiveProvider src="/api/live?friends=all&view=settled">
              {days.map(({ day, items: list }) => (
                <section key={day}>
                  <SectionTitle note={`${list.length} ${list.length === 1 ? "bet" : "bets"}`}>{day === today ? "Today" : day === yesterday ? "Yesterday" : longDay(day)}</SectionTitle>
                  <div className="fx-list">{list.map(({ bet, who }) => <FriendBet key={bet.bet_id} b={bet} who={who} mine={have} reactions={reactions} me={s.me} />)}</div>
                </section>
              ))}
            </LiveProvider>
          ) : (
            <section className="fx-empty">
              <span className="fx-empty-faces" aria-hidden><i /><i /><i /></span>
              <h2>{c.friends.length ? "Nothing in the feed yet" : "Your feed starts with a friend"}</h2>
              <p className="sub">{c.friends.length
                ? "A friend's bet shows here when they enter it: the game, each leg live, and Tail to copy an open one."
                : "Add someone by their exact @handle or email. Once they accept, you see each other's bets in units and can tail an open one."}</p>
              {c.friends.length > 0 && <p className="sub">Nothing from someone? They may have sharing off in their Settings.</p>}
            </section>
          )}
        </div>

        <div className="fx-foot">
          {c.outgoing.length > 0 && (
            <section aria-label="Sent requests">
              <SectionTitle note={c.outgoing.length}>Sent</SectionTitle>
              <div className="card rows">
                {c.outgoing.map((r) => (
                  <div key={r.otherId} className="rowx fx-sent">
                    <div className="fx-person">
                      {r.other && <Avatar p={r.other} size={36} />}
                      <span><b>{r.other?.name ?? "Someone"}</b><span className="sub">waiting for them to accept</span></span>
                    </div>
                    <EndFriend other={r.otherId} label="Cancel" />
                  </div>
                ))}
              </div>
            </section>
          )}
          <p className="sub fx-note">Friends see your bets, results and units, never money. Turn sharing off in <Link href="/more/settings">Settings</Link>.</p>
        </div>
      </div>
    </main>
  );
}
