"use client";

import { usePathname } from "next/navigation";
import { useState, useTransition } from "react";
import { saveQuote } from "@/lib/actions";
import { fmtAm, parseOdds, signed, toDec } from "@/lib/format";

/** Type FanDuel's price for a slip: the verdict updates as you type; the price saves when you leave the box. */
export function PriceBox({ sgpId, label, pFair, fairPrice, naive, legs, matchup, eventId, sport, saved, placeholder, fixed, book }: {
  sgpId: string; label: string; pFair: number | null; fairPrice: number | null; naive?: number | null; legs: string[];
  matchup?: string | null; eventId?: string | null; sport?: string | null; saved?: number; placeholder: string; fixed?: number | null;
  book?: string;
}) {
  const path = usePathname();
  const [text, setText] = useState(saved != null ? fmtAm(saved).replace("−", "-") : "");
  const [state, setState] = useState<string | null>(saved != null ? "Saved" : null);
  const [pending, start] = useTransition();
  const price = parseOdds(text) ?? fixed ?? null;
  const ev = price != null && pFair ? pFair * toDec(price) - 1 : null;
  const save = () => {
    const p = parseOdds(text);
    if (p == null || p === saved) return;
    start(async () => {
      const r = await saveQuote({ sgp_id: sgpId, price: p, fair_price: fairPrice, naive_price: naive ?? null, p_fair: pFair,
                                  legs, matchup, odds_event_id: eventId, sport, book: book ?? "FanDuel" }, path);
      setState(r.ok ? "Saved" : r.error);
    });
  };
  const id = `fdp-${sgpId}`;
  return (
    <div className="pricebox">
      <label htmlFor={id}>
        {label}
        <input id={id} value={text} placeholder={placeholder} inputMode="text" autoComplete="off"
               onChange={(e) => { setText(e.target.value); setState(null); }} onBlur={save}
               onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
      </label>
      <span aria-live="polite">
        {ev == null ? <>Worth it above <b className="mono">{fmtAm(fairPrice)}</b></>
          : ev >= 0 ? <span className="pos">Worth a fun-bucket dollar: EV <b className="mono">{signed(ev)}</b></span>
          : <span className="neg">Skip: EV <b className="mono">{signed(ev)}</b> (fair {fmtAm(fairPrice)})</span>}
      </span>
      {(pending || state) && <span className="faint">{pending ? "Saving…" : state}</span>}
    </div>
  );
}
