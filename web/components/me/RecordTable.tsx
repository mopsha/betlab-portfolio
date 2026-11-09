import type { Line } from "@/lib/bets";
import { MINUS, signed } from "@/lib/format";

export const units = (u: number | null, d = 2) => (u === null ? "—" : (u >= 0 ? "+" : MINUS) + Math.abs(u).toFixed(d) + "u");
export const cls = (x: number | null) => (x === null ? "" : x > 0 ? "pos" : x < 0 ? "neg" : "");

/** A record table (My bets > Record and Stats): bets, W-L, units, ROI on cash staked, CLV and how often it beat the close. */
export function RecordTable({ lines, total, head = "Market" }: { lines: Line[]; total: Line; head?: string }) {
  const row = (l: Line, strong = false) => {
    const roi = l.staked ? l.units / l.staked : null;
    const Cell = strong ? "th" : "td";
    return (
      <tr key={l.group}>
        <Cell style={strong ? { textTransform: "none", letterSpacing: 0, fontSize: 13, color: "var(--ink)" } : undefined}>{l.group}</Cell>
        <td className="n hide-sm">{l.bets}</td>
        <td className="n">{l.won}–{l.lost}{l.push ? `–${l.push}` : ""}</td>
        <td className={`n ${cls(l.units)}`}>{units(l.units)}</td>
        <td className={`n hide-sm ${cls(roi)}`}>{signed(roi)}</td>
        <td className={`n ${cls(l.clvN ? l.clvSum : null)}`}>{l.clvN ? signed(l.clvSum / l.clvN) : "—"}</td>
        <td className="n hide-sm">{l.clvN ? `${l.beat}/${l.clvN}` : "—"}</td>
      </tr>
    );
  };
  return (
    <div className="tbl">
      <table>
        <thead><tr><th>{head}</th><th className="n hide-sm">Bets</th><th className="n">W–L</th><th className="n">Units</th><th className="n hide-sm">ROI</th>
          <th className="n">CLV</th><th className="n hide-sm">Beat close</th></tr></thead>
        <tbody>{lines.map((l) => row(l))}{lines.length > 1 && row(total, true)}</tbody>
      </table>
    </div>
  );
}
