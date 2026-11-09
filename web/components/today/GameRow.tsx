import Link from "next/link";
import type { FeedGame } from "@/lib/data";
import type { GameLive } from "@/lib/live";
import { SPORT_SHORT, fmtAm, inOrder, label, matchupText, signed, time } from "@/lib/format";
import { isEarlyLean } from "@/lib/early";
import { Art } from "@/components/ui/Art";

export const gameHref = (gameId: string) => {
  const [league, ...rest] = gameId.split(":");
  return `/games/${league}/${encodeURIComponent(rest.join(":"))}`;
};

const TIER = { pick: "Pick", lean: "Lean", check: "Check" } as const;

/** A game in the feed: both logos, who and when, and its one or two best things to look at. Tap for the game page. */
export function GameRow({ g, art }: { g: FeedGame; art?: GameLive }) {
  const bets = g.offers.filter((o) => o.tier !== "check");
  const sgps = g.tickets.filter((t) => t.kind === "sgp");
  const best = [...sgps].sort((a, b) => (b.p_fair ?? 0) - (a.p_fair ?? 0))[0];
  const started = g.commence_time && new Date(g.commence_time).getTime() <= Date.now();
  const ufc = g.league === "ufc";
  return (
    <Link className="card game-row grow2" href={gameHref(g.game_id)}>
      <div className="gr-top">
        <span className="gr-logos">
          {inOrder(g.league, { s: art?.away, n: g.away ?? g.matchup ?? "" }, { s: art?.home, n: g.home ?? "" }).map(({ s, n }, i) =>
            <Art key={i} src={s?.logo} name={s?.name ?? n} abbr={s?.abbr} color={s?.color} size={28} kind={ufc ? "player" : "team"} />)}
        </span>
        <span className="gr-what"><span className="gr-match">{matchupText(g.matchup, g.league)}</span>
          <span className="sub">{started ? "Live" : time(g.commence_time)} · {SPORT_SHORT[g.league] ?? g.league}</span></span>
        <span className="chev" aria-hidden>›</span>
      </div>
      {(bets.length > 0 || sgps.length > 0) && (
        <div className="gr-items">
          {bets.slice(0, 2).map((o) => (
            <div className="gr-item" key={o.offer_id}>
              <span className={`tag ${o.tier}`}>{TIER[o.tier]}</span>
              {isEarlyLean(o) && <span className="tag warn" title="Game-line leans this far out have lost to the closing line so far">Early</span>}
              <span className="what">{label(o.label)}</span>
              <span className="price">{fmtAm(o.price)}</span>
              <span className={`ev ${(o.ev ?? 0) >= 0 ? "pos" : "neg"}`}>{signed(o.ev)}</span>
            </div>
          ))}
          {bets.length > 2 && <div className="gr-item faint">+{bets.length - 2} more on this game</div>}
          {sgps.length > 0 && (
            <div className="gr-item muted">
              <span className="what">{sgps.length} parlay{sgps.length === 1 ? "" : "s"}{best ? ` · best "${best.body.theme ?? "SGP"}" fair ${fmtAm(best.fair_price)}` : ""}</span>
            </div>
          )}
        </div>
      )}
    </Link>
  );
}
