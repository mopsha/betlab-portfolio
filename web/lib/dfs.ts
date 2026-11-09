// The DFS optimizer's slates (Nov 5, idea #38; written by the worker's dfs.py, migration 0040). Read-only: you enter a lineup yourself.
export type DfsPlayer = { slot: string; id: string; name: string; team: string; game: string; salary: number; proj: number; basis: "market" | "average"; status: string };
export type DfsLineup = { salary: number; proj: number; players: DfsPlayer[] };
export type DfsSlate = { slate_id: string; league: string; label: string | null; lock_at: string; games: number | null;
  priced: number | null; players: number | null; lineups: DfsLineup[]; built_at: string };

/** Slates still open first, soonest lock first; then what locked in the last day. */
export function dfsOrder(rows: DfsSlate[], now = Date.now()): DfsSlate[] {
  const t = (s: DfsSlate) => Date.parse(s.lock_at);
  const open = rows.filter((s) => t(s) > now).sort((a, b) => t(a) - t(b));
  const done = rows.filter((s) => t(s) <= now && now - t(s) < 86400_000).sort((a, b) => t(b) - t(a));
  return [...open, ...done];
}
export const DFS_LOBBY: Record<string, string> = { nba: "https://www.draftkings.com/lobby#/NBA", nfl: "https://www.draftkings.com/lobby#/NFL" };
