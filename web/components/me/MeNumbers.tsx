import Link from "next/link";
import { AreaChart } from "@/components/ui/Chart";
import { MINUS, signed } from "@/lib/format";
import { RANGES, rangeLabel, type MeNumbers as Numbers, type Range } from "@/lib/me-view";

const units = (u: number) => (u >= 0 ? "+" : MINUS) + Math.abs(u).toFixed(1) + "u";
const tone = (x: number | null) => (x === null ? "" : x > 0.00004 ? "pos" : x < -0.00004 ? "neg" : "");

/** Your number (the Me reorganization, Nov 5): units won as the hero with Week / Month / All beside it, the chips
 *  changing the number, the chart under it and the four stats in one row (a link to Record and stats). Links, so Me
 *  stays a server page. */
export function MeNumbers({ n, range }: { n: Numbers; range: Range }) {
  const href = (r: Range) => (r === "all" ? "/more" : `/more?range=${r}`);
  const label = rangeLabel(range);
  const cells: [string, string, string][] = [
    ["Record", `${n.won}-${n.lost}`, ""],
    ["Return", n.roi === null ? "—" : signed(n.roi), tone(n.roi)],
    ["Vs close", n.clv === null ? "—" : signed(n.clv), tone(n.clv)],
    ["Streak", n.streak ?? "—", ""],
  ];
  return (
    <section className="me-top" aria-label="Units won">
      <div className="me-num">
        <div>
          <div className={`hero-num ${tone(n.units / 100)}`}>{units(n.units)}</div>
          <p className="sub">{label}</p>
        </div>
        <nav className="me-chips" aria-label="Range">
          {RANGES.map(([k, l]) => <Link key={k} className="mk" href={href(k)} aria-current={k === range ? "true" : undefined} scroll={false} replace>{l}</Link>)}
        </nav>
      </div>
      <div className="me-chart">
        {n.points.length > 2
          ? <AreaChart points={n.points} label={`Units over time, ${label}: ${units(n.units)}`} height={96} />
          : <p className="sub">{n.bets ? "The chart starts after a second day with a settled bet." : `No settled bet ${range === "all" ? "yet" : label}.`}</p>}
      </div>
      <Link className="card me-stats" href="/more/record" aria-label={`Record and stats, ${label}: ${cells.map(([l, v]) => `${l} ${v}`).join(", ")}`}>
        {cells.map(([l, v, c]) => <span key={l} className="me-cell"><span className="cap">{l}</span><span className={`numx ${c}`}>{v}</span></span>)}
        <span className="chev" aria-hidden>›</span>
      </Link>
    </section>
  );
}
