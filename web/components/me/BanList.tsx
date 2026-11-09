"use client";

import { useState, useTransition } from "react";
import { setBans } from "@/lib/actions";
import type { Ban } from "@/lib/bans";
import TEAMS from "@/lib/teams.json";
import { SetGroup } from "@/components/me/SettingsKit";

const LEAGUES: Record<string, string> = { nfl: "NFL", nba: "NBA", nhl: "NHL" };
const TEAM_NAMES = Object.entries(TEAMS as Record<string, { name: string }[]>)
  .flatMap(([lg, rows]) => rows.map((r) => ({ lg, name: r.name })));

/** Settings > Ban list (Oct 25): players and teams BetLab gives no bets on. Their games and stats still show; their
 *  props and sides leave Home, game pages, the promo finder, the worker's tickets and your pick alerts. */
export function BanList({ bans }: { bans: Ban[] }) {
  const [list, setList] = useState<Ban[]>(bans);
  const [kind, setKind] = useState<"player" | "team">("player");
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const save = (next: Ban[]) => {
    const before = list;
    setList(next); setMsg(null);
    start(async () => {
      const r = await setBans(next);
      if (!r.ok) { setList(before); setMsg(r.error); }
    });
  };
  const add = (e: React.FormEvent) => {
    e.preventDefault();
    const n = name.trim();
    if (!n) return;
    // a team picked from the list keeps its league, so "Jets" in the NFL never bans Winnipeg
    const known = kind === "team" ? TEAM_NAMES.find((t) => t.name.toLowerCase() === n.toLowerCase()) : undefined;
    if (list.some((b) => b.kind === kind && b.name.toLowerCase() === n.toLowerCase())) { setName(""); return; }
    save([...list, { kind, name: known?.name ?? n, league: known?.lg ?? null }]);
    setName("");
  };
  return (
    <>
      <SetGroup title={list.length ? `Banned · ${list.length}` : "Banned"}>
        {list.length === 0 ? <p className="st-status">Nobody banned.</p> : list.map((b, i) => (
          <div className="st-line" key={`${b.kind}-${b.name}`}>
            <span className="st-name">{b.name}<small>{b.kind === "team" ? "Team" : "Player"}{b.league ? ` · ${LEAGUES[b.league] ?? b.league}` : ""}</small></span>
            <button type="button" className="btn quiet" disabled={pending} aria-label={`Remove ${b.name}`}
                    onClick={() => save(list.filter((_, j) => j !== i))}>Remove</button>
          </div>
        ))}
      </SetGroup>
      <form onSubmit={add}>
        <SetGroup title="Add" foot="BetLab won't suggest bets on these: a player's props, a team's moneyline, spread or to-win, in picks, parlays, the promo finder and pick alerts. Their games and stats still show. Totals aren't on anyone, so they stay.">
          <div className="st-chips" role="group" aria-label="Ban a">
            {(["player", "team"] as const).map((k) => (
              <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}>{k === "player" ? "Player" : "Team"}</button>
            ))}
          </div>
          <label className="st-field"><span>Name</span>
            <input value={name} list={kind === "team" ? "ban-teams" : undefined} placeholder={kind === "team" ? "New York Jets" : "Josh Allen"}
                   onChange={(e) => { setName(e.target.value); setMsg(null); }} style={{ width: 200 }} />
          </label>
        </SetGroup>
        <datalist id="ban-teams">{TEAM_NAMES.map((t) => <option key={t.lg + t.name} value={t.name}>{LEAGUES[t.lg]}</option>)}</datalist>
        <div className="actions" style={{ marginTop: 14 }}><button className="btn" disabled={pending || !name.trim()}>Ban {kind}</button></div>
      </form>
      {msg && <p className="err" role="status">{msg}</p>}
    </>
  );
}
