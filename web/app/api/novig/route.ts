import { NOVIG_PRICER, novigQuote } from "@/lib/novig";

export const dynamic = "force-dynamic";

/** The Build tab's Novig price: ?ids=<outcome>,<outcome> -> Novig's exact parlay price, or { refused: true } when Novig
 *  won't combine the legs (400) or has no price right now (404). A 429 or a failure is asked again (3 tries). Free, no
 *  key; the browser can't call Novig itself (CORS). */
export async function GET(req: Request) {
  const ids = (new URL(req.url).searchParams.get("ids") ?? "").split(",").filter((x) => /^[0-9a-f-]{36}$/i.test(x));
  if (ids.length < 2 || ids.length > 20) return Response.json({ error: "2 to 20 Novig outcome ids" }, { status: 400 });
  const refused = () => Response.json({ refused: true }, { headers: { "Cache-Control": "no-store" } });
  for (let i = 0; i < 3; i++) {
    let wait = 800;
    try {
      const r = await fetch(NOVIG_PRICER, { method: "POST", headers: { "Content-Type": "application/json", "User-Agent": "BetLab" },
        body: JSON.stringify({ outcomeIds: ids }), cache: "no-store", signal: AbortSignal.timeout(6_000) });   // per try
      const body = await r.json().catch(() => null);
      const q = r.ok ? novigQuote(body) : null;
      if (q) return Response.json(q, { headers: { "Cache-Control": "no-store" } });
      if (r.status === 400 || (r.status === 404 && !String(body?.message ?? "").startsWith("Cannot "))) return refused();
      if (r.status === 429) wait = Math.min(Number(r.headers.get("Retry-After")) || 1, 5) * 1000;
      else console.error(`novig pricer: ${r.status} ${String(body?.message ?? "").slice(0, 80)}`);
    } catch { /* tried again below */ }
    if (i < 2) await new Promise((res) => setTimeout(res, wait));
  }
  return refused();
}
