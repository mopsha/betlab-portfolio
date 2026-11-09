// Friends (Oct 27; the overhaul's look, Nov 5): a person's avatar, the hero that leads Friends and a profile, the row
// of friends' faces, and a friend's bet as the feed and profiles show it: Live's own card (the tracker, ring legs,
// units) headed by who placed it, with Tail as its main button while it's open.
import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";
import { bookOfBet, isSettled } from "@/lib/bets";
import type { MyBet } from "@/lib/data";
import { MINUS, time } from "@/lib/format";
import { betKey, canTail, hue, type Profile, type Reaction } from "@/lib/social";
import { BetCard } from "@/components/live/BetCard";
import { Glow } from "@/components/ui/Kit";
import { TailButton } from "@/components/friends/FriendsUi";
import { ReactButton, RxHost } from "@/components/friends/Reactions";

type Person = Pick<Profile, "name" | "handle">;

/** A person's steady color (from their handle): their avatar, and the glow behind their hero. */
export const personColor = (handle: string) => `hsl(${hue(handle)} 55% 45%)`;

export function Avatar({ p, size = 36 }: { p: Person; size?: number }) {
  return (
    <span className="fr-avatar" aria-hidden style={{ width: size, height: size, fontSize: size * 0.42, background: personColor(p.handle) }}>
      {p.name.trim()[0]?.toUpperCase() ?? "?"}
    </span>
  );
}

const unitsText = (u: number) => (u >= 0 ? "+" : MINUS) + Math.abs(u).toFixed(1) + "u";

/** Who someone is and how they're doing: avatar, name and @handle, units won as the big number, a record line. The
 *  glow is the person's own color. `children`: the buttons under it. */
export function PersonHero({ p, units, line, big = false, children }:
  { p: Person; units: number | null; line?: ReactNode; big?: boolean; children?: ReactNode }) {
  return (
    <Glow as="section" colors={[personColor(p.handle)]} className={`fx-hero${big ? " big" : ""}`}>
      <div className="fx-hero-top">
        <Avatar p={p} size={big ? 72 : 56} />
        <div className="fx-hero-who">
          {big ? <h1>{p.name}</h1> : <b>{p.name}</b>}
          <span className="sub">@{p.handle}</span>
        </div>
        {units !== null && (
          <div className="fx-hero-num">
            <span className={`hero-num ${units > 0.004 ? "pos" : units < -0.004 ? "neg" : ""}`}>{unitsText(units)}</span>
            <span className="cap">units won</span>
          </div>
        )}
      </div>
      {line && <p className="sub fx-hero-line">{line}</p>}
      {children}
    </Glow>
  );
}

/** Your friends as faces in a sideways row, each with how many bets they placed today; a tap opens the profile. */
export function FriendFaces({ friends, today }: { friends: Profile[]; today: Record<string, number> }) {
  return (
    <nav className="fx-faces" aria-label="Your friends">
      {friends.map((f) => {
        const n = today[f.user_id] ?? 0;
        return (
          <Link key={f.user_id} href={`/friends/${f.handle}`} className="fx-face" aria-label={`${f.name}${n ? `, ${n} ${n === 1 ? "bet" : "bets"} today` : ""}`}>
            <span className="fx-face-pic" style={{ "--pc": personColor(f.handle) } as CSSProperties}><Avatar p={f} size={56} />{n > 0 && <b className="fx-count">{n}</b>}</span>
            <span className="fx-face-name">{f.name}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/** A friend's bet as Live shows a bet (the same card and tracker; Mike, Oct 27: "the cards should look like the my
 *  bets screen"), headed by who placed it and when, with Tail while it's still open. A settled one folds its legs.
 *  Wrap a list in <LiveProvider src="/api/live?friends=...">: the tracker reads friends' bets from there. */
export function FriendBet({ b, who, mine, showWho = true, reactions, me }: { b: MyBet; who: Profile; mine: Set<string>; showWho?: boolean;
  reactions?: Reaction[]; me?: string }) {
  const head = showWho ? (
    <Link href={`/friends/${who.handle}`} className="fx-by">
      <Avatar p={who} size={36} />
      <span><b>{who.name}</b><span className="sub">{time(b.placed_at)}</span></span>
    </Link>
  ) : null;
  const tail = canTail(b) ? <TailButton betId={b.bet_id} price={b.price} book={bookOfBet(b)} mine={mine.has(betKey(b))} /> : null;
  if (!reactions || !me) return <div className="fx-bet"><BetCard b={b} head={head} actions={tail ?? <></>} fold={isSettled(b)} /></div>;
  return (
    <RxHost betId={b.bet_id} list={reactions.filter((r) => r.bet_id === b.bet_id)} me={me} canReact>
      <div className="fx-bet"><BetCard b={b} head={head} actions={<>{tail}<ReactButton /></>} fold={isSettled(b)} /></div>
    </RxHost>
  );
}
