import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { loader } from "./load-ts.mjs";

const D = loader()(new URL("../lib/devices.ts", import.meta.url));
const FIX = JSON.parse(readFileSync(new URL("../../tests/fixtures/devices.json", import.meta.url), "utf8"));

test("a session's device name from its user agent (shared fixture)", () => {
  for (const [ua, name] of FIX.cases) assert.equal(D.deviceName(ua), name, ua);
});
