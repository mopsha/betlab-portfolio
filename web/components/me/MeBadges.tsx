import Link from "next/link";
import { SectionTitle } from "@/components/ui/Kit";
import type { Badge } from "@/lib/achievements";
import { badgeRow } from "@/lib/me-view";

/** Badges on Me: the ones earned in a sideways row, newest first, with a couple still locked dimmed at the end. Each
 *  shows its own art (lib/achievements.ts); the whole list is on Stats. */
export function MeBadges({ badges }: { badges: Badge[] }) {
  const got = badges.filter((b) => b.earned).length;
  return (
    <section>
      <SectionTitle note={`${got} of ${badges.length}`} right={<Link href="/more/stats#badges" aria-label="All badges">All</Link>}>Badges</SectionTitle>
      <ul className="me-badges" aria-label="Badges">
        {badgeRow(badges).map((b) => (
          <li key={b.id} className={`me-badge${b.earned ? "" : " off"}`} title={`${b.title}: ${b.how}`}>
            <span aria-hidden>{b.icon}</span>
            <span className="sr-only">{b.title}{b.earned ? "" : b.progress ? `, locked: ${b.progress.have} of ${b.progress.need}` : ", locked"}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
