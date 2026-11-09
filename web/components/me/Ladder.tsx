"use client";

import { usePathname } from "next/navigation";
import { useState, useTransition } from "react";
import { changeLadder, ladderStep, startLadder, stopLadder } from "@/lib/actions";
import type { Game, MyBet, Offer } from "@/lib/data";
import { isSettled, profit, stakeOf, statusOf } from "@/lib/bets";
import { dayTime, fmtAm, label, signed, toDec } from "@/lib/format";
import { ladderState, newsWindow, shownStack, stepName, stepOptions, stepsToTarget, suggestStep, type Ladder as L } from "@/lib/ladder";
import { fmtU } from "@/lib/real";
import { BOOKS } from "@/lib/books";
import { useMyBooks } from "@/components/app/MyBooks";
import { rungs, teamMark } from "@/lib/wallet-view";
import Link from "next/link";
import type { ReactNode } from "react";
import { Art, ArtStack, type ArtOf } from "@/components/ui/Art";
import { Glow } from "@/components/ui/Kit";
import { BookMark } from "@/components/promos/Token";
import { BookLink } from "@/components/ui/BookLink";

const PHASE: Record<string, string> = { climbed: "Climbed", busted: "Busted", stopped: "Stopped", "in play": "In play", "next step": "Waiting for a step" };
const what = (b: MyBet) => stepName(b);      // its legs, not the slip reader's "$10.4 cash" (Nov 6)
const at = (iso: string, minutes: number) => new Date(Date.parse(iso) - minutes * 60_000).toISOString();
const clock = (iso: string) => new Date(iso).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
/** "Oct 28": a past ladder's day ("Wed 10:19 AM" didn't say which Wednesday). */
const date = (iso: string) => new Date(iso).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
const RECENT_MS = 3 * 864e5;      // a ladder that ended in the last 3 days leads the page until you start another

/** My bets › Ladder (Mike, Oct 26): a ladder challenge, start to target, the whole stack on one bet at a time. You can
 *  choose a game or not; the worker (src/betlab/ladders.py) holds the day's best step (or that game's) and locks it once
 *  its game's news is in, then alerts you ("I don't need a pick on demand"). You place the locked step at the book and
 *  confirm it here, turn it down for the next one, or make one of your own open bets the step. Outside the 5u-a-day rule. */
/** The look (the overhaul, Nov 5): the stack as the big number beside its target and a rung per step; the current step as
 *  the main card, with its picture; the steps so far as a timeline, newest on top; starting one behind one button.
 *  `art`: each offer's and each step bet's pictures, by offer id or bet id (app/more/ladder/page.tsx). */
export function LadderView({ ladders, bets, offers, games: today = [], dayEnd, art = {} }:
  { ladders: L[]; bets: MyBet[]; offers: Offer[]; games?: Game[]; dayEnd?: string; art?: Record<string, ArtOf[]> }) {
  const [starting, setStarting] = useState(false);
  const path = usePathname();
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [from, setFrom] = useState("1");
  const [to, setTo] = useState("100");
  const myBooks = useMyBooks();                       // a new ladder starts at one of the account's books (Nov 6)
  const [book, setBook] = useState<string>(myBooks[0]);
  const [pick, setPick] = useState("");
  const run = (fn: () => Promise<{ ok: boolean; error?: string }>) =>
    start(async () => { const r = await fn(); setError(r.ok ? null : r.error ?? "Couldn't save that."); });

  const states = ladders.map((l) => ({ l, s: ladderState(l, bets) }));
  const live = states.find(({ l, s }) => l.status === "active" && (s.phase === "in play" || s.phase === "next step"));
  // with none running, the newest one that busted or climbed in the last 3 days leads, saying what happened (Nov 6: it was
  // folded away under Past ladders, so the page read "No ladder running" the morning after a loss)
  const lastStep = (x: (typeof states)[number]) => x.s.steps.at(-1)?.placed_at ?? x.l.ended_at ?? x.l.created_at;
  const ended = !live ? states.find((x) => (x.s.phase === "busted" || x.s.phase === "climbed") && Date.now() - Date.parse(lastStep(x)) < RECENT_MS) : undefined;
  const past = states.filter((x) => x !== live && x !== ended);
  const skipped = live?.l.skipped ?? [];
  const game = live?.l.game_id ?? "";
  const before = dayEnd ? Date.parse(dayEnd) : null;
  const atBk = live?.l.book ?? "FanDuel";      // the ladder's one book: every step is priced and locked there
  // today's games in start order, each with how many steps BetLab has there now (priced or not yet)
  const options = stepOptions(offers, Date.now(), before, atBk).filter((o) => !skipped.includes(o.offer_id));
  const count = (id: string) => options.filter((o) => o.game_id === id).length;
  const held = live?.s.phase === "next step" && !live.l.locked ? suggestStep(offers, Date.now(), skipped, game || null, before, atBk) : null;
  const own = bets.filter((b) => !isSettled(b) && !b.ladder_id && b.mode === "real");
  const gameName = (id: string) => today.find((g) => g.game_id === id)?.matchup ?? "your game";
  const a = Number(from), b = Number(to);


  return (
    <div className="ld">
      {error && <p className="err" role="alert">{error}</p>}
      {ended && (() => {
        const { l, s } = ended, last = s.steps.at(-1);
        const busted = s.phase === "busted";
        return (
          <section className={`card ld-ended ${busted ? "lost" : "won"}`}>
            <div className="ld-hero-top"><span className="cap">Your last ladder · {fmtU(Number(l.start_units))} to {fmtU(Number(l.target_units))}</span>
              <span className={`tag ${busted ? "lost" : "won"}`}>{busted ? "Busted" : "Climbed"}</span></div>
            <h2 className="ld-pitch">{busted ? `It ended at step ${s.steps.length}` : `You climbed to ${fmtU(shownStack(s.stack))}`}</h2>
            {last && <p className="sub">{busted ? <><b>{what(last)}</b> {last.price != null ? fmtAm(last.price) : ""} lost with {fmtU(stakeOf(last))} on it.</>
              : <>The last step, <b>{what(last)}</b>, took it over the target.</>} {s.won} of {s.steps.length} steps won · ended at {fmtU(shownStack(s.stack))}.</p>}
            <Rungs won={s.won} ahead={busted ? stepsToTarget(Math.max(s.stack, Number(l.start_units)), Number(l.target_units), 100) : 0} ended={busted ? "busted" : "climbed"} />
            <Timeline steps={s.steps} l={l} art={art} />
          </section>
        );
      })()}
      {live ? (() => {
        const { l, s } = live;
        const n = s.steps.length + (s.phase === "next step" ? 1 : 0);
        const lk = l.locked;
        const [lo, hi] = newsWindow(held?.league);
        const target = Number(l.target_units), ahead = stepsToTarget(s.stack, target, 100);
        const state = lk && s.phase === "next step" ? "Step locked" : held && s.phase === "next step" ? "Holding a step" : PHASE[s.phase];
        const from = (
          <label className="field">Step from<select value={game} disabled={pending} aria-label="The game for the next step"
            onChange={(e) => run(() => changeLadder(l.ladder_id, { game: e.target.value || null }, path))}>
            <option value="">Any game today</option>
            {today.map((g) => { const k = count(g.game_id);
              return <option key={g.game_id} value={g.game_id}>{g.matchup} · {dayTime(g.commence_time)} · {k ? `${k} step${k > 1 ? "s" : ""} now` : "nothing yet"}</option>; })}
          </select></label>
        );
        return (
          <>
            <section className="ld-hero">
              <div className="ld-hero-top">
                <span className="cap ld-at"><BookMark book={atBk} size={18} /> Ladder at {atBk}</span>
                <span className={`tag${lk && s.phase === "next step" ? " pick" : ""}`}>{state}</span>
              </div>
              <div className="ld-stack"><span className="hero-num">{fmtU(s.stack)}</span><span className="ld-target">of {fmtU(target)}</span></div>
              <Rungs won={s.won} ahead={ahead} ended={null} label={`Step ${n}: ${s.won} won, ${ahead} more even-money wins to the target`} />
              <p className="sub ld-where"><b>Step {n}</b> · {s.won} won · {ahead} more even-money win{ahead === 1 ? "" : "s"} to the target</p>
            </section>

            {s.open && (
              <StepCard cap={`Step ${n} · in play`} arts={art[s.open.bet_id]?.length ? art[s.open.bet_id] : guess(what(s.open))} label={what(s.open)} sub={stepSub(s.open)}
                price={s.open.price != null ? fmtAm(s.open.price) : "—"} book={s.open.book ?? atBk}
                cells={[["On it", fmtU(stakeOf(s.open))], ["To win", s.toWin != null ? fmtU(s.toWin) : "—"], ["If it wins", s.toWin != null ? fmtU(s.stack + s.toWin) : "—", "pos"]]}>
                <p className="sub">It settles with your bet in <Link href="/bets">Live</Link>; the next step comes after.</p>
              </StepCard>
            )}

            {s.phase === "next step" && lk && (
              <StepCard cap={`Step ${n} · locked ${l.locked_at ? clock(l.locked_at) : ""} · ${lk.tier}`} arts={art[lk.offer_id]?.length ? art[lk.offer_id] : guess(lk.label)} label={label(lk.label)}
                sub={`${lk.matchup ?? ""} · ${dayTime(lk.commence_time)}`} price={fmtAm(lk.price)} book={lk.book ?? "FanDuel"}
                cells={[["On it", fmtU(s.stack)], ["If it wins", fmtU(s.stack * toDec(lk.price)), "pos"], ["Edge", lk.ev != null ? signed(lk.ev) : "—"]]}>
                <p className="sub">Place {fmtU(s.stack)} on it at {lk.book ?? "FanDuel"} before it starts ({dayTime(lk.commence_time)}), then confirm.</p>
                <div className="actions ld-act">
                  {/* the betslip at the book (Nov 6): the lock's own link, else the live offer's (locks before Nov 6 carry none) */}
                  <BookLink book={lk.book ?? "FanDuel"} links={[lk.fd_url ?? offers.find((o) => o.offer_id === lk.offer_id)?.fd_url]} className="btn ghost" />
                  <button className="btn" disabled={pending}
                    onClick={() => run(() => ladderStep(l.ladder_id, s.stack, { offer: { kind: lk.tier === "pick" ? "pick" : "lean",
                      pick_id: lk.offer_id, price: lk.price, label: lk.label, matchup: lk.matchup, book: lk.book ?? "FanDuel" } }, path))}>I placed it · step {n}</button>
                  <button className="btn quiet" disabled={pending} onClick={() => run(() => changeLadder(l.ladder_id, { skip: lk.offer_id }, path))}>Not this one</button>
                </div>
              </StepCard>
            )}

            {s.phase === "next step" && !lk && (
              <>
                {l.notice?.startsWith("none:") && <p className="err ld-note">{gameName(l.notice.slice(5))}&apos;s news is in and BetLab has no +EV step there.
                  Choose another game or any game.</p>}
                {l.notice?.startsWith("missed:") && <p className="err ld-note">Your locked step ({l.notice.slice(7)}) started before it was placed.
                  BetLab will lock the next one.</p>}
                {held ? (
                  <StepCard cap={`Step ${n} · holding · ${held.tier}`} arts={art[held.offer_id]?.length ? art[held.offer_id] : guess(held.label)} label={label(held.label)} sub={`${held.matchup ?? ""} · ${dayTime(held.commence_time)}`}
                    price={fmtAm(held.price)} book={held.book ?? "FanDuel"}
                    cells={[["On it", fmtU(s.stack)], ["If it wins", fmtU(s.stack * toDec(held.price)), "pos"], ["Edge", signed(held.ev)]]}>
                    <p className="sub">BetLab locks {game ? "this game's best step" : "the day's best step"} once its game&apos;s news is in
                      (around {clock(at(held.commence_time!, hi))}–{clock(at(held.commence_time!, lo))}) and alerts you. Until then it can change as
                      the card is re-priced. Nothing to place yet.</p>
                    <div className="actions">
                      <button className="btn quiet" disabled={pending} onClick={() => run(() => changeLadder(l.ladder_id, { skip: held.offer_id }, path))}>Not this one</button>
                    </div>
                  </StepCard>
                ) : (
                  <div className="card ld-wait">
                    <span className="cap">Step {n} · nothing to place yet</span>
                    {game
                      ? <p className="sub">Nothing in {gameName(game)} fits a step at {atBk} yet (a +EV pick or lean at −250 to +150). BetLab prices it again in
                        its last pull before kickoff and locks its best step then, or tells you it has none.</p>
                      : <p className="sub">Nothing on today&apos;s card fits a step at {atBk} yet (a +EV pick or lean at −250 to +150). BetLab keeps looking
                        through the day&apos;s pulls and locks the best one once its news is in.</p>}
                  </div>
                )}
                <div className="card ld-from">
                  {from}
                  {skipped.length > 0 && <button className="tk-quiet" disabled={pending}
                    onClick={() => run(() => changeLadder(l.ladder_id, { unskip: true }, path))}>Show the {skipped.length} you turned down again</button>}
                  {own.length > 0 && (
                    <details className="wl-limits ld-own">
                      <summary>Or use one of your open bets</summary>
                      <form onSubmit={(e) => { e.preventDefault(); if (pick) run(() => ladderStep(l.ladder_id, s.stack, { betId: pick }, path)); }}>
                        <label className="field">Your open bet<select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Your open bet">
                          <option value="">Choose…</option>
                          {own.map((x) => <option key={x.bet_id} value={x.bet_id}>{what(x)}{x.price != null ? ` ${fmtAm(x.price)}` : ""}</option>)}
                        </select></label>
                        <button className="btn quiet" disabled={pending || !pick}>Make it step {n} at {fmtU(s.stack)}</button>
                      </form>
                    </details>
                  )}
                </div>
              </>
            )}

            <Timeline steps={s.steps} l={l} art={art} />
            <div className="ld-end">
              <button className="tk-quiet" disabled={pending}
                onClick={() => { if (confirm(s.steps.length ? "Stop this ladder? Its bets stay in Live." : "Remove this ladder? It has no steps yet."))
                  run(() => stopLadder(l.ladder_id, path)); }}>{s.steps.length ? "Stop ladder" : "Remove ladder"}</button>
            </div>
          </>
        );
      })() : (
        <section className="ld-start">
          <div className="ld-hero">
            <span className="cap">{ended ? "Start another" : "No ladder running"}</span>
            {!ended && <h2 className="ld-pitch">Roll one stack toward a target</h2>}
            {!ended && <Rungs won={0} ahead={a > 0 && b > a ? stepsToTarget(a, b, 100) : 7} ended="stopped" />}
            {!ended && <p className="sub">The whole stack goes on one bet at a time. One loss ends it.</p>}
          </div>
          {!starting ? <button className="btn ld-go" type="button" onClick={() => setStarting(true)}>Start a ladder</button> : (
            <form className="card ld-form" onSubmit={(e) => { e.preventDefault(); run(() => startLadder(a, b, path, book)); }}>
              <div className="wl-fields">
                <label className="field">Start (u)<input inputMode="decimal" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="Start in units" /></label>
                <label className="field">Target (u)<input inputMode="decimal" value={to} onChange={(e) => setTo(e.target.value)} aria-label="Target in units" /></label>
              </div>
              <div className="field">Book
                <div className="wl-books" role="group" aria-label="The book every step is at">
                  {BOOKS.filter((x) => myBooks.includes(x)).map((x) => <button key={x} type="button" className="wl-pick" aria-pressed={book === x} onClick={() => setBook(x)}><BookMark book={x} size={22} />{x}</button>)}
                </div>
              </div>
              {a > 0 && b > a && <p className="sub">{stepsToTarget(a, b, 100)} even-money wins in a row ({stepsToTarget(a, b, -110)} at −110). At a fair
                coin flip that&apos;s about 1 in {Math.round(2 ** stepsToTarget(a, b, 100))}.</p>}
              <div className="actions">
                <button className="btn" disabled={pending}>Start ladder</button>
                <button className="btn quiet" type="button" onClick={() => setStarting(false)}>Cancel</button>
              </div>
            </form>
          )}
          <details className="wl-limits ld-rules">
            <summary>How a ladder works</summary>
            <p className="sub">Start small and roll the whole stack into one bet at a time until you hit the target. One loss ends it. Choose a
              game or not: BetLab holds the day&apos;s best step (its strongest +EV pick near even money), locks it once that game&apos;s news is in
              and alerts you. The whole ladder stays at the book you pick. Ladder steps are real bets outside the 5u-a-day rule.</p>
          </details>
        </section>
      )}

      {past.length > 0 && (
        <details className="wl-done ld-past"><summary>Past ladders <span className="n">{past.length}</span></summary>
          <div className="ld-pastlist">
            {past.map(({ l, s }) => (
              <article key={l.ladder_id} className="card ld-old">
                <div className="ld-hero-top"><b className="ld-old-name">{fmtU(Number(l.start_units))} to {fmtU(Number(l.target_units))}</b>
                  <span className={`tag ${s.phase === "climbed" ? "won" : s.phase === "busted" ? "lost" : ""}`}>{PHASE[s.phase]}</span></div>
                <Rungs won={s.won} ahead={s.phase === "climbed" ? 0 : stepsToTarget(Math.max(s.stack, Number(l.start_units)), Number(l.target_units), 100)}
                  ended={s.phase === "climbed" ? "climbed" : s.phase === "busted" ? "busted" : "stopped"} />
                <p className="sub">{s.won} of {s.steps.length} steps won · ended at {fmtU(shownStack(s.stack))} · {date(l.created_at)}
                  {s.steps.length ? `–${date(lastStep({ l, s }))}` : ""}</p>
                {s.steps.length > 0 && <Timeline steps={s.steps} l={l} art={art} />}
              </article>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

/** A step with no picture from its game (an old game, a board that didn't answer): its team by name, when the label
 *  starts with exactly one NFL, NBA or NHL team. */
function guess(name: string): ArtOf[] {
  const t = teamMark(name.replace(/\s+(ML|to win|[+\-\u2212]\d+(\.\d+)?)$/i, ""));
  return t.src ? [{ src: t.src, name: t.name, abbr: t.abbr, kind: "team" }] : [];
}

const stepSub = (b: MyBet) => [b.matchup && b.matchup !== b.label ? String(b.matchup).split(":")[0] : "", dayTime(b.pick_commence_time ?? b.ticket_commence_time ?? b.game_start ?? null)]
  .filter(Boolean).join(" · ");

/** The climb as stairs, one per step: won, the one you're on, lost, and the even-money wins still to come. */
function Rungs({ won, ahead, ended, label: aria }: { won: number; ahead: number; ended: "climbed" | "busted" | "stopped" | null; label?: string }) {
  const list = rungs(won, ahead, ended);
  return (
    <div className="ld-rungs" role={aria ? "img" : undefined} aria-label={aria} aria-hidden={aria ? undefined : true}>
      {list.map((k, i) => <i key={i} className={`is-${k}`} style={{ height: `${Math.round(100 * (0.3 + 0.7 * (list.length > 1 ? i / (list.length - 1) : 1)))}%` }} />)}
    </div>
  );
}

/** The step to act on: its picture, what it is and its price, three numbers, then what to do. */
function StepCard({ cap, arts = [], label: name, sub, price, book, cells, children }: { cap: string; arts?: ArtOf[]; label: string; sub: string; price: string;
  book: string; cells: [string, string, string?][]; children: ReactNode }) {
  return (
    <Glow as="article" className="bet ld-now" colors={[arts[0]?.color, arts[1]?.color]}>
      <span className="cap">{cap}</span>
      <div className="bet-top">
        {arts.length === 1 ? <Art {...arts[0]} size={48} /> : arts.length ? <ArtStack items={arts} size={36} /> : null}
        <div className="bet-what">
          <span className="bet-label">{name}</span>
          {sub && <span className="bet-game">{sub}</span>}
        </div>
        <div className="bet-px">
          <span className="bet-price">{price}</span>
          <span className="bet-book">{book}</span>
        </div>
      </div>
      <div className="cells">{cells.map(([k, v, tone]) => <div key={k}><small>{k}</small><b className={tone ?? ""}>{v}</b></div>)}</div>
      {children}
    </Glow>
  );
}

/** The steps so far as a timeline, newest on top (you climb up): each step's bet, how it went and the stack after it. */
function Timeline({ steps, l, art }: { steps: MyBet[]; l: L; art: Record<string, ArtOf[]> }) {
  let stack = Number(l.start_units);
  const rows = steps.map((b, i) => {
    const st = statusOf(b), settled = isSettled(b);
    if (settled) stack += profit(b) ?? 0;
    return { b, n: i + 1, st, settled, after: stack };
  }).reverse();
  return (
    <ol className="ld-line">
      {rows.map(({ b, n, st, settled, after }) => {
        const a = art[b.bet_id]?.length ? art[b.bet_id] : guess(what(b));
        return (
          <li key={b.bet_id} className={st === "won" ? "won" : st === "lost" ? "lost" : settled ? "flat" : "open"}>
            <span className="ld-node" aria-hidden>{a.length === 1 ? <Art {...a[0]} size={30} className="disc" /> : n}</span>
            <span className="grow"><b>{what(b)}</b>
              <small>Step {n} · {b.price != null ? `${fmtAm(b.price)} · ` : ""}{fmtU(stakeOf(b))} on it</small></span>
            <span className="ld-after">{settled ? <><small>{st}</small><b>{fmtU(shownStack(after))}</b></> : <small>in play</small>}</span>
          </li>
        );
      })}
      <li className="start"><span className="ld-node" aria-hidden />
        <span className="grow"><small>Started with {fmtU(Number(l.start_units))} · {date(l.created_at)}</small></span></li>
    </ol>
  );
}
