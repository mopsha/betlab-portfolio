import Link from "next/link";
import { RecordTable } from "@/components/me/RecordTable";
import { RecordSwitch } from "@/components/me/RecordSwitch";
import { SectionTitle } from "@/components/ui/Kit";
import { bonusSummary, boostSummary, bookOfBet, promoLedger, record } from "@/lib/bets";
import { expiringSoon, expiresText, promoTitle } from "@/lib/promos";
import { fmtU, realStart } from "@/lib/real";
import { missedBets } from "@/lib/missed";
import { isBanned } from "@/lib/bans";
import { allPicks, promosData, unitOf } from "@/lib/data";
import { fmtAm, MINUS, num, signed } from "@/lib/format";
import { betsView } from "@/app/bets/load";

const units = (u: number | null, d = 2) => (u === null ? "—" : (u >= 0 ? "+" : MINUS) + Math.abs(u).toFixed(d) + "u");
const cls = (x: number | null) => (x === null ? "" : x > 0 ? "pos" : x < 0 ? "neg" : "");

/** Me › Record (in My bets until the overhaul, Nov 4): the record by market and by book, missed bets, what promos
 *  earned, and the paper record apart. */
export default async function Record() {
  const [{ d, hasReal, counted, paper }, wallet, picks] = await Promise.all([betsView(), promosData().catch(() => []), allPicks().catch(() => [])]);
  const settings = d.settings;
  const missed = missedBets(picks.filter((p) => !isBanned(settings.bans ?? [], p.label ?? "", p.league)),
    d.bets.flatMap((b) => (b.pick_id ? [b.pick_id] : [])), realStart(settings.real_from));
  const { lines, total } = record(counted);
  const byBook = record(counted, bookOfBet);   // FanDuel and DraftKings side by side (Oct 12)
  const paperRec = record(paper);
  const bonus = bonusSummary(counted);
  const boosted = boostSummary(counted);
  const finder = promoLedger(counted, unitOf(settings));
  const soon = expiringSoon(wallet);
  return (
    <main className="rail">
      <RecordSwitch on="record" />
      {hasReal && <SectionTitle>Real money</SectionTitle>}
      {total.bets ? <div className="card" style={{ padding: "6px 6px 2px" }}><RecordTable lines={lines} total={total} /></div> : hasReal ? (
        <div className="card empty"><span>No real bet graded yet. Results land the morning after each game.</span></div>
      ) : (
        <div className="card empty"><b>No record yet</b><span>Your record starts with your first graded bet.</span></div>
      )}
      {missed.picks.length > 0 && (
        <>
          <SectionTitle>Missed bets</SectionTitle>
          <div className="card" style={{ padding: "12px 14px" }}>
            <p>You skipped <b>{missed.picks.length}</b> pick{missed.picks.length === 1 ? "" : "s"}: {missed.won}-{missed.lost}{missed.push ? `-${missed.push}` : ""},{" "}
              <b className={cls(missed.units)}>{units(missed.units)}</b> at 1u each{missed.clv !== null ? <> · CLV <b>{signed(missed.clv)}</b></> : null}.</p>
            {missed.tookN > 0 && <p className="faint">The {missed.tookN} you took: {units(missed.tookUnits)} at 1u each.</p>}
            <details>
              <summary className="faint">See them</summary>
              {missed.picks.slice(0, 50).map((p) => (
                <p key={p.pick_id} style={{ margin: "8px 0 0" }}><b>{p.label}</b> {fmtAm(p.price)}{" · "}
                  <span className={cls(num(p.profit_flat))}>{p.status === "push" ? "push" : units(num(p.profit_flat))}</span>
                  <br /><span className="faint">{p.matchup} · {new Date(p.commence_time!).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" })}</span></p>
              ))}
            </details>
          </div>
        </>
      )}
      {(bonus.bets > 0 || boosted.bets > 0 || soon.length > 0) && (
        <>
          <SectionTitle right={<Link href="/more/promos">Wallet ›</Link>}>Promos</SectionTitle>
          <div className="card promo-ledger">
            {bonus.bets > 0 && <p><b>Bonus bets</b> {bonus.settled} settled{bonus.bets > bonus.settled ? `, ${bonus.bets - bonus.settled} open` : ""}: {fmtU(bonus.face)} of
              bonus turned into <b className={cls(bonus.converted)}>{units(bonus.converted)}</b>
              {bonus.rate !== null && <> · kept <b>{Math.round(bonus.rate * 100)}%</b></>}</p>}
            {boosted.bets > 0 && <p><b>Profit boosts</b> {boosted.settled} settled{boosted.bets > boosted.settled ? `, ${boosted.bets - boosted.settled} open` : ""}, {boosted.won} won:
              {" "}<b className={cls(boosted.units)}>{units(boosted.units)}</b> on {fmtU(boosted.staked)} staked; the boosts added
              {" "}<b className={cls(boosted.fromBoost)}>{units(boosted.fromBoost)}</b></p>}
            {finder.settled > 0 && <p><b>From the finder</b> {finder.settled} settled: <b className={cls(finder.units)}>{units(finder.units)}</b>
              {" "}against <b>{units(finder.expected)}</b> expected{finder.placed > finder.settled ? ` (${finder.placed - finder.settled} open)` : ""}</p>}
            {soon.length > 0 && <p><b>Expiring soon</b> {soon.map((p) => `${promoTitle(p)}${p.book ? ` (${p.book})` : ""} ${expiresText(p)}`).join(" · ")}
              {" "}<Link href="/build/promo">Use one ›</Link></p>}
            <p className="faint">All included in your units won; bonus stakes never count in staked units or ROI. A bonus bet pays only its profit,
              so a fair +400 keeps about 80% of its face and a -110 favorite about 45%; a boost is worth most on a bet priced near the sharp fair price.</p>
          </div>
        </>
      )}
      {byBook.total.bets > 0 && (
        <>
          <SectionTitle>By book{hasReal ? " · real money" : ""}</SectionTitle>
          <div className="card" style={{ padding: "6px 6px 2px" }}><RecordTable head="Book" lines={byBook.lines} total={byBook.total} /></div>
        </>
      )}
      {hasReal && paperRec.total.bets > 0 && (
        <>
          <SectionTitle>Paper</SectionTitle>
          <div className="card" style={{ padding: "6px 6px 2px" }}><RecordTable lines={paperRec.lines} total={paperRec.total} /></div>
        </>
      )}
      <details className="more" style={{ marginTop: 12 }}>
        <summary>About these numbers</summary>
        <div className="more-body">
          <p>Units are at the price you marked: a 1u bet at +120 that wins is +1.20u. A real bet counts its stake in units (1u unless you edit it); paper bets count 1u. Real money and paper are kept apart.</p>
          <p>A bonus bet (tick Bonus bet under Edit) is the book&apos;s credit: a win adds only its profit, a loss counts 0, and it
            stays out of today&apos;s 5u cap, the fun bucket and ROI.</p>
          <p>CLV is how your price compares with the sharp closing price, the best sign a bet was good whatever the result. Beating the close
            on most bets matters more than the win-loss record over a few weeks. Parlays have no CLV.</p>
          <p>The model&apos;s own paper record (every pick, whether you marked it or not) is under Me › Model and markets.</p>
        </div>
      </details>
    </main>
  );
}
