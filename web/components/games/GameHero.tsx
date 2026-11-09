// A game page's top (the overhaul, Nov 4): both teams' logos large, the score big once it starts (the start time
// before), the clock as a pill, each team's color as a soft light behind its side, and the chance to win as a bar
// where the page has one. Drawn on the server from the game's ESPN entry (lib/art.ts).
import type { CSSProperties, ReactNode } from "react";
import type { GameLive, Side } from "@/lib/live";
import { Art } from "@/components/ui/Art";
import { Glow, LivePill } from "@/components/ui/Kit";
import { CardTap } from "@/components/games/Cards";
import { inOrder } from "@/lib/format";

function Team({ s, g }: { s: Side; g: GameLive }) {
  const ufc = g.sport === "ufc";
  return (
    <div className="gh-team">
      <CardTap card={ufc ? null : { kind: "team", name: s.name, abbr: s.abbr }} sport={g.sport}>
        <Art src={s.logo} name={s.name} abbr={s.abbr} color={s.color} size={64} kind={ufc ? "player" : "team"} alt={s.name} />
      </CardTap>
      <span className="gh-name">{s.name}</span>
    </div>
  );
}

export type WinChance = { away: number; home: number; label: string };

export function GameHero({ g, title, when, chance, children }: { g?: GameLive; title: string; when: string; chance?: WinChance | null; children?: ReactNode }) {
  if (!g) return (
    <Glow className="ghero" as="section">
      <div className="gh-plain"><h1>{title}</h1><span className="sub">{when}</span></div>
      {children}
    </Glow>
  );
  const started = g.state !== "pre", ufc = g.sport === "ufc";
  // soccer reads home team first (Nov 5): its side, score and chance go first; the rest away first
  const [first, second] = inOrder(g.sport, g.away, g.home);
  const a = first.score ?? 0, h = second.score ?? 0;
  const raw = chance && chance.away + chance.home > 0 ? chance : null;
  const bar = raw && first === g.home ? { ...raw, away: raw.home, home: raw.away } : raw;
  return (
    <Glow className="ghero" as="section" colors={[first.color, second.color]}>
      <h1 className="sr-only">{title}</h1>
      <div className="gh-row">
        <Team s={first} g={g} />
        <div className="gh-mid">
          {started && <LivePill state={g.state} detail={g.detail} start={g.start} note={g.redZone ? "Red zone" : null} />}
          {started && !ufc
            ? <div className="gh-score"><span className={`score-num${a < h ? " trail" : ""}`}>{a}</span><span className={`score-num${h < a ? " trail" : ""}`}>{h}</span></div>
            : <span className="gh-when">{ufc && started ? g.detail : when}</span>}
          {g.state === "in" && g.down && <span className="sub">{g.down}</span>}
        </div>
        <Team s={second} g={g} />
      </div>
      {bar && (
        <div className="gh-chance">
          <div className="gh-bar" role="img" aria-label={`${bar.label}: ${first.name} ${Math.round(bar.away * 100)}%, ${second.name} ${Math.round(bar.home * 100)}%`}>
            <span style={{ flexGrow: Math.max(bar.away, 0.02), background: first.color ?? "var(--ink-3)" } as CSSProperties} />
            <span style={{ flexGrow: Math.max(bar.home, 0.02), background: second.color ?? "var(--accent)" } as CSSProperties} />
          </div>
          <div className="gh-pcts"><span className={bar.away >= bar.home ? "lead" : ""}>{Math.round(bar.away * 100)}%</span><span>{bar.label}</span>
            <span className={bar.home > bar.away ? "lead" : ""}>{Math.round(bar.home * 100)}%</span></div>
        </div>
      )}
      {children}
    </Glow>
  );
}
