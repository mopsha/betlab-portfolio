import { BackLink } from "@/components/ui/BackLink";
import Link from "next/link";
import { coverageDoc } from "@/lib/data";

const cls = (v: string) => (/^✓/.test(v) ? "yes" : /^✗/.test(v) ? "no" : /^planned/i.test(v) ? "plan" : "");

/** More > Markets: what each sport has, side by side (docs/COVERAGE.md, Mike's view, 2026-09-30). */
export default async function Markets() {
  const c = await coverageDoc();
  return (
    <main className="wide">
      <BackLink fallback="/more" label="Me" />
      <div className="head"><h1>Markets</h1>{c?.updated && <span className="stamp">updated {c.updated}</span>}</div>
      {!c ? <div className="card empty"><span>The table appears after the next cloud run.</span></div> : (
        <>
          <div className="card tbl coverage">
            <table>
              <thead><tr>{c.columns.map((h) => <th key={h}>{h}</th>)}</tr></thead>
              <tbody>{c.rows.map((r) => (
                <tr key={r[0]}>{r.map((v, i) => i === 0 ? <th scope="row" key={i}>{v}</th> : <td key={i} className={cls(v)}>{v}</td>)}</tr>
              ))}</tbody>
            </table>
          </div>
          {(c.key?.length || c.notes?.length) ? (
            <details className="more" style={{ marginTop: 10 }}>
              <summary>What the columns mean</summary>
              <div className="more-body">
                <ul className="bnotes">{(c.key ?? []).map((k) => <li key={k}>{k}</li>)}</ul>
                {(c.notes ?? []).map((n) => <p key={n} className="faint">{n}</p>)}
              </div>
            </details>
          ) : null}
        </>
      )}
    </main>
  );
}
