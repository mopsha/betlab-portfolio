"use client";

// Today's parlays as cards you swipe sideways (the overhaul, Nov 4): the league's logo and the slice, the pictures of
// who's in it, the price big, the legs in a line. A tap opens that parlay's full ticket below the row (its legs, both
// books' prices, the price box, I placed this): the same TicketCard as before, handed in already drawn.
import { useState, type ReactNode } from "react";
import { Art, ArtStack, type ArtOf } from "@/components/ui/Art";

export type ParlayCard = { id: string; league: string; chip: string; art: ArtOf[]; price: string; cap: string; sub: string; placed?: boolean };

export function ParlayShelf({ cards, details }: { cards: ParlayCard[]; details: ReactNode[] }) {
  const [open, setOpen] = useState<string | null>(cards.length === 1 ? cards[0].id : null);
  const at = cards.findIndex((c) => c.id === open);
  return (
    <>
      <div className="hscroll pshelf" role="list">
        {cards.map((c) => (
          <button type="button" role="listitem" key={c.id} className={`card pcard${open === c.id ? " on" : ""}`} aria-expanded={open === c.id}
                  onClick={() => setOpen(open === c.id ? null : c.id)}>
            <span className="pcard-top"><span className="chipx"><Art kind="league" name={c.league} size={18} /><span>{c.chip}</span></span></span>
            <span className="pcard-price"><span><span className="numx">{c.price}</span><span className="cap">{c.cap}{c.placed ? " · placed" : ""}</span></span><ArtStack items={c.art} size={30} max={3} /></span>
            <span className="sub pcard-legs">{c.sub}</span>
          </button>
        ))}
      </div>
      {at >= 0 && <div className="pshelf-open">{details[at]}</div>}
    </>
  );
}
