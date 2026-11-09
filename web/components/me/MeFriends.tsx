import Link from "next/link";
import type { CSSProperties } from "react";
import { Avatar, personColor } from "@/components/friends/Friends";
import { Icon, SectionTitle } from "@/components/ui/Kit";
import type { Profile } from "@/lib/social";

/** Friends on Me: their faces in a sideways row (a ring and a count when they bet today), then Add. A face opens the
 *  friend's profile; Feed opens Friends. `requests`: friend requests waiting on you. */
export function MeFriends({ friends, today, requests }: { friends: Profile[]; today: Record<string, number>; requests: number }) {
  return (
    <section>
      <SectionTitle note={requests ? <span className="warn">{requests} request{requests === 1 ? "" : "s"}</span> : friends.length || undefined}
        right={<Link href="/friends" aria-label="Friends feed">Feed</Link>}>Friends</SectionTitle>
      <nav className="me-faces" aria-label="Your friends">
        {friends.map((f) => {
          const n = today[f.user_id] ?? 0;
          return (
            <Link key={f.user_id} href={`/friends/${f.handle}`} className="fx-face" aria-label={`${f.name}${n ? `, ${n} ${n === 1 ? "bet" : "bets"} today` : ""}`}>
              <span className="fx-face-pic" style={{ "--pc": personColor(f.handle) } as CSSProperties}><Avatar p={f} size={52} />{n > 0 && <b className="fx-count">{n}</b>}</span>
              <span className="fx-face-name">{f.name}</span>
            </Link>
          );
        })}
        <Link href="/friends" className="fx-face me-add" aria-label="Add a friend">
          <span className="me-add-pic"><Icon name="plus" /></span>
          <span className="fx-face-name">Add</span>
        </Link>
      </nav>
    </section>
  );
}
