import { booksOff, type Bet, type Leg, type Ticket } from "@/lib/data";
import { onBooks, type Book } from "@/lib/books";
import { dkHref } from "@/lib/draftkings";
import { BookLink } from "@/components/ui/BookLink";
import { dayTime, fmtAm, matchupText, pct, signed } from "@/lib/format";
import { mainLineText } from "@/lib/fanduel";
import { FdLink } from "@/components/ui/FdLink";
import { MarkButton } from "@/components/live/MarkButton";
import { PriceBox } from "@/components/ui/PriceBox";

/** A leg and its prices at the account's books (Nov 6): FanDuel's first, the others after it. */
const legRow = (on: Book[]) => (l: Leg, i: number) => {
  const prices = ([["FanDuel", l.price, "FD"], ["DraftKings", l.dk_price, "DK"], ["Novig", l.nv_price, "NV"]] as const)
    .filter(([b, p]) => on.includes(b) && p != null);
  const [first, ...rest] = prices;
  return (
    <li key={`${i}-${l.label}`}>
      <span>
        {l.label}
        {l.read ? <> <span className="dot" title="Fits our read of the game">●</span></> : null}
        {l.questionable ? <> <span className="q" title={`Questionable: ${l.questionable}`}>Q</span></> : null}
        {l.dk_moved && l.dk_label && on.includes("DraftKings") ? <><br /><span className="faint">DraftKings: {l.dk_label}</span></> : null}
      </span>
      <span className="lp">{first ? <>{first[0] === "FanDuel" ? "" : `${first[2]} `}{fmtAm(first[1])}</> : <span className="faint">fair {fmtAm(l.fair_price)}</span>}
        {rest.map(([b, p, short]) => <span key={b} className="faint" title={`${b}'s price`}> · {short} {fmtAm(p)}</span>)}</span>
    </li>
  );
};

/** Legs FanDuel's odds feed doesn't list get no link, so the button carries the rest (or is gone): the Conference
 *  League's goals markets aren't in the feed at all (Oct 22: an 8-leg cup SGP+ with no button). Say what to add by hand. */
export function fdMissingText(legs: Leg[]): string | null {
  const miss = legs.filter((l) => !l.link).length;
  if (!miss || !legs.length) return null;
  if (legs.length - miss === 1 && legs.length > 1) return `Only 1 of these ${legs.length} legs is in FanDuel's odds feed, so there's no parlay link: build it in FanDuel's app.`;
  return miss === legs.length
    ? "None of these legs are in FanDuel's odds feed, so there's no link: build it in FanDuel's app."
    : `${miss} of these ${legs.length} legs aren't in FanDuel's odds feed: the button adds the rest, add them in FanDuel's app.`;
}

function FdMissing({ legs }: { legs: Leg[] }) {
  const text = fdMissingText(legs);
  const main = mainLineText(legs.map((l) => l.link && l.link_main));
  return <>{text && <p className="faint">{text}</p>}{main && <p className="faint">{main}</p>}</>;
}

/** The slip at DraftKings (Mike, Oct 12: both books side by side): its legs' product, the likely quote and a price box
 *  for DraftKings' SGP price, which teaches its own quote model, and the whole slip in one tap (iPhone test, Oct 13).
 *  A slip DraftKings doesn't fully post says so. */
function DkSide({ t, legs, quote }: { t: Ticket; legs: Leg[]; quote?: number }) {
  const dk = t.body.dk;
  if (!dk || !dk.of || t.kind === "td" || t.kind === "over") return null;
  const href = dkHref(legs.map((l) => l.dk_link));
  const main = mainLineText(legs.map((l) => l.dk_link && l.dk_link_main), "DraftKings");
  if (dk.legs < dk.of) return <p className="faint">DraftKings posts {dk.legs} of these {dk.of} legs: this slip isn&apos;t on DraftKings.</p>;
  return (
    <>
      <div className="sline">
        <span>DraftKings legs <b>{fmtAm(dk.naive_price)}</b></span>
        {dk.likely_price != null && <span title={dk.stand_in ? "From FanDuel's quote pattern until about 40 DraftKings quotes are typed" : "From your typed DraftKings quotes"}>
          DraftKings likely <b>{fmtAm(dk.likely_price)}</b>{dk.stand_in ? " (FanDuel's pattern)" : ""}</span>}
        {dk.moved ? <span>{dk.moved} leg{dk.moved > 1 ? "s" : ""} at DraftKings&apos; nearest number</span> : null}
      </div>
      <PriceBox sgpId={`${t.sgp_id}~dk`} book="DraftKings" label={t.kind === "sgp_plus" ? "DraftKings SGP+" : "DraftKings SGP"}
        placeholder={t.kind === "sgp_plus" ? "+1500" : "+800"} pFair={t.p_fair} fairPrice={t.fair_price} naive={dk.naive_price ?? null}
        legs={legs.map((l) => l.dk_label ?? l.label)} matchup={t.matchup} eventId={t.body.event_id ?? null} sport={t.sport} saved={quote} />
      {main && <p className="faint">{main}</p>}
      {href && <div className="actions"><a className="btn ghost" href={href} target="_blank" rel="noopener">Open in DraftKings</a></div>}
    </>
  );
}

/** The slip at Novig (Oct 28): its exact price from Novig's parlay pricer (no quote to type), the largest stake its
 *  market maker takes, and the whole slip in Novig's app in one tap. A slip Novig doesn't fully list, or that no market
 *  maker priced, says so. */
function NvSide({ t }: { t: Ticket }) {
  const nv = t.body.nv;
  if (!nv || !nv.of || t.kind === "td" || t.kind === "over") return null;
  if (nv.legs < nv.of) return <p className="faint">Novig lists {nv.legs} of these {nv.of} legs: this slip isn&apos;t on Novig.</p>;
  if (nv.price == null) return nv.refused
    ? <p className="faint">No Novig market maker priced this slip just now (they quote parlays live; it&apos;s asked again every half hour).</p> : null;
  return (
    <>
      <div className="sline">
        <span title="Novig's own price for this slip, from its parlay pricer: exact, no quote to type">Novig <b>{fmtAm(nv.price)}</b> exact</span>
        {nv.stake_max != null && <span>up to ${Math.floor(nv.stake_max)}</span>}
        {nv.priced_at && <span className="faint">priced {dayTime(nv.priced_at)}</span>}
      </div>
      {nv.link && <div className="actions"><BookLink book="Novig" links={[nv.link]} /></div>}
    </>
  );
}

/** Where "I placed this" goes (Mike, Oct 28: three books): the best known price, FanDuel's or DraftKings' typed quote or
 *  Novig's exact one when its market maker takes at least a unit ($5); a tie goes to FanDuel, then DraftKings. */
export function bestBook(t: Ticket, quote?: number, dkQuote?: number, on: readonly Book[] = onBooks([])): { book: Book; price: number | null } {
  if (t.kind === "td") return { book: "FanDuel", price: quote ?? t.price };
  const nv = t.body.nv;
  const nvPrice = nv?.price != null && (nv.stake_max == null || nv.stake_max >= 5) ? nv.price : undefined;
  const options: [Book, number | undefined][] = [["FanDuel", quote], ["DraftKings", dkQuote], ["Novig", nvPrice]];
  let best: [Book, number] | null = null;
  for (const [book, price] of options) if (on.includes(book) && price != null && (best === null || price > best[1])) best = [book, price];
  // nothing known at a book that's on (Nov 6): its first book, at FanDuel's listed price only if that's FanDuel
  return best ? { book: best[0], price: best[1] } : { book: on[0], price: on[0] === "FanDuel" ? t.price : null };
}

const legDetail = (l: Leg, i: number) => (
  <li key={`${i}-${l.label}`}>
    <span>
      {l.label}
      <br />
      <span className="faint">
        fair {pct(l.p_fair, 0)} ({fmtAm(l.fair_price)})
        {l.p_read != null && Math.abs(l.p_read - (l.p_fair ?? 0)) >= 0.005 ? ` · with our read ${pct(l.p_read, 0)}` : ""}
        {l.source ? ` · ${l.source}` : ""}
        {l.note ? ` · ${l.note}` : ""}
      </span>
    </span>
    <span className="lp">{fmtAm(l.price)}</span>
  </li>
);

/** A parlay as a compact ticket: legs, one stats line, the FanDuel price box, actions; the story and math behind More. */
export async function TicketCard({ t, mine, quote, dkQuote }: { t: Ticket; mine?: Bet; quote?: number; dkQuote?: number }) {
  const b = t.body;
  const on = onBooks(await booksOff());     // the account's books (Nov 6): a boosted TD ticket is FanDuel's alone
  if (t.kind === "td" && !on.includes("FanDuel")) return null;
  const row = legRow(on);
  // a lone NBA game's slip lists its game's legs by label only (fun_nba.game_slips, for grading): take the full leg
  // from the flat list by its label (Oct 20: the slip showed no legs and no FanDuel button)
  const byLabel = new Map((b.legs ?? []).map((l) => [l.label, l]));
  const full = (l: Leg | string): Leg => typeof l === "string" ? byLabel.get(l) ?? { label: l } : l;
  const games = b.games?.map((g) => ({ ...g, legs: (g.legs as (Leg | string)[]).map(full) }))
    ?? (b.legs ? [{ matchup: t.matchup ?? "", commence_time: t.commence_time ?? "", legs: b.legs, fair_price: undefined }] : []);
  const legs = games.flatMap((g) => g.legs);
  // "I placed this" goes to the book with the best known price (bestBook): a typed quote or Novig's exact one; a
  // boosted TD ticket is FanDuel's. Rehearsal, Oct 13: a slip with only a DraftKings quote was marked at FanDuel.
  const at = bestBook(t, quote, dkQuote, on);
  const multi = games.length > 1;
  const chip = t.kind === "sgp_plus" ? `SGP+ · ${games.length} games · ${legs.length} legs`
    : t.kind === "td" ? `Anytime TD · ${games.length} games` : b.style === "single" ? "Best single" : `SGP · ${legs.length} legs`;
  return (
    <article className="card bet">
      <div className="ticket-head">
        <span className="tag">{chip}</span>
        {b.longshot && <span className="tag warn">Long shot</span>}
        {b.style === "story" && <span className="tag">One story</span>}
        {b.fits_read ? <span className="tag lean">Fits our read · {b.fits_read}</span> : null}
      </div>
      {b.theme && <span className="ticket-theme">{b.theme}</span>}
      {multi ? games.map((g) => (
        <div key={g.matchup}>
          <div className="sline"><b>{matchupText(g.matchup, t.sport)}</b><span>{dayTime(g.commence_time)}{g.fair_price != null ? ` · this game ${fmtAm(g.fair_price)}` : ""}</span></div>
          <ul className="legs">{g.legs.map(row)}</ul>
        </div>
      )) : <ul className="legs">{legs.map(row)}</ul>}
      <div className="sline">
        <span><b>{pct(t.p_fair, t.kind === "sgp" ? 0 : 1)}</b> to hit</span>
        <span>fair <b>{fmtAm(t.fair_price)}</b>{b.read_price != null && b.read_price !== t.fair_price ? ` (read ${fmtAm(b.read_price)})` : ""}</span>
        {t.naive_price != null && <span>legs {fmtAm(t.naive_price)}</span>}
        {b.likely_price != null && on.includes("FanDuel") && <span title="FanDuel's likely quote for this slip, from your typed quotes (quote model)">FanDuel likely <b>{fmtAm(b.likely_price)}</b></span>}
        {b.lift != null && <span>{Number(b.lift).toFixed(2)}× together</span>}
        {t.kind === "td" && b.ev != null && <span>EV <b className={b.ev >= 0 ? "pos" : "neg"}>{signed(b.ev)}</b></span>}
      </div>
      {on.includes("FanDuel") && <PriceBox sgpId={t.sgp_id} label={t.kind === "td" ? "Boosted price" : t.kind === "sgp_plus" ? "FanDuel SGP+" : "FanDuel SGP"}
        placeholder={t.kind === "sgp_plus" ? "+1500" : "+800"} pFair={t.p_fair} fairPrice={t.fair_price} naive={t.naive_price}
        legs={legs.map((l) => l.label)} matchup={t.matchup} eventId={b.event_id ?? null} sport={t.sport} saved={quote}
        fixed={t.kind === "td" ? t.price : null} />}
      {on.includes("DraftKings") && <DkSide t={t} legs={legs} quote={dkQuote} />}
      {on.includes("Novig") && <NvSide t={t} />}
      {on.includes("FanDuel") && <FdMissing legs={legs} />}
      <div className="actions">
        <MarkButton marked={!!mine} mine={mine} input={{ kind: "parlay", sgp_id: t.sgp_id, price: at.price,
          book: at.book, matchup: t.matchup,
          fair_price: t.fair_price, p_fair: t.p_fair, legs: legs.map((l) => l.label), odds_event_id: b.event_id ?? null }} />
        {on.includes("FanDuel") && <FdLink links={legs.map((l) => l.link)} />}
        <details className="more">
          <summary>More</summary>
          <div className="more-body">
            {b.story && <p>{b.story}</p>}
            <ul className="legs">{legs.map(legDetail)}</ul>
            {b.why && <p>{b.why}</p>}
          </div>
        </details>
      </div>
    </article>
  );
}

/** An over to root for: one line, the reason behind Why. */
export async function OverRow({ t, mine }: { t: Ticket; mine?: Bet }) {
  const b = t.body;
  if (!onBooks(await booksOff()).includes("FanDuel")) return null;     // FanDuel's price and link only
  return (
    <article className="card bet">
      <div className="bet-top">
        <span className="bet-label">{b.label}</span>
        <span className="bet-price">{fmtAm(t.price)}</span>
      </div>
      <div className="sline">
        <span>fair <b>{pct(t.p_fair, 0)}</b> ({fmtAm(t.fair_price)})</span>
        <span>EV <b className={(b.ev ?? 0) >= 0 ? "pos" : "neg"}>{signed(b.ev)}</b>{b.ev_read != null ? ` · read ${signed(b.ev_read)}` : ""}</span>
      </div>
      <div className="actions">
        <MarkButton marked={!!mine} mine={mine} input={{ kind: "parlay", sgp_id: t.sgp_id, price: t.price, label: b.label, matchup: t.matchup,
          fair_price: t.fair_price, p_fair: t.p_fair, legs: b.label ? [b.label] : [], odds_event_id: b.event_id ?? null }} />
        <FdLink links={[b.link]} />
        {(b.read || b.note) && (
          <details className="more"><summary>Why</summary><div className="more-body"><p>{b.read || b.note}</p></div></details>
        )}
      </div>
      {b.link && b.link_main && <p className="faint">{mainLineText([true])}</p>}
    </article>
  );
}
