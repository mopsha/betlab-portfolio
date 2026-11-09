import { ImageResponse } from "next/og";
import { myBetsData } from "@/lib/data";
import { card } from "@/lib/share";

export const dynamic = "force-dynamic";

const TONE = { win: "#2fd286", loss: "#ff6b6b", even: "#a2abb8", open: "#8ea2ff" } as const;
const DOT = { won: "#2fd286", lost: "#ff6b6b", void: "#6f7886", open: "#3a424e" } as const;

/** A bet as a 1080x1350 picture (Mike's W13, Oct 24), for the Share button. Only the signed-in account's own bets:
 * my_bets is row-level secured, so another account's id finds nothing. */
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const b = (await myBetsData()).bets.find((x) => x.bet_id === id);
  if (!b) return new Response("Not found", { status: 404 });
  const c = card(b);
  const tone = TONE[c.tone];
  const legSize = c.legs.length > 7 ? 30 : 36;
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: "#0d0f13", color: "#e9ecf1",
        padding: "72px 72px 60px", fontSize: 32 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 34, color: "#a2abb8" }}>
          <div style={{ display: "flex" }}><span style={{ color: "#e9ecf1" }}>Bet</span><span style={{ color: "#8ea2ff" }}>Lab</span></div>
          <span>{c.book} · {c.when}</span>
        </div>
        <div style={{ display: "flex", marginTop: 56, fontSize: c.status.length > 8 ? 88 : 120, letterSpacing: -2, color: tone, lineHeight: 1 }}>{c.status}</div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 28 }}>
          <span style={{ fontSize: 44 }}>{c.title}</span>
          <span style={{ fontSize: 48, color: "#e9ecf1" }}>{c.price}</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", marginTop: 36, padding: "28px 32px", borderRadius: 28, background: "#161a20",
          border: `2px solid ${tone}40`, flexGrow: 1 }}>
          {c.legs.map((l, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", padding: "12px 0", borderTop: i ? "1px solid #262c35" : "none", fontSize: legSize }}>
              <div style={{ width: 26, height: 26, borderRadius: 13, background: DOT[l.result], marginRight: 22, flexShrink: 0 }} />
              <span style={{ flexGrow: 1, color: l.result === "lost" ? "#ff9b9b" : "#e9ecf1" }}>{l.label}</span>
              {l.value && <span style={{ color: "#a2abb8", marginLeft: 16 }}>{l.value}</span>}
            </div>
          ))}
          {c.more > 0 && <div style={{ display: "flex", paddingTop: 12, color: "#a2abb8", fontSize: 28 }}>+{c.more} more legs</div>}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 40 }}>
          <span style={{ fontSize: 76, color: tone, letterSpacing: -1 }}>{c.headline}</span>
          <span style={{ fontSize: 30, color: "#a2abb8" }}>{c.detail}</span>
        </div>
      </div>
    ),
    { width: 1080, height: 1350, headers: { "Cache-Control": "private, no-store" } },
  );
}
