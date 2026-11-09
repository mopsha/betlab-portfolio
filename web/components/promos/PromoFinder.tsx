"use client";

// The promo finder (the overhaul's look, Nov 5: three steps, Your token · Where · Rank by, and results built like the
// pick card, with pictures). What it does is unchanged since Oct 30:
// The promo finder (Oct 30; Mike: "how it decides what bet is best, how I can't choose bet for a slice or for multiple
// games"): pick a token from the wallet (or type one), where to look (a slice, games you pick, one game, or today
// across sports) and how to rank (Max value, Balanced, Safe: lib/promo-finder.ts), then place the best one. Placing
// records it at the token's dollars with its bonus or boost, and a lock saves both of its bets.

import Link from "next/link";
import { mainLineText } from "@/lib/fanduel";
import { useEffect, useMemo, useState, useTransition } from "react";
import { loadPack, placePromo, undoPromo } from "@/lib/actions";
import {
  customRow, DEFAULT_BANDS, evaluate, findLocks, mergePack, Pricer, promoCandidates,
  type Band, type BuildBook, type Pack, type PackGame, type Promo, type QuoteModel, type SlipLeg,
} from "@/lib/builder";
import type { Ban } from "@/lib/bans";
import { dayTime, fmtAm, label as nice, matchupText, MINUS, num, parseOdds, pct, toAm } from "@/lib/format";
import { asPromo, bonusLeft, legKindName, marketName, unpricedKinds, wagerOf, promoSports, promoTitle, SPORT_CHOICES, tokenFitsGame, type PromoRow } from "@/lib/promos";
import { MODES, rank, scopeEvents, tokenDollars, type Mode, type Result, type Scope } from "@/lib/promo-finder";
import { slicesOf } from "@/lib/slices";
import { BookLink } from "@/components/ui/BookLink";
import { useMyBooks } from "@/components/app/MyBooks";
import { bookOf } from "@/lib/books";
import { Art, ArtStack, type ArtOf } from "@/components/ui/Art";
import { Glow } from "@/components/ui/Kit";
import { BookMark, Ends, TokenCard, useNow } from "@/components/promos/Token";

const BOOKS: BuildBook[] = ["FanDuel", "DraftKings", "Novig"];
const KIND: Record<Result["kind"], string> = { single: "Single", parlay: "Parlay", sgp: "Same-game", lock: "Lock" };
const WHERE = [["slice", "A slice"], ["games", "Games I pick"], ["game", "One game"], ["today", "Today"]] as const;
/** A leg's pictures: its player or its team; a total (or anything on no one) shows the game's two teams. */
type LegArt = (eid: string, label: string) => ArtOf[];
const MODE_KEY = "betlab-promo-mode";
const LOCKS_KEY = "betlab-promo-locks";
/** A lock's other book: FanDuel hedges at DraftKings, any other book at FanDuel; with that one off, another on (Nov 6),
 *  or none (no locks with one book). */
const hedgeOf = (b: BuildBook, on: readonly string[]): BuildBook | null =>
  ([b === "FanDuel" ? "DraftKings" : "FanDuel", "DraftKings", "Novig"] as BuildBook[]).find((x) => x !== b && on.includes(x)) ?? null;
const money = (x: number) => `${x < 0 ? MINUS : ""}$${Math.abs(x).toFixed(2)}`;

export function PromoFinder({ games: allGames, bands, quoteModel, bans = [], promos: wallet, start = null, unitDollars, startGame = null, art = {} }: {
  games: PackGame[]; bands: Band[] | null; quoteModel: QuoteModel | null; bans?: Ban[]; promos: PromoRow[];
  start?: string | null; unitDollars: number; startGame?: string | null;
  /** each game's two teams as pictures, away first (as Build's): game choices and legs show logos */
  art?: Record<string, ArtOf[]>;
}) {
  const now = useNow();
  const on = useMyBooks();                          // the account's books (Nov 6): tokens and prices at these only
  const promos = wallet.filter((p) => !p.book || on.includes(bookOf(p.book)));
  const [switching, setSwitching] = useState(false);
  // the token: one from the wallet, or typed here
  const [pick, setPick] = useState<string>(start && promos.some((p) => p.promo_id === start) ? start : promos[0]?.promo_id ?? "typed");
  const [typed, setTyped] = useState<{ kind: "bonus" | "boost"; pct: string; dollars: string; cap: string }>({ kind: "bonus", pct: "30", dollars: "10", cap: "" });
  const token = promos.find((p) => p.promo_id === pick) ?? null;
  // the wager (Nov 3): up to the token's max, not always all of it; everything below reprices at it
  const [wager, setWager] = useState("");
  useEffect(() => setWager(""), [pick]);
  const tokenMax = token ? num(token.amount_dollars) : null;
  const promo: Promo = token ? { ...asPromo(token), stake: wagerOf(wager, tokenMax) } as Promo : typed.kind === "bonus"
    ? { kind: "bonus", stake: Number(typed.dollars) || undefined }
    : { kind: "boost", pct: Math.min(Math.max(Number(typed.pct) || 0, 1), 500), stake: Number(typed.dollars) || undefined, maxExtra: Number(typed.cap) || undefined };
  const [book, setBook] = useState<BuildBook>(BOOKS.find((b) => b === token?.book) ?? on[0]);
  useEffect(() => { const b = BOOKS.find((x) => x === token?.book); if (b) setBook(b); }, [token?.book]);

  // where to look: a token for some sports only (its sports, or its note: "NBA Only") sees only their games, and one for
  // some teams only (Oct 31: "boosts for specific games") only theirs
  const sports = token ? promoSports(token) : null;
  const teams = token?.teams?.length ? token.teams : null;
  const named = token?.games?.length ? token.games : null;   // picked from the board when it was added (Nov 5)
  const games = useMemo(() => allGames.filter((g) => (!sports?.length || sports.includes(g.sport)) && (!token || tokenFitsGame(token, g.event_id, g.matchup, g.commence_time))),
    [allGames, sports?.join(","), teams?.join(","), named?.map((g) => g.event_id).join(",")]);   // eslint-disable-line react-hooks/exhaustive-deps
  const slices = useMemo(() => slicesOf(games), [games]);
  const [scope, setScope] = useState<Scope>(startGame ? { kind: "game", event: startGame } : slices[0] ? { kind: "slice", key: slices[0].key } : { kind: "today" });
  const [picked, setPicked] = useState<string[]>([]);
  // a token for some games starts on all of them, whichever day they're on
  useEffect(() => { if (teams || named) { setPicked(games.map((g) => g.event_id)); setScope({ kind: "games", events: [] }); } },
    [teams?.join(","), named?.length, games.length]);   // eslint-disable-line react-hooks/exhaustive-deps
  const shownScope: Scope = scope.kind === "slice" && !slices.some((x) => x.key === scope.key) ? { kind: "slice", key: slices[0]?.key ?? "" }
    : scope.kind === "game" && !games.some((g) => g.event_id === scope.event) ? { kind: "game", event: games[0]?.event_id ?? "" } : scope;
  const events = useMemo(() => scopeEvents(shownScope.kind === "games" ? { kind: "games", events: picked } : shownScope, games, slices, sports),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(shownScope), picked, games, slices]);

  // how to rank
  const [mode, setModeState] = useState<Mode>("balanced");
  useEffect(() => { try { const m = localStorage.getItem(MODE_KEY) as Mode | null; if (m && MODES.some((x) => x.key === m)) setModeState(m); } catch { /* default */ } }, []);
  const setMode = (m: Mode) => { setModeState(m); try { localStorage.setItem(MODE_KEY, m); } catch { /* this visit */ } };
  // two-book locks (the promo on one side, cash on the other) only when asked (Mike, Oct 30): a lock tied up $35 of
  // cash, over the 5u daily cap, to make $2.18
  const [showLocks, setShowLocksState] = useState(false);
  useEffect(() => { try { setShowLocksState(localStorage.getItem(LOCKS_KEY) === "1"); } catch { /* default off */ } }, []);
  const setShowLocks = (on: boolean) => { setShowLocksState(on); try { localStorage.setItem(LOCKS_KEY, on ? "1" : "0"); } catch { /* this visit */ } };

  // the games' packs, loaded as the scope needs them
  const [packs, setPacks] = useState<Record<string, Pack>>({});
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  const need = events.filter((e) => !packs[e] && !failed[e]);
  useEffect(() => {
    for (const eid of need) {
      loadPack(eid).then((parts) => {
        const pk = mergePack(parts);
        if (pk) setPacks((p) => ({ ...p, [eid]: pk })); else setFailed((f) => ({ ...f, [eid]: true }));
      }).catch(() => setFailed((f) => ({ ...f, [eid]: true })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [need.join(",")]);
  const pricer = useMemo(() => new Pricer(packs, book), [packs, book]);
  const hedge = hedgeOf(book, on);
  const hedger = useMemo(() => (hedge ? new Pricer(packs, hedge) : null), [packs, hedge]);
  const ready = events.filter((e) => packs[e]);
  const results = useMemo(() => {
    if (!ready.length) return [];
    const picks = promoCandidates(pricer, ready, promo, bands ?? DEFAULT_BANDS, quoteModel, bans);
    const locks = showLocks && hedger ? findLocks(pricer, hedger, ready, promo, 20, bans) : [];
    return rank(picks, locks, promo, mode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pricer, hedger, ready.join(","), JSON.stringify(promo), mode, bands, quoteModel, bans, showLocks]);
  const S = tokenDollars(promo);


  // pictures: a team leg's logo from its game's two teams, a player's photo by name (/api/faces, as Build does)
  const [faces, setFaces] = useState<Record<string, string | null>>({});
  const legArt: LegArt = (eid, label) => {
    const pk = packs[eid], l = pk?.legs?.[label], pair = art[eid] ?? [];
    if (l?.player) return [{ src: faces[`${pk.sport}|${l.player}`] ?? null, name: l.player, kind: "player" }];
    const t = l?.team?.toLowerCase();
    const hit = t ? pair.find((a) => a.name.toLowerCase().includes(t) || t.includes(a.name.toLowerCase()) || a.abbr?.toLowerCase() === t) : null;
    return hit ? [hit] : pair;
  };
  const wanted = [...new Set(results.flatMap((r) => r.legs.map((l) => { const pk = packs[l.event_id], who = pk?.legs?.[l.label]?.player; return who ? `${pk.sport}|${who}` : ""; }))
    .filter((k) => k && faces[k] === undefined))].slice(0, 40);
  useEffect(() => {
    if (!wanted.length) return;
    let on = true;
    const bySport = new Map<string, string[]>();
    for (const k of wanted) { const [sp, name] = [k.slice(0, k.indexOf("|")), k.slice(k.indexOf("|") + 1)]; bySport.set(sp, [...(bySport.get(sp) ?? []), name]); }
    for (const [sp, names] of bySport) {
      const fill = (j: { faces?: Record<string, string | null> } | null) => { if (on) setFaces((f) => ({ ...f, ...Object.fromEntries(names.map((n) => [`${sp}|${n}`, j?.faces?.[n] ?? null])) })); };
      fetch(`/api/faces?sport=${encodeURIComponent(sp)}&names=${encodeURIComponent(names.join("|"))}`).then((r) => (r.ok ? r.json() : null)).then(fill).catch(() => fill(null));
    }
    return () => { on = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted.join("|")]);

  const slice = shownScope.kind === "slice" ? slices.find((x) => x.key === shownScope.key) : null;
  const others = promos.filter((p) => p.promo_id !== pick);
  const choose = (id: string) => { setPick(id); setSwitching(false); };
  const gameRow = (g: PackGame) => (
    <>
      {art[g.event_id]?.length ? <ArtStack items={art[g.event_id]} size={26} /> : <Art kind="league" name={g.sport} size={26} />}
      <span className="grow">{matchupText(g.matchup, g.sport)}<small>{dayTime(g.commence_time)}</small></span>
    </>
  );

  return (
    <div className="pf">
      <div className="pf-steps">
        <section className="pf-step">
          <h2 className="pf-h"><i aria-hidden>1</i>Your token</h2>
          {token ? <TokenCard p={token} now={now} compact /> : (
            <div className="card pf-typed">
              <div className="seg" role="group" aria-label="Kind">
                {(["bonus", "boost"] as const).map((k) => <button key={k} type="button" aria-current={typed.kind === k} onClick={() => setTyped({ ...typed, kind: k })}>{k === "bonus" ? "Bonus bet" : "Profit boost"}</button>)}
              </div>
              <div className="wl-fields">
                {typed.kind === "boost" && <label className="field">Boost %<input inputMode="decimal" value={typed.pct} onChange={(e) => setTyped({ ...typed, pct: e.target.value })} /></label>}
                <label className="field">{typed.kind === "bonus" ? "Bonus $" : "Stake $"}<input inputMode="decimal" value={typed.dollars} onChange={(e) => setTyped({ ...typed, dollars: e.target.value })} /></label>
                {typed.kind === "boost" && <label className="field">Max extra $<input inputMode="decimal" value={typed.cap} placeholder="none" onChange={(e) => setTyped({ ...typed, cap: e.target.value })} /></label>}
              </div>
              <p className="sub">A token typed here isn&apos;t kept. <Link href="/more/promos">Add it to your wallet ›</Link></p>
            </div>
          )}
          <div className="pf-switch">
            <button type="button" className="tk-quiet" aria-expanded={switching} onClick={() => setSwitching(!switching)}>
              {switching ? "Keep this one" : token ? (others.length ? `Switch token · ${others.length} more` : "Type one instead") : promos.length ? `Use one from your wallet · ${promos.length}` : "Your wallet is empty"}
            </button>
            <Link className="tk-quiet" href="/more/promos">Wallet ›</Link>
          </div>
          {switching && (
            <div className="card rows pf-tokens">
              {others.map((p) => (
                <button key={p.promo_id} type="button" className="rowx" onClick={() => choose(p.promo_id)}>
                  <BookMark book={p.book} size={28} />
                  <span className="grow">{promoTitle(p).replace(/^./, (c) => c.toUpperCase())}<small>{p.book ?? "Any book"} · <Ends p={p} now={now} /></small></span>
                </button>
              ))}
              {pick !== "typed" && <button type="button" className="rowx" onClick={() => choose("typed")}><span className="grow">Type one<small>A token not in your wallet</small></span></button>}
            </div>
          )}

          {token && (
            <label className="field">{token.kind === "bonus" ? "Bonus $ to use" : "Wager $"}
              <input inputMode="decimal" value={wager} placeholder={tokenMax ? `${tokenMax} (the max)` : "10"} onChange={(e) => setWager(e.target.value)} />
            </label>
          )}
          {token && tokenMax && Number(wager) > tokenMax ? <p className="sub">This one&apos;s max is ${tokenMax}, so the results use that.</p> : null}
          <div className="field">Book
            <div className="wl-books" role="group" aria-label="Book">
              {BOOKS.filter((b) => on.includes(b)).map((b) => <button key={b} type="button" className="wl-pick" aria-pressed={book === b} onClick={() => setBook(b)}><BookMark book={b} size={22} />{b}</button>)}
            </div>
          </div>
        </section>

        <section className="pf-step">
          <h2 className="pf-h"><i aria-hidden>2</i>Where</h2>
          {teams || named ? <p className="sub">This token is for {[...(named ?? []).map((g) => g.matchup), ...(teams ?? []).map((t) => `${t} games`)].join(", ")} only{games.length ? "" : ": its prices come about an hour before it starts"}.</p> : null}
          {token?.market ? <p className="sub">{marketName(token.market)} only: other bets aren&apos;t searched.</p> : null}
          {sports?.length ? <p className="sub">This token is for {sports.map((x) => SPORT_CHOICES.find(([k]) => k === x)?.[1] ?? x).join(", ")} only: just those games are searched.</p> : null}
          <div className="pf-seg" role="group" aria-label="Where">
            {WHERE.map(([k, l]) => (
              <button key={k} type="button" aria-current={scope.kind === k} onClick={() => setScope(
                k === "slice" ? { kind: "slice", key: slices[0]?.key ?? "" } : k === "game" ? { kind: "game", event: games[0]?.event_id ?? "" }
                  : k === "games" ? { kind: "games", events: picked } : { kind: "today" })}>{l}</button>
            ))}
          </div>
          {/* every slice in view, the one searched marked (Oct 31, Mike: "choose which slice the promo is used on, not
              just whatever slice it decides"; a dropdown that started on the next slice read as the finder's choice) */}
          {scope.kind === "slice" && (slices.length ? (
            <div className="pf-choices" role="radiogroup" aria-label="Slice">
              {slices.map((s) => (
                <label key={s.key} className="pf-choice">
                  <input type="radio" name="finder-slice" checked={shownScope.kind === "slice" && shownScope.key === s.key}
                    onChange={() => setScope({ kind: "slice", key: s.key })} />
                  <Art kind="league" name={s.sport} size={26} />
                  <span className="grow">{s.title}<small>{s.events.length} game{s.events.length === 1 ? "" : "s"} · {dayTime(s.first)}</small></span>
                </label>
              ))}
            </div>
          ) : <p className="sub">No slices left on the board.</p>)}
          {scope.kind === "game" && (games.length ? (
            <div className="pf-choices" role="radiogroup" aria-label="Game">
              {games.slice(0, 80).map((g) => (
                <label key={g.event_id} className="pf-choice">
                  <input type="radio" name="finder-game" checked={shownScope.kind === "game" && shownScope.event === g.event_id}
                    onChange={() => setScope({ kind: "game", event: g.event_id })} />
                  {gameRow(g)}
                </label>
              ))}
            </div>
          ) : <p className="sub">No games on the board.</p>)}
          {scope.kind === "games" && (
            <div className="pf-choices" role="group" aria-label="Games">
              {games.slice(0, 80).map((g) => (
                <label key={g.event_id} className="pf-choice">
                  <input type="checkbox" checked={picked.includes(g.event_id)}
                    onChange={(e) => setPicked(e.target.checked ? [...picked, g.event_id] : picked.filter((x) => x !== g.event_id))} />
                  {gameRow(g)}
                </label>
              ))}
            </div>
          )}
          {scope.kind === "today" && <p className="sub">The next games today, across {sports?.length ? "the token's sports" : "every sport"}.</p>}
        </section>

        <section className="pf-step">
          <h2 className="pf-h"><i aria-hidden>3</i>Rank by</h2>
          <div className="pf-seg three" role="group" aria-label="Rank by">
            {MODES.map((m) => <button key={m.key} type="button" aria-current={mode === m.key} onClick={() => setMode(m.key)}>{m.label}</button>)}
          </div>
          <p className="sub">{MODES.find((m) => m.key === mode)!.blurb}</p>
          <label className="pf-locks"><input type="checkbox" checked={showLocks} onChange={(e) => setShowLocks(e.target.checked)} />
            <span><b>Show locks</b><small>The promo at one book, cash on the other side at another: a small sure profit, but the cash side can be large.</small></span></label>
        </section>
      </div>

      <div className="pf-results">
        <h2 className="section-title">
          <span>Best for {token ? `your ${promoTitle(token)}` : promo.kind === "bonus" ? "a bonus bet" : `a ${promo.kind === "boost" ? promo.pct : ""}% boost`}</span>
        </h2>
        <p className="sub pf-scope"><BookMark book={book} size={18} /> {book}{slice ? ` · ${slice.title}` : ""} · {events.length ? `${ready.length} of ${events.length} game${events.length === 1 ? "" : "s"} priced` : "no games here"}</p>
        {!events.length ? <div className="card empty"><b>No games to search</b><span>{scope.kind === "games" ? "Tick the games to search." : "Nothing left in this scope today."}</span></div>
          : !ready.length ? <div className="card empty"><b>Pricing…</b></div>
          : !results.length ? <div className="card empty"><b>Nothing fits</b><span>{token?.leg_kinds?.length && unpricedKinds(token).length === token.leg_kinds.length
              ? `We don't price ${token.leg_kinds.map(legKindName).join(" or ")} legs, so there's nothing to build for this one: bet it at ${book} yourself.`
              : <>No bet here meets the token&apos;s terms at this book{mode !== "max" ? "; try Max value or another scope" : ""}.</>}</span></div>
          : <div className="pf-list">{results.map((r, i) => <ResultCard key={`${S}|${book}|${r.kind}|${r.legs.map((l) => l.event_id + l.label).join("+")}`} r={r} rank={i + 1} pricer={pricer} hedger={hedger ?? pricer} book={book} promo={promo} S={S}
              token={token} unitDollars={unitDollars} bands={bands} quoteModel={quoteModel} legArt={legArt} />)}</div>}
      </div>
    </div>
  );
}

function uniq(items: ArtOf[]): ArtOf[] {
  const seen = new Set<string>();
  return items.filter((a) => (seen.has(a.name) ? false : (seen.add(a.name), true)));
}

/** One side of a bet with its picture: a single's whole card top, or one of a lock's two linked cards. */
function Side({ arts, label, sub, price, note }: { arts: ArtOf[]; label: string; sub: string; price: string; note?: string }) {
  return (
    <div className="bet-top">
      {arts.length === 1 ? <Art {...arts[0]} size={48} /> : arts.length ? <ArtStack items={arts} size={36} /> : null}
      <div className="bet-what">
        <span className="bet-label">{label}</span>
        <span className="bet-game">{sub}</span>
      </div>
      <div className="bet-px">
        <span className="bet-price">{price}</span>
        {note && <span className="bet-book">{note}</span>}
      </div>
    </div>
  );
}

function ResultCard({ r, rank: n, pricer, hedger, book, promo, S, token, unitDollars, bands, quoteModel, legArt }: {
  r: Result; rank: number; pricer: Pricer; hedger: Pricer; book: BuildBook; promo: Promo; S: number; token: PromoRow | null;
  unitDollars: number; bands: Band[] | null; quoteModel: QuoteModel | null; legArt: LegArt;
}) {
  const exact = r.kind !== "sgp";
  const [placing, setPlacing] = useState(false);
  const [price, setPrice] = useState(fmtAm(r.lock ? r.lock.promoPrice : toAm(r.dec)).replace(MINUS, "-"));
  const [dollars, setDollars] = useState(String(S));
  const hedge$ = r.lock ? Math.round(S * r.lock.hedge * 100) / 100 : 0;
  const [hedgeDollars, setHedgeDollars] = useState(String(hedge$));
  const [hedgePrice, setHedgePrice] = useState(r.lock ? fmtAm(r.lock.hedgePrice).replace(MINUS, "-") : "");
  const [done, setDone] = useState<{ sgp_id: string; lock_id?: string | null } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const main = book === "Novig" ? null
    : mainLineText(r.legs.map((l) => { const x = pricer.leg(l.event_id, l.label); return x?.link && x.link_main; }), book);
  const [pending, go] = useTransition();
  const hedgeLegs: SlipLeg[] = r.lock ? [{ event_id: r.lock.event_id, label: r.lock.hedgeLeg }] : [];

  const place = () => go(async () => {
    const p = parseOdds(price), e = evaluate(pricer, r.legs, price, bands ?? DEFAULT_BANDS, quoteModel);
    if (p == null || !e) { setErr("Enter the book's odds, like +150."); return; }
    let hedge = null;
    if (r.lock) {
      const hp = parseOdds(hedgePrice), he = evaluate(hedger, hedgeLegs, hedgePrice, bands ?? DEFAULT_BANDS, quoteModel);
      if (hp == null || !he) { setErr("Enter the hedge's odds."); return; }
      hedge = { row: customRow(hedger, hedgeLegs, he), price: hp, book: hedger.book, dollars: Number(hedgeDollars) };
    }
    const row = customRow(pricer, r.legs, e);
    const res = await placePromo({ row, price: p, book, dollars: Number(dollars), promo_id: token?.promo_id ?? null, promo_ev: r.value * Number(dollars) / S,
      promo: promo.kind === "boost" ? { kind: "boost", pct: promo.pct, maxExtra: promo.maxExtra } : { kind: "bonus" }, hedge });
    if (!res.ok) setErr(res.error); else { setErr(null); setPlacing(false); setDone({ sgp_id: row.sgp_id, lock_id: res.lock_id }); }
  });
  const undo = () => go(async () => { if (done) { const res = await undoPromo(done); if (res.ok) setDone(null); else setErr(res.error); } });

  const perTen = promo.kind !== "none" && !(promo.stake && promo.stake > 0);     // a typed token with no dollars: per $10
  const arts = uniq(r.legs.flatMap((l) => legArt(l.event_id, l.label)));
  const game = (eid: string) => { const pk = pricer.pack(eid); return pk ? `${matchupText(pk.matchup, pk.sport)} · ${dayTime(pk.commence_time)}` : ""; };
  const tags = (
    <span className="bet-tags">
      <span className={`tag ${n === 1 ? "pick" : ""}`}>{n === 1 ? "Best" : `No. ${n}`}</span>
      <span className={`tag${r.kind === "lock" ? " won" : ""}`}>{KIND[r.kind]}{r.kind === "parlay" ? ` · ${r.games} games` : ""}</span>
    </span>
  );
  const foot = (
    <>
      {!exact && <p className="sub">Same-game price is FanDuel&apos;s likely quote; ranked at {fmtAm(toAm(r.at))} in case it comes in lower. Check the real price before you place it.</p>}
      {done ? (
        <div className="actions"><span className="mine">Placed ✓ {r.lock ? "both bets" : ""}</span>
          <button className="btn quiet" type="button" disabled={pending} onClick={undo}>Undo</button></div>
      ) : placing ? (
        <div className="pf-place">
          <div className="wl-fields">
            <label className="field">{book} price<input value={price} onChange={(e) => setPrice(e.target.value)} /></label>
            <label className="field">{promo.kind === "bonus" ? "Bonus $" : "Stake $"}<input inputMode="decimal" value={dollars} onChange={(e) => {
              setDollars(e.target.value);
              if (r.lock && Number(e.target.value) > 0) setHedgeDollars(String(Math.round(Number(e.target.value) * r.lock.hedge * 100) / 100));
            }} /></label>
            {r.lock && <>
              <label className="field">{hedger.book} hedge price<input value={hedgePrice} onChange={(e) => setHedgePrice(e.target.value)} /></label>
              <label className="field">Hedge $ (cash)<input inputMode="decimal" value={hedgeDollars} onChange={(e) => setHedgeDollars(e.target.value)} /></label>
            </>}
          </div>
          {token && Number(dollars) > 0 && Number(dollars) < Number(token.amount_dollars) && <p className="sub">{token.kind === "bonus"
            ? `The other $${bonusLeft(num(token.amount_dollars), Number(dollars))} stays in your wallet as its own bonus bet.`
            : "A boost is used once, so the rest of its max wager doesn't carry over."}</p>}
          <p className="sub">Saved as {(Number(dollars) / unitDollars).toFixed(2)}u at ${unitDollars} a unit{r.lock ? `, plus a ${(Number(hedgeDollars) / unitDollars).toFixed(2)}u cash hedge` : ""}{token ? `; uses your ${promoTitle(token)}` : ""}.</p>
          <div className="actions">
            <button className="btn" type="button" disabled={pending} onClick={place}>{pending ? "Saving…" : r.lock ? "I placed both" : "I placed it"}</button>
            <button className="btn quiet" type="button" onClick={() => setPlacing(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="actions">
          <button className="btn" type="button" onClick={() => setPlacing(true)}>{r.lock ? "Place both…" : "Place…"}</button>
          <BookLink book={book} links={r.legs.map((l) => pricer.leg(l.event_id, l.label)?.link)} icon />
          {r.lock && <BookLink book={hedger.book} links={[r.lock.hedgeLink]} icon />}
        </div>
      )}
      {!placing && main && <p className="sub">{main}</p>}
      {err && <p className="err" role="alert">{err}</p>}
    </>
  );

  // a two-book lock: two linked cards, the promo's side and the cash on the other, then what the pair makes
  if (r.lock) {
    const lk = r.lock;
    return (
      <article className="pf-lock">
        <Glow className="bet pf-side" colors={[arts[0]?.color]}>
          <span className="cap pf-side-cap"><BookMark book={book} size={18} /> Your promo at {book}</span>
          <Side arts={arts} label={nice(r.legs[0]?.label)} sub={game(lk.event_id)} price={fmtAm(lk.promoPrice)} />
        </Glow>
        <div className="pf-link" aria-hidden><span>and</span></div>
        <div className="card bet pf-side">
          <span className="cap pf-side-cap"><BookMark book={hedger.book} size={18} /> {money(hedge$)} cash at {hedger.book}</span>
          <Side arts={uniq(legArt(lk.event_id, lk.hedgeLeg))} label={nice(lk.hedgeLeg)} sub="The other side of the same game" price={fmtAm(lk.hedgePrice)} />
        </div>
        <div className="card bet pf-sum">
          {tags}
          <div className="cells">
            <div><small>You&apos;re up</small><b className={r.value > 0 ? "pos" : "neg"}>{money(r.value)}</b></div>
            <div><small>Winning side</small><b>Either</b></div>
            <div><small>Cash tied up</small><b>{money(hedge$)}</b></div>
          </div>
          {foot}
        </div>
      </article>
    );
  }

  const one = r.legs.length === 1;
  return (
    <Glow as="article" className="bet pf-result" colors={[arts[0]?.color, arts[1]?.color]}>
      <div className="bet-top">
        {arts.length === 1 ? <Art {...arts[0]} size={48} /> : arts.length ? <ArtStack items={arts} size={arts.length > 2 ? 30 : 36} max={3} /> : null}
        <div className="bet-what">
          <span className="bet-label">{one ? nice(r.legs[0].label) : `${r.legs.length}-leg ${r.kind === "sgp" ? "same-game parlay" : "parlay"}`}</span>
          {(one || r.kind === "sgp") && <span className="bet-game">{game(r.legs[0].event_id)}</span>}
          {tags}
        </div>
        <div className="bet-px">
          <span className="bet-price">{fmtAm(toAm(r.dec))}</span>
          {!exact && <span className="bet-book">likely</span>}
        </div>
      </div>
      {!one && (
        <ul className="pf-legs">
          {r.legs.map((l) => { const a = legArt(l.event_id, l.label);
            return (
              <li key={l.event_id + l.label}>
                {a.length === 1 ? <Art {...a[0]} size={28} /> : a.length ? <ArtStack items={a} size={22} /> : <span className="pf-dot" aria-hidden />}
                <span className="grow"><b>{nice(l.label)}</b>{r.kind !== "sgp" && <small>{matchupText(pricer.pack(l.event_id)?.matchup, pricer.pack(l.event_id)?.sport)}</small>}</span>
              </li>
            ); })}
        </ul>
      )}
      <div className="cells">
        <div><small>{perTen ? "Expected per $10" : "Expected"}</small><b className={r.value > 0 ? "pos" : "neg"}>{money(r.value)}</b></div>
        <div><small>Chance</small><b>{pct(r.p, 0)}</b></div>
        {promo.kind === "boost"
          ? <div><small>Boost adds</small><b>{money(r.boostAdds)}</b></div>
          : <div><small>Legs</small><b>{r.legs.length}</b></div>}
      </div>
      {foot}
    </Glow>
  );
}
