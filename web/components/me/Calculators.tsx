"use client";

import { useMemo, useState } from "react";
import { fmtAm, implied, MINUS, parseOdds, pct, signed, toAm, toDec } from "@/lib/format";

// The Learn tab's calculators, ported from the old page with the same math.
const ev = (p: number, a: number) => p * (toDec(a) - 1) - (1 - p);
const kelly = (p: number, a: number) => { const b = toDec(a) - 1; return Math.max(0, (b * p - (1 - p)) / b); };
function bisect(f: (x: number) => number, lo: number, hi: number) {
  for (let i = 0; i < 80; i++) { const m = (lo + hi) / 2; if (f(lo) * f(m) <= 0) hi = m; else lo = m; }
  return (lo + hi) / 2;
}
/** No-vig chances by the power method (takes more of the vig off the underdog), as BetLab prices. */
export function devigPower(prices: number[]) {
  const imp = prices.map(implied), tot = imp.reduce((a, b) => a + b, 0);
  if (Math.abs(tot - 1) < 1e-9) return imp;
  const k = bisect((k) => imp.reduce((s, p) => s + p ** k, 0) - 1, 0.01, 50);
  return imp.map((p) => p ** k);
}
const n = (v: string) => Number(String(v).replace(MINUS, "-"));
const usd = (v: number) => (v < 0 ? MINUS : "") + "$" + Math.abs(v).toFixed(2);

type Out = [string, string, string?][];

function Calc({ title, fields, run, say }: {
  title: string; fields: [string, string, string?][]; run: (v: Record<string, string>) => Out; say?: (v: Record<string, string>) => string;
}) {
  const [v, setV] = useState<Record<string, string>>(Object.fromEntries(fields.map(([k, , d]) => [k, d ?? ""])));
  let out: Out;
  try { out = run(v); } catch { out = [["Enter", "the fields above"]]; }
  return (
    <div className="calc">
      <span className="section-label" style={{ margin: 0 }}>{title}</span>
      <div className="calc-fields">
        {fields.map(([k, l]) => (
          <label key={k} className="field">{l}<input inputMode="text" value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} /></label>
        ))}
      </div>
      <div className="calc-out">{out.map(([k, val, cls]) => <div key={k}><span className="faint">{k}</span><b className={`mono ${cls ?? ""}`}>{val}</b></div>)}</div>
      {say && <p className="faint">{say(v)}</p>}
    </div>
  );
}

export function OddsCalc() {
  return <Calc title="Odds converter" fields={[["a", "American odds", "-110"]]}
    run={(v) => { const a = parseOdds(v.a); if (a == null) return [["Enter odds", "like −110 or +150"]]; const d = toDec(a);
      return [["Decimal", d.toFixed(3)], ["Break-even", pct(1 / d, 1)], ["Profit on $10", usd(10 * (d - 1))]]; }}
    say={(v) => { const a = parseOdds(v.a); if (a == null) return ""; const be = pct(1 / toDec(a), 1);
      return a < 0 ? `Risk $${Math.abs(a)} to win $100. You need to win ${be} of these bets to break even.` : `Risk $100 to win $${a}. You need to win ${be} of these bets to break even.`; }} />;
}

export function VigCalc() {
  return <Calc title="No-vig calculator" fields={[["a", "Side A", "-110"], ["b", "Side B", "-110"], ["c", "Draw (soccer)", ""]]}
    run={(v) => { const ps = [v.a, v.b, v.c].map(parseOdds); const used = ps[2] == null ? ps.slice(0, 2) : ps;
      if (used.some((p) => p == null)) return [["Enter prices", "like −110"]];
      const pr = used as number[], tot = pr.map(implied).reduce((a, b) => a + b, 0), fair = devigPower(pr), names = ["A", "B", "Draw"];
      return [["Implied total", pct(tot, 1)], ["Book's hold", pct(1 - 1 / tot, 2)], ...fair.map((p, i) => [`Fair ${names[i]}`, `${pct(p, 1)} · ${fmtAm(toAm(1 / p))}`] as [string, string])]; }} />;
}

export function EvCalc() {
  return <Calc title="EV calculator" fields={[["p", "Win chance %", "55"], ["a", "Price", "-110"]]}
    run={(v) => { const p = n(v.p) / 100, a = parseOdds(v.a); if (!(p > 0 && p < 1) || a == null) return [["Enter", "a chance and a price"]];
      const e = ev(p, a); return [["EV per $1", signed(e), e >= 0 ? "pos" : "neg"], ["Break-even", pct(implied(a), 1)], ["Fair price", fmtAm(toAm(1 / p))], ["Per $100 staked", (e >= 0 ? "+" : "") + usd(e * 100)]]; }} />;
}

/** Quarter-Kelly in units, taking 1u as 1% of the money set aside (BetLab's staking), capped at 2u. */
export function UnitsCalc() {
  return <Calc title="Stake sizing" fields={[["p", "Win chance %", "54"], ["a", "Price", "-110"]]}
    run={(v) => { const p = n(v.p) / 100, a = parseOdds(v.a);
      if (!(p > 0 && p < 1) || a == null) return [["Enter", "a chance and a price"]];
      const k = kelly(p, a), qk = Math.min(2, k / 4 / 0.01);
      return [["Edge", k > 0 ? "yes" : "none: skip it", k > 0 ? "pos" : "neg"], ["¼-Kelly (cap 2u)", `${qk.toFixed(2)}u`], ["Flat bet", "1u"], ["Daily cap", "5u"]]; }} />;
}

export function ClvCalc() {
  return <Calc title="CLV calculator" fields={[["bet", "Price you got", "-105"], ["a", "Close, your side", "-125"], ["b", "Close, other side", "+105"]]}
    run={(v) => { const [bet, a, b] = [v.bet, v.a, v.b].map(parseOdds); if ([bet, a, b].some((x) => x == null)) return [["Enter", "three prices"]];
      const fair = devigPower([a!, b!])[0], c = ev(fair, bet!);
      return [["Fair close (your side)", pct(fair, 1)], ["Fair close price", fmtAm(toAm(1 / fair))], ["Your CLV", signed(c), c >= 0 ? "pos" : "neg"]]; }} />;
}

export function ParlayCalc() {
  return <Calc title="Parlay math (up to 4 legs)" fields={[["1", "Leg 1", "-110"], ["2", "Leg 2", "-110"], ["3", "Leg 3", "-110"], ["4", "Leg 4", "-110"]]}
    run={(v) => { const legs = ["1", "2", "3", "4"].map((k) => parseOdds(v[k])).filter((x): x is number => x != null);
      if (legs.length < 2) return [["Enter", "at least two legs"]];
      const dec = legs.reduce((m, a) => m * toDec(a), 1), fairP = legs.reduce((m, a) => m * implied(a) / 1.0476, 1), e = fairP * dec - 1;
      return [["Parlay pays", fmtAm(toAm(dec))], ["Fair price", fmtAm(toAm(1 / fairP))], ["Chance to hit", pct(fairP, 1)], ["Book's edge", signed(-e), "neg"]]; }}
    say={() => "Assumes each leg is a standard −110/−110 market with the vig removed, and that legs are independent."} />;
}

export function BonusCalc() {
  return <Calc title="Bonus bet value" fields={[["amt", "Bonus bet $", "10"], ["a", "Price", "+300"], ["p", "Fair win %", "24"]]}
    run={(v) => { const amt = n(v.amt), a = parseOdds(v.a), p = n(v.p) / 100; if (!(amt > 0 && p > 0 && p < 1) || a == null) return [["Enter", "all three fields"]];
      const val = amt * p * (toDec(a) - 1); return [["Cash value", usd(val)], ["Kept", pct(val / amt) + " of face value"], ["If it wins", usd(amt * (toDec(a) - 1))]]; }} />;
}

function mulberry32(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

/** 40 bettors with the same true edge: how many are still behind after N bets. Seeded, so the first view is stable. */
export function VarianceSim() {
  const [p, setP] = useState("55"), [a, setA] = useState("-110"), [nb, setN] = useState("300"), [seed, setSeed] = useState(7);
  const res = useMemo(() => {
    const pp = n(p) / 100, aa = parseOdds(a), N = Math.min(3000, Math.max(10, Math.round(n(nb))));
    if (!(pp > 0 && pp < 1) || aa == null || !N) return null;
    const rnd = mulberry32(seed), win = toDec(aa) - 1, runs: number[][] = [];
    for (let r = 0; r < 40; r++) { let u = 0; const path = [0]; for (let i = 0; i < N; i++) { u += rnd() < pp ? win : -1; path.push(u); } runs.push(path); }
    return { runs, N, e1: pp * win - (1 - pp) };
  }, [p, a, nb, seed]);
  const W = 640, H = 220, L = 44, R = 12, T = 12, B = 24;
  let svg = null, sayText = "";
  if (res) {
    const all = res.runs.flat(); let lo = Math.min(...all, 0), hi = Math.max(...all, 0);
    const span = hi - lo, step = span <= 20 ? 5 : span <= 60 ? 10 : span <= 150 ? 25 : 50;
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const X = (i: number) => L + (i / res.N) * (W - L - R), Y = (v: number) => T + ((hi - v) / (hi - lo || 1)) * (H - T - B);
    const ticks = []; for (let v = lo; v <= hi + 1e-9; v += step) ticks.push(v);
    const every = Math.max(1, Math.floor(res.N / 200));
    svg = (
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Forty simulated bettors, in units">
        {ticks.map((v) => <g key={v}><line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="var(--line)" strokeWidth={v === 0 ? 1.5 : 1} /><text x={L - 8} y={Y(v) + 4} textAnchor="end">{v > 0 ? "+" : v < 0 ? MINUS : ""}{Math.abs(v)}u</text></g>)}
        {res.runs.map((path, r) => { let d = ""; for (let i = 0; i <= res.N; i += every) d += `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(path[i]).toFixed(1)}`;
          return <path key={r} d={d} fill="none" stroke={path[res.N] < 0 ? "var(--neg)" : "var(--ink-2)"} strokeOpacity={0.45} strokeWidth={1} />; })}
        <path d={`M${X(0)},${Y(0)}L${X(res.N)},${Y(res.e1 * res.N)}`} stroke="var(--accent)" strokeWidth={2.5} strokeDasharray="6 4" fill="none" />
        <text x={W - R} y={H - 6} textAnchor="end">bet {res.N}</text>
      </svg>
    );
    const behind = res.runs.filter((r) => r[res.N] < 0).length;
    sayText = `Expected: ${signed(res.e1 * res.N, 1, "u", 1)} after ${res.N} bets (dashed). ${behind} of 40 bettors with exactly this edge were still behind (red).${res.e1 < 0 ? " With no edge, the vig wins in the long run." : ""}`;
  }
  return (
    <div className="calc">
      <span className="section-label" style={{ margin: 0 }}>Simulate 40 bettors with the same edge</span>
      <div className="calc-fields">
        <label className="field">True win %<input value={p} onChange={(e) => setP(e.target.value)} /></label>
        <label className="field">Price<input value={a} onChange={(e) => setA(e.target.value)} /></label>
        <label className="field">Bets each<input value={nb} onChange={(e) => setN(e.target.value)} /></label>
        <button className="btn quiet" type="button" onClick={() => setSeed(seed + 1)} style={{ alignSelf: "end" }}>Run again</button>
      </div>
      {svg}
      <p className="faint">{sayText}</p>
    </div>
  );
}
