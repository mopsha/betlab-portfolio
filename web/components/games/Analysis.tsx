// Each league's game analysis, built by the Python side (game_analysis.body), drawn as folded
// sections on the game page. Ported from the claude.ai page (page/index.html), compact first.
import { Fragment, type ReactNode } from "react";
import type { Analysis } from "@/lib/data";
import { MINUS, bookName, fmtAm, label, num, pct, signed } from "@/lib/format";
import { FdLink } from "@/components/ui/FdLink";

export type Fold = { key: string; title: string; n?: number; body: ReactNode };

const ord = (n?: number | null) => n == null ? "—" : n + ((n % 100 >= 11 && n % 100 <= 13) ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th");
const fixed = (x: unknown, d = 1) => { const v = num(x); return v === null ? "—" : v.toFixed(d).replace("-", MINUS); };
const epa = (x: unknown) => { const v = num(x); return v === null ? "—" : (v >= 0 ? "+" : MINUS) + Math.abs(v).toFixed(2); };
const About = ({ children }: { children: ReactNode }) => (
  <details className="more"><summary>About these numbers</summary><div className="more-body"><p>{children}</p></div></details>
);

export function Edges({ items }: { items?: { text: string; size?: number }[] }) {
  if (!items?.length) return null;
  return (
    <ul className="edges">
      {items.map((m) => {
        const size = num(m.size);
        const w = size === null ? 0 : Math.min(Math.abs(size) / 2.5, 1) * 50, off = (size ?? 0) > 0;
        return (
          <li key={m.text}>{m.text}
            {size !== null && <div className="ebar" role="img" aria-label={`${off ? "Offense" : "Defense"} edge, ${Math.abs(size).toFixed(1)} SD`}>
              <span className={off ? "off" : "def"} style={{ [off ? "left" : "right"]: "50%", width: `${w}%` }} /></div>}
          </li>
        );
      })}
    </ul>
  );
}

// ------------------------------------------------------------------------------------- NFL

const NFL_TAPE: [string, (t: any) => string, string?][] = [
  ["Plays", (t) => fixed(t.plays, 0)], ["Seconds a play", (t) => fixed(t.sec_per_play, 1)], ["Pass rate", (t) => pct(t.pass_rate)],
  ["Dropbacks", (t) => fixed(t.dropbacks, 0)], ["Runs", (t) => fixed(t.rushes, 0)],
  ["Pass offense EPA", (t) => epa(t.pass_off?.value), "pass_off"], ["Run offense EPA", (t) => epa(t.rush_off?.value), "rush_off"],
  ["Pass defense EPA", (t) => epa(t.pass_def?.value), "pass_def"], ["Run defense EPA", (t) => epa(t.rush_def?.value), "rush_def"],
  ["Pressure allowed", (t) => pct(t.protection?.value), "protection"], ["Pass rush", (t) => pct(t.pass_rush?.value), "pass_rush"],
  ["Red-zone TDs", (t) => pct(t.red_zone?.value), "red_zone"],
];

function NflTape({ g }: { g: Analysis }) {
  const [a, h] = g.teams ?? [];
  if (!a || !h) return null;
  const qb = (t: any) => t.qb ? `${t.qb.change ? "NEW · " : ""}${t.qb.name ?? "—"}` : "—";
  return (
    <div className="tape">
      <div className="hd">{a.name}</div><div className="k">at</div><div className="h hd">{h.name}</div>
      <div>{qb(a)}</div><div className="k">Starting QB</div><div className="h">{qb(h)}</div>
      {NFL_TAPE.map(([lab, f, key]) => {
        const ra = key ? a[key]?.rank : null, rh = key ? h[key]?.rank : null;
        const cell = (t: any, r: number | null, o: number | null, side: string) => (
          <div className={`${side}${r != null && o != null && r < o ? " better" : ""}`}>{f(t)}{r != null && <> <span className="rk">{ord(r)}</span></>}</div>);
        return <Fragment key={lab}>{cell(a, ra, rh, "")}<div className="k">{lab}</div>{cell(h, rh, ra, "h")}</Fragment>;
      })}
    </div>
  );
}

function hurtList(injuries?: Record<string, any[]>, names?: Record<string, string>) {
  const teams = Object.entries(injuries ?? {}).filter(([, l]) => l?.length);
  if (!teams.length) return null;
  const cls = (s: string) => (s === "Out" || s === "Doubtful" ? "out" : s === "Questionable" ? "q" : "");
  return (
    <div className="hurt">
      {teams.map(([team, list]) => (
        <div key={team}><b>{names?.[team] ?? team}</b>
          <ul>{list.map((p: any) => (
            <li key={p.name ?? p.player}><span className={`st ${cls(p.status)}`}>{p.status}</span>{p.name ?? p.player}{" "}
              <span className="faint">{p.position ?? p.pos ?? ""}{p.snap_share != null ? ` · ${Math.round(p.snap_share * 100)}% of snaps` : ""}
                {p.toi_min != null ? ` · ${p.toi_min} min · ${pct(p.shot_share)} of shots` : ""}{p.injury ? ` · ${String(p.injury).toLowerCase()}` : ""}</span></li>
          ))}</ul></div>
      ))}
    </div>
  );
}

export function nflTop(g: Analysis): ReactNode {
  const lines: any[] = [...(g.lines ?? [])].sort((x, y) => (y.ev_if_right ?? -9) - (x.ev_if_right ?? -9));
  if (!lines.length) return null;
  const head = <tr><th>Line</th><th className="n">FanDuel</th><th className="n">Market</th><th className="n">With script</th><th className="n">EV if right</th></tr>;
  const row = (l: any) => <tr key={l.label}><td>{label(l.label)}</td><td className="n">{fmtAm(l.price)}</td><td className="n">{pct(l.p_market)}</td>
    <td className="n">{pct(l.p_script)}</td><td className={`n ${(l.ev_if_right ?? 0) >= 0 ? "pos" : "neg"}`}>{signed(l.ev_if_right, 0)}</td></tr>;
  return (
    <section className="sec">
      <h2>Lines that fit the script</h2>
      <div className="read">{Object.values(g.script_read ?? {}).map((s: any) => <span key={s.why}>{s.why}</span>)}</div>
      <div className="tbl"><table><thead>{head}</thead><tbody>{lines.slice(0, 4).map(row)}</tbody></table></div>
      {lines.length > 4 && <details className="more"><summary>All {lines.length} lines</summary>
        <div className="tbl"><table><thead>{head}</thead><tbody>{lines.map(row)}</tbody></table></div></details>}
      <About>Market is the sharp books&apos; no-vig chance of that side. With script moves it by this game&apos;s pass matchup and projected dropbacks, the one effect that held up on 2025 prop lines. A read to shop with, not a pick. Rushing props showed no such effect, so they aren&apos;t leaned.</About>
    </section>
  );
}

export function nflFolds(g: Analysis, fun: Analysis | undefined): Fold[] {
  const names = Object.fromEntries((g.teams ?? []).map((t: any) => [t.team, t.name]));
  const effects = Object.values(g.injury_effects ?? {}).filter(Boolean) as string[];
  const hurt = hurtList(g.injuries, names);
  const nHurt = Object.values(g.injuries ?? {}).flat().length;
  const reads: any[] = (fun?.reads ?? []).map((r: any) => ({ ...r, gap: r.p_model - r.p_market })).sort((x: any, y: any) => Math.abs(y.gap) - Math.abs(x.gap));
  const STAT: Record<string, string> = { receptions: "receptions", receiving_yards: "receiving yds", rushing_yards: "rushing yds", passing_yards: "passing yds", tds: "anytime TD" };
  return [
    { key: "story", title: "How the game goes", body: <>
      {fun?.read && <div className="read">{Object.values(fun.read).filter(Boolean).map((t: any) => <span key={t}>{t}</span>)}</div>}
      <p className="prose">{g.script}</p></> },
    { key: "tape", title: "Tale of the tape and matchups", body: <div className="two"><NflTape g={g} /><Edges items={g.matchups} /></div> },
    ...(hurt || effects.length ? [{ key: "hurt", title: "Who's hurt", n: nHurt, body: <>
      {effects.length > 0 && <div className="read"><b>What it does to the numbers</b>{effects.map((e) => <span key={e}>{e}</span>)}</div>}
      {hurt}<About>Regulars only (35%+ of snaps in the last three games) and any QB. Game status comes out Friday for Sunday games; before that it&apos;s the practice report. Missing line starters, a top target, a top pass rusher or defensive backs move the projection (tested on 2016–25).</About></> }] : []),
    ...(g.matchup_notes?.length ? [{ key: "notes", title: "Matchup notes (unconfirmed)", n: g.matchup_notes.length, body: <>
      <ul className="edges">{g.matchup_notes.map((n: any) => <li key={n.label}><b>{label(n.label)}</b> <span className="mono">{fmtAm(n.price)}</span><br />
        <span className="faint">{n.why} · market {pct(n.p_market)} · with matchup {pct(n.p_matchup)}</span></li>)}</ul>
      <About>Receivers facing defenses that give up a lot (or very little) to their position, and deep threats against defenses that do or don&apos;t allow the deep ball. Promising on 2025 lines but not proven, so every one is tracked before it counts.</About></> }] : []),
    ...(reads.length ? [{ key: "reads", title: "Our model vs. the market", n: reads.length, body: <>
      <div className="tbl"><table><thead><tr><th>Player</th><th>Stat</th><th className="n">Line</th><th className="n">Market over</th><th className="n">Our model</th><th className="n">Gap</th></tr></thead>
        <tbody>{reads.map((r) => <tr key={r.player + r.stat} className={Math.abs(r.gap) >= 0.12 ? "hl" : ""}><td>{r.player}</td><td>{STAT[r.stat] ?? r.stat}</td>
          <td className="n">{r.line}</td><td className="n">{pct(r.p_market)}</td><td className="n">{pct(r.p_model)}</td>
          <td className={`n ${r.gap >= 0 ? "pos" : "neg"}`}>{signed(r.gap, 0, " pts")}</td></tr>)}</tbody></table></div>
      <About>Our model&apos;s view of each over (usage, efficiency, game script, injuries) next to the market&apos;s no-vig chance. It has no weight in prices: it earns one only by beating real prop lines. Highlighted rows disagree by 12+ points; the market usually knows why.</About></> }] : []),
    ...(g.weather?.text ? [{ key: "weather", title: "Weather", body: <p className="prose">{g.weather.text}</p> }] : []),
    ...(g.notes?.length ? [{ key: "data", title: "Data notes", body: <ul className="edges">{g.notes.map((n: string) => <li key={n}>{n}</li>)}</ul> }] : []),
  ];
}

export function nflMeta(g: Analysis): string[] {
  const m = g.market, o = g.ours, [a, h] = g.teams ?? [];
  const out: string[] = [];
  if (m) out.push(`${m.spread_home > 0 ? h?.name ?? g.home : a?.name ?? g.away} ${MINUS}${Math.abs(m.spread_home)} · total ${m.total}`,
    `Market ${g.away} ${Math.round(m.away_points)}, ${g.home} ${Math.round(m.home_points)}`);
  if (o) out.push(`Our ratings: ${o.margin > 0 ? g.home : g.away} by ${Math.abs(o.margin).toFixed(1)}`);
  return out;
}

// ------------------------------------------------------------------------------- College

const CUNITS: [string, string][] = [["epa", "EPA / play"], ["success", "Success rate"], ["pass_epa", "Pass EPA"], ["rush_epa", "Run EPA"],
  ["line_yards", "Line yards"], ["stuff_rate", "Stuff rate"], ["explosiveness", "Explosiveness"]];

export function ncaafTop(g: Analysis): ReactNode {
  if (g.ny_blocked) return <p className="err" style={{ marginTop: 16 }}>{g.ny_blocked}: analysis only (New York rules).</p>;
  const reads = Object.entries(g.read ?? {});
  if (!reads.length) return null;
  return (
    <section className="sec">
      <h2>Early read</h2>
      <div className="grid-tickets">{reads.map(([k, r]: [string, any]) => (
        <div className="card bet" key={k}><div className="bet-top"><span className="tag lean">{k} read</span><span className="bet-label">{label(r.label)}</span>
          <span className="bet-price">{r.price != null ? fmtAm(r.price) : ""}</span></div>
          <div className="sline"><span><b>{Number(r.strength).toFixed(1)}</b> SD</span><span>{Number(r.edge_pts).toFixed(1)} pts</span></div>
          {r.drivers?.length > 0 && <p className="note">{r.drivers.join(" · ")}</p>}</div>))}</div>
      <About>The efficiency read beat opening lines in 2022–25 (not closing lines), so it&apos;s strongest early in the week. Tracked, never priced, until this season&apos;s record agrees.</About>
    </section>
  );
}

export function ncaafFolds(g: Analysis): Fold[] {
  const [a, h] = g.teams ?? [];
  const cell = (u: any) => (u?.rank ? String(u.rank) : "—");
  return [
    ...(a && h ? [{ key: "units", title: "Units and where it's decided", body: <div className="two">
      <div className="tbl"><table><thead><tr><th>FBS rank (1 = best)</th><th className="n">{a.team} O</th><th className="n">{h.team} D</th><th className="n">{h.team} O</th><th className="n">{a.team} D</th></tr></thead>
        <tbody>{CUNITS.map(([k, l]) => <tr key={k}><td>{l}</td><td className="n">{cell(a["off_" + k])}</td><td className="n">{cell(h["def_" + k])}</td>
          <td className="n">{cell(h["off_" + k])}</td><td className="n">{cell(a["def_" + k])}</td></tr>)}</tbody></table></div>
      <Edges items={g.matchups} /></div> }] : []),
    ...(g.weather?.text ? [{ key: "weather", title: "Weather", body: <p className="prose">{g.weather.text}</p> }] : []),
  ];
}

export function ncaafMeta(g: Analysis): string[] {
  const m = g.market, o = g.ours, out: string[] = [];
  if (m) out.push(`${m.spread_home > 0 ? g.home : g.away} ${MINUS}${Math.abs(m.spread_home)} · total ${m.total}`);
  if (o) out.push(`Our read: ${o.margin > 0 ? g.home : g.away} by ${Math.abs(o.margin).toFixed(1)}, ${Number(o.total).toFixed(0)} pts`);
  return out;
}

// ------------------------------------------------------------------------------------- NHL

/** A book's price with its EV under it: the game page's price tables show FanDuel and DraftKings side by side
 *  (Oct 13); "—" where the book doesn't post that side at that number. */
const bookCell = (price: number | null | undefined, ev: number | null | undefined) => (
  <td className="n">{price == null ? "—" : <>{fmtAm(price)}{ev != null && <><br /><span className={ev >= 0 ? "pos" : "neg"}>{signed(ev)}</span></>}</>}</td>
);

/** The price tables' book columns at the account's books (Nov 6): the game page sets `g.books_on` (onBooks). */
type BookCol = [string, (o: any) => [number | null | undefined, number | null | undefined]];
const COLS: BookCol[] = [["FanDuel", (o) => [o.price, o.ev]], ["DraftKings", (o) => [o.dk_price, o.dk_ev]], ["Novig", (o) => [o.nv_price, o.nv_ev]]];
const UFC_COLS: BookCol[] = [["FanDuel", (o) => [o.fanduel?.price, o.fanduel?.ev]], ["DraftKings", (o) => [o.draftkings?.price, o.draftkings?.ev]],
  ["Novig", (o) => [o.novig?.price, o.novig?.ev]]];
const colsOf = (g: Analysis, all: BookCol[] = COLS) => all.filter(([b]) => !Array.isArray(g.books_on) || g.books_on.includes(b));
const bookHeads = (cols: BookCol[]) => cols.map(([b]) => <th key={b} className="n">{b}</th>);
const bookCells = (cols: BookCol[], o: any) => cols.map(([b, f]) => <Fragment key={b}>{bookCell(...f(o))}</Fragment>);

/** A prop's Novig over / under (novig_parlays.attach_tables, Oct 28): a side shows only with $50+ behind it, and a side
 *  priced above the sharp chance is green. */
const novigOu = (x: any) => x.nv_over == null && x.nv_under == null ? "—" : <>
  <span className={(x.nv_ev_over ?? -1) >= 0 ? "pos" : ""}>{x.nv_over == null ? "—" : fmtAm(x.nv_over)}</span>{" / "}
  <span className={(x.nv_ev_under ?? -1) >= 0 ? "pos" : ""}>{x.nv_under == null ? "—" : fmtAm(x.nv_under)}</span></>;

const GSTATUS: Record<string, string> = { confirmed: "Confirmed", expected: "Expected", probable: "Probable", "our guess": "Our guess" };

export function nhlTop(g: Analysis): ReactNode {
  const fd: any[] = g.fanduel ?? [];
  return (
    <>
      {g.read && <section className="sec"><div className="read"><b>Our read (tracked, not a pick)</b>
        <span>{label(g.read.label)} at {fmtAm(g.read.price)}: our model {pct(g.read.p_model)}, market no-vig {pct(g.read.p_market)}.</span></div></section>}
      {fd.length > 0 && <section className="sec"><h2>Your books vs. the sharp book</h2>
        <div className="tbl"><table><thead><tr><th>Side</th>{bookHeads(colsOf(g))}<th className="n">Sharp no-vig</th></tr></thead>
          <tbody>{fd.map((o) => <tr key={o.label}><td>{label(o.label)}</td>{bookCells(colsOf(g), o)}<td className="n">{pct(o.p_market)}</td></tr>)}</tbody></table></div>
        <About>From today&apos;s odds pull ({fd[0].source}). Each book&apos;s price with its EV under it. This is where the NHL card&apos;s picks come from: a book lagging the sharp price by 3%+ EV; a bet goes to the better book.</About></section>}
    </>
  );
}

export function nhlFolds(g: Analysis): Fold[] {
  const [a, h] = g.teams ?? [];
  const L = g.line ?? {}, Mo = g.model ?? {};
  const cell = (t: any, v: ReactNode, r?: number | null, side = "") => <div className={side}>{v}{r != null && <> <span className="rk">{ord(r)}</span></>}</div>;
  const tape = a && h && (
    <div className="tape">
      <div className="hd">{a.team}</div><div className="k">at</div><div className="h hd">{h.team}</div>
      <div>{a.record}</div><div className="k">Record</div><div className="h">{h.record}</div>
      <div>{a.goalie ?? "—"} <span className="rk">{GSTATUS[a.goalie_status] ?? a.goalie_status}</span></div><div className="k">Goalie</div>
      <div className="h">{h.goalie ?? "—"} <span className="rk">{GSTATUS[h.goalie_status] ?? h.goalie_status}</span></div>
      {cell(a, pct(a.goalie_sv, 1))}<div className="k">Save %</div>{cell(h, pct(h.goalie_sv, 1), null, "h")}
      {cell(a, fixed(a.shots, 1), a.ranks?.off_shots)}<div className="k">Shots expected</div>{cell(h, fixed(h.shots, 1), h.ranks?.off_shots, "h")}
      {cell(a, fixed(a.xg, 2))}<div className="k">Goals expected</div>{cell(h, fixed(h.xg, 2), null, "h")}
      {g.special?.[a.team] && <>{cell(a, pct(g.special[a.team].pp_pct), g.special[a.team].pp_rank)}<div className="k">Power play</div>
        {cell(h, pct(g.special[h.team]?.pp_pct), g.special[h.team]?.pp_rank, "h")}
        {cell(a, pct(g.special[a.team].pk_pct), g.special[a.team].pk_rank)}<div className="k">Penalty kill</div>
        {cell(h, pct(g.special[h.team]?.pk_pct), g.special[h.team]?.pk_rank, "h")}</>}
    </div>
  );
  const gap = (m: number | null, k: number | null) => m == null || k == null ? "—" : Math.abs(m - k) < 0.005 ? "0 pts" : signed(m - k, 0, " pts");
  const row = (lab: string, mkt: number | null, mod: number | null, price: unknown) => (
    <tr key={lab}><td>{lab}</td><td className="n">{price == null ? "—" : fmtAm(price)}</td><td className="n">{pct(mkt)}</td><td className="n">{pct(mod)}</td><td className="n">{gap(mod, mkt)}</td></tr>);
  const props: any[] = g.props ?? [];
  const hurt = hurtList(g.injuries);
  const STATN: Record<string, string> = { shots: "shots", points: "points", saves: "saves" };
  return [
    ...(g.script ? [{ key: "story", title: "How the game goes", body: <p className="prose">{g.script}</p> }] : []),
    { key: "tape", title: "Tale of the tape and matchups", body: <div className="two">{tape}<Edges items={g.matchups} /></div> },
    { key: "lines", title: "The lines and our model", body: <>
      <div className="tbl"><table><thead><tr><th>{bookName(g.book) || "DraftKings"}</th><th className="n">Price</th><th className="n">Market</th><th className="n">Our model</th><th className="n">Gap</th></tr></thead>
        <tbody>
          {row(`${h?.team} ML`, L.p_home, Mo.p_home, L.ml_home)}
          {row(`${a?.team} ML`, L.p_home == null ? null : 1 - L.p_home, Mo.p_home == null ? null : 1 - Mo.p_home, L.ml_away)}
          {L.total != null && row(`Over ${L.total}`, L.p_over, Mo.p_over, L.over)}
          {L.total != null && row(`Under ${L.total}`, L.p_over == null ? null : 1 - L.p_over, Mo.p_over == null ? null : 1 - Mo.p_over, L.under)}
        </tbody></table></div>
      <About>{g.book === "FanDuel" ? "FanDuel's prices; Market is Pinnacle's no-vig chance." : "DraftKings' prices from ESPN's free feed; Market is DraftKings' no-vig chance."} Our model: expected shots and goals from each team&apos;s recent play against tonight&apos;s goalies. Our totals lose to the market&apos;s (2025-26), so trust its total over ours.</About></> },
    ...(props.length ? [{ key: "props", title: "Player props", n: props.length, body: <>
      <div className="tbl"><table><thead><tr><th>Player</th><th>FanDuel line</th><th className="n">Over / under</th><th className="n">Novig</th><th className="n">Market over</th><th className="n">Our model</th><th className="n">Best EV</th></tr></thead>
        <tbody>{props.map((x) => <tr key={x.player + x.stat + x.line} className={x.read ? "hl" : ""}><td>{x.player} <span className="faint">{x.team ?? ""}</span></td>
          <td>{STATN[x.stat] ?? x.stat} {x.line}</td><td className="n">{fmtAm(x.fd_over)} / {x.fd_under == null ? "—" : fmtAm(x.fd_under)}</td>
          <td className="n">{novigOu(x)}</td>
          <td className="n">{pct(x.p_market)}</td><td className="n">{pct(x.p_model)}</td>
          <td className="n">{x.ev_over == null ? "—" : signed(Math.max(x.ev_over, x.ev_under ?? -1))}</td></tr>)}</tbody></table></div>
      <About>Market over is the other books&apos; no-vig chance at FanDuel&apos;s number. Our model is the machine-learning model (ice time, shot rates, lineup, tonight&apos;s game read); it has no weight in prices yet. Highlighted rows fit our game read. Every line is logged to train the model.</About></> }] : []),
    ...(hurt ? [{ key: "hurt", title: "Who's hurt", n: Object.values(g.injuries ?? {}).flat().length, body: hurt }] : []),
  ];
}

// ------------------------------------------------------------------------------------ Soccer

export function soccerTop(g: Analysis): ReactNode {
  const lines: any[] = g.lines ?? [];
  if (!lines.length) return null;
  const name = (s: string) => s === "Draw" ? "Draw" : `${s} win`;
  const moved = (o: any) => o.first_price == null || o.first_price === o.price ? "—" : `${fmtAm(o.first_price)} → ${fmtAm(o.price)}`;
  return (
    <section className="sec"><h2>Your books vs. the sharp book</h2>
      <div className="tbl"><table><thead><tr><th>3-way</th>{bookHeads(colsOf(g))}<th className="n">Sharp no-vig</th><th className="n hide-sm">FanDuel moved</th></tr></thead>
        <tbody>{lines.map((o) => <tr key={o.side}><td>{name(o.side)}</td>{bookCells(colsOf(g), o)}<td className="n">{pct(o.p_market)}</td><td className="n hide-sm">{moved(o)}</td></tr>)}</tbody></table></div>
      <About>Regulation time (90 minutes plus stoppage). Each book&apos;s price, with its EV under it, against {bookName(lines[0].source) || "the sharp book"}&apos;s no-vig chance at our latest pull. Soccer is market-only: our ratings lost to the close in every league, so a pick needs FanDuel to lag the sharp price by 3%+ EV. Every line is logged to test whether FanDuel lags at all.</About>
    </section>
  );
}

export function soccerMeta(g: Analysis): string[] {
  const fav = [...(g.lines ?? [])].filter((o: any) => o.side !== "Draw").sort((a: any, b: any) => b.p_market - a.p_market)[0];
  const [h, a] = g.analysis?.teams ?? [];
  const shots = h?.shots != null && a?.shots != null ? [`Shots projected ${fixed(h.shots, 0)}–${fixed(a.shots, 0)}`] : [];
  return [g.competition, ...(fav ? [`${fav.side} ${pct(fav.p_market)} to win`] : []), ...shots].filter(Boolean);
}

/** Badges for the soccer game header: whose lineup is still a guess, and heavy rotation. */
export function soccerBadges(g: Analysis): string[] {
  const an = g.analysis;
  if (!an) return [];
  const out: string[] = an.lineup === "expected" ? ["Lineups not out yet: last XIs shown"] : [];
  for (const t of an.teams ?? []) {
    const r = t.rotation;
    if (r?.missing?.length) out.push(`${t.team} without ${r.missing.slice(0, 2).join(", ")}`);
    else if (r?.changes >= 4) out.push(`${t.team}: ${r.changes} changes`);
  }
  return out;
}

/** The soccer analysis (cards/analysis_soccer.py): the story, the tape, the likeliest shooters. */
function goalsRead(an: any): Fold[] {
  const r = an?.goals_read;
  if (!r) return [];
  const row = (lab: string, mine: number, mkt: number) => (
    <tr key={lab}><td>{lab}</td><td className="n">{pct(mkt)}</td><td className="n">{pct(mine)}</td>
      <td className="n">{signed(mine - mkt, 0, " pts")}</td></tr>);
  return [{ key: "goals", title: "Goals read", body: <>
    <div className="tbl"><table><thead><tr><th></th><th className="n">Market</th><th className="n">Lineup read</th><th className="n">Gap</th></tr></thead>
      <tbody>{row("Over 2.5 goals", r.p_over25, r.p_over25_mkt)}{row("Both teams to score", r.p_btts, r.p_btts_mkt)}</tbody></table></div>
    <About>The lineup read starts from the market&apos;s expected goals and adjusts for who actually starts (each starter&apos;s
      expected goals from the shots model). {an.lineup === "confirmed" ? "Lineups are confirmed." : "Lineups aren't out yet, so it uses each team's last XI."}
      It has no weight: every confirmed-lineup read is logged and checked against the market&apos;s log loss.</About></> }];
}

/** The 3-way in one place (analysis_soccer.moneyline): market now vs first look, best book, Europe, lineup read. */
function moneylineRead(an: any): Fold[] {
  const ml = an?.moneyline;
  if (!ml?.sides?.length) return [];
  const name = (s: string) => s === "Draw" ? "Draw" : `${s} win`;
  const best = (s: any) => s.best_price == null ? "—" : <>{fmtAm(s.best_price)} <span className="faint">{bookName(s.best_book)}</span>
    <div className={`faint${s.best_ev > 0 ? " pos" : ""}`}>{signed(s.best_ev)}</div></>;
  const lineup = ml.sides.some((s: any) => s.p_lineup != null);
  const rec = ml.lineup_record;
  return [{ key: "moneyline", title: "Moneyline read", body: <>
    {ml.summary && <p className="prose">{ml.summary}</p>}
    <div className="tbl"><table><thead><tr><th>3-way</th><th className="n">Market now</th><th className="n">First look</th>
      <th className="n">Move</th><th className="n">Best price</th>{lineup && <th className="n">Lineup read</th>}</tr></thead>
      <tbody>{ml.sides.map((s: any) => <tr key={s.side}><td>{name(s.side)}</td><td className="n">{pct(s.p_market)}</td>
        <td className="n">{pct(s.p_first)}</td><td className="n">{s.move == null ? "—" : signed(s.move, 0, " pts")}</td>
        <td className="n">{best(s)}</td>{lineup && <td className="n">{pct(s.p_lineup)}</td>}</tr>)}</tbody></table></div>
    <About>Market: the sharp book&apos;s no-vig chances (regulation time) now and at our first look at this match; a move
      of 2+ points is the sharp money&apos;s direction. Best price: the better of FanDuel and DraftKings for each side
      (ties to FanDuel) with its EV against those chances; a pick needs 3%+. European games within 4 days either side
      come from the cup matches we price. {lineup ? <>Lineup read: the starters&apos; expected goals on a score grid
      ({ml.lineup === "confirmed" ? "confirmed lineups" : "each team's last XI until the lineups are out"}). It has no
      weight{rec?.n ? <>: on {rec.n} graded matches its log loss is {fixed(rec.log_loss, 3)} vs the market&apos;s {fixed(rec.log_loss_mkt, 3)} (lower is better)</> : null}.</> : null}</About></> }];
}

export function soccerFolds(g: Analysis): Fold[] {
  const an = g.analysis;
  if (!an) return [];
  if (!an.teams?.length) return moneylineRead(an);           // a match with only the moneyline read (no ESPN match yet)
  const [h, a] = an.teams ?? [];
  const cell = (v: ReactNode, r?: number | null, n?: number | null, side = "") =>
    <div className={side}>{v}{r != null && <> <span className="rk">{ord(r)}{n ? ` of ${n}` : ""}</span></>}</div>;
  const rot = (t: any) => t.rotation == null ? "—" : `${t.rotation.changes ?? 0} change${t.rotation.changes === 1 ? "" : "s"}${t.rotation.missing?.length ? `, without ${t.rotation.missing.join(", ")}` : ""}`;
  const tape = h && a && (
    <div className="tape">
      <div className="hd">{h.team}</div><div className="k">vs</div><div className="h hd">{a.team}</div>
      {cell(fixed(h.xg, 2))}<div className="k">Goals expected (market)</div>{cell(fixed(a.xg, 2), null, null, "h")}
      {h.goals_model != null && <>{cell(fixed(h.goals_model, 2))}<div className="k">Goals expected (lineup read)</div>{cell(fixed(a.goals_model, 2), null, null, "h")}</>}
      {cell(fixed(h.shots, 1))}<div className="k">Shots projected</div>{cell(fixed(a.shots, 1), null, null, "h")}
      {cell(fixed(h.sot, 1))}<div className="k">On target projected</div>{cell(fixed(a.sot, 1), null, null, "h")}
      {cell(fixed(h.shots_for, 1), h.rank_for)}<div className="k">Shots a game (last 10)</div>{cell(fixed(a.shots_for, 1), a.rank_for, null, "h")}
      {cell(fixed(h.shots_against, 1), h.rank_against)}<div className="k">Shots allowed (last 10)</div>{cell(fixed(a.shots_against, 1), a.rank_against, null, "h")}
      {cell(h.rest_days == null ? "—" : `${fixed(h.rest_days, 0)} days`)}<div className="k">Rest</div>{cell(a.rest_days == null ? "—" : `${fixed(a.rest_days, 0)} days`, null, null, "h")}
      {an.lineup === "confirmed" && <>{cell(rot(h))}<div className="k">Lineup</div>{cell(rot(a), null, null, "h")}</>}
    </div>
  );
  const shooters: any[] = an.shooters ?? [];
  // FanDuel's 2+ shots rung (else its first): its price, its own no-margin chance, and the model's
  const rung = (r: any[]) => r.find((x) => x.line === 1.5) ?? r[0];
  return [
    ...(an.script ? [{ key: "story", title: "How the game goes", body: <p className="prose">{an.script}</p> }] : []),
    ...moneylineRead(an),
    ...(tape ? [{ key: "tape", title: "Tale of the tape", body: <>{tape}
      <About>Goals expected: the sharp 1X2 and goals line fit to a score grid. Shots projected: our shots model on {an.lineup === "confirmed" ? "tonight's lineups" : "each team's last XI (lineups come out about an hour before kickoff)"}, plus substitutes. Ranks: this season in the league (1st = most shots, fewest allowed).</About></> }] : []),
    ...goalsRead(an),
    ...(shooters.length ? [{ key: "shooters", title: "Likeliest shooters", n: shooters.length, body: <>
      <div className="tbl"><table><thead><tr><th>Player</th><th className="n">Shots</th><th className="n">On target</th><th className="n">1+ shot</th>
        <th>FanDuel</th><th className="n">FanDuel fair</th><th className="n">Our model</th></tr></thead>
        <tbody>{shooters.map((s) => { const r = rung(s.fd_shots ?? []); return (
          <tr key={s.player}><td>{s.player} <span className="faint">{s.team}</span></td>
            <td className="n">{fixed(s.shots, 1)}</td><td className="n">{fixed(s.sot, 1)}</td><td className="n">{pct(s.p_shot)}</td>
            <td>{r ? <>{r.line + 0.5}+ shots {fmtAm(r.fd_price)}</> : <span className="faint">not posted</span>}</td>
            <td className="n">{r ? pct(r.p_fd_fair) : "—"}</td><td className="n">{r ? pct(r.p_model) : "—"}</td></tr>); })}</tbody></table></div>
      <About>Expected shots from our machine-learning model (each player&apos;s shot rate, minutes, role, his team&apos;s and the opponent&apos;s shot form, the market&apos;s expected goals). FanDuel fair: FanDuel&apos;s own shot ladder with its margin (about 16%) taken off. The model has no weight in prices yet: every FanDuel rung is logged and graded to test it.</About></> }] : []),
    ...(shooters.some((s) => s.p_ga != null) ? [{ key: "scorers", title: "Score or assist", body: <>
      <div className="tbl"><table><thead><tr><th>Player</th><th className="n">Score</th><th className="n">Assist</th><th className="n">Score or assist</th>
        <th>FanDuel score or assist</th><th>FanDuel to score</th><th className="n">Pinnacle fair</th></tr></thead>
        <tbody>{shooters.map((s) => (
          <tr key={s.player}><td>{s.player} <span className="faint">{s.team}</span></td>
            <td className="n">{pctOdds(s.p_goal)}</td><td className="n">{pctOdds(s.p_assist)}</td><td className="n">{pctOdds(s.p_ga)}</td>
            <td>{s.fd_ga ? (s.fd_ga.link ? <FdLink links={[s.fd_ga.link]} label={fmtAm(s.fd_ga.fd_price)} className="fdprice" />
              : fmtAm(s.fd_ga.fd_price)) : <span className="faint">not posted</span>}</td>
            <td>{s.fd_scorer ? (s.fd_scorer.link ? <FdLink links={[s.fd_scorer.link]} label={fmtAm(s.fd_scorer.fd_price)} className="fdprice" />
              : fmtAm(s.fd_scorer.fd_price)) : <span className="faint">not posted</span>}</td>
            <td className="n">{s.pin_scorer != null ? pctOdds(s.pin_scorer) : "—"}</td></tr>))}</tbody></table></div>
      <About>Our model&apos;s chances (fair odds in brackets): goals and assists per 90 minutes, role and minutes, both teams&apos; form and the market&apos;s expected goals. FanDuel&apos;s prices open its betslip: a FanDuel price longer than our fair odds pays more than the model thinks it should (FanDuel has no sharp book to check it against here, and the model has no weight yet). Pinnacle fair: its no-vig scorer chance, the sharp price our scorer picks use. The model has no weight in prices yet.</About></> }] : []),
  ];
}

/** "41% (+144)": a chance with its fair American odds. */
const pctOdds = (p: unknown) => { const v = num(p); return v == null || v <= 0 || v >= 1 ? "—" : `${pct(v)} (${fmtAm(v >= 0.5 ? -100 * v / (1 - v) : 100 * (1 - v) / v)})`; };

export function nhlMeta(g: Analysis): string[] {
  const L = g.line ?? {}, Mo = g.model ?? {};
  const out: string[] = [];
  if (L.ml_home != null) {
    const favHome = (L.p_home ?? Mo.p_home) >= 0.5;
    out.push(`${favHome ? g.home : g.away} ${fmtAm(favHome ? L.ml_home : L.ml_away)} · total ${L.total ?? "—"}`);
  }
  out.push(`Our model: ${g.home} ${pct(Mo.p_home)} to win, ${fixed(Mo.exp_total, 1)} goals`);
  return out;
}

// ------------------------------------------------------------------------------------ NBA

/** The NBA game (reports/nba.py): listed in the morning with the market's line and national TV; its player
 *  lines arrive when the game is priced, 15-45 minutes before tip, after lineups (Oct 12). */
export function nbaMeta(g: Analysis): string[] {
  const out: string[] = [];
  const sp = num(g.spread_home), tot = num(g.total);
  if (sp != null) {
    const fav = sp >= 0 ? g.home : g.away;
    out.push(`${fav} ${Math.abs(sp) < 0.25 ? "pick'em" : `${MINUS}${+Math.abs(sp).toFixed(1)}`} · total ${tot ?? "—"}`);
  }
  if (g.national_tv?.length) out.push(`National TV: ${g.national_tv.join(", ")}`);
  const m = g.model;
  if (m) out.push(`Our model: ${m.margin >= 0 ? g.home : g.away} by ${+Math.abs(m.margin).toFixed(1)}, ${+(+m.total).toFixed(1)} points`
    + (m.key_out ? ` (${m.key_out} key player${m.key_out > 1 ? "s" : ""} out, not adjusted)` : ""));
  return out;
}

/** Regulars out tonight (nba_reads.absences): the read uses season ratings and doesn't adjust for them yet. */
function outList(g: Analysis): ReactNode {
  const o = g.model?.out;
  if (!o || (!o.home?.length && !o.away?.length)) return null;
  const side = (team: string, xs: any[]) => xs?.length
    ? <span>{team}: {xs.map((x) => `${x.name} (${Math.round(x.minutes)} min)`).join(", ")}</span> : null;
  return (
    <div className="read"><b>Out tonight, and the read doesn&apos;t adjust for it</b>
      {side(g.away, o.away)}{side(g.home, o.home)}
      <span className="faint">Our ratings come from the season so far; the market already prices these absences. Reads with key players out are tracked separately.</span>
    </div>
  );
}

/** The team model's read against the market (nba_reads.py): tracked, no weight in prices. */
export function nbaTop(g: Analysis): ReactNode {
  const m = g.model, sp = num(g.spread_home), tot = num(g.total);
  if (!m || sp == null) return null;
  const side = (x: number) => `${x >= 0 ? g.home : g.away} by ${+Math.abs(x).toFixed(1)}`;
  const gap = (x: number) => (Math.abs(x) < 0.05 ? "0 pts" : signed(x, 1, " pts", 1));
  return (
    <section className="sec"><h2>Our read</h2>
      <div className="tbl"><table><thead><tr><th></th><th className="n">Market</th><th className="n">Our model</th><th className="n">Gap</th></tr></thead>
        <tbody>
          <tr><td>Margin</td><td className="n">{side(sp)}</td><td className="n">{side(m.margin)}</td><td className="n">{gap(m.margin - sp)} {m.margin - sp >= 0 ? g.home : g.away}</td></tr>
          {tot != null && <tr><td>Total</td><td className="n">{tot}</td><td className="n">{+(+m.total).toFixed(1)}</td><td className="n">{gap(m.total - tot)}</td></tr>}
        </tbody></table></div>
      <About>Our team model: each team&apos;s offense and defense per 100 possessions, adjusted for opponents, and pace, from the
        last 400 days with recent games counting most, plus rest. It has no weight in prices: there were no past NBA lines
        to test it on, so every read is logged and graded against the closing line and the result.
        {m.early ? " Early season: the ratings are mostly last season's, and rosters changed, so expect big gaps that mean little." : ""}</About>
      {outList(g)}
    </section>
  );
}

function nbaTape(g: Analysis): Fold[] {
  const m = g.model, rk = m?.ranks ?? {};
  const a = rk[g.away], h = rk[g.home];
  if (!m || !a || !h) return [];
  return [{ key: "tape", title: "Tale of the tape", body: (
    <div className="tape">
      <div className="hd">{g.away}</div><div className="k">at</div><div className="h hd">{g.home}</div>
      <div>{fixed(m.away_points, 1)}</div><div className="k">Points expected</div><div className="h">{fixed(m.home_points, 1)}</div>
      <div><span className="rk">{ord(a.off_ortg)}</span></div><div className="k">Offense</div><div className="h"><span className="rk">{ord(h.off_ortg)}</span></div>
      <div><span className="rk">{ord(a.def_ortg)}</span></div><div className="k">Defense</div><div className="h"><span className="rk">{ord(h.def_ortg)}</span></div>
      <div><span className="rk">{ord(a.pace)}</span></div><div className="k">Pace</div><div className="h"><span className="rk">{ord(h.pace)}</span></div>
      <div>{m.rest?.[g.away] == null ? "—" : `${m.rest[g.away]}d`}</div><div className="k">Rest</div><div className="h">{m.rest?.[g.home] == null ? "—" : `${m.rest[g.home]}d`}</div>
    </div>) }];
}

export function nbaFolds(g: Analysis): Fold[] {
  const lines: any[] = g.lines ?? [];
  if (!lines.length) {
    return [...nbaTape(g), { key: "lines", title: "Player lines", body: <p className="prose">FanDuel&apos;s player lines are priced 15 to 45 minutes
      before tip, once the starting lineups are out. They show up here then, with any lean, and the night&apos;s parlay tickets.</p> }];
  }
  const sorted = [...lines].sort((a, b) => Math.abs(num(b.gap) ?? 0) - Math.abs(num(a.gap) ?? 0));
  return [...nbaTape(g), { key: "lines", title: "Player lines", n: lines.length, body: <>
    <div className="tbl"><table><thead><tr><th>Player</th><th>FanDuel line</th><th className="n">Over / under</th><th className="n">Novig</th><th className="n">Market over</th>
      <th className="n">Our model</th><th className="n">Gap</th><th className="n hide-sm">Minutes</th></tr></thead>
      <tbody>{sorted.map((x) => <tr key={x.player + x.stat + x.line}>
        <td>{x.player} <span className="faint">{x.team ?? ""}</span>{x.day_to_day && <span className="tag warn" style={{ marginLeft: 6 }}>day-to-day</span>}</td>
        <td>{x.label ?? x.stat} {x.line}</td>
        <td className="n">{fmtAm(x.fd_over)} / {x.fd_under == null ? "—" : fmtAm(x.fd_under)}</td>
        <td className="n">{novigOu(x)}</td>
        <td className="n">{pct(x.p_market)}</td><td className="n">{pct(x.p_model)}</td>
        <td className={`n ${(num(x.gap) ?? 0) > 0 ? "pos" : (num(x.gap) ?? 0) < 0 ? "neg" : ""}`}>{signed(x.gap, 0, " pts")}</td>
        <td className="n hide-sm">{num(x.minutes) == null ? "—" : Math.round(num(x.minutes)!)}</td></tr>)}</tbody></table></div>
    <About>Market over is the no-vig chance at FanDuel&apos;s number, and it sets the price. Our model (minutes and per-minute rates from
      recent games, tonight&apos;s lineup) is shown for learning: it has no weight until it beats the market on logged lines.
      Sorted by the biggest gap.</About></> }];
}

// ------------------------------------------------------------------------------------- UFC

/** The UFC fight page (cards/analysis_ufc.py): segment, weight class and rounds. */
export function ufcMeta(g: Analysis): string[] {
  return [g.segment, g.title ? `${g.weight_class} title fight` : g.weight_class, g.rounds ? `${g.rounds} rounds` : null]
    .filter(Boolean) as string[];
}

const UFC_METHOD: [string, string][] = [["ko", "KO/TKO"], ["sub", "Submission"], ["dec", "Decision"]];

/** Each of Mike's books against the sharp no-vig moneyline, then how DraftKings prices the way it ends. */
export function ufcTop(g: Analysis): ReactNode {
  const rows: any[] = g.books ?? [];
  const dk = g.dk ?? {};
  const [a, b] = g.fighters ?? [];
  return (
    <>
      {rows.length > 0 && <section className="sec"><h2>The moneyline at your books vs. the sharp book</h2>
        <div className="tbl"><table><thead><tr><th>Fighter</th>{bookHeads(colsOf(g, UFC_COLS))}<th className="n">Sharp no-vig</th></tr></thead>
          <tbody>{rows.map((o) => <tr key={o.label}><td>{label(o.label)}</td>{bookCells(colsOf(g, UFC_COLS), o)}<td className="n">{pct(o.p_market)}</td></tr>)}</tbody></table></div>
        <About>From the latest pull ({rows[0].source}). Each book&apos;s price with its EV under it. The card&apos;s UFC bets come from here: a book lagging the sharp price, at the best of your books. A draw or no contest voids the moneyline.</About></section>}
      {dk.method && a && b && <section className="sec"><h2>How it ends (DraftKings)</h2>
        <div className="tbl"><table><thead><tr><th>Result</th><th className="n">{a.name}</th><th className="n">{b.name}</th></tr></thead>
          <tbody>{UFC_METHOD.map(([k, lab]) => <tr key={k}><td>{lab}</td>
            {(["a", "b"] as const).map((s) => { const c = dk.method[`${s}_${k}`]; return <td className="n" key={s}>{pct(c?.p)}<br /><span className="faint">{fmtAm(c?.price)}</span></td>; })}</tr>)}
            {dk.distance && <tr><td>Goes the distance</td><td className="n" colSpan={2}>{pct(dk.distance.p_yes)} <span className="faint">yes {fmtAm(dk.distance.yes)} / no {fmtAm(dk.distance.no)}</span></td></tr>}
            {dk.total && <tr><td>Over {dk.total.line} rounds</td><td className="n" colSpan={2}>{pct(dk.total.p_over)} <span className="faint">over {fmtAm(dk.total.over)} / under {fmtAm(dk.total.under)}</span></td></tr>}
          </tbody></table></div>
        <About>DraftKings&apos; prices from ESPN, as chances with the margin taken out. The six method outcomes carry about {pct(dk.method_margin)} of margin together (a moneyline about 4%), which is why we don&apos;t bet them: no edge showed on the fights we could check (Oct 23).</About></section>}
    </>
  );
}

function UfcTape({ a, b }: { a: any; b: any }) {
  const fm = (x: any) => x.form ?? {};
  const wins = (x: any) => { const w = fm(x).wins ?? {}; return fm(x).fights ? `${w.ko ?? 0} KO · ${w.sub ?? 0} sub · ${w.dec ?? 0} dec` : "—"; };
  const losses = (x: any) => { const l = fm(x).losses ?? {}; return fm(x).fights ? `${l.ko ?? 0} KO · ${l.sub ?? 0} sub · ${l.dec ?? 0} dec` : "—"; };
  const rows: [string, (x: any) => ReactNode][] = [
    ["Record", (x) => x.record ?? "—"], ["Age", (x) => x.age ?? "—"], ["Height", (x) => x.height ?? "—"],
    ["Reach", (x) => x.reach ?? "—"], ["Stance", (x) => x.stance ?? "—"], ["From", (x) => x.country ?? "—"],
    ["UFC fights since 2021", (x) => fm(x).fights ?? 0], ["Wins by", wins], ["Losses by", losses],
    ["Went the distance", (x) => pct(fm(x).distance)],
  ];
  return (
    <div className="tape">
      <div className="hd">{a.name}</div><div className="k">vs</div><div className="h hd">{b.name}</div>
      {rows.map(([lab, f]) => <Fragment key={lab}><div>{f(a)}</div><div className="k">{lab}</div><div className="h">{f(b)}</div></Fragment>)}
    </div>
  );
}

export function ufcFolds(g: Analysis): Fold[] {
  const [a, b] = g.fighters ?? [];
  if (!a || !b) return [];
  const last = (x: any) => (
    <div key={x.name}><b>{x.name}</b>
      {(x.form?.last ?? []).length ? <ul className="plain">{x.form.last.map((f: any) => (
        <li key={f.date + f.opponent}><span className={f.result === "W" ? "pos" : f.result === "L" ? "neg" : "faint"}>{f.result}</span> {f.opponent}
          <span className="faint"> · {f.method}{f.round ? `, round ${f.round}` : ""} · {f.date}</span></li>))}</ul>
        : <p className="faint">No UFC fights since 2021: a debut or a long layoff.</p>}
    </div>
  );
  const cr = g.class_rates;
  const mo = g.model, dk = g.dk ?? {};
  const debut = mo ? [mo.debut_a && a.name, mo.debut_b && b.name].filter(Boolean) : [];
  return [
    ...(g.story ? [{ key: "story", title: "How the fight goes", body: <p className="prose">{g.story}</p> }] : []),
    ...(mo ? [{ key: "model", title: "Our model (tracked, no weight)", body: <>
      <div className="tbl"><table><thead><tr><th></th><th className="n">Our model</th><th className="n">DraftKings no-vig</th></tr></thead>
        <tbody>
          <tr><td>{a.name} wins</td><td className="n">{pct(mo.p_a)}</td><td className="n">{pct(dk.ml?.p_a)}</td></tr>
          <tr><td>{b.name} wins</td><td className="n">{pct(mo.p_a == null ? null : 1 - mo.p_a)}</td><td className="n">{pct(dk.ml?.p_a == null ? null : 1 - dk.ml.p_a)}</td></tr>
          <tr><td>Goes the distance</td><td className="n">{pct(mo.p_dist)}</td><td className="n">{pct(dk.distance?.p_yes)}</td></tr>
        </tbody></table></div>
      {debut.length > 0 && <p className="faint">{debut.join(" and ")}: no UFC fights since 2021, so the model sees an average fighter. The market knows more.</p>}
      <About>Ratings and fight stats from ESPN&apos;s UFC results since 2021, fit on every earlier fight. Out of sample it beats a coin flip and Elo, but on the fights where we have DraftKings&apos; prices the market beat it clearly (log loss 0.642 vs 0.721, Oct 23), so it never moves a price or a pick. It&apos;s logged every card to keep score.</About></> }] : []),
    ...((g.same_fight ?? []).length ? [{ key: "sgp", title: "Same-fight parlays", n: g.same_fight.length, body: <>
      <div className="tbl"><table><thead><tr><th>Parlay</th><th className="n">Fair chance</th><th className="n">Fair odds</th><th className="n">Legs multiplied</th><th className="n">DraftKings single</th></tr></thead>
        <tbody>{g.same_fight.map((c: any) => <tr key={c.label}><td>{c.label}</td><td className="n">{pct(c.p)}</td>
          <td className="n">{c.fair_price == null ? "—" : fmtAm(c.fair_price)}</td><td className="n">{c.naive == null ? "—" : pct(c.naive)}</td>
          {c.dk_price == null ? <td className="n">—</td> : bookCell(c.dk_price, c.dk_ev)}</tr>)}</tbody></table></div>
      <About>Who wins is the sharp moneyline; how each fighter wins (finish or decision) is DraftKings&apos; method market with its margin taken out; when a finish comes is set so the parlays agree with the sharp total-rounds line (or, without one, every UFC finish since 2021 at this length). A same-game parlay is only worth it when the book pays more than the fair odds: type its quote into the Build tab. &quot;Legs multiplied&quot; is what you&apos;d get treating the legs as unrelated: the gap is why books price these themselves. A win by decision is the same bet as DraftKings&apos; points prop, priced next to it.</About></> }] : []),
    { key: "tape", title: "Tale of the tape", body: <UfcTape a={a} b={b} /> },
    { key: "last", title: "Last five fights", body: <div className="two">{last(a)}{last(b)}</div> },
    ...(cr ? [{ key: "class", title: `${g.weight_class} ${g.rounds}-rounders`, body: <>
      <p className="prose">Since 2021, {cr.n} UFC {String(g.weight_class).toLowerCase()} fights scheduled for {g.rounds} rounds: {pct(cr.distance)} went to the
        judges, {pct(cr.ko)} ended by KO/TKO and {pct(cr.sub)} by submission.</p>
      <About>ESPN&apos;s results for every UFC card since 2021. A base rate, not a prediction: who is fighting matters more than the class.</About></> }] : []),
  ];
}
