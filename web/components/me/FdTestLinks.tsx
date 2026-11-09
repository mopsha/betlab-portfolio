"use client";

import { useState } from "react";

const URL_NY = "https://ny.sportsbook.fanduel.com/";
// Round 2 (Oct 6: A-E all stayed in a browser). FanDuel publishes no app scheme, so these are
// guesses; a wrong one does nothing.
const SCHEMES = ["fanduelsportsbook://", "fdsb://", "fanduel://", "sportsbook-fanduel://"];

/** Five ways to open FanDuel; tap each from BetLab on the home screen and note which opens the app. */
type Offer = { label: string; matchup: string | null; url: string } | null;

/** Round 3 (Oct 6: F, fanduelsportsbook://, opened the app). Does the app take a bet through it? */
function round3(url: string) {
  const u = new URL(url);
  const tail = u.pathname + u.search;
  return [
    ["J", "fanduelsportsbook:/" + tail],
    ["K", "fanduelsportsbook://" + u.host + tail],
    ["L", "fanduelsportsbook://sportsbook.fanduel.com" + tail],
  ] as const;
}

export function FdTestLinks({ offer }: { offer: Offer }) {
  const [copied, setCopied] = useState(false);
  return (
    <>
      <section className="card settings">
        <p>Open BetLab from your home screen, then tap each button. Note which ones open the <b>FanDuel app</b>{" "}
          (not a web page), and tell Claude the letters.</p>
      </section>
      <section className="card settings">
        <div className="actions" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
          <a className="btn" href={URL_NY} target="_blank" rel="noopener">A · New tab (how it works today)</a>
          <a className="btn" href={URL_NY}>B · Same window</a>
          <button className="btn" onClick={() => { window.location.href = URL_NY; }}>C · Script redirect</button>
          <a className="btn" href={"x-safari-" + URL_NY}>D · Hand off to Safari</a>
          <button className="btn quiet" onClick={async () => {
            try { await navigator.clipboard.writeText(URL_NY); setCopied(true); } catch { setCopied(false); }
          }}>{copied ? "Copied: paste it in Safari" : "E · Copy the link"}</button>
        </div>
        <p className="faint">Also try pressing and holding button A: if the menu offers “Open in FanDuel Sportsbook”, that
          works today.</p>
      </section>
      <section className="card settings">
        <p><b>Round 2.</b> F-I try FanDuel&apos;s app directly. A wrong one does nothing or shows an error; that&apos;s fine.</p>
        <div className="actions" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
          {SCHEMES.map((s, i) => (
            <a key={s} className="btn" href={s}>{"FGHI"[i]} · {s}</a>
          ))}
        </div>
        <p className="faint">Then open this same page in Safari (not the home-screen app) and tap B there.</p>
      </section>
      <section className="card settings">
        <p><b>Round 3.</b> F opened the app. Now: does a bet come along? Each button should open FanDuel with this bet in
          the betslip. Don&apos;t place it, just look, then come back.</p>
        {offer ? (
          <>
            <p className="faint">{offer.label}{offer.matchup ? ` · ${offer.matchup}` : ""}</p>
            <div className="actions" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
              {round3(offer.url).map(([k, href]) => (
                <a key={k} className="btn" href={href}>{k} · {href.slice(0, 48)}…</a>
              ))}
            </div>
          </>
        ) : <p className="faint">No upcoming FanDuel bet with a link right now; check back after the morning run.</p>}
      </section>
    </>
  );
}
