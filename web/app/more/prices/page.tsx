import { RecordSwitch } from "@/components/me/RecordSwitch";
import { SectionTitle } from "@/components/ui/Kit";
import { myBetsData, type CustomParlay, type QuoteRow } from "@/lib/data";
import { fmtAm, implied, num, pct, signed, toDec } from "@/lib/format";

const cls = (x: number | null) => (x === null ? "" : x > 0 ? "pos" : x < 0 ? "neg" : "");

function PriceRow({ q, custom }: { q: QuoteRow | CustomParlay; custom?: boolean }) {
  const fair = num(q.p_fair);
  const ev = fair !== null ? fair * toDec(q.price) - 1 : null;
  const c = custom ? (q as CustomParlay) : null;
  const status = c?.status && c.status !== "open" ? c.status : null;
  return (
    <tr>
      <td style={{ whiteSpace: "normal", minWidth: 140 }}>
        {String(q.matchup ?? "").split(":")[0]}
        <br /><span className="faint">{new Date(q.quoted_at).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" })}
          {" · "}{q.legs?.length ?? q.n_legs ?? "?"} legs{c?.grade ? ` · grade ${c.grade}` : ""}</span>
      </td>
      <td className="n">{fmtAm(q.price)}</td>
      <td className="n hide-sm">{fmtAm(q.fair_price)}</td>
      <td className={`n ${cls(ev)}`}>{signed(ev)}</td>
      {custom && <td className={`n ${status === "won" ? "pos" : status === "lost" ? "neg" : ""}`}>{status ?? "open"}</td>}
    </tr>
  );
}

/** Me › Record and stats › Prices (in My bets until the overhaul, Nov 4): your own parlays with their grade and result, and the
 *  FanDuel prices you typed. */
export default async function Prices() {
  const d = await myBetsData();
  const priced = d.quotes.filter((q) => num(q.p_fair) !== null);
  return (
    <main className="rail">
      <RecordSwitch on="prices" />
      <SectionTitle>Your own parlays</SectionTitle>
      {d.customs.length ? (
        <div className="card" style={{ padding: "6px 6px 2px" }}><div className="tbl"><table>
          <thead><tr><th>Parlay</th><th className="n">Price</th><th className="n hide-sm">Fair</th><th className="n">EV</th><th className="n">Result</th></tr></thead>
          <tbody>{[...d.customs].sort((a, b) => b.quoted_at.localeCompare(a.quoted_at)).map((q) => <PriceRow key={q.sgp_id} q={q} custom />)}</tbody>
        </table></div></div>
      ) : <p className="note">Parlays you build and save show here with their grade and result.</p>}
      <SectionTitle note={d.quotes.length}>FanDuel prices you typed</SectionTitle>
      {d.quotes.length ? (
        <div className="card" style={{ padding: "6px 6px 2px" }}><div className="tbl"><table>
          <thead><tr><th>Slip</th><th className="n">FanDuel</th><th className="n hide-sm">Fair</th><th className="n">EV</th></tr></thead>
          <tbody>{[...d.quotes].sort((a, b) => b.quoted_at.localeCompare(a.quoted_at)).map((q) => <PriceRow key={q.sgp_id} q={q} />)}</tbody>
        </table></div></div>
      ) : <p className="note">Type FanDuel&apos;s price into a parlay&apos;s price box and it lands here.</p>}
      {d.quotes.length > 0 && (
        <p className="note" style={{ marginTop: 10 }}>
          FanDuel&apos;s prices implied {pct(priced.reduce((s, q) => s + implied(q.price), 0) / Math.max(1, priced.length), 1)} on average against a fair{" "}
          {pct(priced.reduce((s, q) => s + Number(q.p_fair), 0) / Math.max(1, priced.length), 1)}; the gap is FanDuel&apos;s parlay margin.
        </p>
      )}
    </main>
  );
}
