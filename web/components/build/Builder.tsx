"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { loadPack, markBet, placePromo, saveCustom, type MarkInput } from "@/lib/actions";
import {
  boardTabs, slipId, customRow, DEFAULT_BANDS, evaluate, mergePack, Pricer, SLIP_THEMES, themedSlip,
  type Band, type BuildBook, type Evaluation, type Pack, type PackGame, type Promo, type QuoteModel, type SlipLeg,
} from "@/lib/builder";
import { useMyBooks } from "@/components/app/MyBooks";
import { bestBook, BUILD_BOOKS, mainLines, popularProps, readSlips, tabTitle, tokenFits, type StoredSlip } from "@/lib/build-view";
import { dayTime, fmtAm, inOrder, matchupText, MINUS, pct, SPORTS, toAm, toDec } from "@/lib/format";
import type { Bet } from "@/lib/data";
import type { Ban } from "@/lib/bans";
import { leagueLogo } from "@/lib/league-art";
import type { NovigQuote } from "@/lib/novig";
import type { PromoRow } from "@/lib/promos";
import { isReal } from "@/lib/real";
import { useRealFrom } from "@/components/app/RealFrom";
import { Art, ArtStack, type ArtOf } from "@/components/ui/Art";
import { Icon } from "@/components/ui/Kit";
import { BookMenu } from "@/components/build/BookMenu";
import { BuildModes } from "@/components/build/BuildModes";
import { Ideas, MainCard, PropRows, Sections, type Idea, type LegCtx } from "@/components/build/Markets";
import { SlipPanel, type NovigState } from "@/components/build/SlipPanel";

type Slips = Record<string, StoredSlip>;
type Saved = { sgp_id: string; grade: string | null; price: number | null };
const KEY = "betlab-build-v2";
const EMPTY: StoredSlip = { legs: [], prices: {} };
const PROMO_KEY = "betlab-build-promo";
const SCAN = 16;                                   // Ideas look through the sport's next 16 games

/** Build your own parlay: legs from any upcoming game of one sport (never across sports, Mike's rule), priced from the
 *  games' simulated draws, graded, and saved to be tracked. One slip per sport, kept in this browser until saved.
 *  Reorganized Nov 5 ("all the right functionality exists, it can just be organized so much better"): three layers of
 *  controls (the header with the book, saved parlays and search; the modes; sport and game), then one row of market
 *  tabs with only the chosen tab's markets on the page, and everything about the slip (prices at each book, a promo,
 *  placing it) inside the slip. What a slip is worth is lib/builder.ts, unchanged. */
export function Builder({ games, bands, quoteModel, saved, marked, preset = null, bans = [], art = {}, promos = [] }: {
  games: PackGame[]; bands: Band[] | null; quoteModel?: QuoteModel | null; saved: Saved[]; marked: Record<string, Bet>; bans?: Ban[];
  /** each game's two teams as pictures, away first: the strip, the main lines and the slip show logos */
  art?: Record<string, ArtOf[]>;
  /** a promo from a link (the promo helper, /promo): its terms and game win over what this browser remembered */
  preset?: { promo: Promo; game: string | null } | null;
  /** the wallet's open tokens, offered in the slip's promo row */
  promos?: PromoRow[];
}) {
  const path = usePathname();
  const realFrom = useRealFrom();
  const sports = useMemo(() => [...new Set(games.map((g) => g.sport))], [games]);
  const live = useMemo(() => new Set(games.map((g) => g.event_id)), [games]);
  const [sport, setSport] = useState(sports[0] ?? "nfl");
  const [slips, setSlips] = useState<Slips>({});
  const [game, setGame] = useState<string>("");
  const [tab, setTab] = useState<string>("popular");
  const [q, setQ] = useState("");
  const [searching, setSearching] = useState(false);
  const [open, setOpen] = useState(false);         // the slip sheet, on phones
  const [packs, setPacks] = useState<Record<string, Pack>>({});
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const strip = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  // A bonus bet or profit boost to spend (Oct 22): the slip shows its value, and the bet is marked with it.
  const [promo, setPromoState] = useState<Promo>({ kind: "none" });
  const [tokenId, setTokenId] = useState<string | null>(null);
  const presetGame = preset?.game ? games.find((g) => g.event_id === preset.game) ?? null : null;
  const setPromo = (x: Promo) => { setPromoState(x); try { localStorage.setItem(PROMO_KEY, JSON.stringify(x)); } catch { /* this visit only */ } };
  useEffect(() => {
    if (preset) {
      setPromo(preset.promo);
      if (presetGame) { setSport(presetGame.sport); setGame(presetGame.event_id); }
      return;
    }
    try { const x = JSON.parse(localStorage.getItem(PROMO_KEY) || "null"); if (x?.kind) setPromoState(x); } catch { /* start with none */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The slips in this browser, minus legs whose game has started.
  useEffect(() => {
    try {
      const { slips: clean, sport: last } = readSlips(JSON.parse(localStorage.getItem(KEY) || "{}"), (eid) => live.has(eid));
      setSlips(clean);
      if (last && sports.includes(last) && !presetGame) setSport(last);
    } catch { /* storage blocked: start empty */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, sports]);
  const persist = (next: Slips, sp = sport) => {
    setSlips(next);
    try { localStorage.setItem(KEY, JSON.stringify({ ...next, _sport: sp })); } catch { /* not saved across visits */ }
  };

  const inSport = games.filter((g) => g.sport === sport);
  const slip = slips[sport] ?? EMPTY;
  const current = inSport.some((g) => g.event_id === game) ? game : inSport[0]?.event_id ?? "";

  // The search finds games by team; when no game matches, it filters the picked game's legs instead.
  const ql = q.trim().toLowerCase();
  const gameHits = ql ? inSport.filter((g) => g.matchup.toLowerCase().includes(ql)) : [];
  const shown = gameHits.length ? gameHits : inSport;
  const legQ = ql && !gameHits.length ? ql : "";
  useEffect(() => { if (searching) search.current?.focus(); }, [searching]);

  // Keep the picked game's card in view.
  useEffect(() => {
    strip.current?.querySelector<HTMLElement>('[aria-current="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [current, sport]);

  const myBooks = useMyBooks();                                   // the account's books (Nov 6): Build prices at these only
  const books = BUILD_BOOKS.filter((b) => myBooks.includes(b));
  const [picked, setBookState] = useState<BuildBook>(books[0]);    // the book this slip is built for (Oct 12)
  const book = books.includes(picked) ? picked : books[0];
  const setBook = (b: BuildBook) => { setMsg(null); setBookState(b); };
  const pricers = useMemo(() => Object.fromEntries(BUILD_BOOKS.map((b) => [b, new Pricer(packs, b)])) as Record<BuildBook, Pricer>, [packs]);
  const pricer = pricers[book];
  const pk = packs[current];
  const cur = inSport.find((g) => g.event_id === current);
  const pair = art[current] ?? [];
  const all = useMemo(() => Object.values(pk?.legs ?? {}), [pk]);
  const tabs = useMemo(() => boardTabs(legQ ? all.filter((l) => l.label.toLowerCase().includes(legQ)) : all, pk?.matchup), [all, pk, legQ]);
  const lines = useMemo(() => (pk ? mainLines(all, pk.matchup, (art[current] ?? []).map((a) => a.abbr)) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [all, pk, current]);
  const popular = useMemo(() => popularProps(all.map((l) => pricer.leg(current, l.label) ?? l), sport, bans),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [all, pricer, current, sport]);
  const gameTab = tabs.find((t) => t.key === "game"), statTabs = tabs.filter((t) => t.key !== "game");
  const keys: [string, string][] = [
    ...(!pk || lines || popular.length ? [["popular", "Popular"] as [string, string]] : []),
    ...(!pk || gameTab ? [["lines", "Lines"] as [string, string]] : []),
    ...statTabs.map((t) => [t.key, tabTitle(t.key, t.title)] as [string, string]),
    ["ideas", "Ideas"],
  ];
  const curKey = keys.some(([k]) => k === tab) || !pk ? tab : keys[0][0];
  // Load each pack once: the picked game's, every game on the slip, and the next games while Ideas is open.
  const next = useMemo(() => [...inSport].sort((a, b) => a.commence_time.localeCompare(b.commence_time)).slice(0, SCAN).map((g) => g.event_id),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [games, sport]);
  const ideasOpen = curKey === "ideas" && !legQ;
  const need = [...new Set([current, ...slip.legs.map((l) => l.event_id), ...(ideasOpen ? next : [])])].filter((e) => e && !packs[e] && !failed[e]);
  useEffect(() => {
    for (const eid of need) {
      loadPack(eid).then((parts) => {
        const pk = mergePack(parts);
        if (pk) setPacks((p) => ({ ...p, [eid]: pk })); else setFailed((f) => ({ ...f, [eid]: true }));
      }).catch(() => setFailed((f) => ({ ...f, [eid]: true })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [need.join(",")]);

  const ready = slip.legs.every((l) => packs[l.event_id]);

  // Novig (Oct 28): no price to type. Novig's parlay pricer answers with its exact price (api/novig). Asked for every
  // slip Novig lists, whichever book is chosen, so its box can sit beside the others; a short wait first, so a run of
  // taps asks once.
  const nvIds = slip.legs.length >= 2 && books.includes("Novig") ? pricers.Novig.novigIds(slip.legs) : null;
  const [nvq, setNvq] = useState<{ key: string; q: NovigQuote | null } | null>(null);
  const nvKey = nvIds?.join(",") ?? "";
  useEffect(() => {
    if (!nvKey) return;
    let on = true;
    const t = setTimeout(() => {
      fetch(`/api/novig?ids=${nvKey}`).then((r) => r.json()).then((j) => {
        if (on) setNvq({ key: nvKey, q: j && typeof j.price === "number" ? (j as NovigQuote) : null });
      }).catch(() => on && setNvq({ key: nvKey, q: null }));
    }, 500);
    return () => { on = false; clearTimeout(t); };
  }, [nvKey]);
  const nvNow = nvq && nvq.key === nvKey ? nvq : null;
  const nv: NovigState = slip.legs.length < 2 ? { state: "few", q: null } : !nvIds ? { state: "unlisted", q: null }
    : !nvNow ? { state: "asking", q: null } : nvNow.q ? { state: "priced", q: nvNow.q } : { state: "refused", q: null };

  // Each book's verdict on the slip, at the price typed for it (Novig's: the one its pricer gave).
  const priceText = (b: BuildBook) => (b === "Novig" ? (nv.q ? fmtAm(nv.q.price).replace(MINUS, "-") : "") : slip.prices[b] ?? "");
  const evals = useMemo(() => Object.fromEntries(books.map((b) => [b,
    slip.legs.length && ready ? evaluate(pricers[b], slip.legs, priceText(b), bands ?? DEFAULT_BANDS, quoteModel ?? null) : null])) as Record<BuildBook, Evaluation | null>,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pricers, slip, ready, nv.q?.price, bands, quoteModel, books.join()]);
  const e = evals[book];
  // The price we know at each book: typed, Novig's exact one, or the legs' product when it's one leg per game.
  const known = Object.fromEntries(books.map((b) => {
    const x = evals[b];
    return [b, !x ? null : x.typed != null ? x.typed : b !== "Novig" && x.games.length === slip.legs.length ? Math.round(toAm(x.naive)) : null];
  })) as Record<BuildBook, number | null>;
  const best = bestBook(known);
  const compared = books.filter((b) => known[b] != null).length > 1;
  // `marked` holds open bets only: an open slip keeps the id it was placed under, a new one gets its game day's (Nov 9)
  const id = slipId(pricer, slip.legs, (x) => !!marked[x]);
  const notHere = book !== "FanDuel" ? slip.legs.filter((l) => pricer.leg(l.event_id, l.label)?.unavailable).map((l) => l.label) : [];
  const mine = saved.find((s) => s.sgp_id === id);

  const use = (legs: SlipLeg[]) => { setMsg(null); setOpen(true); persist({ ...slips, [sport]: { legs, prices: {} } }); };
  const toggle = (eid: string, label: string) => {
    const has = slip.legs.some((l) => l.event_id === eid && l.label === label);
    const legs = has ? slip.legs.filter((l) => !(l.event_id === eid && l.label === label)) : [...slip.legs, { event_id: eid, label }];
    setMsg(null);
    if (!legs.length) setOpen(false);
    persist({ ...slips, [sport]: { ...slip, legs } });
  };
  const row = e ? customRow(pricer, slip.legs, e, id) : null;
  const nGames = new Set(slip.legs.map((l) => l.event_id)).size;
  const markInput: MarkInput | null = e && row ? { kind: "custom", sgp_id: id, price: e.typed, book, matchup: row.matchup,
    fair_price: Math.round(e.fair), p_fair: e.p, legs: slip.legs.map((l) => l.label), odds_event_id: nGames === 1 ? slip.legs[0].event_id : null,
    boost: promo.kind === "boost" ? promo.pct : null, bonus: promo.kind === "bonus",
    games: row.games.map((g) => ({ matchup: g.matchup, game_ref: g.game_ref, legs: g.legs })) } : null;
  const save = () => {
    if (!row) return;
    start(async () => { const r = await saveCustom(row, path); setMsg(r.ok ? null : r.error); });
  };
  // "I placed this": the slip is saved first (a placed parlay is graded from its saved row), then marked, as the two
  // buttons did one after the other. With a wallet token chosen (Nov 9) it goes through placePromo, as the finder does: the
  // token's id (it leaves the wallet), its dollars as the stake (one unit when it names none), its boost cap. Either way the
  // promo is cleared after, so the next slip isn't saved as a bonus or boosted bet by mistake.
  const token = tokenId ? promos.find((p) => p.promo_id === tokenId) ?? null : null;
  const clearPromo = () => { setTokenId(null); if (promo.kind !== "none") setPromo({ kind: "none" }); };
  const place = () => {
    if (!row || !markInput) return;
    start(async () => {
      if (token && promo.kind !== "none") {
        if (e?.typed == null) { setMsg(`Type ${book}'s price first: the bet is saved at it.`); return; }
        const dollars = Number(token.amount_dollars) > 0 ? Number(token.amount_dollars) : null;
        const r = await placePromo({ row, price: e.typed, book, dollars, promo_id: token.promo_id,
          promo: promo.kind === "boost" ? { kind: "boost", pct: promo.pct, maxExtra: promo.maxExtra } : { kind: "bonus" } });
        if (!r.ok) { setMsg(r.error); return; }
        setMsg(null); clearPromo();
        return;
      }
      const r = await saveCustom(row, path);
      if (!r.ok) { setMsg(r.error); return; }
      const m = await markBet(markInput, path);
      setMsg(m.ok ? null : m.error);
      if (m.ok) clearPromo();
    });
  };

  const chosen = new Set(slip.legs.map((l) => l.event_id + "|" + l.label));
  const perGame = new Map<string, number>();
  for (const l of slip.legs) perGame.set(l.event_id, (perGame.get(l.event_id) ?? 0) + 1);
  const ctx: LegCtx = { eid: current, pricer, book, chosen, toggle };

  const ideas: Idea[] = useMemo(() => (curKey !== "ideas" ? [] : SLIP_THEMES.filter((x) => x.key !== "btts" || sport === "soccer")
    .map((x) => ({ key: x.key, title: x.title, sub: x.sub, pick: themedSlip(pricer, next, x.key, 3, bans ?? []) }))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [curKey, pricer, next, sport]);

  // pictures: a team leg's logo from its game's two teams, a prop's player by name (/api/faces)
  const [faces, setFaces] = useState<Record<string, string | null>>({});
  const face = (name: string) => faces[`${sport}|${name}`] ?? null;
  const teamArt = (eid: string, team?: string): ArtOf | null => {
    if (!team) return null;
    const t = team.toLowerCase();
    return (art[eid] ?? []).find((a) => a.name.toLowerCase().includes(t) || t.includes(a.name.toLowerCase()) || a.abbr?.toLowerCase() === t) ?? null;
  };
  const legArt = (l: SlipLeg): ArtOf | null => {
    const x = packs[l.event_id]?.legs?.[l.label];
    if (x?.player) return { src: face(x.player), name: x.player, kind: "player" };
    return teamArt(l.event_id, x?.team) ?? null;
  };
  const onPage = legQ ? statTabs.flatMap((t) => t.sections.map((s) => s.title))
    : curKey === "popular" ? popular.map((l) => l.player!)
    : curKey === "ideas" ? ideas.flatMap((x) => x.pick?.legs ?? []).flatMap((l) => { const who = packs[l.event_id]?.legs?.[l.label]?.player; return who ? [who] : []; })
    : statTabs.find((t) => t.key === curKey)?.sections.map((s) => s.title) ?? [];
  const wanted = [...new Set(onPage.concat(slip.legs.flatMap((l) => { const who = packs[l.event_id]?.legs?.[l.label]?.player; return who ? [who] : []; })))]
    .filter((n) => faces[`${sport}|${n}`] === undefined).slice(0, 40);
  useEffect(() => {
    if (!wanted.length) return;
    let on = true;
    fetch(`/api/faces?sport=${encodeURIComponent(sport)}&names=${encodeURIComponent(wanted.join("|"))}`).then((r) => (r.ok ? r.json() : null)).then((j) => {
      if (on) setFaces((f) => ({ ...f, ...Object.fromEntries(wanted.map((n) => [`${sport}|${n}`, (j?.faces?.[n] as string | undefined) ?? null])) }));
    }).catch(() => { if (on) setFaces((f) => ({ ...f, ...Object.fromEntries(wanted.map((n) => [`${sport}|${n}`, null])) })); });
    return () => { on = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted.join("|"), sport]);
  const slipArt = (() => {
    const seen = new Set<string>(), out: ArtOf[] = [];
    for (const l of slip.legs) { const a = legArt(l) ?? art[l.event_id]?.[0]; if (a && !seen.has(a.name)) { seen.add(a.name); out.push(a); } }
    return out;
  })();

  // the wallet's tokens for this slip: the ones that fit it first
  const slipDec = e ? (e.typed != null ? toDec(e.typed) : e.games.length === slip.legs.length ? e.naive : null) : null;
  const tokens = promos.map((p) => ({ p, fits: slip.legs.length > 0 && tokenFits(p, { book, sport, legs: slip.legs.length, dec: slipDec,
    matchups: [...new Set(slip.legs.map((l) => packs[l.event_id]?.matchup).filter((m): m is string => !!m))] }) }))
    .sort((a, b) => Number(b.fits) - Number(a.fits));

  useEffect(() => {
    if (!open) return;
    const esc = (ev: KeyboardEvent) => { if (ev.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [open]);

  const head = (
    <>
      <div className="shead bd-head">
        <h1>Build</h1>
        <span className="shead-tools">
          {games.length > 0 && <BookMenu book={book} books={books} onPick={setBook} />}
          <Link className="ib" href="/build/saved" aria-label="Your saved parlays" title="Your saved parlays"><Icon name="saved" /></Link>
          {games.length > 0 && (
            <button type="button" className="ib" aria-label="Find a team or player" title="Find a team or player" aria-expanded={searching}
                    onClick={() => { if (searching) setQ(""); setSearching(!searching); }}><Icon name="search" /></button>
          )}
        </span>
      </div>
      {searching && (
        <div className="bd-search">
          <input ref={search} type="search" value={q} onChange={(ev) => setQ(ev.target.value)} placeholder="Find a team or player"
                 aria-label="Find a team or player" autoComplete="off" onKeyDown={(ev) => { if (ev.key === "Escape") { setQ(""); setSearching(false); } }} />
          <button type="button" className="btn quiet" onClick={() => { setQ(""); setSearching(false); }}>Close</button>
        </div>
      )}
      <BuildModes on="build" />
    </>
  );

  if (!games.length) {
    return <div className="bd">{head}<div className="card empty"><b>Nothing to build from yet</b><span>Games show up here the morning of game day, once they&apos;re priced.</span></div></div>;
  }

  const bestPrice = best ? known[best] : null;

  return (
    <div className={`bd${slip.legs.length ? " has-slip" : ""}`}>
      <section className="bd-pick">
        {head}

        {sports.length > 1 && (
          <nav className="bd-sports" aria-label="Sport">
            {sports.map((s) => (
              <button key={s} type="button" className="mk" aria-pressed={s === sport} onClick={() => { setSport(s); setQ(""); persist(slips, s); }}>
                {leagueLogo(s) && <Art kind="league" name={s} size={18} />}{SPORTS[s] ?? s}{slips[s]?.legs.length ? <b className="bd-count">{slips[s].legs.length}</b> : null}
              </button>
            ))}
          </nav>
        )}

        <div className="bd-strip-wrap">
          <button type="button" className="bd-nudge" aria-label="Earlier games" onClick={() => strip.current?.scrollBy({ left: -320, behavior: "smooth" })}>‹</button>
          <div className="bd-strip" ref={strip} role="group" aria-label="Games">
            {shown.map((g) => {
              const [a, h] = g.matchup.includes(" @ ") ? g.matchup.split(" @ ") : [g.matchup, ""];
              const n = perGame.get(g.event_id), on = g.event_id === current;
              const pair = art[g.event_id] ?? [];
              const two = pair.length === 2 ? inOrder(g.sport, pair[0], pair[1]) : pair;     // soccer: home first (Nov 5)
              const sep = two !== pair && pair.length === 2 ? " vs " : " @ ";
              return (
                <button key={g.event_id} type="button" className="bd-game" aria-current={on}
                        onClick={() => { setGame(g.event_id); if (gameHits.length) setQ(""); }}>
                  {on && two[1]?.color && <span className="bd-glow" style={{ background: two[1].color }} aria-hidden />}
                  <span className="bd-game-art">{two.map((x) => <Art key={x.name} {...x} size={34} />)}{n ? <b className="bd-count" aria-label={`${n} on your slip`}>{n}</b> : null}</span>
                  <span className="bd-game-name">{two.length === 2 && two[0].abbr && two[1].abbr ? `${two[0].abbr}${sep}${two[1].abbr}` : h ? matchupText(`${a} @ ${h}`, g.sport) : a}</span>
                  <span className="sub">{dayTime(g.commence_time)}</span>
                </button>
              );
            })}
          </div>
          <button type="button" className="bd-nudge" aria-label="Later games" onClick={() => strip.current?.scrollBy({ left: 320, behavior: "smooth" })}>›</button>
        </div>

        {!legQ && (
          <nav className="segx bd-tabs" aria-label={cur ? `Markets for ${matchupText(cur.matchup, cur.sport)}` : "Markets"}>
            {keys.map(([k, title]) => <button key={k} type="button" aria-pressed={k === curKey} onClick={() => setTab(k)}>{title}</button>)}
          </nav>
        )}

        <div className="bd-markets">
          {curKey === "ideas" && !legQ ? (
            <Ideas ideas={ideas} loading={next.some((i) => !packs[i] && !failed[i])} book={book} legArt={legArt} onUse={use} />
          ) : !pk ? <p className="sub bd-note">{failed[current] ? "Couldn't load this game's legs. Reload to try again." : "Loading legs…"}</p>
            : legQ ? (tabs.length ? tabs.map((t) => <Sections key={t.key} tab={t} ctx={ctx} face={face} heading />) : <p className="sub bd-note">No leg matches “{q}”.</p>)
            : curKey === "popular" ? (
              <>
                {lines && <MainCard lines={lines} ctx={ctx} pair={pair} />}
                <PropRows legs={popular} ctx={ctx} face={face} />
              </>
            ) : curKey === "lines" && gameTab ? <Sections tab={gameTab} ctx={ctx} face={face} />
            : statTabs.filter((t) => t.key === curKey).map((t) => <Sections key={t.key} tab={t} ctx={ctx} face={face} />)}
        </div>
      </section>

      {open && <div className="bd-scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
      <aside className={`bd-slip${open ? " open" : ""}`} id="slip" aria-label="Your slip">
        <SlipPanel legs={slip.legs} prices={slip.prices} nGames={nGames} ready={ready} book={book} setBook={setBook}
                   setPrice={(b, text) => persist({ ...slips, [sport]: { ...slip, prices: { ...slip.prices, [b]: text } } })}
                   leg={(l) => pricer.leg(l.event_id, l.label)} matchupOf={(eid) => packs[eid]?.matchup} legArt={legArt}
                   evals={evals} known={known} best={best} compared={compared} notHere={notHere} nv={nv} nvIds={nvIds} bands={bands} quoteModel={quoteModel ?? null}
                   promo={promo} setPromo={setPromo} tokens={tokens} tokenId={tokenId} setTokenId={setTokenId} fromLink={!!preset}
                   toggle={toggle} clear={() => { setMsg(null); setOpen(false); persist({ ...slips, [sport]: { ...EMPTY } }); }} close={() => setOpen(false)}
                   saved={mine} bet={marked[id]} markInput={markInput} save={save} place={place} pending={pending}
                   real={isReal(new Date(), realFrom)} msg={msg} />
      </aside>

      {slip.legs.length > 0 && !open && (
        <button type="button" className="bd-bar" onClick={() => setOpen(true)} aria-label="Open your slip">
          <ArtStack items={slipArt} size={30} max={3} />
          <span className="bd-bar-what">
            <b>{slip.legs.length} leg{slip.legs.length === 1 ? "" : "s"}{e ? ` · grade ${e.grade}` : ""}</b>
            <span>{best ? `${compared ? "best price " : ""}at ${best}` : e ? `fair ${fmtAm(e.fair)} · ${book}` : book}</span>
          </span>
          <span className="numx bd-bar-px">{bestPrice != null ? fmtAm(bestPrice) : e ? pct(e.p, 0) : ""}</span>
        </button>
      )}
    </div>
  );
}
