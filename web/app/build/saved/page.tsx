import Link from "next/link";
import { SubHead } from "@/components/ui/Kit";
import { recordByGrade } from "@/lib/builder";
import { buildData } from "@/lib/data";
import { fmtAm, label, signed } from "@/lib/format";

export const dynamic = "force-dynamic";

const STATUS: Record<string, string> = { won: "won", lost: "lost", void: "void", push: "push" };

/** Build › your saved parlays (Nov 5: its own page behind the header's bookmark; it sat under the whole builder): how
 *  each grade has done, then the parlays, newest first. */
export default async function SavedParlays() {
  const { customs } = await buildData();
  const byGrade = recordByGrade(customs);
  const graded = byGrade.reduce((s, g) => s + g.graded, 0);
  return (
    <main className="rail bd-saved">
      <SubHead title="Your parlays" back="/build" backLabel="Build" />
      {!customs.length ? (
        <div className="card empty"><b>No saved parlays yet</b><span>Build a slip and tap Save, or I placed this: it shows up here with its grade and how it did.</span>
          <Link className="btn" href="/build">Build one</Link></div>
      ) : (
        <>
          {graded > 0 && (
            <>
              <h2 className="section-title"><span>How each grade has done</span><small>{graded} graded</small></h2>
              <div className="tbl card">
                <table>
                  <thead><tr><th>Grade</th><th className="n">Graded</th><th className="n">Hit</th><th className="n">Expected</th><th className="n">Units</th></tr></thead>
                  <tbody>{byGrade.map((g) => (
                    <tr key={g.grade}><td>{g.grade}</td><td className="n">{g.graded}</td><td className="n">{g.won}</td>
                      <td className="n">{g.expected.toFixed(1)}</td><td className={`n ${g.units >= 0 ? "pos" : "neg"}`}>{signed(g.units, 1, "u", 1)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </>
          )}
          <h2 className="section-title"><span>Saved</span><small>{customs.length}</small></h2>
          <div className="feed">
            {customs.slice(0, 30).map((c) => (
              <div className="card saved-row" key={c.sgp_id}>
                <span className="tag">{c.grade || "?"}</span>
                <span className="sr-legs">{(c.legs ?? []).map(label).join(" + ")}</span>
                <span className="mono">{fmtAm(c.price)}<span className="faint"> fair {fmtAm(c.fair_price)}</span></span>
                {c.status && STATUS[c.status] ? <span className={`tag ${c.status === "won" ? "won" : c.status === "lost" ? "lost" : ""}`}>{STATUS[c.status]}</span>
                  : <span className="tag">open</span>}
              </div>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
