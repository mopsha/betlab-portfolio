import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const { dkHref } = loader()(new URL("../lib/draftkings.ts", import.meta.url));
const DK = "https://sportsbook.draftkings.com/?outcomes=";

test("a single bet keeps the feed's link (round 2 'E')", () => {
  assert.equal(dkHref([`${DK}0ML86264675_3`]), `${DK}0ML86264675_3`);
});

test("a parlay joins its outcome ids with an encoded plus (round 3 'J')", () => {
  assert.equal(dkHref([`${DK}0ML86264675_3`, `${DK}0OU86264804O250_1`]), `${DK}0ML86264675_3%2B0OU86264804O250_1`);
});

test("an outcome id with a '#' stays encoded inside the parlay", () => {
  const btts = `${DK}0QA368995794%232280997250_13L40685Q11714Q20`;
  assert.equal(dkHref([`${DK}0ML1_3`, btts]), `${DK}0ML1_3%2B0QA368995794%232280997250_13L40685Q11714Q20`);
});

test("no link unless every leg has a DraftKings link", () => {
  assert.equal(dkHref([`${DK}0ML1_3`, undefined]), null);
  assert.equal(dkHref([`${DK}0ML1_3`, "https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=2"]), null);
  assert.equal(dkHref([]), null);
});
