"use client";

// Me > Promos (Oct 30; the overhaul's look, Nov 5): the bonus bets and profit boosts you hold, soonest to end first, each
// a token card (components/promos/Token.tsx). Add one behind one button, typed or read from a screenshot of the book's
// promos screen; Use it opens the finder with it (Build), and the bet you place with it marks it used.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { addPromo, setPromoStatus, unusePromo, updatePromo, usedPromo } from "@/lib/actions";
import { fmtAm } from "@/lib/format";
import { fmtU } from "@/lib/real";
import { MARKET_CHOICES } from "@/lib/builder";
import { LEG_CHOICES, splitTeams, promoSports, promoState, promoTitle, SPORT_CHOICES, usedOnChoices, wallet, type PromoDraft, type PromoGame, type PromoRow, type UsedBet } from "@/lib/promos";
import { endsOf } from "@/lib/wallet-view";
import { useMyBooks } from "@/components/app/MyBooks";
import { BookMark, TokenCard, useNow } from "@/components/promos/Token";
import { shrink } from "@/components/build/SlipUpload";

const BOOKS = ["FanDuel", "DraftKings", "Novig"];
const MAX_SHOTS = 20;          // lib/promo-read.ts MAX_IMAGES (that file is server-only)
const READ_WAIT = 200_000;      // the server reads each screenshot (45 s and one retry, 6 at once: lib/promo-read.ts), with room for the upload
type Draft = Partial<PromoDraft> & { key: number };
/** A recent real bet, for I used it: what it was, its price and stake in units. */
export type WalletBet = UsedBet & { text: string; price: number | null; stake: number | null };

/** An ISO time as the value of a datetime-local input, in Eastern time. */
function localInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
/** A datetime-local value (Eastern) as an ISO time: the offset of that moment in New York, summer or winter time. */
function fromLocal(v: string): string | null {
  if (!v) return null;
  for (const off of ["-04:00", "-05:00"]) {
    const t = new Date(`${v}:00${off}`);
    if (localInput(t.toISOString()) === v) return t.toISOString();
  }
  return new Date(`${v}:00-05:00`).toISOString();
}

const gameTime = (iso: string) => new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
const gameDay = (iso: string) => new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric" });

function PromoForm({ start, onDone, saveLabel, title, games }: { start: Draft; onDone: (d: Draft | null) => void; saveLabel: string; title: string; games: PromoGame[] }) {
  const myBooks = useMyBooks();          // a token's book: one the account has on (Nov 6), or the one it already has
  const [d, setD] = useState<Draft>(start);
  const [teamsText, setTeamsText] = useState((start.teams ?? []).join(", "));
  const [err, setErr] = useState<string | null>(null);
  const [pending, go] = useTransition();
  const set = (k: keyof PromoRow, v: unknown) => { setD({ ...d, [k]: v }); setErr(null); };
  const n = (v: string) => (v.trim() === "" ? null : Number(v.replace(/[^0-9.+-]/g, "")));
  const field = (label: string, k: keyof PromoRow, ph = "") => (
    <label className="field">{label}<input inputMode="decimal" placeholder={ph} value={d[k] == null ? "" : String(d[k])}
      onChange={(e) => set(k, n(e.target.value))} /></label>
  );
  const picked = d.games ?? [];
  // the sport first, then its games from the schedule, by day (Nov 5, Mike); no sport, no list: it would run to hundreds
  const left = games.filter((g) => g.sport && (d.sports ?? []).includes(g.sport) && !picked.some((x) => x.event_id === g.event_id));
  const days = [...new Set(left.map((g) => gameDay(g.commence_time)))];
  const addGame = (id: string) => { const g = games.find((x) => x.event_id === id); if (g) set("games", [...picked, g]); };
  const toggleSport = (k: string, on: boolean) => {      // dropping a sport drops its games
    setD({ ...d, sports: on ? (d.sports ?? []).filter((x) => x !== k) : [...(d.sports ?? []), k], games: on ? picked.filter((g) => g.sport !== k) : d.games });
    setErr(null);
  };
  const save = () => go(async () => {
    const r = d.promo_id ? await updatePromo(d.promo_id, d) : await addPromo(d);
    if (!r.ok) setErr(r.error ?? "Couldn't save that."); else onDone(null);
  });
  return (
    <div className="card wl-form">
      <h3>{title}</h3>
      <div className="seg" role="group" aria-label="Kind">
        {(["bonus", "boost"] as const).map((k) => (
          <button key={k} type="button" aria-current={d.kind === k} onClick={() => set("kind", k)}>{k === "bonus" ? "Bonus bet" : "Profit boost"}</button>
        ))}
      </div>
      <div className="field">Book
        <div className="wl-books" role="group" aria-label="Book">
          {BOOKS.filter((b) => myBooks.includes(b as never) || d.book === b).map((b) => <button key={b} type="button" className="wl-pick" aria-pressed={d.book === b} onClick={() => set("book", d.book === b ? null : b)}><BookMark book={b} size={22} />{b}</button>)}
        </div>
        <span className="faint">{d.book ? "" : "None picked: any book"}</span>
      </div>
      <div className="wl-fields">
        {d.kind === "boost" && field("Boost %", "pct", "30")}
        {field(d.kind === "boost" ? "Max wager $" : "Bonus $", "amount_dollars", d.kind === "boost" ? "25" : "10")}
        {d.kind === "boost" && field("Max extra winnings $", "max_extra_dollars", "none")}
        <label className="field">Ends<input type="datetime-local" value={localInput(d.expires_at)} onChange={(e) => set("expires_at", fromLocal(e.target.value))} /></label>
      </div>
      <div className="field">Sport
        <div className="wl-books" role="group" aria-label="Sport">
          {SPORT_CHOICES.map(([k, l]) => {
            const on = (d.sports ?? []).includes(k);
            return <button key={k} type="button" className="wl-pick" aria-pressed={on} onClick={() => toggleSport(k, on)}>{l}</button>;
          })}
        </div>
        <span className="faint">{d.sports?.length ? "" : "None picked: any sport"}</span>
      </div>
      {(d.sports?.length || picked.length) ? (
        <div className="field">Games
          <select aria-label="Add a game" value="" onChange={(e) => addGame(e.target.value)} disabled={!left.length}>
            <option value="">{picked.length ? "Add another game" : left.length ? "Any game · or pick one" : "No games this week"}</option>
            {days.map((day) => (
              <optgroup key={day} label={day}>
                {left.filter((g) => gameDay(g.commence_time) === day).map((g) => <option key={g.event_id} value={g.event_id}>{g.matchup} · {gameTime(g.commence_time)}</option>)}
              </optgroup>
            ))}
          </select>
          {picked.length > 0 && (
            <div className="wl-books" role="group" aria-label="Picked games">
              {picked.map((g) => (
                <button key={g.event_id} type="button" className="wl-pick" aria-pressed aria-label={`Remove ${g.matchup}`}
                  onClick={() => set("games", picked.filter((x) => x.event_id !== g.event_id))}>{g.matchup} ×</button>
              ))}
            </div>
          )}
        </div>
      ) : null}
      <details className="wl-limits" open={[d.min_legs, d.min_odds, d.max_odds, d.note, d.market].some((x) => x != null && x !== "") || !!d.teams?.length || !!d.leg_kinds?.length}>
        <summary>Its limits <span className="faint">legs, odds, bet type, teams</span></summary>
        <div className="wl-fields">
          {field("Min legs", "min_legs", "1")}
          {field("Min odds", "min_odds", "-200")}
          {field("Max odds", "max_odds", "none")}
        </div>
        <label className="field">Bet type
          <select value={d.market ?? ""} onChange={(e) => set("market", e.target.value || null)}>
            <option value="">Any bet</option>
            {MARKET_CHOICES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <div className="field">Only these legs <span className="faint">every leg must be one; none is any</span>
          <div className="wl-books" role="group" aria-label="Leg kinds">
            {LEG_CHOICES.map(([k, l]) => { const on = !!d.leg_kinds?.includes(k); return (
              <button key={k} type="button" className="wl-pick" aria-pressed={on}
                onClick={() => set("leg_kinds", on ? (d.leg_kinds ?? []).filter((x) => x !== k) : [...(d.leg_kinds ?? []), k])}>{l}</button>); })}
          </div>
        </div>
        <label className="field">Teams, for a game not posted yet<input value={teamsText} placeholder="Knicks vs Celtics"
          onChange={(e) => { setTeamsText(e.target.value); set("teams", splitTeams(e.target.value)); }} /></label>
        <label className="field">Note<input value={d.note ?? ""} placeholder="NFL only, SGP only…" onChange={(e) => set("note", e.target.value || null)} /></label>
      </details>
      <div className="actions">
        <button className="btn" type="button" disabled={pending || !d.kind} onClick={save}>{pending ? "Saving…" : saveLabel}</button>
        <button className="btn quiet" type="button" onClick={() => onDone(null)}>Cancel</button>
        {err && <span className="err" role="status">{err}</span>}
      </div>
    </div>
  );
}

const asRow = (d: Draft): PromoRow => ({ promo_id: `draft-${d.key}`, kind: d.kind === "boost" ? "boost" : "bonus", book: d.book ?? null,
  amount_dollars: d.amount_dollars ?? null, pct: d.pct ?? null, max_extra_dollars: d.max_extra_dollars ?? null, min_legs: d.min_legs ?? null,
  min_odds: d.min_odds ?? null, max_odds: d.max_odds ?? null, sports: d.sports ?? null, teams: d.teams ?? null, market: d.market ?? null, games: d.games ?? null, leg_kinds: d.leg_kinds?.length ? d.leg_kinds : null, note: d.note ?? null,
  expires_at: d.expires_at ?? null, status: "open" });

export function PromoWallet({ rows, bets = [], held = [], games = [] }: { rows: PromoRow[]; bets?: WalletBet[]; held?: string[]; games?: PromoGame[] }) {
  const router = useRouter();
  const now = useNow();
  const { open, done } = wallet(rows, now);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Draft | null>(null);     // a token being edited, in place of its card
  const [drafts, setDrafts] = useState<Draft[]>([]);               // found on a screenshot, each to confirm
  const [fixing, setFixing] = useState<number | null>(null);       // the draft whose form is open
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, go] = useTransition();
  const bonus$ = open.filter((p) => p.kind === "bonus").reduce((s, p) => s + Number(p.amount_dollars ?? 0), 0);
  const boosts = open.filter((p) => p.kind === "boost").length;
  const today = open.filter((p) => endsOf(p, now)?.today);
  const [using, setUsing] = useState<string | null>(null);   // the token whose I used it list is open

  // Nov 9: the read gives up after READ_WAIT (the server's own limit is 45 s and one retry per screenshot), and says which way it
  // failed; up to MAX_SHOTS screenshots at once, and how many didn't read
  async function read(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true); setMsg(null);
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), READ_WAIT);
    try {
      const images = await Promise.all([...files].slice(0, MAX_SHOTS).map(shrink));
      const r = await fetch("/api/promos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ images }), signal: ctl.signal });
      const j = await r.json().catch(() => null);
      if (!j) setMsg(r.redirected || r.status === 401 ? "Sign in again, then try once more." : "No answer came back: try again.");
      else if (!r.ok) setMsg(j.error ?? "Couldn't read those screenshots.");
      else {
        setDrafts((j.promos as Partial<PromoDraft>[]).map((p, i) => ({ ...p, key: Date.now() + i })));
        setAdding(false);
        setMsg(!j.promos.length ? "No promos found on those screenshots."
          : j.failed ? `Read ${j.read - j.failed} of ${j.read} screenshots: send the other ${j.failed === 1 ? "one" : j.failed} again.` : null);
      }
    } catch (e) {
      setMsg((e as Error).name === "AbortError" ? "Reading took too long: try again in a moment."
        : navigator.onLine === false ? "You look offline: try again." : "Couldn't read those screenshots.");
    } finally { clearTimeout(timer); setBusy(false); }
  }
  const act = (fn: () => Promise<{ ok: boolean; error?: string }>) => go(async () => {
    const r = await fn();
    if (!r.ok) setMsg(r.error ?? "Couldn't save that."); else { setUsing(null); router.refresh(); }
  });
  const status = (id: string, s: "void" | "open" | "delete") => go(async () => {
    const r = await setPromoStatus(id, s);
    if (!r.ok) setMsg(r.error ?? "Couldn't save that."); else router.refresh();
  });
  const dropDraft = (key: number) => { setDrafts((x) => x.filter((y) => y.key !== key)); setFixing(null); };
  const saveDraft = (d: Draft) => go(async () => {
    const r = await addPromo(d);
    if (!r.ok) { setMsg(r.error ?? "Couldn't save that."); setFixing(d.key); } else { dropDraft(d.key); router.refresh(); }
  });
  // Keep all: every draft read cleanly; one with a problem stays to fix
  const saveAll = () => go(async () => {
    const kept: number[] = [];
    for (const d of drafts.filter((x) => !x.problem)) { const r = await addPromo(d); if (r.ok) kept.push(d.key); else setMsg(r.error ?? "Couldn't save that."); }
    setDrafts((x) => x.filter((y) => !kept.includes(y.key)));
    router.refresh();
  });
  const shot = (label: string, cls: string) => (
    <label className={cls} aria-disabled={busy} aria-busy={busy}>
      {busy ? <><span className="wl-spin" aria-hidden /> Reading…</> : label}
      <input type="file" accept="image/*" multiple hidden disabled={busy} onChange={(e) => { read(e.target.files); e.target.value = ""; }} />
    </label>
  );

  return (
    <div className="wl">
      <section className="wl-hero">
        <div className="wl-hero-main">
          {bonus$ > 0
            ? <><span className="hero-num">${Number.isInteger(bonus$) ? bonus$ : bonus$.toFixed(2)}</span><span className="sub">in bonus bets</span></>
            : <><span className="hero-num">{open.length}</span><span className="sub">{open.length === 1 ? "promo waiting" : "promos waiting"}</span></>}
        </div>
        <p className="sub wl-hero-line">
          {open.length === 0 ? "Add the bonus bets and boosts your books give you."
            : [bonus$ > 0 ? `${open.length} waiting` : "", boosts ? `${boosts} boost${boosts === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · ")}
          {today.length > 0 && <>{open.length > 0 && (bonus$ > 0 || boosts > 0) ? " · " : ""}<b className="warn">{today.length} end{today.length === 1 ? "s" : ""} today</b></>}
        </p>
        {/* Nov 9 (Mike: "it needs to be easier to enter promos with a screenshot"): the screenshot leads, typing is second */}
        <div className="wl-add actions">
          {shot("From a screenshot", "btn")}
          {!adding && <button className="btn quiet" type="button" onClick={() => { setAdding(true); setMsg(null); }}><span aria-hidden>+</span> Type one</button>}
        </div>
        {!busy && !drafts.length && <p className="faint">A picture of the book&apos;s promos or bonus bets screen: BetLab reads every one on it, and you check each before it&apos;s kept.</p>}
        {msg && <p className="sub" role="status">{msg}</p>}
      </section>

      {adding && (
        <section className="wl-adding">
          <PromoForm games={games} start={{ key: 0, kind: "bonus" }} title="Type a promo" saveLabel="Add it" onDone={() => { setAdding(false); router.refresh(); }} />
        </section>
      )}

      {drafts.length > 0 && (
        <section className="wl-found">
          <h2 className="section-title"><span>Found on the screenshot</span><small>{drafts.length}</small></h2>
          <p className="sub">Check each against the book, then keep it.</p>
          {drafts.filter((d) => !d.problem).length > 1 && (
            <div className="actions"><button className="btn quiet" type="button" disabled={pending} onClick={saveAll}>Keep all {drafts.filter((d) => !d.problem).length}</button></div>
          )}
          <div className="wl-list">
            {drafts.map((d) => fixing === d.key
              ? <PromoForm games={games} key={d.key} start={d} title="Fix it, then keep it" saveLabel="Keep it" onDone={() => { dropDraft(d.key); router.refresh(); }} />
              : (
                <TokenCard key={d.key} p={asRow(d)} now={now}>
                  {d.problem && <p className="warn-text" role="status">{d.problem} Fix it first.</p>}
                  <div className="tk-actions">
                    <button className="btn" type="button" disabled={pending || !!d.problem} onClick={() => saveDraft(d)}>Keep it</button>
                    <button className="btn quiet" type="button" onClick={() => setFixing(d.key)}>Fix first</button>
                    <button className="tk-quiet" type="button" onClick={() => dropDraft(d.key)}>Not mine</button>
                  </div>
                </TokenCard>
              ))}
          </div>
        </section>
      )}

      {open.length > 0 && (
        <div className="wl-list">
          {open.map((p) => editing?.promo_id === p.promo_id
            ? <PromoForm games={games} key={p.promo_id} start={editing} title={`Edit your ${promoTitle(p)}`} saveLabel="Save" onDone={() => { setEditing(null); router.refresh(); }} />
            : (
              <TokenCard key={p.promo_id} p={p} now={now}>
                <div className="tk-actions">
                  <Link className="btn tk-use" href={`/build/promo?promo_id=${p.promo_id}`}>Use it</Link>
                  <span className="tk-more">
                    <button className="tk-quiet" type="button" onClick={() => setEditing({ ...p, sports: promoSports(p), key: 1 })}>Edit</button>
                    <button className="tk-quiet" type="button" aria-expanded={using === p.promo_id} onClick={() => setUsing(using === p.promo_id ? null : p.promo_id)}>I used it</button>
                    <button className="tk-quiet" type="button" disabled={pending} onClick={() => status(p.promo_id, "void")}>Won&apos;t use</button>
                  </span>
                </div>
                {using === p.promo_id && (() => {
                  const choices = usedOnChoices(p, bets, now);
                  return (
                    <div className="tk-used">
                      <p className="sub">{choices.length ? "Which bet did it go on?" : `No bet${p.book ? ` at ${p.book}` : ""} in the last week to tie it to.`}</p>
                      {choices.map((b) => (
                        <button key={b.bet_id} className="tk-bet" type="button" disabled={pending} onClick={() => act(() => usedPromo(p.promo_id, b.bet_id))}>
                          <BookMark book={b.book} size={24} />
                          <span className="grow"><b>{b.text}</b>
                            <small>{[b.price != null ? fmtAm(b.price) : "", b.stake != null ? fmtU(Number(b.stake)) : "",
                              new Date(b.placed_at).toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric" })].filter(Boolean).join(" · ")}</small></span>
                        </button>
                      ))}
                      <button className="tk-bet" type="button" disabled={pending} onClick={() => act(() => usedPromo(p.promo_id, null))}>
                        <span className="grow"><b>A bet not in BetLab</b><small>Just mark it used</small></span>
                      </button>
                    </div>
                  );
                })()}
              </TokenCard>
            ))}
        </div>
      )}

      {done.length > 0 && (
        <details className="wl-done">
          <summary>Used and ended <span className="n">{done.length}</span></summary>
          <div className="card rows">
            {done.map((p) => {
              const st = promoState(p, now);
              return (
                <div key={p.promo_id} className="rowx wl-old">
                  <BookMark book={p.book} size={24} />
                  <span className="grow">{promoTitle(p).replace(/^./, (c) => c.toUpperCase())}
                    <small>{[p.book, st === "used" ? "used" : st === "void" ? "not used" : endsOf(p, now)?.text].filter(Boolean).join(" · ")}</small></span>
                  {st === "used" && !held.includes(p.promo_id) && <button className="tk-quiet" type="button" disabled={pending} onClick={() => act(() => unusePromo(p.promo_id))}>Bring back</button>}
                  {st !== "used" && <button className="tk-quiet" type="button" disabled={pending} onClick={() => status(p.promo_id, st === "void" ? "open" : "delete")}>
                    {st === "void" ? "Bring back" : "Remove"}</button>}
                </div>
              );
            })}
          </div>
        </details>
      )}
    </div>
  );
}
