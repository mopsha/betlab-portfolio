"use client";

// The slip (the reorganization, Nov 5): a sheet on phones, a pinned column on wide screens. Top to bottom: the grade,
// the legs, three numbers, the price at each book, a promo, then the actions. The price boxes are the same typed
// prices as before (one per book now, so both can sit side by side) and Novig's exact price from its pricer.
import { useState, type ReactNode } from "react";
import { mainLineText } from "@/lib/fanduel";
import { DEFAULT_BANDS, gradeClass, promoEv, promoFits, type Band, type BuildBook, type Evaluation, type PackLeg, type Promo,
  type QuoteModel, type SlipLeg } from "@/lib/builder";
import { BUILD_BOOKS } from "@/lib/build-view";
import { useMyBooks } from "@/components/app/MyBooks";
import type { MarkInput } from "@/lib/actions";
import type { Bet } from "@/lib/data";
import { fmtAm, label as nice, MINUS, pct, signed, toAm, toDec } from "@/lib/format";
import { novigSlipLink, type NovigQuote } from "@/lib/novig";
import type { PromoRow } from "@/lib/promos";
import { Art, type ArtOf } from "@/components/ui/Art";
import { BookLink } from "@/components/ui/BookLink";
import { MarkButton } from "@/components/live/MarkButton";
import { BookMark } from "@/components/promos/Token";
import { PromoChoice } from "@/components/build/PromoChoice";

export type NovigState = { state: "few" | "unlisted" | "asking" | "priced" | "refused"; q: NovigQuote | null };

export type SlipProps = {
  legs: SlipLeg[]; prices: Partial<Record<BuildBook, string>>; nGames: number; ready: boolean;
  book: BuildBook; setBook: (b: BuildBook) => void; setPrice: (b: BuildBook, text: string) => void;
  leg: (l: SlipLeg) => PackLeg | undefined; matchupOf: (eid: string) => string | undefined; legArt: (l: SlipLeg) => ArtOf | null;
  evals: Record<BuildBook, Evaluation | null>; known: Record<BuildBook, number | null>;
  /** the book that pays most among the known prices; `compared`: two or more books have a price, so "best" means something */
  best: BuildBook | null; compared: boolean;
  notHere: string[]; nv: NovigState; nvIds: string[] | null;
  bands: Band[] | null; quoteModel: QuoteModel | null;
  promo: Promo; setPromo: (p: Promo) => void; tokens: { p: PromoRow; fits: boolean }[]; tokenId: string | null;
  setTokenId: (id: string | null) => void; fromLink: boolean;
  toggle: (eid: string, label: string) => void; clear: () => void; close: () => void;
  saved: { grade: string | null; price: number | null } | undefined; bet: Bet | undefined; markInput: MarkInput | null;
  save: () => void; place: () => void; pending: boolean; real: boolean; msg: string | null;
};

/** What a book would likely pay an untyped same-game slip: its usual share of fair, never more than the legs' product. */
const likely = (e: Evaluation, bands: Band[]) => Math.min(Math.min(e.typical, Math.max(...bands.map((b) => Number(b.ratio)))) / e.p, e.naive);

export function SlipPanel(s: SlipProps) {
  const [promoOpen, setPromoOpen] = useState(false);
  const bands = s.bands ?? DEFAULT_BANDS;
  const e = s.evals[s.book];
  const any = e ?? BUILD_BOOKS.map((b) => s.evals[b]).find(Boolean) ?? null;
  const myBooks = useMyBooks();                                                   // the account's books on (Nov 6)      // the chance is the same at every book
  const plain = (x: Evaluation) => x.games.length === s.legs.length;              // one leg per game: it pays the legs' product
  const n = s.legs.length;

  if (!n) {
    return (
      <div className="bd-panel empty"><b>No legs yet</b><span>Tap a price to start a parlay. Legs from more than one game make an SGP+.</span>
        {s.promo.kind !== "none" && <span>Your {s.promo.kind === "bonus" ? "bonus bet" : `${s.promo.pct}% profit boost`} is ready: the slip shows what it&apos;s worth.</span>}</div>
    );
  }

  const bestPrice = s.best ? s.known[s.best] : null;
  const top = s.compared ? s.best : null;          // the box to mark
  const edge = any && bestPrice != null ? any.p * toDec(bestPrice) - 1 : null;

  const box = (b: BuildBook) => {
    const ev = s.evals[b];
    let value: ReactNode, note: ReactNode;
    if (b === "Novig") {
      const q = s.nv.q;
      value = <span className={`numx bd-pbox-v${top === b ? " pos" : ""}`}>{s.nv.state === "priced" && q ? fmtAm(q.price) : "—"}</span>;
      note = s.nv.state === "few" ? "2+ legs" : s.nv.state === "unlisted" ? "a leg isn't there" : s.nv.state === "asking" ? "asking…"
        : s.nv.state === "priced" ? (q?.stake_max != null ? `exact · up to $${Math.floor(q.stake_max)}` : "exact") : "no price now";
    } else {
      const hint = !s.ready ? "…" : !ev ? "—" : plain(ev) ? fmtAm(Math.round(toAm(ev.naive))) : "type it";
      value = <input className="numx" aria-label={`${b} ${s.nGames > 1 ? "SGP+" : "SGP"} price`} value={s.prices[b] ?? ""} placeholder={hint}
                     inputMode="text" autoComplete="off" disabled={s.ready && !ev} onChange={(x) => s.setPrice(b, x.target.value)} />;
      note = !s.ready ? "pricing…" : !ev ? "a leg isn't there"
        : ev.typed != null ? <span className={ev.p * toDec(ev.typed) >= 1 ? "pos" : "neg"}>EV {((ev.p * toDec(ev.typed) - 1) * 100).toFixed(1).replace("-", MINUS)}%</span>
        : plain(ev) ? "the legs' product" : `likely about ${fmtAm(Math.round(toAm(likely(ev, bands))))}`;
    }
    return (
      <div key={b} className={`bd-pbox${top === b ? " best" : ""}${s.book === b ? " on" : ""}`}>
        <button type="button" className="bd-pbox-h" aria-pressed={s.book === b} onClick={() => s.setBook(b)} aria-label={`${b}${s.book === b ? ", the book this slip is for" : ": build this slip there"}`}>
          <BookMark book={b} size={20} /><span>{b}</span>
        </button>
        {value}
        <small>{top === b && <em>Best</em>}{note}</small>
      </div>
    );
  };

  // the promo's worth at this book: the typed price, the legs' product, or the likely price until one is typed
  const promoLine = (() => {
    if (s.promo.kind === "none" || !e) return null;
    const dec = e.typed != null ? toDec(e.typed) : plain(e) ? e.naive : likely(e, bands);
    const v = promoEv(e.p, dec, s.promo);
    const stake = s.promo.stake;
    const text = (stake ? `${v < 0 ? MINUS : "+"}$${Math.abs(v * stake).toFixed(2)} · ` : "")
      + (s.promo.kind === "bonus" ? `keeps ${(v * 100).toFixed(0)}%` : `EV ${(v * 100).toFixed(1).replace("-", MINUS)}%`);
    return (
      <>
        <b className={`numx ${v >= (s.promo.kind === "bonus" ? 0.6 : 0) ? "pos" : "neg"}`}>{text}</b>
        {" "}{e.typed != null ? `at ${fmtAm(e.typed)}` : plain(e) ? `at ${fmtAm(toAm(dec))}, the legs' product` : `at the likely ${fmtAm(toAm(dec))}; type the real price`}
        {!promoFits(s.promo, n, dec) && <span className="neg"> · outside the token's terms</span>}
      </>
    );
  })();
  const promoName = s.promo.kind === "bonus" ? "Bonus bet" : s.promo.kind === "boost" ? `${s.promo.pct}% profit boost` : "";
  const fit = s.tokens.find((t) => t.fits)?.p;
  const waiting = s.tokens.length
    ? `${s.tokens.length} waiting${fit ? ` · ${fit.kind === "boost" ? `a ${fit.pct}% boost` : `a $${fit.amount_dollars ?? ""} bonus bet`.replace("$ ", "")} fits this slip` : ""}`
    : "A bonus bet or a profit boost";
  const main = s.book !== "Novig" ? mainLineText(s.legs.map((l) => { const x = s.leg(l); return x?.link && x.link_main; }), s.book) : null;
  const savedText = s.saved && e ? (s.saved.grade === e.grade && s.saved.price === e.typed ? "Saved" : "Update") : "Save";

  return (
    <div className="bd-panel">
      <span className="bd-grab" aria-hidden />
      <div className="bd-slip-head">
        <div>
          <h2>Your slip</h2>
          <span className="sub">{n} leg{n === 1 ? "" : "s"} · {s.nGames > 1 ? `${s.nGames} games` : "one game"} · <button type="button" className="bd-clear" onClick={s.clear}>Clear</button></span>
        </div>
        <span className="bd-slip-tools">
          {e && <span className={`bd-grade ${gradeClass(e.idx)}`} role="img" aria-label={`Grade ${e.grade}${e.provisional ? ", provisional" : ""}`}>{e.grade}</span>}
          <button type="button" className="ib bd-close" aria-label="Close your slip" onClick={s.close}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg></button>
        </span>
      </div>

      <ul className="bd-legs">
        {s.legs.map((l) => {
          const x = s.leg(l), a = s.legArt(l);
          return (
            <li key={l.event_id + l.label}>
              {a ? <Art {...a} size={38} className="disc" /> : <span className="art mg disc" style={{ ["--art" as string]: "38px" }} aria-hidden />}
              <span className="bd-leg-what">
                <b>{nice(l.label)}</b>
                <span className="sub">{x ? `${pct(x.p)} chance` : "…"}{s.nGames > 1 && s.matchupOf(l.event_id) ? ` · ${s.matchupOf(l.event_id)}` : ""}</span>
              </span>
              <span className="numx">{!x ? "…" : x.unavailable ? <span className="sub neg">not at {s.book}</span> : fmtAm(x.price)}</span>
              <button type="button" className="bd-rm" aria-label={`Remove ${l.label}`} onClick={() => s.toggle(l.event_id, l.label)}>✕</button>
            </li>
          );
        })}
      </ul>

      {!any ? <p className="sub">{!s.ready ? "Pricing…" : "Can't price these legs together."}</p> : (
        <>
          <div className="cells">
            <div><small>Chance</small><b>{pct(any.p, 1)}</b></div>
            <div><small>Fair price</small><b>{fmtAm(any.fair)}</b></div>
            <div><small>{top ? "Edge at best" : bestPrice != null ? `Edge at ${fmtAm(bestPrice)}` : "Edge"}</small><b className={edge == null ? "" : edge >= 0 ? "pos" : "neg"}>{edge == null ? "—" : signed(edge)}</b></div>
          </div>

          <div>
            <div className="cap bd-cap">The price at each book</div>
            <div className="bd-pboxes">{BUILD_BOOKS.filter((b) => myBooks.includes(b)).map(box)}</div>
            {top && top !== s.book && s.evals[top] && <p className="sub bd-hint">{top} pays most. Tap its name to build this slip there.</p>}
            {!e && s.ready && s.notHere.length > 0 && (
              <p className="sub bd-hint">{s.book} doesn&apos;t post {s.notHere.length === 1 ? "this leg" : "these legs"}{s.book === "DraftKings" ? " at this number" : ""}: {s.notHere.map(nice).join(", ")}.
                Swap {s.notHere.length === 1 ? "it" : "them"} or build it at another book.</p>
            )}
            {s.nv.state === "refused" && <p className="sub bd-hint">No Novig market maker priced these legs together just now. Some same-game pairs aren&apos;t allowed
              (two of one line, a stat inside another on one player); try again or swap a leg.</p>}
          </div>

          <div className={`bd-promo${promoOpen ? " open" : ""}`}>
            <button type="button" className="bd-promo-row" aria-expanded={promoOpen} onClick={() => setPromoOpen(!promoOpen)}>
              <span><b>{promoName || "Add a promo"}</b><span className="sub">{promoName ? promoLine ?? "Chosen: its value shows once the slip prices" : waiting}</span></span>
              <span className="chev" aria-hidden>{promoOpen ? "⌄" : "›"}</span>
            </button>
            {promoOpen && <PromoChoice promo={s.promo} setPromo={s.setPromo} tokens={s.tokens} tokenId={s.tokenId} setTokenId={s.setTokenId}
                                       fromLink={s.fromLink} onDone={() => setPromoOpen(false)} />}
          </div>

          {e && (
            <>
              <div className="bd-acts">
                {s.bet && s.markInput ? <MarkButton marked mine={s.bet} input={s.markInput} />
                  : <button type="button" className="btn bd-cta" disabled={s.pending} onClick={s.place}>{s.pending ? "Saving…" : s.real ? `I placed this at ${s.book}` : "Mark as mine"}</button>}
                <span className="bd-acts-side">
                  <BookLink book={s.book} icon links={s.book === "Novig" ? [s.nvIds ? novigSlipLink(s.nvIds) : null] : s.legs.map((l) => s.leg(l)?.link)} />
                  <button type="button" className="btn quiet" disabled={s.pending || savedText === "Saved"} onClick={s.save}>{savedText}</button>
                </span>
              </div>
              {main && <p className="sub">{main}</p>}
              {s.msg && <p className="err" role="alert">{s.msg}</p>}
              <details className="more">
                <summary>Why this grade</summary>
                <div className="more-body">
                  <p>{e.why}</p>
                  <p>The legs alone would pay <b className="mono">{fmtAm(toAm(e.naive))}</b>; together they hit <b className="mono">{e.lift.toFixed(2)}×</b> as often as separate bets would.</p>
                  <ul className="bd-notes">
                    {[...e.notes, ...e.rules.map((r) => "Your rule: " + r)].map((x) => <li key={x}>{x}</li>)}
                    {!e.notes.length && !e.rules.length && <li>No leg flagged, and your rules all hold.</li>}
                  </ul>
                  <ul className="legs">
                    {e.legs.map((l) => (
                      <li key={l.event_id + l.label}>
                        <span>{nice(l.label)}<br /><span className="faint">fair {pct(l.p)} ({fmtAm(toAm(1 / l.p))}) · {s.book} pays {(l.p * toDec(l.price) * 100).toFixed(0)}% of fair{l.source ? ` · ${l.source}` : ""}</span></span>
                        <span className="lp">{fmtAm(l.price)}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="faint">The grade compares {s.book === "DraftKings" ? "DraftKings'" : s.book === "Novig" ? "Novig's exact" : "FanDuel's"} price with what {s.quoteModel ? `FanDuel usually pays a slip like this${s.book === "DraftKings" ? " (FanDuel's pattern stands in until about 40 DraftKings quotes are typed)" : ""}` : "parlays this size usually pay"} ({(e.typical * 100).toFixed(0)}% of fair), then checks each leg's price, whether the legs help each other, and your rules.</p>
                </div>
              </details>
            </>
          )}
        </>
      )}
    </div>
  );
}
