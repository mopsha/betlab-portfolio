import { SubHead } from "@/components/ui/Kit";
import { dfsData } from "@/lib/data";
import { DFS_LOBBY, dfsOrder } from "@/lib/dfs";
import { SPORTS } from "@/lib/format";

export const dynamic = "force-dynamic";

const money = (n: number) => `$${n.toLocaleString("en-US")}`;
const lockTime = (iso: string) => new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", hour: "numeric", minute: "2-digit" });

/** Me > Extras > DFS lineups (Nov 5, idea #38): the best DraftKings classic lineups at what the betting market expects of each
 *  player. Built by the worker each pregame tick until the slate locks (dfs.py). */
export default async function DfsPage() {
  const slates = dfsOrder(await dfsData());
  return (
    <main className="rail">
      <SubHead title="DFS lineups" />
      <p className="sub">The most projected points under DraftKings&apos; cap, from the betting market&apos;s prices. Not a pick: contests take about 15%, and this doesn&apos;t know who else is playing whom.</p>
      {!slates.length && <div className="card empty"><b>DFS lineups are off</b><span>DraftKings blocks BetLab&apos;s server from reading its salaries, so nothing is built.</span></div>}
      {slates.map((s) => {
        const locked = Date.parse(s.lock_at) <= Date.now();
        return (
          <section key={s.slate_id} className="dfs-slate">
            <h2 className="section-title"><span>{SPORTS[s.league] ?? s.league.toUpperCase()} · {s.label}</span></h2>
            <p className="sub">{locked ? "Locked" : "Locks"} {lockTime(s.lock_at)} · {s.games} game{s.games === 1 ? "" : "s"} · {s.priced} of {s.players} players priced by the market{!locked && DFS_LOBBY[s.league] ? <> · <a href={DFS_LOBBY[s.league]} target="_blank" rel="noreferrer">Open DraftKings</a></> : null}</p>
            {s.lineups.map((l, i) => (
              <article key={i} className="card dfs-lineup">
                <header><b>Lineup {i + 1}</b><span className="mono">{l.proj.toFixed(1)} proj · {money(l.salary)}</span></header>
                <ul>
                  {l.players.map((p) => (
                    <li key={p.id}>
                      <span className="dfs-slot">{p.slot}</span>
                      <span className="grow">{p.name} <small>{p.team}{p.status ? ` · ${p.status}` : ""}</small></span>
                      <span className="mono faint">{money(p.salary)}</span>
                      <span className="mono dfs-proj" title={p.basis === "market" ? "From the market's lines" : "His DraftKings average: no lines for him"}>{p.proj.toFixed(1)}{p.basis === "average" ? "*" : ""}</span>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
            {s.lineups.some((l) => l.players.some((p) => p.basis === "average")) && <p className="sub">* His DraftKings average: the market has no lines for him.</p>}
          </section>
        );
      })}
    </main>
  );
}
