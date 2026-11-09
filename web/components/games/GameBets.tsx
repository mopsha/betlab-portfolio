"use client";

// "Your bet" on a game's page (the overhaul, Nov 4): each of your open bets with a leg on this game, as a small card
// with those legs as rings, from the same /api/live poll as Live. A tap opens Live.
import Link from "next/link";
import { LegRing, LiveProvider, useLive } from "@/components/live/LiveBets";
import { fmtAm } from "@/lib/format";

export type OpenBet = { id: string; name: string; price: number | null };

function Rows({ bets, espnId, teams }: { bets: OpenBet[]; espnId: string; teams: [string, string] }) {
  const data = useLive();
  if (!data) return null;
  const on = bets.flatMap((bet) => {
    const b = data.bets[bet.id];
    const g = b?.games.find((x) => (espnId && x.espnId === espnId) || (x.home.name === teams[1] && x.away.name === teams[0]));
    return b && g ? [{ bet, b, legs: b.legs.filter((l) => l.gameKey === g.key) }] : [];
  });
  if (!on.length) return null;
  return (
    <div className="yourbets">
      {on.map(({ bet, b, legs }) => (
        <Link className="card yourbet" href="/bets" key={bet.id}>
          <span className="yb-what">
            <span className="cap">Your bet</span>
            <span className="yb-name">{bet.name}{bet.price !== null && <> <span className="numx">{fmtAm(bet.price)}</span></>}</span>
            {b.legs.length > legs.length && <span className="sub">{legs.length} of its {b.legs.length} legs are on this game</span>}
          </span>
          <span className="tl-rings">{legs.slice(0, 5).map((l, i) => <LegRing key={`${i}-${l.label}`} l={l} tap={false} size={legs.length > 4 ? 40 : 46} />)}
            {legs.length > 5 && <span className="sub">+{legs.length - 5}</span>}</span>
        </Link>
      ))}
    </div>
  );
}

export function GameBets({ bets, espnId, teams }: { bets: OpenBet[]; espnId: string; teams: [string, string] }) {
  if (!bets.length) return null;
  return <LiveProvider><Rows bets={bets} espnId={espnId} teams={teams} /></LiveProvider>;
}
