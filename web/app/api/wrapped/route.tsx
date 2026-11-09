import { ImageResponse } from "next/og";
import { recordBets } from "@/lib/bets";
import { myBetsData } from "@/lib/data";
import { liveSettled, markLiveSettled } from "@/lib/live-bets";
import { isReal } from "@/lib/real";
import { periods, wrapped } from "@/lib/wrapped";

export const dynamic = "force-dynamic";

const POS = "#2fd286", NEG = "#ff6b6b", INK = "#e9ecf1", INK2 = "#a2abb8", ACCENT = "#8ea2ff";
const u = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(2)}u`;

/** Wrapped as a 1080x1350 picture (Mike's W17, Oct 27), for its Share button: the period's P/L, record, biggest hit,
 * player and type. The signed-in account's own bets only (my_bets is row-level secured). ?p=2026-10 or season. */
export async function GET(req: Request) {
  const d = await myBetsData();
  // bets the live tracker already settled count, as on My bets (its P/L and this one always agree)
  const bets = markLiveSettled(d.bets, await liveSettled(d.bets));
  const { counted } = recordBets(bets, isReal(new Date(), d.settings.real_from));
  const list = periods(counted);
  const want = new URL(req.url).searchParams.get("p");
  const p = want && list.includes(want) ? want : list[0];
  const w = p ? wrapped(counted, p) : null;
  if (!w) return new Response("Nothing to wrap yet", { status: 404 });
  const t = w.total, tone = t.units >= 0 ? POS : NEG;
  const rows: [string, string, string?][] = [
    ["Record", `${t.won}-${t.lost}${t.push ? `-${t.push}` : ""}`],
    ...(w.roi !== null ? [["ROI", `${w.roi >= 0 ? "+" : "−"}${Math.abs(w.roi * 100).toFixed(1)}%`, w.roi >= 0 ? POS : NEG] as [string, string, string]] : []),
    ...(w.best ? [["Biggest hit", `${w.best.price.split(" ")[0]} · ${u(w.best.units)}`, POS] as [string, string, string]] : []),
    ...(w.heartbreak ? [["Heartbreaker", `${w.heartbreak.hit} of ${w.heartbreak.hit + 1} at ${w.heartbreak.bet.price.split(" ")[0]}`] as [string, string]] : []),
    ...(w.player ? [["Your player", w.player.name] as [string, string]] : []),
    ...(w.book && w.books.length > 1 ? [["Best book", w.book.group] as [string, string]] : []),
    ...(w.bestRun > 1 ? [["Longest streak", `${w.bestRun} wins`] as [string, string]] : []),
  ];
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: "#0d0f13", color: INK,
        padding: "72px 72px 64px", fontSize: 32, backgroundImage: `radial-gradient(circle at 85% 0%, ${tone}33, transparent 55%)` }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 34, color: INK2 }}>
          <div style={{ display: "flex" }}><span style={{ color: INK }}>Bet</span><span style={{ color: ACCENT }}>Lab</span><span style={{ marginLeft: 14 }}>Wrapped</span></div>
          <span>{t.bets} bets · {w.days} days</span>
        </div>
        <div style={{ display: "flex", marginTop: 64, fontSize: 64, color: INK2 }}>{w.period === "season" ? "My season" : `My ${w.name}`}</div>
        <div style={{ display: "flex", marginTop: 8, fontSize: 168, letterSpacing: -4, color: tone, lineHeight: 1 }}>{u(t.units)}</div>
        <div style={{ display: "flex", flexDirection: "column", marginTop: 48, padding: "16px 36px", borderRadius: 28, background: "#161a20",
          border: "2px solid #262c35", flexGrow: 1 }}>
          {rows.map(([k, v, c], i) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "18px 0",
              borderTop: i ? "1px solid #262c35" : "none", fontSize: 38 }}>
              <span style={{ color: INK2 }}>{k}</span><span style={{ color: c ?? INK }}>{v}</span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", marginTop: 40 }}>
          <span style={{ fontSize: 28, color: INK2 }}>My betting type</span>
          <span style={{ fontSize: 64, color: ACCENT, letterSpacing: -1 }}>{w.persona.name}</span>
        </div>
      </div>
    ),
    { width: 1080, height: 1350, headers: { "Cache-Control": "private, no-store" } },
  );
}
