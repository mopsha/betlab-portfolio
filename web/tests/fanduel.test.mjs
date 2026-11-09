import assert from "node:assert/strict";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const { fdHref, appLink, isIOS, mainLineText } = loader()(new URL("../lib/fanduel.ts", import.meta.url));

test("app link keeps the New York host in the path (round 3 'K')", () => {
  const web = fdHref(["https://sportsbook.fanduel.com/addToBetslip?marketId=42.5&selectionId=7"]);
  assert.equal(web, "https://ny.sportsbook.fanduel.com/addToBetslip?marketId=42.5&selectionId=7");
  assert.equal(appLink(web), "fanduelsportsbook://ny.sportsbook.fanduel.com/addToBetslip?marketId=42.5&selectionId=7");
});

test("parlay links go through the app scheme too", () => {
  const web = fdHref(["https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=2",
                      "https://sportsbook.fanduel.com/addToBetslip?marketId=3&selectionId=4"]);
  assert.match(appLink(web), /^fanduelsportsbook:\/\/ny\.sportsbook\.fanduel\.com\/addToBetslip\?marketId\[0\]=1/);
});

test("a parlay with one linked leg gets no link: it would open as a single bet (Nov 5)", () => {
  const leg = "https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=2";
  assert.equal(fdHref([null, leg, null]), null);
  assert.match(fdHref([leg, null, leg]), /marketId\[1\]=1/);
});

test("only iPhone and iPad get the app link", () => {
  assert.equal(isIOS("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"), true);
  assert.equal(isIOS("Mozilla/5.0 (Windows NT 10.0; Win64; x64)"), false);
});

test("legs linked to a main market say to check the number (Oct 30, Brunson 1.5 -> 2.5)", () => {
  assert.equal(mainLineText([false, undefined]), null);
  assert.equal(mainLineText([true]), "Check the number on FanDuel's slip: this link follows FanDuel's main line, which can move.");
  assert.equal(mainLineText([true, false, true], "DraftKings"),
    "Check the number on 2 of these legs on DraftKings' slip: their links follow DraftKings' main line, which can move.");
});
