"use client";

// The markets of one game, a tab at a time (the reorganization, Nov 5): Popular (the main lines as one card, then a few
// props as photo rows), Lines and each stat (every rung as price buttons), and Ideas (themed slips as cards).
import { shortLeg, type BoardTab, type BuildBook, type PackLeg, type Pricer, type SlipLeg, type ThemedSlip } from "@/lib/builder";
import { MAIN_TITLES, mainText, propText, tabTitle, type MainLines } from "@/lib/build-view";
import { fmtAm, label as nice, pct, toAm } from "@/lib/format";
import { Art, ArtStack, type ArtOf } from "@/components/ui/Art";

export type LegCtx = { eid: string; pricer: Pricer; book: BuildBook; chosen: Set<string>; toggle: (eid: string, label: string) => void };

/** One leg as a price button: pressed when it's on the slip, dimmed when the chosen book doesn't post it. */
export function PriceButton({ l, ctx, text, chance = false, className = "" }: { l: PackLeg; ctx: LegCtx; text?: string; chance?: boolean; className?: string }) {
  const x = ctx.pricer.leg(ctx.eid, l.label);
  const off = !x || x.unavailable;
  return (
    <button type="button" className={`bd-pb${off ? " off" : ""} ${className}`} aria-pressed={ctx.chosen.has(ctx.eid + "|" + l.label)}
            onClick={() => ctx.toggle(ctx.eid, l.label)} title={nice(l.label)}
            aria-label={`${nice(l.label)} ${off ? `not at ${ctx.book}` : fmtAm(x.price)}`}>
      {text && <small>{text}</small>}
      <span className="bd-pr"><b className="numx">{off ? "—" : fmtAm(x.price)}</b>{chance && <i>{pct(l.p)}</i>}</span>
    </button>
  );
}

/** Spread, total and to win for each team, with its logo. */
export function MainCard({ lines, ctx, pair }: { lines: MainLines; ctx: LegCtx; pair: ArtOf[] }) {
  return (
    <div className="card bd-main" role="group" aria-label="Main lines" style={{ ["--cols" as string]: lines.cols.length }}>
      <div className="bd-main-row head" aria-hidden>
        <span />{lines.cols.map((c) => <span key={c} className="cap">{MAIN_TITLES[c]}</span>)}
      </div>
      {lines.rows.map((r) => (
        <div key={r.name} className="bd-main-row">
          <span className={`bd-team${r.side >= 0 && pair[r.side]?.abbr ? " short" : ""}`}>
            {r.side >= 0 && pair[r.side] && <Art {...pair[r.side]} size={32} />}
            <span className="bd-full">{r.name}</span>
            {r.side >= 0 && pair[r.side]?.abbr && <span className="bd-abbr" aria-hidden>{pair[r.side].abbr}</span>}
          </span>
          {lines.cols.map((c) => (r.cells[c] ? <PriceButton key={c} l={r.cells[c]!} ctx={ctx} text={mainText(c, r.cells[c]!)} /> : <span key={c} className="bd-gap" />))}
        </div>
      ))}
    </div>
  );
}

/** Props as rows: the player's photo, the leg in words with its chance, and the price. */
export function PropRows({ legs, ctx, face }: { legs: PackLeg[]; ctx: LegCtx; face: (name: string) => string | null }) {
  if (!legs.length) return null;
  return (
    <div className="card bd-props">
      {legs.map((l) => (
        <div key={l.label} className="bd-prop">
          <Art src={face(l.player!)} name={l.player!} kind="player" size={38} />
          <span className="bd-prop-what"><b>{l.player}</b><span className="sub">{nice(propText(l))} · {pct(l.p)} chance</span></span>
          <PriceButton l={l} ctx={ctx} className="fixed" />
        </div>
      ))}
    </div>
  );
}

/** Every rung of a tab: a section per market (Lines) or per player (a stat), each row a set of price buttons. */
export function Sections({ tab, ctx, face, heading }: { tab: BoardTab; ctx: LegCtx; face: (name: string) => string | null; heading?: boolean }) {
  const players = tab.key !== "game";
  return (
    <div className="card bd-secs">
      {heading && <div className="bd-secs-title">{tab.key === "game" ? "Lines" : tabTitle(tab.key, tab.title)}</div>}
      {tab.sections.map((s) => (
        <div key={s.title} className="bd-sec">
          <div className="bd-sec-h">
            {players && <Art src={face(s.title)} name={s.title} kind="player" size={38} />}
            <span>{s.title}{s.sub && <span className="sub"> · {s.sub}</span>}</span>
          </div>
          {/* six columns: a lone rung takes two (three to a line), a pair three each, a three-way two each */}
          <div className="bd-grid">
            {s.rows.flatMap((r) => r.legs.map((l, i) => (
              <PriceButton key={l.label} l={l} ctx={ctx} text={nice(shortLeg(l))} chance
                           className={`${r.legs.length === 2 ? "half" : "third"}${i === 0 && r.legs.length > 1 ? " first" : ""}`} />
            )))}
          </div>
        </div>
      ))}
    </div>
  );
}

export type Idea = { key: string; title: string; sub: string; pick: ThemedSlip | null };

/** Themed slips as cards (they were a row of chips over the markets): a tap loads the legs into the slip. */
export function Ideas({ ideas, loading, book, legArt, onUse }: { ideas: Idea[]; loading: boolean; book: BuildBook;
    legArt: (l: SlipLeg) => ArtOf | null; onUse: (legs: SlipLeg[]) => void }) {
  return (
    <div className="bd-ideas">
      {ideas.map((x) => {
        const pick = x.pick;
        if (!pick) {
          return (
            <div key={x.key} className="card bd-idea none">
              <span className="bd-idea-h"><b>{x.title}</b><span className="sub">{x.sub}</span></span>
              <span className="sub">{loading ? "Looking through the next games…" : "Not enough games fit that right now."}</span>
            </div>
          );
        }
        const arts = pick.legs.map(legArt).filter((a): a is ArtOf => !!a);
        return (
          <button key={x.key} type="button" className="card bd-idea" onClick={() => onUse(pick.legs)} aria-label={`${x.title}: load these ${pick.legs.length} legs into your slip`}>
            <span className="bd-idea-top">
              <span className="bd-idea-h"><b>{x.title}</b><span className="sub">{x.sub}</span></span>
              <span className="numx bd-idea-px">{fmtAm(Math.round(toAm(pick.dec)))}</span>
            </span>
            <span className="bd-idea-legs">
              {arts.length > 0 && <ArtStack items={arts} size={30} max={4} />}
              <span>{pick.legs.map((l) => nice(l.label)).join(" + ")}</span>
            </span>
            <span className="sub">{(pick.p * 100).toFixed(pick.p < 0.1 ? 1 : 0)}% to hit · fair {fmtAm(Math.round(toAm(1 / pick.p)))} · {book} pays {fmtAm(Math.round(toAm(pick.dec)))} ·{" "}
              <span className={pick.ev >= 0 ? "pos" : "neg"}>{pick.ev > 0 ? "+" : ""}{(pick.ev * 100).toFixed(1)}% value</span></span>
            <span className="bd-idea-go">Load into slip</span>
          </button>
        );
      })}
    </div>
  );
}
