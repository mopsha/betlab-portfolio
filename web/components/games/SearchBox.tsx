"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { CardTap } from "@/components/games/Cards";
import { Art, ArtStack } from "@/components/ui/Art";
import { gameHref } from "@/components/today/GameRow";
import { SPORTS } from "@/lib/format";
import type { SearchResults } from "@/lib/data";
import { betName } from "@/lib/gameday";
import { sidesOf, teamMark } from "@/lib/wallet-view";

const WAIT_MS = 300;
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "");

/** Teams, players, fighters, games and your bets. A team or player opens your record with it; a game opens its page. */
export function SearchBox() {
  const [q, setQ] = useState("");
  const [r, setR] = useState<SearchResults | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (q.trim().length < 2) { setR(null); setFailed(false); return; }
    const stop = new AbortController();
    const t = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q.trim())}`, { signal: stop.signal, cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        setR(await res.json()); setFailed(false);
      } catch (e) { if ((e as Error).name !== "AbortError") setFailed(true); }
    }, WAIT_MS);
    return () => { clearTimeout(t); stop.abort(); };
  }, [q]);
  const none = r && !r.teams.length && !r.players.length && !r.games.length && !r.bets.length;
  const row = (art: ReactNode, title: string, sub: string) => <>{art}<span className="srow-what"><b>{title}</b>{sub && <small>{sub}</small>}</span>
    <span className="chev" aria-hidden>›</span></>;
  const pair = (matchup: string | null | undefined) => <ArtStack items={sidesOf(matchup).map((n) => ({ ...teamMark(n), kind: "team" as const }))} size={28} max={2} />;
  return (
    <>
      <label className="searchfield">
        <span className="sr-only">Search teams, players, fighters and your bets</span>
        <svg aria-hidden viewBox="0 0 24 24" width="18" height="18"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2.2" />
          <path d="m20 20-3.6-3.6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" /></svg>
        <input id="search" type="search" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Teams, players, fighters, your bets" />
      </label>
      {failed && <p className="faint" role="alert">Search didn&apos;t answer. Try again.</p>}
      <div aria-live="polite">
        {none && <p className="faint">Nothing found for &ldquo;{q.trim()}&rdquo;.</p>}
        {!!r?.teams.length && <><h2 className="day">Teams</h2><div className="srows">
          {r.teams.map((t) => <CardTap key={`${t.sport}${t.name}`} card={{ kind: "team", name: t.name, abbr: t.abbr[0] }} sport={t.sport} className="card srow">
            {row(<Art {...teamMark(t.name)} name={t.name} size={40} />, t.name, SPORTS[t.sport] ?? t.sport)}</CardTap>)}
        </div></>}
        {!!r?.players.length && <><h2 className="day">Players</h2><div className="srows">
          {r.players.map((p) => <CardTap key={p.title} card={{ kind: "player", name: p.title }} sport={p.sport} className="card srow">
            {row(<Art src={p.photo} name={p.title} kind="player" size={40} />, p.title, SPORTS[p.sport] ?? p.sport)}</CardTap>)}
        </div></>}
        {!!r?.games.length && <><h2 className="day">Games</h2><div className="srows">
          {r.games.map((g) => {
            const body = row(pair(g.title), g.title, when(g.at));
            return g.game_id ? <Link key={`${g.title}${g.at}`} className="card srow" href={gameHref(g.game_id)}>{body}</Link>
              : <div key={`${g.title}${g.at}`} className="card srow">{body}</div>;
          })}
        </div></>}
        {!!r?.bets.length && <><h2 className="day">Your bets</h2><div className="srows">
          {r.bets.map((b) => <Link key={b.bet_id} className="card srow" href="/bets?view=settled">
            {row(pair(b.matchup), betName(b), when(b.placed_at))}</Link>)}
        </div></>}
      </div>
    </>
  );
}
