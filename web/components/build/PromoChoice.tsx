"use client";

// A promo on the slip (the reorganization, Nov 5): it was a row of switches and fields above the markets; now it's one
// row in the slip that opens here. Wallet tokens first (the ones that fit this slip on top), then the same typed bonus
// bet / profit boost fields as before. Choosing one shows what the slip is worth with it; I placed this then saves the bet
// with the wallet token (its id and dollars, Nov 9), or as a bonus or boosted bet for a typed one.
import Link from "next/link";
import type { Promo } from "@/lib/builder";
import { fmtAm, parseOdds } from "@/lib/format";
import { asPromo, promoTerms, type PromoRow } from "@/lib/promos";
import { kindName, tokenValueText } from "@/lib/wallet-view";
import { BookMark, Ends, useNow } from "@/components/promos/Token";

const BOOSTS = [25, 30, 50, 100];
type Term = "stake" | "maxExtra" | "minLegs" | "minOdds" | "maxOdds";

export function PromoChoice({ promo, setPromo, tokens, tokenId, setTokenId, fromLink, onDone }: {
  promo: Promo; setPromo: (p: Promo) => void; tokens: { p: PromoRow; fits: boolean }[]; tokenId: string | null;
  setTokenId: (id: string | null) => void; fromLink: boolean; onDone: () => void;
}) {
  const now = useNow();
  // a token's terms (stake, extra winnings cap, fewest legs, shortest odds), typed as the book states them
  const setTerm = (key: Term, text: string) => {
    if (promo.kind === "none") return;
    const n = key === "minOdds" || key === "maxOdds" ? parseOdds(text) : Number(text.replace(/[^0-9.]/g, ""));
    setTokenId(null);
    setPromo({ ...promo, [key]: text.trim() && n != null && Number.isFinite(n) && n !== 0 ? n : undefined });
  };
  const term = (key: Term, label: string, hint: string) => promo.kind !== "none" && (
    <label className="bd-term"><span>{label}</span>
      <input inputMode={key === "minOdds" || key === "maxOdds" ? "text" : "decimal"} aria-label={label} placeholder={hint}
             defaultValue={promo[key] == null ? "" : key === "minOdds" || key === "maxOdds" ? fmtAm(promo[key]) : String(promo[key])}
             onBlur={(ev) => setTerm(key, ev.target.value)} />
    </label>
  );
  const kind = (k: Promo["kind"]) => {
    const t = promo.kind === "none" ? {} : { stake: promo.stake, minLegs: promo.minLegs, minOdds: promo.minOdds };
    setTokenId(null);
    setPromo(k === "boost" ? { ...t, maxExtra: promo.kind === "boost" ? promo.maxExtra : undefined, kind: "boost", pct: promo.kind === "boost" ? promo.pct : 50 }
      : k === "bonus" ? { ...t, kind: "bonus" } : { kind: "none" });
  };
  return (
    <div className="bd-promo-pick">
      {tokens.length > 0 && (
        <div className="bd-toks" role="group" aria-label="Your wallet">
          <span className="cap">From your wallet</span>
          {tokens.map(({ p, fits }) => (
            <button key={p.promo_id} type="button" className={`bd-tok${fits ? "" : " nofit"}`} aria-pressed={tokenId === p.promo_id}
                    onClick={() => { setTokenId(p.promo_id); setPromo(asPromo(p)); }}>
              <BookMark book={p.book} size={32} />
              <span className="bd-tok-what">
                <b>{kindName(p.kind)}{p.book ? ` · ${p.book}` : ""}</b>
                <span className="sub">{fits ? "Fits this slip" : "Doesn't fit this slip as it stands"}{promoTerms(p) ? ` · ${promoTerms(p)}` : ""}</span>
                <Ends p={p} now={now} />
              </span>
              <span className="numx bd-tok-v">{tokenValueText(p)}</span>
            </button>
          ))}
        </div>
      )}

      <div className="bd-typed">
        <span className="cap">{tokens.length ? "Or type one" : "Type a promo"}</span>
        <div className="bd-kinds" role="group" aria-label="Promo">
          {([["none", "No promo"], ["bonus", "Bonus bet"], ["boost", "Profit boost"]] as const).map(([k, t]) => (
            <button key={k} type="button" className="mk" aria-pressed={promo.kind === k && (k === "none" || !tokenId)} onClick={() => kind(k)}>{t}</button>
          ))}
        </div>
        {promo.kind === "boost" && (
          <div className="bd-boosts">
            {BOOSTS.map((b) => (
              <button key={b} type="button" className="mk" aria-pressed={promo.pct === b} onClick={() => { setTokenId(null); setPromo({ ...promo, kind: "boost", pct: b }); }}>{b}%</button>
            ))}
            <label className="bd-term">
              <input inputMode="numeric" aria-label="Boost percent" value={BOOSTS.includes(promo.pct) ? "" : String(promo.pct)} placeholder="Other"
                     onChange={(ev) => { const n = Number(ev.target.value.replace(/[^0-9.]/g, "")); if (n > 0 && n <= 500) { setTokenId(null); setPromo({ ...promo, kind: "boost", pct: n }); } }} /><span>%</span>
            </label>
          </div>
        )}
        {promo.kind !== "none" && (
          <div className="bd-terms" key={`${promo.kind}${tokenId ?? ""}${fromLink ? "-link" : ""}`}>
            {term("stake", promo.kind === "bonus" ? "Bonus $" : "Stake $", "10")}
            {promo.kind === "boost" && term("maxExtra", "Max extra winnings $", "none")}
            {term("minLegs", "Min legs", "any")}
            {term("minOdds", "Min odds", "any")}
            {term("maxOdds", "Max odds", "any")}
          </div>
        )}
      </div>

      <p className="sub">Want the best bet for a token instead? <Link href={tokenId ? `/build/promo?promo_id=${encodeURIComponent(tokenId)}` : "/build/promo"}>Use a promo ›</Link>
        {tokenId ? " I placed this saves the bet at the token's dollars and takes it out of your wallet." : ""}</p>
      <button type="button" className="btn quiet bd-promo-done" onClick={onDone}>Done</button>
    </div>
  );
}
