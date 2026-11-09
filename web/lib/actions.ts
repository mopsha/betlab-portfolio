"use server";

import { toggled } from "./watch";
import { revalidatePath } from "next/cache";
import type { CustomRow } from "./builder";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { fixtureWrites, friendBets, myId, packParts, settingsData, socialData, todosData, unitOf, type Bet, type MyBet, type Settings, type Todo } from "./data";
import { betKey, canTail, cleanHandle, REACTIONS, tailRow, type Profile } from "./social";
import { BOOKS, bookOf } from "./books";
import { num, parseOdds } from "./format";
import { isReal } from "./real";
import { fixtureMode } from "./mode";
import { placed } from "./order";
import { betRow, fairOf, type Draft } from "./slip";
import { bonusLeft, cleanPromo, promoUsable, type PromoRow } from "./promos";
import { cleanBans, type Ban } from "./bans";
import { supabaseServer } from "./supabase/server";
import { type FontId, type ThemeId, fontOf, themeOf } from "@/lib/looks";
import { ladderState, type Ladder } from "./ladder";

export type MarkInput = {
  kind: "pick" | "lean" | "parlay" | "custom"; pick_id?: string | null; sgp_id?: string | null;
  price?: number | null; label?: string | null; matchup?: string | null; fair_price?: number | null;
  p_fair?: number | null; legs?: string[] | null; odds_event_id?: string | null;
  book?: string | null;   // the book the bet is priced at (Oct 12: FanDuel or DraftKings); parlays are FanDuel's until day 4
  boost?: number | null;  // a profit boost in percent (Oct 22: marked from Build's promo mode)
  bonus?: boolean;        // a bonus bet (Build's promo mode)
  games?: { matchup: string; game_ref?: string | null; legs: string[] }[] | null;   // a Build slip's games, each with its legs
};
export type Result = { ok: true } | { ok: false; error: string };

const done = (path?: string): Result => {
  revalidatePath("/", "layout");
  if (path) revalidatePath(path);
  return { ok: true };
};

function friendly(message: string): string {
  if (/row-level security|permission denied/i.test(message)) return "You can view this but not change it.";
  if (/duplicate key/i.test(message)) return "Already marked.";
  return "Couldn't save that. Try again in a moment.";
}

/** Mark a pick, lean or parlay as yours. Paper until Oct 18; from then a placed bet: 1 unit at the price
 *  shown, both editable after (Mike, 2026-10-02; units only since Oct 12). Writes as the signed-in user. */
export async function markBet(input: MarkInput, path?: string): Promise<Result> {
  const settings = await settingsData();
  const real = isReal(new Date(), settings.real_from);        // each account's own start (Oct 10)
  const stake = real ? 1 : null;
  const row = { ...input, book: bookOf(input.book), mode: real ? ("real" as const) : ("paper" as const), stake };
  if (fixtureMode()) {
    fixtureWrites.bets.push({ bet_id: crypto.randomUUID(), placed_at: new Date().toISOString(), ...row } as Bet);
    return done(path);
  }
  const sb = await supabaseServer();
  const { error } = await sb.from("bets").insert(row);
  return error ? { ok: false, error: friendly(error.message) } : done(path);
}

export async function undoBet(key: { pick_id?: string | null; sgp_id?: string | null }, path?: string): Promise<Result> {
  const [col, val] = key.pick_id ? ["pick_id", key.pick_id] : ["sgp_id", key.sgp_id];
  if (fixtureMode()) {
    fixtureWrites.bets = fixtureWrites.bets.filter((b) => (b as Record<string, unknown>)[col as string] !== val);
    return done(path);
  }
  const sb = await supabaseServer();
  const { error } = await sb.from("bets").delete().eq(col as string, val as string);
  return error ? { ok: false, error: friendly(error.message) } : done(path);
}

/** The book's price typed for a slip: how we learn each book's parlay pricing next to fair odds. A DraftKings quote
 *  is saved under the slip's id + "~dk" with book DraftKings (Oct 12), so a slip can hold both books' prices. */
export async function saveQuote(q: { sgp_id: string; price: number; fair_price?: number | null; naive_price?: number | null;
  p_fair?: number | null; legs?: string[]; matchup?: string | null; odds_event_id?: string | null; sport?: string | null;
  book?: string | null },
  path?: string): Promise<Result> {
  if (fixtureMode()) {
    fixtureWrites.quotes = [...fixtureWrites.quotes.filter((x) => x.sgp_id !== q.sgp_id), { sgp_id: q.sgp_id, price: q.price, quoted_at: new Date().toISOString() }];
    return done(path);
  }
  const sb = await supabaseServer();
  const { error } = await sb.from("quotes").upsert({ ...q, book: bookOf(q.book), n_legs: q.legs?.length ?? null, quoted_at: new Date().toISOString() },
                                                  { onConflict: "user_id,sgp_id" });
  return error ? { ok: false, error: friendly(error.message) } : done(path);
}

/** One game's builder pack (its legs and simulated draws), read as the signed-in user. */
export async function loadPack(eventId: string): Promise<Record<string, any>[]> {
  return packParts(eventId);
}

/** Save & track a parlay you built: graded leg by leg with the paper record's slips (never shared). */
export async function saveCustom(row: CustomRow, path?: string): Promise<Result> {
  const r = { ...row, quoted_at: new Date().toISOString() };
  if (fixtureMode()) {
    fixtureWrites.customs = [...fixtureWrites.customs.filter((x) => x.sgp_id !== row.sgp_id), { ...r, status: null, profit_1u: null }];
    return done(path);
  }
  const sb = await supabaseServer();
  const { error } = await sb.from("custom_parlays").upsert(r, { onConflict: "user_id,sgp_id" });
  return error ? { ok: false, error: friendly(error.message) } : done(path);
}


/** Tick or reopen a to-do on the shared list (More > Plan). */
export async function setTodoDone(id: string, isDone: boolean): Promise<Result> {
  const change = { status: isDone ? "done" : "open", done_at: isDone ? new Date().toISOString() : null } as const;
  if (fixtureMode()) {
    const t = (await todosData()).find((x) => x.id === id);
    if (t) fixtureWrites.todos = [...fixtureWrites.todos.filter((x) => x.id !== id), { ...t, ...change }];
    return done("/more/plan");
  }
  const sb = await supabaseServer();
  const { error } = await sb.from("todos").update(change).eq("id", id);
  return error ? { ok: false, error: friendly(error.message) } : done("/more/plan");
}

/** Add an item for you or a request for Claude. Claude reads requests at the start of every session. */
export async function addTodo(input: { owner: "you" | "claude"; title: string; due: string | null }): Promise<Result> {
  const title = input.title.trim();
  if (!title) return { ok: false, error: "Write what needs doing first." };
  if (!["you", "claude"].includes(input.owner)) return { ok: false, error: "Pick who it's for." };
  const row = { owner: input.owner, title: title.slice(0, 300), due: input.due || null, added_by: "app", ord: Date.now() };
  if (fixtureMode()) {
    fixtureWrites.todos.push({ id: crypto.randomUUID(), detail: "", status: "open", done_at: null, created_at: new Date().toISOString(), ...row } as Todo);
    return done("/more/plan");
  }
  const sb = await supabaseServer();
  const { error } = await sb.from("todos").insert(row);
  return error ? { ok: false, error: friendly(error.message) } : done("/more/plan");
}

/** The fun bucket (units a month) and the real-money date (More > Settings). No bankroll or unit size
 *  (Oct 12: the app counts units only); their old columns keep their defaults. */
export async function saveSettings(s: Settings): Promise<Result> {
  if (!(s.fun_bucket_monthly >= 0 && s.fun_bucket_monthly <= 1000)) return { ok: false, error: "Enter parlay units a month, 0 or more." };
  if (s.real_from && Number.isNaN(Date.parse(s.real_from))) return { ok: false, error: "That real-money date isn't a date." };
  const row = { fun_bucket_monthly: s.fun_bucket_monthly, book: s.book || "FanDuel",
                ...(s.real_from !== undefined ? { real_from: s.real_from } : {}), updated_at: new Date().toISOString() };
  if (fixtureMode()) { fixtureWrites.settings = row; return done("/more/settings"); }
  const sb = await supabaseServer();
  const { error } = await sb.from("user_settings").upsert(row, { onConflict: "user_id" });
  return error ? { ok: false, error: friendly(error.message) } : done("/more/settings");
}

/** Save a slip read from a screenshot (My bets > Add, Oct 24) as a real bet, after you confirmed or fixed it. With `promoId`
 *  (Nov 9: the wallet token the draft offered, lib/promos.ts slipTokens) the bet takes that token, as I used it does: it's
 *  claimed first (open, the wager within its dollars, a partial bonus split) and leaves the wallet. */
export async function addSlipBet(d: Draft, unitDollars: number, placedAt: string, promoId?: string | null): Promise<Result> {
  if (!d.legs.length || d.legs.some((l) => !l.label.trim())) return { ok: false, error: "Every leg needs its wording." };
  if (!Number.isFinite(d.price) || Math.abs(d.price) < 100) return { ok: false, error: "Enter the book's odds, like +978 or -110." };
  if (!(d.stake_dollars > 0) || !(unitDollars > 0)) return { ok: false, error: "Enter the wager and your unit size." };
  if (Number.isNaN(Date.parse(placedAt))) return { ok: false, error: "That time isn't a time." };
  const bet_id = crypto.randomUUID();
  let row: Record<string, unknown> = { ...betRow(d, unitDollars, new Date(placedAt).toISOString(), crypto.randomUUID().slice(0, 8)), bet_id };
  if (fixtureMode()) {
    if (promoId) fixtureWrites.promos = fixtureWrites.promos.map((p) => (p.promo_id === promoId ? { ...p, status: "used" } : p));
    fixtureWrites.bets.push({ ...row, promo_id: promoId ?? null } as unknown as Bet);
    return done("/bets");
  }
  if (unitDollars !== (await settingsData()).unit_dollars) await setUnitDollars(unitDollars);   // the unit typed is the account's
  const sb = await supabaseServer();
  const claim = promoId ? await claimToken(sb, promoId, d.stake_dollars) : null;
  if (typeof claim === "string") return { ok: false, error: claim };
  if (claim) {
    if ((claim.p.kind === "bonus") !== d.bonus) { await claim.undo(); return { ok: false, error: `That token is a ${claim.p.kind === "bonus" ? "bonus bet" : "profit boost"}: set the slip to match, or pick none.` }; }
    row = { ...row, ...tokenFields(claim.p, unitDollars), ...(claim.p.kind === "boost" && claim.p.pct == null ? { boost: row.boost } : {}) };
  }
  const { error } = await sb.from("bets").insert(row);
  if (error) { await claim?.undo(); return { ok: false, error: friendly(error.message) }; }
  const fair = fairOf(d);        // apart from the bet: a price that fails to save must not lose the bet (migration 0038)
  if (fair) await sb.from("slip_prices").insert({ bet_id, p: fair.p });
  return done("/bets");
}

/** Dollars per unit on the account (Settings, Oct 30): the slip reader and promo placements turn dollars into units
 *  with it, on every device. */
export async function setUnitDollars(dollars: number): Promise<Result> {
  if (!(dollars > 0) || dollars > 100000) return { ok: false, error: "A unit is a dollar amount above 0." };
  const unit_dollars = Math.round(dollars * 100) / 100;
  if (fixtureMode()) { fixtureWrites.settings = { ...(fixtureWrites.settings ?? await settingsData()), unit_dollars }; return { ok: true }; }
  const sb = await supabaseServer();
  const { error } = await sb.from("user_settings").upsert({ unit_dollars, updated_at: new Date().toISOString() }, { onConflict: "user_id" });
  return error ? { ok: false, error: friendly(error.message) } : { ok: true };
}

/** The first-run welcome's last step (Nov 5): the account's unit, and that it's seen the welcome. */
export async function finishWelcome(dollars: number): Promise<Result> {
  if (!(dollars > 0)) return { ok: false, error: "A unit needs to be above $0." };
  const unit_dollars = Math.round(dollars * 100) / 100;
  if (fixtureMode()) { fixtureWrites.settings = { ...(fixtureWrites.settings ?? await settingsData()), unit_dollars }; return { ok: true }; }
  const sb = await supabaseServer();
  const now = new Date().toISOString();
  const { error } = await sb.from("user_settings").upsert({ unit_dollars, onboarded_at: now, updated_at: now }, { onConflict: "user_id" });
  return error ? { ok: false, error: error.message } : { ok: true };
}

/** Leg push alerts on or off for this account (user_settings.notify.legs; the worker's leg_alerts.py skips an
 *  account set to false). Other notify keys are kept. */
export async function setLegAlerts(on: boolean): Promise<Result> {
  const notify = { ...((await settingsData()).notify ?? {}), legs: on };
  const row = { notify, updated_at: new Date().toISOString() };
  if (fixtureMode()) { fixtureWrites.settings = { ...(fixtureWrites.settings ?? await settingsData()), notify }; return done("/more/settings"); }
  const sb = await supabaseServer();
  const { error } = await sb.from("user_settings").upsert(row, { onConflict: "user_id" });
  return error ? { ok: false, error: friendly(error.message) } : done("/more/settings");
}

/** Alert settings (Settings, Nov 2): any notify keys, the rest kept; the worker's alert_prefs.py reads them. */
export async function setNotify(patch: Record<string, unknown>): Promise<Result> {
  const notify = { ...((await settingsData()).notify ?? {}), ...patch };
  const row = { notify, updated_at: new Date().toISOString() };
  if (fixtureMode()) { fixtureWrites.settings = { ...(fixtureWrites.settings ?? await settingsData()), notify }; return done("/more/settings"); }
  const sb = await supabaseServer();
  const { error } = await sb.from("user_settings").upsert(row, { onConflict: "user_id" });
  return error ? { ok: false, error: friendly(error.message) } : done("/more/settings");
}

/** The ban list (Settings, Oct 25): players and teams BetLab gives no bets on, here, on the phone and in the worker's
 *  tickets and alerts (lib/bans.ts). The whole list is saved each time; at most 200 entries. */
export async function setBans(list: Ban[]): Promise<Result> {
  const bans = cleanBans(list).slice(0, 200);
  const row = { bans, updated_at: new Date().toISOString() };
  if (fixtureMode()) { fixtureWrites.settings = { ...(fixtureWrites.settings ?? await settingsData()), bans }; return done("/more/settings"); }
  const sb = await supabaseServer();
  const { error } = await sb.from("user_settings").upsert(row, { onConflict: "user_id" });
  return error ? { ok: false, error: friendly(error.message) } : done("/more/settings");
}

/** The wall's tile order after a drag (lib/order.ts): the tiles as shown, put in place in the saved list. */
export async function setWallOrder(shown: string[]): Promise<Result> {
  const keys = shown.map(String).filter(Boolean).slice(0, 200);
  const wall_order = placed((await settingsData()).wall_order ?? [], keys);
  const row = { wall_order, updated_at: new Date().toISOString() };
  if (fixtureMode()) { fixtureWrites.settings = { ...(fixtureWrites.settings ?? await settingsData()), wall_order }; return { ok: true }; }
  const sb = await supabaseServer();
  const { error } = await sb.from("user_settings").upsert(row, { onConflict: "user_id" });
  return error ? { ok: false, error: friendly(error.message) } : { ok: true };   // the page already shows the new order
}

/** Back to the wall's own order, biggest tile first (Mike, Oct 25): forget the tiles you dragged. */
export async function resetWallOrder(): Promise<Result> {
  const row = { wall_order: [], updated_at: new Date().toISOString() };
  if (fixtureMode()) { fixtureWrites.settings = { ...(fixtureWrites.settings ?? await settingsData()), wall_order: [] }; return { ok: true }; }
  const sb = await supabaseServer();
  const { error } = await sb.from("user_settings").upsert(row, { onConflict: "user_id" });
  return error ? { ok: false, error: friendly(error.message) } : { ok: true };
}

/** A theme (lib/looks.ts) or the device's light/dark; a cookie so the first paint is already right. Also on the
 *  account (user_settings.theme, Oct 25): the worker's leg alerts speak "diva" to an account on Pink. */
export async function setTheme(theme: ThemeId): Promise<void> {
  const jar = await cookies();
  if (!themeOf(theme)) jar.delete("theme");
  else jar.set("theme", theme, { path: "/", maxAge: 60 * 60 * 24 * 400, sameSite: "lax" });
  if (!fixtureMode()) {
    const sb = await supabaseServer();
    await sb.from("user_settings").upsert({ theme: themeOf(theme) ? theme : "system", updated_at: new Date().toISOString() },
                                          { onConflict: "user_id" });   // best effort: the alerts' voice only
  }
  revalidatePath("/", "layout");
}

/** The body font (lib/looks.ts); Classic is the default. */
export async function setFont(font: FontId): Promise<void> {
  const jar = await cookies();
  if (!fontOf(font)) jar.delete("font");
  else jar.set("font", font, { path: "/", maxAge: 60 * 60 * 24 * 400, sameSite: "lax" });
  revalidatePath("/", "layout");
}

export async function signOut(): Promise<void> {
  if (!fixtureMode()) await (await supabaseServer()).auth.signOut();
  redirect("/login");
}


/** Change a placed bet's stake (units), the price you actually got, the book you placed it at, whether it was a
 *  bonus bet (the book's credit: a win pays the profit only, a loss costs nothing; Oct 19), or what a cash-out paid
 *  back in units (Oct 22; blank: not cashed out), or its profit boost in percent (Oct 22; the price stays the book's). */
export async function updateBet(betId: string, change: { stake: number; price: string; book?: string; bonus?: boolean; cashout?: string; boost?: string;
                                                        protect?: boolean; reset?: boolean },
                                path?: string): Promise<Result> {
  const price = change.price.trim() ? parseOdds(change.price) : null;
  // the stake is written only when it changed (Nov 9): slips and promos save 3 decimals ($/unit), so rounding an
  // untouched 0.382u to 0.38 on every edit moved the bankroll; and a ladder step's stake is the whole stack (up to
  // 100,000u), so the 100u cap applies only to a raised stake on a bet outside a ladder
  const now = await betNow(betId);
  const stake = Math.round(change.stake * 1000) / 1000;
  const same = now?.stake != null && Math.abs(Number(now.stake) - stake) < 0.0005;
  const cap = now?.ladder_id ? 100_000 : 100;
  if (!same && !(stake > 0 && stake <= cap)) return { ok: false, error: `Enter a stake in units, above 0 and at most ${cap.toLocaleString("en-US")}.` };
  if (change.price.trim() && price == null) return { ok: false, error: "Enter a price like -110 or +150." };
  const cash = change.cashout === undefined ? undefined : change.cashout.trim() ? Number(change.cashout) : null;
  if (cash !== undefined && cash !== null && !(Number.isFinite(cash) && cash >= 0 && cash <= 1000))
    return { ok: false, error: "Enter what the cash-out paid back in units, like 1.06." };
  const boost = change.boost === undefined ? undefined : change.boost.trim() ? Number(change.boost.replace("%", "")) : null;
  if (boost !== undefined && boost !== null && !(Number.isFinite(boost) && boost > 0 && boost <= 500))
    return { ok: false, error: "Enter the profit boost in percent, like 50." };
  const row = { ...(same ? {} : { stake }), price, ...(change.book ? { book: bookOf(change.book) } : {}),
                ...(change.bonus !== undefined ? { bonus: change.bonus } : {}),
                ...(change.protect !== undefined ? { protect: change.protect } : {}),   // Bet Protect+ (0023, Oct 26)
                ...(change.reset !== undefined ? { reset: change.reset } : {}),         // a bet reset (0031, Nov 1)
                ...(cash !== undefined ? { cashout: cash === null ? null : Math.round(cash * 1000) / 1000 } : {}),
                ...(boost !== undefined ? { boost } : {}) };
  if (fixtureMode()) {
    fixtureWrites.bets = fixtureWrites.bets.map((b) => (b.bet_id === betId ? { ...b, ...row } : b));
    return done(path);
  }
  const sb = await supabaseServer();
  const { error } = await sb.from("bets").update(row).eq("bet_id", betId);
  return error ? { ok: false, error: friendly(error.message) } : done(path);
}

/** A bet's stake and ladder as saved now (Edit compares against them); null when it can't be read. */
async function betNow(betId: string): Promise<{ stake: number | null; ladder_id: string | null } | null> {
  if (fixtureMode()) {
    const b = fixtureWrites.bets.find((x) => x.bet_id === betId) as { stake?: number | null; ladder_id?: string | null } | undefined;
    return b ? { stake: b.stake ?? null, ladder_id: b.ladder_id ?? null } : null;
  }
  const { data } = await (await supabaseServer()).from("bets").select("stake,ladder_id").eq("bet_id", betId).maybeSingle();
  return data ? { stake: data.stake as number | null, ladder_id: (data.ladder_id as string | null) ?? null } : null;
}

// ---------------------------------------------------------------------------- ladders (Oct 26, lib/ladder.ts)

/** Start a ladder challenge: from `start` units to `target` (Mike's first: 1u -> 100u), every step at one `book`
 *  (Oct 26: "ladder needs to be at one book whole time"). One active ladder at a time. */
export async function startLadder(start: number, target: number, path?: string, book = "FanDuel"): Promise<Result> {
  if (!(start > 0 && start <= 100)) return { ok: false, error: "Start with some units, like 1." };
  if (!(target > start && target <= 100_000)) return { ok: false, error: "The target has to be above the start." };
  if (fixtureMode()) {
    if (fixtureWrites.ladders.some((l) => l.status === "active")) return { ok: false, error: "Finish or stop the ladder you're on first." };
    fixtureWrites.ladders.push({ ladder_id: crypto.randomUUID(), start_units: start, target_units: target, status: "active",
                                 created_at: new Date().toISOString(), book: bookOf(book) });
    return done(path);
  }
  const sb = await supabaseServer();
  const { data: active } = await sb.from("ladders").select("*").eq("status", "active");
  // a ladder its steps already ended (busted or climbed) is closed here rather than blocking a new one (Nov 6: Mike's
  // busted ladder stayed "active" and the page invited him to start another, then refused); it still reads as busted
  const ids = (active ?? []).map((l) => l.ladder_id as string);
  const { data: steps } = ids.length ? await sb.from("my_bets").select("*").in("ladder_id", ids) : { data: [] };
  const over = (active ?? []).filter((l) => ["busted", "climbed"].includes(ladderState(l as Ladder, (steps ?? []) as MyBet[]).phase));
  if (over.length) await sb.from("ladders").update({ status: "stopped", ended_at: new Date().toISOString(), locked: null, locked_at: null })
    .in("ladder_id", over.map((l) => l.ladder_id));
  if ((active?.length ?? 0) > over.length) return { ok: false, error: "Finish or stop the ladder you're on first." };
  const { error } = await sb.from("ladders").insert({ start_units: start, target_units: target, book: bookOf(book) });
  return error ? { ok: false, error: friendly(error.message) } : done(path);
}

/** Stop a ladder (walk away with the stack, or give up on it). Its bets stay, still graded as normal. A ladder that
 *  never had a step is deleted instead, so a tryout leaves nothing under Past ladders (Mike, Oct 26). */
export async function stopLadder(ladderId: string, path?: string): Promise<Result> {
  if (fixtureMode()) {
    const used = fixtureWrites.bets.some((b) => b.ladder_id === ladderId);
    fixtureWrites.ladders = used
      ? fixtureWrites.ladders.map((l) => (l.ladder_id === ladderId ? { ...l, status: "stopped", ended_at: new Date().toISOString() } : l))
      : fixtureWrites.ladders.filter((l) => l.ladder_id !== ladderId);
    return done(path);
  }
  const sb = await supabaseServer();
  const { data: steps } = await sb.from("bets").select("bet_id").eq("ladder_id", ladderId).limit(1);
  const { error } = steps?.length
    ? await sb.from("ladders").update({ status: "stopped", ended_at: new Date().toISOString() }).eq("ladder_id", ladderId)
    : await sb.from("ladders").delete().eq("ladder_id", ladderId);
  return error ? { ok: false, error: friendly(error.message) } : done(path);
}

/** Make a bet the ladder's next step, staked at `stake` units (the whole stack): BetLab's suggestion (a pick or
 *  lean, saved like Place; a pick already marked is the same bet), or one of the user's own open bets by id. A real
 *  bet, outside the 5u-a-day rule (Mike, Oct 26). */
export async function ladderStep(ladderId: string, stake: number, step: { betId?: string; offer?: MarkInput }, path?: string): Promise<Result> {
  if (!(stake > 0 && stake <= 100_000)) return { ok: false, error: "That stake isn't a number of units." };
  const units = Math.round(stake * 100) / 100;
  if (fixtureMode()) {
    const id = step.betId ?? fixtureWrites.bets.find((b) => step.offer?.pick_id && b.pick_id === step.offer.pick_id)?.bet_id;
    if (id) fixtureWrites.bets = fixtureWrites.bets.map((b) => (b.bet_id === id ? { ...b, ladder_id: ladderId, stake: units, mode: "real" } : b));
    else if (step.offer) fixtureWrites.bets.push({ bet_id: crypto.randomUUID(), placed_at: new Date().toISOString(), ...step.offer,
      book: bookOf(step.offer.book), mode: "real", stake: units, ladder_id: ladderId } as Bet);
    fixtureWrites.ladders = fixtureWrites.ladders.map((l) => (l.ladder_id === ladderId ? { ...l, locked: null, locked_at: null, notice: null } : l));
    return done(path);
  }
  const sb = await supabaseServer();
  let betId = step.betId ?? null;
  if (!betId && step.offer?.pick_id) {
    const { data: had } = await sb.from("bets").select("bet_id").eq("pick_id", step.offer.pick_id);
    betId = had?.[0]?.bet_id ?? null;
    if (!betId) {
      const row = { ...step.offer, book: bookOf(step.offer.book), mode: "real" as const, stake: units, ladder_id: ladderId };
      const { error } = await sb.from("bets").insert(row);
      if (!error) await sb.from("ladders").update({ locked: null, locked_at: null, notice: null }).eq("ladder_id", ladderId);
      return error ? { ok: false, error: friendly(error.message) } : done(path);
    }
  }
  if (!betId) return { ok: false, error: "Pick a bet for this step." };
  const { error } = await sb.from("bets").update({ ladder_id: ladderId, stake: units, mode: "real" }).eq("bet_id", betId);
  if (!error) await sb.from("ladders").update({ locked: null, locked_at: null, notice: null }).eq("ladder_id", ladderId);
  return error ? { ok: false, error: friendly(error.message) } : done(path);
}

/** Change a ladder (migration 0021): `skip` turns an offer down ("Not this one"; a locked step is unlocked so the worker
 *  picks the next), `unskip` brings every turned-down one back, `game` keeps the next step to one game (null: any game
 *  today; a new choice unlocks a locked step and clears a notice). Saved on the ladder, so both apps and the worker see it. */
export async function changeLadder(ladderId: string, change: { skip?: string; unskip?: boolean; game?: string | null }, path?: string): Promise<Result> {
  const apply = (l: Ladder): Partial<Ladder> => {
    const out: Partial<Ladder> = {};
    if (change.skip) {
      out.skipped = [...new Set([...(l.skipped ?? []), change.skip])];
      if (l.locked?.offer_id === change.skip) Object.assign(out, { locked: null, locked_at: null });
    }
    if (change.unskip) out.skipped = [];
    if (change.game !== undefined) Object.assign(out, { game_id: change.game, notice: null, locked: null, locked_at: null });
    return out;
  };
  if (fixtureMode()) {
    fixtureWrites.ladders = fixtureWrites.ladders.map((l) => (l.ladder_id === ladderId ? { ...l, ...apply(l) } : l));
    return done(path);
  }
  const sb = await supabaseServer();
  const { data } = await sb.from("ladders").select("*").eq("ladder_id", ladderId);
  if (!data?.length) return { ok: false, error: "That ladder isn't there any more." };
  const { error } = await sb.from("ladders").update(apply(data[0] as Ladder)).eq("ladder_id", ladderId);
  return error ? { ok: false, error: friendly(error.message) } : done(path);
}

// ------------------------------------------------------------------------------------- Friends (Oct 27, 0024)

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Your name and @handle (Friends): what friends see, and how they find you. */
export async function saveProfile(name: string, handleText: string): Promise<Result> {
  const n = name.trim(), handle = cleanHandle(handleText);
  if (!n || n.length > 40) return { ok: false, error: "Your name: 1 to 40 characters." };
  if (!handle) return { ok: false, error: "Your @handle: 3 to 20 letters, digits or _." };
  if (fixtureMode()) {
    const me = await myId();
    fixtureWrites.profiles = [...fixtureWrites.profiles.filter((p) => p.user_id !== me), { user_id: me, name: n, handle }];
    return done("/friends");
  }
  const sb = await supabaseServer();
  const { error } = await sb.from("profiles").upsert({ user_id: await myId(), name: n, handle }, { onConflict: "user_id" });
  if (error && /duplicate key|unique/i.test(error.message)) return { ok: false, error: `@${handle} is taken: try another.` };
  return error ? { ok: false, error: friendly(error.message) } : done("/friends");
}

/** Ask someone to be friends, found by their exact @handle or email (find_person: no browsing). */
export async function requestFriend(q: string): Promise<Result> {
  const s = await socialData();
  if (!s.profile) return { ok: false, error: "Set your name and @handle first." };
  let found: Profile | null;
  if (fixtureMode()) {
    found = s.profiles.find((p) => p.user_id !== s.me && p.handle === cleanHandle(q)) ?? null;   // the preview: by handle
  } else {
    const { data } = await (await supabaseServer()).rpc("find_person", { q });
    found = ((data ?? []) as Profile[])[0] ?? null;
  }
  if (!found) return { ok: false, error: "No one with that @handle or email. Check the spelling, or ask them for their @handle." };
  if (s.friendships.some((f) => (f.requester === found!.user_id && f.addressee === s.me) || (f.addressee === found!.user_id && f.requester === s.me)))
    return { ok: false, error: `You and ${found.name} are already friends, or a request is waiting.` };
  if (fixtureMode()) {
    fixtureWrites.profiles.some((p) => p.user_id === found!.user_id) || fixtureWrites.profiles.push(found);
    fixtureWrites.friendships.push({ requester: s.me, addressee: found.user_id, status: "pending", created_at: new Date().toISOString(), accepted_at: null });
    return done("/friends");
  }
  const { error } = await (await supabaseServer()).from("friendships").insert({ addressee: found.user_id });
  return error ? { ok: false, error: friendly(error.message) } : done("/friends");
}

/** Accept or decline a request someone sent you. */
export async function answerFriend(from: string, accept: boolean): Promise<Result> {
  if (!UUID.test(from)) return { ok: false, error: "That isn't a person." };
  if (fixtureMode()) {
    const me = await myId();
    fixtureWrites.friendships = fixtureWrites.friendships.flatMap((f) => f.requester === from && f.addressee === me && f.status === "pending"
      ? (accept ? [{ ...f, status: "accepted" as const, accepted_at: new Date().toISOString() }] : []) : [f]);
    return done("/friends");
  }
  const sb = await supabaseServer();
  const { error } = accept ? await sb.rpc("accept_friend", { from_user: from })
    : await sb.from("friendships").delete().eq("requester", from).eq("addressee", await myId());
  return error ? { ok: false, error: friendly(error.message) } : done("/friends");
}

/** End a friendship, or take back a request you sent. */
export async function endFriend(other: string): Promise<Result> {
  if (!UUID.test(other)) return { ok: false, error: "That isn't a person." };     // it goes into a filter below
  const me = await myId();
  const pair = (f: { requester: string; addressee: string }) => (f.requester === me && f.addressee === other) || (f.requester === other && f.addressee === me);
  if (fixtureMode()) { fixtureWrites.friendships = fixtureWrites.friendships.filter((f) => !pair(f)); return done("/friends"); }
  const sb = await supabaseServer();
  const { error } = await sb.from("friendships").delete().or(`and(requester.eq.${me},addressee.eq.${other}),and(requester.eq.${other},addressee.eq.${me})`);
  return error ? { ok: false, error: friendly(error.message) } : done("/friends");
}

/** The books turned off on the account (Settings > Your books, 0043): never all three. */
export async function setBooksOff(off: string[]): Promise<Result> {
  const books_off = BOOKS.filter((b) => off.includes(b));
  if (books_off.length >= BOOKS.length) return { ok: false, error: "Keep at least one book on." };
  if (fixtureMode()) { fixtureWrites.settings = { ...(fixtureWrites.settings ?? await settingsData()), books_off }; return done("/"); }
  const sb = await supabaseServer();
  const { error } = await sb.from("user_settings").upsert({ books_off, updated_at: new Date().toISOString() }, { onConflict: "user_id" });
  return error ? { ok: false, error: friendly(error.message) } : done("/");
}

/** Watch a game or stop (Nov 7, 0045): a watched game's own same-game slips join Today's Parlays when its slice locks,
 *  and the lock alert names them (lib/watch.ts, worker alerts.watched_slips). */
export async function setWatching(gameId: string, on: boolean): Promise<Result> {
  const cur = fixtureMode() ? (fixtureWrites.settings ?? await settingsData()) : await settingsData();
  const watching = toggled(cur.watching ?? [], gameId, on);
  if (fixtureMode()) { fixtureWrites.settings = { ...cur, watching }; return done("/"); }
  const sb = await supabaseServer();
  const { error } = await sb.from("user_settings").upsert({ watching, updated_at: new Date().toISOString() }, { onConflict: "user_id" });
  return error ? { ok: false, error: friendly(error.message) } : done("/");
}

/** Whether friends see your bets (Settings; on by default). */
export async function setShareBets(on: boolean): Promise<Result> {
  if (fixtureMode()) { fixtureWrites.settings = { ...(fixtureWrites.settings ?? await settingsData()), share_bets: on }; return done("/more/settings"); }
  const sb = await supabaseServer();
  const { error } = await sb.from("user_settings").upsert({ share_bets: on, updated_at: new Date().toISOString() }, { onConflict: "user_id" });
  return error ? { ok: false, error: friendly(error.message) } : done("/more/settings");
}

/** Tail (W16): copy a friend's open bet into your own bets, at the price you got and your book (1u once real money
 *  has started). Only bets friend_bets shows you, and only before the game starts. */
export async function tailBet(betId: string, priceText: string, book: string): Promise<Result> {
  const b = (await friendBets()).find((x) => x.bet_id === betId);
  if (!b) return { ok: false, error: "That bet isn't shared with you any more." };
  if (!canTail(b)) return { ok: false, error: "Too late: its game has started or it's settled." };
  const price = parseOdds(priceText);
  if (price == null) return { ok: false, error: "Enter the odds you got, like +450 or -110." };
  const row = tailRow(b, { price, book, real: isReal(new Date(), (await settingsData()).real_from) });
  if (fixtureMode()) {
    if (fixtureWrites.bets.some((x) => betKey(x) === betKey(row))) return { ok: false, error: "Already in your bets." };
    fixtureWrites.bets.push({ bet_id: crypto.randomUUID(), placed_at: new Date().toISOString(), ...row } as unknown as Bet);
    return done("/bets");
  }
  const { error } = await (await supabaseServer()).from("bets").insert(row);
  if (error && /duplicate key/i.test(error.message)) return { ok: false, error: "Already in your bets." };
  return error ? { ok: false, error: friendly(error.message) } : done("/bets");
}

/** React to a friend's bet (0042): one per bet, `null` takes yours back. The database lets only a friend's shared bet
 *  take one (can_react), never your own. */
export async function reactToBet(betId: string, reaction: string | null): Promise<Result> {
  if (!UUID.test(betId)) return { ok: false, error: "That isn't a bet." };
  if (reaction !== null && !REACTIONS.some((r) => r.key === reaction)) return { ok: false, error: "That isn't a reaction." };
  const me = await myId();
  if (fixtureMode()) {
    fixtureWrites.reactions = [...fixtureWrites.reactions.filter((r) => r.bet_id !== betId),
      { bet_id: betId, user_id: me, name: "You", reaction: reaction ?? "", created_at: new Date().toISOString() }];
    return done("/friends");
  }
  const sb = await supabaseServer();
  const { error } = reaction
    ? await sb.from("bet_reactions").upsert({ bet_id: betId, user_id: me, reaction, created_at: new Date().toISOString() }, { onConflict: "bet_id,user_id" })
    : await sb.from("bet_reactions").delete().eq("bet_id", betId).eq("user_id", me);
  if (error && /row-level security/i.test(error.message)) return { ok: false, error: "That bet isn't shared with you any more." };
  return error ? { ok: false, error: friendly(error.message) } : done("/friends");
}

// ------------------------------------------------------------------------------------- promos (Oct 30, 0029)

/** Add a token to the wallet (typed, or read from a screenshot and checked on screen). */
export async function addPromo(d: Partial<PromoRow>): Promise<Result & { id?: string }> {
  const { row, error } = cleanPromo(d);
  if (!row) return { ok: false, error: error ?? "That isn't a promo." };
  if (fixtureMode()) {
    const id = crypto.randomUUID();
    fixtureWrites.promos.push({ promo_id: id, status: "open", created_at: new Date().toISOString(), ...row });
    return { ...done("/more/promos"), id };
  }
  const sb = await supabaseServer();
  const { data, error: e } = await sb.from("promos").insert(row).select("promo_id").single();
  return e ? { ok: false, error: friendly(e.message) } : { ...done("/more/promos"), id: data?.promo_id };
}

/** Change a token's terms or expiry. */
export async function updatePromo(id: string, d: Partial<PromoRow>): Promise<Result> {
  const { row, error } = cleanPromo(d);
  if (!row) return { ok: false, error: error ?? "That isn't a promo." };
  if (fixtureMode()) {
    const i = fixtureWrites.promos.findIndex((p) => p.promo_id === id);
    if (i >= 0) fixtureWrites.promos[i] = { ...fixtureWrites.promos[i], ...row };
    return done("/more/promos");
  }
  const sb = await supabaseServer();
  const { source: _source, ...edit } = row;
  const { error: e } = await sb.from("promos").update(edit).eq("promo_id", id);
  return e ? { ok: false, error: friendly(e.message) } : done("/more/promos");
}

/** Void a token you won't use (or bring a voided one back), or delete it outright. */
export async function setPromoStatus(id: string, status: "void" | "open" | "delete"): Promise<Result> {
  if (fixtureMode()) {
    fixtureWrites.promos = status === "delete" ? fixtureWrites.promos.filter((p) => p.promo_id !== id)
      : fixtureWrites.promos.map((p) => (p.promo_id === id ? { ...p, status } : p));
    return done("/more/promos");
  }
  const sb = await supabaseServer();
  const q = status === "delete" ? sb.from("promos").delete().eq("promo_id", id)
    : sb.from("promos").update({ status }).eq("promo_id", id).neq("status", "used");
  const { error } = await q;
  return error ? { ok: false, error: friendly(error.message) } : done("/more/promos");
}

/** I used it (Oct 31): the token went on `betId` (a bet saved without it: the bet takes the token, its bonus or boost,
 *  and the database marks it used), or on a bet not in BetLab (null: just marked used). */
export async function usedPromo(id: string, betId: string | null): Promise<Result> {
  if (fixtureMode()) {
    fixtureWrites.promos = fixtureWrites.promos.map((p) => (p.promo_id === id ? { ...p, status: "used" } : p));
    return done("/more/promos");
  }
  const sb = await supabaseServer();
  if (!betId) {
    const { error } = await sb.from("promos").update({ status: "used" }).eq("promo_id", id).eq("status", "open");
    return error ? { ok: false, error: friendly(error.message) } : done("/more/promos");
  }
  const unit = unitOf(await settingsData());
  const { data: b } = await sb.from("bets").select("stake").eq("bet_id", betId).maybeSingle();
  const stake = num(b?.stake);
  const claim = await claimToken(sb, id, stake !== null ? Math.round(stake * unit * 100) / 100 : null, { overMax: true });
  if (typeof claim === "string") return { ok: false, error: claim };
  const { error } = await sb.from("bets").update(tokenFields(claim.p, unit)).eq("bet_id", betId);
  if (error) { await claim.undo(); return { ok: false, error: friendly(error.message) }; }
  return done("/more/promos");
}

/** What a bet takes from the token it used: its id, and the bonus flag or the boost with its cap in units. */
function tokenFields(p: PromoRow, unit: number) {
  const cap = Number(p.max_extra_dollars) || 0;
  return p.kind === "bonus" ? { promo_id: p.promo_id, bonus: true }
    : { promo_id: p.promo_id, boost: p.pct == null ? null : Number(p.pct), boost_cap: cap > 0 ? Math.round((cap / unit) * 1000) / 1000 : null };
}

type Sb = Awaited<ReturnType<typeof supabaseServer>>;
/** Take a wallet token for a bet of `wager` dollars (Nov 9), before the bet is written: it must still be open (promoUsable: a
 *  used one could go on a second bet), the wager at most its dollars (unless `overMax`: I used it ties a bet already placed), and a
 *  bonus bet used for less than its face (Nov 3) is split, the rest becoming its own open token on the same terms. The split is one
 *  conditional update, made only while the token is open at the face just read, so two placements can't both split it (the iPhone's
 *  BetStore.claimToken is the same). Returns the token and an undo for when the bet then fails to save, or the reason it can't. */
async function claimToken(sb: Sb, id: string, wager: number | null, opt: { overMax?: boolean } = {}): Promise<{ p: PromoRow; undo: () => Promise<void> } | string> {
  const { data: p } = await sb.from("promos").select("*").eq("promo_id", id).maybeSingle();
  const bad = promoUsable(p);
  if (bad || !p) return bad ?? "That promo is gone.";
  const face = num(p.amount_dollars);
  if (!opt.overMax && wager !== null && face !== null && wager > face + 0.004) return `This ${p.kind === "bonus" ? "bonus bet" : "boost's max wager"} is $${face}.`;
  const left = p.kind === "bonus" && wager !== null ? bonusLeft(face, wager) : 0;
  if (!(left > 0)) return { p, undo: async () => {} };
  const cut = await sb.from("promos").update({ amount_dollars: wager }).eq("promo_id", id).eq("status", "open").eq("amount_dollars", face!).select("promo_id");
  if (cut.error) return friendly(cut.error.message);
  if (!cut.data?.length) return "That promo just changed: reload and try again.";
  const { promo_id: _id, created_at: _at, from_bet: _from, status: _s, ...terms } = p as PromoRow & { created_at?: string; from_bet?: string | null };
  const made = await sb.from("promos").insert({ ...terms, amount_dollars: left, status: "open" }).select("promo_id").single();
  const back = async () => { await sb.from("promos").update({ amount_dollars: face }).eq("promo_id", id); };
  if (made.error) { await back(); return friendly(made.error.message); }
  return { p: { ...p, amount_dollars: wager }, undo: async () => { await sb.from("promos").delete().eq("promo_id", made.data.promo_id); await back(); } };
}

/** Bring back a token marked used by hand (no bet holds it); one a bet holds comes back when that bet is undone. */
export async function unusePromo(id: string): Promise<Result> {
  if (fixtureMode()) {
    fixtureWrites.promos = fixtureWrites.promos.map((p) => (p.promo_id === id ? { ...p, status: "open" } : p));
    return done("/more/promos");
  }
  const sb = await supabaseServer();
  const { data: held } = await sb.from("bets").select("bet_id").eq("promo_id", id).limit(1);
  if (held?.length) return { ok: false, error: "A bet holds this promo: undo that bet to get it back." };
  const { error } = await sb.from("promos").update({ status: "open" }).eq("promo_id", id).eq("status", "used");
  return error ? { ok: false, error: friendly(error.message) } : done("/more/promos");
}

/** One side of a promo placement: the slip (customRow) at the price taken, at its book, for these dollars. */
export type PlaceSide = { row: CustomRow; price: number; book: string; dollars: number };
export type PromoPlacement = Omit<PlaceSide, "dollars"> & {
  dollars: number | null;           // null: one unit (Build's I placed this with a token that names no dollars, Nov 9)
  promo: { kind: "bonus" | "boost"; pct?: number; maxExtra?: number };
  promo_id?: string | null;         // the wallet token it used: the database marks it used (0029's trigger)
  promo_ev?: number | null;         // the finder's expected dollars for it
  hedge?: PlaceSide | null;         // a two-book lock's cash side, saved with the same lock_id
};

/** Place a bet with a promo (the finder, Oct 30): the stake is the token's dollars over the account's unit (not 1u,
 *  as Build's Place saved before), with the bonus or boost flags, the boost's cap in units and the token's id; a lock
 *  saves its hedge too, both under one lock_id. Real from the account's real-money date, paper before. */
export async function placePromo(x: PromoPlacement): Promise<Result & { lock_id?: string | null }> {
  if (!Number.isFinite(x.price) || Math.abs(x.price) < 100) return { ok: false, error: "Enter the book's odds, like +150 or -110." };
  if (x.dollars !== null && !(x.dollars > 0)) return { ok: false, error: "Enter the dollars on it." };
  if (x.hedge && !(x.hedge.dollars > 0 && Math.abs(x.hedge.price) >= 100)) return { ok: false, error: "The hedge needs its price and dollars." };
  const settings = await settingsData();
  const unit = unitOf(settings), real = isReal(new Date(), settings.real_from);
  const lock_id = x.hedge ? crypto.randomUUID() : null;
  const units = (d: number) => Math.round((d / unit) * 1000) / 1000;
  const bet = (side: PlaceSide, extra: Record<string, unknown>) => ({
    kind: "custom" as const, sgp_id: side.row.sgp_id, price: side.price, book: bookOf(side.book), matchup: side.row.matchup,
    fair_price: side.row.fair_price, p_fair: side.row.p_fair, legs: side.row.legs, odds_event_id: side.row.odds_event_id,
    games: side.row.games.map((g) => ({ matchup: g.matchup, game_ref: g.game_ref, legs: g.legs })),
    mode: real ? ("real" as const) : ("paper" as const), stake: real ? units(side.dollars) : null, lock_id, ...extra,
  });
  const dollars = x.dollars ?? unit;
  const main = bet({ ...x, dollars }, {
    bonus: x.promo.kind === "bonus", boost: x.promo.kind === "boost" ? x.promo.pct ?? null : null,
    boost_cap: x.promo.kind === "boost" && x.promo.maxExtra ? units(x.promo.maxExtra) : null,
    promo_id: x.promo_id ?? null, promo_ev: x.promo_ev != null && Number.isFinite(x.promo_ev) ? Math.round(x.promo_ev * 100) / 100 : null,
  });
  const rows = [main, ...(x.hedge ? [bet(x.hedge, {})] : [])];
  const customs = [x, ...(x.hedge ? [x.hedge] : [])].map((side) => ({ ...side.row, price: side.price, quoted_at: new Date().toISOString() }));
  const ids = rows.map((r) => r.sgp_id);
  if (fixtureMode()) {
    if (x.promo_id) { const bad = promoUsable(fixtureWrites.promos.find((p) => p.promo_id === x.promo_id)); if (bad) return { ok: false, error: bad }; }
    if (fixtureWrites.bets.some((b) => ids.includes(b.sgp_id ?? ""))) return { ok: false, error: ALREADY_BET };
    for (const c of customs) fixtureWrites.customs = [...fixtureWrites.customs.filter((y) => y.sgp_id !== c.sgp_id), { ...c, status: null, profit_1u: null }];
    for (const r of rows) fixtureWrites.bets.push({ bet_id: crypto.randomUUID(), placed_at: new Date().toISOString(), ...r } as unknown as Bet);
    if (x.promo_id) fixtureWrites.promos = fixtureWrites.promos.map((p) => (p.promo_id === x.promo_id ? { ...p, status: "used" } : p));
    return { ...done("/bets"), lock_id };
  }
  const sb = await supabaseServer();
  // Nov 9: a bet on this slip at this book already holds its id (bets' unique user_id, sgp_id), so the insert would fail, but only
  // after the earlier bet's saved slip was overwritten and a bonus split; refuse before anything is written
  const { data: had } = await sb.from("bets").select("sgp_id").in("sgp_id", ids).limit(1);
  if (had?.length) return { ok: false, error: ALREADY_BET };
  const claim = x.promo_id ? await claimToken(sb, x.promo_id, dollars) : null;
  if (typeof claim === "string") return { ok: false, error: claim };
  const c = await sb.from("custom_parlays").upsert(customs, { onConflict: "user_id,sgp_id" });
  if (c.error) { await claim?.undo(); return { ok: false, error: friendly(c.error.message) }; }
  const { error } = await sb.from("bets").insert(rows);
  if (error) { await claim?.undo(); return { ok: false, error: friendly(error.message) }; }
  return { ...done("/bets"), lock_id };
}
const ALREADY_BET = "You already have a bet on this slip at this book: pick another, or undo that bet first.";

/** Undo a promo placement: the bet, and its lock's hedge with it (the token goes back to the wallet). */
export async function undoPromo(key: { sgp_id: string; lock_id?: string | null }): Promise<Result> {
  if (fixtureMode()) {
    fixtureWrites.bets = fixtureWrites.bets.filter((b) => !(key.lock_id ? b.lock_id === key.lock_id : b.sgp_id === key.sgp_id));
    return done("/bets");
  }
  const sb = await supabaseServer();
  const { error } = key.lock_id ? await sb.from("bets").delete().eq("lock_id", key.lock_id)
    : await sb.from("bets").delete().eq("sgp_id", key.sgp_id);
  return error ? { ok: false, error: friendly(error.message) } : done("/bets");
}

/** Signed-in devices (migration 0037): one session, or every other one with null. */
export async function endSessions(session: string | null): Promise<{ ended?: number; error?: string }> {
  const { data, error } = await (await supabaseServer()).rpc("end_sessions", session ? { session } : {});
  if (error) return { error: error.message };
  revalidatePath("/more/settings");
  return { ended: Number(data ?? 0) };
}
