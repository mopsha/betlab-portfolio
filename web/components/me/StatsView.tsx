// My bets > Stats (Oct 24): personal stats (Mike's #40) and achievements (W29), from the same bets as the Record tab.
import Link from "next/link";
import { achievements, GROUPS, nextUp, type Badge } from "@/lib/achievements";
import { profit, stakeOf, statusOf } from "@/lib/bets";
import type { MyBet } from "@/lib/data";
import { dayTime, fmtAm, label, longDay, signed } from "@/lib/format";
import { betName } from "@/lib/gameday";
import { legsOf, stats } from "@/lib/stats";
import { periodName, periods } from "@/lib/wrapped";
import { PlayerCards } from "@/components/games/PlayerCards";
import { RecordTable, cls, units } from "@/components/me/RecordTable";

/** Cumulative units by day as a line, zero marked; the last point labeled. */
function UnitsChart({ points }: { points: { day: string; units: number }[] }) {
  if (points.length < 2) return <p className="faint">The chart starts after a second day with a settled bet.</p>;
  const W = 640, H = 180, P = 8;
  const ys = [0, ...points.map((p) => p.units)], lo = Math.min(...ys), hi = Math.max(...ys), span = hi - lo || 1;
  const x = (i: number) => P + (i / (points.length - 1)) * (W - 2 * P);
  const y = (u: number) => P + (1 - (u - lo) / span) * (H - 2 * P);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.units).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  return (
    <figure className="st-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Units over time: ${units(last.units)} after ${points.length} days`}>
        <line x1={P} x2={W - P} y1={y(0)} y2={y(0)} className="st-zero" />
        <path d={`${d} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`} className={`st-area ${last.units >= 0 ? "up" : "down"}`} />
        <path d={d} className={`st-line ${last.units >= 0 ? "up" : "down"}`} />
        <circle cx={x(points.length - 1)} cy={y(last.units)} r={4} className={`st-dot ${last.units >= 0 ? "up" : "down"}`} />
      </svg>
      <figcaption className="faint">{longDay(points[0].day)} to {longDay(last.day)} · now <b className={cls(last.units)}>{units(last.units)}</b></figcaption>
    </figure>
  );
}

/** One badge: earned (when, and the price that did it), or locked with its progress. */
function BadgeTile({ b }: { b: Badge }) {
  return (
    <div className={`badge${b.earned ? " got" : ""}`} title={b.how}>
      <span className="badge-icon" aria-hidden>{b.icon}</span>
      <b>{b.title}</b>
      <span className="faint">{b.how}</span>
      {b.earned ? <span className="badge-when">{longDay(b.earned)}{b.by && statusOf(b.by) === "won" && b.by.price != null ? ` · ${fmtAm(b.by.price)}` : ""}</span>
        : b.progress ? <span className="badge-when faint">{b.progress.have} of {b.progress.need}</span> : <span className="badge-when faint">Locked</span>}
    </div>
  );
}

function OneBet({ b, head }: { b: MyBet; head: string }) {
  const p = profit(b);
  return (
    <div className="st-one">
      <span className="faint">{head}</span>
      <b>{b.kind === "custom" || b.kind === "parlay" ? `${betName({ legs: b.legs }, legsOf(b))} · ${String(b.matchup ?? "").split(":")[0]}`
        : b.label ? label(b.label) : String(b.matchup ?? "").split(":")[0]}</b>
      <span className="faint">{fmtAm(b.price)} · {stakeOf(b)}u · {dayTime(b.placed_at)}</span>
      <b className={cls(p)}>{units(p)}</b>
    </div>
  );
}

export function StatsView({ bets, real }: { bets: MyBet[]; real: boolean }) {
  const s = stats(bets);
  const badges = achievements(bets);
  const got = badges.filter((b) => b.earned).length;
  const next = nextUp(badges);
  const roi = s.total.staked ? s.total.units / s.total.staked : null;
  const cur = s.streaks.current;
  if (!s.total.bets) return <div className="card empty"><b>No stats yet</b><span>Stats start with your first graded {real ? "real " : ""}bet.</span></div>;
  const table = (title: string, head: string, lines: typeof s.bySport) => lines.length > 0 && (
    <>
      <h2 className="section-label">{title}</h2>
      <div className="card" style={{ padding: "6px 6px 2px" }}><RecordTable head={head} lines={lines} total={s.total} /></div>
    </>
  );
  const month = periods(bets)[0];
  return (
    <>
      {month && (
        <Link href="/wrapped" className="card st-wrapped">
          <span><b>Your {periodName(month)} Wrapped</b><span className="faint">Your month as a story: the big hit, the heartbreaker, your type</span></span>
          <span aria-hidden>›</span>
        </Link>
      )}
      <div className="strip">
        <span className="stat-pill">{real ? "Real P/L" : "Units"} <b className={cls(s.total.units)}>{units(s.total.units)}</b></span>
        <span className="stat-pill">ROI <b className={cls(roi)}>{signed(roi)}</b></span>
        {cur.kind && <span className="stat-pill">Streak <b className={cur.kind === "won" ? "pos" : "neg"}>{cur.n}{cur.kind === "won" ? "W" : "L"}</b></span>}
        <span className="stat-pill">Best run <b>{s.streaks.bestWin}W</b></span>
        <span className="stat-pill">Badges <b>{got}</b> of {badges.length}</span>
      </div>

      <h2 className="section-label">Units over time</h2>
      <div className="card" style={{ padding: "12px" }}><UnitsChart points={s.timeline} /></div>

      {(s.extremes.best || s.extremes.worst) && (
        <div className="st-pair">
          {s.extremes.best && <OneBet b={s.extremes.best} head="Biggest win" />}
          {s.extremes.worst && <OneBet b={s.extremes.worst} head="Worst loss" />}
        </div>
      )}

      <PlayerCards bets={bets} />

      {table("By sport", "Sport", s.bySport)}
      {table("Singles vs parlays", "Type", s.byType)}
      {table("By price", "Price", s.byBand)}
      {table("Cash, boosts and bonus bets", "Money", s.byMoney)}
      {table("By book", "Book", s.byBook)}
      {table("By day of the week", "Day", s.byWeekday)}

      <h2 className="section-label">Achievements · {got} of {badges.length}</h2>
      {got > 0 && <div className="badges">{badges.filter((b) => b.earned).map((b) => <BadgeTile key={b.id} b={b} />)}</div>}
      {next.length > 0 && <>
        <h3 className="section-label">Next up</h3>
        <div className="badges">{next.map((b) => <BadgeTile key={b.id} b={b} />)}</div>
      </>}
      <details className="more" style={{ marginTop: 10 }}>
        <summary>All {badges.length} badges, by kind</summary>
        <div className="more-body">
          {GROUPS.map((g) => {
            const list = badges.filter((b) => b.group === g);
            return (
              <section key={g}>
                <h3 className="section-label">{g} · {list.filter((b) => b.earned).length} of {list.length}</h3>
                <div className="badges">{list.map((b) => <BadgeTile key={b.id} b={b} />)}</div>
              </section>
            );
          })}
        </div>
      </details>
      <p className="faint" style={{ marginTop: 10 }}>Units are at the price you took; ROI is on cash staked (bonus bets add profit, never stake). Badges reward
        winning and beating the close, never betting more.</p>
    </>
  );
}
