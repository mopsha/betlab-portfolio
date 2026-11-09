// A game on the Games tab (ported from the iPhone's GameCardRow, Oct 24): both teams with their logos on a soft
// gradient in their colors, a color bar down the left, the start, what there is to act on, the sport, and the chevron
// inside the card ("the color should include the arrow").
import Link from "next/link";
import type { CSSProperties } from "react";
import type { Game } from "@/lib/data";
import type { GameLive, Side } from "@/lib/live";
import { SPORT_SHORT, inOrder, time } from "@/lib/format";
import { gameHref } from "@/components/today/GameRow";

function Team({ s, fallback, ufc }: { s?: Side; fallback: string; ufc: boolean }) {
  return (
    <span className="gc-team">
      {s?.logo
        // eslint-disable-next-line @next/next/no-img-element
        ? <img className={ufc ? "round" : ""} src={s.logo} alt="" width={24} height={24} loading="lazy" />
        : <i className="gc-blank" aria-hidden />}
      <b>{s?.name || fallback}</b>
    </span>
  );
}

/** `linked`: false for a game with no page yet (the calendar lists games weeks ahead): the same card, nothing to open. */
export function GameCard({ g, art, count, linked = true }: { g: Game; art?: GameLive; count?: number; linked?: boolean }) {
  const ufc = g.league === "ufc";
  const style = { "--ca": art?.away.color ?? "transparent", "--ch": art?.home.color ?? "transparent" } as CSSProperties;
  const colored = !!(art?.away.color || art?.home.color);
  const className = `card gcard${colored ? " colored" : ""}${linked ? "" : " nolink"}`;
  const inner = (
    <>
      <span className="gc-teams">
        {(g.home || art ? inOrder(g.league, { s: art?.away, f: g.away ?? g.matchup ?? "" }, { s: art?.home, f: g.home ?? "" })
          : [{ s: undefined, f: g.away ?? g.matchup ?? "" }]).map((x, i) => <Team key={i} s={x.s} fallback={x.f} ufc={ufc} />)}
      </span>
      <span className="gc-side">
        <span className="gc-time">{art?.state === "in" ? <><i className="ldot" /> {art.detail}</> : art?.state === "post" ? "Final" : time(g.commence_time)}</span>
        <span className="gc-tags">{count ? <span className="tag lean">{count}</span> : null}<span className="tag">{SPORT_SHORT[g.league] ?? g.league}</span></span>
      </span>
      {linked && <span className="gc-chev" aria-hidden>›</span>}
    </>
  );
  return linked ? <Link className={className} href={gameHref(g.game_id)} style={style}>{inner}</Link> : <div className={className} style={style}>{inner}</div>;
}
