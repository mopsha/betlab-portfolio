import { cookies } from "next/headers";
import { BackLink } from "@/components/ui/BackLink";
import { Avatar } from "@/components/friends/Friends";
import { ShareRow, SignOutRow } from "@/components/me/SettingsRows";
import { SetGroup, SetRow, TINT } from "@/components/me/SettingsKit";
import { BookMark } from "@/components/promos/Token";
import { deviceSessions, settingsData, socialData } from "@/lib/data";
import { onBooks } from "@/lib/books";
import { FONTS, THEMES } from "@/lib/looks";
import { fixtureMode } from "@/lib/mode";
import { supabaseServer } from "@/lib/supabase/server";
import { UNIT_DEFAULT } from "@/lib/real";

const n = (k: number, one: string) => `${k} ${one}${k === 1 ? "" : "s"}`;
const clock = (t: string) => { const [h, m] = t.split(":").map(Number); return `${h % 12 || 12}${m ? `:${String(m).padStart(2, "0")}` : ""} ${h < 12 ? "AM" : "PM"}`; };

/** Me > Settings (reorganized Nov 6; Mike: "it's pretty ah rn"): who you are, then short rows like the iPhone's own
 *  Settings, each with what it's set to and a screen of its own (books, money, bans, alerts, devices, look, links). */
export default async function SettingsPage() {
  const [s, jar, sessions, social] = await Promise.all([settingsData(), cookies(), deviceSessions().catch(() => []), socialData().catch(() => null)]);
  const email = fixtureMode() ? null : (await (await supabaseServer()).auth.getUser()).data.user?.email ?? null;
  const theme = THEMES.find((t) => t.id === (jar.get("theme")?.value ?? "system")) ?? THEMES[0];
  const font = FONTS.find((f) => f.id === (jar.get("font")?.value ?? "classic")) ?? FONTS[0];
  const on = onBooks(s.books_off);
  const bans = s.bans ?? [], players = bans.filter((b) => b.kind === "player").length, teams = bans.length - players;
  const nt = s.notify ?? {};
  const sends = [nt.picks !== false && "Picks", nt.leans === true && "leans", nt.locks !== false && "locks", nt.legs !== false && "legs"].filter(Boolean) as string[];
  const me = social?.profile ?? null;
  return (
    <main className="rail stg">
      <BackLink fallback="/more" label="Me" />
      <div className="head"><h1>Settings</h1></div>

      <a className="st-me" href="/friends">
        {me ? <Avatar p={me} size={56} /> : <span className="fr-avatar" style={{ width: 56, height: 56, fontSize: 24, background: "var(--sunk)" }} aria-hidden>?</span>}
        <span><b>{me?.name ?? "You"}</b><span>{[me && `@${me.handle}`, email ?? (fixtureMode() ? "Local preview" : null)].filter(Boolean).join(" · ")}</span></span>
      </a>

      <SetGroup title="Betting">
        <SetRow href="/more/settings/books" icon="books" tint={TINT.books} title="Your books"
          value={<span className="st-books">{on.map((b) => <BookMark key={b} book={b} size={24} />)}</span>} />
        <SetRow href="/more/settings/money" icon="money" tint={TINT.money} title="Units and money"
          value={`$${s.unit_dollars ?? UNIT_DEFAULT} a unit`} />
        <SetRow href="/more/settings/bans" icon="ban" tint={TINT.ban} title="Ban list"
          value={bans.length ? [players && n(players, "player"), teams && n(teams, "team")].filter(Boolean).join(", ") : "Nobody"} />
      </SetGroup>

      <SetGroup title="Alerts">
        <SetRow href="/more/settings/alerts" icon="bell" tint={TINT.bell} title="Notifications"
          value={nt.quiet ? `Quiet ${clock(nt.quiet.from)}–${clock(nt.quiet.to)}` : sends.length ? sends.join(", ") : "Off"} />
      </SetGroup>

      <SetGroup title="Friends and privacy">
        <ShareRow on={s.share_bets !== false} />
        <SetRow href="/more/settings/devices" icon="devices" tint={TINT.devices} title="Signed-in devices"
          value={sessions.length ? `${sessions.length}` : undefined} />
      </SetGroup>

      <SetGroup title="Look">
        <SetRow href="/more/settings/look" icon="look" tint={TINT.look} title="Theme and font" value={`${theme.label} · ${font.label}`} />
      </SetGroup>

      <SetGroup title="Help">
        <SetRow href="/more/settings/links" icon="link" tint={TINT.link} title="Test the Open in links" />
      </SetGroup>

      <SignOutRow preview={fixtureMode()} />
    </main>
  );
}
