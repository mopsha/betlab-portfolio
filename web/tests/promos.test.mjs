import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const P = loader()(new URL("../lib/promos.ts", import.meta.url));
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/promos.json", import.meta.url), "utf8"));
const now = new Date(FIX.now);
const byId = Object.fromEntries(FIX.promos.map((p) => [p.promo_id, p]));

test("a token for one market and certain games (shared fixture)", () => {
  const B = loader()(new URL("../lib/builder.ts", import.meta.url));
  for (const c of FIX.market_fits) assert.equal(B.marketFits(c.market, { stat: c.stat, player: c.player }, c.kinds), c.want, JSON.stringify(c));
  for (const c of FIX.fits_game) assert.equal(P.tokenFitsGame(c, c.event, c.matchup, c.start ?? ""), c.want, JSON.stringify(c));
});

test("a token's wager and what a bonus bet leaves", () => {
  for (const c of FIX.wager) assert.equal(P.wagerOf(c.typed, c.max) ?? null, c.want, JSON.stringify(c));
  for (const c of FIX.bonus_left) assert.equal(P.bonusLeft(c.face, c.dollars), c.want, JSON.stringify(c));
});

test("the wallet: open soonest-expiring first, the rest after (shared fixture)", () => {
  const w = P.wallet(FIX.promos, now);
  assert.deepEqual(w.open.map((p) => p.promo_id), FIX.expect.open);
  assert.deepEqual(w.done.map((p) => p.promo_id), FIX.expect.done);
  assert.deepEqual(P.expiringSoon(FIX.promos, now).map((p) => p.promo_id), FIX.expect.soon);
  for (const [id, s] of Object.entries(FIX.expect.state)) assert.equal(P.promoState(byId[id], now), s, id);
});

test("each token in words: title, terms, expiry (shared fixture)", () => {
  for (const [id, t] of Object.entries(FIX.expect.title)) assert.equal(P.promoTitle(byId[id]), t, id);
  for (const [id, t] of Object.entries(FIX.expect.terms)) assert.equal(P.promoTerms(byId[id]), t, id);
  for (const [id, t] of Object.entries(FIX.expect.expires)) assert.equal(P.expiresText(byId[id], now), t, id);
});

test("a token becomes the finder's promo, and a bad one isn't saved", () => {
  assert.deepEqual(JSON.parse(JSON.stringify(P.asPromo(byId.b))), { kind: "boost", pct: 30, maxExtra: 10, stake: 25, minLegs: 3, minOdds: -200 });
  assert.equal(P.cleanPromo({ kind: "boost" }).row, null);
  assert.equal(P.cleanPromo({ kind: "bonus", amount_dollars: 0 }).row, null);
  const ok = P.cleanPromo({ kind: "bonus", amount_dollars: 50, book: "FanDuel", min_odds: 5, sports: ["NFL "] }).row;
  assert.equal(ok.min_odds, null);                 // not American odds
  assert.deepEqual(ok.sports, ["nfl"]);
});

test("a token's sports: its own, else the ones its note names (Oct 30: \"NBA Only\" in a note; shared fixture)", () => {
  for (const [note, want] of FIX.expect.note_sports) assert.deepEqual(P.promoSports({ sports: null, note }), want, note);
  assert.deepEqual(P.promoSports({ sports: ["nfl"], note: "NBA only" }), ["nfl"]);         // the field wins
  assert.equal(P.promoTerms({ ...byId.c, note: "NBA Only" }), "−200 to +2000 · NBA");
});

test("a token for some games: its teams, split and matched to a game's side (Oct 31; shared fixture)", () => {
  for (const [text, want] of FIX.expect.split_teams) assert.deepEqual(P.splitTeams(text), want, text);
  for (const [teams, matchup, want] of FIX.expect.team_fits) assert.equal(P.teamFits(teams, matchup), want, `${teams} in ${matchup}`);
  assert.equal(P.promoTerms({ ...byId.c, teams: ["Knicks"] }), "−200 to +2000 · Knicks games");
});

test("I used it: the bets a token may have gone on (Oct 31: a Novig bonus saved without its token; shared fixture)", () => {
  const U = FIX.used_on;
  for (const c of U.cases) assert.deepEqual(P.usedOnChoices(c.promo, U.bets, now).map((b) => b.bet_id), c.want, JSON.stringify(c.promo));
});

test("a token is cleaned before it's saved: sports as the finder's keys, out-of-range limits dropped (Nov 9; shared fixture)", () => {
  for (const c of FIX.clean.cases) {
    const { row, error } = P.cleanPromo(c.in);
    if (c.error) { assert.equal(row, null, JSON.stringify(c.in)); assert.equal(error, c.error); continue; }
    for (const [k, v] of Object.entries(c.want)) assert.deepEqual(row[k], v, `${k} of ${JSON.stringify(c.in)}`);
  }
});

test("a read token's expiry goes out in Eastern time with its offset (Nov 9; shared fixture)", () => {
  for (const [v, want] of FIX.expiry.cases) assert.equal(P.etExpiry(v), want, String(v));
});

test("/api/promos sends each token cleaned, with the id and status the iPhone decodes (Nov 9; shared fixture)", () => {
  const read = [
    { kind: "boost", book: "FanDuel", amount_dollars: 25, pct: 30, max_extra_dollars: null, min_legs: 3, min_odds: null, max_odds: null,
      sports: ["NFL"], teams: null, market: null, expires_at: "2026-11-10T04:59:00Z", note: null },
    { kind: "boost", book: "DraftKings", amount_dollars: 10, pct: null, max_extra_dollars: 0, min_legs: null, min_odds: null, max_odds: null,
      sports: null, teams: null, market: null, expires_at: null, note: "SGP only" },
  ];
  assert.deepEqual(JSON.parse(JSON.stringify(read.map(P.promoDraft))), FIX.draft_answer.promos);
});

test("a token placed must still be open (Nov 9: a used token could go on a second bet; shared fixture)", () => {
  for (const [id, want] of FIX.usable.cases) assert.equal(P.promoUsable(byId[id], now), want, id);
});

test("a slip read from a screenshot offers the wallet tokens it may have used (Nov 9; shared fixture)", () => {
  const rows = [...FIX.promos, ...FIX.slip_tokens.tokens];
  for (const c of FIX.slip_tokens.cases) {
    assert.deepEqual(P.slipTokens(c.slip, rows, now).map((p) => p.promo_id), c.want, JSON.stringify(c.slip));
    assert.equal(P.slipToken(c.slip, rows, now)?.promo_id ?? null, c.pick, JSON.stringify(c.slip));
  }
});

test("leg kinds, a read token's game and a boost's expiry (shared fixture, Nov 9)", () => {
  for (const c of FIX.clean_kinds) assert.deepEqual(P.cleanKinds(c.in), c.want, JSON.stringify(c));
  const tg = FIX.team_games;
  for (const c of tg.cases) {
    const out = P.teamGames(c.in, tg.schedule, new Date(tg.now));
    assert.deepEqual(out.games?.map((g) => g.event_id) ?? null, c.want_games, JSON.stringify(c));
    assert.deepEqual(P.splitTeams(out.teams), c.want_teams, JSON.stringify(c));
    assert.deepEqual(out.sports ?? null, c.want_sports, JSON.stringify(c));
  }
  for (const c of FIX.boost_expiry) assert.equal(P.boostExpiry(c.in).expires_at ?? null, c.want, JSON.stringify(c));
  assert.deepEqual(P.unpricedKinds({ leg_kinds: ["tds", "first_td"] }), ["first_td"]);
});

test("each screenshot's book, settled across the batch (shared fixture, Nov 9)", () => {
  for (const c of FIX.shot_books) assert.deepEqual(P.shotBooks(c.shots, c.mine), c.want, JSON.stringify(c));
});
