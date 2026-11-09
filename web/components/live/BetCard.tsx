// A bet as My bets shows it (Oct 27: shared with Friends, so a friend's bet looks exactly like your own): the bet, its
// price and money, the live tracker, and its actions. `head` goes above it (a friend's name); `actions` replaces Edit
// and Share (a friend's bet gets Tail instead).
import type { ReactNode } from "react";
import { BetGlow, LiveBet, LiveTop, WithoutTracker } from "@/components/live/LiveBets";
import { MarkButton } from "@/components/live/MarkButton";
import { ShareButton } from "@/components/live/ShareButton";
import { boosted, bookOfBet, isBonus, isSettled, personalClv, profit, stakeOf, startOf, statusOf } from "@/lib/bets";
import type { MyBet } from "@/lib/data";
import { betName } from "@/lib/gameday";
import { dayTime, fmtAm, label, matchupText, MINUS, num, signed, toDec } from "@/lib/format";
import { fmtU } from "@/lib/real";
import { slipEv } from "@/lib/slip";
import { legsOf } from "@/lib/stats";

const units = (u: number | null, d = 2) => (u === null ? "—" : (u >= 0 ? "+" : MINUS) + Math.abs(u).toFixed(d) + "u");
const cls = (x: number | null) => (x === null ? "" : x > 0 ? "pos" : x < 0 ? "neg" : "");

/** What a bet was on, in one line: the bet's own label, or the ticket's title and leg count. */
function what(b: MyBet): string {
  if (b.label) return label(b.label);
  const n = b.legs?.length ?? 0;
  const head = String(b.matchup ?? "").split(":")[0];     // "SGP+ Sun Sep 27 · NFL early window: games…"
  return n ? `${head} · ${n} legs` : head || "Parlay";
}

export function BetCard({ b, fold = false, head, actions }: { b: MyBet; fold?: boolean; head?: ReactNode; actions?: ReactNode }) {
  const s = statusOf(b);
  const settled = isSettled(b);
  const p = profit(b);
  const st = stakeOf(b);
  const clv = personalClv(b);
  // short (Oct 24, from the iPhone): a parlay is "4-leg parlay", a single its bet; the only tags are bonus and boost
  const n = legsOf(b), parlay = n > 1;
  const boost = num(b.boost) ?? 0;
  const price = num(b.price);
  const win = price !== null ? boosted(b, st * (toDec(price) - 1)) : null;
  const when = startOf(b) ? dayTime(startOf(b)) : `marked ${dayTime(b.placed_at)}`;
  return (
    <BetGlow id={b.bet_id} className={settled ? s : ""} win={win}>
      {head}
      <LiveTop id={b.bet_id} compact={fold} />
      <div className="bk-head">
        <div className="bk-what">
          <span className="bk-name">{parlay ? betName({ legs: b.legs }, n) : what(b)}</span>
          {!parlay && b.label && b.matchup && <span className="sub">{matchupText(b.matchup, b.sport ?? b.league)}</span>}
          <span className="sub">{bookOfBet(b)} · {fmtU(st)}{isBonus(b) ? " bonus" : ""}{boost > 0 ? ` · ${boost}% boost` : ""} · {when}</span>
          {(b.ladder_id || b.protect || b.reset) && (
            <span className="bet-tags">
              {b.ladder_id && <span className="tag">ladder</span>}
              {b.protect && <span className="tag">Bet Protect+</span>}
              {b.reset && <span className="tag">bet reset</span>}
            </span>
          )}
        </div>
        <div className="bk-px">
          <span className="numx bk-price">{price !== null ? fmtAm(b.price) : b.fair_price != null ? `fair ${fmtAm(b.fair_price)}` : ""}</span>
          {settled
            ? <span className={`sub ${cls(p)}`}><b>{units(p)}</b></span>
            : win !== null ? <span className="sub pos">wins {fmtU(win)}</span> : null}
        </div>
      </div>
      {(clv !== null || (!settled && b.clv_now != null) || b.slip_p != null || b.live_settled) && (
        <div className="bk-notes sub">
          {clv !== null && <span>CLV <b className={cls(clv)}>{signed(clv)}</b></span>}
          {clv === null && !settled && b.clv_now != null && <span title={`Your price against the sharp chance at ${dayTime(b.clv_at ?? "")} (live CLV; the close decides it)`}>
            CLV now <b className={cls(b.clv_now)}>{signed(b.clv_now)}</b></span>}
          {b.slip_p != null && price !== null && (() => {
            const v = slipEv(Number(b.slip_p), price, b.boost, isBonus(b));
            return <span>Fair {fmtAm(v.fair)} when added · <b className={cls(v.ev)}>{signed(v.ev)}</b> value</span>;
          })()}
          {b.live_settled && <span>{b.live_settled} live · not graded yet</span>}
        </div>
      )}
      <LiveBet id={b.bet_id} collapsed={fold} />
      {(b.legs?.length || !settled || b.mode === "real" || b.label || actions) ? (
        <div className="actions bk-actions">
          {actions ?? <>
            {/* a settled bet keeps Edit (Nov 9: a misread price or stake was wrong for good once graded), never Undo */}
            {(!settled || b.mode === "real") && <MarkButton marked bare settled={settled} mine={b} input={{ kind: b.kind, pick_id: b.pick_id, sgp_id: b.sgp_id }} />}
            <ShareButton id={b.bet_id} />
          </>}
          {b.legs?.length ? (
            <WithoutTracker id={b.bet_id}><details className="more">
              <summary>Legs</summary>
              <ul className="legs more-body">
                {b.legs.map((l, i) => {
                  const r = b.leg_results?.find((x) => x.leg === l);
                  return <li key={`${i}-${l}`}><span>{l}</span><span className={`lp ${r?.result === "won" ? "pos" : r?.result === "lost" ? "neg" : "faint"}`}>
                    {r ? `${r.result}${r.value != null ? ` · ${r.value}` : ""}` : "open"}</span></li>;
                })}
              </ul>
            </details></WithoutTracker>
          ) : null}
        </div>
      ) : null}
    </BetGlow>
  );
}
