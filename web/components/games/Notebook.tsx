// The Notebook on an NFL game page (Mike, Nov 6: "our analysis should work a lot like" @conchpicks' notebooks): the
// story, what changed, each defense's recent pattern in plain counts, then the bet. The worker writes the words
// (src/betlab/cards/notebook_nfl.py); the bet is the game's best pick or lean, our prices deciding it, named here and
// shown once, as its own card under "Bets on this game" (no duplicate cards). The words set no price.
import type { Analysis, Offer } from "@/lib/data";
import { fmtAm, pct } from "@/lib/format";

export type NotebookBody = { story?: string; changes?: string[]; patterns?: { text: string }[] };

export function Notebook({ nb, bet }: { nb: NotebookBody | undefined; bet: Offer | undefined }) {
  if (!nb || (!nb.story && !nb.changes?.length && !nb.patterns?.length)) return null;
  return (
    <section className="card notebook" aria-label="The notebook">
      <h2 className="nb-title">The notebook</h2>
      {nb.story && <div className="nb-part"><span className="cap">The story</span><p>{nb.story}</p></div>}
      {!!nb.changes?.length && <div className="nb-part"><span className="cap">What changed</span>
        <ul>{nb.changes.map((c) => <li key={c}>{c}</li>)}</ul></div>}
      {!!nb.patterns?.length && <div className="nb-part"><span className="cap">The pattern</span>
        <ul>{nb.patterns.map((p) => <li key={p.text}>{p.text}</li>)}</ul></div>}
      <div className="nb-part nb-bet"><span className="cap">The bet</span>
        {bet ? <p><b>{bet.label} {fmtAm(bet.price)}</b>{bet.book ? ` at ${bet.book}` : ""} · {bet.tier === "pick" ? "a pick" : "a lean"}
          {bet.ev != null ? `, ${pct(bet.ev)} EV` : ""}. It&apos;s the first card under Bets on this game.</p>
          : <p>Nothing worth betting in this game. Most games are priced right.</p>}
      </div>
      <p className="faint nb-foot">The notes explain the game; they don&apos;t set prices. The bet is whatever our prices like best here.</p>
    </section>
  );
}

/** The notebook in a preview body, if the worker wrote one. */
export const notebookOf = (g: Analysis | undefined): NotebookBody | undefined => g?.notebook;
