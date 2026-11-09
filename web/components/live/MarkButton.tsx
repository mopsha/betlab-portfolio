"use client";

import { usePathname } from "next/navigation";
import { useState, useTransition } from "react";
import { markBet, undoBet, updateBet, type MarkInput } from "@/lib/actions";
import { BOOKS } from "@/lib/books";
import { useMyBooks } from "@/components/app/MyBooks";
import type { Bet } from "@/lib/data";
import { fmtAm, MINUS, num } from "@/lib/format";
import { fmtU, isReal } from "@/lib/real";
import { useRealFrom } from "@/components/app/RealFrom";

/** Mark as mine / Undo. Paper until Oct 18; from then "I placed this" records a real bet at 1 unit and
 *  the price shown, and Edit fixes the stake or the price FanDuel actually gave. Writes to the signed-in
 *  user's own bets. Pass `mine` (the bet) where the caller has it, so a placed bet can be edited here. `bare`: no
 *  "Placed 1u at +120" line, for a card that already says it (Live's bet card). `settled`: a graded bet can still be
 *  edited (stake, price, book, bonus, boost, cash-out; its profit follows, as grading works it out) but never undone. */
export function MarkButton({ input, marked, mine, bare = false, settled = false }: { input: MarkInput; marked: boolean; mine?: Bet; bare?: boolean; settled?: boolean }) {
  const realFrom = useRealFrom();
  const path = usePathname();
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [stake, setStake] = useState("");
  const [price, setPrice] = useState("");
  const myBooks = useMyBooks();                // the edit's book menu: the account's books (Nov 6), and the bet's own
  const [book, setBook] = useState("FanDuel");
  const [bonus, setBonus] = useState(false);
  const [cashout, setCashout] = useState("");
  const [boost, setBoost] = useState("");
  const [protect, setProtect] = useState(false);
  const [reset, setReset] = useState(false);
  const edit = () => {   // the bet's current values, which arrive after the mark is saved
    setStake(String(num(mine?.stake) ?? 1));
    setPrice(mine?.price != null ? fmtAm(mine.price).replace(MINUS, "-") : "");
    setBook(mine?.book ?? input.book ?? "FanDuel");
    setBonus(mine?.bonus === true);
    setCashout(mine?.cashout != null ? String(mine.cashout) : "");
    setBoost(mine?.boost != null ? String(mine.boost) : "");
    setProtect(mine?.protect === true);
    setReset(mine?.reset === true);
    setEditing(true);
  };
  const run = (fn: () => Promise<{ ok: boolean; error?: string }>, after?: () => void) =>
    start(async () => { const r = await fn(); setError(r.ok ? null : r.error ?? "Couldn't save that."); if (r.ok) after?.(); });

  if (marked) {
    const real = mine?.mode === "real";
    // A real parlay marked before FanDuel's price was typed has no price, so it can't count in the real P/L:
    // ask for it right there (the rehearsal of Oct 9 found it easy to miss).
    const noPrice = real && mine != null && mine.price == null;
    const parlay = input.kind === "parlay" || input.kind === "custom";
    return (
      <span className="actions">
        {!bare && <span className="mine">✓ {real ? `Placed ${fmtU(num(mine?.stake) ?? 1)}${mine?.bonus ? " bonus" : ""}${mine?.boost ? ` +${mine.boost}% boost` : ""}${mine?.protect ? " · Bet Protect+" : ""}${mine?.reset ? " · Bet reset" : ""}${mine?.price != null ? ` at ${fmtAm(mine.price)}` : ""}${mine?.book ? ` · ${mine.book}` : ""}` : "Yours"}</span>}
        {noPrice && !editing && <button className="btn" disabled={pending} onClick={edit}>Add the price you got</button>}
        {real && mine && !editing && !noPrice && <button className="btn quiet" disabled={pending} onClick={edit}>Edit</button>}
        {!settled && <button className="btn quiet" disabled={pending}
                onClick={() => run(() => undoBet({ pick_id: input.pick_id, sgp_id: input.sgp_id }, path))}>Undo</button>}
        {real && mine && editing && (
          <form className="placed-edit" onSubmit={(e) => { e.preventDefault(); run(() => updateBet(mine.bet_id, { stake: Number(stake), price, book, bonus, cashout, boost, protect, reset }, path), () => setEditing(false)); }}>
            <label>Units<input inputMode="decimal" value={stake} onChange={(e) => setStake(e.target.value)} aria-label="Stake in units" /></label>
            <label>Price<input value={price} onChange={(e) => setPrice(e.target.value)} placeholder={parlay ? "+1200" : "-110"} aria-label="Price you got" /></label>
            <label>Book<select value={book} onChange={(e) => setBook(e.target.value)} aria-label="Book you placed it at">
              {BOOKS.filter((b) => myBooks.includes(b) || b === book).map((b) => <option key={b}>{b}</option>)}</select></label>
            <label className="check" title="The book's credit, not cash: a win pays the profit only, a loss costs nothing">
              <input type="checkbox" checked={bonus} onChange={(e) => setBonus(e.target.checked)} aria-label="Bonus bet" />Bonus bet</label>
            <label className="check" title="FanDuel's Bet Protect+: 3% of the stake on top; a leg on a player who sits counts as won">
              <input type="checkbox" checked={protect} onChange={(e) => setProtect(e.target.checked)} aria-label="Bet Protect+" />Bet Protect+</label>
            <label className="check" title="A bet reset token: if this loses, the stake comes back as a bonus bet in your wallet">
              <input type="checkbox" checked={reset} onChange={(e) => setReset(e.target.checked)} aria-label="Bet reset" />Bet reset</label>
            <label title="A profit boost in percent: the price stays the book's own, a win's profit is boosted">Boost %
              <input inputMode="decimal" value={boost} onChange={(e) => setBoost(e.target.value)} placeholder="—" aria-label="Profit boost in percent" /></label>
            <label title="Cashed out early: what the book paid back, in units ($5.29 on a $5 = 1u bet is 1.058). Blank: not cashed out">Cashed out (u back)
              <input inputMode="decimal" value={cashout} onChange={(e) => setCashout(e.target.value)} placeholder="—" aria-label="Cash-out paid back, in units" /></label>
            <button className="btn" disabled={pending}>Save</button>
            <button type="button" className="btn quiet" onClick={() => setEditing(false)}>Cancel</button>
          </form>
        )}
        {noPrice && !editing && <span className="err">No price yet: this bet can't count in your real P/L until you add it.</span>}
        {error && <span className="err" role="alert">{error}</span>}
      </span>
    );
  }
  const real = isReal(new Date(), realFrom);
  return (
    <span className="actions">
      <button className="btn" disabled={pending} onClick={() => run(() => markBet(input, path))}>
        {real ? "I placed this" : "Mark as mine"}
      </button>
      {error && <span className="err" role="alert">{error}</span>}
    </span>
  );
}
