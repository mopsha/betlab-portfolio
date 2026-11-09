import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { modelData, type Golive, type PaperPick } from "@/lib/data";
import { dayTime, fmtAm, label, MINUS, pct, scoreName, signed, SPORT_SHORT } from "@/lib/format";

const STATUS: Record<string, [string, string]> = { pass: ["strong", "won"], failing: ["weak spot", "lost"], "not yet": ["building", ""] };
const SHOW = [["all", "All"], ["won", "Won"], ["lost", "Lost"], ["open", "Open"], ["mine", "Yours"]] as const;
const settledOf = (p: PaperPick) => ["won", "lost", "push"].includes(String(p.status));
const fmtU = (v: number | null | undefined) => (v == null ? "—" : signed(v, 2, "u", 1));
const fmtClv = (v: number | null | undefined) => (v == null ? "—" : signed(v));
const clvOf = (p: PaperPick) => p.clv_raw ?? p.clv;

/** Cumulative units won (solid) against what closing line value says we should have won (dashed). */
function Chart({ picks }: { picks: PaperPick[] }) {
  let won = 0, exp = 0;
  const pts = picks.map((p, i) => { won += Number(p.profit_flat) || 0; exp += (Number(clvOf(p)) || 0) * (Number(p.units_flat) || 1); return { i: i + 1, won, exp }; });
  const W = 640, H = 200, L = 44, R = 12, T = 12, B = 26;
  const ys = pts.flatMap((p) => [p.won, p.exp]).concat(0);
  let lo = Math.min(...ys), hi = Math.max(...ys);
  const span = Math.max(hi - lo, 2), step = span <= 6 ? 1 : span <= 15 ? 2 : span <= 40 ? 5 : 10;
  lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
  const X = (i: number) => L + ((i - 1) / Math.max(pts.length - 1, 1)) * (W - L - R);
  const Y = (v: number) => T + ((hi - v) / (hi - lo || 1)) * (H - T - B);
  const grid = [];
  for (let v = lo; v <= hi + 1e-9; v += step) grid.push(v);
  const path = (k: "won" | "exp") => pts.map((p, j) => `${j ? "L" : "M"}${X(p.i).toFixed(1)},${Y(p[k]).toFixed(1)}`).join("");
  const last = pts[pts.length - 1];
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Units won versus units closing line value predicts">
      {grid.map((v) => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="var(--line)" strokeWidth={v === 0 ? 1.5 : 1} />
          <text x={L - 8} y={Y(v) + 4} textAnchor="end">{v > 0 ? "+" : v < 0 ? MINUS : ""}{Math.abs(v)}u</text>
        </g>
      ))}
      <path d={path("exp")} fill="none" stroke="var(--accent)" strokeWidth={2} strokeDasharray="5 4" />
      <path d={path("won")} fill="none" stroke="var(--ink)" strokeWidth={2} />
      <circle cx={X(last.i)} cy={Y(last.won)} r={4} fill="var(--ink)" />
      <text x={L} y={H - 6}>pick 1</text>
      <text x={W - R} y={H - 6} textAnchor="end">pick {pts.length}</text>
    </svg>
  );
}

function Scorecard({ g }: { g: Golive }) {
  const r = g.rules;
  const markets = [...g.markets].sort((a, b) => b.picks.with_clv - a.picks.with_clv || b.leans.with_clv - a.leans.with_clv || a.market.localeCompare(b.market));
  return (
    <div className="feed">
      {markets.map((m) => {
        const [word, cls] = STATUS[m.status] ?? [m.status, ""];
        const n = m.picks.with_clv;
        return (
          <div className="card mrow" key={m.market}>
            <div className="mrow-top">
              <b>{scoreName(m.market)}</b>
              <span className={`tag ${cls}`}>{word}</span>
              <span className="bar" role="img" aria-label={`${n} of ${r.min_picks} picks measured`}><span style={{ width: `${Math.min(100, m.progress * 100)}%` }} /></span>
              <span className="mono faint">{n}/{r.min_picks}</span>
            </div>
            <div className="sline">
              <span>CLV <b className={(m.picks.avg_clv ?? 0) >= r.min_avg_clv ? "pos" : ""}>{fmtClv(m.picks.avg_clv)}</b></span>
              <span>beat close <b>{m.picks.beat_close == null ? "—" : pct(m.picks.beat_close)}</b></span>
              {m.leans.with_clv > 0 && <span>leans {m.leans.with_clv} · {fmtClv(m.leans.avg_clv)}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** More > Model: is the model earning trust? Closing line value first, the record second. */
export default async function Model({ searchParams }: { searchParams: Promise<{ show?: string }> }) {
  const sp = await searchParams;
  const show = SHOW.some(([k]) => k === sp.show) ? sp.show! : "all";
  const { results, golive, syncedAt, picks, marked } = await modelData();
  const o = results?.overall;
  const settled = picks.filter(settledOf).sort((a, b) => String(a.commence_time).localeCompare(String(b.commence_time)));
  const list = picks.filter((p) => show === "all" || (show === "mine" ? marked.has(p.pick_id)
      : show === "open" ? !settledOf(p) && p.status !== "void" : p.status === show))
    .sort((a, b) => String(b.commence_time).localeCompare(String(a.commence_time)));
  const ap = golive?.all_markets?.picks;
  const strong = golive?.markets.filter((m) => m.status === "pass").map((m) => m.market) ?? [];
  const best = [...(golive?.markets ?? [])].sort((a, b) => b.progress - a.progress)[0];
  const rs = golive?.research ?? {};
  const rec = (x?: { n?: number; won?: number; hits?: number; hit_rate?: number }) =>
    x?.n ? `${x.won ?? x.hits}–${x.n - (x.won ?? x.hits ?? 0)} (${pct(x.hit_rate)})` : "no graded reads yet";
  const byMarket = Object.entries(results?.by_market ?? {});

  return (
    <main className="rail">
      <BackLink fallback="/more" label="Me" />
      <div className="head"><h1>Model</h1>{syncedAt && <span className="stamp">updated {dayTime(syncedAt)}</span>}</div>

      <div className="strip">
        <span className="stat-pill">Record <b>{o?.record ?? "—"}</b></span>
        <span className="stat-pill">Units <b className={(o?.units ?? 0) >= 0 ? "pos" : "neg"}>{fmtU(o?.units)}</b></span>
        <span className="stat-pill">Avg CLV <b>{fmtClv(o?.avg_clv)}</b><span className="faint">goal +1%</span></span>
        <span className="stat-pill">Beat close <b>{o?.beat_close_pct == null ? "—" : pct(o.beat_close_pct)}</b><span className="faint">goal 55%</span></span>
      </div>
      <p className="lede">
        {strong.length ? <>Strong now: <b>{strong.map(scoreName).join(", ")}</b>. </>
          : best?.picks.with_clv ? <>No market is proven yet; furthest along is <b>{scoreName(best.market)}</b> with {best.picks.with_clv} of {golive!.rules.min_picks} picks measured. </>
          : <>No market has measured picks yet. </>}
        {ap?.with_clv ? <>{ap.with_clv} pick{ap.with_clv === 1 ? "" : "s"} measured against the close, {pct(ap.sure_positive)} sure the edge is real.</> : null}
      </p>

      {golive && (
        <>
          <h2 className="section-label">Strengths and weak spots · each market against the close</h2>
          <Scorecard g={golive} />
          {golive.by_book?.length ? (
            <>
              <h2 className="section-label">By book · picks and leans against the close</h2>
              <div className="card" style={{ padding: "6px 6px 2px" }}><div className="tbl"><table>
                <thead><tr><th>Book</th><th className="n">Picks</th><th className="n">CLV</th><th className="n hide-sm">Beat close</th>
                  <th className="n">Leans</th><th className="n">CLV</th></tr></thead>
                <tbody>{golive.by_book.map((b) => (
                  <tr key={b.book}>
                    <td>{b.book}</td>
                    <td className="n">{b.picks.with_clv}/{b.picks.logged}</td>
                    <td className="n">{fmtClv(b.picks.avg_clv)}</td>
                    <td className="n hide-sm">{b.picks.beat_close == null ? "—" : pct(b.picks.beat_close)}</td>
                    <td className="n">{b.leans.with_clv}/{b.leans.logged}</td>
                    <td className="n">{fmtClv(b.leans.avg_clv)}</td>
                  </tr>))}</tbody>
              </table></div></div>
              <p className="note">Measured / logged. DraftKings is priced from Oct 12; everything before is FanDuel&apos;s.</p>
            </>
          ) : null}
          <details className="more" style={{ marginTop: 10 }}>
            <summary>How markets are scored</summary>
            <div className="more-body">
              <p>A market is <b>strong</b> once it has {golive.rules.min_picks}+ picks with measured closing line value, average CLV of {signed(golive.rules.min_avg_clv, 0)} or better, and beats the close {pct(golive.rules.min_beat_close)} of the time. With {golive.rules.min_picks}+ picks and a missed bar, it's a <b>weak spot</b> to fix. Leans are the same signal at smaller edges: supporting evidence, not a substitute. Real bets are your call either way.</p>
              <p className="faint">Research reads (never picks): college early read, spreads {rec(rs.college_early_read?.spread)}, totals {rec(rs.college_early_read?.total)} · NFL prop script lean {rec(rs.nfl_props_reads?.script)} · matchup notes {rec(rs.nfl_props_reads?.matchup)}</p>
            </div>
          </details>
        </>
      )}

      <h2 className="section-label">Units won vs what CLV predicts</h2>
      {settled.length >= 2 ? (
        <div className="card chart-card">
          <Chart picks={settled} />
          <p className="faint">Solid: units won. Dashed: what closing line value says we should have won. The gap between them is luck.</p>
        </div>
      ) : <div className="card empty"><span>The chart starts after two graded picks under the current rules.</span></div>}

      {byMarket.length > 0 && (
        <>
          <h2 className="section-label">By market</h2>
          <div className="card tbl">
            <table>
              <thead><tr><th>Market</th><th className="n">Bets</th><th className="n">Record</th><th className="n">Units</th><th className="n hide-sm">Return</th><th className="n">CLV</th><th className="n hide-sm">Beat</th></tr></thead>
              <tbody>{byMarket.map(([k, m]) => (
                <tr key={k}><td>{scoreName(k)}</td><td className="n">{m.bets}</td><td className="n">{m.record}</td>
                  <td className={`n ${m.units >= 0 ? "pos" : "neg"}`}>{fmtU(m.units)}</td><td className="n hide-sm">{m.roi == null ? "—" : signed(m.roi)}</td>
                  <td className="n">{fmtClv(m.avg_clv)}</td><td className="n hide-sm">{m.beat_close_pct == null ? "—" : pct(m.beat_close_pct)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}

      <h2 className="section-label">Paper record · current rules</h2>
      <nav className="chips" aria-label="Show" style={{ marginBottom: 10 }}>
        {SHOW.map(([k, l]) => <Link key={k} href={k === "all" ? "/more/model" : `/more/model?show=${k}`} aria-current={k === show} scroll={false}>{l}</Link>)}
      </nav>
      {list.length ? (
        <div className="feed">
          {list.slice(0, 100).map((p) => (
            <div className="card prow" key={p.pick_id}>
              <div className="bet-top">
                <span className="bet-label">{label(p.label)}{marked.has(p.pick_id) && <span className="mine"> ✓</span>}</span>
                <span className="bet-price">{fmtAm(p.price)}</span>
              </div>
              <div className="sline">
                <span>{SPORT_SHORT[p.league] ?? p.league} · {p.matchup} · {dayTime(p.commence_time)}</span>
                {settledOf(p) || p.status === "void" ? <span className={`tag ${p.status === "won" ? "won" : p.status === "lost" ? "lost" : ""}`}>{p.status}</span> : <span className="tag">open</span>}
                {p.profit_flat != null && <span><b className={p.profit_flat >= 0 ? "pos" : "neg"}>{fmtU(p.profit_flat)}</b></span>}
                {clvOf(p) != null && <span>CLV <b className={clvOf(p)! >= 0 ? "pos" : "neg"}>{fmtClv(clvOf(p))}</b></span>}
              </div>
            </div>
          ))}
        </div>
      ) : <div className="card empty"><span>No picks here yet. Every paper pick lands in this list with its result and CLV the morning after the game.</span></div>}
    </main>
  );
}
