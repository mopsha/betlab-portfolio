import type { Bet, Offer } from "@/lib/data";
import { dayTime, fmtAm, label, marketName, matchupText, pct, signed, sportName, toAm } from "@/lib/format";
import { isEarlyLean } from "@/lib/early";
import { BookLink } from "@/components/ui/BookLink";
import { MarkButton } from "@/components/live/MarkButton";
import { Art, ArtStack, type ArtOf } from "@/components/ui/Art";
import { Glow } from "@/components/ui/Kit";

const TIER_NAME = { pick: "Pick", lean: "Lean", check: "Check the news" } as const;

/** One bet: whose it is (the player's photo or the team's logo, its color as a soft light), what, price, three numbers,
 *  the actions; the reasoning one tap away. `pair`: both teams, for a total. */
export function BetRow({ o, mine, showGame = true, art, pair }: { o: Offer; mine?: Bet; showGame?: boolean; art?: ArtOf | null; pair?: ArtOf[] }) {
  return (
    <Glow as="article" className="bet" colors={[art?.color ?? pair?.[0]?.color]}>
      <div className="bet-top">
        {art ? <Art {...art} size={48} /> : pair?.length ? <ArtStack items={pair} size={36} /> : null}
        <div className="bet-what">
          <span className="bet-label">{label(o.label)}</span>
          {showGame && <span className="bet-game">{matchupText(o.matchup, o.league)} · {dayTime(o.commence_time)}</span>}
          <span className="bet-game">{sportName(o.league)} · {marketName(o.market)}</span>
          <span className="bet-tags">
            <span className={`tag ${o.tier}`}>{TIER_NAME[o.tier]}</span>
            {isEarlyLean(o) && <span className="tag warn" title="Game-line leans this far out have lost to the closing line so far">Early · unproven</span>}
          </span>
        </div>
        <div className="bet-px">
          <span className="bet-price">{fmtAm(o.price)}</span>
          <span className="bet-book">{o.book ?? "FanDuel"}</span>
        </div>
      </div>
      {o.tier !== "check" && (
        <div className="cells">
          <div><small>Chance</small><b>{pct(o.p_final, 1)}</b></div>
          <div><small>Fair price</small><b>{o.p_final ? fmtAm(Math.round(toAm(1 / o.p_final))) : "—"}</b></div>
          <div><small>Edge</small><b className={(o.ev ?? 0) >= 0 ? "pos" : "neg"}>{signed(o.ev)}</b></div>
        </div>
      )}
      {/* the book's bet limit, and the other book's price when it posts the bet (DraftKings, Oct 12) */}
      {(o.bet_limit != null || (o.other_book && o.other_price != null)) && (
        <span className="bet-game">
          {o.bet_limit != null ? <>${Math.round(o.bet_limit).toLocaleString()} available</> : null}
          {o.bet_limit != null && o.other_book && o.other_price != null ? " · " : null}
          {o.other_book && o.other_price != null
            ? <>{o.other_book} {o.other_point != null && o.other_point !== o.point ? `${o.market === "spreads" && o.other_point > 0 ? "+" : ""}${o.other_point} ` : ""}{fmtAm(o.other_price)}</> : null}
        </span>
      )}
      <div className="actions">
        {o.tier !== "check" && (
          <MarkButton marked={!!mine} mine={mine}
            input={{ kind: o.tier === "pick" ? "pick" : "lean", pick_id: o.offer_id, price: o.price, label: o.label, matchup: o.matchup,
                     book: o.book ?? "FanDuel" }} />
        )}
        {o.tier !== "check" && <BookLink book={o.book} links={[o.fd_url]} icon />}
        <details className="more">
          <summary>{o.tier === "check" ? "Model vs. market" : "Why"}</summary>
          <div className="more-body">
            {isEarlyLean(o) && <p>Early lean: game-line leans more than 36 hours before the start have closed against us so far
              (weekly review #3), while late ones beat the close. Worth waiting for the news.</p>}
            {o.context && <p>{o.context}</p>}
            {o.why && <p>{o.why}</p>}
            <p className="note">
              Market {pct(o.p_market, 1)} · our model {pct(o.p_model, 1)} · stake {o.units_flat ?? 1}u (tiers {o.units_tier ?? "—"}u,
              ¼-Kelly {o.units_kelly ?? "—"}u){o.market_source ? ` · ${o.market_source}` : ""}
            </p>
          </div>
        </details>
      </div>
    </Glow>
  );
}
