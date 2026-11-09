import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

// Execute the actual pure TypeScript modules, including their dependencies,
// without importing Next.js server-only data or adding a test-runner dependency.
const modules = new Map();
function load(url) {
  const key = url.href;
  if (modules.has(key)) return modules.get(key).exports;
  const module = { exports: {} };
  modules.set(key, module);
  const code = ts.transpileModule(readFileSync(url, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const run = vm.runInThisContext(`(function(require, module, exports) {\n${code}\n})`, {
    filename: fileURLToPath(url),
  });
  run((name) => load(new URL(`${name}.ts`, url)), module, module.exports);
  return module.exports;
}
const { profit, personalClv, record, bucketUsed, atRiskOn, bookOfBet, recordBets, bonusSummary } = load(new URL("../lib/bets.ts", import.meta.url));
const bet = (fields = {}) => ({ kind: "pick", mode: "real", stake: 2, price: 120,
  pick_status: "won", ticket_status: null, profit_flat: 1.2, profit_1u: null,
  league: "nfl", market: "spreads", pick_kind: "game", logged_price: 120,
  close_push: 0, clv: 0.1, clv_raw: null, ...fields });
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-10, `${actual} != ${expected}`);

test("winnings use the user's price and the stake in units (no dollars or bankroll since Oct 12)", () => {
  near(profit(bet({ price: 150, stake: 3 })), 4.5);
  near(profit(bet({ price: -125, stake: 3 })), 2.4);
});
test("missing-price winnings scale both single and parlay fallback profit by stake", () => {
  near(profit(bet({ price: null })), 2.4);
  near(profit(bet({ price: null, kind: "custom", profit_flat: null, profit_1u: 1.5 })), 3);
  near(profit(bet({ price: null, stake: 3 })), 3.6);
  assert.equal(profit(bet({ price: null, profit_flat: null })), null);
});
test("losses, pushes, voids, open bets and paper stakes retain their settlement behavior", () => {
  assert.equal(profit(bet({ pick_status: "lost" })), -2);
  assert.equal(profit(bet({ pick_status: "push" })), 0);
  assert.equal(profit(bet({ pick_status: "void" })), 0);
  assert.equal(profit(bet({ pick_status: "open" })), null);
  near(profit(bet({ mode: "paper", stake: null, price: null })), 1.2);
});
test("a Novig slip counts a void leg at its fair value, below the stake if need be (Oct 28)", () => {
  const legs = (...r) => r.map((result, i) => ({ leg: `L${i}`, result, p: result === "void" ? 0.4 : null }));
  near(profit(bet({ book: "Novig", price: 100, leg_results: legs("won", "void") })), 2 * (2 * 0.4 - 1));
  near(profit(bet({ book: "Novig", price: 500, pick_status: "void", leg_results: legs("void", "void") })), 2 * (6 * 0.16 - 1));
  near(profit(bet({ book: "FanDuel", price: 100, leg_results: legs("won", "void") })), 0);
  near(profit(bet({ book: "Novig", price: 150, stake: 3 })), 4.5);
});
test("a different personal price changes CLV and the record's beat-close count", () => {
  const worse = bet({ price: -125 });
  near(personalClv(worse), -0.1); // original +120, fair close 50%; own -125
  near(personalClv(bet({ price: 150 })), 0.25);
  const r = record([worse, bet({ price: 150 })]);
  assert.equal(r.total.clvN, 2);
  assert.equal(r.total.beat, 1);
  near(r.total.clvSum, 0.15);
});
test("football CLV retains closing pushes when repriced", () => {
  // 45% win, 10% push, 45% loss: at +120 CLV is 9%, at +150 it is 22.5%.
  near(personalClv(bet({ clv: 0.09, close_push: 0.1, price: 150 })), 0.225);
});
test("props use the raw close, never the retired corrected close", () => {
  near(personalClv(bet({ pick_kind: "prop", clv: 0.3, clv_raw: 0.1, price: 150 })), 0.25);
  assert.equal(personalClv(bet({ pick_kind: "prop", clv: 0.3, clv_raw: null })), null);
  assert.equal(personalClv(bet({ pick_kind: null, market: "player_receptions", clv: 0.3, clv_raw: null })), null);
});
test("missing closing data is excluded instead of counting the model's CLV at a new price", () => {
  assert.equal(personalClv(bet({ close_push: null, price: 150 })), null);
  assert.equal(personalClv(bet({ logged_price: undefined })), null);
  assert.equal(personalClv(bet({ clv: null })), null);
  near(personalClv(bet({ close_push: null })), 0.1);
  near(personalClv(bet({ price: null, close_push: null })), 0.1);
  assert.equal(record([bet({ price: 150, close_push: null })]).total.clvN, 0);
});
test("parlays and invalid price/push data never produce personal CLV", () => {
  for (const fields of [{ kind: "parlay" }, { kind: "custom" }, { price: 0 }, { price: 150, close_push: 2 }]) {
    assert.equal(personalClv(bet(fields)), null);
  }
});

test("a parlay with a void leg pays at the price without that leg (Oct 10)", () => {
  const legs = [{ leg: "A", result: "won" }, { leg: "B", result: "void", p: 0.5 }, { leg: "C", result: "won" }];
  const t = bet({ kind: "parlay", pick_status: null, ticket_status: "won", price: 500, stake: 1, leg_results: legs });
  near(profit(t), 6 * 0.5 - 1);                              // +500 is 6.0; the void leg at 50% halves it: +200
  const short = bet({ kind: "parlay", pick_status: null, ticket_status: "won", price: -150, stake: 1,
    leg_results: [{ leg: "A", result: "won" }, { leg: "B", result: "void", p: 0.3 }] });
  near(profit(short), 0);                                     // never below the stake back
});

test("the fun bucket and the daily cap count units: a stake, or 1u when none is set", () => {
  const now = new Date("2026-10-20T16:00:00Z");
  const parlays = [{ kind: "parlay", mode: "real", stake: 0.5, placed_at: "2026-10-19T16:00:00Z" },
    { kind: "custom", mode: "paper", stake: null, placed_at: "2026-10-02T16:00:00Z" },
    { kind: "parlay", mode: "real", stake: 2, placed_at: "2026-09-30T16:00:00Z" },     // last month
    { kind: "pick", mode: "real", stake: 1, placed_at: "2026-10-19T16:00:00Z" }];     // not a parlay
  near(bucketUsed(parlays, now), 1.5);
  const day = [bet({ pick_status: "open", stake: 2, placed_at: "2026-10-20T15:00:00Z" }),
    bet({ pick_status: "open", stake: null, placed_at: "2026-10-20T15:00:00Z" }),
    bet({ pick_status: "open", mode: "paper", stake: 1, placed_at: "2026-10-20T15:00:00Z" })];
  near(atRiskOn(day, "2026-10-20"), 3);
});

test("the record by book: DraftKings bets on their own row, older bets count as FanDuel's", () => {
  const rows = [bet({ price: 150, book: "DraftKings" }), bet({ price: 120, book: "FanDuel" }), bet({ price: 110 })];
  const r = record(rows, bookOfBet);
  const by = Object.fromEntries(r.lines.map((l) => [l.group, l.bets]));
  assert.deepEqual(by, { FanDuel: 2, DraftKings: 1 });
  assert.equal(r.total.bets, 3);
});

test("Novig bets (the Novig sync's, Oct 23) get their own row and grade like any custom bet", () => {
  const nv = bet({ kind: "custom", book: "Novig", price: 105, stake: 0.5, pick_status: null, ticket_status: "won",
                   sgp_id: "novig-abc", label: "Rangers ML · Novig $2.50 (auto)" });
  near(profit(nv), 0.525);
  const r = record([nv, bet({ book: "FanDuel" })], bookOfBet);
  assert.deepEqual(Object.fromEntries(r.lines.map((l) => [l.group, l.bets])), { FanDuel: 1, Novig: 1 });
});

test("from Oct 18 the record counts real bets only, starting at 0-0; paper stays apart", () => {
  const paperWin = { mode: "paper", kind: "pick", price: 100, pick_status: "won", placed_at: "2026-10-12T15:00:00Z" };
  const paperParlay = { mode: "paper", kind: "parlay", stake: 2, price: 500, ticket_status: "lost", placed_at: "2026-10-12T15:00:00Z" };
  // before real money: everything counts (paper)
  let r = recordBets([paperWin, paperParlay], false);
  assert.equal(r.useReal, false);
  assert.equal(record(r.counted).total.won, 1);
  // Oct 18, no real bet marked yet: a clear record
  r = recordBets([paperWin, paperParlay], true);
  assert.equal(r.useReal, true);
  assert.equal(record(r.counted).total.bets, 0);
  assert.equal(bucketUsed(r.counted, new Date("2026-10-18T16:00:00Z")), 0);
  assert.equal(r.paper.length, 2);
  // the first real bet counts alone
  const realLoss = { mode: "real", kind: "pick", stake: 1, price: -110, pick_status: "lost", placed_at: "2026-10-18T16:00:00Z" };
  r = recordBets([paperWin, paperParlay, realLoss], true);
  assert.deepEqual([record(r.counted).total.won, record(r.counted).total.lost], [0, 1]);
});

test("a bonus bet pays its profit only, and a loss costs nothing (Oct 19: promo credits)", () => {
  const b = (f) => bet({ bonus: true, kind: "custom", pick_status: null, stake: 2, price: 400, ...f });
  near(profit(b({ ticket_status: "won" })), 8);           // 2u at +400: the 8u profit, no stake back
  assert.equal(profit(b({ ticket_status: "lost" })), 0);
  assert.equal(profit(b({ ticket_status: "void" })), 0);
  near(profit(bet({ pick_status: "lost", stake: 2 })), -2);  // cash bets unchanged
});

test("bonus bets stay out of staked units, the daily cap and the fun bucket, but their winnings count", () => {
  const today = new Date().toISOString();
  const cash = bet({ kind: "custom", pick_status: null, ticket_status: "lost", stake: 1, price: 300, placed_at: today });
  const won = bet({ kind: "custom", pick_status: null, ticket_status: "won", stake: 2, price: 400, bonus: true, placed_at: today });
  const { total } = record([cash, won]);
  near(total.staked, 1);
  near(total.units, 7);                                  // -1 cash, +8 from the bonus win
  const open = (f) => bet({ kind: "custom", pick_status: null, ticket_status: null, stake: 3, price: 300,
                            placed_at: today, ticket_commence_time: today, ...f });
  const day = new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  near(atRiskOn([open({}), open({ bonus: true })], day), 3);
  near(bucketUsed([open({}), open({ bonus: true })]), 3);
});

test("the bonus line: face used, what it turned into, and the conversion rate", () => {
  const b = (f) => bet({ bonus: true, kind: "custom", pick_status: null, price: 400, ...f });
  const s = bonusSummary([b({ ticket_status: "won", stake: 1 }), b({ ticket_status: "lost", stake: 3 }),
                          b({ ticket_status: "void", stake: 5 }), b({ ticket_status: null, stake: 2 }), bet({})]);
  assert.deepEqual([s.bets, s.settled, s.won], [4, 2, 1]);
  near(s.face, 4);
  near(s.converted, 4);
  near(s.rate, 1);
  assert.equal(bonusSummary([bet({})]).rate, null);
});

test("a cash-out settles the bet at what the book paid back, whatever the legs do (Oct 22)", () => {
  const { statusOf } = load(new URL("../lib/bets.ts", import.meta.url));
  const cashed = bet({ kind: "parlay", stake: 1, price: 1398, pick_status: null, ticket_status: "lost", cashout: 1.058 });
  assert.equal(statusOf(cashed), "cashout");
  near(profit(cashed), 0.058);                                   // $5.29 back on $5
  near(profit({ ...cashed, ticket_status: null }), 0.058);       // before the ticket grades too
  near(profit({ ...cashed, bonus: true }), 1.058);               // a bonus bet's cash-out is all profit
});

test("a profit boost multiplies a win's profit; the price stays the book's own (Oct 22)", () => {
  const { boostSummary } = load(new URL("../lib/bets.ts", import.meta.url));
  const kmet = bet({ kind: "custom", stake: 2, price: 178, pick_status: null, ticket_status: "won", boost: 100 });
  near(profit(kmet), 2 * 1.78 * 2);                                    // +7.12u: $10 paid $45.60
  near(profit({ ...kmet, ticket_status: "lost" }), -2);
  const s = boostSummary([kmet, bet({ kind: "custom", stake: 1, price: 325, pick_status: null, ticket_status: "lost", boost: 30 })]);
  near(s.units, 7.12 - 1); near(s.fromBoost, 3.56); assert.equal(s.won, 1); near(s.staked, 3);
});

test("a bet without a start of its own files by its first game's kickoff (Oct 25: time order at all times)", () => {
  const B = load(new URL("../lib/bets.ts", import.meta.url));
  const starts = { "nfl:2026_07_PIT_NO": "2026-10-25T13:30:00+00:00", "nfl:2026_07_GB_DET": "2026-10-25T20:25:00+00:00" };
  const b = { games: [{ matchup: "GB @ DET", game_ref: "2026_07_GB_DET", legs: [] }, { matchup: "PIT @ NO", game_ref: "2026_07_PIT_NO", legs: [] },
                      { matchup: "x", game_ref: "nba|CHI|WSH|2026-10-24T23:10:00+00:00", legs: [] }] };
  assert.equal(B.gameStart(b, starts), "2026-10-24T23:10:00.000Z");
  assert.equal(B.gameStart({ games: [{ matchup: "GB @ DET", game_ref: "2026_07_GB_DET", legs: [] }] }, starts), "2026-10-25T20:25:00.000Z");
  assert.equal(B.gameStart({ games: [{ matchup: "fight", game_ref: "ufc:6:4", legs: [] }] }, starts), null);
  assert.equal(B.startOf({ game_start: "2026-10-25T20:25:00.000Z" }), "2026-10-25T20:25:00.000Z");
});

test("the record counts a push as a loss and a cash-out as its bet settled (Mike, Oct 26)", () => {
  const { record: rec } = load(new URL("../lib/bets.ts", import.meta.url));
  const b = (x) => bet({ kind: "custom", pick_status: null, ticket_status: "open", price: 200, stake: 1, ...x });
  const r = rec([
    b({ ticket_status: "won" }),
    b({ ticket_status: "push" }),                       // a loss in the record, 0 in P/L
    b({ ticket_status: "lost", cashout: 1.5 }),         // cashed out, then its bet lost: a loss, +0.5u
    b({ ticket_status: "open", cashout: 0.4 }),         // cashed out, its games still on: not in the W-L yet, -0.6u
    b({ ticket_status: "void" }),
  ]).total;
  assert.deepEqual([r.bets, r.won, r.lost, r.push], [5, 1, 2, 1]);
  near(r.units, 2 + 0 + 0.5 - 0.6 + 0);
});

test("Bet Protect+ takes 3% of the stake off every settled bet but a void (Oct 26)", () => {
  const { profit: pr } = load(new URL("../lib/bets.ts", import.meta.url));
  const b = (x) => bet({ kind: "custom", pick_status: null, price: 911, stake: 2, protect: true, ...x });
  near(pr(b({ ticket_status: "won", bonus: true })), 2 * 9.11 - 0.06);   // Oct 19: a bonus bet still pays the fee in cash
  near(pr(b({ ticket_status: "lost" })), -2.06);
  near(pr(b({ ticket_status: "lost", bonus: true })), -0.06);
  near(pr(b({ ticket_status: "void" })), 0);
  near(pr(b({ ticket_status: "won", protect: false })), 18.22);
});

const PROMO = JSON.parse(readFileSync(new URL("../../tests/fixtures/promo_profit.json", import.meta.url), "utf8"));
for (const c of PROMO.cases) {
  test(`promo profit (shared fixture): ${c.name}`, () => {
    near(profit(bet({ kind: "custom", pick_status: null, ...c.bet })), c.profit);
  });
}

test("a boosted bonus bet counts once, as a bonus (Oct 30)", () => {
  const { boostSummary } = load(new URL("../lib/bets.ts", import.meta.url));
  const bets = PROMO.cases.map((c) => bet({ kind: "custom", pick_status: null, ...c.bet }));
  const boost = boostSummary(bets), bonus = bonusSummary(bets);
  assert.equal(boost.bets, 4);                           // the cash boosts only
  assert.equal(bonus.bets, 5);
  near(boost.fromBoost, 1 + 0.5 + 0.3);                  // each win's boost, within its cap
});
