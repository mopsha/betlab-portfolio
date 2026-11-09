"use client";

import { DK_HOST, outcomeId } from "@/lib/draftkings";

type Offer = { label: string; matchup: string | null; url: string };

// Round 1: what opens DraftKings' app from the home-screen app at all? FanDuel's web links never left the
// browser (Oct 6) and only its app scheme worked, so these try DraftKings' likely schemes. DraftKings publishes
// none; a wrong one does nothing or shows an error.
const SCHEMES = ["dksb://", "draftkings://", "dksportsbook://"];

/** Round 2: does one bet land in the betslip? The web link as the feed gives it, then app-scheme guesses. */
function round2(url: string, id: string) {
  const u = new URL(url);
  return [
    ["E", url, true],
    ["F", `dksb://sb/addbet/${id}`, false],
    ["G", `dksb://${u.host}${u.pathname}${u.search}`, false],
    ["H", `draftkings://${u.host}${u.pathname}${u.search}`, false],
  ] as const;
}

/** Round 3: do two bets from different games land as one parlay? Formats betslip-sharing sites use. */
function round3(a: string, b: string) {
  return [
    ["I", `${DK_HOST}/?outcomes=${a}+${b}`],
    ["J", `${DK_HOST}/?outcomes=${a}%2B${b}`],
    ["K", `${DK_HOST}/?outcomes=${a},${b}`],
    ["L", `${DK_HOST}/?outcomes=${a}&outcomes=${b}`],
  ] as const;
}

export function DkTestLinks({ offers }: { offers: Offer[] }) {
  const first = offers[0];
  const id = first ? outcomeId(first.url) : null;
  const ids = offers.slice(0, 2).map((o) => outcomeId(o.url)).filter((x): x is string => !!x);
  return (
    <>
      <section className="card settings">
        <p>Open BetLab from your home screen, then tap each button. Note what each one does (opens the <b>DraftKings
          app</b>, a web page, or nothing) and tell Claude the letters. Don&apos;t place anything: just look, then come back.</p>
      </section>
      <section className="card settings">
        <p><b>Round 1.</b> Which one opens the DraftKings app?</p>
        <div className="actions" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
          <a className="btn" href={`${DK_HOST}/`} target="_blank" rel="noopener">A · Web link (how it works today)</a>
          {SCHEMES.map((s, i) => <a key={s} className="btn" href={s}>{"BCD"[i]} · {s}</a>)}
        </div>
        <p className="faint">Also press and hold A: if the menu offers “Open in DraftKings”, that works today.</p>
      </section>
      <section className="card settings">
        <p><b>Round 2.</b> Does this bet land in the betslip?</p>
        {first && id ? (
          <>
            <p className="faint">{first.label}{first.matchup ? ` · ${first.matchup}` : ""}</p>
            <div className="actions" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
              {round2(first.url, id).map(([k, href, web]) => (
                <a key={k} className="btn" href={href} {...(web ? { target: "_blank", rel: "noopener" } : {})}>{k} · {href.slice(0, 46)}…</a>
              ))}
            </div>
          </>
        ) : <p className="faint">No upcoming DraftKings bet with a link right now; check back after the morning run.</p>}
      </section>
      <section className="card settings">
        <p><b>Round 3.</b> Do these two bets land together, as a parlay?</p>
        {ids.length === 2 ? (
          <>
            <p className="faint">{offers[0].label} · {offers[1].label}</p>
            <div className="actions" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
              {round3(ids[0], ids[1]).map(([k, href]) => (
                <a key={k} className="btn" href={href} target="_blank" rel="noopener">{k} · {href.slice(0, 46)}…</a>
              ))}
            </div>
            <p className="faint">If a round-2 app link worked, try the winner of this round there too and say so.</p>
          </>
        ) : <p className="faint">Needs two upcoming DraftKings bets from different games; check back after the morning run.</p>}
      </section>
    </>
  );
}
