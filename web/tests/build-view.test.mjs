import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const V = loader()(new URL("../lib/build-view.ts", import.meta.url));
const leg = (label, x) => ({ label, player: "", team: "", price: -110, p: 0.5, p_pack: 0.5, ...x });

const GAME = "Chicago Bulls @ New York Knicks";
const LEGS = [
  leg("Chicago Bulls ML", { team: "CHI", stat: "moneyline", side: "yes", price: 245, p: 0.28 }),
  leg("New York Knicks ML", { team: "NYK", stat: "moneyline", side: "yes", price: -300, p: 0.72 }),
  leg("Chicago Bulls +7.5", { team: "CHI", stat: "spread", side: "yes", point: 7.5, p: 0.5 }),
  leg("New York Knicks -7.5", { team: "NYK", stat: "spread", side: "yes", point: -7.5, p: 0.5 }),
  leg("Chicago Bulls +3.5", { team: "CHI", stat: "spread", side: "yes", point: 3.5, p: 0.36 }),
  leg("New York Knicks -3.5", { team: "NYK", stat: "spread", side: "yes", point: -3.5, p: 0.64 }),
  leg("Over 228.5 total points", { stat: "total", side: "over", point: 228.5, p: 0.51 }),
  leg("Under 228.5 total points", { stat: "total", side: "under", point: 228.5, p: 0.49 }),
  leg("Over 220.5 total points", { stat: "total", side: "over", point: 220.5, p: 0.7 }),
  leg("Jalen Brunson over 24.5 points", { player: "Jalen Brunson", stat: "points", side: "over", point: 24.5, price: -135, p: 0.6 }),
  leg("Jalen Brunson over 19.5 points", { player: "Jalen Brunson", stat: "points", side: "over", point: 19.5, price: -400, p: 0.78 }),
  leg("Jalen Brunson under 24.5 points", { player: "Jalen Brunson", stat: "points", side: "under", point: 24.5, p: 0.4 }),
  leg("Mikal Bridges over 1.5 threes", { player: "Mikal Bridges", stat: "threes", side: "over", point: 1.5, price: -120, p: 0.58 }),
  leg("Josh Hart over 9.5 rebounds", { player: "Josh Hart", stat: "rebounds", side: "over", point: 9.5, price: 150, p: 0.3 }),
  leg("OG Anunoby over 14.5 points", { player: "OG Anunoby", stat: "points", side: "over", point: 14.5, price: -115, p: 0.55 }),
];

test("the main lines: the rung closest to even, each team on its row, over above under", () => {
  const m = V.mainLines(LEGS, GAME, ["CHI", "NYK"]);
  assert.deepEqual(m.cols, ["spread", "total", "win"]);
  assert.deepEqual(m.rows.map((r) => r.name), ["Chicago Bulls", "New York Knicks"]);
  assert.deepEqual(m.rows.map((r) => r.cells.spread.label), ["Chicago Bulls +7.5", "New York Knicks -7.5"]);
  assert.deepEqual(m.rows.map((r) => r.cells.total.label), ["Over 228.5 total points", "Under 228.5 total points"]);
  assert.deepEqual(m.rows.map((r) => r.cells.win.label), ["Chicago Bulls ML", "New York Knicks ML"]);
  assert.equal(V.mainText("spread", m.rows[0].cells.spread), "+7.5");
  assert.equal(V.mainText("total", m.rows[1].cells.total), "U 228.5");
  assert.equal(V.mainText("win", m.rows[0].cells.win), "");
});

test("a three-way game: no spread column, the draw on its own row", () => {
  const m = V.mainLines([
    leg("AC Milan to win", { team: "AC Milan", stat: "moneyline", side: "yes" }),
    leg("Ferencváros TC to win", { team: "Ferencváros TC", stat: "moneyline", side: "yes" }),
    leg("Draw", { stat: "draw", side: "yes" }),
  ], "Ferencváros TC @ AC Milan");
  assert.deepEqual(m.cols, ["win"]);
  assert.deepEqual(m.rows.map((r) => [r.name, r.cells.win.label]), [["Ferencváros TC", "Ferencváros TC to win"], ["AC Milan", "AC Milan to win"], ["Draw", "Draw"]]);
  assert.equal(V.mainLines([], "A @ B"), null);
});

test("popular props: one per player, overs inside 50-80%, best priced first, never a banned player", () => {
  const got = V.popularProps(LEGS, "nba", []).map((l) => l.label);
  assert.deepEqual(got, ["Mikal Bridges over 1.5 threes", "Jalen Brunson over 24.5 points", "OG Anunoby over 14.5 points"]);
  const banned = V.popularProps(LEGS, "nba", [{ kind: "player", name: "Jalen Brunson" }]).map((l) => l.label);
  assert.ok(!banned.some((l) => l.includes("Brunson")));
  assert.equal(V.propText(LEGS[9]), "Over 24.5 points");
});

test("the best book is the one that pays most among known prices", () => {
  assert.equal(V.bestBook({ FanDuel: 412, DraftKings: 405, Novig: 430 }), "Novig");
  assert.equal(V.bestBook({ FanDuel: -120, DraftKings: -110, Novig: null }), "DraftKings");
  assert.equal(V.bestBook({ FanDuel: null }), null);
});

test("a wallet token fits a slip by book, sport, teams and terms", () => {
  const tok = { promo_id: "p", kind: "boost", book: "DraftKings", amount_dollars: 25, pct: 50, max_extra_dollars: null, min_legs: 3, min_odds: null, max_odds: null,
    sports: ["nba"], teams: null, note: null, expires_at: null, status: "open" };
  const slip = { book: "DraftKings", sport: "nba", matchups: [GAME], legs: 3, dec: 5 };
  assert.equal(V.tokenFits(tok, slip), true);
  assert.equal(V.tokenFits(tok, { ...slip, book: "FanDuel" }), false);
  assert.equal(V.tokenFits(tok, { ...slip, sport: "nhl" }), false);
  assert.equal(V.tokenFits(tok, { ...slip, legs: 2 }), false);
  assert.equal(V.tokenFits(tok, { ...slip, legs: 2, dec: null }), false);
  assert.equal(V.tokenFits({ ...tok, teams: ["Celtics"] }, slip), false);
  assert.equal(V.tokenFits({ ...tok, book: null, teams: ["Knicks"] }, { ...slip, book: "Novig" }), true);
});

test("stored slips: a price per book; the old single price is dropped; started games' legs go", () => {
  const { slips, sport } = V.readSlips({ _sport: "nba",
    nba: { legs: [{ event_id: "a", label: "x" }, { event_id: "gone", label: "y" }], price: "+450" },
    nhl: { legs: [{ event_id: "a", label: "z" }], prices: { FanDuel: "+300", Novig: "+320", Other: "1" } }, junk: 4 }, (e) => e === "a");
  assert.equal(sport, "nba");
  assert.deepEqual(slips, { nba: { legs: [{ event_id: "a", label: "x" }], prices: {} }, nhl: { legs: [{ event_id: "a", label: "z" }], prices: { FanDuel: "+300" } } });
});
