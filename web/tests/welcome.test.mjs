import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const W = loader()(new URL("../lib/welcome.ts", import.meta.url));
const swift = readFileSync(new URL("../../ios/BetLab/Me/WelcomeView.swift", import.meta.url), "utf8").replaceAll('\\"', '"');

test("the welcome says the same in both apps", () => {
  for (const s of [...W.WELCOME.flatMap((p) => [p.title, ...p.lines]), W.WELCOME_UNIT.title, W.WELCOME_UNIT.line, W.WELCOME_UNIT.help]) {
    assert.ok(swift.includes(s), s);
  }
});
