// Share cards (Mike's W13, Oct 24): a bet as a picture to send. This is the card's content, pure so the tests run it;
// app/api/share/[id] draws it. A parlay that lost by one leg says so: the brutal ones are worth sharing too.
import { isBonus, isSettled, profit, stakeOf, statusOf } from "./bets";
import type { MyBet } from "./data";
import { fmtAm, label, num } from "./format";
import { bookOfBet } from "./bets";
import { betName } from "./gameday";

export type CardLeg = { label: string; result: "won" | "lost" | "void" | "open"; value: string | null };
export type Card = { status: string; tone: "win" | "loss" | "even" | "open"; title: string; price: string; legs: CardLeg[];
  more: number; headline: string; detail: string; book: string; when: string };

const MAX_LEGS = 10;

export function card(b: MyBet, now = new Date()): Card {
  const s = statusOf(b), settled = isSettled(b), p = profit(b);
  const results = b.leg_results ?? [];
  const labels = b.legs?.length ? b.legs : b.label ? [b.label] : [];
  const used = new Set<number>();
  const legs: CardLeg[] = labels.map((l) => {
    const i = results.findIndex((r, k) => !used.has(k) && r.leg === l);        // repeated labels ("Over 2.5 goals") in order
    if (i >= 0) used.add(i);
    const r = i >= 0 ? results[i] : null;
    const res = r?.result === "won" || r?.result === "lost" ? r.result : r?.result === "void" || r?.result === "push" ? "void" : settled && labels.length === 1 && (s === "won" || s === "lost") ? s : "open";
    return { label: label(l), result: res as CardLeg["result"], value: r?.value != null ? String(r.value) : null };
  });
  const lostLegs = legs.filter((l) => l.result === "lost").length;
  const oneAway = s === "lost" && legs.length > 1 && lostLegs === 1 && legs.every((l) => l.result !== "open");
  const stake = stakeOf(b), price = num(b.price);
  const toWin = price !== null ? stake * ((price > 0 ? price / 100 : 100 / -price)) * (1 + (num(b.boost) ?? 0) / 100) : null;
  const u = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(2)}u`;
  const tone: Card["tone"] = s === "won" ? "win" : s === "lost" ? "loss" : settled ? "even" : "open";
  const status = s === "won" ? "WON" : s === "lost" ? (oneAway ? "ONE LEG AWAY" : "LOST") : s === "cashout" ? "CASHED OUT" : settled ? s.toUpperCase() : "OPEN";
  const money = isBonus(b) ? `${stake}u bonus bet` : `${stake}u${(num(b.boost) ?? 0) > 0 ? ` · ${num(b.boost)}% boost` : ""}`;
  return {
    status, tone,
    title: betName({ legs: labels, price: null }, labels.length),
    price: price !== null ? fmtAm(price) + ((num(b.boost) ?? 0) > 0 ? ` → ${fmtAm(Math.round(price > 0 ? price * (1 + num(b.boost)! / 100) : (100 / -price) * (1 + num(b.boost)! / 100) * 100))}` : "") : "",
    legs: legs.slice(0, MAX_LEGS), more: Math.max(0, legs.length - MAX_LEGS),
    headline: settled && p !== null ? u(p) : toWin !== null ? `to win ${u(toWin).slice(1)}` : "",
    detail: oneAway ? `${legs.length - 1} of ${legs.length} hit · ${money}` : money,
    book: bookOfBet(b),
    when: new Date(b.placed_at ?? now).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", year: "numeric" }),
  };
}
