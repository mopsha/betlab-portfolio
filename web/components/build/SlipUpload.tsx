"use client";

// Snap a slip (Oct 24): pick sportsbook screenshots, Claude reads them (/api/slip), you check each draft, and each is
// saved as a real bet that tracks, alerts and grades like the rest. Several at once (Mike, Oct 25: "multiple pics in
// case it doesn't fit on one screen or multiple bets at once", and "add from clipboard"): choose several files, or
// paste (Cmd/Ctrl+V anywhere on the page, or the Paste button); one slip across screens comes back as one bet. Each
// image is shrunk on the device first (a screenshot is several MB) and never stored. A draft whose odds sit well above
// its legs' own prices multiplied is flagged before saving (Oct 27: four misread slips paid 2-4.6x that, impossible).

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { addSlipBet } from "@/lib/actions";
import { betName } from "@/lib/gameday";
import { chooseGame, easternIso, fairOf, priceCheck, slipEv, type Draft, type GameChoice } from "@/lib/slip";
import { parseOdds } from "@/lib/format";
import { expiresText, promoTerms, promoTitle, slipToken, slipTokens, type PromoRow } from "@/lib/promos";

const UNIT_KEY = "betlab-unit-dollars";
const MAX_SIDE = 1600;
const MAX_IMAGES = 6;

/** A picked or pasted image as a JPEG data URL, at most 1600px on its long side. */
export async function shrink(file: Blob): Promise<string> {
  const img = await createImageBitmap(file);
  const k = Math.min(1, MAX_SIDE / Math.max(img.width, img.height));
  const c = document.createElement("canvas");
  c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
  c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", 0.85);
}

const localInput = (iso: string) => {   // an instant as a datetime-local value in Eastern time
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
};

// the wager and boost stay as typed until saved (Nov 9: a number field dropped the "." as it was typed, so $2.50 became 250);
// promoId: the wallet token chosen for it (Nov 9); undefined until one is picked, when the one that fits (if only one) is offered
type Item = { id: number; d: Draft; placed: string; priceText: string; stakeText: string; boostText: string; saved: boolean;
              choices: GameChoice[]; promoId?: string | null };
/** The typed dollars or percent as a number ("2." is 2 while typing); 0 when there's nothing. */
const typedNum = (t: string) => Number(t.replace(/[^0-9.]/g, "")) || 0;
const clock = (iso: string) => new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", hour: "numeric", minute: "2-digit" });

/** The wallet tokens a draft may have used (lib/promos.ts slipTokens), and the one chosen: picked, or the only one that fits. */
function draftTokens(it: Item, tokens: PromoRow[]) {
  const boost = typedNum(it.boostText);
  const s = { book: it.d.book, bonus: it.d.bonus, boost_pct: boost > 0 ? boost : null, stake_dollars: typedNum(it.stakeText), price: parseOdds(it.priceText), legs: it.d.legs.length };
  const fits = slipTokens(s, tokens);
  const chosen = it.promoId === undefined ? slipToken(s, tokens)?.promo_id ?? null : fits.some((p) => p.promo_id === it.promoId) ? it.promoId : null;
  return { fits, chosen };
}

export function SlipUpload({ ready, unitDollars, tokens = [] }: { ready: boolean; unitDollars?: number | null; tokens?: PromoRow[] }) {
  const router = useRouter();
  const [images, setImages] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  // the account's unit (Settings, Oct 30); this device's old one until the account has one
  const [unit, setUnit] = useState(unitDollars ? String(unitDollars) : "5");
  useEffect(() => { if (unitDollars) return; try { const u = localStorage.getItem(UNIT_KEY); if (u) setUnit(u); } catch { /* default $5 */ } }, [unitDollars]);

  async function add(blobs: Blob[]) {
    const pics = blobs.filter((b) => b.type.startsWith("image/"));
    if (!pics.length) { setErr("No image there: copy a screenshot first."); return; }
    setErr(null); setItems([]);
    try {
      const shrunk = await Promise.all(pics.map(shrink));
      setImages((have) => {
        const next = [...have, ...shrunk];
        if (next.length > MAX_IMAGES) setErr(`Up to ${MAX_IMAGES} screenshots at a time: kept the first ${MAX_IMAGES}.`);
        return next.slice(0, MAX_IMAGES);
      });
    } catch { setErr("That file isn't an image this browser can open."); }
  }
  // Cmd/Ctrl+V anywhere on the page adds what's on the clipboard
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const files = [...(e.clipboardData?.files ?? [])];
      if (files.length && ready) { e.preventDefault(); add(files); }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  });
  async function pasteButton() {
    try {
      const got: Blob[] = [];
      for (const it of await navigator.clipboard.read()) {
        const t = it.types.find((x) => x.startsWith("image/"));
        if (t) got.push(await it.getType(t));
      }
      await add(got);
    } catch { setErr("The browser didn't allow pasting here: press Cmd/Ctrl+V, or choose the file."); }
  }
  async function read() {
    if (!images.length) return;
    setBusy(true); setErr(null);
    try {
      const r = await fetch("/api/slip", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ images }) });
      const j = await r.json().catch(() => ({}));
      const drafts: { draft: Draft & { choices?: GameChoice[] }; placed_at: string }[] = j.drafts ?? (j.draft ? [{ draft: j.draft, placed_at: j.placed_at }] : []);
      if (!r.ok || !drafts.length) { setErr(j.error ?? "Couldn't read that slip."); return; }
      setItems(drafts.map((x, i) => { const { choices = [], ...d } = x.draft; return { id: i, d, placed: localInput(x.placed_at), saved: false,
                                       priceText: `${d.price > 0 ? "+" : ""}${d.price}`, stakeText: String(d.stake_dollars ?? ""),
                                       boostText: d.boost_pct ? String(d.boost_pct) : "", choices }; }));
    } catch { setErr("You look offline: try again."); }
    finally { setBusy(false); }
  }
  const update = (id: number, f: (x: Item) => Item) => setItems((xs) => xs.map((x) => (x.id === id ? f(x) : x)));
  async function save(it: Item) {
    const price = parseOdds(it.priceText);
    if (price == null) { setErr("Enter the book's odds, like +978 or -110."); return; }
    const stake = typedNum(it.stakeText), boost = typedNum(it.boostText);
    if (!(stake > 0)) { setErr("Enter the wager in dollars, like 2.50."); return; }
    setBusy(true); setErr(null);
    try { localStorage.setItem(UNIT_KEY, unit); } catch { /* this time only */ }
    const r = await addSlipBet({ ...it.d, price, stake_dollars: stake, boost_pct: boost > 0 ? boost : null }, Number(unit),
                               easternIso(`${it.placed}:00`), draftTokens(it, tokens).chosen);   // the time typed is Eastern
    setBusy(false);
    if (!r.ok) { setErr(r.error); return; }
    const left = items.filter((x) => x.id !== it.id && !x.saved).length;
    if (!left) router.push("/bets");
    else update(it.id, (x) => ({ ...x, saved: true }));
  }
  const reset = () => { setItems([]); setImages([]); setErr(null); };

  return (
    <div className="slip">
      {!ready && <p className="banner">Reading slips is waiting for its key: add ANTHROPIC_API_KEY to the web service in Railway.</p>}
      {!items.length && <>
        <div className="slip-pics">
          {images.map((src, i) => (
            <figure key={i} className="slip-pic">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={src} alt={`Screenshot ${i + 1}`} />
              <button type="button" className="btn quiet small" onClick={() => setImages((xs) => xs.filter((_, k) => k !== i))}
                      aria-label={`Remove screenshot ${i + 1}`}>✕</button>
            </figure>
          ))}
          {images.length < MAX_IMAGES && (
            <label className="slip-pick">
              <input type="file" accept="image/*" multiple onChange={(e) => { add([...(e.target.files ?? [])]); e.target.value = ""; }}
                     disabled={!ready || busy} />
              <span>{images.length ? "+ Another screenshot" : "Choose screenshots of your slips"}</span>
            </label>
          )}
        </div>
        <div className="actions">
          <button type="button" className="btn quiet" onClick={pasteButton} disabled={!ready || busy}>Paste</button>
          {images.length > 0 && <button className="btn" onClick={read} disabled={!ready || busy}>
            {busy ? "Reading…" : images.length > 1 ? `Read ${images.length} screenshots` : "Read slip"}</button>}
        </div>
        <p className="faint">One slip across several screens comes back as one bet; different bets come back one each. You can also paste a screenshot (Cmd/Ctrl+V).</p>
      </>}
      {err && <p className="err" role="status">{err}</p>}

      {items.map((it) => it.saved ? (
        <p key={it.id} className="card slip-saved">Saved: {betName({ legs: it.d.legs.map((l) => l.label) })} ✓</p>
      ) : (
        <form key={it.id} className="card slip-draft" onSubmit={(e) => { e.preventDefault(); save(it); }}>
          {items.length > 1 && <h3 className="section-label">Bet {it.id + 1} of {items.length}</h3>}
          <div className="slip-grid">
            <label className="field">Book<select value={it.d.book} onChange={(e) => update(it.id, (x) => ({ ...x, d: { ...x.d, book: e.target.value as Draft["book"] } }))}>
              {["FanDuel", "DraftKings", "Novig"].map((b) => <option key={b}>{b}</option>)}</select></label>
            <label className="field">Odds (before boost)<input value={it.priceText} onChange={(e) => update(it.id, (x) => ({ ...x, priceText: e.target.value }))} /></label>
            <label className="field">Wager $<input inputMode="decimal" value={it.stakeText}
              onChange={(e) => { const t = e.target.value.replace(/[^0-9.]/g, ""); update(it.id, (x) => ({ ...x, stakeText: t, d: { ...x.d, stake_dollars: typedNum(t) } })); }} /></label>
            <label className="field">Your unit $<input inputMode="decimal" value={unit} onChange={(e) => setUnit(e.target.value.replace(/[^0-9.]/g, ""))} /></label>
            <label className="field">Profit boost %<input inputMode="decimal" value={it.boostText} placeholder="none"
              onChange={(e) => { const t = e.target.value.replace(/[^0-9.]/g, ""), n = typedNum(t); update(it.id, (x) => ({ ...x, boostText: t, d: { ...x.d, boost_pct: n > 0 ? n : null } })); }} /></label>
            <label className="field">Placed (ET)<input type="datetime-local" value={it.placed} onChange={(e) => update(it.id, (x) => ({ ...x, placed: e.target.value }))} /></label>
          </div>
          <label className="field toggle"><input type="checkbox" checked={it.d.bonus}
            onChange={(e) => update(it.id, (x) => ({ ...x, d: { ...x.d, bonus: e.target.checked } }))} />Bonus bet</label>
          <label className="field toggle" title="FanDuel's Bet Protect+: 3% of the stake on top; a leg on a player who sits counts as won">
            <input type="checkbox" checked={it.d.protect === true}
            onChange={(e) => update(it.id, (x) => ({ ...x, d: { ...x.d, protect: e.target.checked } }))} />Bet Protect+</label>
          <label className="field toggle" title="A bet reset token: if this loses, the stake comes back as a bonus bet in your wallet">
            <input type="checkbox" checked={it.d.reset === true}
            onChange={(e) => update(it.id, (x) => ({ ...x, d: { ...x.d, reset: e.target.checked } }))} />Bet reset</label>
          <TokenPick it={it} tokens={tokens} pick={(id) => update(it.id, (x) => ({ ...x, promoId: id }))} />
          <ol className="slip-legs">
            {it.d.legs.map((l, i) => (
              <li key={i}>
                <input value={l.label} aria-label={`Leg ${i + 1}`}
                  onChange={(e) => update(it.id, (x) => ({ ...x, d: { ...x.d, legs: x.d.legs.map((y, k) => (k === i ? { ...y, label: e.target.value, prices: undefined } : y)) } }))} />
                <span className={l.matched ? "faint" : "warn-text"}>{l.matched ? `${l.matchup}${l.game_ref ? "" : " · no grading ref"}` : `${l.matchup} · no game found: tracks by name`}</span>
                {!l.matched && it.choices.length > 0 && (
                  <select className="slip-game" aria-label={`Game for leg ${i + 1}`} value=""
                    onChange={(e) => { const c = it.choices[Number(e.target.value)]; if (c) update(it.id, (x) => ({ ...x, d: { ...x.d, legs: x.d.legs.map((y, k) => (k === i ? chooseGame(y, c) : y)) } })); }}>
                    <option value="" disabled>Pick its game…</option>
                    {it.choices.map((c, k) => <option key={k} value={k}>{`${c.sport.toUpperCase()} · ${c.matchup} · ${clock(c.start)}`}</option>)}
                  </select>
                )}
                <button type="button" className="btn quiet small" aria-label={`Remove leg ${i + 1}`}
                  onClick={() => update(it.id, (x) => ({ ...x, d: { ...x.d, legs: x.d.legs.filter((_, k) => k !== i) } }))}>Remove</button>
              </li>
            ))}
          </ol>
          <PriceFlag d={it.d} priceText={it.priceText} />
          <SlipValueLine d={it.d} priceText={it.priceText} />
          <div className="actions">
            <button className="btn" disabled={busy || !it.d.legs.length}>{busy ? "Saving…" : "Save bet"}</button>
            <button type="button" className="btn quiet" onClick={() => setItems((xs) => xs.filter((x) => x.id !== it.id))}>Skip this one</button>
          </div>
        </form>
      ))}
      {items.length > 0 && <div className="actions">
        <button type="button" className="btn quiet" onClick={reset}>Start over</button>
      </div>}
      {items.length > 0 && <p className="faint">Check the legs against your slips: the wording is what the tracker and the grading read.</p>}
    </div>
  );
}

const am = (n: number) => `${n > 0 ? "+" : ""}${n}`;

/** A bonus bet or boosted slip (Nov 9): which wallet token it used, so it leaves the wallet as I used it would. The only one that
 *  fits starts chosen; with several, you pick. Nothing shows when no token fits. */
function TokenPick({ it, tokens, pick }: { it: Item; tokens: PromoRow[]; pick: (id: string | null) => void }) {
  const { fits, chosen } = draftTokens(it, tokens);
  if (!fits.length) return null;
  return (
    <label className="field">From your wallet
      <select value={chosen ?? ""} onChange={(e) => pick(e.target.value || null)}>
        <option value="">{fits.length === 1 ? "Not this one" : "Pick the token it used"}</option>
        {fits.map((p) => <option key={p.promo_id} value={p.promo_id}>{[promoTitle(p), p.book, promoTerms(p), expiresText(p)].filter(Boolean).join(" · ")}</option>)}
      </select>
      <span className="faint">{chosen ? "Saved with this token: it leaves your wallet." : "None: the wallet keeps every token."}</span>
    </label>
  );
}

/** Is this parlay +EV? The slip's fair price from its games' simulated draws, against what it pays with any boost or bonus. Our
 * market-anchored estimate, not a promise; it goes once a leg is edited, since it was worked out on the legs as read. */
function SlipValueLine({ d, priceText }: { d: Draft; priceText: string }) {
  const price = parseOdds(priceText), fair = fairOf(d);
  if (d.fair && !fair && d.fair.missing.length) return <p className="faint" role="status">No fair price: {d.fair.missing.join(", ")} {d.fair.missing.length === 1 ? "isn't" : "aren't"} in our prices (a game that's started is gone).</p>;
  if (!fair || price == null) return null;
  const v = slipEv(fair.p, price, d.boost_pct, d.bonus);
  const say = v.verdict === "plus" ? "+EV" : v.verdict === "minus" ? "−EV" : "About even";
  return (
    <p className="card calrow" role="status" style={{ margin: "8px 0" }}>
      <span><b>{say}</b> <span className="faint">fair {am(v.fair)}, this pays {am(price)}{d.boost_pct ? ` with a ${d.boost_pct}% boost` : ""}{d.bonus ? " as a bonus bet" : ""}</span></span>
      <b>{v.ev > 0 ? "+" : ""}{(v.ev * 100).toFixed(1)}%</b>
    </p>
  );
}

/** The read odds against the legs' own prices at that book, multiplied: a parlay can't pay much more than that, so a
 * price far above it means a misread leg or price. Shown only when every leg has a price at the book. */
function PriceFlag({ d, priceText }: { d: Draft; priceText: string }) {
  const c = priceCheck(d.legs, d.book, parseOdds(priceText));
  if (!c?.flag) return null;
  return (
    <p className="banner" role="status">
      These odds don't fit these legs: at {d.book} the {d.legs.length === 1 ? "leg pays" : `${d.legs.length} legs multiplied pay`} {am(c.legs_price)},
      and a parlay never pays much more than that ({c.ratio.toFixed(1)}x here). Check the odds and each leg against your slip.
    </p>
  );
}
